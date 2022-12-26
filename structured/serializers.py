"""
Defines the Serializer API type, along with a few common implementations of it:
 - NullSerializer: A placeholder type used as an initial value for `sum`
 - StructSerializer: A basic wrapper around struct.Struct
 - StructActionSerializer: StructSerializer, with transformations applied to
     unpacked values.
 - CompoundSerializer: A serializer that combines two normally incompatible
     serializers.
Serializers also support combining with addition, and StructSerializers (based
on struct.Struct) support multiplication by an integer.

The Serializer API is almost identical to struct.Struct, with a few additions
and one alteration:
 - New method 'preprocess'.
 - New attribute `num_values`.
 - New unpacking method `unpack_read`.
 - New packing method `pack_read`.
 - New configuration method `with_byte_order`.
 - Modified packing method `pack`
 - All unpacking methods may return an iterable of values instead of a tuple.
For more details, check the docstrings on each method or attribute.
"""

from __future__ import annotations

__all__ = [
    'Serializer',
    'StructSerializer',
    'StructActionSerializer',
    'CompoundSerializer',
]

import re
import struct
from functools import cached_property, partial, reduce
from io import BytesIO
from itertools import chain, repeat
from typing import TypeVar, overload

from . import basic_types   # not fully initialized, so cant import from
from .base_types import ByteOrder
from .type_checking import (
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Generic,
    Iterable,
    ReadableBuffer,
    Self,
    T,
    Ts,
    Ss,
    WritableBuffer,
    Unpack,
)


def noop_action(x: T) -> T:
    """A noop for StructActionSerializers where no additional wrapping is
    needed.
    """
    return x


_reOverlap: re.Pattern[str] = re.compile(r'(.*?)(\d+)\D$')


def fold_overlaps(format1: str, format2: str, combine_strings: bool = False) -> str:
    """Combines two format strings into one, combining common types into counted
    versions, i.e.: 'h' + 'h' -> '2h'.  The format strings must not contain
    byte order specifiers.

    :param format1: First format string to combine, may be empty.
    :param format2: Second format string to combine, may be empty.
    :return: The combined format string.
    """
    if not format1:
        return format2
    elif not format2:
        return format1
    if (overlap := format1[-1]) == format2[0] and (
        combine_strings or overlap not in ('s', 'p')
    ):
        if match := _reOverlap.match(format1):
            prelude, count = match.groups()
            count = int(count)
        else:
            prelude = format1[:-1]
            count = 1
        count += 1
        format = f'{prelude}{count}{overlap}{format2[1:]}'
    else:
        format = format1 + format2
    return format


def split_byte_order(format: str) -> tuple[ByteOrder, str]:
    if format:
        try:
            return ByteOrder(format[0]), format[1:]
        except ValueError:
            pass
    return ByteOrder.DEFAULT, format


class Serializer(Generic[Unpack[Ts]]):
    size: int
    """A possibly dynamic attribute indicating the size in bytes for this
    Serializer to pack or unpack.  Due to serializers dealing with possibly
    dynamic data, this is only guaranteed to be up to date with the most
    recently called `pack*` or `unpack*` method.  Also note, serializers are
    shared between classes, so you really must access `size` *immediately* after
    one of these calls to ensure it's accurate.
    """
    num_values: int
    """Indicates the number of variables returned from an unpack operation, and
    the number of varialbes required for a pack operation.
    """

    def preprocess(self, partial_object: Any) -> Serializer:
        """Perform any state logic needed just prior to an pack/unpack operation
        on `partial_object`. The object will be a fully initialized instance
        for pack operations, but only a proxy object for unpack operations.
        Durin unpacking, only the attributes unpacked before this serializer are
        set on the object.

        :param partial_object: The object being packed or unpacked.
        :return: A serializer appropriate for unpacking the next attribute(s).
        """
        return self

    def pack(self, *values: Unpack[Ts]) -> bytes:
        """Pack the given values according to this Serializer's logic, returning
        the packed bytes.

        :return: The packed bytes version of the values.
        """
        raise NotImplementedError

    def pack_into(
        self,
        buffer: WritableBuffer,
        offset: int,
        *values: Unpack[Ts],
    ) -> None:
        """Pack the given values according to this Serializer's logic, placing
        them into a buffer supporting the Buffer Protocol.

        :param buffer: An object supporting the Buffer Protocol.
        :param offset: Location in the buffer to place the packed bytes.
        """
        raise NotImplementedError

    def pack_write(self, writable: BinaryIO, *values: Unpack[Ts]) -> None:
        """Pack the given values according to this Serializer's logic, placing
        them into a writable file-like object.

        :param writable: A writable file-like object.
        """
        raise NotImplementedError

    def unpack(self, buffer: ReadableBuffer) -> Iterable:
        """Unpack values from a bytes-like buffer, returning the values in a
        tuple.  Unlike `struct.pack`, the Serializer must accept a buffer that
        is larger than the needed number of bytes for unpacking.

        :param buffer: A readable bytes-like object.
        :return: The unpacked values in a tuple.
        """
        raise NotImplementedError

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> Iterable:
        """Unpack values from a buffer supporting the Buffer Protocol, returning
        the values in a tuple.

        :param buffer: A readable object supporing the Buffer Protocol.
        :param offset: Location in the buffer to draw data from.
        :return: The unpacked values in a tuple.
        """
        raise NotImplementedError

    def unpack_read(self, readable: BinaryIO) -> Iterable:
        """Unpack values from a readable file-like object, returning the values
        in a tuple.

        :param readable: A readable file-like object.
        :return: The unpacked values in a tuple.
        """
        raise NotImplementedError

    # Internal methods useful for configuring / combining serializers
    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        """Create a serializer with the same packing / unpacking logic, but
        configured to use the specified byte order.

        :param byte_order: ByteOrder to use with the new serializer.
        :return: A new serializer, or this one if no changes were needed.
        """
        return self

    def __add__(self, other: Serializer[Unpack[Ss]]) -> CompoundSerializer[Unpack[Ts], Unpack[Ss]]:
        if isinstance(other, Serializer) and not isinstance(other, NullSerializer):
            # Default is to make a CompoundSerializer joining the two.
            # Subclasses can provide an __radd__ if optimizing can be done
            return CompoundSerializer((self, other))
        return NotImplemented


TSerializer = TypeVar('TSerializer', bound=Serializer)


class NullSerializer(Serializer[Unpack[tuple[()]]]):
    """A dummy serializer to function as the initial value for sum(...)"""

    size = 0
    num_values = 0

    def pack(self, *values: Unpack[tuple[()]]) -> bytes:
        return b''

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: Unpack[tuple[()]]) -> None:
        return

    def pack_write(self, writable: BinaryIO, *values: Unpack[tuple[()]]) -> None:
        return

    def unpack(self, buffer: ReadableBuffer) -> tuple[()]:
        return ()

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[()]:
        return ()

    def unpack_read(self, readable: BinaryIO) -> tuple[()]:
        return ()

    def __add__(self, other: TSerializer) -> TSerializer:
        if isinstance(other, Serializer):
            return other
        return NotImplemented

    def __radd__(self, other: TSerializer) -> TSerializer:
        return self.__add__(other)


class StructSerializer(Generic[Unpack[Ts]], struct.Struct, Serializer[Unpack[Ts]]):
    """A Serializer that is a thin wrapper around struct.Struct, class creation
    is cached.
    """

    _instance_cache: ClassVar[dict[Any, StructSerializer]] = {}

    def __new__(cls, *args, **kwargs) -> Self:
        # Simple caching of creation.  Doesn't do any processing to detect
        # equivalent arguments
        key = tuple(chain(args, sorted(kwargs.items())))
        if cached := cls._instance_cache.get(key, None):
            return cached
        else:
            new_instance = super().__new__(cls)
            cls._instance_cache[key] = new_instance
            # __init__ is called automatically
            return new_instance

    @property
    def byte_order(self) -> ByteOrder:
        return self._split_format[0]

    @property
    def base_format(self) -> str:
        return self._split_format[1]

    @cached_property
    def _split_format(self) -> tuple[ByteOrder, str]:
        return split_byte_order(self.format)

    def __init__(
        self,
        format: str,
        num_values: int = 1,
        byte_order: ByteOrder = ByteOrder.DEFAULT,
    ) -> None:
        """Create a struct.Struct based Serializer

        :param format: Format string.
        :param num_values: Number of values which will be packed/unpacked by
            this Serializer.
        :param byte_order: ByteOrder marking for the format string.
        """
        super().__init__(byte_order.value + format)
        self.num_values = num_values

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        old_byte_order, fmt = self._split_format
        if old_byte_order is byte_order:
            return self
        else:
            return StructSerializer(fmt, self.num_values, byte_order)

    def unpack(self, buffer: ReadableBuffer) -> tuple[Unpack[Ts]]:
        return super().unpack(buffer[: self.size])  # type: ignore

    def unpack_read(self, readable: BinaryIO) -> tuple[Unpack[Ts]]:
        # NOTE: use super-class's unpack to not interfere with custom
        # logic in subclasses
        return super().unpack(readable.read(self.size)) # type: ignore

    def pack_write(self, writable: BinaryIO, *values: Unpack[Ts]) -> None:
        # NOTE: Call the super-class's pack, so we don't interfere with
        # any custom logic in pack_write for subclasses
        writable.write(super().pack(*values))

    @overload
    def __add__(self, other: StructSerializer[Unpack[Ss]]) -> StructSerializer[Unpack[Ts], Unpack[Ss]]:
        ...

    @overload
    def __add__(self, other: Serializer[Unpack[Ss]]) -> Serializer[Unpack[Ts], Unpack[Ss]]:
        ...

    def __add__(self, other: Serializer) -> Serializer:
        if isinstance(other, StructSerializer):
            # Don't need a CompoundSerializer for joining with another Struct
            byte_order, lfmt = self._split_format
            byte_order2, rfmt = other._split_format
            # TODO: Check for conflict in byte_order, byte_order2?
            return StructSerializer(
                fold_overlaps(lfmt, rfmt),
                self.num_values + other.num_values,
                byte_order,
            )
        return super().__add__(other)

    def __mul__(self, other: int) -> StructSerializer:  # no tool to hint this yet
        if not isinstance(other, int):
            return NotImplemented
        elif other <= 0:
            raise ValueError('count must be positive')
        elif other == 1:
            return self
        byte_order, fmt = self._split_format
        fmt = reduce(partial(fold_overlaps, combine_strings=True), repeat(fmt, other))
        return StructSerializer(fmt, self.num_values * other, byte_order)


class StructActionSerializer(Generic[Unpack[Ts]], StructSerializer[Unpack[Ts]]):
    """A Serializer acting as a thin wrapper around struct.Struct, with
    transformations applied to unpacked values.
    """

    def __init__(
        self,
        fmt: str,
        num_attrs: int = 1,
        byte_order: ByteOrder = ByteOrder.DEFAULT,
        actions: tuple[Callable[[Any], Any], ...] = (),
    ) -> None:
        super().__init__(fmt, num_attrs, byte_order)
        self.actions = actions

    def unpack(self, buffer: ReadableBuffer) -> tuple[Unpack[Ts]]:
        return tuple(
            action(value)
            for action, value in zip(self.actions, super().unpack(buffer))
        )   # type: ignore

    def unpack_from(self, buffer: ReadableBuffer, offset: int = ...) -> tuple[Unpack[Ts]]:
        return tuple(
            action(value)
            for action, value in zip(self.actions, super().unpack_from(buffer, offset))
        )   # type: ignore

    def unpack_read(self, readable: BinaryIO) -> tuple[Unpack[Ts]]:
        return tuple(
            action(value)
            for action, value in zip(self.actions, super().unpack_read(readable))
        )   # type: ignore

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        old_byte_order, fmt = self._split_format
        if old_byte_order is byte_order:
            return self
        return StructActionSerializer(fmt, self.num_values, byte_order, self.actions)

    def __add__(self, other: StructSerializer[Unpack[Ss]]) -> StructActionSerializer[Unpack[Ts], Unpack[Ss]]:
        if isinstance(other, StructActionSerializer):
            actions = other.actions
        elif isinstance(other, StructSerializer):
            actions = repeat(noop_action, other.num_values)
        else:
            return NotImplemented
        byte_order, lfmt = self._split_format
        _, rfmt = other._split_format
        fmt = fold_overlaps(lfmt, rfmt)
        num_values = self.num_values + other.num_values
        actions = tuple(chain(self.actions, actions))
        return StructActionSerializer(fmt, num_values, byte_order, actions)

    def __radd__(self, other: StructSerializer[Unpack[Ss]]) -> StructActionSerializer[Unpack[Ss], Unpack[Ts]]:
        # NOTE: StructActionSerializer + StructActionSerializer handled by __add__
        if isinstance(other, StructSerializer):
            actions = repeat(noop_action, other.num_values)
        else:
            return NotImplemented
        byte_order, lfmt = other._split_format
        _, rfmt = self._split_format
        fmt = fold_overlaps(lfmt, rfmt)
        num_values = self.num_values + other.num_values
        actions = tuple(chain(actions, self.actions))
        return StructActionSerializer(fmt, num_values, byte_order, actions)

    def __mul__(self, other: int) -> StructActionSerializer:    # no way to hint this yet
        if not isinstance(other, int):
            return NotImplemented
        elif other <= 0:
            raise ValueError('count must be positive')
        elif other == 1:
            return self
        byte_order, fmt = split_byte_order(self.format)
        fmt = reduce(fold_overlaps, [fmt] * other)
        num_values = self.num_values * other
        actions = tuple(chain.from_iterable(repeat(self.actions, other)))
        return StructActionSerializer(fmt, num_values, byte_order, actions)


class CompoundSerializer(Generic[Unpack[Ts]], Serializer[Unpack[Ts]]):
    """A serializer that chains together multiple serializers."""

    serializers: tuple[Serializer, ...]

    def __init__(self, serializers: tuple[Serializer, ...]) -> None:
        self.serializers = serializers
        self.size = 0
        self.num_values = sum(serializer.num_values for serializer in serializers)
        if any(isinstance(serializer, CompoundSerializer) for serializer in serializers):
            raise TypeError('cannot nest CompoundSerializers')
        self._needs_preprocess = any(serializer.preprocess is not Serializer.preprocess for serializer in serializers)

    def preprocess(self, partial_object: Any) -> Serializer:
        if not self._needs_preprocess:
            return self
        else:
            return _SpecializedCompoundSerializer(self, partial_object)

    def _iter_packers(self, values: tuple[Unpack[Ts]]) -> Iterable[tuple[Serializer, tuple[Any, ...], int]]:
        """Common boilerplate needed for iterating over sub-serializers and
        tracking which values get sent to which, as well as updating the total
        size.
        """
        size = 0
        i = 0
        for serializer in self.serializers:
            count = serializer.num_values
            yield serializer, values[i : i + count], size
            size += serializer.size
            i += count
        self.size = size

    def pack(self, *values: Unpack[Ts]) -> bytes:
        with BytesIO() as out:
            for serializer, vals, _ in self._iter_packers(values):
                out.write(serializer.pack(*vals))
            return out.getvalue()

    def pack_into(
        self,
        buffer: WritableBuffer,
        offset: int,
        *values: Unpack[Ts],
    ) -> None:
        for serializer, vals, size in self._iter_packers(values):
            serializer.pack_into(buffer, offset  + size, *vals)

    def pack_write(self, writable: BinaryIO, *values: Unpack[Ts]) -> None:
        for serializer, vals, _ in self._iter_packers(values):
            serializer.pack_write(writable, *vals)

    def _iter_unpackers(self) -> Iterable[tuple[Serializer, int]]:
        """Common boilerplate needed for iterating over sub-serializers and
        tracking the total size upacked so far.
        """
        size = 0
        for serializer in self.serializers:
            yield serializer, size
            size += serializer.size
        self.size = size

    def unpack(self, buffer: ReadableBuffer) -> Iterable:
        for serializer, size in self._iter_unpackers():
            yield from serializer.unpack(buffer[size:])

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> Iterable:
        for serializer, size in self._iter_unpackers():
            yield from serializer.unpack_from(buffer, offset + size)

    def unpack_read(self, readable: BinaryIO) -> Iterable:
        for serializer, _ in self._iter_unpackers():
            yield from serializer.unpack_read(readable)

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        serializers = tuple(
            serializer.with_byte_order(byte_order) for serializer in self.serializers
        )
        return CompoundSerializer(serializers)

    def __add__(self, other: Serializer[Unpack[Ss]]) -> CompoundSerializer[Unpack[Ts], Unpack[Ss]]:
        if isinstance(other, CompoundSerializer):
            to_append = list(other.serializers)
        elif isinstance(other, Serializer):
            to_append = [other]
        else:
            return NotImplemented
        serializers = list(self.serializers)
        return self._add_impl(serializers, to_append)

    @staticmethod
    def _add_impl(
        serializers: list[Serializer], to_append: Iterable[Serializer]
    ) -> CompoundSerializer:
        for candidate in to_append:
            joined = serializers[-1] + candidate
            if isinstance(joined, CompoundSerializer):
                # Don't need to make nested CompoundSerializers
                serializers.append(candidate)
            else:
                serializers[-1] = joined
        return CompoundSerializer(tuple(serializers))

    def __radd__(self, other: Serializer[Unpack[Ss]]) -> CompoundSerializer[Unpack[Ss], Unpack[Ts]]:
        # NOTE: CompountSerializer + CompoundSerializer will always call __add__
        # so we only need to optimize for Serializer + CompoundSerializer
        if isinstance(other, Serializer):
            serializers = [other]
        else:
            return NotImplemented
        to_append = self.serializers[:]
        return self._add_impl(serializers, to_append)


class _SpecializedCompoundSerializer(Generic[Unpack[Ts]], CompoundSerializer[Unpack[Ts]]):
    """CompoundSerializer that will forward a partial_object to sub-serializers,
    and update the size of the originating CompoundSerializer.
    """
    def __init__(self, origin: CompoundSerializer, partial_object: Any) -> None:
        self.origin = origin
        self.partial_object = partial_object
        self.serializers = tuple(
            serializer.preprocess(partial_object) for serializer in origin.serializers
        )
        self.size = origin.size
        self.num_values = origin.num_values

    def preprocess(self, partial_object: Any) -> Serializer:
        return self

    def _iter_packers(self, values: tuple[Unpack[Ts]]) -> Iterable[tuple[Serializer, tuple[Any, ...], int]]:
        size = 0
        i = 0
        for serializer in self.serializers:
            count = serializer.num_values
            yield serializer.preprocess(self.partial_object), values[i : i + count], size
            size += serializer.size
            i += count
        self.size = size
        self.origin.size = size

    def _iter_unpackers(self) -> Iterable[tuple[Serializer, int]]:
        size = 0
        for serializer in self.serializers:
            yield serializer.preprocess(self.partial_object), size
            size += serializer.size
        self.size = size
        self.origin.size = size


class UnionSerializer(Serializer):
    # NOTE: Union types are not allowed in TypeVarTuples, so we can't hint this
    """Serializer to handle loading of attributes with multiple types, type is
    decided just prior to packing/unpacking the attribute.
    """
    default: Serializer
    result_map: dict[Any, Serializer]

    def __init__(self, decider: Callable[[Any], Any], result_map: dict[Any, Any], default: Any = None) -> None:
        """result_map should be a mapping of possible return values from `decider`
        to `Annotated` instances with a Serializer as an extra argument.  The
        default should either be `None` to raise an error if the decider returns
        an unmapped value, or an `Annotated` instance with a Serializer as an
        extra argument.
        """
        self.decide = decider
        self.default = basic_types.unwrap_annotated(default)
        self.result_map = {
            key: basic_types.unwrap_annotated(serializer)
            for key, serializer in result_map.items()
        }
        # Check types
        if not isinstance(self.default, Serializer):
            raise TypeError('default must be a Serializer')
        if any(not isinstance(serializer, Serializer) for serializer in self.result_map.values()):
            raise TypeError('result_map values must be Serializers')
        self._last_serializer = self.default

    @property
    def size(self) -> int:
        return self._last_serializer.size

    def preprocess(self, partial_object: Any) -> Serializer:
        result = self.decide(partial_object)
        serializer = self.result_map.get(result, self.default)
        try:
            self._last_serializer = serializer.preprocess(partial_object)
        except AttributeError:
            if serializer is None:
                raise ValueError(f'Union decider {self.decide!r} returned an unmapped value {result!r}') from None
            else:
                raise
        return self._last_serializer

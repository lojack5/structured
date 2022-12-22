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
 - New attribute `num_values`.
 - New unpacking method `unpack_read`.
 - New packing method `pack_read`.
 - New configuration method `with_byte_order`.
 - Modified packing method `pack`
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
from functools import cached_property, partial, reduce, wraps
from io import BytesIO
from itertools import chain, repeat
from typing import TypeVar, overload

from .base_types import ByteOrder
from .type_checking import (
    _T,
    Annotated,
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Iterable,
    ReadableBuffer,
    Self,
    WritableBuffer,
)


def noop_action(x: _T) -> _T:
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


class Serializer:
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

    def pack(self, *values: Any) -> bytes:
        """Pack the given values according to this Serializer's logic, returning
        the packed bytes.

        :return: The packed bytes version of the values.
        """
        raise NotImplementedError

    def pack_into(
        self,
        buffer: WritableBuffer,
        offset: int,
        *values: Any,
    ) -> None:
        """Pack the given values according to this Serializer's logic, placing
        them into a buffer supporting the Buffer Protocol.

        :param buffer: An object supporting the Buffer Protocol.
        :param offset: Location in the buffer to place the packed bytes.
        """
        raise NotImplementedError

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        """Pack the given values according to this Serializer's logic, placing
        them into a writable file-like object.

        :param writable: A writable file-like object.
        """
        raise NotImplementedError

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        """Unpack values from a bytes-like buffer, returning the values in a
        tuple.  Unlike `struct.pack`, the Serializer must accept a buffer that
        is larger than the needed number of bytes for unpacking.

        :param buffer: A readable bytes-like object.
        :return: The unpacked values in a tuple.
        """
        raise NotImplementedError

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        """Unpack values from a buffer supporting the Buffer Protocol, returning
        the values in a tuple.

        :param buffer: A readable object supporing the Buffer Protocol.
        :param offset: Location in the buffer to draw data from.
        :return: The unpacked values in a tuple.
        """
        raise NotImplementedError

    def unpack_read(self, readable: BinaryIO) -> tuple:
        """Unpack values from a readable file-like object, returning the values
        in a tuple.

        :param readable: A readable file-like object.
        :return: The unpacked values in a tuple.
        """
        raise NotImplementedError

    # Internal methods useful for configuring / combining serializers
    def with_byte_order(self, byte_order: ByteOrder) -> Serializer:
        """Create a serializer with the same packing / unpacking logic, but
        configured to use the specified byte order.

        :param byte_order: ByteOrder to use with the new serializer.
        :return: A new serializer, or this one if no changes were needed.
        """
        return self

    def __add__(self, other: Serializer) -> CompoundSerializer:
        if isinstance(other, Serializer) and not isinstance(other, NullSerializer):
            # Default is to make a CompoundSerializer joining the two.
            # Subclasses can provide an __radd__ if optimizing can be done
            return CompoundSerializer((self, other))
        return NotImplemented


TSerializer = TypeVar('TSerializer', bound=Serializer)


class NullSerializer(Serializer):
    """A dummy serializer to function as the initial value for sum(...)"""

    size = 0
    num_values = 0

    def pack(self, *values: Any) -> bytes:
        return b''

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: Any) -> None:
        return

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        return

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        return ()

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        return ()

    def unpack_read(self, readable: BinaryIO) -> tuple:
        return ()

    def __add__(self, other: TSerializer) -> TSerializer:
        if isinstance(other, Serializer):
            return other
        return NotImplemented

    def __radd__(self, other: TSerializer) -> TSerializer:
        return self.__add__(other)


class StructSerializer(struct.Struct, Serializer):
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

    def with_byte_order(self, byte_order: ByteOrder) -> StructSerializer:
        old_byte_order, fmt = self._split_format
        if old_byte_order is byte_order:
            return self
        else:
            return StructSerializer(fmt, self.num_values, byte_order)

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        return super().unpack(buffer[: self.size])

    def unpack_read(self, readable: BinaryIO) -> tuple:
        # NOTE: use super-class's unpack to not interfere with custom
        # logic in subclasses
        return super().unpack(readable.read(self.size))

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        # NOTE: Call the super-class's pack, so we don't interfere with
        # any custom logic in pack_write for subclasses
        writable.write(super().pack(*values))

    @overload
    def __add__(self, other: StructSerializer) -> StructSerializer:
        ...

    @overload
    def __add__(self, other: Serializer) -> Serializer:
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

    def __mul__(self, other: int) -> StructSerializer:
        if not isinstance(other, int):
            return NotImplemented
        elif other <= 0:
            raise ValueError('count must be positive')
        elif other == 1:
            return self
        byte_order, fmt = self._split_format
        fmt = reduce(partial(fold_overlaps, combine_strings=True), repeat(fmt, other))
        return StructSerializer(fmt, self.num_values * other, byte_order)


def _apply_actions(unpacker):
    @wraps(unpacker)
    def wrapped(self, *args, **kwargs):
        return tuple(
            action(value)
            for action, value in zip(self.actions, unpacker(self, *args, **kwargs))
        )

    return wrapped


class StructActionSerializer(StructSerializer):
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

    unpack = _apply_actions(StructSerializer.unpack)
    unpack_from = _apply_actions(StructSerializer.unpack_from)
    unpack_read = _apply_actions(StructSerializer.unpack_read)

    def with_byte_order(self, byte_order: ByteOrder) -> StructActionSerializer:
        old_byte_order, fmt = self._split_format
        if old_byte_order is byte_order:
            return self
        return StructActionSerializer(fmt, self.num_values, byte_order, self.actions)

    def __add__(self, other: StructSerializer) -> StructActionSerializer:
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

    def __radd__(self, other: StructSerializer) -> StructActionSerializer:
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

    def __mul__(self, other: int) -> StructActionSerializer:
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


class CompoundSerializer(Serializer):
    """A serializer that chains together multiple serializers."""

    serializers: tuple[Serializer, ...]

    def __init__(self, serializers: tuple[Serializer, ...]) -> None:
        self.serializers = serializers
        self.size = 0
        self.num_values = sum(serializer.num_values for serializer in serializers)

    def pack(self, *values: Any) -> bytes:
        i = 0
        with BytesIO() as out:
            for serializer in self.serializers:
                count = serializer.num_values
                out.write(serializer.pack(*(values[i : i + count])))
                i += count
            return out.getvalue()

    def pack_into(
        self,
        buffer: WritableBuffer,
        offset: int,
        *values: Any,
    ) -> None:
        size = 0
        i = 0
        for serializer in self.serializers:
            count = serializer.num_values
            serializer.pack_into(buffer, offset + size, *(values[i : i + count]))
            size += serializer.size
            i += count
        self.size = size

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        self.size = 0
        i = 0
        for serializer in self.serializers:
            count = serializer.num_values
            serializer.pack_write(writable, *(values[i : i + count]))
            self.size += serializer.size
            i += count

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        values = []
        start = 0
        for serializer in self.serializers:
            values.append(serializer.unpack(buffer[start:]))
            start += serializer.size
        self.size = start
        return tuple(chain.from_iterable(values))

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        values = []
        size = 0
        for serializer in self.serializers:
            values.append(serializer.unpack_from(buffer, offset + size))
            size += serializer.size
        self.size = size
        return tuple(chain.from_iterable(values))

    def unpack_read(self, readable: BinaryIO) -> tuple:
        values = []
        size = 0
        for serializer in self.serializers:
            values.append(serializer.unpack_read(readable))
            size += serializer.size
        self.size = size
        return tuple(chain.from_iterable(values))

    def with_byte_order(self, byte_order: ByteOrder) -> CompoundSerializer:
        serializers = tuple(
            serializer.with_byte_order(byte_order) for serializer in self.serializers
        )
        return CompoundSerializer(serializers)

    def __add__(self, other: Serializer) -> CompoundSerializer:
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

    def __radd__(self, other: Serializer) -> CompoundSerializer:
        # NOTE: CompountSerializer + CompoundSerializer will always call __add__
        # so we only need to optimize for Serializer + CompoundSerializer
        if isinstance(other, Serializer):
            serializers = [other]
        else:
            return NotImplemented
        to_append = self.serializers[:]
        return self._add_impl(serializers, to_append)

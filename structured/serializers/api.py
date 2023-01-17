"""Defines the base Serializer API.

The Serializer API is almost identical to struct.Struct, with a few additions
and one alteration:
 - New methods 'prepack' and 'preunpack'.
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
    'NullSerializer',
    'CompoundSerializer',
]

from io import BytesIO

from ..base_types import ByteOrder
from ..type_checking import (
    Any,
    BinaryIO,
    ClassVar,
    Generic,
    Iterable,
    ReadableBuffer,
    Self,
    Ss,
    Ts,
    TypeVar,
    Unpack,
    WritableBuffer,
)


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

    def preprocess(self, target: Any) -> None:
        """Called just prior to a pack or unpack operations.  For packing, the
        `target` is the actual Structured isntance being packed.  For unpacking,
        the `target` may be the actual instance, or a proxy object with only the
        attributes unpacked so far set.
        """
        self.target = target

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

    def __add__(
        self, other: Serializer[Unpack[Ss]]
    ) -> CompoundSerializer[Unpack[Ts], Unpack[Ss]]:
        if isinstance(other, (CompoundSerializer, NullSerializer)):
            # Allow the other __radd__ to work, even in cases where other is
            # not a subclass of self (ie: StructSerializer + CompoundSerializer)
            return NotImplemented
        elif isinstance(other, Serializer):
            # Default is to make a CompoundSerializer joining the two.
            # Subclasses can provide an __radd__ if optimizing can be done
            return CompoundSerializer((self, other))
        return NotImplemented


TSerializer = TypeVar('TSerializer', bound=Serializer)


class NullSerializer(Serializer[Unpack[tuple[()]]]):
    """A dummy serializer to function as the initial value for sum(...)"""

    size: ClassVar[int] = 0
    num_values: ClassVar[int] = 0

    def pack(self, *values: Unpack[tuple[()]]) -> bytes:
        return b''

    def pack_into(
        self, buffer: WritableBuffer, offset: int, *values: Unpack[tuple[()]]
    ) -> None:
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


class CompoundSerializer(Generic[Unpack[Ts]], Serializer[Unpack[Ts]]):
    """A serializer that chains together multiple serializers."""

    serializers: tuple[Serializer, ...]

    def __init__(self, serializers: tuple[Serializer, ...]) -> None:
        self.serializers = serializers
        self.size = 0
        self.num_values = sum(serializer.num_values for serializer in serializers)
        if any(
            isinstance(serializer, CompoundSerializer) for serializer in serializers
        ):
            raise TypeError('cannot nest CompoundSerializers')

    def preprocess(self, target: Any) -> None:
        for serializer in self.serializers:
            serializer.preprocess(target)

    def _iter_packers(
        self, values: tuple[Unpack[Ts]]
    ) -> Iterable[tuple[Serializer, tuple[Any, ...], int]]:
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
            serializer.pack_into(buffer, offset + size, *vals)

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

    def __add__(
        self, other: Serializer[Unpack[Ss]]
    ) -> CompoundSerializer[Unpack[Ts], Unpack[Ss]]:
        if isinstance(other, CompoundSerializer):
            to_append = list(other.serializers)
        elif isinstance(other, Serializer):
            to_append = [other]
        else:
            return super().__add__(other)
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

    def __radd__(
        self, other: Serializer[Unpack[Ss]]
    ) -> CompoundSerializer[Unpack[Ss], Unpack[Ts]]:
        # NOTE: CompountSerializer + CompoundSerializer will always call __add__
        # so we only need to optimize for Serializer + CompoundSerializer
        if isinstance(other, Serializer):
            serializers = [other]
        else:
            return NotImplemented
        to_append = self.serializers[:]
        return self._add_impl(serializers, to_append)

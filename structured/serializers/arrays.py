"""
All the serializers for arrays.  Provides a general purpose ArraySerializer,
plus specializations for arrays containing types with direct serialization via
struct.
"""

__all__ = [
    'ArraySerializer',
    'StaticStructArraySerializer',
    'DynamicStructArraySerializer',
    'HeaderSerializer',
]

from ..base_types import ByteOrder
from ..type_checking import (
    BinaryIO,
    Generic,
    ReadableBuffer,
    Self,
    T,
    Union,
    Unpack,
    WritableBuffer,
)
from .api import NullSerializer, Serializer
from .structs import StructSerializer

HeaderSerializer = Union[
    NullSerializer, StructSerializer[int], StructSerializer[int, int]
]


class ArraySerializer(Generic[T], Serializer[list[T]]):
    """Generic array serializer."""

    def __init__(
        self,
        header_serializer: HeaderSerializer,
        item_serializer: Serializer[T],
        static_length: int = -1,
    ) -> None:
        self.header_serializer = header_serializer
        self.item_serializer = item_serializer
        self.static_length = static_length
        self.size = 0
        self.num_values = 1

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        return type(self)(
            self.header_serializer.with_byte_order(byte_order),
            self.item_serializer.with_byte_order(byte_order),
            self.static_length,
        )

    def _header_pack_values(self, items: list[T], data_size: int) -> tuple[int, ...]:
        """Which values need to be passed to the header serializer for packing."""
        count = len(items)
        if self.static_length >= 0:
            # Static sized
            if count != self.static_length:
                raise ValueError(
                    f'Array length {count} does not match static length '
                    f'{self.static_length}'
                )
            if self.header_serializer.num_values == 1:
                # With a data size
                return (data_size,)
            else:
                return ()
        else:
            # Dynamic sized
            if self.header_serializer.num_values == 2:
                # With a data size
                return count, data_size
            else:
                return (count,)

    def _header_unpack_values(self, *header_values: int) -> tuple[int, int]:
        if self.static_length >= 0:
            # Static sized
            if self.header_serializer.num_values == 1:
                # With a data size
                return self.static_length, header_values[0]
            else:
                return self.static_length, -1
        else:
            # Dynamic sized
            if self.header_serializer.num_values == 2:
                # With a data size
                return header_values
            else:
                return header_values[0], -1

    def _check_data_size(self, expected: int, actual: int) -> None:
        if expected >= 0 and expected != actual:
            raise ValueError(
                f'Array data size {actual} does not match expected size {expected}'
            )

    def prepack(self, partial_object) -> Self:
        self._partial_object = partial_object
        return self

    def preunpack(self, partial_object) -> Self:
        self._partial_object = partial_object
        return self

    def pack(self, *values: Unpack[tuple[list[T]]]) -> bytes:
        data = [b'']
        size = header_size = self.header_serializer.size
        item_serializer = self.item_serializer.prepack(self._partial_object)
        for item in values[0]:
            data.append(item_serializer.pack(item))
            size += item_serializer.size
        header_values = self._header_pack_values(values[0], size - header_size)
        data[0] = self.header_serializer.pack(*header_values)
        self.size = size
        return b''.join(data)

    def pack_into(
        self, buffer: WritableBuffer, offset: int, *values: Unpack[tuple[list[T]]]
    ) -> None:
        items = values[0]
        size = header_size = self.header_serializer.size
        item_serializer = self.item_serializer.prepack(self._partial_object)
        for item in items:
            item_serializer.pack_into(buffer, offset + size, item)
            size += item_serializer.size
        header_values = self._header_pack_values(items, size - header_size)
        self.size = size
        self.header_serializer.pack_into(buffer, offset, *header_values)

    def pack_write(self, writable: BinaryIO, *values: Unpack[tuple[list[T]]]) -> None:
        # TODO: Why is the typechecker flagging this?
        writable.write(self.pack(*values))  # type: ignore

    def unpack(self, buffer: ReadableBuffer) -> tuple[list[T]]:
        header = self.header_serializer.unpack(buffer)
        count, data_size = self._header_unpack_values(*header)
        size = header_size = self.header_serializer.size
        item_serializer = self.item_serializer.preunpack(self._partial_object)
        items = []
        for _ in range(count):
            items.extend(item_serializer.unpack(buffer[size:]))
            size += item_serializer.size
        self._check_data_size(data_size, size - header_size)
        self.size = size
        return (items,)

    def unpack_from(self, buffer: ReadableBuffer, offset: int) -> tuple[list[T]]:
        header = self.header_serializer.unpack_from(buffer, offset)
        count, data_size = self._header_unpack_values(*header)
        size = header_size = self.header_serializer.size
        item_serializer = self.item_serializer.preunpack(self._partial_object)
        items = []
        for _ in range(count):
            items.extend(item_serializer.unpack_from(buffer, offset + size))
            size += item_serializer.size
        self._check_data_size(data_size, size - header_size)
        self.size = size
        return (items,)

    def unpack_read(self, readable: BinaryIO) -> tuple[list[T]]:
        header = self.header_serializer.unpack_read(readable)
        count, data_size = self._header_unpack_values(*header)
        size = header_size = self.header_serializer.size
        item_serializer = self.item_serializer.preunpack(self._partial_object)
        items = []
        for _ in range(count):
            items.extend(item_serializer.unpack_read(readable))
            size += item_serializer.size
        self._check_data_size(data_size, size - header_size)
        self.size = size
        return (items,)


class StaticStructArraySerializer(Generic[T], Serializer[list[T]]):
    """Specialization of ArraySerializer for static length arrays of items
    that can be unpacked with struct.Struct
    """

    def __init__(self, count: int, item_serializer: StructSerializer[T]) -> None:
        self.count = count
        # Need to save the original for with_byte_order
        self.item_serializer = item_serializer
        self.serializer = item_serializer * count
        self.num_values = 1

    @property
    def size(self) -> int:
        return self.serializer.size

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        return type(self)(self.count, self.item_serializer.with_byte_order(byte_order))

    def _check_length(self, items: list[T]) -> None:
        if len(items) != self.count:
            raise ValueError(
                f'Array length {len(items)} does not match static length {self.count}'
            )

    def pack(self, *values: Unpack[tuple[list[T]]]) -> bytes:
        self._check_length(values[0])
        return self.serializer.pack(*values[0])

    def pack_into(
        self, buffer: WritableBuffer, offset: int, *values: Unpack[tuple[list[T]]]
    ) -> None:
        self._check_length(values[0])
        self.serializer.pack_into(buffer, offset, *values[0])

    def pack_write(self, writable: BinaryIO, *values: Unpack[tuple[list[T]]]) -> None:
        self._check_length(values[0])
        self.serializer.pack_write(writable, *values[0])

    def unpack(self, buffer: ReadableBuffer) -> tuple[list[T]]:
        return (list(self.serializer.unpack(buffer)),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int) -> tuple[list[T]]:
        return (list(self.serializer.unpack_from(buffer, offset)),)

    def unpack_read(self, readable: BinaryIO) -> tuple[list[T]]:
        return (list(self.serializer.unpack_read(readable)),)


class DynamicStructArraySerializer(Generic[T], Serializer[list[T]]):
    """Specialization of ArraySerializer for dynamic length arrays of items
    that can be unpacked with struct.Struct
    """

    def __init__(
        self,
        count_serializer: StructSerializer[int],
        item_serializer: StructSerializer[T],
    ) -> None:
        self.count_serializer = count_serializer
        self.item_serializer = item_serializer
        self.num_values = 0
        self.size = 0

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        return type(self)(
            self.count_serializer.with_byte_order(byte_order),
            self.item_serializer.with_byte_order(byte_order),
        )

    def _packer(self, values: tuple[list[T]]) -> tuple[Serializer, list[T]]:
        items = values[0]
        count = len(items)
        if count == 0:
            # Since we'll be modifying its .num_values, we want a copy
            serializer = StructSerializer(self.count_serializer.format)
        else:
            serializer = self.count_serializer + (self.item_serializer * count)
        serializer.num_values -= 1
        self.size = serializer.size
        return serializer, items

    def pack(self, *values: Unpack[tuple[list[T]]]) -> bytes:
        serializer, items = self._packer(values)
        return serializer.pack(serializer.num_values, *items)

    def pack_into(
        self, buffer: WritableBuffer, offset: int, *values: Unpack[tuple[list[T]]]
    ) -> None:
        serializer, items = self._packer(values)
        serializer.pack_into(buffer, offset, serializer.num_values, *items)

    def pack_write(self, writable: BinaryIO, *values: Unpack[tuple[list[T]]]) -> None:
        serializer, items = self._packer(values)
        serializer.pack_write(writable, serializer.num_values, *items)

    def unpack(self, buffer: ReadableBuffer) -> tuple[list[T]]:
        (count,) = self.count_serializer.unpack(buffer)
        size = self.count_serializer.size
        serializer = self.item_serializer * count
        items = serializer.unpack(buffer[size:])
        self.size = size + serializer.size
        return (list(items),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int) -> tuple[list[T]]:
        (count,) = self.count_serializer.unpack_from(buffer, offset)
        size = self.count_serializer.size
        serializer = self.item_serializer * count
        items = serializer.unpack_from(buffer, offset + size)
        self.size = size + serializer.size
        return (list(items),)

    def unpack_read(self, readable: BinaryIO) -> tuple[list[T]]:
        (count,) = self.count_serializer.unpack_read(readable)
        size = self.count_serializer.size
        serializer = self.item_serializer * count
        items = serializer.unpack_read(readable)
        self.size = size + serializer.size
        return (list(items),)

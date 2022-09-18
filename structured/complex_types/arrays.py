"""
Array types
"""
from __future__ import annotations
from typing import get_type_hints

__all__ = [
    'array', 'Header',
]

import io
from itertools import repeat
from functools import cache

from .array_headers import *
from ..base_types import (
    Serializer, StructSerializer, format_type, requires_indexing, struct_cache,
    ByteOrder,
)
from ..basic_types import *
from ..utils import specialized
from ..type_checking import (
    Union, ReadableBuffer, WritableBuffer, SupportsRead, SupportsWrite, Any,
    NoReturn, ClassVar, Generic, TypeVar,
)


T = TypeVar('T', bound=Header)
U = TypeVar('U',
    # Any of the Annotated types
    bool8, int8, uint8, int16, uint16, int32, uint32, int64, uint64, float16,
    float32, float64,
    # Or any format_type or a Structured type
    format_type, Structured,
    covariant=True,
    #bound=Union[format_type, Structured],
)


class array(list[U], requires_indexing, Generic[T, U]):
    """Class which dispatches to the appropriate array type for handling the
    various options when creating an array annotation:
     - Statically sized or dynamically sized
     - Size checked or no size check
     - array of Structured objects, or array of basic format_types.

    To create, first pick a header type (size of the array and optional size
    check):
      Header[2]             # Statically sized, no size check
      Header[2, uint16]     # Statically sized, uint16 size check prior
      Header[uint8]         # Dynamically sized, length is uint8 prior
      Header[uint8, uint16] # Dynamically sized, uint16 size check after length

    Then declare your array:
      array[Header[2], uint16]

    For Headers that take only one argument, you can simply write:
      array[2, uint16]
    However, type checkers may complain about this.

    Arrays can hold any of the format types (uint8, int32, etc), or any user
    defined Structured object.
    """
    @classmethod
    def error(cls, exc_type: type[Exception], msg: str) -> NoReturn:
        """Helper to add 'array[] to the beginning of exception messages, and
        raise the exception.

        :param exc_type: Exception type to raise
        :param msg: Exception message
        """
        raise exc_type(f'{cls.__qualname__}[] {msg}')

    def __class_getitem__(
            cls,
            args: tuple[type[T], type[U]]
        ) -> type[Serializer]:
        """Perform error checks and dispatch to the applicable class factory."""
        if not isinstance(args, tuple) or len(args) < 2:
            cls.error(TypeError, 'expected 2 arguments')
        args = tuple(map(unwrap_annotated, args))
        if len(args) == 2:
            header, array_type = args
        else:
            header = Header[args[:-1]]
            array_type = args[-1]
        # TypeVar checks:
        if (isinstance(header, StructuredAlias) or
            isinstance(array_type, TypeVar)):
            return StructuredAlias(cls, (header, array_type))   # type: ignore
        # Type checking
        if (not isinstance(header, type) or
            not issubclass(header, HeaderBase) or
            header is HeaderBase or
            header is Header
        ):
            header = Header[header]
        if (not isinstance(array_type, type) or
            not issubclass(array_type, (format_type, Structured))
        ):
            cls.error(
                TypeError,
                'array object type must be a format type or Structured type'
            )
        return cls._create(header, array_type)

    @classmethod
    @cache
    def _create(
            cls,
            header: type[Header],
            array_type: type[U]
        ) -> type[Serializer]:
        """Actual creation of the header."""
        if issubclass(array_type, format_type):
            if issubclass(header, (StaticCheckedHeader, DynamicCheckedHeader)):
                cls.error(
                    TypeError,
                    'size checked arrays are only supported for Structured '
                    'arrays'
                )
            elif issubclass(header, StaticHeader):
                @specialized(cls, header, array_type)
                class _array1(_format_array):
                    count: ClassVar[int] = header._count
                    obj_type: ClassVar[type[format_type]] = array_type
                return _array1
            else:
                count = get_type_hints(header)['count']
                @specialized(cls, header, array_type)
                class _array2(_dynamic_format_array):
                    count_type: ClassVar[type[SizeTypes]] = count
                    obj_type: ClassVar[type[format_type]] = array_type
                return _array2
        else:
            @specialized(cls, header, array_type)
            class _array3(_structured_array):
                header_type: ClassVar[type[Header]] = header
                obj_type: ClassVar[type[Structured]] = array_type
            return _array3


class _structured_array(Serializer):
    """All the Serialization logic for arrays containing Structured objects.
    Subclass and set header_type and obj_type to create an array implementation.
    """
    header_type: ClassVar[type[Header]]
    obj_type: ClassVar[type[Structured]]

    def __init__(self, byte_order: ByteOrder):
        """Setup the array header."""
        self.header = self.header_type(0, 0)

    def pack(self, *values: Any) -> bytes:
        """Pack an array into bytes."""
        with io.BytesIO() as out:
            self.pack_write(out, *values)
            return out.getvalue()

    def pack_into(
            self,
            buffer: WritableBuffer,
            offset: int,
            *values: Any
        ) -> None:
        """Pack an array into a buffer supporting the Buffer Protocol."""
        items: list[Structured] = values[0]
        self.header.count = len(items)
        self.size = header_size = self.header.serializer.size
        for item in items:
            item.pack_into(buffer, offset + self.size)
            self.size += item.serializer.size
        self.header.data_size = self.size - header_size
        self.header.pack_into(buffer, offset)

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        """Pack an array and write it to a file-like object."""
        items: list[Structured] = values[0]
        self.header.count = len(items)
        if self.header.two_pass:
            header_pos = writable.tell()
        else:
            header_pos = 0
        self.header.pack_write(writable)
        self.size = self.header.serializer.size
        data_size = 0
        for item in items:
            item.pack_write(writable)
            data_size += item.serializer.size
        self.size += data_size
        if self.header.two_pass:
            final_pos = writable.tell()
            writable.seek(header_pos)
            self.header.data_size = data_size
            self.header.pack_write(writable)
            writable.seek(final_pos)

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        """Unpack an array from a bytes-like buffer."""
        self.header.unpack(buffer)
        self.size = header_size = self.header.serializer.size
        unpack_item = self.obj_type.create_unpack
        items: list[Structured] = []
        for i in range(self.header.count):
            items.append(unpack_item(buffer[self.size:]))
            self.size += items[-1].serializer.size
        data_size = self.size - header_size
        self.header.validate_data_size(data_size)
        return items,

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        """Unpack an array from a buffer supporting the Buffer Protocol."""
        self.header.unpack_from(buffer, offset)
        self.size = header_size = self.header.serializer.size
        unpack_item = self.obj_type.create_unpack_from
        items: list[Structured] = []
        for i in range(self.header.count):
            items.append(unpack_item(buffer, offset + self.size))
            self.size += items[-1].serializer.size
        data_size = self.size - header_size
        self.header.validate_data_size(data_size)
        return items,

    def unpack_read(self, readable: SupportsRead) -> tuple:
        """Unpack an array from a file-like object."""
        self.header.unpack_read(readable)
        self.size = self.header.serializer.size
        data_size = 0
        items: list[Structured] = []
        for i in range(self.header.count):
            items.append(self.obj_type.create_unpack_read(readable))
            data_size += items[-1].serializer.size
        self.size += data_size
        self.header.validate_data_size(data_size)
        return items,


class _format_array(Serializer):
    """Statically sized array of format_type objects.

    Subclass and set the following ClassVars:

    :param count: The static size of the array
    :type count: int
    :param obj_type: The format_type class stored in the array
    :type obj_type: type[format_type]
    """
    count: ClassVar[int]
    obj_type: ClassVar[type[format_type]]

    size: int

    def __init__(self, byte_order: ByteOrder):
        """Create the packer/unpacker for the array, and set the static size
        needed for this serializer.

        :param byte_order: Byte order to use when packing/unpacking.
        """
        actions = tuple(repeat(self.obj_type.unpack_action, self.count))
        fmt = f'{byte_order.value}{self.count}{self.obj_type.format}'
        self.serializer = struct_cache(fmt, actions)
        self.size = self.serializer.size

    def _check_arr(self, values: tuple[list]) -> list:
        """Extract the array from values, and verify it is of the correct
        static length.

        :param values: values passed in from the Structured class.
        :raises ValueError: If the array length is not the static size for this
            class
        :return: The array to pack
        """
        arr = values[0]
        if (count := len(arr)) != self.count:
            raise ValueError(
                f'array length must be {self.count} to pack, got {count}'
            )
        return arr

    def pack(self, *values: Any) -> bytes:
        """Pack an array of the approriate size into bytes.

        :return: The packed array.
        """
        return self.serializer.pack(*self._check_arr(values))

    def pack_into(
            self,
            buffer: WritableBuffer,
            offset: int,
            *values: Any,
        ) -> None:
        """Pack an array of the appropriate size into a buffer supporting the
        Buffer Protocol.

        :param buffer: The buffer to place the packed array into
        :param offset: Location in the buffer to place the packed array
        """
        self.serializer.pack_into(buffer, offset, *self._check_arr(values))

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        """Pack an array of the appropriate size and write it to a file-like
        object.

        :param writable: A writable file-like object.
        """
        self.serializer.pack_write(writable, *self._check_arr(values))

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        """Unpack an array from a buffer.

        :param buffer: A bytes-like object to unpack from
        :return: The unpacked array as the single element of a tuple
        """
        return list(self.serializer.unpack(buffer[:self.size])),

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        """Unpack an array from a buffer supporting the Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol
        :param offset: Location in the buffer to unpack from
        :return: The unpacked array as the single element of a tuple
        """
        return list(self.serializer.unpack_from(buffer, offset)),

    def unpack_read(self, readable: SupportsRead) -> tuple:
        """Unpack an array from a readable object.

        :param readable: The readable file-like object to unpack from
        :return: The unpacked array as the single element of a tuple
        """
        return list(self.serializer.unpack_read(readable)),


class _dynamic_format_array(Serializer):
    """Dynamically sized array of format_type objects.

    Subclass and set the following ClassVars:

    :param count_type: The type of integer to unpack/pack for the array length.
    :type count_type: type[Union[uint8, uint16, uint32, uint64]]
    :param obj_type: The format_type subclass of the objects to store.
    :type obj_type: type[format_type]
    """
    count_type: ClassVar[type[SizeTypes]]
    obj_type: ClassVar[type[format_type]]

    size: int

    def __init__(self, byte_order: ByteOrder) -> None:
        """Set up a struct object for packing/unpacking the array length, and
        initialize this Serializer's dynamic size.

        :param byte_order: ByteOrder to use for packing/unpacking
        """
        self.size = 0
        fmt = f'{byte_order.value}{self.count_type.format}'
        self.header = struct_cache(fmt)
        self.byte_order = byte_order.value

    def _arr_count_st(
            self,
            values: tuple[Any, ...],
        ) -> tuple[list, int, StructSerializer]:
        """Extract the array to pack, determine its size, and create a
        StructSerializer for packing the array along with its length.

        :param values: The values as passed by the Structured instance.
        :return: The array to pack, its length, and the Struct for packing it.
        """
        arr = values[0]
        count = len(arr)
        fmt = (f'{self.byte_order}{self.count_type.format}{count}'
               f'{self.obj_type.format}')
        st = struct_cache(fmt)
        self.size = st.size
        return arr, count, st

    def pack(self, *values: Any) -> bytes:
        """Pack an array into bytes.

        :return: The packed array.
        """
        arr, count, st = self._arr_count_st(values)
        return st.pack(count, *arr)

    def pack_into(
            self,
            buffer: WritableBuffer,
            offset: int,
            *values: Any,
        ) -> None:
        """Pack an array into a buffer supporting the Buffer Protocol.

        :param buffer: The buffer supporing the Buffer Protocol.
        :param offset: Location in the buffer to place the packed array.
        """
        arr, count, st = self._arr_count_st(values)
        st.pack_into(buffer, offset, count, *arr)

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        """Pack an array and write it to a file-like object.

        :param writable: A writable file-like object.
        """
        arr, count, st = self._arr_count_st(values)
        st.pack_write(writable, count, *arr)

    def _st(self, count: int) -> StructSerializer:
        """Create a StructSerializer for unpacking a specified number of items.

        :param count: The number of elements to unpack in the array.
        :return: The StructSerializer for unpacking.
        """
        actions = tuple(repeat(self.count_type.unpack_action, count))
        fmt = f'{self.byte_order}{count}{self.obj_type.format}'
        return struct_cache(fmt, actions)

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        """Unpack an array from a bytes-like buffer.

        :param buffer: The buffer to unpack from.
        :return: The array contained as a single element in a tuple
        """
        count = self.header.unpack(buffer)[0]
        st = self._st(count)
        return list(st.unpack(buffer[self.header.size:])),

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        """Unpack an array from a buffer supporting the Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Location in the buffer to draw data from.
        :return: The unpacked array contained as a single element in a tuple.
        """
        count = self.header.unpack_from(buffer, offset)[0]
        st = self._st(count)
        return list(st.unpack_from(buffer, offset + self.header.size)),

    def unpack_read(self, readable: SupportsRead) -> tuple:
        """Unpack an array from a readable file-like object.

        :param readable: A readable file-like object.
        :return: The unpacked array contained as a single element in a tuple.
        """
        count = self.header.unpack_read(readable)[0]
        st = self._st(count)
        return list(st.unpack_read(readable)),

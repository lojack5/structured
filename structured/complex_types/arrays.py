"""
Array types
"""
from __future__ import annotations

__all__ = [
    'array',
    'Header',
]

import io
from functools import cache

from ..base_types import ByteOrder, requires_indexing
from ..basic_types import (
    bool8,
    float16,
    float32,
    float64,
    int8,
    int16,
    int32,
    int64,
    uint8,
    uint16,
    uint32,
    uint64,
    unwrap_annotated,
)
from ..serializers import Serializer, StructSerializer
from ..structured import Structured
from ..type_checking import (
    Annotated,
    Any,
    BinaryIO,
    ClassVar,
    Generic,
    NoReturn,
    ReadableBuffer,
    TypeVar,
    WritableBuffer,
    get_type_hints,
)
from ..utils import StructuredAlias
from .array_headers import (
    DynamicCheckedHeader,
    Header,
    HeaderBase,
    StaticCheckedHeader,
    StaticHeader,
)

T = TypeVar('T', bound=Header)

# Unsure if this works as indended:  The passed type should be one of the
# basic types, or derived from format_type (like pad, char, etc), or derived
# from Structured.
U = TypeVar(
    'U',
    # Any of the Annotated types
    bool8,
    int8,
    uint8,
    int16,
    uint16,
    int32,
    uint32,
    int64,
    uint64,
    float16,
    float32,
    float64,
    # Or any format_type or a Structured type
    StructSerializer,
    Structured,
    covariant=True,
    # bound=Union[format_type, Structured],
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

    def __class_getitem__(cls, args: tuple[type[T], type[U]]) -> type[list[U]]:
        """Perform error checks and dispatch to the applicable class factory."""
        if not isinstance(args, tuple) or len(args) < 2:
            cls.error(TypeError, 'expected 2 arguments')
        if len(args) == 2:
            header, array_type = args
        else:
            header = Header[args[:-1]]
            array_type = args[-1]
        # TypeVar checks:
        if isinstance(header, StructuredAlias) or isinstance(array_type, TypeVar):
            return StructuredAlias(cls, (header, array_type))  # type: ignore
        return cls._create(header, array_type)

    @classmethod
    @cache
    def _create(
        cls,
        header: type[Header],
        array_type,  # TODO: proper annotation?
    ) -> type[list[U]]:
        """Actual creation of the array."""
        # Check header type
        if (
            not isinstance(header, type)
            or not issubclass(header, HeaderBase)
            or header is HeaderBase
            or header is Header
        ):
            raise TypeError(f'invalid array header type: {type(header)}')
        # Check object type
        array_type = unwrap_annotated(array_type)
        if isinstance(array_type, StructSerializer):
            # Simple type as array object
            if issubclass(header, (StaticCheckedHeader, DynamicCheckedHeader)):
                cls.error(
                    TypeError,
                    'size checked arrays are only supported for Structured ' 'arrays',
                )
            elif issubclass(header, StaticHeader):
                # Static size
                serializer = _format_array(header._count, array_type)
            else:
                # Dynamic Size
                count = get_type_hints(header, include_extras=True)['count']
                count = unwrap_annotated(count)
                serializer = _dynamic_format_array(count, array_type)
            return Annotated[list[U], serializer]
        elif isinstance(array_type, type) and issubclass(array_type, Structured):
            return Annotated[list[U], _structured_array(header(0, 0), array_type)]
        else:
            raise TypeError(
                'array object type must be a Structured class or formatted type.'
            )


class _structured_array(Serializer):
    """All the Serialization logic for arrays containing Structured objects.
    Subclass and set header_type and obj_type to create an array implementation.
    """

    num_values: ClassVar[int] = 1
    header: Header
    obj_type: type[Structured]

    def __init__(self, header: Header, obj_type: type[Structured]) -> None:
        """Setup the array header."""
        self.header = header
        self.obj_type = obj_type

    def with_byte_order(self, byte_order: ByteOrder) -> _structured_array:
        # TODO: with_byte_order for Structured classes.
        return _structured_array(self.header.with_byte_order(byte_order), self.obj_type)

    def pack(self, *values: Any) -> bytes:
        """Pack an array into bytes."""
        with io.BytesIO() as out:
            self.pack_write(out, *values)
            return out.getvalue()

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: Any) -> None:
        """Pack an array into a buffer supporting the Buffer Protocol."""
        items: list[Structured] = values[0]
        self.header.count = len(items)
        self.size = header_size = self.header.serializer.size
        for item in items:
            item.pack_into(buffer, offset + self.size)
            self.size += item.serializer.size
        self.header.data_size = self.size - header_size
        self.header.pack_into(buffer, offset)

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
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
            items.append(unpack_item(buffer[self.size :]))
            self.size += items[-1].serializer.size
        data_size = self.size - header_size
        self.header.validate_data_size(data_size)
        return (items,)

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
        return (items,)

    def unpack_read(self, readable: BinaryIO) -> tuple:
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
        return (items,)


class _format_array(Serializer):
    """Statically sized array of format_type objects.

    Subclass and set the following ClassVars:

    :param count: The static size of the array
    :type count: int
    :param obj_type: The format_type class stored in the array
    :type obj_type: type[format_type]
    """

    _serializer: StructSerializer
    num_values: ClassVar[int] = 1
    size: int

    def __init__(self, count: int, obj_serializer: StructSerializer):
        self._serializer = obj_serializer * count
        self.size = self._serializer.size

    def with_byte_order(self, byte_order: ByteOrder) -> Serializer:
        return _format_array(1, self._serializer.with_byte_order(byte_order))

    def _check_arr(self, values: tuple[list]) -> list:
        """Extract the array from values, and verify it is of the correct
        static length.

        :param values: values passed in from the Structured class.
        :raises ValueError: If the array length is not the static size for this
            class
        :return: The array to pack
        """
        arr = values[0]
        if (count := len(arr)) != (expected := self._serializer.num_values):
            raise ValueError(f'array length must be {expected} to pack, got {count}')
        return arr

    def pack(self, *values: Any) -> bytes:
        """Pack an array of the approriate size into bytes.

        :return: The packed array.
        """
        return self._serializer.pack(*self._check_arr(values))

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
        self._serializer.pack_into(buffer, offset, *self._check_arr(values))

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        """Pack an array of the appropriate size and write it to a file-like
        object.

        :param writable: A writable file-like object.
        """
        self._serializer.pack_write(writable, *self._check_arr(values))

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        """Unpack an array from a buffer.

        :param buffer: A bytes-like object to unpack from
        :return: The unpacked array as the single element of a tuple
        """
        return (list(self._serializer.unpack(buffer)),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        """Unpack an array from a buffer supporting the Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol
        :param offset: Location in the buffer to unpack from
        :return: The unpacked array as the single element of a tuple
        """
        return (list(self._serializer.unpack_from(buffer, offset)),)

    def unpack_read(self, readable: BinaryIO) -> tuple:
        """Unpack an array from a readable object.

        :param readable: The readable file-like object to unpack from
        :return: The unpacked array as the single element of a tuple
        """
        return (list(self._serializer.unpack_read(readable)),)


class _dynamic_format_array(Serializer):
    """Dynamically sized array of format_type objects.

    Subclass and set the following ClassVars:

    :param count_type: The type of integer to unpack/pack for the array length.
    :type count_type: type[Union[uint8, uint16, uint32, uint64]]
    :param obj_type: The format_type subclass of the objects to store.
    :type obj_type: type[format_type]
    """

    _count_serializer: StructSerializer
    _obj_serializer: StructSerializer

    num_values: ClassVar[int] = 1
    size: int

    def __init__(
        self, count_serializer: StructSerializer, obj_serializer: StructSerializer
    ) -> None:
        """Set up a struct object for packing/unpacking the array length, and
        initialize this Serializer's dynamic size.

        :param byte_order: ByteOrder to use for packing/unpacking
        """
        self.size = 0
        self._count_serializer = count_serializer
        self._obj_serializer = obj_serializer

    def with_byte_order(self, byte_order: ByteOrder) -> _dynamic_format_array:
        count_serializer = self._count_serializer.with_byte_order(byte_order)
        obj_serializer = self._obj_serializer.with_byte_order(byte_order)
        return _dynamic_format_array(count_serializer, obj_serializer)

    def _arr_st(
        self,
        values: tuple[Any, ...],
    ) -> tuple[list, StructSerializer]:
        """Extract the array to pack, determine its size, and create a
        StructSerializer for packing the array along with its length.

        :param values: The values as passed by the Structured instance.
        :return: The array to pack, its length, and the Struct for packing it.
        """
        arr = values[0]
        count = len(arr)
        st = self._count_serializer + (self._obj_serializer * count)
        # Hack: st.num_values is purely used internally to count the number of
        # elements in the list, we -1 to adjust for the length value at the
        # beginning.
        st.num_values -= 1
        self.size = st.size
        return arr, st

    def pack(self, *values: Any) -> bytes:
        """Pack an array into bytes.

        :return: The packed array.
        """
        arr, st = self._arr_st(values)
        return st.pack(st.num_values, *arr)

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
        arr, st = self._arr_st(values)
        st.pack_into(buffer, offset, st.num_values, *arr)

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        """Pack an array and write it to a file-like object.

        :param writable: A writable file-like object.
        """
        arr, st = self._arr_st(values)
        st.pack_write(writable, st.num_values, *arr)

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        """Unpack an array from a bytes-like buffer.

        :param buffer: The buffer to unpack from.
        :return: The array contained as a single element in a tuple
        """
        count: int = self._count_serializer.unpack(buffer)[0]
        st = self._obj_serializer * count
        return (list(st.unpack(buffer[self._count_serializer.size :])),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        """Unpack an array from a buffer supporting the Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Location in the buffer to draw data from.
        :return: The unpacked array contained as a single element in a tuple.
        """
        count: int = self._count_serializer.unpack_from(buffer, offset)[0]
        st = self._obj_serializer * count
        return (list(st.unpack_from(buffer, offset + self._count_serializer.size)),)

    def unpack_read(self, readable: BinaryIO) -> tuple:
        """Unpack an array from a readable file-like object.

        :param readable: A readable file-like object.
        :return: The unpacked array contained as a single element in a tuple.
        """
        count: int = self._count_serializer.unpack_read(readable)[0]
        st = self._obj_serializer * count
        return (list(st.unpack_read(readable)),)

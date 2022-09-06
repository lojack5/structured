"""
Array types
"""
from __future__ import annotations
from functools import partial

__all__ = [
    'array_size', 'size_check', 'array_type',
    'array',
]

import io
from itertools import repeat
from functools import cache

from ..base_types import (
    Serializer, StructSerializer, format_type, requires_indexing, struct_cache,
    ByteOrder,
)
from ..basic_types import uint8, uint16, uint32, uint64
from ..utils import specialized, container
from ..structured import Structured
from ..type_checking import (
    Union, ReadableBuffer, WritableBuffer, SupportsRead, SupportsWrite, Any,
    NoReturn, ClassVar, Optional,
)


SizeTypes = Union[uint8, uint16, uint32, uint64]


# Containers to allow optional more verbose supplying of array
# arguments, in any order.
class size_check(container): pass
class array_size(container): pass
class array_type(container): pass


class array(list, requires_indexing):
    """Class which dispatches to the appropriate array type for handling the
    various options when creating an array annotation:
     - Statically sized or dynamically sized
     - Size checked or no size check
     - array of Structured objects, or array of basic format_types.

    Usage:
        array[array_size, size_check, array_type]
    or:
        array[array_size, array_type]

    Arrays can hold any of the format types (uint8, int32, etc), or any user
    defined Structured object.  The arguments to the array specialization may be
    optionally provided with the helper classes 'array_size', 'size_check', and
    or 'array_type' for more readability:

        array[10, array_type[MyStructuredType]]
        array[array_size[10], MyStructuredType]]
        array[array_size[uint32], size_check[uint16], MyStructuredType]

    :param array_size: If an integer, indicates the static size of the array.
        Otherwise, if one of the uint* types, indicates a type to unpack which
        determines the array size.
    :type array_size: Union[int, type[Union[uint8 ,uint16, uint32, uint64]]]
    :param size_check: Optional.  When specified, indicates a type to unpack
        (after the array size if applicable) which indicates the packed size
        of the array elements in bytes.
    :type size_check: type[Union[uint8, uint16, uint32, uint64]]
    :param array_type: The type of object stored in the array.
    :type array_type: type[Union[format_type, Structured]]

    """
    @classmethod
    def error(cls, exc_type: type[Exception], msg: str) -> NoReturn:
        """Helper to add 'array[] to the beginning of exception messages, and
        raise the exception.

        :param exc_type: Exception type to raise
        :param msg: Exception message
        """
        raise exc_type(f'{cls.__qualname__}[] {msg}')

    @classmethod
    def _process_args(cls, args: Any) -> tuple[tuple, dict[str, Any]]:
        """Parse array indexing arguments into keyword arguments (those passed
        with the 'array_size', 'size_check', and 'array_type' marker classes),
        and regular arguments.  Also performs error checking on duplicate
        marker classes.

        :param args: arguments passed to array[]
        :return: The resulting arguments and keyword arguments
        """
        if not isinstance(args, tuple):
            args = (args, )
        final_args = []
        kwargs = {}
        for arg in args:
            for cont_cls in (array_size, size_check, array_type):
                if isinstance(arg, cont_cls):
                    if cont_cls.__name__ in kwargs:
                        cls.error(
                            TypeError,
                            f"argument repeated: '{cont_cls.__name__}'"
                        )
                    kwargs[cont_cls.__name__] = container.unwrap(arg)
                    break
            else:
                final_args.append(arg)
        return tuple(final_args), kwargs

    @classmethod
    @cache
    def __class_getitem__(cls, args) -> type[Serializer]:
        """Perform error checks and dispatch to the applicable class factory."""
        args, kwargs = cls._process_args(args)
        try:
            return cls._create_2_arg(*args, **kwargs)
        except TypeError:
            pass
        return cls._create_3_arg(*args, **kwargs)


    @classmethod
    def _check_count(cls, count: Union[int, type[SizeTypes]]) -> None:
        """Verify the count argument is of the correct type and value (> 0).

        :param count: Count unpack type or static size
        """
        if isinstance(count, int):
            if count <= 0:
                cls.error(ValueError, 'count must be positive')
        elif not isinstance(count, type) or not issubclass(count, SizeTypes):
            cls.error(TypeError, 'count must be an integer or a uint* type.')

    @classmethod
    def _check_object_type(
            cls,
            obj_type: Union[type[format_type],
            type[Structured]],
        ) -> None:
        """Verify the array object type is of the correct type.

        :param obj_type: A format_type or Structured class.
        """
        if (not isinstance(obj_type, type) or
            not issubclass(obj_type, (format_type, Structured))
        ):
            cls.error(
                TypeError,
                'object type must be a format_type or a Structured class'
            )

    @classmethod
    def _check_size_check(cls, check: type[SizeTypes]) -> None:
        """Verify the array size check argument is of the correct type.

        :param check: the size check type for the array
        """
        if not isinstance(check, type) or not issubclass(check, SizeTypes):
            cls.error(TypeError, 'size check must be a uint* type')

    @classmethod
    def _create_2_arg(
            cls,
            count: Union[int, type[SizeTypes]],
            obj_type: Union[type[format_type],
            type[Structured]],
        ) -> type[Serializer]:
        """Two-arg class creator for array[], creating a no size check array.

        NOTE: argument names must match the marker class names.

        :param count: Static size or count type for the array
        :param obj_type: Array object type
        :return: The specialized array class
        """
        cls._check_count(count)
        cls._check_object_type(obj_type)
        if isinstance(count, int):
            if issubclass(obj_type, format_type):
                array_cls = format_array(count, obj_type)
            else:
                array_cls = structured_array(count, obj_type)
        else:
            if issubclass(obj_type, format_type):
                array_cls = dynamic_format_array(count, obj_type)
            else:
                array_cls = dynamic_structured_array(count, obj_type)
        return specialized(cls, count, obj_type)(array_cls)

    @classmethod
    def _create_3_arg(
            cls,
            array_size: Union[int, type[SizeTypes]],
            size_check: type[SizeTypes],
            array_type: Union[type[format_type], type[Structured]],
        ) -> type[Serializer]:
        """Three-arg class creator for array[], creating a size checked array.

        NOTE: argument names must match the marker class names.

        :param count: Static size or count type for the array
        :param size_check:
        :param obj_type: Array object type
        :return: The specialized array class
        """
        cls._check_count(array_size)
        cls._check_object_type(array_type)
        cls._check_size_check(size_check)
        if issubclass(array_type, format_type):
            cls.error(
                TypeError,
                'size check only supported for arrays of Structured objects.'
            )
        if isinstance(array_size, int):
            array_cls = checked_structured_array(
                array_size, size_check, array_type
            )
        else:
            array_cls = dynamic_checked_structured_array(
                array_size, size_check, array_type
            )
        return specialized(cls, array_size, size_check, array_type)(array_cls)


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


def format_array(
        count_val: int,
        array_obj_type: type[format_type],
    ) -> type[Serializer]:
    """Create an array specialization for a static array of format_type objects.

    :param count_val: Static size of the specialization.
    :param array_obj_type: format_type subclass of the objects to store.
    :return: The specialized class.
    """
    class _array(_format_array):
        count = count_val
        obj_type = array_obj_type
    return _array


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


def dynamic_format_array(
        count: type[SizeTypes],
        array_obj_type: type[format_type],
    ) -> type[Serializer]:
    """Create an array specialization for a dynamically sized array of
    format_type objects.

    :param count: Type to pack/unpack to determine the array length.
    :type count: type[Union[uint8, uint16, uint32, uint64]]
    :param array_obj_type: format_type subclass of the objects in the array.
    :type array_obj_type: type[format_type]
    :return: The specialized array class.
    """
    class _array(_dynamic_format_array):
        count_type = count
        obj_type = array_obj_type
    return _array


class _header:
    """Base class for packing/unpacking the header for a Structured array.  The
    header consists of optionally an array length, and a array data size.  To
    create a concrete implementation of a header, subclass and provide the
    following:

    __init__: Should take the ByteOrder for the array.
    pack_header: Given an array length and array data size, pack any or all of
        this information using `packer`, which is one of `pack`, `pack_into`,
        or `pack_write` of the StructSerializer class, already partially called
        (via functools.partial).  That is, the packer *only* takes the values
        to pack.
    unpack_header: Unpacks (if necessary) the array length and array data size
        using `unpacker`, which is one of `self.header.unpack`,
        `self.header.unpack_from`, or `self.header.unpack_read` of this object.
        That is, the unpacker will unpack whatever values, this method should
        fill in any value not handled by the unpacker, and return a tuple of
        (array_count, array_data_size).
    check_size: raise an error if applicable if the given expected size is not
        correct.

    If the array data size is unknown before packing the actual array elements,
    set the ClassVar `two_pass` to `True`, and the header will be packed a
    second time *after* the array elements are packed, with the correct data
    size.
    """
    two_pass: ClassVar[bool] = False

    header: StructSerializer
    size: int

    def __init__(self, byte_order: ByteOrder, fmt: Optional[str] =  '') -> None:
        """Create the StructSerializer for unpacking the header information, and
        set the static size of this header.

        :param byte_order: The byte order to use for packing/unpacking.
        :param fmt: Optional format specifier for the header.
        """
        self.header = struct_cache(fmt, byte_order=byte_order)
        self.size = 0

    def pack_header(self, packer, count, data_size) -> None:
        """Pack the header for an array.

        :param packer: One of `pack`, `pack_into`, or `pack_write` bound to
            this object's self.header, with all arguments already specified
            except the values to pack (count, data_size).
        :param count: Number of elements in the array.
        :param data_size: Packed size of the array (may be 0 for two_pass).
        """

    def unpack_header(self, unpacker) -> tuple[int, int]:
        """Unpack the header for an array.

        :param unpacker: One of `unpack`, `unpack_from`, or `unpack_read` bound
            to this object's self.header, with all parameters already provided.
            That is, simply calling the unpacker unpacks whichever values
            self.header is set up to unpack.
        :return: The array length and array data size
        """
        raise NotImplementedError   # pragma: no cover

    def check_size(self, expected_size: int):
        """Verify the array unpacked using the correct number of bytes.

        NOTE: Since _headers are used as mixin classes, you have access to
        the array's self.size attribute for calculating actual array data size.

        :param expected_size: Expected size of the packed array.
        """


class _static_header(_header):
    """An array header for a statically sized array with no size checks.

    To specialize, subclass and set the following ClassVars:

    :param count: Static size of the array
    :type count: int
    """
    count: ClassVar[int]

    def pack_header(self, packer, count, data_size) -> None:
        """Pack the header for the array.  Check that the array size matches
        the static size specified for this header.

        :param packer: Packer used for packing the header (unused).
        :param count: Array length.
        :param data_size: Array data size (unused)
        :raises ValueError: If `count` does not match the static size for this
            header.
        """
        if count != self.count:
            raise ValueError(
                f'array length must be {self.count} to pack, got {count}'
            )

    def unpack_header(self, unpacker) -> tuple[int, int]:
        """'Unpack' the header for an array.  Always returns the static size
        for this header, and 0 for data size.

        :param unpacker: The unpacker to use (unused).
        :return: The static size of the array, and 0 for the data size.
        """
        return self.count, 0


class _checked_static_header(_static_header):
    """An array header for a statically sized array with a array data size
    check just prior.  To speciallize, subclass and set the following:

    :param size_type: format_type of the array data size indicator.
    :type size_type: type[Union[uint8, uint16, uint32, uint64]]
    """
    two_pass: ClassVar[bool] = True

    size_type: ClassVar[type[SizeTypes]]

    def __init__(self, byte_order: ByteOrder) -> None:
        """Setup the header unpacker."""
        super().__init__(byte_order, self.size_type.format)

    def pack_header(self, packer, count: int, data_size: int):
        """Pack the array header.

        :param packer: Packer to use.
        :param count: Array length (unused).
        :param data_size: Size of the packed array elements.
        """
        super().pack_header(packer, count, 0)
        packer(data_size)

    def unpack_header(self, unpacker) -> tuple[int, int]:
        """Unpack an array header.

        :param unpacker: Unpacker to use.
        :return: The static size of the array, and the expected size of the
            packed array.
        """
        return self.count, unpacker()[0]

    def check_size(self, expected_size: int):
        """Verify the unpacked array is of the expected size.

        :param expected_size: Expected packed size of the array.
        :raises ValueError: If the array did not use the expected data size.
        """
        data_size = self.size - self.header.size
        if data_size != expected_size:
            raise ValueError(
                f'expected packed array size of {expected_size}, but got '
                f'{data_size}'
            )


class _dynamic_header(_header):
    """An array header for a dynamically sized array with no size check. To
    specialize, subclass and set the following ClassVars:

    :param count_type: The format_type subclass used to store the array length.
    :type count_type: type[Union[uint8, uint16, uint32, uint64]]
    """
    count_type: ClassVar[type[SizeTypes]]

    def __init__(self, byte_order: ByteOrder) -> None:
        """Setup the header packer/unpacker."""
        super().__init__(byte_order, self.count_type.format)

    def pack_header(self, packer, count: int, data_size: int):
        """Pack the array header.

        :param packer: The packer to use.
        :param count: Number of elements in the array.
        :param data_size: Packed size of the array (unused).
        """
        packer(count)

    def unpack_header(self, unpacker) -> tuple[int, int]:
        """Unpack an array header.

        :param unpacker: The unpacker to use.
        :return: The array length, and 0 for the expected size.
        """
        return unpacker()[0], 0


class _checked_dynamic_header(_dynamic_header):
    """An array header for a dynamically sized array with a data size check. To
    specialize, subclass and set the following ClassVars:

    :param count_type: The format_type holding the length of the array.
    :type count_type: type[Union[uint8, uint16, uint32, uint64]]
    :param size_type: The format_type holding the packed size of the array.
    :type size_type: type[Union[uint8, uint16, uint32, uint64]]
    """
    size_type: ClassVar[type[SizeTypes]]
    two_pass: ClassVar[bool] = True

    def __init__(self, byte_order: ByteOrder) -> None:
        """Setup the header packer/unpacker."""
        fmt = f'{self.count_type.format}{self.size_type.format}'
        # Call _header's init, not _dynamic_header's, since we're not using
        # the same StructSerializer that _dynamic_header would make.
        _header.__init__(self, byte_order, fmt)

    def pack_header(self, packer, count: int, data_size: int):
        """Pack the array header.

        :param packer: Packer to use.
        :param count: Number of elements in the array.
        :param data_size: Packed size of the array elements.
        """
        packer(count, data_size)

    def unpack_header(self, unpacker) -> tuple[int, int]:
        """Unpack an array header.

        :param unpacker: Unpacker to use.
        :return: The number of elements and the packed size of the elements.
        """
        return unpacker()


class _structured_array(_header, Serializer):
    """Base for all arrays of Structured objects.  Subclass along with a
    _header subclass to get the desired array type.  NOTE: The _header subclass
    must be first in the base class sequence, to ensure the init method of the
    header is called.  To specialize, subclass and set the following ClassVars:

    :param obj_type: The type of object stored in the array.
    :type obj_type: type[Structured]
    :param header_type: A specialized _header subclass implementing the desired
        functionality.
    :type header_type: type[_header]
    """
    obj_type: ClassVar[type[Structured]]

    def pack(self, *values: Any) -> bytes:
        """Pack an array into bytes.

        :return: The packed array.
        """
        with io.BytesIO() as out:
            self.pack_write(out, *values)   # type: ignore
            return out.getvalue()

    def pack_into(self, buffer: WritableBuffer, offset: int, *values) -> None:
        """Pack an array into a buffer supporting the Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Location in the buffer to place the packed data.
        """
        arr: list[Structured] = values[0]
        count = len(arr)
        # Not necessary here, but do it for the error check on array size.
        # We could skip it until the end, but if the array is of the wrong size,
        # we'll get an obscure struct.error exception instead of our more
        # descriptive one.
        self.pack_header(
            partial(self.header.pack_into, buffer, offset), count, 0
        )
        self.size = self.header.size
        for item in arr:
            item.pack_into(buffer, offset + self.size)
            self.size += item.serializer.size
        data_size = self.size - self.header.size
        self.pack_header(
            partial(self.header.pack_into, buffer, offset), count, data_size
        )

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        """Pack an array and write it to a writable file-like object.

        :param writable: A writable file-like object.
        """
        arr: list[Structured] = values[0]
        count = len(arr)
        self.size = self.header.size
        if self.two_pass:
            header_pos = writable.tell()        # type: ignore
        else:
            header_pos = 0
        header_packer = partial(self.header.pack_write, writable)
        self.pack_header(header_packer, count, 0)
        for item in arr:
            item.pack_write(writable)
            self.size += item.serializer.size
        if self.two_pass:
            data_size = self.size - self.header.size
            final_pos = writable.tell()     # type: ignore
            writable.seek(header_pos)       # type: ignore
            self.pack_header(header_packer, count, data_size)
            writable.seek(final_pos)        # type: ignore

    def _item_unpacker(self, buffer: ReadableBuffer) -> Structured:
        """Helper for _unpack, unpacks an item from the correct position in a
        bytes-like object.

        :param buffer: The bytes-like object to unpack from.
        """
        return self.obj_type.create_unpack(buffer[self.size:])

    def _item_unpacker_from(
            self,
            buffer: ReadableBuffer,
            offset: int,
        ) -> Structured:
        """Helper for _unpack, unpacks an item from the correct position in a
        buffer supporting the Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Start location in the buffer for the array.
        """
        return self.obj_type.create_unpack_from(buffer, offset + self.size)

    def _unpack(self, header_unpacker, item_unpacker):
        """Unpack an array, using the specific variants of unpack, unpack_from,
        or unpack_read for the header and the array.  The unpackers should be
        callable with no arguments (so set up with functools.partial if
        necessary).

        :param header_unpacker: Header unpacking function.
        :param item_unpacker: Item unpacking function.
        :return: The unpacked array, contained as a single element in a tuple.
        """
        self.size = self.header.size
        count, expected_size = self.unpack_header(header_unpacker)
        arr = []
        for i in range(count):
            arr.append(item_unpacker())
            self.size += arr[-1].serializer.size
        self.check_size(expected_size)
        return arr,

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        """Unpack an array from a bytes-like buffer.

        :param buffer: The buffer to unpack from.
        :return: The unpacked array, contained as a single element in a tuple.
        """
        return self._unpack(
            partial(self.header.unpack, buffer),
            partial(self._item_unpacker, buffer),
        )

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        """Unpack an array from a buffer supporting the Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Location in the buffer where the array + header starts.
        :return: The unpacked array, contained as a single element in a tuple.
        """
        return self._unpack(
            partial(self.header.unpack_from, buffer, offset),
            partial(self._item_unpacker_from, buffer, offset)
        )

    def unpack_read(self, readable: SupportsRead) -> tuple:
        """Unpack an array from a readable file-like object.

        :param readable: A readable file-like object.
        :return: The unpacked array, contained as a single element in a tuple.
        """
        return self._unpack(
            partial(self.header.unpack_read, readable),
            partial(self.obj_type.create_unpack_read, readable=readable)
        )


def structured_array(
        count_val: int,
        o_type: type[Structured],
    ) -> type[Serializer]:
    """Create a specialization for a statically sized array of Structured
    objects with no size check.

    :param count_val: Static size of the array.
    :param o_type: Structured type of object to store in the array.
    :return: The specialized array.
    """
    class _array(_static_header, _structured_array):
        count: ClassVar[int] = count_val
        obj_type: ClassVar[type[Structured]] = o_type
    return _array


def checked_structured_array(
        count_val: int,
        check_type: type[SizeTypes],
        o_type: type[Structured],
    ) -> type[Serializer]:
    """Create a specialization for a statically sized array of Structured
    objects with a size check.

    :param count_val: Static size of the array.
    :param check_type: format_type used to store the packed size of the array.
    :param o_type: Structured type of object to store in the array.
    :return: The specialized array.
    """
    class _array(_checked_static_header, _structured_array):
        count: ClassVar[int] = count_val
        size_type: ClassVar[type[SizeTypes]] = check_type
        obj_type: ClassVar[type[Structured]] = o_type
    return _array


def dynamic_structured_array(
        count: type[SizeTypes],
        o_type: type[Structured],
    ) -> type[Serializer]:
    """Create a specialization for a dynamically sized array of Structured
    objects with no size check.

    :param count: format_type used to store the array length.
    :param o_type: Structured type of object to store in the array.
    :return: The specialized array.
    """
    class _array(_dynamic_header, _structured_array):
        count_type: ClassVar[type[SizeTypes]] = count
        obj_type: ClassVar[type[Structured]] = o_type
    return _array


def dynamic_checked_structured_array(
        count: type[SizeTypes],
        check_type: type[SizeTypes],
        o_type: type[Structured],
    ) -> type[Serializer]:
    """Create a specialization for a dynamically sized array of Structured
    objects with a size check.

    :param count: format_type used to store the array length.
    :param check_type: format_type used to store the packed array size.
    :param o_type: Structured type of object to store in the array.
    :return: The speciailized array.
    """
    class _array(_checked_dynamic_header, _structured_array):
        count_type: ClassVar[type[SizeTypes]] = count
        size_type: ClassVar[type[SizeTypes]] = check_type
        obj_type: ClassVar[type[Structured]] = o_type
    return _array

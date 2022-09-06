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
from itertools import chain, repeat

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
     """
    @classmethod
    def error(cls, exc_type: type[Exception], msg: str) -> NoReturn:
        raise exc_type(f'{cls.__qualname__}[] {msg}')

    @classmethod
    def _process_args(cls, args: Any) -> tuple[tuple, dict[str, Any]]:
        if not isinstance(args, tuple):
            args = (args, )
        final_args = []
        kwargs = {}
        for arg in args:
            for cont_cls in (array_size, size_check, array_type):
                if isinstance(arg, cont_cls):
                    if cont_cls.__name__ in kwargs:
                        cls.error(TypeError, f"argument repeated: '{cont_cls.__name__}'")
                    kwargs[cont_cls.__name__] = container.unwrap(arg)
                    break
            else:
                final_args.append(arg)
        return tuple(final_args), kwargs

    def __class_getitem__(cls, args) -> type[Serializer]:
        args, kwargs = cls._process_args(args)
        try:
            return cls._create_2_arg(*args, **kwargs)
        except TypeError:
            pass
        return cls._create_3_arg(*args, **kwargs)


    @classmethod
    def _check_count(cls, count: Union[int, type[SizeTypes]]) -> None:
        if isinstance(count, int):
            if count <= 0:
                cls.error(ValueError, 'count must be positive')
        elif not isinstance(count, type) or not issubclass(count, SizeTypes):
            cls.error(TypeError, 'count must be an integer or a uint* type.')

    @classmethod
    def _check_object_type(cls, obj_type: Union[type[format_type], type[Structured]]) -> None:
        if not isinstance(obj_type, type) or not issubclass(obj_type, (format_type, Structured)):
            cls.error(TypeError, 'object type must be a format_type or a Structured class')

    @classmethod
    def _check_size_check(cls, check: type[SizeTypes]) -> None:
        if not isinstance(check, type) or not issubclass(check, SizeTypes):
            cls.error(TypeError, 'size check must be a uint* type')

    @classmethod
    def _create_2_arg(cls, count: Union[int, type[SizeTypes]], obj_type: Union[type[format_type], type[Structured]]) -> type[Serializer]:
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
    def _create_3_arg(cls, array_size: Union[int, type[SizeTypes]], size_check: type[SizeTypes], array_type: Union[type[format_type], type[Structured]]) -> type[Serializer]:
        cls._check_count(array_size)
        cls._check_object_type(array_type)
        cls._check_size_check(size_check)
        if issubclass(array_type, format_type):
            cls.error(TypeError, 'size check only supported for arrays of Structured objects.')
        if isinstance(array_size, int):
            array_cls = checked_structured_array(array_size, size_check, array_type)
        else:
            array_cls = dynamic_checked_structured_array(array_size, size_check, array_type)
        return specialized(cls, array_size, size_check, array_type)(array_cls)


class _format_array(Serializer):
    count: ClassVar[int]
    obj_type: ClassVar[type[format_type]]

    size: int

    def __init__(self, byte_order: ByteOrder):
        actions = tuple(repeat(self.obj_type.unpack_action, self.count))
        fmt = f'{byte_order.value}{self.count}{self.obj_type.format}'
        self.serializer = struct_cache(fmt, actions)
        self.size = self.serializer.size

    def _check_arr(self, values: tuple) -> list:
        arr = values[0]
        if (count := len(arr)) != self.count:
            raise ValueError(f'array length must be {self.count} to pack, got {count}')
        return arr

    def pack(self, *values: Any) -> bytes:
        return self.serializer.pack(*self._check_arr(values))

    def pack_into(
            self,
            buffer: WritableBuffer,
            offset: int,
            *values: Any,
        ) -> None:
        self.serializer.pack_into(buffer, offset, *self._check_arr(values))

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        self.serializer.pack_write(writable, *self._check_arr(values))

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        return list(self.serializer.unpack(buffer[:self.size])),

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        return list(self.serializer.unpack_from(buffer, offset)),

    def unpack_read(self, readable: SupportsRead) -> tuple:
        return list(self.serializer.unpack_read(readable)),


def format_array(
        count_val: int,
        array_obj_type: type[format_type],
    ) -> type[Serializer]:
    class _array(_format_array):
        count = count_val
        obj_type = array_obj_type
    return _array


class _dynamic_format_array(Serializer):
    count_type: ClassVar[type[SizeTypes]]
    obj_type: ClassVar[type[format_type]]

    size: int

    def __init__(self, byte_order: ByteOrder) -> None:
        self.size = 0
        fmt = f'{byte_order.value}{self.count_type.format}'
        self.header = struct_cache(fmt)
        self.byte_order = byte_order.value

    def _arr_count_st(self, values: tuple[Any, ...]) -> tuple[list, int, StructSerializer]:
        arr = values[0]
        count = len(arr)
        fmt = f'{self.byte_order}{self.count_type.format}{count}{self.obj_type.format}'
        st = struct_cache(fmt)
        self.size = st.size
        return arr, count, st

    def pack(self, *values: Any) -> bytes:
        arr, count, st = self._arr_count_st(values)
        return st.pack(count, *arr)

    def pack_into(
            self,
            buffer: WritableBuffer,
            offset: int,
            *values: Any,
        ) -> None:
        arr, count, st = self._arr_count_st(values)
        st.pack_into(buffer, offset, count, *arr)

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        arr, count, st = self._arr_count_st(values)
        st.pack_write(writable, count, *arr)

    def _st(self, count: int) -> StructSerializer:
        actions = tuple(repeat(self.count_type.unpack_action, count))
        fmt = f'{self.byte_order}{count}{self.obj_type.format}'
        return struct_cache(fmt, actions)

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        count = self.header.unpack(buffer)[0]
        st = self._st(count)
        return list(st.unpack(buffer[self.header.size:])),

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        count = self.header.unpack_from(buffer, offset)[0]
        st = self._st(count)
        return list(st.unpack_from(buffer, offset + self.header.size)),

    def unpack_read(self, readable: SupportsRead) -> tuple:
        count = self.header.unpack_read(readable)[0]
        st = self._st(count)
        return list(st.unpack_read(readable)),


def dynamic_format_array(
        count: type[SizeTypes],
        array_obj_type: type[format_type],
    ) -> type[Serializer]:
    class _array(_dynamic_format_array):
        count_type = count
        obj_type = array_obj_type
    return _array


class _header:
    two_pass: ClassVar[bool] = False

    header: StructSerializer
    size: int

    def __init__(self, byte_order: ByteOrder, fmt: Optional[str] =  '') -> None:
        self.header = struct_cache(fmt, byte_order=byte_order)
        self.size = 0
    def pack_header(self, packer, count, data_size) -> None:
        pass    # pragma: no cover
    def unpack_header(self, unpacker) -> tuple[int, int]:
        raise NotImplementedError   # pragma: no cover
    def check_size(self, expected_size: int):
        pass


class _static_header(_header):
    count: ClassVar[int]

    def pack_header(self, packer, count, data_size) -> Optional[bytes]:
        if count != self.count:
            raise ValueError(
                f'array length must be {self.count} to pack, got {count}'
            )
    def unpack_header(self, unpacker):
        return self.count, 0


class _checked_static_header(_static_header):
    two_pass: ClassVar[bool] = True

    size_type: ClassVar[type[SizeTypes]]

    def __init__(self, byte_order: ByteOrder) -> None:
        super().__init__(byte_order, self.size_type.format)
    def pack_header(self, packer, count: int, data_size: int):
        super().pack_header(packer, count, 0)
        packer(data_size)
    def unpack_header(self, unpacker) -> tuple[int, int]:
        return self.count, unpacker()[0]
    def check_size(self, expected_size: int):
        data_size = self.size - self.header.size
        if data_size != expected_size:
            raise ValueError(
                f'expected packed array size of {expected_size}, but got '
                f'{data_size}'
            )


class _dynamic_header(_header):
    count_type: ClassVar[type[SizeTypes]]

    def __init__(self, byte_order: ByteOrder) -> None:
        super().__init__(byte_order, self.count_type.format)
    def pack_header(self, packer, count: int, data_size: int):
        packer(count)
    def unpack_header(self, unpacker) -> tuple[int, int]:
        return unpacker()[0], 0


class _checked_dynamic_header(_dynamic_header):
    size_type: ClassVar[type[SizeTypes]]
    two_pass: ClassVar[bool] = True

    def __init__(self, byte_order: ByteOrder) -> None:
        fmt = f'{self.count_type.format}{self.size_type.format}'
        _header.__init__(self, byte_order, fmt)
    def pack_header(self, packer, count: int, data_size: int):
        packer(count, data_size)
    def unpack_header(self, unpacker) -> tuple[int, int]:
        return unpacker()


class _structured_array(_header, Serializer):
    """Base funtionality for packing/unpacking *just* the items in the array"""
    obj_type: ClassVar[type[Structured]]

    def pack(self, *values: Any) -> bytes:
        with io.BytesIO() as out:
            self.pack_write(out, *values)   # type: ignore
            return out.getvalue()

    def pack_into(self, buffer: WritableBuffer, offset: int, *values) -> None:
        arr: list[Structured] = values[0]
        count = len(arr)
        # Not necessary here, but do it for the error check on array size
        self.pack_header(partial(self.header.pack_into, buffer, offset), count, 0)
        self.size = self.header.size
        for item in arr:
            item.pack_into(buffer, offset + self.size)
            self.size += item.serializer.size
        data_size = self.size - self.header.size
        self.pack_header(partial(self.header.pack_into, buffer, offset), count, data_size)

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
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
        return self.obj_type.create_unpack(buffer[self.size:])
    def _item_unpacker_from(
            self,
            buffer: ReadableBuffer,
            offset: int,
        ) -> Structured:
        return self.obj_type.create_unpack_from(buffer, offset + self.size)

    def _unpack(self, header_unpacker, item_unpacker):
        self.size = self.header.size
        count, expected_size = self.unpack_header(header_unpacker)
        arr = []
        for i in range(count):
            arr.append(item_unpacker())
            self.size += arr[-1].serializer.size
        self.check_size(expected_size)
        return arr,

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        return self._unpack(
            partial(self.header.unpack, buffer),
            partial(self._item_unpacker, buffer),
        )

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        return self._unpack(
            partial(self.header.unpack_from, buffer, offset),
            partial(self._item_unpacker_from, buffer, offset)
        )

    def unpack_read(self, readable: SupportsRead) -> tuple:
        return self._unpack(
            partial(self.header.unpack_read, readable),
            partial(self.obj_type.create_unpack_read, readable=readable)
        )


def structured_array(count_val: int, o_type: type[Structured]) -> type[Serializer]:
    class _array(_static_header, _structured_array):
        count: ClassVar[int] = count_val
        obj_type: ClassVar[type[Structured]] = o_type
    return _array


def checked_structured_array(
        count_val: int,
        check_type: type[SizeTypes],
        o_type: type[Structured],
    ) -> type[Serializer]:
    class _array(_checked_static_header, _structured_array):
        count: ClassVar[int] = count_val
        size_type: ClassVar[type[SizeTypes]] = check_type
        obj_type: ClassVar[type[Structured]] = o_type
    return _array


def dynamic_structured_array(
        count: type[SizeTypes],
        o_type: type[Structured],
    ) -> type[Serializer]:
    class _array(_dynamic_header, _structured_array):
        count_type: ClassVar[type[SizeTypes]] = count
        obj_type: ClassVar[type[Structured]] = o_type
    return _array


def dynamic_checked_structured_array(
        count: type[SizeTypes],
        check_type: type[SizeTypes],
        o_type: type[Structured],
    ) -> type[Serializer]:
    class _array(_checked_dynamic_header, _structured_array):
        count_type: ClassVar[type[SizeTypes]] = count
        size_type: ClassVar[type[SizeTypes]] = check_type
        obj_type: ClassVar[type[Structured]] = o_type
    return _array

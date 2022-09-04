"""
Array types
"""
from __future__ import annotations
from functools import partial

__all__ = [
    'size_check',
    'array',
]

import io
from itertools import repeat

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


class size_check(container):
    def check(self, wrapped):
        if (wrapped is not None or
            not isinstance(wrapped, type) or
            not issubclass(wrapped, SizeTypes)
            ):
            raise TypeError('Size check must be None or a uint* type')



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

    def __class_getitem__(cls, key) -> type[Serializer]:
        if not isinstance(key, tuple):
            key = (key, )
        if len(key) == 3:
            count, check, obj_type = key
        elif len(key) == 2:
            count, obj_type = key
            check = None
        else:
            cls.error(
                TypeError,
                f'requires 2-3 arguments, but {len(key)} were given',
            )
        # Size check type, type checking performed in the class
        if not isinstance(check, size_check):
            check = size_check(check)
        # object type
        if (not isinstance(obj_type, type) or
            not issubclass(obj_type, (format_type, Structured))):
            cls.error(
                TypeError,
                'object type must be a format_type or a Structured class'
            )
        # format_type arrays don't support size checking
        if issubclass(obj_type, format_type) and check.wrapped is not None:
            cls.error(
                TypeError,
                'arrays of format_type objects do not support size checks'
            )
        # count
        if isinstance(count, int) and count <= 0:
            cls.error(ValueError, 'count must be positive')
        elif not isinstance(count, type) or not issubclass(count, SizeTypes):
            cls.error(TypeError, 'count must be an integer or a uint* type.')

        # Dispatch
        if isinstance(count, int):
            if issubclass(obj_type, format_type):
                array_cls = format_array(count, obj_type)
            else:
                if check.wrapped is None:
                    array_cls = structured_array(count, obj_type)
                else:
                    array_cls = checked_structured_array(
                        count, check.wrapped, obj_type
                    )
        else:
            if issubclass(obj_type, format_type):
                array_cls = dynamic_format_array(count, obj_type)
            else:
                if check.wrapped is None:
                    array_cls = dynamic_structured_array(count, obj_type)
                else:
                    array_cls = dynamic_checked_structured_array(
                        count, check.wrapped, obj_type
                    )
        return specialized(cls, key)(array_cls)


class _format_array(Serializer):
    count: ClassVar[int]
    obj_type: ClassVar[type[format_type]]

    size: int

    def __init__(self, byte_order: ByteOrder):
        actions = tuple(repeat(self.obj_type.unpack_action, self.count))
        fmt = f'{byte_order.value}{self.count}{self.obj_type.format}'
        self.serializer = struct_cache(fmt, actions)
        self.size = self.serializer.size

    def pack(self, *values: Any) -> bytes:
        return self.serializer.pack(*values[0])

    def pack_into(
            self,
            buffer: WritableBuffer,
            offset: int,
            *values: Any,
        ) -> None:
        self.serializer.pack_into(buffer, offset, *values[0])

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        writable.write(self.serializer.pack(*values[0]))

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

    def _pack(self, values: tuple[Any, ...], packer, *packer_args):
        arr = values[0]
        fmt = f'{self.byte_order}{len(arr)}{self.count_type.format}'
        st = struct_cache(fmt)
        self.size = st.size
        return packer(*packer_args, *arr)

    def pack(self, *values: Any) -> bytes:
        return self._pack(values, StructSerializer.pack)

    def pack_into(
            self,
            buffer: WritableBuffer,
            offset: int,
            *values: Any,
        ) -> None:
        self._pack(values, StructSerializer.pack_into, buffer, offset)

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        self._pack(values, StructSerializer.pack_write, writable)

    def _unpack_count(self, unpacker: str, *count_args):
        # user getattr, since st might be either a StructSerializer or a
        # StructActionSerializer
        up = getattr(self.header, unpacker)
        count = up(*count_args)[0]
        actions = tuple(repeat(self.count_type.unpack_action, count))
        fmt = f'{self.byte_order}{count}{self.count_type.format}'
        st = struct_cache(fmt, actions)
        self.size = self.header.size + st.size
        return st

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        data_start = self.header.size
        st = self._unpack_count('unpack', buffer[:data_start])
        return list(st.unpack(buffer[data_start:data_start+st.size])),

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        st = self._unpack_count('unpack_from', buffer, offset)
        offset += self.header.size
        return list(st.unpack_from(buffer, offset)),

    def unpack_read(self, readable: SupportsRead) -> tuple:
        st = self._unpack_count('unpack_read', readable)
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

    def __init__(self, byte_order: ByteOrder) -> None:
        self.header = struct_cache('')
        self.size = 0
    def pack_header(self, packer, count, data_size) -> None:
        pass
    def unpack_header(self, unpacker) -> tuple[int, int]:
        raise NotImplementedError
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
        self.header = struct_cache(self.size_type.format, byte_order=byte_order)
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
        self.header = struct_cache(
            self.count_type.format, byte_order=byte_order
        )
    def pack_header(self, packer, count: int, data_size: int):
        packer(count)
    def unpack_header(self, unpacker) -> tuple[int, int]:
        return unpacker()[0], 0


class _checked_dynamic_header(_dynamic_header):
    size_type: ClassVar[type[SizeTypes]]
    two_pass: ClassVar[bool] = True

    def __init__(self, byte_order: ByteOrder) -> None:
        fmt = f'{self.count_type.format}{self.size_type.format}'
        self.header = struct_cache(fmt, byte_order=byte_order)
    def pack_header(self, packer, count: int, data_size: int):
        packer(count, data_size)
    def unpack_header(self, unpacker) -> tuple[int, int]:
        return unpacker()


class _structured_array(Serializer, _header):
    """Base funtionality for packing/unpacking *just* the items in the array"""
    obj_type: ClassVar[type[Structured]]

    def pack(self, *values: Any) -> bytes:
        with io.BytesIO() as out:
            self.pack_write(out, *values)   # type: ignore
            return out.getvalue()

    def pack_into(self, buffer: WritableBuffer, offset: int, *values) -> None:
        arr: list[Structured] = values[0]
        count = len(arr)
        self.size = self.header.size
        for item in arr:
            item.pack_into(buffer, offset + self.size)
            self.size += item.serializer.size
        data_size = self.size - self.header.size
        self.pack_header(self.header.pack_into, count, data_size)

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        arr: list[Structured] = values[0]
        count = len(arr)
        self.size = self.header.size
        if self.two_pass:
            header_pos = writable.tell()        # type: ignore
        else:
            header_pos = 0
        self.pack_header(self.header.pack_write, count, 0)
        for item in arr:
            item.pack_write(writable)
            self.size += item.serializer.size
        if self.two_pass:
            data_size = self.size - self.header.size
            final_pos = writable.tell()     # type: ignore
            writable.seek(header_pos)       # type: ignore
            self.pack_header(self.header.pack_write, count, data_size)
            writable.seek(final_pos)        # type: ignore

    def _item_unpacker(self, buffer: ReadableBuffer, item: Structured) -> None:
        item.unpack(buffer[self.size:])
    def _item_unpacker_from(
            self,
            buffer: ReadableBuffer,
            offset: int,
            item: Structured,
        ) -> None:
        item.unpack_from(buffer, offset + self.size)

    def _unpack(self, header_unpacker, item_unpacker):
        self.size = self.header.size
        count, expected_size = self.unpack_header(header_unpacker)
        arr = []
        for i in range(count):
            item = self.obj_type()
            item_unpacker(item)
            self.size += item.serializer.size
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
            partial(self.obj_type.unpack_read, readable=readable)
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

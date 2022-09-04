"""
Dynamically sized binary blobs.
"""
__all__ = [
    'blob',
]

from ..base_types import *
from ..basic_types import *
from ..type_checking import Union


SizeTypes = Union[uint8, uint16, uint32, uint64]
CountTypes = Union[type[SizeTypes], int]


class blob(bytes, requires_indexing):
    @classmethod
    @cache
    def __class_getitem__(
            cls,
            count: type[CountTypes],
        ) -> Union[type[Serializer], type[char]]:
        if isinstance(count, type) and issubclass(count, SizeTypes):
            _blob = cls.prefixed_blob(count)
        elif isinstance(count, int):
            return char[count]
        else:
            raise TypeError(
                f'{cls.__qualname__} count must be one of `uint*`, an integer, '
                'or an attribute name.'
            )
        return specialized(cls, count)(_blob)

    @classmethod
    def prefixed_blob(cls, count_type: type[SizeTypes]) -> type[Serializer]:
        count_fmt = count_type.format
        class _blob(Serializer):
            def __init__(self, byte_order: ByteOrder) -> None:
                self.byte_order = byte_order.value
                self.count_st = struct_cache(f'{self.byte_order}{count_fmt}')
                self.size = 0

            def _packer(self, values: tuple[bytes]) -> tuple[StructSerializer, int, bytes]:
                raw_data = values[0]
                count = len(raw_data)
                st = struct_cache(f'{self.byte_order}{count_fmt}{count}s')
                self.size = st.size
                return st, count, raw_data

            def pack(self, *values: Any) -> bytes:
                st, count, raw_data = self._packer(values)
                return st.pack(count, raw_data)

            def pack_into(self, buffer: WritableBuffer, offset: int, *values: Any) -> None:
                st, count, raw_data = self._packer(values)
                st.pack_into(buffer, offset, count, raw_data)

            def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
                st, count, raw_data = self._packer(values)
                st.pack_write(writable, count, raw_data)

            def unpack(self, buffer: ReadableBuffer) -> tuple:
                start = self.count_st.size
                count = self.count_st.unpack(buffer[0:start])[0]
                raw_data = buffer[start:start + count]  # type: ignore
                self.size = start + count
                return raw_data,

            def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
                count = self.count_st.unpack_from(buffer, offset)[0]
                size = self.count_st.size
                raw_data = struct_cache(f'{count}s').unpack_from(buffer, offset + size)[0]
                self.size = size + count
                return raw_data,

            def unpack_read(self, readable: SupportsRead) -> tuple:
                count = self.count_st.unpack_read(readable)[0]
                return readable.read(count),
        return _blob

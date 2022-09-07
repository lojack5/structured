"""
Unicode string types, as well as bytes type char.  char is implemented here due
to its potentially Serailizer nature when used with a dynamic size.
"""
__all__ = [
    'EncoderDecoder',
    'unicode', 'char',
    'NET',
]

from functools import cache, partial
import struct

from ..utils import specialized
from ..base_types import (
    Serializer, StructSerializer, requires_indexing, ByteOrder, struct_cache, structured_type, counted,
)
from ..basic_types import uint8, uint16, uint32, uint64
from ..type_checking import (
    ClassVar, ReadableBuffer, SupportsRead, Any, SupportsWrite, WritableBuffer,
    Union, Callable, cast
)


SizeTypes = Union[uint8, uint16, uint32, uint64]
Encoder = Callable[[str], bytes]
Decoder = Callable[[bytes], str]


class NET:
    """Marker class for denoting .NET strings."""


class _char(bytes, counted):
    format: ClassVar[str] = 's'


class char(_char):
    def __class_getitem__(cls, args) -> type[structured_type]:
        if not isinstance(args, tuple):
            args = (args,)
        return cls._create(*args)

    @classmethod
    def _create(cls, count: Union[int, type[SizeTypes], type[NET]]) -> type[structured_type]:
        if isinstance(count, int):
            new_cls = _char[count]
        elif isinstance(count, type) and issubclass(count, SizeTypes):
            new_cls = _dynamic_char[count]
        elif count is NET:
            new_cls = _net_char
        else:
            raise TypeError(f'{cls.__qualname__}[] count must be an int, NET, or uint* type.')
        return specialized(cls, count)(new_cls)


class EncoderDecoder:
    @classmethod
    def encode(cls, strng: str) -> bytes:
        raise NotImplementedError   # pragma: no cover

    @classmethod
    def decode(cls, byts: bytes) -> str:
        raise NotImplementedError   # pragma: no cover


class unicode(str, requires_indexing):
    @classmethod
    @cache
    def __class_getitem__(cls, args) -> type[Serializer]:
        if not isinstance(args, tuple):
            args = (args, )
        return cls.create(*args)

    @classmethod
    def create(cls, count: Union[int, type[SizeTypes], type[NET]], encoding: Union[str, type[EncoderDecoder]] = 'utf8') -> type[Serializer]:
        if isinstance(encoding, str):
            encoder = partial(str.encode, encoding=encoding)
            decoder = partial(bytes.decode, encoding=encoding)
        elif isinstance(encoding, type) and issubclass(encoding, EncoderDecoder):
            encoder = encoding.encode
            decoder = encoding.decode
        else:
            raise TypeError()

        if isinstance(count, int):
            base = _static_char[count]
        elif isinstance(count, type) and issubclass(count, SizeTypes):
            base = _dynamic_char[count]
        elif count is NET:
            base = _net_char
        else:
            raise TypeError()

        new_cls = unicode_wrap(base, encoder, decoder)
        return specialized(cls, count, encoding)(new_cls)



class _static_char(StructSerializer):
    # Need a Serializer based char, so we can unicode wrap it.  Not used for
    # char[int].
    count: ClassVar[int]

    def __init__(self, byte_order: ByteOrder) -> None:
        super().__init__(f'{self.count}s')

    def __class_getitem__(cls: type[StructSerializer], count_val: int) -> type[StructSerializer]:
        class _static(cls):
            count: ClassVar[int] = count_val
        return _static


class _dynamic_char(Serializer):
    count_type: ClassVar[type[SizeTypes]]

    def __init__(self, byte_order: ByteOrder) -> None:
        self.st = struct_cache(self.count_type.format, byte_order=byte_order)
        self.byte_order = byte_order
        self.size = 0

    def _st_count_data(self, values: tuple[Any, ...]) -> tuple[StructSerializer, int, bytes]:
        raw = values[0]
        count = len(raw)
        st = struct_cache(f'{self.count_type.format}{count}s', byte_order=self.byte_order)
        self.size = st.size
        return st, count, raw

    def pack(self, *values: Any) -> bytes:
        st, count, raw = self._st_count_data(values)
        return st.pack(count, raw)

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: Any) -> None:
        st, count, raw = self._st_count_data(values)
        st.pack_into(buffer, offset, count, raw)

    def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
        st, count, raw = self._st_count_data(values)
        st.pack_write(writable, count, raw)

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        count = self.st.unpack(buffer)[0]
        self.size = self.st.size + count
        return buffer[self.st.size:self.size],

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        count = self.st.unpack_from(buffer, offset)[0]
        self.size = self.st.size + count
        st = struct_cache(f'{count}s')
        return st.unpack_from(buffer, offset + self.st.size)

    def unpack_read(self, readable: SupportsRead) -> tuple:
        count = self.st.unpack_read(readable)[0]
        self.size = self.st.size + count
        st = struct_cache(f'{count}s')
        return st.unpack_read(readable)

    def __class_getitem__(cls: type[Serializer], count: type[SizeTypes]) -> type[Serializer]:
        class _dynamic(cls):
            count_type: ClassVar[type[SizeTypes]] = count
        return _dynamic


class _net_char(Serializer):
    def __init__(self, byte_order: ByteOrder) -> None:
        # TODO: Determine if we should add the given ByteOrder, or
        # always use a specific one (need to find some docs *somewhere* on
        # this format, other than old WryeBase code.)
        self.short_len = struct_cache('B', byte_order=byte_order)
        self.long_len = struct_cache('H', byte_order=byte_order)
        self.byte_order = byte_order
        self.size = 0

    def _st_count_data(self, values: tuple[bytes]) -> tuple[StructSerializer, int, bytes]:
        raw = values[0]
        count = len(raw)
        if count < 128:
            st = struct_cache(f'B{count}s', byte_order=self.byte_order)
        elif count > 0x7FFF:
            raise ValueError('.NET string length too long to encode.')
        else:
            st = struct_cache(f'H{count}s', byte_order=self.byte_order)
            count = 0x80 | count & 0x7F | (count & 0xFF80) << 1
        self.size = st.size
        return st, count, raw

    def pack(self, *values: bytes) -> bytes:
        st, count_mark, raw = self._st_count_data(values)
        return st.pack(count_mark, raw)

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: bytes) -> None:
        st, count_mark, raw = self._st_count_data(values)
        st.pack_into(buffer, offset, count_mark, raw)

    def pack_write(self, writable: SupportsWrite, *values: bytes) -> None:
        st, count_mark, raw = self._st_count_data(values)
        writable.write(st.pack(count_mark, raw))

    @staticmethod
    def _decode_length(count: int) -> int:
        count = count & 0x7F | (count >> 1) & 0xFF80
        if count > 0x7FFF:
            raise ValueError('.NET string length too big to encode.')
        return count

    def unpack(self, buffer: ReadableBuffer) -> tuple[bytes]:
        count = self.short_len.unpack(buffer)[0]
        if count >= 128:
            count = self.long_len.unpack(buffer)[0]
            count = self._decode_length(count)
            size = self.long_len.size
        else:
            size = self.short_len.size
        self.size = size + count
        return cast(bytes, buffer[size:size + count]),

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[bytes]:
        count = self.short_len.unpack_from(buffer, offset)[0]
        if count >= 128:
            count = self.long_len.unpack_from(buffer, offset)[0]
            count = self._decode_length(count)
            size = self.long_len.size
        else:
            size = self.short_len.size
        self.size = size + count
        return struct.unpack_from(f'{count}s', buffer, offset + size)

    def unpack_read(self, readable: SupportsRead) -> tuple[bytes]:
        count_pos = readable.tell()     # type: ignore
        count = self.short_len.unpack_read(readable)[0]
        if count >= 128:
            readable.seek(count_pos)    # type: ignore
            count = self.long_len.unpack_read(readable)[0]
            count = self._decode_length(count)
            size = self.long_len.size
        else:
            size = self.short_len.size
        self.size = size + count
        return readable.read(count),


def unicode_wrap(base: type[Serializer], encoder_fn: Encoder, decoder_fn: Decoder) -> type[Serializer]:
    class _unicode(base):
        encoder: ClassVar[Encoder] = encoder_fn
        decoder: ClassVar[Decoder] = decoder_fn

        def pack(self, *values: Any) -> bytes:
            return super().pack(self.encoder(values[0]))

        def pack_into(self, buffer: WritableBuffer, offset: int, *values: str) -> None:
            super().pack_into(buffer, offset, self.encoder(values[0]))

        def pack_write(self, writable: SupportsWrite, *values: str) -> None:
            super().pack_write(writable, self.encoder(values[0]))

        def unpack(self, buffer: ReadableBuffer) -> tuple[str]:
            return self.decoder(super().unpack(buffer)[0]),

        def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[str]:
            return self.decoder(super().unpack_from(buffer, offset)[0]),

        def unpack_read(self, readable: SupportsRead) -> tuple[str]:
            return self.decoder(super().unpack_read(readable)[0]),
    return _unicode

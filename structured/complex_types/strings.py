"""
Unicode string types, as well as bytes type char.  char is implemented here due
to its potentially Serailizer nature when used with a dynamic size.
"""
__all__ = [
    'EncoderDecoder',
    'unicode',
    'char',
    'null_unicode',
    'null_char',
    'NET',
]

import io
import struct
from functools import cache, partial

from ..base_types import (
    ByteOrder,
    Serializer,
    StructSerializer,
    counted,
    requires_indexing,
    struct_cache,
)
from ..basic_types import _uint8, _uint16, _uint32, _uint64, unwrap_annotated
from ..type_checking import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    ReadableBuffer,
    BinaryIO,
    TypeVar,
    Union,
    WritableBuffer,
    cast,
)
from ..utils import StructuredAlias, specialized


_SizeTypes = (_uint8, _uint16, _uint32, _uint64)  # py 3.9 isinstance/subclass
SizeTypes = Union[_uint8, _uint16, _uint32, _uint64]
Encoder = Callable[[str], bytes]
Decoder = Callable[[bytes], str]


class NET:
    """Marker class for denoting .NET strings."""


class _char(bytes, counted):
    format: ClassVar[str] = 's'


class char(_char):
    """A bytestring, with three ways of denoting length. If size is an integer,
    it is a static size.  If a uint* type is specified, it is prefixed with
    a packed value of that type which holds the length.  If the NET type is
    specified, uses the variable (1-2 bytes) .NET string size marker.

        char[3] - statically sized.
        char[uint32] - dynamically sized.
        char[NET] - dynamically sized.

    :param size: The size of the bytestring.
    :type size: Union[int,
                      type[Union[uint8, uint16, uint32, uint64]],
                      type[NET]]
    """

    def __class_getitem__(cls, args) -> type[bytes]:
        """Create a char specialization."""
        if not isinstance(args, tuple):
            args = (args,)
        return cls._create(*map(unwrap_annotated, args))

    @classmethod
    @cache
    def _create(
        cls,
        count: Union[int, type[SizeTypes], type[NET]],
    ) -> type[bytes]:
        if isinstance(count, int):
            new_cls = _char[count]
        elif count in _SizeTypes:
            new_cls = _dynamic_char[count]
        elif count is NET:
            new_cls = _net_char
        elif isinstance(count, TypeVar):
            return StructuredAlias(cls, (count,))  # type: ignore
        elif isinstance(count, bytes):
            new_cls = _terminated_char[count]
        else:
            raise TypeError(
                f'{cls.__qualname__}[] count must be an int, NET, terminator '
                'byte, or uint* type.'
            )
        return Annotated[bytes, new_cls]


class EncoderDecoder:
    """Base class for creating custom encoding/decoding methods for strings.
    Subclass and implement encode for encoding a string to bytes, and decode
    for decoding a string from bytes.
    """

    @classmethod
    def encode(cls, strng: str) -> bytes:
        """Encode `strng`.

        :param strng: String to encode.
        :return: The encoded bytestring.
        """
        raise NotImplementedError  # pragma: no cover

    @classmethod
    def decode(cls, byts: bytes) -> str:
        """Decode `byts`.

        :param byts: The bytestring to decode.
        :return: The decoded string.
        :rtype: str
        """
        raise NotImplementedError  # pragma: no cover


class unicode(str, requires_indexing):
    """A char-like type which is automatically encoded when packing and decoded
    when unpacking.  Arguments are the same as for char, with an additional
    optional argument `encoding`.  If encoding is a string, it is the name of
    a python standard codec to use.  Otherwise, it must be a subclass of
    `EncoderDecoder` to provide the encoding and decoding methods.

    :param size: The size of the *encoded* string.
    :type size: Union[int,
                      Union[type[uint8, uint16, uint32, uint64]],
                      type[NET]]
    :param encoding: Encoding method to use.
    :type encoding: Union[str, type[EncoderDecoder]]
    """

    @classmethod
    def __class_getitem__(cls, args) -> type[str]:
        """Create the specialization."""
        if not isinstance(args, tuple):
            args = (args,)
        # Cache doesn't place nice with default args,
        # _create(uint8)
        # _create(uint8, 'utf8')
        # technically are different call types, so the cache isn't hit.
        # Pass through an intermediary to take care of this.
        return cls.create(*map(unwrap_annotated, args))

    @classmethod
    def create(
        cls,
        count: Union[int, type[SizeTypes], type[NET]],
        encoding: Union[str, type[EncoderDecoder]] = 'utf8',
    ) -> type[str]:
        return cls._create(count, encoding)

    @classmethod
    @cache
    def _create(
        cls,
        count: Union[int, type[SizeTypes], type[NET]],
        encoding: Union[str, type[EncoderDecoder]],
    ) -> type[str]:
        """Create the specialization.

        :param count: Size of the *encoded* string.
        :param encoding: Encoding method to use.
        :return: The specialized class.
        """
        if isinstance(count, TypeVar):
            return StructuredAlias(cls, (count, encoding))  # type: ignore
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
        elif count in _SizeTypes:
            base = _dynamic_char[count]
        elif count is NET:
            base = _net_char
        elif isinstance(count, bytes):
            base = _terminated_char[count]
        else:
            raise TypeError()

        new_cls = unicode_wrap(base, encoder, decoder)
        return Annotated[str, new_cls]


class _static_char(StructSerializer):
    """Serializer for packing/unpacking static length bytestrings.  Provided
    only to be subclassed for static unicode strings.

    :param count: Static size of the bytestring.
    :type count: int
    """

    # Need a Serializer based char, so we can unicode wrap it.  Not used for
    # char[int].
    count: ClassVar[int]

    def __init__(self, byte_order: ByteOrder) -> None:
        """Setup the struct for packing/unpacking."""
        super().__init__(f'{self.count}s')

    def __class_getitem__(
        cls: type[StructSerializer], count_val: int
    ) -> type[StructSerializer]:
        """Create a specialization for a specific static size."""

        class _static(cls):
            count: ClassVar[int] = count_val

        return _static


class _dynamic_char(Serializer):
    """Serializer for packing/unpacking a dynamically sized bytestring.

    :param count_type: The uint* type that holds the bytestring length.
    :type count_type: type[Union[uint8, uint16, uint32, uint64]]
    """

    count_type: ClassVar[type[SizeTypes]]

    def __init__(self, byte_order: ByteOrder) -> None:
        """Setup a size unpacker, initialize size."""
        self.st = struct_cache(self.count_type.format, byte_order=byte_order)
        self.byte_order = byte_order
        self.size = 0

    def _st_count_data(
        self,
        values: tuple[Any, ...],
    ) -> tuple[StructSerializer, int, bytes]:
        """Given data pack as passed in from a Structured object, create a
        struct for packing it and its length.  Returns the struct, length, and
        bytestring to pack.

        :param values: Bytestring as passed from a Structured object.
        :return: The struct instance, length, and bystring.
        """
        raw = values[0]
        count = len(raw)
        fmt = f'{self.count_type.format}{count}s'
        st = struct_cache(fmt, byte_order=self.byte_order)
        self.size = st.size
        return st, count, raw

    def pack(self, *values: Any) -> bytes:
        """Pack a dynamically sized bytestring into bytes."""
        st, count, raw = self._st_count_data(values)
        return st.pack(count, raw)

    def pack_into(
        self,
        buffer: WritableBuffer,
        offset: int,
        *values: Any,
    ) -> None:
        """Pack a dynamically sized bytestring into a buffer supporting the
        Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Location in the buffer to place the size and bytestring
        """
        st, count, raw = self._st_count_data(values)
        st.pack_into(buffer, offset, count, raw)

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        """Pack a dynamically sized bytestring and write it to a file-like
        object.

        :param writable: A writable file-like object.
        """
        st, count, raw = self._st_count_data(values)
        st.pack_write(writable, count, raw)

    def unpack(self, buffer: ReadableBuffer) -> tuple:
        """Unpack a dynamically sized bytestring from a bytes-like object.

        :param buffer: The bytes-like object holding the length and bytestring.
        :return: The unpacked bytestring
        """
        count = self.st.unpack(buffer)[0]
        self.size = self.st.size + count
        return (buffer[self.st.size : self.size],)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple:
        """Unpack a dynamically sized bytestring from a buffer supporting the
        Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Location in the buffer to the length marker of the
            bytestring.
        :return: The unpacked bytestring.
        """
        count = self.st.unpack_from(buffer, offset)[0]
        self.size = self.st.size + count
        st = struct_cache(f'{count}s')
        return st.unpack_from(buffer, offset + self.st.size)

    def unpack_read(self, readable: BinaryIO) -> tuple:
        """Unpack a dynamically sized bytestring from a file-like object.

        :param readable: A readable file-like object.
        :return: The unpacked bytestring.
        """
        count = self.st.unpack_read(readable)[0]
        self.size = self.st.size + count
        st = struct_cache(f'{count}s')
        return st.unpack_read(readable)

    def __class_getitem__(
        cls: type[Serializer],
        count: type[SizeTypes],
    ) -> type[Serializer]:
        """Create a specialization"""

        class _dynamic(cls):
            count_type: ClassVar[type[SizeTypes]] = count

        return _dynamic


class _terminated_char(Serializer):
    """A string whose length is determined by a delimiter."""

    terminator: ClassVar[bytes]
    size: int

    def __init__(self, byte_order: ByteOrder) -> None:
        self.size = 0

    def _st_data(self, values: tuple[bytes]) -> tuple[StructSerializer, bytes]:
        raw = values[0]
        if not raw or raw[-1] != self.terminator:
            raw += self.terminator
        count = len(raw)
        self.size = count
        return struct_cache(f'{count}s'), raw

    def pack(self, *values: bytes) -> bytes:
        st, data = self._st_data(values)
        return st.pack(data)

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: bytes) -> None:
        st, data = self._st_data(values)
        st.pack_into(buffer, offset, data)

    def pack_write(self, writable: BinaryIO, *values: bytes) -> None:
        st, data = self._st_data(values)
        st.pack_write(writable, data)

    def unpack(self, buffer: ReadableBuffer) -> tuple[bytes]:
        end = buffer.find(self.terminator)
        if end == -1:
            raise ValueError('Unterminated string.')
        else:
            self.size = end + 1
            return (bytes(buffer[:end]),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[bytes]:
        size = 0
        term = ord(self.terminator)
        try:
            while buffer[offset + size] != term:
                size += 1
            self.size = size + 1
            return (bytes(buffer[offset : offset + size]),)
        except IndexError:
            raise ValueError(f'Unterminated string.') from None

    def unpack_read(self, readable: BinaryIO) -> tuple[bytes]:
        size = 0
        READ_SIZE = 256
        start_pos = readable.tell()
        with io.BytesIO() as out:
            while chunk := readable.read(READ_SIZE):
                offset = chunk.find(self.terminator)
                if offset == -1:
                    out.write(chunk)
                    size += READ_SIZE
                else:
                    out.write(chunk[:offset])
                    size += offset + 1
                    readable.seek(start_pos + size)
                    break
            else:
                raise ValueError('unterminated string.')
            self.size = size
            return (out.getvalue(),)

    def __class_getitem__(cls, term: bytes) -> type[Serializer]:
        if len(term) != 1:
            raise ValueError('char terminator must be a single byte.')

        class new_cls(_terminated_char):
            terminator: ClassVar[bytes] = term

        return specialized(cls, term)(new_cls)


null_char = Annotated[bytes, char[b'\0']]


class _net_char(Serializer):
    """A .NET string serializer.  Note that the variable sized length encoding
    is dubious.
    """

    def __init__(self, byte_order: ByteOrder) -> None:
        # TODO: Determine if we should add the given ByteOrder, or
        # always use a specific one (need to find some docs *somewhere* on
        # this format, other than old WryeBase code.)
        self.short_len = struct_cache('B', byte_order=byte_order)
        self.long_len = struct_cache('H', byte_order=byte_order)
        self.byte_order = byte_order
        self.size = 0

    def _st_count_data(
        self,
        values: tuple[bytes],
    ) -> tuple[StructSerializer, int, bytes]:
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

    def pack_into(
        self,
        buffer: WritableBuffer,
        offset: int,
        *values: bytes,
    ) -> None:
        st, count_mark, raw = self._st_count_data(values)
        st.pack_into(buffer, offset, count_mark, raw)

    def pack_write(self, writable: BinaryIO, *values: bytes) -> None:
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
        return (cast(bytes, buffer[size : size + count]),)

    def unpack_from(
        self,
        buffer: ReadableBuffer,
        offset: int = 0,
    ) -> tuple[bytes]:
        count = self.short_len.unpack_from(buffer, offset)[0]
        if count >= 128:
            count = self.long_len.unpack_from(buffer, offset)[0]
            count = self._decode_length(count)
            size = self.long_len.size
        else:
            size = self.short_len.size
        self.size = size + count
        return struct.unpack_from(f'{count}s', buffer, offset + size)

    def unpack_read(self, readable: BinaryIO) -> tuple[bytes]:
        count_pos = readable.tell()
        count = self.short_len.unpack_read(readable)[0]
        if count >= 128:
            readable.seek(count_pos)
            count = self.long_len.unpack_read(readable)[0]
            count = self._decode_length(count)
            size = self.long_len.size
        else:
            size = self.short_len.size
        self.size = size + count
        return (readable.read(count),)


def unicode_wrap(
    base: type[Serializer],
    encoder_fn: Encoder,
    decoder_fn: Decoder,
) -> type[Serializer]:
    """Create a unicode specialization.  Extends a char[] serializer class to
    apply encoding/decoding to packing/unpacking.

    :param base: The bytestring Serializer class to base it on.
    :param encoder_fn: A method which takes a string and encodes to bytes.
    :param decoder_fn: A method which takes bytes and decodes to a string.
    :return: The unicode specialization.
    """

    class _unicode(base):
        encoder: ClassVar[Encoder] = encoder_fn
        decoder: ClassVar[Decoder] = decoder_fn

        def pack(self, *values: Any) -> bytes:
            return super().pack(self.encoder(values[0]))

        def pack_into(
            self,
            buffer: WritableBuffer,
            offset: int,
            *values: str,
        ) -> None:
            super().pack_into(buffer, offset, self.encoder(values[0]))

        def pack_write(self, writable: BinaryIO, *values: str) -> None:
            super().pack_write(writable, self.encoder(values[0]))

        def unpack(self, buffer: ReadableBuffer) -> tuple[str]:
            return (self.decoder(super().unpack(buffer)[0]).rstrip('\0'),)

        def unpack_from(
            self,
            buffer: ReadableBuffer,
            offset: int = 0,
        ) -> tuple[str]:
            return (self.decoder(super().unpack_from(buffer, offset)[0]).rstrip('\0'),)

        def unpack_read(self, readable: BinaryIO) -> tuple[str]:
            return (self.decoder(super().unpack_read(readable)[0]).rstrip('\0'),)

    return _unicode


null_unicode = Annotated[str, unicode[b'\0']]

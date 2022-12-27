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

from ..base_types import ByteOrder, requires_indexing
from ..basic_types import _SizeTypes, _TSize, unwrap_annotated
from ..serializers import Serializer, StructSerializer
from ..type_checking import (
    Annotated,
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    ReadableBuffer,
    Self,
    TypeVar,
    Union,
    WritableBuffer,
    cast,
)
from ..utils import StructuredAlias

Encoder = Callable[[str], bytes]
Decoder = Callable[[bytes], str]


class NET:
    """Marker class for denoting .NET strings."""


_single_char = StructSerializer('s')


class char(str, requires_indexing):
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
        return cls._create(*args)

    @classmethod
    @cache
    def _create(
        cls,
        count: Union[int, type[_TSize], type[NET]],
    ) -> type[bytes]:
        if count in _SizeTypes:
            serializer = _dynamic_char(unwrap_annotated(count))
        elif isinstance(count, int):
            serializer = _single_char @ count
        elif count is NET:
            serializer = _net_char()
        elif isinstance(count, TypeVar):
            return StructuredAlias(cls, (count,))  # type: ignore
        elif isinstance(count, bytes):
            serializer = _terminated_char(count)
        else:
            raise TypeError(
                f'{cls.__qualname__}[] count must be an int, NET, terminator '
                'byte, or uint* type.'
            )
        return Annotated[bytes, serializer]


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
        return cls.create(*args)

    @classmethod
    def create(
        cls,
        count: Union[int, type[_TSize], type[NET]],
        encoding: Union[str, type[EncoderDecoder]] = 'utf8',
    ) -> type[str]:
        return cls._create(count, encoding)

    @classmethod
    @cache
    def _create(
        cls,
        count: Union[int, type[_TSize], type[NET]],
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
            raise TypeError('An encoding or an EncoderDecoder must be specified.')

        if count in _SizeTypes:
            serializer = _dynamic_char(unwrap_annotated(count))
        elif isinstance(count, int):
            serializer = _single_char @ count
        elif count is NET:
            serializer = _net_char()
        elif isinstance(count, bytes):
            serializer = _terminated_char(count)
        else:
            raise TypeError('Invalid length argument.')

        return Annotated[str, _unicode(serializer, encoder, decoder)]


class _dynamic_char(Serializer):
    """Serializer for packing/unpacking a dynamically sized bytestring.

    :param count_type: The uint* type that holds the bytestring length.
    :type count_type: type[Union[uint8, uint16, uint32, uint64]]
    """

    num_values: ClassVar[int] = 1

    def __init__(self, count_serializer: StructSerializer) -> None:
        self.st = count_serializer
        self.size = 0

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        return type(self)(self.st.with_byte_order(byte_order))

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
        st = self.st + _single_char @ count
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
        count: int = self.st.unpack_from(buffer, offset)[0]
        self.size = self.st.size + count
        st = _single_char @ count
        return st.unpack_from(buffer, offset + self.st.size)

    def unpack_read(self, readable: BinaryIO) -> tuple:
        """Unpack a dynamically sized bytestring from a file-like object.

        :param readable: A readable file-like object.
        :return: The unpacked bytestring.
        """
        count: int = self.st.unpack_read(readable)[0]
        self.size = self.st.size + count
        st = _single_char @ count
        return st.unpack_read(readable)


class _terminated_char(Serializer):
    """A string whose length is determined by a delimiter."""

    num_values: ClassVar[int] = 1
    size: int

    def __init__(self, terminator: bytes) -> None:
        self.size = 0
        if len(terminator) != 1:
            raise ValueError('string terminator must be a single byte')
        self.terminator = terminator

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        return self

    def _st_data(self, values: tuple[bytes]) -> tuple[StructSerializer, bytes]:
        raw = values[0]
        if not raw or raw[-1] != self.terminator:
            raw += self.terminator
        count = len(raw)
        self.size = count
        return _single_char @ count, raw

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
            raise ValueError('Unterminated string.') from None

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


null_char = Annotated[bytes, char[b'\0']]


class _net_char(Serializer):
    """A .NET string serializer.  Note that the variable sized length encoding
    is dubious.
    """

    num_values: ClassVar[int] = 1

    def __init__(self) -> None:
        # TODO: Determine if we should add the given ByteOrder, or
        # always use a specific one (need to find some docs *somewhere* on
        # this format, other than old WryeBase code.)
        self.short_len = StructSerializer('B')
        self.long_len = StructSerializer('H')
        self.size = 0

    def _st_count_data(
        self,
        values: tuple[bytes],
    ) -> tuple[StructSerializer, int, bytes]:
        raw = values[0]
        count = len(raw)
        if count < 128:
            st = self.short_len + _single_char @ count
        elif count > 0x7FFF:
            raise ValueError('.NET string length too long to encode.')
        else:
            st = self.long_len + _single_char @ count
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


class _unicode(Serializer):
    num_values: ClassVar[int] = 1

    def __init__(
        self, char_serializer: Serializer, encoder: Encoder, decoder: Decoder
    ) -> None:
        self.serializer = char_serializer
        self.encoder = encoder
        self.decoder = decoder

    @property
    def size(self) -> int:
        return self.serializer.size

    def pack(self, *values: str) -> bytes:
        return self.serializer.pack(self.encoder(values[0]))

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: str) -> None:
        self.serializer.pack_into(buffer, offset, self.encoder(values[0]))

    def pack_write(self, writable: BinaryIO, *values: str) -> None:
        self.serializer.pack_write(writable, self.encoder(values[0]))

    def unpack(self, buffer: ReadableBuffer) -> tuple[str]:
        return (self.decoder(self.serializer.unpack(buffer)[0]).rstrip('\0'),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[str]:
        return (
            self.decoder(self.serializer.unpack_from(buffer, offset)[0]).rstrip('\0'),
        )

    def unpack_read(self, readable: BinaryIO) -> tuple[str]:
        return (self.decoder(self.serializer.unpack_read(readable)[0]).rstrip('\0'),)


null_unicode = Annotated[str, unicode[b'\0']]

import io
import struct

__all__ = [
    'TerminatedCharSerializer',
    'DynamicCharSerializer',
    'NETCharSerializer',
    'static_char_serializer',
    'UnicodeSerializer',
    'TCharSerializer',
]

from ..base_types import ByteOrder
from ..type_checking import (
    BinaryIO,
    Callable,
    ClassVar,
    ReadableBuffer,
    Self,
    Union,
    Unpack,
    WritableBuffer,
    cast,
)
from .api import Serializer
from .structs import StructSerializer

_single_char = StructSerializer[bytes]('s')


def static_char_serializer(count: int) -> StructSerializer[bytes]:
    """Create a char serializer for statically sized bytes."""
    return _single_char @ count


class DynamicCharSerializer(Serializer[bytes]):
    """Serializer for handling variable length strings with their size stored
    just prior to the string data.

    :param count_serializer: A StructSerializer unpacking the uint* type holding
        the bytestring length.
    """

    num_values: ClassVar[int] = 1

    def __init__(self, count_serializer: StructSerializer[int]) -> None:
        self.st = count_serializer
        self.size = 0

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        return type(self)(self.st.with_byte_order(byte_order))

    def _st_count_data(
        self,
        values: tuple[bytes],
    ) -> tuple[StructSerializer[int, bytes], int, bytes]:
        """Given data pack as passed in from a Structured object, create a
        struct for packing it and its length.  Returns the struct, length, and
        bytestring to pack.

        :param values: Bytestring as passed from a Structured object.
        :return: The struct instance, length, and bystring.
        """
        raw_data = values[0]
        count = len(raw_data)
        st = self.st + _single_char @ count
        self.size = st.size
        return st, count, raw_data

    def pack(self, *values: Unpack[tuple[bytes]]) -> bytes:
        """Pack a dynamically sized bytestring into bytes."""
        st, count, raw = self._st_count_data(values)
        return st.pack(count, raw)

    def pack_into(
        self,
        buffer: WritableBuffer,
        offset: int,
        *values: Unpack[tuple[bytes]],
    ) -> None:
        """Pack a dynamically sized bytestring into a buffer supporting the
        Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Location in the buffer to place the size and bytestring
        """
        st, count, raw = self._st_count_data(values)
        st.pack_into(buffer, offset, count, raw)

    def pack_write(self, writable: BinaryIO, *values: Unpack[tuple[bytes]]) -> None:
        """Pack a dynamically sized bytestring and write it to a file-like
        object.

        :param writable: A writable file-like object.
        """
        st, count, raw = self._st_count_data(values)
        st.pack_write(writable, count, raw)

    def unpack(self, buffer: ReadableBuffer) -> tuple[bytes]:
        """Unpack a dynamically sized bytestring from a bytes-like object.

        :param buffer: The bytes-like object holding the length and bytestring.
        :return: The unpacked bytestring
        """
        count = self.st.unpack(buffer)[0]
        self.size = self.st.size + count
        return (bytes(buffer[self.st.size : self.size]),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[bytes]:
        """Unpack a dynamically sized bytestring from a buffer supporting the
        Buffer Protocol.

        :param buffer: A buffer supporting the Buffer Protocol.
        :param offset: Location in the buffer to the length marker of the
            bytestring.
        :return: The unpacked bytestring.
        """
        count = self.st.unpack_from(buffer, offset)[0]
        self.size = self.st.size + count
        st = _single_char @ count
        return st.unpack_from(buffer, offset + self.st.size)

    def unpack_read(self, readable: BinaryIO) -> tuple:
        """Unpack a dynamically sized bytestring from a file-like object.

        :param readable: A readable file-like object.
        :return: The unpacked bytestring.
        """
        count = self.st.unpack_read(readable)[0]
        self.size = self.st.size + count
        st = _single_char @ count
        return st.unpack_read(readable)


class TerminatedCharSerializer(Serializer[bytes]):
    """Serializer for handling terminated strings (typically null-terminated)."""

    num_values: ClassVar[int] = 1
    size: int

    def __init__(self, terminator: bytes) -> None:
        self.size = 0
        if len(terminator) != 1:
            raise ValueError('string terminator must be a single byte')
        self.terminator = terminator

    def _st_data(self, values: tuple[bytes]) -> tuple[StructSerializer, bytes]:
        """Common packing logic."""
        raw_data = values[0]
        if not raw_data or raw_data[-1] != self.terminator:
            # Insert terminator if needed
            raw_data += self.terminator
        count = len(raw_data)
        self.size = count
        return _single_char @ count, raw_data

    def pack(self, *values: Unpack[tuple[bytes]]) -> bytes:
        st, data = self._st_data(values)
        return st.pack(data)

    def pack_into(
        self, buffer: WritableBuffer, offset: int, *values: Unpack[tuple[bytes]]
    ) -> None:
        st, data = self._st_data(values)
        st.pack_into(buffer, offset, data)

    def pack_write(self, writable: BinaryIO, *values: Unpack[tuple[bytes]]) -> None:
        st, data = self._st_data(values)
        st.pack_write(writable, data)

    def unpack(self, buffer: ReadableBuffer) -> tuple[bytes]:
        return self.unpack_from(buffer)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[bytes]:
        end = offset
        try:
            while buffer[end] not in (self.terminator, ord(self.terminator)):
                end += 1
        except IndexError:
            raise ValueError('unterminated string.') from None
        self.size = end + 1
        return (bytes(buffer[offset:end]),)

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


class NETCharSerializer(Serializer[bytes]):
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

    def pack(self, *values: Unpack[tuple[bytes]]) -> bytes:
        st, count_mark, raw = self._st_count_data(values)
        return st.pack(count_mark, raw)

    def pack_into(
        self,
        buffer: WritableBuffer,
        offset: int,
        *values: Unpack[tuple[bytes]],
    ) -> None:
        st, count_mark, raw = self._st_count_data(values)
        st.pack_into(buffer, offset, count_mark, raw)

    def pack_write(self, writable: BinaryIO, *values: Unpack[tuple[bytes]]) -> None:
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


Encoder = Callable[[str], bytes]
Decoder = Callable[[bytes], str]
# NOTE: not just Serializer[bytes], because we're implicitly using that these
# serializers return tuple[bytes], not just Iterable[bytes]
TCharSerializer = Union[
    StructSerializer[bytes],
    DynamicCharSerializer,
    NETCharSerializer,
    TerminatedCharSerializer,
]


class UnicodeSerializer(Serializer[str]):
    num_values: ClassVar[int] = 1

    def __init__(
        self, char_serializer: TCharSerializer, encoder: Encoder, decoder: Decoder
    ) -> None:
        self.serializer = char_serializer
        self.encoder = encoder
        self.decoder = decoder

    @property
    def size(self) -> int:
        return self.serializer.size

    def pack(self, *values: Unpack[tuple[str]]) -> bytes:
        return self.serializer.pack(self.encoder(values[0]))

    def pack_into(
        self, buffer: WritableBuffer, offset: int, *values: Unpack[tuple[str]]
    ) -> None:
        self.serializer.pack_into(buffer, offset, self.encoder(values[0]))

    def pack_write(self, writable: BinaryIO, *values: Unpack[tuple[str]]) -> None:
        self.serializer.pack_write(writable, self.encoder(values[0]))

    def unpack(self, buffer: ReadableBuffer) -> tuple[str]:
        return (self.decoder(self.serializer.unpack(buffer)[0]).rstrip('\0'),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[str]:
        return (
            self.decoder(self.serializer.unpack_from(buffer, offset)[0]).rstrip('\0'),
        )

    def unpack_read(self, readable: BinaryIO) -> tuple[str]:
        return (self.decoder(self.serializer.unpack_read(readable)[0]).rstrip('\0'),)

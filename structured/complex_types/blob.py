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
    """A binary blob of bytes, whose size is determined by a format_type stored
    just prior to the blob.  The blob size may also be specified with a static
    integer, however that gives the same result as just using `char`.

    :param count_type: The format_type used to store the blob size.
    :type count_type: type[Union[uint8, uint16, uint32, uint64]]
    """
    @classmethod
    @cache
    def __class_getitem__(
            cls,
            count: type[CountTypes],
        ) -> Union[type[Serializer], type[char]]:
        """Create the blob specialization and validate arguments.

        :param count: The format_type used to store the size of the binary blob.
        :return: The blob specialization.
        """
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
        """Create the blob specialization, with prefixed count stored in a
        `count_type`.

        :param count_type: format_type used to pack/unpack the blob size.
        :return: The blob specialization.
        """
        count_fmt = count_type.format
        class _blob(Serializer):
            def __init__(self, byte_order: ByteOrder) -> None:
                """Setup the blob count packer/unpacker, and serializer size.

                :param byte_order: Byte order to use for packing/unpacking.
                """
                self.byte_order = byte_order.value
                self.count_st = struct_cache(f'{self.byte_order}{count_fmt}')
                self.size = 0

            def _packer(
                    self,
                    values: tuple[bytes],
                ) -> tuple[StructSerializer, int, bytes]:
                """Common implementation for packing.  Creates a
                StructSerializer to pack the values passed in by the Structured
                object.

                :param values: The blob as passed by the Structured object, so:
                    (blob,)
                :return: The StructSerializer for packing, length of the blob,
                    and the blob itself.
                """
                raw_data = values[0]
                count = len(raw_data)
                st = struct_cache(f'{self.byte_order}{count_fmt}{count}s')
                self.size = st.size
                return st, count, raw_data

            def pack(self, *values: Any) -> bytes:
                """Pack the binary blob into bytes.

                :return: The packed blob, prefixed with packed blob length.
                """
                st, count, raw_data = self._packer(values)
                return st.pack(count, raw_data)

            def pack_into(
                    self,
                    buffer: WritableBuffer,
                    offset: int,
                    *values: Any,
                ) -> None:
                """Pack the binary blob into a buffer supporting the Buffer
                Protocol.

                :param buffer: A buffer supporting the Buffer Protocol.
                :param offset: Location in the buffer to place the blob.
                """
                st, count, raw_data = self._packer(values)
                st.pack_into(buffer, offset, count, raw_data)

            def pack_write(self, writable: SupportsWrite, *values: Any) -> None:
                """Pack the binary blob and write it to a file-like object.

                :param writable: A writable file-like object.
                """
                st, count, raw_data = self._packer(values)
                st.pack_write(writable, count, raw_data)

            def unpack(self, buffer: ReadableBuffer) -> tuple:
                """Unpack a binary blob from a buffer.

                :param buffer: A bytes-like object to unpack from.
                :return: The binary blob.
                """
                start = self.count_st.size
                count = self.count_st.unpack(buffer[0:start])[0]
                raw_data = buffer[start:start + count]  # type: ignore
                self.size = start + count
                return raw_data,

            def unpack_from(
                    self,
                    buffer: ReadableBuffer,
                    offset: int = 0,
                ) -> tuple:
                """Unpack a binary blob from a buffer supporint the Buffer
                Protocol.

                :param buffer: A buffer supporting the Buffer Protocol.
                :param offset: Location in the buffer of the blob's size prefix.
                :return: The binary blob.
                """
                count = self.count_st.unpack_from(buffer, offset)[0]
                size = self.count_st.size
                st = struct_cache(f'{count}s')
                raw_data = st.unpack_from(buffer, offset + size)[0]
                self.size = size + count
                return raw_data,

            def unpack_read(self, readable: SupportsRead) -> tuple:
                """Unpack a binary blob from a readable file-like object.

                :param readable: A readable file-like object.
                :return: The binary blob.
                """
                count = self.count_st.unpack_read(readable)[0]
                return readable.read(count),
        return _blob

"""
TupleSerializer, a serializer very similar to a CompoundSerializer, but returns
all of the contained values grouped into a tuple.
"""

__all__ = [
    'TupleSerializer',
]


from ..type_checking import (
    Any,
    BinaryIO,
    ClassVar,
    Generic,
    Iterable,
    Optional,
    ReadableBuffer,
    Ts,
    Unpack,
    WritableBuffer,
)
from .api import NullSerializer, Serializer


class TupleSerializer(Generic[Unpack[Ts]], Serializer[Unpack[Ts]]):
    num_values: ClassVar[int] = 1

    def __init__(self, serializers: Iterable[Serializer]) -> None:
        self.serializer = sum(serializers, NullSerializer())

    def get_final(self) -> Optional[Serializer]:
        return self.serializer.get_final()

    @property
    def size(self) -> int:
        return self.serializer.size

    def prepack(self, partial_object: Any) -> Serializer:
        self._partial_obj = partial_object
        return self

    def pack(self, values: tuple[Unpack[Ts]]) -> bytes:
        return self.serializer.prepack(self._partial_obj).pack(*values)

    def pack_into(
        self, buffer: WritableBuffer, offset: int, values: tuple[Unpack[Ts]]
    ) -> None:
        self.serializer.prepack(self._partial_obj).pack_into(buffer, offset, *values)

    def pack_write(self, writable: BinaryIO, values: tuple[Unpack[Ts]]) -> None:
        self.serializer.prepack(self._partial_obj).pack_write(writable, *values)

    def preunpack(self, partial_object: Any) -> Serializer:
        self._partial_obj = partial_object
        return self

    def unpack(self, buffer: ReadableBuffer) -> tuple[Iterable[Any]]:
        return (self.serializer.preunpack(self._partial_obj).unpack(buffer),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int) -> tuple[Iterable[Any]]:
        return (
            self.serializer.preunpack(self._partial_obj).unpack_from(buffer, offset),
        )

    def unpack_read(self, readable: BinaryIO) -> tuple[Iterable[Any]]:
        return (self.serializer.preunpack(self._partial_obj).unpack_read(readable),)

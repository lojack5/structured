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

    @property
    def size(self) -> int:
        return self.serializer.size

    def preprocess(self, target: Any) -> None:
        self.serializer.preprocess(target)

    def pack(self, values: tuple[Unpack[Ts]]) -> bytes:
        return self.serializer.pack(*values)

    def pack_into(
        self, buffer: WritableBuffer, offset: int, values: tuple[Unpack[Ts]]
    ) -> None:
        self.serializer.pack_into(buffer, offset, *values)

    def pack_write(self, writable: BinaryIO, values: tuple[Unpack[Ts]]) -> None:
        self.serializer.pack_write(writable, *values)

    def preunpack(self, partial_object: Any) -> Serializer:
        self._partial_obj = partial_object
        return self

    def unpack(self, buffer: ReadableBuffer) -> tuple[Iterable[Any]]:
        return (self.serializer.unpack(buffer),)

    def unpack_from(self, buffer: ReadableBuffer, offset: int) -> tuple[Iterable[Any]]:
        return (
            self.serializer.unpack_from(buffer, offset),
        )

    def unpack_read(self, readable: BinaryIO) -> tuple[Iterable[Any]]:
        return (self.serializer.unpack_read(readable),)

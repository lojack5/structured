__all__ = [
    'StructuredSerializer',
]

from ..type_checking import (
    TYPE_CHECKING,
    BinaryIO,
    ClassVar,
    Generic,
    ReadableBuffer,
    TypeVar,
    WritableBuffer,
)
from .api import Serializer

if TYPE_CHECKING:
    from ..structured import Structured

    TStructured = TypeVar('TStructured', bound=Structured)
else:
    TStructured = TypeVar('TStructured')


class StructuredSerializer(Generic[TStructured], Serializer[TStructured]):
    """Serializer which unpacks a Structured-derived instance."""

    num_values: ClassVar[int] = 1
    obj_type: type[TStructured]

    def __init__(self, obj_type: type[TStructured]) -> None:
        self.obj_type = obj_type

    @property
    def size(self) -> int:
        return self.obj_type.serializer.size

    def pack(self, values: TStructured) -> bytes:
        return values.pack()

    def pack_into(
        self, buffer: WritableBuffer, offset: int, values: TStructured
    ) -> None:
        values.pack_into(buffer, offset)

    def pack_write(self, writable: BinaryIO, values: TStructured) -> None:
        values.pack_write(writable)

    def unpack(self, buffer: ReadableBuffer) -> tuple[TStructured]:
        return (self.obj_type.create_unpack(buffer),)

    def unpack_from(
        self, buffer: ReadableBuffer, offset: int = 0
    ) -> tuple[TStructured]:
        return (self.obj_type.create_unpack_from(buffer, offset),)

    def unpack_read(self, readable: BinaryIO) -> tuple[TStructured]:
        return (self.obj_type.create_unpack_read(readable),)

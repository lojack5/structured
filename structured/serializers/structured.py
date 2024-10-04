"""
Serializer for packing/unpacking a Structured-derived object.
"""

__all__ = [
    'StructuredSerializer',
]

from ..type_checking import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    ClassVar,
    Generic,
    ReadableBuffer,
    TypeVar,
    WritableBuffer,
    annotated,
    get_args,
    get_origin,
    safe_issubclass,
)
from ..utils import StructuredAlias
from .api import Serializer

if TYPE_CHECKING:
    # *Only* used for type-hinting, so ok to guard with a TYPE_CHECKING
    from ..structured import Structured

    TStructured = TypeVar('TStructured', bound=Structured)
else:
    TStructured = TypeVar('TStructured')


class StructuredSerializer(Generic[TStructured], Serializer[TStructured]):
    """Serializer which unpacks a Structured-derived instance."""

    _specializations: ClassVar[dict] = {}

    num_values: ClassVar[int] = 1
    obj_type: type[TStructured]

    def __init__(self, obj_type: type[TStructured]) -> None:
        self.obj_type = obj_type
        self.size = 0

    def pack(self, values: TStructured) -> bytes:
        data = values.pack()
        self.size = values.serializer.size
        return data

    def pack_into(
        self, buffer: WritableBuffer, offset: int, values: TStructured
    ) -> None:
        values.pack_into(buffer, offset)
        self.size = values.serializer.size

    def pack_write(self, writable: BinaryIO, values: TStructured) -> None:
        values.pack_write(writable)
        self.size = values.serializer.size

    def unpack(self, buffer: ReadableBuffer) -> tuple[TStructured]:
        value = self.obj_type.create_unpack(buffer)
        self.size = self.obj_type.serializer.size
        return (value,)

    def unpack_from(
        self, buffer: ReadableBuffer, offset: int = 0
    ) -> tuple[TStructured]:
        value = self.obj_type.create_unpack_from(buffer, offset)
        self.size = self.obj_type.serializer.size
        return (value,)

    def unpack_read(self, readable: BinaryIO) -> tuple[TStructured]:
        value = self.obj_type.create_unpack_read(readable)
        self.size = self.obj_type.serializer.size
        return (value,)

    @classmethod
    def _transform(cls, base_type: Any, hint: Any) -> Any:
        from ..structured import Structured

        if safe_issubclass(base_type, Structured):
            return StructuredSerializer(base_type)
        elif safe_issubclass((origin := get_origin(base_type)), Structured):
            spec_args = get_args(base_type)
            key = (origin, spec_args)
            if all(not isinstance(arg, TypeVar) for arg in spec_args):
                # Fully specialized, first try the cache
                try:
                    return cls._specializations[key]
                except KeyError:
                    pass

                class _Specialized(base_type):
                    pass

                serializer = StructuredSerializer(_Specialized)
                cls._specializations[key] = StructuredSerializer(_Specialized)
                return serializer
            else:
                # Not fully specialized, return a StructuredAlias so it
                # can potentially be fully speciailized by a further
                # subclassing of the containing class.
                return StructuredAlias(base_type, spec_args)


annotated.register_transform(StructuredSerializer._transform)

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

    @classmethod
    def _transform(cls, unwrapped: Any, actual: Any) -> Any:
        from ..structured import Structured

        for x in (actual, unwrapped):
            if safe_issubclass(x, Structured):
                return StructuredSerializer(x)
            elif safe_issubclass((origin := get_origin(x)), Structured):
                spec_args = get_args(x)
                key = (origin, spec_args)
                if all(not isinstance(arg, TypeVar) for arg in spec_args):
                    # Fully specialized, first try the cache
                    try:
                        return cls._specializations[key]
                    except KeyError:
                        pass

                    class _Specialized(x):
                        pass

                    serializer = StructuredSerializer(_Specialized)
                    cls._specializations[key] = StructuredSerializer(_Specialized)
                    return serializer
                else:
                    # Not fully specialized, return a StructuredAlias so it
                    # can potentially be fully speciailized by a further
                    # subclassing of the containing class.
                    return StructuredAlias(x, spec_args)


annotated.register_transform(StructuredSerializer._transform)

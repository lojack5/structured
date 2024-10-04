"""
Serializer for special handling of the typing.Self typehint.
"""

__all__ = [
    'SelfSerializer',
]


from ..type_checking import TYPE_CHECKING, Any, ClassVar, Self, annotated
from .api import Serializer
from .structured import StructuredSerializer

if TYPE_CHECKING:
    from ..structured import Structured, _Proxy
else:
    Structured = 'Structured'
    _Proxy = '_Proxy'


class SelfSerializer(Serializer[Structured]):
    num_values: ClassVar[int] = 1

    def prepack(self, partial_object: Structured) -> Serializer:
        return StructuredSerializer(type(partial_object))

    def preunpack(self, partial_object: _Proxy) -> Serializer:
        return StructuredSerializer(partial_object.cls)

    @classmethod
    def _transform(cls, base_type: Any, hint: Any) -> Any:
        if base_type is Self:
            return cls()


annotated.register_transform(SelfSerializer._transform)

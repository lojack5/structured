"""
Class to use with Annotated to specify a custom type for serialization.
"""

from __future__ import annotations

__all__ = [
    'Condition',
]

from ..serializers import ConditionalSerializer, Serializer
from ..type_checking import Any, Callable, Generic, S, annotated, Unpack, Ts, TYPE_CHECKING, TypeVar


if TYPE_CHECKING:
    from ..structured import Structured
    TStructured = TypeVar('TStructured', bound=Structured)
else:
    TStructured = 'Structured'


class Condition(Generic[S, Unpack[Ts]]):
    def __init__(self, condition: Callable[[TStructured], bool], *defaults: tuple[Unpack[Ts]]) -> None:
        self.condition = condition
        self.defaults = defaults

    @staticmethod
    def _transform(base_type: Any, hint: Any) -> Any:
        if isinstance(hint, Condition):
            if not isinstance(base_type, Serializer):
                raise TypeError('Condition must be paired with a serialized type.')
            return ConditionalSerializer(base_type, hint.condition, hint.defaults)
        
annotated.register_transform(Condition._transform)

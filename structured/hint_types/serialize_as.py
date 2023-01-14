"""
Class to use with Annotated to specify a custom type for serialization.
"""
from __future__ import annotations

__all__ = [
    'SerializeAs',
]

from ..serializers import StructActionSerializer, StructSerializer
from ..type_checking import Any, Callable, Generic, S, Self, T, annotated


class SerializeAs(Generic[S, T]):
    __slots__ = ('serializer',)
    serializer: StructSerializer

    def __init__(self, hint: S) -> None:
        extracter = annotated(StructSerializer)
        serializer = extracter.extract(hint)
        if not serializer:
            raise TypeError(f'SerializeAs requires a basic type, got {hint}')
        elif serializer.num_values != 1:
            raise TypeError(
                f'SerializeAs requires a basic type with one value, got {serializer}'
            )
        self.serializer = serializer

    def with_factory(self, action: Callable[[S], T]) -> Self:
        """Specify a factory method for creating your type from the unpacked type."""
        st = self.serializer
        return type(self)(StructActionSerializer(st.format, actions=(action,)))

    @staticmethod
    def _transform(unwrapped: Any, actual: Any) -> Any:
        if isinstance(unwrapped, SerializeAs):
            st = unwrapped.serializer
            if isinstance(st, StructActionSerializer):
                return st
            else:
                return StructActionSerializer(st.format, actions=(actual,))


annotated.register_transform(SerializeAs._transform)

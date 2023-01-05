"""
All of the basic format types that map directly to struct format specifiers.
"""
from __future__ import annotations

__all__ = [
    'SerializeAs',
]

from .serializers import Serializer, StructActionSerializer, StructSerializer
from .type_checking import (
    Annotated,
    Any,
    Callable,
    Generic,
    S,
    Self,
    T,
    get_args,
    get_origin,
    annotated
)
from .utils import StructuredAlias


def __unwrap_annotated(x: Any) -> Any:
    """We use typing.Annotated to provide serialization details.  These can
    show up in a few ways:
    - Annotated[python_type, Serializer]: Happens when hinting with int8, etc
    - Annotated[python_type, Annotated[python_type, Serializer]:  happens if
    - Annotated[user_type, SerializedAs[StructSerializer]]
    - Annotated[user_type, SerializedAs[StructuredAlias]]
    And in all other cases:
    - Annotated[some_type, other_info, ...]

    In the cases we care about, we want the Serializer or StructuredAlias
    instance for generating Structured.serializer, and in the case of
    SerializedAs, we want to convert that to a StructActionSerializer as well.
    In the cases we don't care about, we just want to return the underlying
    actual type (what get_type_hints would return with include_extras=False).
    """
    if get_origin(x) is Annotated:
        # Annotated raises an error if specialized with no args, so no need to
        # test if len(args) > 0
        args = get_args(x)
        actual_type, extras = args[0], args[1:]
        for extra in extras:
            # Look for nested Annotated
            nested_extra = __unwrap_annotated(extra)
            if isinstance(nested_extra, (Serializer, StructuredAlias)):
                return nested_extra
            elif isinstance(nested_extra, SerializeAs):
                st = nested_extra.serializer
                if isinstance(st, StructActionSerializer):
                    # If built with a StructActionSerializer, just use that
                    # (to support custom factory methods)
                    return st
                else:
                    # Otherwise assume the type's __init__ accepts a single
                    # initialization variable
                    return StructActionSerializer(st.format, actions=(actual_type,))
        # Annotated, but no special extra we're looking for
        return actual_type
    # Not Annotated, or bare Annotated
    return x


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
    def _transform(unwrapped, actual, cls, name):
        if isinstance(unwrapped, SerializeAs):
            st = unwrapped.serializer
            if isinstance(st, StructActionSerializer):
                return st
            else:
                return StructActionSerializer(st.format, actions=(actual, ))
        return unwrapped

annotated.register_transform(SerializeAs._transform)

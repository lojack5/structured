"""
All of the basic format types that map directly to struct format specifiers.
"""
from __future__ import annotations

__all__ = [
    'pad',
    'bool8',
    'int8',
    'uint8',
    'int16',
    'uint16',
    'int32',
    'uint32',
    'int64',
    'uint64',
    'float16',
    'float32',
    'float64',
    'pascal',
    'SerializeAs',
]

from itertools import chain

from .base_types import requires_indexing
from .serializers import Serializer, StructActionSerializer, StructSerializer
from .type_checking import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    Generic,
    S,
    Self,
    T,
    TypeVar,
    get_args,
    get_origin,
)
from .utils import StructuredAlias

bool8 = Annotated[int, StructSerializer('?')]
int8 = Annotated[int, StructSerializer('b')]
uint8 = Annotated[int, StructSerializer('B')]
int16 = Annotated[int, StructSerializer('h')]
uint16 = Annotated[int, StructSerializer('H')]
int32 = Annotated[int, StructSerializer('i')]
uint32 = Annotated[int, StructSerializer('I')]
int64 = Annotated[int, StructSerializer('q')]
uint64 = Annotated[int, StructSerializer('Q')]
float16 = Annotated[float, StructSerializer('e')]
float32 = Annotated[float, StructSerializer('f')]
float64 = Annotated[float, StructSerializer('d')]


class counted(requires_indexing):
    """Base class for simple StructSerializers which have a count argument
    before the format specifier.  For example `char[10]` and `pad[13]`.
    """

    serializer: ClassVar[StructSerializer]
    value_type: ClassVar[type]

    def __class_getitem__(cls, count: int) -> Annotated:
        # Use matrix multiplication operator, to fold in strings,
        # ie 's' @ 2 -> '2s', whereas 's' * 2 -> 'ss'
        return Annotated[cls.value_type, cls.serializer @ count]  # type: ignore


class pad(counted):
    """Represents one (or more, via pad[x]) padding bytes in the format string.
    Padding bytes are discarded when read, and are written zeroed out.
    """

    serializer = StructSerializer('x', 0)
    value_type = type(None)


def ispad(annotation: Any) -> bool:
    """Detect pad[x] generated StructSerializers."""
    unwrapped = unwrap_annotated(annotation)
    if isinstance(unwrapped, StructSerializer) and unwrapped.num_values == 0:
        return True
    return False


class pascal(str, counted):
    """String format specifier (bytes in Python).  See 'p' in the stdlib struct
    documentation for specific details.
    """

    serializer = StructSerializer('p')
    value_type = str


_AnnotatedTypes = (
    bool8,
    int8,
    uint8,
    int16,
    uint16,
    int32,
    uint32,
    int64,
    uint64,
    float16,
    float32,
    float64,
)
_UnAnnotatedTypes = (
    pad,
    pascal,
)
_AllTypes = tuple(chain(_AnnotatedTypes, _UnAnnotatedTypes))
_TSize = TypeVar('_TSize', uint8, uint16, uint32, uint64)
_TSize2 = TypeVar('_TSize2', uint8, uint16, uint32, uint64)
_SizeTypes = (uint8, uint16, uint32, uint64)


def unwrap_annotated(x: Any) -> Any:
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
            nested_extra = unwrap_annotated(extra)
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
        serializer = unwrap_annotated(hint)
        if not isinstance(serializer, StructSerializer):
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

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
    'Formatted',
]

from functools import cache
from itertools import chain

from .base_types import requires_indexing
from .serializers import Serializer, StructActionSerializer, StructSerializer, counted
from .type_checking import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    Container,
    Self,
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


class pad(counted):
    """Represents one (or more, via pad[x]) padding bytes in the format string.
    Padding bytes are discarded when read, and are written zeroed out.
    """

    serializer = StructSerializer('x', 0)
    value_type = type(None)


def ispad(annotation: Any) -> bool:
    unwrapped = unwrap_annotated(annotation)
    # Un-indexed
    if isinstance(unwrapped, type) and unwrapped is pad:
        return True
    # Indexed
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
    """Recursively unwrap an Annotated type annotation, searching for one of:
    - A format_type class
    - A Serializer class
    - A StructuredAlias instance
    If none are found, returns the Annotated type (ie: in Annotated[int, ...],
    returns int).  If the annotation isn't an Annotated, returns the original
    annotation.

    :param x: Type annotation to unwrap.
    :return: The (possibly unwrapped) final annotation.
    """
    if get_origin(x) is Annotated:
        if args := get_args(x):
            for meta in args[1:]:
                # Annotated can be nested, ex:
                # b: Annotated[int, int8]
                meta = unwrap_annotated(meta)
                if isinstance(meta, type):
                    if issubclass(meta, Serializer):
                        return meta
                elif isinstance(meta, (StructuredAlias, Serializer)):
                    return meta
            else:
                # Annotated, but not one of the special types we're looking for
                return args[0]
    # Not Annotated
    return x


# NOTE: This typehint isn't working how I want.  The issue is stemming from
# using Annotated instances, and wanting the type to be one of those, or a
# subclass of format_type.  Look into if this is even possible with hints.
#
# TTypes = Union[
#    # Can be exactly one of the Annotated types
#    bool8, int8, uint8, int16, uint16, int32, uint32, int64, uint64, float16,
#    float32, float64,
#    # Or any format_type
#    format_type,
# ]


class Formatted(requires_indexing):
    """Class used for creating new `format_type`s.  Provides a class getitem
    to select the format specifier, by grabbing from one of the provided format
    types.  The allowed types may be overridden by overriding cls._types.

    For examples of how to use this, see `TestFormatted`.
    """

    _types: ClassVar[Container] = frozenset()  # Container[TType]?
    unpack_action: ClassVar[Callable[[Any], Any]]

    @classmethod  # Need to remark as classmethod since we're caching
    @cache
    def __class_getitem__(cls, key: StructSerializer) -> type[Self]:
        """Create an version of this class which uses the given types format
        specifier for packing/unpacking.

        :param key: A format type this type encapsulates (int*, uint*, etc)
        :raises TypeError: If an invalid type is passed, or if the type is not
            included in this class's `_types` container.
        :return: An Annotated with the specialied information.
        """
        unwrapped = unwrap_annotated(key)
        # Error checking
        if not isinstance(unwrapped, StructSerializer) or unwrapped.num_values != 1:
            raise TypeError(f'Formatted key must be a format_type, got {key!r}.')
        if cls._types is Formatted._types:
            # Default, just allow any format type
            pass
        else:
            # Overridden _types, get from that set
            # NOTE: users may do _types = {int8, ...}
            # So we need to check both the actual key and it's unwrapped
            # version
            if key not in cls._types and unwrapped not in cls._types:
                raise TypeError(
                    'Formatted key must be one of the allowed types of '
                    f'{cls.__qualname__}.'
                )
        action = getattr(cls, 'unpack_action', cls)
        return Annotated[
            cls, StructActionSerializer(unwrapped.format, actions=(action,))
        ]

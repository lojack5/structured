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

from .base_types import Serializer, counted, format_type, noop_action
from .type_checking import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    Container,
    get_args,
    get_origin,
)
from .utils import StructuredAlias, specialized


class pad(counted):
    """Represents one (or more, via pad[x]) padding bytes in the format string.
    Padding bytes are discarded when read, and are written zeroed out.
    """

    format: ClassVar[str] = 'x'


class _bool8(format_type):
    """bool struct type, stored as an integer: '?'."""

    format: ClassVar[str] = '?'


bool8 = Annotated[int, _bool8]


class _int8(format_type):
    """8-bit signed integer: 'b'."""

    format: ClassVar[str] = 'b'


int8 = Annotated[int, _int8]


class _uint8(format_type):
    """8-bit unsigned integer: 'B'."""

    format: ClassVar[str] = 'B'


uint8 = Annotated[int, _uint8]


class _int16(format_type):
    """16-bit signed integer: 'h'."""

    format: ClassVar[str] = 'h'


int16 = Annotated[int, _int16]


class _uint16(format_type):
    """16-bit unsigned integer: 'H'."""

    format: ClassVar[str] = 'H'


uint16 = Annotated[int, _uint16]


class _int32(format_type):
    """32-bit signed integer."""

    format: ClassVar[str] = 'i'


int32 = Annotated[int, _int32]


class _uint32(format_type):
    """32-bit unsigned integer: 'I'."""

    format: ClassVar[str] = 'I'


uint32 = Annotated[int, _uint32]


class _int64(format_type):
    """64-bit signed integer: 'q'."""

    format: ClassVar[str] = 'q'


int64 = Annotated[int, _int64]


class _uint64(format_type):
    """64-bit unsigned integer: 'Q'."""

    format: ClassVar[str] = 'Q'


uint64 = Annotated[int, _uint64]


class _float16(format_type):
    """IEEE 754 16-bit half-precision floating point number."""

    format: ClassVar[str] = 'e'


float16 = Annotated[float, _float16]


class _float32(format_type):
    """IEEE 754 32-bit floating point number."""

    format: ClassVar[str] = 'f'


float32 = Annotated[float, _float32]


class _float64(format_type):
    """IEEE 754 64-bit double-precision floating point number."""

    format: ClassVar[str] = 'd'


float64 = Annotated[float, _float64]


# NOTE: char moved to complex_types/unicode.py, since it can optionally
# be created with a dynamic size.


class pascal(str, counted):
    """String format specifier (bytes in Python).  See 'p' in the stdlib struct
    documentation for specific details.
    """

    format: ClassVar[str] = 'p'


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
                    if issubclass(meta, (format_type, Serializer)):
                        return meta
                elif isinstance(meta, StructuredAlias):
                    return meta
            else:
                # Annotated, but not one of the special types we're looking for
                return args[0]
    # Not Annotated
    return x


## NOTE: This typehint isn't working how I want.  The issue is stemming from
## using Annotated instances, and wanting the type to be one of those, or a
## subclass of format_type.  Look into if this is even possible with hints.
# TTypes = Union[
#    # Can be exactly one of the Annotated types
#    bool8, int8, uint8, int16, uint16, int32, uint32, int64, uint64, float16,
#    float32, float64,
#    # Or any format_type
#    format_type,
# ]
class Formatted(format_type):
    """Class used for creating new `format_type`s.  Provides a class getitem
    to select the format specifier, by grabbing from one of the provided format
    types.  The allowed types may be overridden by overriding cls._types.

    For examples of how to use this, see `TestFormatted`.
    """

    _types: ClassVar[Container] = frozenset()  # Container[TType]?

    @classmethod  # Need to remark as classmethod since we're caching
    @cache
    def __class_getitem__(
        cls: type[Formatted],
        key: type[format_type],
    ) -> type[Formatted]:
        """Create an version of this class which uses the given types format
        specifier for packing/unpacking.

        :param key: A format type this type encapsulates (int*, uint*, etc)
        :raises TypeError: If an invalid type is passed, or if the type is not
            included in this class's `_types` container.
        :return: An Annotated with the specialied information.
        """
        unwrapped = unwrap_annotated(key)
        # Error checking
        if not issubclass(unwrapped, format_type):
            raise TypeError(f'Formatted key must be a format_type, got {key!r}.')
        if cls._types is Formatted._types:
            # Default, just allow any format type
            fmt = unwrapped.format
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
            fmt = unwrapped.format
        action = getattr(cls, 'unpack_action', noop_action)
        # Create the subclass
        @specialized(cls, key)
        class _Formatted(cls):
            format: ClassVar[str] = fmt
            unpack_action: ClassVar[Callable[[Any], Formatted]]

        action = action if action is not noop_action else _Formatted
        _Formatted.unpack_action = action
        return _Formatted

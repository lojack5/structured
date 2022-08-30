"""
All of the basic format types that map directly to struct format specifiers.
"""
from __future__ import annotations


__all__ = [
    'pad', 'bool8',
    'int8', 'uint8',
    'int16', 'uint16',
    'int32', 'uint32',
    'int64', 'uint64',
    'float16', 'float32', 'float64',
    'char', 'pascal',
    'Formatted',
]


from functools import cache

from .base_types import format_type, counted, noop_action
from .utils import specialized
from .type_checking import ClassVar, Callable, Any


class pad(counted):
    """Represents one (or more, via pad[x]) padding bytes in the format string.
    Padding bytes are discarded when read, and are written zeroed out.
    """
    format: ClassVar[str] = 'x'


class bool8(int, format_type):
    """bool struct type, stored as an integer."""
    format: ClassVar[str] = '?'


class int8(int, format_type):
    """8-bit signed integer."""
    format: ClassVar[str] = 'b'


class uint8(int, format_type):
    """8-bit unsigned integer."""
    format: ClassVar[str] = 'B'


class int16(int, format_type):
    """16-bit signed integer."""
    format: ClassVar[str] = 'h'


class uint16(int, format_type):
    """16-bit unsigned integer."""
    format: ClassVar[str] = 'H'


class int32(int, format_type):
    """32-bit signed integer."""
    format: ClassVar[str] = 'i'


class uint32(int, format_type):
    """32-bit unsigned integer."""
    format: ClassVar[str] = 'I'


class int64(int, format_type):
    """64-bit signed integer."""
    format: ClassVar[str] = 'q'


class uint64(int, format_type):
    """64-bit unsigned integer."""
    format: ClassVar[str] = 'Q'


class float16(float, format_type):
    """IEEE 754 16-bit half-precision floating point number."""
    format: ClassVar[str] = 'e'


class float32(float, format_type):
    """IEEE 754 32-bit floating point number."""
    format: ClassVar[str] = 'f'


class float64(float, format_type):
    """IEEE 754 64-bit double-precision floating point number."""
    format: ClassVar[str] = 'd'


class char(str, counted):
    """String format specifier (bytes in Python).  See 's' in the stdlib struct
    documentation for specific details.
    """
    format: ClassVar[str] = 's'


class pascal(str, counted):
    """String format specifier (bytes in Python).  See 'p' in the stdlib struct
    documentation for specific details.
    """
    format: ClassVar[str] = 'p'



class Formatted(format_type):
    """Class used for creating new `format_type`s.  Provides a class getitem
    to select the format specifier, by grabbing from one of the provided format
    types.  The allowed types may be overridden by overriding cls._types.

    For examples of how to use this, see `TestFormatted`.
    """
    _types: ClassVar[frozenset[type[format_type]]] = frozenset()

    @classmethod    # Need to remark as classmethod since we're caching
    @cache
    def __class_getitem__(
            cls: type[Formatted],
            key: type[format_type],
        ) -> type[Formatted]:
        # Error checking
        if not issubclass(key, format_type):
            raise TypeError(f'Formatted key must be a format_type, got {key!r}.')
        if cls._types is Formatted._types:
            # Default, just allow any format type
            fmt = key.format
        else:
            # Overridden _types, get from that set
            if key not in cls._types:
                raise TypeError(
                    'Formatted key must be one of the allowed types of '
                    f'{cls.__qualname__}.'
                )
            fmt = key.format
        action = getattr(cls, 'unpack_action', noop_action)
        # Create the subclass
        @specialized(cls, key)
        class _Formatted(cls):
            format: ClassVar[str] = fmt
            unpack_action: ClassVar[Callable[[Any], Formatted]]
        action = action if action is not noop_action else _Formatted
        _Formatted.unpack_action = action
        return _Formatted

"""
Base types for all types that are handled by the Structured class.
"""
from __future__ import annotations

from .utils import specialized
from .type_checking import ClassVar, Callable, Any, _T


def noop_action(x: _T) -> _T:
    return x


class structured_type:
    """Base class for all types packed/unpacked by the Structured class."""


class format_type(structured_type):
    """Base class for all types that directly correlate with a single struct
    format specifier.  The format specifier used is the class variable `format`,
    and any follow on processing can be done with the class variable
    `unpack_action`.  For packing, the applicable `__index__` or `__float__`
    method should be implemented, if not already handled by a base class.

    Types which derived from `format_type` have the advantage of being able to
    pack/unpack as one block of variables, rather than handling one at a time.
    """
    format: ClassVar[str] = ''
    unpack_action: Callable[[Any], Any] = noop_action


class counted(format_type):
    """Base class for `format_type`s that often come in continuous blocks of a
    fixed number of instances.  The examples are char and pad characters.
    """
    def __class_getitem__(cls: type[counted], count: int) -> type[counted]:
        # Error checking
        if not isinstance(count, int):
            raise TypeError('count must be an integer.')
        elif count <= 0:
            raise ValueError('count must be positive.')
        # Create the specialization
        @specialized(cls, count)
        class _counted(cls):
            format: ClassVar[str] = f'{count}{cls.format}'
        return _counted


class complex_type(structured_type):
    """Base class for all types which require more logic for packing and
    unpacking.

    TODO: Flesh this out.
    """

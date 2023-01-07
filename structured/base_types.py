__all__ = [
    'ByteOrder',
    'ByteOrderMode',
]

from enum import Enum

from .type_checking import Any, annotated, safe_issubclass


class ByteOrder(str, Enum):
    """Byte order specifiers for passing to the struct module.  See the stdlib
    documentation for details on what each means.
    """

    DEFAULT = ''
    LITTLE_ENDIAN = '<'
    LE = LITTLE_ENDIAN
    BIG_ENDIAN = '>'
    BE = BIG_ENDIAN
    NATIVE_STANDARD = '='
    NATIVE_NATIVE = '@'
    NETWORK = '!'


class ByteOrderMode(str, Enum):
    """How derived classes with conflicting byte order markings should function."""

    OVERRIDE = 'override'
    STRICT = 'strict'


class requires_indexing:
    """Marker base class to indicate a class must be indexed in order to get a
    true Serializer.
    """

    @staticmethod
    def _transform(unwrapped: Any, actual: Any) -> Any:
        for a in (unwrapped, actual):
            if safe_issubclass(unwrapped, requires_indexing):
                raise TypeError(f'{a.__name__} must be indexed.')
        return unwrapped


annotated.register_transform(requires_indexing._transform)

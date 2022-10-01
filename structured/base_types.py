__all__ = [
    'ByteOrder',
    'ByteOrderMode',
]

from enum import Enum


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

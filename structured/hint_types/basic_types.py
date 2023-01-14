"""
Basic typhints for types with direct struct serialization.
"""

__all__ = [
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
    'pad',
    'pascal',
]

from ..base_types import requires_indexing
from ..serializers import StructSerializer
from ..type_checking import Annotated, ClassVar, TypeVar

bool8 = Annotated[bool, StructSerializer[bool]('?')]
int8 = Annotated[int, StructSerializer[int]('b')]
uint8 = Annotated[int, StructSerializer[int]('B')]
int16 = Annotated[int, StructSerializer[int]('h')]
uint16 = Annotated[int, StructSerializer[int]('H')]
int32 = Annotated[int, StructSerializer[int]('i')]
uint32 = Annotated[int, StructSerializer[int]('I')]
int64 = Annotated[int, StructSerializer[int]('q')]
uint64 = Annotated[int, StructSerializer[int]('Q')]
float16 = Annotated[float, StructSerializer[float]('e')]
float32 = Annotated[float, StructSerializer[float]('f')]
float64 = Annotated[float, StructSerializer[float]('d')]


_SizeTypes = (uint8, uint16, uint32, uint64)
_TSize = TypeVar('_TSize', uint8, uint16, uint32, uint64)


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

    serializer = StructSerializer('x')
    value_type = type(None)


class pascal(bytes, counted):
    """String format specifier (bytes in Python).  See 'p' in the stdlib struct
    documentation for specific details.
    """

    serializer = StructSerializer[bytes]('p')
    value_type = bytes

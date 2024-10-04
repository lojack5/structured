"""
Serializer that wraps another in a condition. When the condition evaluates
to a Truthy value, the original serializer operates as normal. Otherwise,
it acts as if the serializer was not there.
"""

__all__ = [
    'ConditionalSerializer',
]

from ..type_checking import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Callable,
    Generic,
    ReadableBuffer,
    Self,
    Ts,
    TypeVar,
    Unpack,
    WritableBuffer,
)
from .api import ByteOrder, Serializer

if TYPE_CHECKING:
    # *Only* used for type-hinting, so ok to guard with a TYPE_CHECKING
    from ..structured import Structured

    TStructured = TypeVar('TStructured', bound=Structured)
else:
    TStructured = TypeVar('TStructured')


class ConditionalSerializer(Generic[Unpack[Ts]], Serializer[Unpack[Ts]]):
    def __init__(
        self,
        serializer: Serializer[Unpack[Ts]],
        condition: Callable[[TStructured], bool],
        default: tuple[Unpack[Ts]],
    ) -> None:
        self.condition = condition
        self.serializers: dict[bool, Serializer[Unpack[Ts]]] = {
            True: serializer,
            False: SkipSerializer(default),
        }
        self.num_values = serializer.num_values
        if serializer.num_values != len(default):
            expected = len(default)
            raise ValueError(
                'Not enough default arguments provided to Condition, expected '
                f'{self.num_values}, got {expected}'
            )
        
    def get_final(self) -> Serializer | None:
        return self.serializers[True].get_final()

    def with_byte_order(self, byte_order: ByteOrder) -> Self:
        serializer = self.serializers[True].with_byte_order(byte_order)
        defaults = self.serializers[False].values
        return type(self)(serializer, self.condition, defaults)

    def prepack(self, partial_object: Any) -> Serializer[Unpack[Ts]]:
        return self.serializers[self.condition(partial_object)]

    def preunpack(self, partial_object: Any) -> Serializer[Unpack[Ts]]:
        return self.prepack(partial_object)


class SkipSerializer(Generic[Unpack[Ts]], Serializer[Unpack[Ts]]):
    size: int = 0

    def __init__(self, values: tuple[Unpack[Ts]]):
        self.values = values
        self.num_values = len(values)

    def pack(self, *values: Unpack[Ts]) -> bytes:
        return b''

    def pack_into(
        self, buffer: WritableBuffer, offset: int, *values: Unpack[Ts]
    ) -> None:
        pass

    def pack_write(self, writable: BinaryIO, *values: Unpack[Ts]) -> None:
        pass

    def unpack(self, buffer: ReadableBuffer) -> tuple[Unpack[Ts]]:
        return self.values

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> tuple[Unpack[Ts]]:
        return self.values

    def unpack_read(self, readable: BinaryIO) -> tuple:
        return self.values

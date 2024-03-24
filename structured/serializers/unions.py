"""
Serializers for handling union type-hints.  Must be supplied by hinting the
union with typing.Annotated.
"""

from __future__ import annotations

__all__ = [
    'AUnion',
    'LookbackDecider',
    'LookaheadDecider',
]

import os

from ..type_checking import (
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Iterable,
    ReadableBuffer,
    WritableBuffer,
    annotated,
    get_union_args,
)
from .api import Serializer


class AUnion(Serializer):
    """Base class for union serializers, which are used to determine which
    serializer to use for a given value.
    """

    num_values: ClassVar[int] = 1
    result_map: dict[Any, Serializer]
    default: Serializer | None
    _last_serializer: Serializer | None

    def __init__(self, result_map: dict[Any, Any], default: Any = None) -> None:
        """result_map should be a mapping of possible return values from `decider`
        to `Annotated` instances with a Serializer as an extra argument.  The
        default should either be `None` to raise an error if the decider returns
        an unmapped value, or an `Annotated` instance with a Serializer as an
        extra argument.
        """
        self.default = None if not default else self.validate_serializer(default)
        self.result_map = {
            key: self.validate_serializer(serializer)
            for key, serializer in result_map.items()
        }
        self.size = 0

    @staticmethod
    def validate_serializer(hint) -> Serializer:
        serializer = annotated(Serializer).extract(hint)
        if serializer is None:
            raise TypeError(f'Union results must be serializable types, got {hint!r}.')
        elif serializer.num_values != 1:
            raise ValueError('Union results must serializer a single item.')
        return serializer

    def prepack(self, partial_object) -> Serializer:
        self._partial_object = partial_object
        return self

    def preunpack(self, partial_object) -> Serializer:
        self._partial_object = partial_object
        return self

    def get_serializer(self, decider_result: Any, packing: bool) -> Serializer:
        """Given a target used to decide, return a serializer used to unpack."""
        if self.default is None:
            try:
                serializer = self.result_map[decider_result]
            except KeyError:
                raise ValueError(
                    f'Union decider returned an unmapped value {decider_result!r}'
                ) from None
        else:
            serializer = self.result_map.get(decider_result, self.default)
        if packing:
            return serializer.prepack(self._partial_object)
        else:
            return serializer.preunpack(self._partial_object)

    @staticmethod
    def _transform(unwrapped: Any, actual: Any) -> Any:
        if union_args := get_union_args(actual):
            extract = annotated(Serializer).extract
            if all(map(extract, union_args)):
                if isinstance(unwrapped, AUnion):
                    return unwrapped


annotated.register_transform(AUnion._transform)


class LookbackDecider(AUnion):
    # NOTE: Union types are not allowed in TypeVarTuples, so we can't hint this
    """Serializer to handle loading of attributes with multiple types, type is
    decided just prior to packing/unpacking the attribute via inspection of the
    values already unpacked on the object.
    """

    def __init__(
        self,
        decider: Callable[[Any], Any],
        result_map: dict[Any, Any],
        default: Any = None,
    ) -> None:
        """result_map should be a mapping of possible return values from `decider`
        to `Annotated` instances with a Serializer as an extra argument.  The
        default should either be `None` to raise an error if the decider returns
        an unmapped value, or an `Annotated` instance with a Serializer as an
        extra argument.
        """
        super().__init__(result_map, default)
        self.decider = decider

    def decide(self, packing: bool) -> Serializer:
        result = self.decider(self._partial_object)
        return self.get_serializer(result, packing)

    def pack(self, *values: Any) -> bytes:
        serializer = self.decide(True)
        data = serializer.pack(*values)
        self.size = serializer.size
        return data

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: Any) -> None:
        serializer = self.decide(True)
        serializer.pack_into(buffer, offset, *values)
        self.size = serializer.size

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        serializer = self.decide(True)
        serializer.pack_write(writable, *values)
        self.size = serializer.size

    def unpack(self, buffer: ReadableBuffer) -> Iterable:
        serializer = self.decide(False)
        value = serializer.unpack(buffer)
        self.size = serializer.size
        return value

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> Iterable:
        serializer = self.decide(False)
        value = serializer.unpack_from(buffer, offset)
        self.size = serializer.size
        return value

    def unpack_read(self, readable: BinaryIO) -> Iterable:
        serializer = self.decide(False)
        value = serializer.unpack_read(readable)
        self.size = serializer.size
        return value


class LookaheadDecider(AUnion):
    """Union serializer that reads ahead into the input stream to determine how
    to unpack the next value.  For packing, a write decider method is used to
    determine how to pack the next value."""

    read_ahead_serializer: Serializer

    def __init__(
        self,
        read_ahead_serializer: Any,
        write_decider: Callable[[Any], Any],
        result_map: dict[Any, Any],
        default: Any = None,
    ) -> None:
        super().__init__(result_map, default)
        self.decider = write_decider
        serializer = annotated(Serializer).extract(read_ahead_serializer)
        if not serializer:
            raise TypeError(
                'read_ahead_serializer must be a Serializer, got '
                f'{read_ahead_serializer!r}.'
            )
        self.read_ahead_serializer = serializer

    def pack(self, *values: Any) -> bytes:
        result = self.decider(self._partial_object)
        serializer = self.get_serializer(result, True)
        data = serializer.pack(*values)
        self.size = serializer.size
        return data

    def pack_into(self, buffer: WritableBuffer, offset: int, *values: Any) -> None:
        result = self.decider(self._partial_object)
        serializer = self.get_serializer(result, True)
        serializer.pack_into(buffer, offset, *values)
        self.size = serializer.size

    def pack_write(self, writable: BinaryIO, *values: Any) -> None:
        result = self.decider(self._partial_object)
        serializer = self.get_serializer(result, True)
        serializer.pack_write(writable, *values)
        self.size = serializer.size

    def unpack(self, buffer: ReadableBuffer) -> Iterable:
        result = tuple(self.read_ahead_serializer.unpack(buffer))[0]
        serializer = self.get_serializer(result, False)
        values = serializer.unpack(buffer)
        self.size = serializer.size
        return values

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> Iterable:
        result = tuple(self.read_ahead_serializer.unpack_from(buffer, offset))[0]
        serializer = self.get_serializer(result, False)
        values = serializer.unpack_from(buffer, offset)
        self.size = serializer.size
        return values

    def unpack_read(self, readable: BinaryIO) -> Iterable:
        result = tuple(self.read_ahead_serializer.unpack_read(readable))[0]
        readable.seek(-self.read_ahead_serializer.size, os.SEEK_CUR)
        serializer = self.get_serializer(result, False)
        values = serializer.unpack_read(readable)
        self.size = serializer.size
        return values

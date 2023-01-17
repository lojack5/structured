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
    serializer: Serializer

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
        self.serializer = self.default    # type: ignore

    @staticmethod
    def validate_serializer(hint) -> Serializer:
        serializer = annotated(Serializer).extract(hint)
        if serializer is None:
            raise TypeError(f'Union results must be serializable types, got {hint!r}.')
        elif serializer.num_values != 1:
            raise ValueError('Union results must serializer a single item.')
        return serializer

    @property
    def size(self) -> int:
        if self.serializer:
            return self.serializer.size
        else:
            return 0

    def set_serializer(self, decider_result: Any) -> None:
        """Given a target object and decider result, set the current serializer
        to use for  packing/unpacking.
        """
        if self.default is None:
            try:
                serializer = self.result_map[decider_result]
            except KeyError:
                raise ValueError(
                    f'Union decider returned an unmapped value {decider_result!r}'
                ) from None
        else:
            serializer = self.result_map.get(decider_result, self.default)
        serializer.preprocess(self.target)
        self.serializer = serializer

    def decide(self, packing: bool = True) -> None:
        raise NotImplementedError

    def pack(self, *values: Any) -> bytes:
        self.decide()
        return self.serializer.pack(*values)

    def pack_into(self, buffer: WritableBuffer, offset: int, *values) -> None:
        self.decide()
        self.serializer.pack_into(buffer, offset, *values)

    def pack_write(self, writable: BinaryIO, *values) -> None:
        self.decide()
        self.serializer.pack_write(writable, *values)

    def unpack(self, buffer: ReadableBuffer) -> Iterable:
        self.decide(False)
        return self.serializer.unpack(buffer)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> Iterable:
        self.decide(False)
        return self.serializer.unpack_from(buffer, offset)

    def unpack_read(self, readable: BinaryIO) -> Iterable:
        self.decide(False)
        return self.serializer.unpack_read(readable)

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

    def decide(self, packing: bool = True) -> None:
        self.set_serializer(self.decider(self.target))


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
        self.decider_result = None
        self.read_ahead_serializer = serializer

    def decide(self, packing: bool = True):
        if packing:
            self.set_serializer(self.decider(self.target))
        else:
            self.set_serializer(self.decider_result)

    def unpack(self, buffer: ReadableBuffer) -> Iterable:
        self.decider_result = tuple(self.read_ahead_serializer.unpack(buffer))[0]
        return super().unpack(buffer)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> Iterable:
        self.decider_result = tuple(self.read_ahead_serializer.unpack_from(buffer, offset))[0]
        return super().unpack_from(buffer, offset)

    def unpack_read(self, readable: BinaryIO) -> Iterable:
        self.decider_result = tuple(self.read_ahead_serializer.unpack_read(readable))[0]
        readable.seek(-self.read_ahead_serializer.size, os.SEEK_CUR)
        return super().unpack_read(readable)

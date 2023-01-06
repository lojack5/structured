from __future__ import annotations

__all__ = [
    'AUnion',
    'LookbackDecider',
    'LookaheadDecider',
    'config',
]

import os

from ..type_checking import (
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Iterable,
    ReadableBuffer,
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
        self._last_serializer = self.default

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
        if self._last_serializer:
            return self._last_serializer.size
        else:
            return 0

    def get_serializer(
        self, decider_result: Any, partial_object: Any, packing: bool
    ) -> Serializer:
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
            serializer = serializer.prepack(partial_object)
        else:
            serializer = serializer.preunpack(partial_object)
        self._last_serializer = serializer
        return self._last_serializer

    @staticmethod
    def _transform(unwrapped: Any, actual: Any, cls: type, name: str) -> Any:
        for x in (unwrapped, actual):
            if union_args := get_union_args(x):
                extract = annotated(Serializer).extract
                if all(extract(x) is not None for x in union_args):
                    serializer = getattr(cls, name, None)
                    if isinstance(serializer, AUnion):
                        return serializer
                    else:
                        raise TypeError(
                            f'Union type {cls.__name__}.{name} must be configured'
                        )
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

    def prepack(self, partial_object: Any) -> Serializer:
        result = self.decider(partial_object)
        return self.get_serializer(result, partial_object, True)

    def preunpack(self, partial_object: Any) -> Serializer:
        result = self.decider(partial_object)
        return self.get_serializer(result, partial_object, False)


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

    def prepack(self, partial_object: Any) -> Serializer:
        result = self.decider(partial_object)
        return self.get_serializer(result, partial_object, True)

    def unpack(self, buffer: ReadableBuffer) -> Iterable:
        result = tuple(self.read_ahead_serializer.unpack(buffer))[0]
        return self.get_serializer(result, None, False).unpack(buffer)

    def unpack_from(self, buffer: ReadableBuffer, offset: int = 0) -> Iterable:
        result = tuple(self.read_ahead_serializer.unpack_from(buffer, offset))[0]
        return self.get_serializer(result, None, False).unpack_from(buffer, offset)

    def unpack_read(self, readable: BinaryIO) -> Iterable:
        result = tuple(self.read_ahead_serializer.unpack_read(readable))[0]
        readable.seek(-self.read_ahead_serializer.size, os.SEEK_CUR)
        return self.get_serializer(result, None, False).unpack_read(readable)


def config(decider: AUnion) -> Any:
    """Type erasing method for configuring Union types with a UnionSerializer"""
    return decider

"""
Array types
"""
from __future__ import annotations

__all__ = [
    'array',
    'Header',
]

from functools import cache

from ..base_types import requires_indexing
from ..serializers import (
    ArraySerializer,
    DynamicStructArraySerializer,
    NullSerializer,
    Serializer,
    StaticStructArraySerializer,
    StructSerializer,
)
from ..type_checking import Annotated, Generic, S, Self, T, TypeVar, annotated
from ..utils import StructuredAlias
from .basic_types import _SizeTypes


class Header:
    """Dispatching class for creating header serializers."""

    def __init__(
        self,
        count: int | StructSerializer[int],
        data_size: StructSerializer[int] | None,
    ) -> None:
        self.count = count
        self.data_size = data_size

    @classmethod
    def __class_getitem__(cls, args) -> Self:
        # Unpack arguments
        if not isinstance(args, tuple):
            # Length argument only
            length_kind = args
            size_kind = None
        elif len(args) == 2:
            # Length and size check arguments
            length_kind, size_kind = args
        else:
            raise TypeError(f'{cls.__name__}[] expected 1 or 2 arguments, got {args}')
        # Indirection so we can cache on the full arguments
        return cls._create(length_kind, size_kind)

    @classmethod
    @cache
    def _create(
        cls,
        length_kind: int | TypeVar | StructSerializer[int],
        size_kind: None | TypeVar | StructSerializer[int],
    ) -> Self:
        # TypeVar check
        if isinstance(length_kind, TypeVar) or isinstance(size_kind, TypeVar):
            return StructuredAlias(cls, (length_kind, size_kind))  # type: ignore
        # Check length argument
        if length_kind in _SizeTypes:
            unwrapped = annotated(StructSerializer[int]).extract(length_kind)
            if unwrapped:  # Always True for _SizeTypes
                length_kind = unwrapped
        elif isinstance(length_kind, int):
            if length_kind < 0:
                raise ValueError(
                    f'array length must be non-negative, got {length_kind}'
                )
        else:
            raise TypeError(f'invalid array length type: {length_kind!r}')
        # Check size argument
        if size_kind is not None and size_kind not in _SizeTypes:
            raise TypeError(f'invalid array size check type: {size_kind!r}')
        else:
            unwrapped = annotated(StructSerializer[int]).extract(size_kind)
            if unwrapped:  # Always True for _SizeTypes
                size_kind = unwrapped
        # All good
        return cls(length_kind, size_kind)


class array(Generic[S, T], list[T], requires_indexing):
    """Dispatching class used for typehinting to create ArraySerializers"""

    @classmethod
    @cache
    def __class_getitem__(cls, args) -> type[list[T]]:
        if not isinstance(args, tuple) or len(args) != 2:
            raise TypeError(f'{cls.__name__}[] expected 2 arguments, got {args!r}')
        header, item_type = args
        # TypeVar checks
        if isinstance(header, StructuredAlias) or isinstance(item_type, TypeVar):
            return StructuredAlias(cls, (header, item_type))  # type: ignore
        elif not isinstance(header, Header):
            raise TypeError(f'invalid array header type: {header!r}')
        # Item type checks
        item_serializer = annotated(Serializer).extract(item_type)
        if not item_serializer:
            raise TypeError(f'invalid array item type: {item_type!r}')
        # All good, check for specializations for struct.Struct unpackable
        if (
            isinstance(item_serializer, StructSerializer)
            and item_serializer.num_values == 1
        ):
            if isinstance(header.count, int):
                return Annotated[
                    list[T], StaticStructArraySerializer(header.count, item_serializer)
                ]
            else:
                return Annotated[
                    list[T], DynamicStructArraySerializer(header.count, item_serializer)
                ]
        # General array serializer
        if isinstance(header.count, int):
            # Static length
            static_length = header.count
            if header.data_size is None:
                header_serializer = NullSerializer()  # no size check
            else:
                header_serializer = header.data_size  # with size check
        else:
            # Dynamic length
            static_length = -1
            if header.data_size is None:
                header_serializer = header.count  # no size check
            else:
                header_serializer = header.count + header.data_size
        return Annotated[
            list[T],
            ArraySerializer[T](header_serializer, item_serializer, static_length),
        ]

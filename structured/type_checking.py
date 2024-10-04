# pragma: no cover
"""
Central location for importing typing memebers, with fallbacks for older Python
versions pulling from typing_extensions.  Also provides a few helper methods
to simplify some common patterns, as well as a method for extracting desired
hints from Annotated types.
"""
from __future__ import annotations

import sys
import typing
from itertools import chain
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Container,
    Generic,
    Iterable,
    Iterator,
    NewType,
    NoReturn,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

if sys.version_info < (3, 10):
    from typing_extensions import ParamSpec, TypeAlias, TypeGuard

    UnionType = NewType('UnionType', object)  # needed for TypeGuard on 3.9
    union_types = (Union,)
else:
    from types import UnionType
    from typing import ParamSpec, TypeAlias, TypeGuard

    union_types = (Union, UnionType)


if sys.version_info < (3, 11):
    from typing_extensions import Self, TypeVarTuple, Unpack, dataclass_transform
else:
    from typing import Self, TypeVarTuple, Unpack, dataclass_transform


S = TypeVar('S')
T = TypeVar('T')
U = TypeVar('U')
V = TypeVar('V')
W = TypeVar('W')
Ts = TypeVarTuple('Ts')
Ss = TypeVarTuple('Ss')
P = ParamSpec('P')


def update_annotations(cls: type, annotations: dict[str, Any]) -> None:
    """Python <3.10 compatible way to update a class's annotations dict. See:

    https://docs.python.org/3/howto/annotations.html#accessing-the-annotations-dict-of-an-object-in-python-3-9-and-older
    """
    if '__annotations__' in cls.__dict__:
        cls.__annotations__.update(annotations)
    else:
        setattr(cls, '__annotations__', annotations)


def get_annotations(cls: type) -> dict[str, Any]:
    """Python <3.10 compatible way to get a class's annotations dict.  See:

    https://docs.python.org/3/howto/annotations.html#accessing-the-annotations-dict-of-an-object-in-python-3-9-and-older
    """
    return cls.__dict__.get('__annotations__', {})


def isclassvar(annotation: Any) -> bool:
    """Determine if a type annotations is for a class variable.

    :param annotation: Fully resolved type annotation to test.
    """
    return get_origin(annotation) is ClassVar


def isunion(annotation: Any) -> TypeGuard[UnionType]:
    """Determine if a type annotation is a union.

    :param annotation: Fully resolved type annotation to test.
    """
    return get_origin(annotation) in union_types


def get_union_args(annotation: Any) -> tuple[Any, ...]:
    """Get the arguments of a union type annotation, or an empty tuple if the
    annotation is not a union.

    :param annotation: Fully resolved type annotation to test.
    """
    if isunion(annotation):
        return get_args(annotation)
    else:
        return ()


def istuple(annotation: Any) -> TypeGuard[tuple]:
    return get_origin(annotation) in (tuple, Tuple)


def get_tuple_args(annotation: Any, fixed_size: bool = True) -> tuple[Any, ...] | None:
    """Get the arguments to a tuple type hint, or None if the annotation is not
    a tuple hint.  If `fixed_size` is True (default), then the tuple must be
    a fixed length tuple hint.
    """
    if get_origin(annotation) in (tuple, Tuple):
        args = get_args(annotation)
        if fixed_size and args and args[-1] is Ellipsis:
            return None
        return args
    return None


class _annotated(Generic[Unpack[Ts]]):
    _transforms: ClassVar[list[Callable]] = []

    def __init__(self, *transforms: Callable) -> None:
        if transforms:
            self._transforms = type(self)._transforms[:]
            self._transforms.extend(transforms)

    @classmethod
    def register_transform(
        cls, transformer: Callable[[Any, Any], Union[Unpack[Ts]]]
    ) -> None:
        cls._transforms.append(transformer)

    @staticmethod
    def flatten_Annotated(hint: Any) -> tuple[Any, ...]:
        def _iter(h, *, start=0):
            if get_origin(h) is Annotated:
                for sub_h in get_args(h)[start:]:
                    yield from _iter(sub_h, start=1)
            else:
                yield h

        return tuple(_iter(hint))

    def transform(self, typehint: Any):
        base_type, *annotations = self.flatten_Annotated(typehint)
        annotations = (None,) + tuple(annotations)
        for annotation in annotations:
            for transform in reversed(self._transforms):
                new_type = transform(base_type, annotation)
                if new_type is not None:
                    base_type = new_type
        return base_type

    @classmethod
    def register_final_transform(cls, transform: Callable[[Any, Any], Any]):
        cls._transforms.insert(0, transform)

    def with_final(self, check: Callable[[Any, Any], Any]) -> Self:
        return type(self)(check)


annotated = _annotated()


@overload
def safe_issubclass(a, cls: type[T]) -> TypeGuard[type[T]]: ...


@overload
def safe_issubclass(
    a, cls: tuple[Unpack[Ts]]
) -> TypeGuard[type[Union[Unpack[Ts]]]]: ...


def safe_issubclass(a, cls):  # type: ignore
    """issubclass check without having to check if isinstance(a, type) first."""
    try:
        return issubclass(a, cls)
    except TypeError:
        return False


if typing.TYPE_CHECKING:
    import array
    import ctypes
    import io
    import mmap
    import pickle
    import sys

    ReadOnlyBuffer: TypeAlias = bytes
    # Anything that implements the read-write buffer interface. The buffer
    # interface is defined purely on the C level, so we cannot define a normal
    # Protocol for it (until PEP 688 is implemented). Instead we have to list
    # the most common stdlib buffer classes in a Union.
    if sys.version_info >= (3, 8):
        WritableBuffer: TypeAlias = Union[
            bytearray,
            memoryview,
            array.array[Any],
            mmap.mmap,
            # ctypes._CData, pickle.PickleBuffer
        ]
    else:
        WritableBuffer: TypeAlias = Union[  # type: ignore
            bytearray,
            memoryview,
            array.array[Any],
            mmap.mmap,
            # ctypes._CData
        ]
    ReadableBuffer: TypeAlias = Union[ReadOnlyBuffer, WritableBuffer]
else:
    WritableBuffer: TypeAlias = bytearray
    ReadableBuffer: TypeAlias = Union[bytes, bytearray]

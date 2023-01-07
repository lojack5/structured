# pragma: no cover
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


class _annotated(Generic[Unpack[Ts]]):
    _transforms: ClassVar[list[Callable]] = []

    def __init__(self, *want_types: Unpack[Ts]) -> None:
        subclass_checks = [
            get_args(x)[0]
            for x in want_types
            if (origin := get_origin(x)) in (type, Type)
        ]
        subclass_checks = [
            union_args if (union_args := get_union_args(x)) else (x,)
            for x in subclass_checks
        ]
        self.subclass_checks = tuple(chain.from_iterable(subclass_checks))
        instance_checks = [
            origin if origin else x
            for x in want_types
            if (origin := get_origin(x)) not in (type, Type)
        ]
        instance_checks = [
            union_args if (union_args := get_union_args(x)) else (x,)
            for x in instance_checks
        ]
        self.instance_checks = tuple(chain.from_iterable(instance_checks))
        self._custom_check = None

    @classmethod
    def register_transform(
        cls, transformer: Callable[[Any, Any], Union[Unpack[Ts]]]
    ) -> None:
        cls._transforms.append(transformer)

    def extract(
        self, a: Any, *, cls: type | None = None, name: str = '', _actual=None
    ) -> Union[Unpack[Ts], None]:
        if get_origin(a) is Annotated:
            args = get_args(a)
            if _actual is not None:
                actual, extras = _actual, args[1:]
            else:
                actual, extras = args[0], args[1:]
            for extra in extras:
                nested = self.extract(extra, cls=cls, name=name, _actual=actual)
                if nested is not None:
                    nested = self._transform_and_check(nested, actual, cls, name)
                    if nested:
                        return nested  # type: ignore
            return self._transform_and_check(actual, _actual, cls, name)  # type: ignore
        return self._transform_and_check(a, _actual, cls, name)  # type: ignore

    def _transform_and_check(self, unwrapped, actual, cls, name):
        for xform in type(self)._transforms:
            unwrapped = xform(unwrapped, actual)
        if self._custom_check:
            if unwrapped is not None:
                if self._custom_check(unwrapped):
                    return unwrapped
            elif self._custom_check(actual):
                return actual
        for x in (unwrapped, actual):
            if isinstance(x, type):
                if issubclass(x, self.subclass_checks):
                    return x
            if isinstance(x, self.instance_checks):
                return x

    def with_check(
        self, checker: Callable[[Any], TypeGuard[U]]
    ) -> _annotated[Unpack[Ts], U]:
        inst = _annotated()
        inst.instance_checks = self.instance_checks
        inst.subclass_checks = self.subclass_checks
        inst._custom_check = checker
        return inst  # type: ignore

    @overload
    def __call__(self, *want_types: type[T]) -> _annotated[T]:
        ...

    @overload
    def __call__(self, *want_types: type[Union[T, U]]) -> _annotated[T, U]:
        ...

    @overload
    def __call__(self, *want_types: type[Union[T, U, V]]) -> _annotated[T, U, V]:
        ...

    @overload
    def __call__(self, *want_types: type[Union[T, U, V, W]]) -> _annotated[T, U, V, W]:
        ...

    def __call__(self, *want_types):
        return _annotated(*want_types)


annotated = _annotated()


@overload
def safe_issubclass(a, cls: type[T]) -> TypeGuard[type[T]]:
    ...


@overload
def safe_issubclass(a, cls: tuple[Unpack[Ts]]) -> TypeGuard[type[Union[Unpack[Ts]]]]:
    ...


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

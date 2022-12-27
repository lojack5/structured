# pragma: no cover

import sys
import typing
from types import UnionType
from typing import (
    Annotated,
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Container,
    Generic,
    Iterable,
    NoReturn,
    Optional,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
    Union,
)

if sys.version_info < (3, 10):
    from typing_extensions import ParamSpec, TypeAlias, TypeGuard
else:
    from typing import ParamSpec, TypeAlias, TypeGuard

if sys.version_info < (3, 11):
    from typing_extensions import Self, dataclass_transform, TypeVarTuple, Unpack
else:
    from typing import Self, dataclass_transform, TypeVarTuple, Unpack


S = TypeVar('S')
T = TypeVar('T')
Ts = TypeVarTuple('Ts')
Ss = TypeVarTuple('Ss')


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
    return get_origin(annotation) in (Union, UnionType)


def get_union_args(annotation: Any) -> tuple[Any, ...]:
    """Get the arguments of a union type annotation, or an empty tuple if the
    annotation is not a union.

    :param annotation: Fully resolved type annotation to test.
    """
    if isunion(annotation):
        return get_args(annotation)
    else:
        return ()


if typing.TYPE_CHECKING:
    import array
    import ctypes
    import io
    import mmap
    import pickle
    import sys
    from typing import Any

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

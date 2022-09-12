import sys
import typing
from typing import (
    Any, Callable, ClassVar, Optional, Protocol, TypeVar, Union, Generic,
    get_origin, get_type_hints, runtime_checkable, NoReturn, cast,
)

if sys.version_info < (3, 10):
    from typing_extensions import TypeAlias, TypeGuard
else:
    from typing import TypeAlias, TypeGuard


_T = TypeVar('_T')


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


@runtime_checkable
class _SupportsRead1(Protocol):
    def read(self, size: Union[int, None] = ...) -> bytes: ...

    def seek(self, offset: int, whence: int = ..., /) -> int: ...

    def tell(self) -> int: ...


@runtime_checkable
class _SupportsRead2(Protocol):
    def read(self, size: Union[int, None] = ..., /) -> bytes: ...

    def seek(self, offset: int, whence: int = ..., /) -> int: ...

    def tell(self) -> int: ...

SupportsRead: TypeAlias = Union[_SupportsRead1, _SupportsRead2]


@runtime_checkable
class _SupportsWrite1(Protocol):
    def write(self, data: bytes) -> int: ...

    def seek(self, offset: int, whence: int = ..., /) -> int: ...

    def tell(self) -> int: ...


@runtime_checkable
class _SupportsWrite2(Protocol):
    def write(self, buffer: 'ReadableBuffer', /) -> int: ...

    def seek(self, offset: int, whence: int = ..., /) -> int: ...

    def tell(self) -> int: ...


SupportsWrite: TypeAlias = Union[_SupportsWrite1, _SupportsWrite2]


if typing.TYPE_CHECKING:
    import array
    import ctypes
    import mmap
    import pickle
    import sys
    import io
    from typing import Any

    ReadOnlyBuffer: TypeAlias = bytes
    # Anything that implements the read-write buffer interface. The buffer
    # interface is defined purely on the C level, so we cannot define a normal
    # Protocol for it (until PEP 688 is implemented). Instead we have to list
    # the most common stdlib buffer classes in a Union.
    if sys.version_info >= (3, 8):
        WritableBuffer: TypeAlias = Union[
            bytearray, memoryview, array.array[Any], mmap.mmap,
            # ctypes._CData, pickle.PickleBuffer
        ]
    else:
        WritableBuffer: TypeAlias = Union[  # type: ignore
            bytearray, memoryview, array.array[Any], mmap.mmap,
            # ctypes._CData
        ]
    ReadableBuffer: TypeAlias = Union[ReadOnlyBuffer, WritableBuffer]
else:
    WritableBuffer: TypeAlias = bytearray
    ReadableBuffer: TypeAlias = Union[bytes, bytearray]

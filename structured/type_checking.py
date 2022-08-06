import sys
import typing
from typing import Union, Protocol, runtime_checkable

if sys.version_info < (3, 10):
    from typing_extensions import TypeAlias
else:
    from typing import TypeAlias


@runtime_checkable
class SupportsRead(Protocol):
    def read(self, size: int | None = ...) -> bytes: ...


@runtime_checkable
class SupportsWrite(Protocol):
    def write(self, data: bytes) -> int: ...


if typing.TYPE_CHECKING:
    import array
    import ctypes
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
        WriteableBuffer: TypeAlias = Union[
            bytearray, memoryview, array.array[Any], mmap.mmap, ctypes._CData,
            pickle.PickleBuffer
        ]
    else:
        WriteableBuffer: TypeAlias = Union[  # type: ignore
            bytearray, memoryview, array.array[Any], mmap.mmap, ctypes._CData
        ]
    ReadableBuffer: TypeAlias = Union[ReadOnlyBuffer, WriteableBuffer]
else:
    WritableBuffer: TypeAlias = bytearray
    ReadableBuffer: TypeAlias = Union[bytes, bytearray]

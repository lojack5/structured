import typing
from typing import TypeAlias

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
        WriteableBuffer: TypeAlias = (
            bytearray | memoryview | array.array[Any] | mmap.mmap |
            ctypes._CData | pickle.PickleBuffer
        )
    else:
        WriteableBuffer: TypeAlias = (  # type: ignore
            bytearray | memoryview | array.array[Any] | mmap.mmap |
            ctypes._CData
        )
    ReadableBuffer: TypeAlias = ReadOnlyBuffer | WriteableBuffer
else:
    WritableBuffer: TypeAlias = bytearray
    ReadableBuffer: TypeAlias = bytes | bytearray

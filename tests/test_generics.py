import struct
from structured import *
from typing import Generic, TypeVar, Union

_Byte = TypeVar('_Byte', bound=Union[uint8, int8])
_String = TypeVar('_String', bound=Union[char, pascal, unicode])


class Base(Generic[_Byte, _String], Structured):
    a: _Byte
    b: _String


class UnsignedUnicode(Base[uint8, unicode[uint8]]):
    pass


def test_generics() -> None:
    obj = UnsignedUnicode(10, 'Hello')
    target_data = struct.pack('BB5s', 10, 5, b'Hello')

    # pack/unpack
    assert obj.pack() == target_data

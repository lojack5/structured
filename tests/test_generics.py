import struct
from typing import Generic, TypeVar, Union, get_type_hints

import pytest

from structured import *
from structured.utils import StructuredAlias


_Byte = TypeVar('_Byte', bound=Union[uint8, int8])
_String = TypeVar('_String', bound=Union[char, pascal, unicode])
_Size = TypeVar('_Size', bound=Union[uint8, uint16, uint32, uint64])
T = TypeVar('T', bound=Structured)
U = TypeVar('U')
V = TypeVar('V')


class Base(Generic[_Byte, _String], Structured):
    a: _Byte
    b: _String


class UnsignedUnicode(Base[uint8, unicode[uint8]]):
    pass


class Item(Structured):
    a: int8


class TestAliasing:
    tvar_map = {
        _Size: uint32,
        _Byte: uint8,
        T: Item,
    }

    def test_unicode(self) -> None:
        obj = unicode[_Size]
        assert isinstance(obj, StructuredAlias)
        assert obj.cls is unicode
        assert obj.args == (_Size, 'utf8')
        assert obj.resolve(self.tvar_map) is unicode[uint32]

    def test_Header(self) -> None:
        obj = Header[1, _Size]
        assert isinstance(obj, StructuredAlias)
        assert obj.cls is Header
        assert obj.args == (1, _Size)
        assert obj.resolve(self.tvar_map) is Header[1, uint32]

    def test_char(self) -> None:
        obj = char[_Size]
        assert isinstance(obj, StructuredAlias)
        assert obj.cls is char
        assert obj.args == (_Size,)
        assert obj.resolve(self.tvar_map) is char[uint32]

    def test_array(self) -> None:
        # same typevar
        obj = array[Header[_Size], _Size]
        assert isinstance(obj, StructuredAlias)
        assert obj.cls is array
        assert obj.args == (Header[_Size], _Size)
        assert obj.resolve(self.tvar_map) is array[Header[uint32], uint32]

        # different typevars
        obj = array[Header[_Size, _Byte], T]
        assert isinstance(obj, StructuredAlias)
        assert obj.cls is array
        assert obj.args == (Header[_Size, _Byte], T)

        obj1 = obj.resolve({_Size: uint32})
        assert isinstance(obj1, StructuredAlias)
        assert isinstance(obj1.args[0], StructuredAlias)
        assert obj1.args[0].args == (uint32, _Byte)
        assert obj1.args[1] is T

        obj2 = obj1.resolve({_Byte: uint8})
        assert isinstance(obj2, StructuredAlias)
        assert obj2.cls is array
        assert obj2.args == (Header[uint32, uint8], T)

        obj3 = obj2.resolve({T: Item})
        assert obj3 is array[Header[uint32, uint8], Item]
        assert obj.resolve(self.tvar_map) is array[Header[uint32, uint8], Item]


def test_automatic_resolution():
    class Item(Structured):
        a: int8

    class Base(Generic[_Size, T, U, V], Structured):
        a: _Size
        b: unicode[U]
        c: array[Header[1, V], T]

    class PartiallySpecialized(Generic[U, T], Base[uint8, T, uint32, U]): pass
    class FullySpecialized1(Base[uint8, Item, uint32, uint16]): pass
    class FullySpecialized2(PartiallySpecialized[uint16, Item]): pass

    assert PartiallySpecialized.attrs == ('a', 'b')
    hints = get_type_hints(PartiallySpecialized)
    assert hints['a'] is uint8
    assert hints['b'] is unicode[uint32]
    assert isinstance(hints['c'], StructuredAlias)

    assert FullySpecialized1.attrs == FullySpecialized2.attrs
    assert FullySpecialized1.attrs == ('a', 'b', 'c')
    assert get_type_hints(FullySpecialized1) == get_type_hints(FullySpecialized2)


def test_serialized_generics() -> None:
    class Base(Generic[_Size], Structured):
        a: list[_Size] = serialized(array[Header[3], _Size])

    class Concrete(Base[uint32]):
        pass

    assert Concrete.attrs == ('a',)
    target_data = struct.pack(f'3I', 1, 2, 3)
    target_obj =  Concrete.create_unpack(target_data)
    assert target_obj.a == [1, 2, 3]


def test_errors() -> None:
    class NotGeneric(Structured):
        a: uint8

    with pytest.raises(TypeError):
        NotGeneric._specialize(uint8)
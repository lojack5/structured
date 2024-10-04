import struct
from typing import Tuple, Generic, TypeVar

from structured import *

from . import standard_tests


T = TypeVar('T')
U = TypeVar('U')


def test_tuple_detection():
    class Base(Structured):
        a: tuple[int8, int16]

    assert isinstance(Base.serializer, TupleSerializer)
    assert Base.serializer.serializer.format == 'bh'

    target_obj = Base((1, 2))
    target_data = struct.pack('bh', 1, 2)
    standard_tests(target_obj, target_data)

    class Base2(Structured):
        a: Tuple[int8, int16]
    assert isinstance(Base2.serializer, TupleSerializer)

    target_obj = Base2((1, 2))
    standard_tests(target_obj, target_data)


def test_non_detection():
    class Base(Structured):
        a: tuple[int8, int]
    assert Base.attrs == ()

    class Base2(Structured):
        a: tuple[int8, ...]
    assert Base2.attrs == ()


def test_generics():
    class GenericStruct(Generic[T, U], Structured):
        a: tuple[T, U]
    assert isinstance(GenericStruct.serializer, NullSerializer)

    class ConcreteStruct1(GenericStruct[int8, int]):
        pass
    assert isinstance(ConcreteStruct1.serializer, NullSerializer)

    class ConcreteStruct2(GenericStruct[int8, int16]):
        pass
    assert isinstance(ConcreteStruct2.serializer, TupleSerializer)

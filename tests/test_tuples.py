import struct
from typing import Tuple

from structured import *

from . import standard_tests


def test_tuple_detection():
    class Base(Structured):
        a: tuple[int8, int16]

    assert isinstance(Base.serializer, TupleSerializer)

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
    assert Base.attrs == ()

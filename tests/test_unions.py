import sys
import struct
from operator import attrgetter
import io
from typing import Union, Annotated

import pytest

from structured import *
from structured.serializers import AUnion

from . import standard_tests


def test_errors() -> None:
    with pytest.raises(TypeError):
        # Invalid type in the result map
        LookbackDecider(lambda x: x, {0: int}, int32)
    with pytest.raises(TypeError):
        # Invalid default serializer
        LookbackDecider(lambda x: x, {0: int32}, int)
    with pytest.raises(ValueError):
        # Mapped result serializer must unpack a single value
        LookbackDecider(lambda x: x, {1: pad[1]}, None)
    with pytest.raises(ValueError):
        # Default serializer must unpack a single value
        LookbackDecider(lambda x: x, {1: int32}, pad[1])

    class Proxy:
        a = 0
    a = Proxy()

    # No default specified, and decider returned an invalid value
    serializer = LookbackDecider(attrgetter('a'), {1: int32}, None)
    with pytest.raises(ValueError):
        serializer = serializer.prepack(a)
        serializer.pack(1)


def test_lookback() -> None:
    class Base(Structured):
        a: Annotated[Union[int8, char[1]], LookbackDecider(lambda x: 0, {0: int8}, int8)]

    assert isinstance(Base.serializer, LookbackDecider)

    test_data = struct.pack('b', 42)
    test_obj = Base(42)

    standard_tests(test_obj, test_data)


def test_lookahead() -> None:
    class Record(Structured):
        sig: char[4]

    class IntRecord(Record):
        value: uint32

    class FloatRecord(Record):
        value: float32

    class Outer(Structured):
        record: Annotated[Union[IntRecord, FloatRecord], LookaheadDecider(char[4], attrgetter('record.sig'), {b'IINT': IntRecord, b'FLOA': FloatRecord}, None)]

    int_data = struct.pack('4sI', b'IINT', 42)
    float_data = struct.pack('4sf', b'FLOA', 1.125) # NOTE: exact float in binary

    int_obj = Outer(IntRecord(b'IINT', 42))
    float_obj = Outer(FloatRecord(b'FLOA', 1.125))

    for obj, data in ((int_obj, int_data), (float_obj, float_data)):
        standard_tests(obj, data)


@pytest.mark.skipif(sys.version_info < (3, 10), reason='requires Python 3.10 or higher')
def test_union_syntax() -> None:
    class Base(Structured):
        a: Annotated[int8 | char[4], LookbackDecider(lambda x: 0, {0: int8}, int8)]

    assert isinstance(Base.serializer, AUnion)


def test_compound_serializer() -> None:
    class Base(Structured):
        a_type: uint8
        a: Annotated[Union[uint32, float32, char[4]], LookbackDecider(attrgetter('a_type'), {0: uint32, 1: float32}, char[4])]

    assert Base.attrs == ('a_type', 'a')
    assert isinstance(Base.serializer, CompoundSerializer)

    # NOTE: Using a float that can be represented exactly in binary
    test_data = [struct.pack('=BI', 0, 42), struct.pack('=Bf', 1, 1.125), struct.pack('=B4s', 2, b'FOOD')]
    test_objs = [Base(0, 42), Base(1, 1.125), Base(2, b'FOOD')]

    # Check size to ensure the preprocessing serializers are correctly updating
    # their origin serializers.
    for data, obj in zip(test_data, test_objs):
        standard_tests(obj, data)

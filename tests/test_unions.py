import sys
import struct
from operator import attrgetter
import io
from typing import Union

import pytest

from structured import *
from structured.serializers import AUnion


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
        serializer.prepack(a)


def test_lookback() -> None:
    class Base(Structured):
        a: Union[int8, char[1]] = config(LookbackDecider(lambda x: 0, {0: int8}, int8))

    assert isinstance(Base.serializer, LookbackDecider)

    test_data = struct.pack('b', 42)
    test_obj = Base(42)

    assert test_obj.pack() == test_data
    assert Base.create_unpack(test_data) == test_obj

    buffer = bytearray(len(test_data))
    test_obj.pack_into(buffer)
    assert bytes(buffer) == test_data
    assert Base.create_unpack_from(buffer) == test_obj

    with io.BytesIO() as stream:
        test_obj.pack_write(stream)
        assert stream.getvalue() == test_data
        stream.seek(0)
        assert Base.create_unpack_read(stream) == test_obj


def test_lookahead() -> None:
    class Record(Structured):
        sig: char[4]

    class IntRecord(Record):
        value: uint32

    class FloatRecord(Record):
        value: float32

    class Outer(Structured):
        record: Union[IntRecord, FloatRecord] = config(LookaheadDecider(char[4], attrgetter('record.sig'), {b'IINT': IntRecord, b'FLOA': FloatRecord}, None))

    int_data = struct.pack('4sI', b'IINT', 42)
    float_data = struct.pack('4sf', b'FLOA', 1.125) # NOTE: exact float in binary

    int_obj = Outer(IntRecord(b'IINT', 42))
    float_obj = Outer(FloatRecord(b'FLOA', 1.125))

    for obj, data in ((int_obj, int_data), (float_obj, float_data)):
        assert obj.pack() == data
        assert Outer.create_unpack(data) == obj

        buffer = bytearray(len(data))
        obj.pack_into(buffer)
        assert bytes(buffer) == data
        assert Outer.create_unpack_from(buffer) == obj

        with io.BytesIO() as stream:
            obj.pack_write(stream)
            assert stream.getvalue() == data
            stream.seek(0)
            assert Outer.create_unpack_read(stream) == obj


@pytest.mark.skipif(sys.version_info < (3, 10), reason='requires Python 3.10 or higher')
def test_union_syntax() -> None:
    class Base(Structured):
        a: int8 | char[4] = config(LookbackDecider(lambda x: 0, {0: int8}, int8))

    assert isinstance(Base.serializer, AUnion)


def test_compound_serializer() -> None:
    class Base(Structured):
        a_type: uint8
        a: Union[uint32, float32, char[4]] = config(LookbackDecider(attrgetter('a_type'), {0: uint32, 1: float32}, char[4]))

    assert Base.attrs == ('a_type', 'a')
    assert isinstance(Base.serializer, CompoundSerializer)

    # NOTE: Using a float that can be represented exactly in binary
    test_data = [struct.pack('=BI', 0, 42), struct.pack('=Bf', 1, 1.125), struct.pack('=B4s', 2, b'FOOD')]
    test_objs = [Base(0, 42), Base(1, 1.125), Base(2, b'FOOD')]

    # Check size to ensure the preprocessing serializers are correctly updating
    # their origin serializers.
    for data, obj in zip(test_data, test_objs):
        assert obj.pack() == data
        assert obj.serializer.size == 5
        assert Base.create_unpack(data) == obj
        assert obj.serializer.size == 5

        buffer = bytearray(len(data))
        obj.pack_into(buffer)
        assert obj.serializer.size == 5
        assert bytes(buffer) == data
        assert Base.create_unpack_from(buffer) == obj
        assert obj.serializer.size == 5

        with io.BytesIO() as stream:
            obj.pack_write(stream)
            assert obj.serializer.size == 5
            assert stream.getvalue() == data
            stream.seek(0)
            assert Base.create_unpack_read(stream) == obj
            assert obj.serializer.size == 5

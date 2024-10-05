import struct

import pytest

from structured import *
from structured.type_checking import Annotated

from . import standard_tests, Final


class TestConditional:
    def test_errors(self) -> None:
        with pytest.raises(TypeError):
            class Base(Structured):
                a: Annotated[int, Condition(lambda x: True, 0)]

        with pytest.raises(ValueError):
            class Base(Structured):
                a: Annotated[uint8, Condition(lambda x: True)]
    
        with pytest.raises(ValueError):
            class Base(Structured):
                a: Annotated[uint8, Condition(lambda x: True, 1, 2)]

    def test_condition(self) -> None:
        # See docs NOTE about using Condition with simple types and padding, to
        # avoid having to do that here, we'll use the NETWORK byte order specifier
        class Versioned(Structured, byte_order=ByteOrder.NETWORK):
            version: uint8
            field1: uint32
            field5: Annotated[int16, Condition(lambda x: x.version > 2, -1)] # Added in version 3
            field2: char[2]
            field4: Annotated[float32, Condition(lambda x: x.version > 1, 0.0)] # Added in version 2
            field3: uint16

        v1_data = struct.pack('!BI2sH', 1, 42, b'Hi', 69)
        v1_obj = Versioned(1, 42, -1, b'Hi', 0.0, 69)
        # Note: Pick float values that can be represented exactly
        v2_data = struct.pack('!BI2sfH', 2, 42, b'Hi', 1.125, 69)
        v2_obj = Versioned(2, 42, -1, b'Hi', 1.125, 69)
        v3_data = struct.pack('!BIh2sfH', 3, 42, -42, b'Hi', 1.125, 69)
        v3_obj = Versioned(3, 42, -42, b'Hi', 1.125, 69)

        standard_tests(v1_obj, v1_data)
        standard_tests(v2_obj, v2_data)
        standard_tests(v3_obj, v3_data)

        v2_obj.version = 1
        assert v2_obj.pack() == v1_data
        v3_obj.version = 2
        assert v3_obj.pack() == v2_data
        v3_obj.version = 1
        assert v3_obj.pack() == v1_data

    def test_finality(self) -> None:
        class Base(Structured):
            a: Annotated[int, Final(), Condition(lambda x: True, 0)]

        assert isinstance(Base.serializer, ConditionalSerializer)
        assert Base.serializer.serializers[True].is_final()
        assert Base.serializer.is_final()

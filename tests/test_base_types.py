import io
import struct

from typing import Annotated

import pytest

from structured import *
from structured.serializers import noop_action
from structured.type_checking import annotated

from . import standard_tests


## Only tests needed for lines not tested by Structured tests


def test_counted() -> None:
    cls = annotated(Serializer).extract(pad[2])
    assert isinstance(cls, StructSerializer)
    assert cls.format == '2x'
    assert cls.num_values == 0

    with pytest.raises(TypeError):
        pad['']
    with pytest.raises(ValueError):
        pad[-1]


class TestCustomType:
    def test_subclassing_any(self) -> None:
        class MutableType:
            def __init__(self, value: int):
                self._value = value

            def __int__(self) -> int:
                return self._value

            def __index__(self) -> int:
                # For struct.pack
                return self._value

            def negate(self) -> None:
                self._value = -self._value

            def __eq__(self, other) -> bool:
                if isinstance(other, type(self)):
                    return self._value == other._value
                else:
                    return self._value == other

        for bo in ByteOrder:
            class Base(Structured, byte_order=bo):
                a: Annotated[MutableType, SerializeAs(int16)]
                b: Annotated[MutableType, SerializeAs(uint32)]
            assert isinstance(Base.serializer, StructActionSerializer)
            assert Base.serializer.actions == (MutableType, MutableType)
            target_obj = Base(MutableType(11), MutableType(42))
            target_data = Base.serializer.pack(11, 42)

            standard_tests(target_obj, target_data)

            b = Base.create_unpack(target_data)
            assert isinstance(b.a, MutableType)


    def test_custom_action(self) -> None:
        class MutableType:
            _wrapped: int

            def __init__(self, not_an_int, value: int):
                self._wrapped = value

            def __index__(self) -> int:
                return self._wrapped

            @classmethod
            def from_int(cls, value: int):
                return cls(None, value)

            def __eq__(self, other):
                if isinstance(other, MutableType):
                    return self._wrapped == other._wrapped
                else:
                    return self._wrapped == other
        MutableType8 = Annotated[MutableType, SerializeAs(int8).with_factory(MutableType.from_int)]

        class Base(Structured):
            a: MutableType8
            b: int8
        assert isinstance(Base.serializer, StructActionSerializer)
        assert Base.serializer.actions == (MutableType.from_int, noop_action)
        assert Base.serializer.format == '2b'
        assert Base.serializer.num_values == 2

        target_obj = Base(MutableType(None, 42), 10)
        target_data = struct.pack('2b', 42, 10)

        standard_tests(target_obj, target_data)

    def test_errors(self) -> None:
        with pytest.raises(TypeError):
            # Must serialize as a StructSerializer with 1 value
            SerializeAs(pad[1])
        with pytest.raises(TypeError):
            SerializeAs(StructSerializer('2b'))
        with pytest.raises(TypeError):
            # Not a struct serializer
            SerializeAs(array)

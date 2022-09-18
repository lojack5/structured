import io

import pytest

from structured import *


## Only tests needed for lines not tested by Structured tests


def test_counted() -> None:
    cls = pad[2]
    assert cls.format == '2x'
    assert cls.__qualname__ == 'pad[2]'

    with pytest.raises(TypeError):
        pad['']
    with pytest.raises(ValueError):
        pad[0]


class TestFormatted:
    def test_subclassing_any(self) -> None:
        class MutableType(Formatted):
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

        assert MutableType[int16].format == 'h'
        assert MutableType[int16].unpack_action is MutableType[int16]

        class Base(Structured):
            a: MutableType[int16]
            b: MutableType[uint32]
        target_obj = Base(MutableType[int16](11), MutableType[uint32](42))

        target_data = Base.serializer.pack(11, 42)

        assert target_obj.pack() == target_data
        b = Base.create_unpack(target_data)
        assert isinstance(b.a, MutableType)
        assert type(b.a) is MutableType[int16]
        assert b == target_obj
        assert b.a == 11

    def test_custom_action(self) -> None:
        class MutableType(Formatted):
            _wrapped: int

            def __init__(self, not_an_int, value: int):
                self._wrapped = value

            def __index__(self) -> int:
                return self._wrapped

            @classmethod
            def from_int(cls, value: int):
                return cls(None, value)

            def __eq__(self, other):
                if isinstance(other, type(self)):
                    return self._wrapped == other._wrapped
                else:
                    return self._wrapped == other
        MutableType.unpack_action = MutableType.from_int
        class Base(Structured):
            a: MutableType[int8]
            b: int8
        target_obj = Base(MutableType[int8](None, 42), 10)

        assert isinstance(Base.serializer, StructActionSerializer)
        target_data = Base.serializer.pack(42, 10)

        assert target_obj.pack() == target_data
        assert Base.create_unpack(target_data) == target_obj

        buffer = bytearray(Base.serializer.size)
        target_obj.pack_into(buffer)
        assert bytes(buffer) == target_data
        assert Base.create_unpack_from(buffer) == target_obj

        with io.BytesIO() as stream:
            target_obj.pack_write(stream)
            assert stream.getvalue() == target_data
            stream.seek(0)
            assert Base.create_unpack_read(stream) == target_obj

    def test_subclassing_specialized(self) -> None:
        class MutableType(Formatted):
            _types = frozenset({int8, int16})
        assert MutableType[int8].format == 'b'
        assert MutableType[int8].unpack_action is MutableType[int8]

    def test_errors(self) -> None:
        class Error1(Formatted):
            # Purposfully setting an incorrect type for _types, hence the ignore
            _types = frozenset({int})   # type: ignore
        with pytest.raises(TypeError):
            # Errors due to not having `int8` in `_types`
            Error1[int8]
        with pytest.raises(TypeError):
            # Errors due to `int` not being a `format_type`
            Error1[int]

        class Error2(Formatted):
            pass
        with pytest.raises(TypeError):
            Error2[int]

        Error3 = Error2[int8]
        with pytest.raises(TypeError):
            Error3[int8]

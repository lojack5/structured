__author__ = 'Lojack'

import io
import struct

import pytest

import structured
from structured import *


class TestStructured:
    def test_byte_order(self) -> None:
        for byte_order in ByteOrder:
            class Base(Structured, byte_order=byte_order):
                a: int8
            assert isinstance(Base.serializer, struct.Struct)
            if byte_order is ByteOrder.DEFAULT:
                assert Base.serializer.format[0] == 'b'
            else:
                assert Base.serializer.format[0] == byte_order.value

    def test_folding(self) -> None:
        class Base(Structured):
            a: int8
            b: int8
            c: int32
            d: int64
        assert isinstance(Base.serializer, struct.Struct)
        assert Base.serializer.format == '2biq'

    def test_types(self) -> None:
        class Base(Structured):
            _: pad[2]
            __: pad
            a: int8
            A: uint8
            b: int16
            B: uint16
            c: int32
            C: uint32
            d: int64
            D: uint64
            e: float16
            f: float32
            g: float64
            h: char[2]
            i: char
            j: pascal[2]
            k: pascal
            l: bool8

            other_member: int

            def method(self):
                return 'foo'

        assert isinstance(Base.serializer, struct.Struct)
        assert ''.join(Base.attrs) == 'aAbBcCdDefghijkl'
        assert Base.serializer.format == '3xbBhHiIqQefd2ss2pp?'

    def test_extending(self) -> None:
        # Test non-string types are folded in the format string
        class Base(Structured):
            a: int8
            b: int16
            c: int16
        class Derived(Base):
            d: int16
        assert isinstance(Derived.serializer, struct.Struct)
        assert Derived.serializer.format == 'b3h'
        # Test string types aren't folded
        # We shouldn't do
        ##
        ##  for string_type in (char, pascal):
        ##     class Base2(Structured):
        ##         a: string_type[10]
        # Since if annotations are strings (the will be in future python
        # versions), even `typing.get_type_hints` would fail to get the
        # type hints on Base2
        class Base2(Structured):
            a: char[10]
        class Derived2(Base2):
            b: char[3]
        assert isinstance(Derived2.serializer, struct.Struct)
        assert Derived2.serializer.format == '10s3s'

        class Base3(Structured):
            a: pascal[10]
        class Derived3(Base3):
            b: pascal[3]
        assert isinstance(Derived3.serializer, struct.Struct)
        assert Derived3.serializer.format == '10p3p'

    def test_override_types(self) -> None:
        class Base1(Structured):
            a: int8
            b: int16
        class Derived1(Base1):
            a: int16
        assert isinstance(Derived1.serializer, struct.Struct)
        assert Derived1.serializer.format == '2h'

        class Base2(Structured):
            a: int8
            b: int8
            c: int8
        class Derived2(Base2):
            b: None
        assert isinstance(Derived2.serializer, struct.Struct)
        assert Derived2.serializer.format == '2b'
        assert tuple(Derived2.attrs) == ('a', 'c')


    def test_mismatched_byte_order(self) -> None:
        class Base(Structured):
            a: int8
        with pytest.raises(ValueError):
            class Derived(Base, byte_order=ByteOrder.LE):
                b: int8
        class Derived2(Base, byte_order=ByteOrder.LE, byte_order_mode=ByteOrderMode.OVERRIDE):
            b: int8
        assert isinstance(Derived2.serializer, struct.Struct)
        assert Derived2.serializer.format == ByteOrder.LE.value + '2b'  # type: ignore

    def test_unpack_read(self) -> None:
        class Base(Structured):
            a: int8
        b = Base(42)
        data = b.pack()
        with io.BytesIO(data) as stream:
            b.a = 0
            b.unpack_read(stream)
        assert b.a == 42

    def test_pack_write(self) -> None:
        class Base(Structured):
            a: int8
        b = Base(42)
        data = b.pack()
        with io.BytesIO() as stream:
            b.pack_write(stream)
            assert data == stream.getvalue()

    def test_pack_unpack(self) -> None:
        class Base(Structured):
            a: int8
            _: pad[2]
            b: char[6]

        assert isinstance(Base.serializer, struct.Struct)

        target_obj = Base(1, b'Hello!')

        st = struct.Struct('b2x6s')
        target_data = st.pack(1, b'Hello!')

        assert target_obj.pack() == target_data
        assert Base.create_unpack(target_data) == target_obj

    def test_pack_unpack_into(self) -> None:
        class Base(Structured):
            a: int8
            b: char[6]
        target_obj = Base(1, b'Hello!')

        assert isinstance(Base.serializer, struct.Struct)

        buffer = bytearray(Base.serializer.size)
        target_obj.pack_into(buffer)
        assert bytes(buffer) == target_obj.pack()
        assert Base.create_unpack_from(buffer) == target_obj

    def test_str(self) -> None:
        class Base(Structured):
            a: int8
            _: pad[3]
            b: char[6]
        b = Base(10, b'Hello!')
        assert str(b) == "Base(a=10, b=b'Hello!')"


class TestCounted:
    def test_indexing(self) -> None:
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

        assert MutableType[int16].format == int16.format
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
        assert MutableType[int8].format == int8.format
        assert MutableType[int8].unpack_action is MutableType[int8]

    def test_errors(self) -> None:
        class Error1(Formatted):
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


def test_fold_overlaps() -> None:
    # Test the branch not exercised by the above tests.
    assert structured.fold_overlaps('b', '') == 'b'          # type: ignore
    assert structured.fold_overlaps('4sI', 'I') == '4s2I'    # type: ignore

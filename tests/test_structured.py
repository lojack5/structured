__author__ = 'Lojack'

import pytest

import structured
from structured import *


class TestStructured:
    def test_byte_order(self) -> None:
        for byte_order in ByteOrder:
            class Base(Structured, byte_order=byte_order):
                a: int8
            if byte_order is ByteOrder.DEFAULT:
                assert Base.struct.format[0] == 'b'
            else:
                assert Base.struct.format[0] == byte_order.value

    def test_folding(self) -> None:
        class Base(Structured):
            a: int8
            b: int8
            c: int32
            d: int64
        assert Base.struct.format == '2biq'

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

            _private_member: int

            def method(self):
                return 'foo'

        assert ''.join(Base._attr_actions.keys()) == 'aAbBcCdDefghijkl'
        assert Base.struct.format == '3xbBhHiIqQefd2ss2pp?'

        with pytest.raises(TypeError):
            class Base2(Structured):
                a: bool

    def test_extending(self) -> None:
        # Test non-string types are folded in the format string
        class Base(Structured):
            a: int8
            b: int16
            c: int16
        class Derived(Base):
            d: int16
        assert Derived.struct.format == 'b3h'
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
        assert Derived2.struct.format == '10s3s'

        class Base3(Structured):
            a: pascal[10]
        class Derived3(Base3):
            b: pascal[3]
        assert Derived3.struct.format == '10p3p'

    def test_duplicate_names(self) -> None:
        class Base(Structured):
            a: int8
            b: int16
        with pytest.raises(SyntaxError):
            class Derived(Base):
                a: int16

    def test_mismatched_byte_order(self) -> None:
        class Base(Structured):
            a: int8
        with pytest.raises(ValueError):
            class Derived(Base, byte_order=ByteOrder.LE):
                b: int8
        class Derived2(Base, byte_order=ByteOrder.LE, byte_order_mode=ByteOrderMode.OVERRIDE):
            b: int8
        assert Derived2.struct.format == ByteOrder.LE.value + '2b'

    def test_pack_unpack(self) -> None:
        class Base(Structured):
            a: int8
            _: pad[2]
            b: char[6]
        b = Base()
        b.a = 1
        b.b = b'Hello!'

        class_packed = b.pack()
        struct_packed = Base.struct.pack(b.a, b.b)
        assert class_packed == struct_packed

        b.a = 0
        b.b = b''
        b.unpack(class_packed)
        assert b.a == 1
        assert b.b == b'Hello!'

    def test_pack_unpack_into(self) -> None:
        class Base(Structured):
            a: int8
            b: char[6]
        b = Base()
        b.a = 1
        b.b = b'Hello!'

        buffer = bytearray(Base.struct.size)
        b.pack_into(buffer)
        assert bytes(buffer) == b.pack()
        b.a = 0
        b.b = b''
        b.unpack_from(buffer)
        assert b.a == 1
        assert b.b == b'Hello!'

    def test_str(self) -> None:
        class Base(Structured):
            a: int8
            _: pad[3]
            b: char[6]
        b = Base()
        b.a = 10
        b.b = b'Hello!'
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

        assert MutableType[int16].format == int16.format
        assert MutableType[int16].apply_on_load

        class Base(Structured):
            a: MutableType[int16]
            b: MutableType[uint32]

        b = Base()
        data = Base.struct.pack(11, 42)
        b.unpack(data)
        assert isinstance(b.a, MutableType)
        assert type(b.a) is MutableType[int16]
        assert int(b.a) == 11

        packed = b.pack()
        assert data == packed

        b.a.negate()
        assert int(b.a) == -11


    def test_subclassing_specialized(self) -> None:
        class MutableType(Formatted):
            _types = {int8, int16}
        assert MutableType[int8].format == int8.format
        assert MutableType[int8].apply_on_load

    def test_errors(self) -> None:
        class Error1(Formatted):
            _types = frozenset({int})
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


def test_extract_byte_order() -> None:
    # Test the branch not exercised by the above tests
    byte_order, format = structured.StructuredMeta.extract_byte_order('')
    assert byte_order is ByteOrder.DEFAULT
    assert format == ''


def test_fold_overlaps() -> None:
    # Test the branch not exercised by the above tests.
    assert structured.fold_overlaps('b', '') == 'b'

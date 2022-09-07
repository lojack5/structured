__author__ = 'Lojack'

import io
import struct

import pytest

import structured
from structured import *
from structured.base_types import structured_type


class TestStructured:
    def test_init__(self) -> None:
        class Base(Structured):
            a: int8
            b: int32
            c: int16

        with pytest.raises(TypeError):
            Base(1, 2, 3, 4)    # Too many args
        with pytest.raises(TypeError):
            Base(1)             # not enough args
        with pytest.raises(TypeError):
            Base(2, 3, a=1)     # a both positional and keyword
        with pytest.raises(TypeError):
            Base(1, 2, 3, foo=1)    # Extra argument

        a = Base(1, 2, 3)
        assert a.a == 1
        assert a.b == 2
        assert a.c == 3

        b = Base(1, 2, c=3)
        assert b == a

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
        assert Derived2.serializer.format == ByteOrder.LE.value + '2b'

    def test_unpack_read(self) -> None:
        class Base(Structured):
            a: int  = serialized(int8)
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

        test_obj = Base(0, b'')
        test_obj.unpack(target_data)
        assert test_obj == target_obj


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

        test_obj = Base(0, b'')
        test_obj.unpack_from(buffer)
        assert test_obj == target_obj

    def test_str(self) -> None:
        class Base(Structured):
            a: int8
            _: pad[3]
            b: char[6]
        b = Base(10, b'Hello!')
        assert str(b) == "Base(a=10, b=b'Hello!')"

    def test_eq(self) -> None:
        class Base(Structured):
            a: int8
            b: char[6]
        class Derived(Base):
            pass

        a = Base(1, 'Hello!')
        b = Base(1, 'Hello!')
        c = Derived(1, 'Hello!')
        d = Base(0, 'Hello!')
        e = Base(1, 'banana')

        assert a == b
        assert a != c
        assert a != d
        assert a != e


def test_fold_overlaps() -> None:
    # Test the branch not exercised by the above tests.
    # Linter ignores due to 'fold_overlaps' not being in __all__
    assert structured.fold_overlaps('b', '') == 'b'          # type: ignore
    assert structured.fold_overlaps('4sI', 'I') == '4s2I'    # type: ignore
    assert structured.fold_overlaps('', 'b') == 'b'          # type: ignore


class rogue_type(structured_type): pass


def test_create_serializers() -> None:
    # Just the bits not tested by the above
    with pytest.raises(TypeError):
        class Error(Structured):
            a: array
    with pytest.raises(TypeError):
        class Error2(Structured):
            a: rogue_type

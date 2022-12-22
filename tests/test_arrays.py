import struct
import io
from typing import Annotated

import pytest

from structured import *
from structured.complex_types.array_headers import HeaderBase


class Item(Structured):
    a: int32
    b: uint8
    c: char[uint8]


@pytest.fixture
def items() -> list[Item]:
    return [
        Item(1, 11, b'foo'),
        Item(2, 22, b'bar'),
        Item(3, 33, b'Hello'),
    ]


def test_backwards_compat():
    a1 = array[1, uint32, Item]     # type: ignore
    a2 = array[Header[1, uint32], Item]
    assert a1 is a2


def test_errors():
    ## Number of args
    with pytest.raises(TypeError):
        Header[1, 2, 3]     # too many
    with pytest.raises(TypeError):
        array[Header[1]]    # type: ignore (not enough)
    with pytest.raises(TypeError):
        array[Header[1], 2, 3, 4]   # type: ignore (too many)
    ## Header type
    with pytest.raises(TypeError):
        array[Header, int32]
    with pytest.raises(TypeError):
        array[HeaderBase, int32]    # type: ignore
    ## Array type
    with pytest.raises(TypeError):
        array[Header[1], 2]     # type: ignore
    with pytest.raises(TypeError):
        array[Header[1], int]   # type: ignore
    ## Size check type
    with pytest.raises(TypeError):
        Header[1, 2]
    with pytest.raises(TypeError):
        Header[1, int]
    ## format_type arrays with a size check
    with pytest.raises(TypeError):
        array[Header[1, uint32], int32]
    with pytest.raises(TypeError):
        array[Header[uint32, uint32], int32]
    ## Array size
    with pytest.raises(ValueError):
        Header[0]       # invalid size
    with pytest.raises(ValueError):
        Header[0, uint32]      # invalid size
    with pytest.raises(TypeError):
        Header[int]     # invalid type
    with pytest.raises(TypeError):
        Header[int8]    # invalid type


def test_static_format():
    class Static(Structured):
        a: int32
        b: Annotated[list[uint32], array[Header[5], uint32]]
    target_obj = Static(42, [1, 2, 3, 4, 5])

    st = struct.Struct('i5I')
    target_data = st.pack(42, 1, 2, 3, 4, 5)

    # pack/unpack
    assert target_obj.pack() == target_data
    assert Static.create_unpack(target_data) == target_obj

    # from/into
    buffer = bytearray(Static.serializer.size)
    target_obj.pack_into(buffer)
    assert target_obj.serializer.size == st.size
    assert bytes(buffer) == target_data
    assert Static.create_unpack_from(buffer) == target_obj

    # read/write
    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert target_obj.serializer.size == st.size
        assert stream.getvalue() == target_data
        stream.seek(0)
        assert Static.create_unpack_read(stream) == target_obj

    # Incorrect array size
    target_obj.b = []
    with pytest.raises(ValueError):
        target_obj.pack()


def test_static_format_action():
    class WrappedInt:
        def __init__(self, wrapped: int):
            self._wrapped = wrapped

        def __index__(self) -> int:
            return self._wrapped

        def __eq__(self, other):
            if isinstance(other, type(self)):
                return self._wrapped == other._wrapped
            return NotImplemented
    WrappedInt8 = Annotated[WrappedInt, SerializeAs(int8)]

    class StaticAction(Structured):
        a: array[Header[3], WrappedInt8]

    target_obj = StaticAction(list(map(WrappedInt, (1 ,2, 3))))

    st = struct.Struct('3b')
    target_data = st.pack(1, 2, 3)

    # pack/unpack
    assert target_obj.pack() == target_data
    assert StaticAction.create_unpack(target_data) == target_obj

    # from/into
    buffer = bytearray(st.size)
    target_obj.pack_into(buffer)
    assert target_obj.serializer.size == st.size
    assert bytes(buffer) == target_data
    assert StaticAction.create_unpack_from(buffer) == target_obj

    # read/write
    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert target_obj.serializer.size == st.size
        assert stream.getvalue() == target_data
        stream.seek(0)
        assert StaticAction.create_unpack_read(stream) == target_obj


def test_static_structured(items: list[Item]):
    class Compound(Structured):
        a: Annotated[list[Item], array[Header[3], Item]]

    target_obj = Compound(items)
    with io.BytesIO() as out:
        for item in target_obj.a:
            # Using the fact that Structured.pack is tested already on basic
            # types to ensure this data is correct
            item.pack_write(out)
        target_data = out.getvalue()
    size = len(target_data)

    # pack/unpack
    assert target_obj.pack() == target_data
    assert Compound.create_unpack(target_data) == target_obj

    # from/into
    buffer = bytearray(size)
    target_obj.pack_into(buffer)
    assert target_obj.serializer.size == size
    assert bytes(buffer) == target_data
    assert Compound.create_unpack_from(buffer) == target_obj

    # read/write
    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert stream.getvalue() == target_data
        assert target_obj.serializer.size == size
        stream.seek(0)
        assert Compound.create_unpack_read(stream) == target_obj

    # incorrect array size
    target_obj.a = []
    with pytest.raises(ValueError):
        target_obj.pack()


def test_static_checked_structured(items: list[Item]):
    class Compound(Structured):
        a: Annotated[list[Item], array[Header[3, uint32], Item]]
    target_obj = Compound(items)

    with io.BytesIO() as stream:
        stream.write(struct.pack('I', 0))
        data_size = 0
        for item in target_obj.a:
            item.pack_write(stream)
            data_size += item.serializer.size
        stream.seek(0)
        stream.write(struct.pack('I', data_size))
        target_data = stream.getvalue()
    size = len(target_data)

    # pack/unpack
    assert target_obj.pack() == target_data
    assert Compound.create_unpack(target_data) == target_obj

    # from/into
    buffer = bytearray(size)
    target_obj.pack_into(buffer)
    assert target_obj.serializer.size == size
    assert Compound.create_unpack_from(buffer) == target_obj

    # read/write
    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert stream.getvalue() == target_data
        assert target_obj.serializer.size == size
        stream.seek(0)
        assert Compound.create_unpack_read(stream) == target_obj

    # Incorrect array size
    target_obj.a = []
    with pytest.raises(ValueError):
        target_obj.pack()

    # Test malformed data_size
    st = struct.Struct('I')
    st.pack_into(buffer, 0, 0)
    with pytest.raises(ValueError):
        Compound.create_unpack_from(buffer)


def test_dynamic_format():
    class Compound(Structured):
        a: array[Header[uint32], int8]
    target_obj = Compound([1, 2, 3])

    st = struct.Struct('I3b')
    target_data = st.pack(3, 1, 2, 3)

    # pack/unpack
    assert target_obj.pack() == target_data
    assert Compound.create_unpack(target_data) == target_obj

    # from/into
    buffer = bytearray(st.size)
    target_obj.pack_into(buffer)
    assert bytes(buffer) == target_data
    assert target_obj.serializer.size == st.size
    assert Compound.create_unpack_from(buffer) == target_obj

    # read/write
    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert stream.getvalue() == target_data
        assert target_obj.serializer.size == st.size
        stream.seek(0)
        assert Compound.create_unpack_read(stream) == target_obj


def test_dynamic_structured(items: list[Item]):
    class Compound(Structured):
        a: array[Header[uint32], Item]
    target_obj = Compound(items)

    with io.BytesIO() as out:
        # Item uses a plain struct serializer, already tested
        # So no need to construct the data fully from struct.pack
        out.write(struct.pack('I', 3))
        for item in target_obj.a:
            item.pack_write(out)
        target_data = out.getvalue()
    size = len(target_data)

    # pack/unpack
    assert target_obj.pack() == target_data
    assert Compound.create_unpack(target_data) == target_obj

    # from/into
    buffer = bytearray(size)
    target_obj.pack_into(buffer)
    assert bytes(buffer) == target_data
    assert target_obj.serializer.size == size
    assert Compound.create_unpack_from(buffer) == target_obj

    # read/write
    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert stream.getvalue() == target_data
        assert target_obj.serializer.size == size
        stream.seek(0)
        assert Compound.create_unpack_read(stream) == target_obj


def test_dynamic_checked_structured(items: list[Item]):
    class Compound(Structured):
        b: uint32
        a: array[Header[uint32, uint32], Item]
    target_obj = Compound(42, items)

    with io.BytesIO() as out:
        out.write(struct.pack('3I', 42, 3, 0))
        data_size = 0
        for item in target_obj.a:
            item.pack_write(out)
            data_size += item.serializer.size
        out.seek(0)
        out.write(struct.pack('3I', 42, 3, data_size))
        target_data = out.getvalue()
    size = len(target_data)

    # pack/unpack
    assert target_obj.pack() == target_data
    assert Compound.create_unpack(target_data) == target_obj

    # from/indo
    buffer = bytearray(size)
    target_obj.pack_into(buffer)
    assert bytes(buffer) == target_data
    assert target_obj.serializer.size == size
    assert Compound.create_unpack_from(buffer) == target_obj

    # read/write
    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert stream.getvalue() == target_data
        assert target_obj.serializer.size == size
        stream.seek(0)
        assert Compound.create_unpack_read(stream) == target_obj

    # Test malformed data_size
    st = struct.Struct('3I')
    st.pack_into(buffer, 0, 42, 3, 0)      # write over data_size with 0
    with pytest.raises(ValueError):
        Compound.create_unpack_from(buffer)

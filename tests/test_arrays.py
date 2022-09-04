import struct
import io

import pytest

from structured import *


class Item(Structured):
    a: int32
    b: uint8


def test_static_format():
    class Static(Structured):
        a: int32
        b: array[5, uint32]
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


def test_static_format_action():
    class WrappedInt(Formatted):
        def __init__(self, wrapped: int):
            self._wrapped = wrapped

        def __index__(self) -> int:
            return self._wrapped

        def __eq__(self, other):
            if isinstance(other, type(self)):
                return self._wrapped == other._wrapped
            return NotImplemented

    class StaticAction(Structured):
        a: array[3, WrappedInt[int8]]

    target_obj = StaticAction(list(map(WrappedInt[int8], (1 ,2, 3))))

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


def test_static_structured():
    class Compound(Structured):
        a: array[3, Item]

    target_obj = Compound([Item(1, 11), Item(2, 22), Item(3, 33)])
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


def test_static_checked_structured():
    class Compound(Structured):
        a: array[3, uint32, Item]
    target_obj = Compound([Item(1, 11), Item(2, 22), Item(3, 33)])

    with io.BytesIO() as stream:
        array_data_size = Item.serializer.size * 3
        stream.write(struct.pack('I', array_data_size))
        for item in target_obj.a:
            item.pack_write(stream)
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

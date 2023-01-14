import struct
import io
from typing import Annotated

import pytest

from structured import *

from . import standard_tests


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
    ## Array size
    with pytest.raises(ValueError):
        Header[-1]       # invalid size
    with pytest.raises(ValueError):
        Header[-1, uint32]      # invalid size
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

    standard_tests(target_obj, target_data)

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
    target_data = struct.pack('3b', 1, 2, 3)

    standard_tests(target_obj, target_data)


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

    standard_tests(target_obj, target_data)

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

    standard_tests(target_obj, target_data)

    # Incorrect array size
    target_obj.a = []
    with pytest.raises(ValueError):
        target_obj.pack()

    # Test malformed data_size
    buffer = bytearray(target_data)
    struct.pack_into('I', buffer, 0, 0)
    with pytest.raises(ValueError):
        Compound.create_unpack_from(buffer)


def test_dynamic_format():
    class Compound(Structured):
        a: array[Header[uint32], int8]
    assert isinstance(Compound.serializer, DynamicStructArraySerializer)
    target_obj = Compound([1, 2, 3])
    target_data = struct.pack('I3b', 3, 1, 2, 3)

    standard_tests(target_obj, target_data)


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

    standard_tests(target_obj, target_data)


def test_dynamic_checked_structured(items: list[Item]):
    class Compound(Structured):
        b: uint32
        a: array[Header[uint32, uint32], Item]
    assert isinstance(Compound.serializer, CompoundSerializer)
    array_serializer = Compound.serializer.serializers[1]
    assert isinstance(array_serializer, ArraySerializer)
    assert isinstance(array_serializer.header_serializer, StructSerializer)
    assert array_serializer.header_serializer.format == '2I'
    assert array_serializer.header_serializer.num_values == 2
    assert array_serializer.static_length == -1

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

    standard_tests(target_obj, target_data)

    # Test malformed data_size
    buffer = bytearray(target_data)
    struct.pack_into('3I', buffer, 0, 42, 3, 0) # write over data_size with 0
    with pytest.raises(ValueError):
        Compound.create_unpack_from(buffer)

import struct
from operator import attrgetter

import pytest

from structured import *
from structured.type_checking import Self, Generic, TypeVar, Annotated

from . import standard_tests


class TestSelf:
    def test_detection(self) -> None:
        class Base(Structured):
            a: Self

        assert isinstance(Base.serializer, SelfSerializer)

        with pytest.raises(RecursionError):
            Base.create_unpack(b'')

        class Derived(Base):
            b: int8

        assert isinstance(Derived.serializer, CompoundSerializer)
        assert isinstance(Derived.serializer.serializers[0], SelfSerializer)


        T = TypeVar('T')
        class BaseGeneric(Generic[T], Structured):
            a: T
            b: Self

        class DerivedGeneric(BaseGeneric[int8]):
            pass

        assert isinstance(DerivedGeneric.serializer, CompoundSerializer)
        assert isinstance(DerivedGeneric.serializer.serializers[1], SelfSerializer)
        assert isinstance(DerivedGeneric.serializer.serializers[0], struct.Struct)
        assert DerivedGeneric.serializer.serializers[0].format == 'b'


    def test_arrays(self) -> None:
        # Test nesting to at least 2 levels
        class Base(Structured):
            a: array[Header[uint32], Self]
            b: uint8

        level2_items = [
            Base([], 42),
        ]
        level1_items = [
            Base([], 1),
            Base([], 2),
            Base(level2_items, 3),
        ]
        level0_item = Base(level1_items, 0)

        # Level 2 data
        item_data = struct.pack('IB', 0, 42)
        # Level 1 data
        item1_data = struct.pack('IB', 0, 1)
        item2_data = struct.pack('IB', 0, 2)
        item3_data = struct.pack('I', 1) + item_data + struct.pack('B', 3)
        # Level 0 data
        container_data = struct.pack('I', 3) + item1_data + item2_data + item3_data + struct.pack('B', 0)

        standard_tests(level0_item, container_data)

        unpacked_obj = Base.create_unpack(container_data)
        assert isinstance(unpacked_obj.a[0], Base)

    def test_unions(self) -> None:
        decider = LookbackDecider(
            attrgetter('type_flag'),
            {
                0: Self,
                1: uint64,
            }
        )
        class Base(Structured):
            type_flag: uint8
            data: Annotated[Self | uint64, decider]

        nested_obj = Base(1, 42)
        # Note: not the same as pack('BQ', ...), because of padding inserted
        nested_data = struct.pack('B', 1) + struct.pack('Q', 42)
        container_obj = Base(0, nested_obj)
        container_data = struct.pack('B', 0) + nested_data
        assert container_obj.pack() == container_data
        standard_tests(container_obj, container_data)

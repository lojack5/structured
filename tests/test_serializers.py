"""Serializer tests which aren't covered by the tests of full Structured
classes"""
from typing import Union, Annotated

import pytest

from structured import *


class TestStructSerializers:
    def test_errors(self) -> None:
        # Base class invalid multipliers
        st = StructSerializer[int]('b')
        with pytest.raises(TypeError):
            st * 1.0    # type: ignore
        with pytest.raises(ValueError):
            st * -1     # type: ignore

        st2 = StructSerializer[int]('b', byte_order=ByteOrder.NETWORK)
        with pytest.raises(ValueError):
            st + st2    # type: ignore

        st3 = StructActionSerializer('b')
        with pytest.raises(TypeError):
            1 + st3     # type: ignore


    def test_add(self) -> None:
        st = StructSerializer('b')
        st2 = StructActionSerializer('b')

        # According to https://docs.python.org/3/reference/datamodel.html#object.__radd__,
        # StructActionSerializer.__radd__ should be called here, but instead
        # STructSerializer.__add__ is
        # Why??
        res = st + st2
        assert isinstance(res, StructActionSerializer)
        assert res.format == '2b'

        null = NullSerializer()
        assert st2 + null is st2


    def test_eq(self) -> None:
        # This should hit the NotImplemented case, which falls back to
        # object.__eq__, which will be False
        st1 = StructSerializer('b')
        st2 = StructActionSerializer('b')
        null = NullSerializer()
        assert st1 != null
        assert st2 != null

        assert st2 == st2
        assert st1 != st2


    def test_hash(self) -> None:
        st1 = StructSerializer('b')
        st2 = StructActionSerializer('b')
        st3 = StructActionSerializer('b', actions=(lambda x: x, ))

        d = {
            st1: 1,
            st2: 2,
            st3: 3,
        }
        assert len(d) == 3


    def test_with_byte_order(self) -> None:
        st = StructActionSerializer('b')
        st2 = st.with_byte_order(ByteOrder.NETWORK)
        assert st2.base_format == 'b'
        assert st2.byte_order == ByteOrder.NETWORK


class TestNullSerializer:
    def test_pack(self) -> None:
        null = NullSerializer()
        assert null.pack() == b''

    def test_add(self) -> None:
        # Error case is the only one not tested by other tests
        null = NullSerializer()
        with pytest.raises(TypeError):
            null + 1    # type: ignore


class TestCompoundSerializer:
    class Base1(Structured):
        # Force a compound serializer
        a: int8
        b: Annotated[Union[int8, char[1]], LookbackDecider(lambda x: 0, {0: int8})]

    def test_add(self) -> None:
        # The rest are tested by Structured class creation
        # Compound + Compound
        st = self.Base1.serializer + self.Base1.serializer
        assert isinstance(st, CompoundSerializer)
        assert len(st.serializers) == 4

        # Compound + Struct
        st2 = StructSerializer('b')
        st3 = self.Base1.serializer + st2
        assert isinstance(st3, CompoundSerializer)
        assert len(st3.serializers) == 3

        # Struct + Compound
        st4 = st2 + self.Base1.serializer
        assert isinstance(st4, CompoundSerializer)
        assert len(st4.serializers) == 2 # the nested StructSerializer is combined

        # Error cases
        with pytest.raises(TypeError):
            1 + self.Base1.serializer   # type: ignore
        with pytest.raises(TypeError):
            self.Base1.serializer + 1   # type: ignore

    def test_preprocess(self) -> None:
        # Sort of a silly test, but here it is
        preprocessed = self.Base1.serializer.preunpack(None)
        assert preprocessed is preprocessed.preunpack(None)


class TestUnionSerializer:
    def test_lookahead(self) -> None:
        serializer = LookbackDecider(lambda x: 0, {0: int8})
        assert serializer.size == 0

        with pytest.raises(TypeError):
            LookaheadDecider(1, lambda x: 0, {0: int8})


import io
import struct

import pytest

from structured import *


class TestBlob:
    def test_errors(self):
        with pytest.raises(TypeError):
            blob[1.0]
        with pytest.raises(NotImplementedError):
            blob['size']

    def test_static(self):
        assert blob[13] is char[13]

    def test_prefixed(self):
        class Base(Structured):
            a: int16
            b: blob[uint8]
            c: int32
            d: int32

        assert isinstance(Base.serializer, CompoundSerializer)
        assert tuple(Base.serializer.serializers.values()) == (
            slice(0, 1),
            slice(1, 2),
            slice(2, 4),
        )
        assert Base.attrs == ('a', 'b', 'c', 'd')
        b = Base()

        st = struct.Struct('hBs2I')
        target_data = st.pack(10, 1, b'a', 42, 11)
        assert len(target_data) == st.size

        # unpack/pack
        b.unpack(target_data)
        assert b.serializer.size == st.size
        assert b.a == 10
        assert b.b == b'a'
        assert b.c == 42
        assert b.d == 11
        test_data = b.pack()
        assert test_data == target_data

        # unpack_from/pack_into
        buffer = bytearray(target_data)
        b.a = 0
        b.unpack_from(buffer)
        assert b.a == 10
        b.pack_into(buffer)
        assert  test_data == bytes(target_data)

        # unpack_read/pack_write
        with io.BytesIO() as out:
            b.pack_write(out)
            assert out.getvalue() == target_data
        with io.BytesIO(target_data) as ins:
            b.unpack_read(ins)
            assert b.a == 10


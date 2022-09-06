import io
import struct

import pytest

from structured import *


def test_errors() -> None:
    with pytest.raises(TypeError):
        blob[1.0]

def test_static() -> None:
    assert blob[13] is char[13]

def test_prefixed() -> None:
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

    st = struct.Struct('hBs2I')

    target_obj = Base(10, b'a', 42, 11)
    target_data = st.pack(10, 1, b'a', 42, 11)

    # unpack/pack
    assert target_obj.pack() == target_data
    assert Base.create_unpack(target_data) == target_obj

    # from/into
    buffer = bytearray(st.size)
    target_obj.pack_into(buffer)
    assert target_obj.serializer.size == st.size
    assert bytes(buffer) == target_data
    assert Base.create_unpack_from(buffer) == target_obj

    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert target_obj.serializer.size == st.size
        assert stream.getvalue() == target_data
        stream.seek(0)
        assert Base.create_unpack_read(stream) == target_obj

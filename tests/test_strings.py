import io
import struct

import pytest

from structured import *


def test_errors() -> None:
    with pytest.raises(TypeError):
        unicode[int8]
    with pytest.raises(TypeError):
        unicode[5, uint32]
    with pytest.raises(TypeError):
        char[1.0]


class TesteChar:
    def test_static(self) -> None:
        assert issubclass(char[13], structured.format_type) # type: ignore
        assert char[13].format == '13s'

    def test_dynamic(self) -> None:
        class Base(Structured):
            a: int16
            b: char[uint8]
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


class TestUnicode:
    def test_default(self) -> None:
        target_str = '你好'
        target_data = target_str.encode('utf8')
        target_len = len(target_data)

        class Base(Structured):
            a: unicode[target_len]
        target_obj = Base(target_str)

        # pack/unpack
        assert target_obj.pack() == target_data
        assert Base.create_unpack(target_data) == target_obj

        # from/into
        buffer = bytearray(target_len)
        target_obj.pack_into(buffer)
        assert target_obj.serializer.size == target_len
        assert bytes(buffer) == target_data
        assert Base.create_unpack_from(buffer) == target_obj

        # read/write
        with io.BytesIO() as stream:
            target_obj.pack_write(stream)
            assert stream.getvalue() == target_data
            assert target_obj.serializer.size == target_len
            stream.seek(0)
            assert Base.create_unpack_read(stream) == target_obj


    def test_custom(self) -> None:
        class Custom(EncoderDecoder):
            @classmethod
            def encode(cls, strng: str) -> bytes:
                return b'Hello!'

            @classmethod
            def decode(cls, byts: bytes) -> str:
                return 'banana'

        class Base(Structured):
            a: unicode[6, Custom]
        target_obj = Base('banana')
        target_data = b'Hello!'
        size = 6

        # pack/unpack
        assert target_obj.pack() == target_data
        test = Base.create_unpack(target_data)
        assert isinstance(test.a, str)
        assert test == target_obj
        assert test.serializer.size == size
        assert Base.create_unpack(b'123456') == target_obj

        # from/into
        buffer = bytearray(size)
        target_obj.pack_into(buffer)
        assert target_obj.serializer.size == size
        assert bytes(buffer) == target_data
        assert Base.create_unpack_from(buffer) == target_obj

        # read/write
        with io.BytesIO() as stream:
            target_obj.pack_write(stream)
            assert stream.getvalue() == target_data
            stream.seek(0)
            assert Base.create_unpack_read(stream) == target_obj


    def test_dynamic(self) -> None:
        target_str = '你好'
        target_bytes = target_str.encode()
        target_len = len(target_bytes)
        st = struct.Struct(f'I{target_len}s')
        target_data = st.pack(target_len, target_bytes)

        class Base(Structured):
            a: unicode[uint32]
        target_obj = Base(target_str)

        # pack/unpack
        assert target_obj.pack() == target_data
        assert Base.create_unpack(target_data) == target_obj

        # from/into
        buffer = bytearray(st.size)
        target_obj.pack_into(buffer)
        assert bytes(buffer) == target_data
        assert target_obj.serializer.size == st.size
        assert Base.create_unpack_from(buffer) == target_obj

        # read/write
        with io.BytesIO() as stream:
            target_obj.pack_write(stream)
            assert stream.getvalue() == target_data
            assert target_obj.serializer.size == st.size
            stream.seek(0)
            assert Base.create_unpack_read(stream) == target_obj

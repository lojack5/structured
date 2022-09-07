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
        assert issubclass(char[13], char)
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


    def test_net_errors(self) -> None:
        class Base(Structured):
            a: char[NET]
        error_length = 0x8000

        error_str = b'a' * error_length
        error_obj = Base(error_str)
        error_data = struct.pack('H', error_length)
        error_size_mark = 0x80 | error_length & 0x7F | (error_length & 0xFF80) << 1
        ## NOTE: Not sure if it's even possible to encode a length marker that
        ## would fail decoding.  Will have to dig into and reverse engineer
        ## bit manipulation to find out.
        #error_data = struct.pack('H', error_size_mark)

        with pytest.raises(ValueError):
            error_obj.pack()
        #with pytest.raises(ValueError):
        #    Base.create_unpack(error_data)


    def test_net(self) -> None:
        # NOTE: Code for encoding/decoding the string length is dubious.
        # Source is old Wrye Base code for reading/writing OMODs, but I've
        # and it seems to work properly, so these tests just exercise the
        # code lines, but don't verify their accuracy.
        class Base(Structured):
            short: char[NET]
            long: char[NET]
        assert isinstance(Base.serializer, structured.CompoundSerializer)
        assert tuple(Base.serializer.serializers.values()) == (
            slice(0, 1),
            slice(1, 2),
        )
        assert Base.attrs == ('short', 'long')
        target_obj = Base(b'Hello', b'a'*200)

        st = struct.Struct('B5s')
        partial_target = st.pack(5, b'Hello')
        partial_size = st.size
        target_size = 1 + 5 + 2 + 200

        # pack/unpack
        packed_data = target_obj.pack()
        packed_size = len(packed_data)
        assert packed_data[:partial_size] == partial_target
        assert Base.create_unpack(packed_data) == target_obj
        assert packed_size == target_size

        # from/into
        buffer = bytearray(packed_size)
        target_obj.pack_into(buffer)
        assert target_obj.serializer.size == packed_size
        assert bytes(buffer) == packed_data
        assert bytes(buffer)[:partial_size] == partial_target
        assert Base.create_unpack_from(buffer) == target_obj

        # read/write
        with io.BytesIO() as stream:
            target_obj.pack_write(stream)
            assert target_obj.serializer.size == packed_size
            assert stream.getvalue() == packed_data
            assert stream.getvalue()[:partial_size] == partial_target
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

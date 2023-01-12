import io

from structured import *


def standard_tests(target_obj: Structured, target_data: bytes):
    assert target_obj.pack() == target_data
    assert type(target_obj).create_unpack(target_data) == target_obj

    buffer = bytearray(len(target_data))
    target_obj.pack_into(buffer)
    assert bytes(buffer) == target_data
    assert type(target_obj).create_unpack_from(buffer) == target_obj

    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert stream.getvalue() == target_data
        stream.seek(0)
        assert type(target_obj).create_unpack_read(stream) == target_obj

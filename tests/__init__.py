import io

from structured import Structured, Serializer


class Final(Serializer):
    num_values = 1
    size = 0

    def get_final(self):
        return self


def standard_tests(target_obj: Structured, target_data: bytes):
    target_size = len(target_data)
    assert target_obj.pack() == target_data
    assert type(target_obj).create_unpack(target_data) == target_obj
    assert target_obj.serializer.size == target_size, f'{target_obj.serializer.size} != {target_size}'

    buffer = bytearray(len(target_data))
    target_obj.pack_into(buffer)
    assert bytes(buffer) == target_data
    assert target_obj.serializer.size == target_size
    assert type(target_obj).create_unpack_from(buffer) == target_obj
    assert target_obj.serializer.size == target_size

    with io.BytesIO() as stream:
        target_obj.pack_write(stream)
        assert target_obj.serializer.size == target_size
        assert stream.getvalue() == target_data
        stream.seek(0)
        assert type(target_obj).create_unpack_read(stream) == target_obj
        assert target_obj.serializer.size == target_size

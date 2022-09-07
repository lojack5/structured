from structured import *


def test_container() -> None:
    assert size_check.unwrap(size_check[int]) is int
    assert size_check.unwrap(size_check[(1,)]) == 1

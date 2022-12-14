from __future__ import annotations

from typing import Annotated, ClassVar, get_origin

from structured import *
from structured.base_types import requires_indexing


class A: pass


def test_eval_annotation() -> None:
    # Prior versions of the code would fail to evaluate `ClassVar[A]`
    class Base(Structured):
        a: ClassVar[A]
        b: int8


def test_for_annotated() -> None:
    """Ensure all usable types are an Annotated, with a few exceptions.

    Current exceptions are unindexed pad, char, and unicode, but those are an
    error to not index.
    """
    # Basic types
    for kind in (bool8, int8, uint8, int16, uint16, int32, uint32, int64, uint64, float16, float32, float64):
        assert get_origin(kind) is Annotated
    # Simple type: pad
    assert get_origin(pad) is not Annotated
    assert get_origin(pad[3]) is Annotated
    # Complex types: array
    assert get_origin(array) is not Annotated
    assert get_origin(array[Header[1], int8]) is Annotated
    # Complex types: char
    assert get_origin(char) is not Annotated
    assert get_origin(char[10]) is Annotated
    assert get_origin(char[uint32]) is Annotated
    # Complex types: unicode
    assert get_origin(unicode) is not Annotated
    assert issubclass(unicode, requires_indexing)
    assert get_origin(unicode[10]) is Annotated
    assert get_origin(unicode[uint32]) is Annotated


def test_alternate_syntax() -> None:
    # Test using only Annotated
    class Base(Structured):
        a: Annotated[int, int8]
        b: Annotated[bytes, char[10]]
        c: Annotated[str, unicode[15]]
        d: Annotated[list[int8], array[Header[2], int8]]
        e: Annotated[None, pad[3]]
    assert Base.attrs == ('a', 'b', 'c', 'd', )

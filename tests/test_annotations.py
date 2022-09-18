from __future__ import annotations

from typing import Annotated, ClassVar, get_origin, get_type_hints

from structured import *
from structured.basic_types import (
    unwrap_annotated, _int8, _AnnotatedTypes, _UnAnnotatedTypes,
)
from structured.base_types import format_type, requires_indexing


def test_eval_annotation() -> None:
    # Prior versions of the code would fail to evaluate `ClassVar[A]`
    class Base(Structured):
        a: ClassVar[A]
        b: int8


def test_unwrap_annotated() -> None:
    class A:
        a: int8
        b: Annotated[int, int8]
        c: int
        d: Annotated[int, 'foo']

    hints = get_type_hints(A, include_extras=True)
    assert unwrap_annotated(hints['a']) is _int8
    assert unwrap_annotated(hints['b']) is _int8
    assert unwrap_annotated(hints['c']) is int
    assert unwrap_annotated(hints['d']) is int


def test_for_annotated() -> None:
    """Ensure all usable types are an Annotated, with a few exceptions.

    Current exceptsion are unindexed pad, char, and unicode.
    """
    # Basic types
    for kind in _AnnotatedTypes:
        assert get_origin(kind) is Annotated
    for kind in _UnAnnotatedTypes:
        assert get_origin(kind) is not Annotated
        assert issubclass(kind, format_type)
    # Complex types: array
    assert get_origin(array) is not Annotated
    assert get_origin(array[Header[1], int8]) is Annotated
    # Complex types: char
    assert get_origin(char) is not Annotated
    assert issubclass(char, format_type)
    assert get_origin(char[10]) is Annotated
    assert get_origin(char[uint32]) is Annotated
    # Complex types: unicode
    assert get_origin(unicode) is not Annotated
    assert issubclass(unicode, requires_indexing)
    assert get_origin(unicode[10]) is Annotated
    assert get_origin(unicode[uint32]) is Annotated


class A: pass

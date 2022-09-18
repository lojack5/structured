from __future__ import annotations

from typing import Annotated, ClassVar, get_type_hints

from structured import *
from structured.basic_types import unwrap_annotated, _int8


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


class A: pass

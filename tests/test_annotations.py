from __future__ import annotations

from typing import ClassVar

from structured import *


def test_eval_annotation() -> None:
    # Prior versions of the code would fail to evaluate `ClassVar[A]`
    class Base(Structured):
        a: ClassVar[A]
        b: int8


class A: pass

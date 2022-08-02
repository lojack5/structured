from __future__ import annotations

from typing import ClassVar

from structured import *


class A: pass


def test_eval_annotation() -> None:
    # Prior versions of eval_annotation would fail to find A
    class Base(Structured):
        a: ClassVar[A]
        b: int8

import structured


def test_container() -> None:
    assert structured.utils.container.unwrap(1) == 1    # type: ignore

    wrapped = structured.utils.container[(1,)]           # type: ignore
    assert wrapped.unwrap(wrapped) == 1

import pytest

from noodler.history import Edit, EditHistory


def _tracked(log: list[str], name: str, *, discard: bool = False) -> Edit:
    return Edit(
        description=name,
        undo=lambda: log.append(f"undo {name}"),
        redo=lambda: log.append(f"redo {name}"),
        discard=(lambda: log.append(f"discard {name}")) if discard else None,
    )


def test_an_empty_history_has_nothing_to_undo_or_redo() -> None:
    history = EditHistory()
    assert not history.can_undo
    assert not history.can_redo
    assert history.undo() is None
    assert history.redo() is None


def test_undo_and_redo_walk_the_stack_in_order() -> None:
    log: list[str] = []
    history = EditHistory()
    history.record(_tracked(log, "first"))
    history.record(_tracked(log, "second"))

    assert history.undo().description == "second"
    assert history.undo().description == "first"
    assert not history.can_undo
    assert log == ["undo second", "undo first"]

    assert history.redo().description == "first"
    assert history.redo().description == "second"
    assert not history.can_redo
    assert log[-2:] == ["redo first", "redo second"]


def test_a_new_edit_abandons_the_redo_branch() -> None:
    log: list[str] = []
    history = EditHistory()
    history.record(_tracked(log, "first", discard=True))
    history.undo()
    assert history.can_redo

    history.record(_tracked(log, "second"))

    assert not history.can_redo
    assert "discard first" in log, "an unreachable edit must release what it held"


def test_the_history_is_bounded_and_releases_what_it_drops() -> None:
    log: list[str] = []
    history = EditHistory(limit=2)
    for name in ("a", "b", "c"):
        history.record(_tracked(log, name, discard=True))

    assert [edit.description for edit in history.done] == ["b", "c"]
    assert log == ["discard a"]


def test_a_limit_below_one_still_keeps_the_latest_edit() -> None:
    history = EditHistory(limit=0)
    history.record(Edit("only", lambda: None, lambda: None))
    assert [edit.description for edit in history.done] == ["only"]


def test_clearing_releases_both_directions() -> None:
    log: list[str] = []
    history = EditHistory()
    history.record(_tracked(log, "kept", discard=True))
    history.record(_tracked(log, "undone", discard=True))
    history.undo()

    history.clear()

    assert not history.can_undo
    assert not history.can_redo
    assert sorted(log[-2:]) == ["discard kept", "discard undone"]


def test_an_edit_without_a_discard_is_dropped_quietly() -> None:
    history = EditHistory(limit=1)
    history.record(Edit("first", lambda: None, lambda: None))
    history.record(Edit("second", lambda: None, lambda: None))
    assert [edit.description for edit in history.done] == ["second"]


def test_a_failing_undo_leaves_the_edit_off_the_stack() -> None:
    """The caller sees the error rather than a history that silently lies."""

    def explode() -> None:
        raise RuntimeError("cannot reverse")

    history = EditHistory()
    history.record(Edit("bad", explode, lambda: None))
    with pytest.raises(RuntimeError, match="cannot reverse"):
        history.undo()
    assert not history.can_undo

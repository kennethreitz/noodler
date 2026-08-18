"""Groups: modules that go around together."""

import pytest

from noodler.groups import GroupBook, GroupError, ModuleGroup


def test_a_group_is_made_over_a_selection_and_its_members_are_companions() -> None:
    book = GroupBook()
    group = book.make(["vco", "lpg", "env"])
    assert book.group_of("vco") == group and book.group_of("env") == group
    assert book.companions("vco") == {"lpg", "env"}
    assert book.companions("nobody") == set()
    assert book.get(group).name == "GROUP 1"


def test_fewer_than_two_things_is_not_a_group() -> None:
    book = GroupBook()
    with pytest.raises(GroupError):
        book.make(["vco"])
    with pytest.raises(GroupError):
        book.make([])
    group = book.make(["vco", "lpg"])
    with pytest.raises(GroupError, match="already"):
        book.make(["vco", "lpg"])
    assert book.group_of("vco") == group


def test_grouping_over_a_group_nests_it_whole() -> None:
    book = GroupBook()
    voice = book.make(["vco", "lpg"], name="VOICE")
    outer = book.make(["vco", "clock"])
    assert book.get(outer).groups == [voice]
    assert book.get(outer).members == ["clock"]
    assert book.parent_of(voice) == outer and book.root_of(voice) == outer
    assert book.lineage(voice) == [voice, outer]
    assert book.modules_in(outer) == {"vco", "lpg", "clock"}
    assert book.groups_in(outer) == {outer, voice}
    # Companions follow the innermost group: the lpg goes with the vco, the
    # clock goes with the whole board.
    assert book.companions("vco") == {"lpg"}
    assert book.companions("clock") == {"vco", "lpg"}
    assert book.top_level() == [outer]


def test_dissolving_an_inner_group_hands_its_members_up() -> None:
    book = GroupBook()
    voice = book.make(["vco", "lpg"])
    outer = book.make(["vco", "clock"])
    book.dissolve(voice)
    assert voice not in book
    assert set(book.get(outer).members) == {"clock", "vco", "lpg"}
    assert book.get(outer).groups == []
    book.dissolve(outer)
    assert len(book) == 0 and book.group_of("vco") is None


def test_releasing_a_module_leaves_no_group_of_one() -> None:
    book = GroupBook()
    group = book.make(["vco", "lpg", "env"])
    assert book.release("env") == group
    assert book.get(group).members == ["vco", "lpg"]
    assert book.release("lpg") == group
    assert group not in book, "one thing is not a group"
    assert book.release("vco") is None
    # A removed module is forgotten the same way.
    again = book.make(["a", "b"])
    book.forget("a")
    assert again not in book


def test_a_book_reads_back_from_saved_groups_and_keeps_counting_after_them() -> None:
    saved = [ModuleGroup("group_3", "PADS", ["a", "b"], []), ModuleGroup("group_1", "ALL", ["c"], ["group_3"])]
    book = GroupBook(saved)
    assert book.parent_of("group_3") == "group_1"
    assert book.companions("a") == {"b"}
    assert book.companions("c") == {"a", "b"}
    new = book.make(["x", "y"])
    assert new == "group_4"
    book.rename(new, "DRUMS")
    assert book.get(new).name == "DRUMS"
    book.clear()
    assert len(book) == 0

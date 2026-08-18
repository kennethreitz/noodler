"""Reversible rack edits.

Patching is exploratory: a cable is pulled to hear what happens, a module is
removed to make room, and either may turn out to be wrong a second later. One
keypress can now take a module and every cable attached to it, so the rack
needs a way back.

An edit is stored as the pair of callables that perform it in each direction,
rather than as a snapshot of the whole patch. Snapshots would have to rebuild
the interface from scratch on every undo, discarding module panels that were
never touched; inverse operations only disturb what actually changed, which is
also what makes an undo read as *that* edit being lifted rather than the patch
being replaced.

Nothing here knows about Dear PyGui or the patch graph — an edit is described
by whoever records it.
"""

from collections.abc import Callable
from dataclasses import dataclass, field


DEFAULT_HISTORY_LIMIT = 64


@dataclass(frozen=True, slots=True)
class Edit:
    """One reversible change, described in the instrument's own words."""

    description: str
    undo: Callable[[], None]
    redo: Callable[[], None]
    discard: Callable[[], None] | None = None
    """Release anything the edit was holding on to, once it can never run again."""


@dataclass(slots=True)
class EditHistory:
    """A bounded undo and redo stack over reversible rack edits."""

    limit: int = DEFAULT_HISTORY_LIMIT
    done: list[Edit] = field(default_factory=list)
    undone: list[Edit] = field(default_factory=list)

    @property
    def can_undo(self) -> bool:
        return bool(self.done)

    @property
    def can_redo(self) -> bool:
        return bool(self.undone)

    def record(self, edit: Edit) -> None:
        """Add a freshly performed edit, invalidating anything undone before it.

        A new edit makes the redo branch unreachable, which is the moment its
        retained resources can be released.
        """
        self._discard_all(self.undone)
        self.done.append(edit)
        while len(self.done) > max(1, self.limit):
            self._discard(self.done.pop(0))

    def undo(self) -> Edit | None:
        """Reverse the most recent edit and make it available to redo."""
        if not self.done:
            return None
        edit = self.done.pop()
        edit.undo()
        self.undone.append(edit)
        return edit

    def redo(self) -> Edit | None:
        """Perform the most recently undone edit again."""
        if not self.undone:
            return None
        edit = self.undone.pop()
        edit.redo()
        self.done.append(edit)
        return edit

    def clear(self) -> None:
        """Forget every edit, releasing whatever they were holding."""
        self._discard_all(self.done)
        self._discard_all(self.undone)

    @staticmethod
    def _discard(edit: Edit) -> None:
        if edit.discard is not None:
            edit.discard()

    @classmethod
    def _discard_all(cls, edits: list[Edit]) -> None:
        for edit in edits:
            cls._discard(edit)
        edits.clear()


__all__ = ["DEFAULT_HISTORY_LIMIT", "Edit", "EditHistory"]

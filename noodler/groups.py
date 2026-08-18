"""Groups: modules that go around together.

A group is a name over some modules, and possibly over other groups, the way
a board on Muse holds cards and other boards. It is logical only: it owns
nothing, it changes no signal, it is not a container anything has to be
dragged into. What it does is move as one -- drag a member and the group it
belongs to comes along -- and hold still: a group can be dissolved, and a
module can be taken out of one, but a module in a group is never left behind.

This module is the model: who is in what, and what to do to it. Nothing here
knows about the rack's panels or the screen; that is the application's part.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator


class GroupError(ValueError):
    """A grouping that cannot be made."""


@dataclass
class ModuleGroup:
    """A name over some modules and some groups."""

    group_id: str
    name: str
    members: list[str] = field(default_factory=list)
    """Module instance ids directly in this group."""
    groups: list[str] = field(default_factory=list)
    """Group ids directly in this group."""


class GroupBook:
    """Every group in one rack, and how they nest.

    A module is directly in at most one group; a group is directly in at most
    one group. Both may be in none, which is the top level.
    """

    def __init__(self, groups: Iterable[ModuleGroup] = ()) -> None:
        self.groups: dict[str, ModuleGroup] = {}
        self._counter = 0
        for group in groups:
            self.groups[group.group_id] = ModuleGroup(
                group.group_id, group.name, list(group.members), list(group.groups)
            )
            digits = "".join(ch for ch in group.group_id if ch.isdigit())
            if digits:
                self._counter = max(self._counter, int(digits))

    # ---- reading ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self.groups)

    def __iter__(self) -> Iterator[ModuleGroup]:
        return iter(self.groups.values())

    def __contains__(self, group_id: object) -> bool:
        return group_id in self.groups

    def get(self, group_id: str) -> ModuleGroup | None:
        return self.groups.get(group_id)

    def group_of(self, instance_id: str) -> str | None:
        """The group a module is directly in, or None at the top level."""
        for group in self.groups.values():
            if instance_id in group.members:
                return group.group_id
        return None

    def parent_of(self, group_id: str) -> str | None:
        """The group a group is directly in, or None at the top level."""
        for group in self.groups.values():
            if group_id in group.groups:
                return group.group_id
        return None

    def root_of(self, group_id: str) -> str:
        """The outermost group a group is in -- itself, if it is at the top."""
        current = group_id
        seen = {current}
        while True:
            parent = self.parent_of(current)
            if parent is None or parent in seen:
                return current
            seen.add(parent)
            current = parent

    def lineage(self, group_id: str) -> list[str]:
        """The group and every group it is in, innermost first."""
        line = [group_id]
        current = group_id
        while True:
            parent = self.parent_of(current)
            if parent is None or parent in line:
                return line
            line.append(parent)
            current = parent

    def modules_in(self, group_id: str) -> set[str]:
        """Every module in a group, at any depth."""
        modules: set[str] = set()
        pending = [group_id]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            group = self.groups.get(current)
            if group is None:
                continue
            modules.update(group.members)
            pending.extend(group.groups)
        return modules

    def groups_in(self, group_id: str) -> set[str]:
        """Every group inside a group, at any depth, itself included."""
        inside: set[str] = set()
        pending = [group_id]
        while pending:
            current = pending.pop()
            if current in inside:
                continue
            inside.add(current)
            group = self.groups.get(current)
            if group is not None:
                pending.extend(group.groups)
        return inside

    def companions(self, instance_id: str) -> set[str]:
        """The modules that move with one: everything in its innermost group,
        at any depth, itself aside. Empty for a module in no group."""
        group_id = self.group_of(instance_id)
        if group_id is None:
            return set()
        return self.modules_in(group_id) - {instance_id}

    def top_level(self) -> list[str]:
        """The groups in no other group."""
        return [g.group_id for g in self.groups.values() if self.parent_of(g.group_id) is None]

    # ---- changing --------------------------------------------------------

    def _next_id(self) -> str:
        while True:
            self._counter += 1
            candidate = f"group_{self._counter}"
            if candidate not in self.groups:
                return candidate

    def make(self, selection: Iterable[str], name: str | None = None) -> str:
        """Group a selection of modules; return the new group's id.

        A selected module already in a group brings its outermost group in
        whole -- a board goes on a board -- so a group is never split by
        grouping over it. Fewer than two things to group is an error, and so
        is a selection that is exactly one existing group.
        """
        wanted = list(dict.fromkeys(selection))
        if not wanted:
            raise GroupError("nothing selected to group")
        members: list[str] = []
        children: list[str] = []
        for instance_id in wanted:
            group_id = self.group_of(instance_id)
            if group_id is None:
                if instance_id not in members:
                    members.append(instance_id)
                continue
            root = self.root_of(group_id)
            if root not in children:
                children.append(root)
        if len(members) + len(children) < 2:
            if children and not members:
                raise GroupError("that is already a group")
            raise GroupError("a group needs at least two things in it")
        group_id = self._next_id()
        self.groups[group_id] = ModuleGroup(
            group_id, name or f"GROUP {self._counter}", members, children
        )
        return group_id

    def dissolve(self, group_id: str) -> None:
        """Take a group away; what was in it goes to whatever it was in."""
        group = self.groups.pop(group_id, None)
        if group is None:
            return
        parent_id = self.parent_of(group_id)
        parent = self.groups.get(parent_id) if parent_id is not None else None
        if parent is not None:
            parent.groups.remove(group_id)
            for member in group.members:
                if member not in parent.members:
                    parent.members.append(member)
            for child in group.groups:
                if child not in parent.groups:
                    parent.groups.append(child)

    def release(self, instance_id: str) -> str | None:
        """Take one module out of its group; return the group it left.

        A group left with fewer than two things in it is dissolved: one
        thing is not a group.
        """
        group_id = self.group_of(instance_id)
        if group_id is None:
            return None
        group = self.groups[group_id]
        group.members.remove(instance_id)
        if len(group.members) + len(group.groups) < 2:
            self.dissolve(group_id)
        return group_id

    def forget(self, instance_id: str) -> None:
        """A module is gone from the rack: it is gone from its group too."""
        self.release(instance_id)

    def rename(self, group_id: str, name: str) -> None:
        group = self.groups.get(group_id)
        if group is not None:
            group.name = name

    def clear(self) -> None:
        self.groups.clear()
        self._counter = 0


__all__ = ["GroupBook", "GroupError", "ModuleGroup"]

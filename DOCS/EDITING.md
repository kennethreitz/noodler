# Editing the rack

**Status:** Adopted, 2026-08-18

Patching is exploratory. A cable is pulled to hear what happens, a module is
removed to make room, and either may turn out to be wrong a second later. This
document covers the keys that edit a rack and the history that makes those
edits safe to try.

## The keyboard

For most of its life the rack advertised `SELECT CABLE + DELETE TO UNPATCH`
while `app.py` registered no key handlers at all — only mouse ones. The
instrument was telling the user to press a key that did nothing.

| key | action |
| --- | --- |
| Delete / Backspace | unpatch selected cables, remove selected modules |
| ⌘Z / ⌘⇧Z | undo, redo |
| ⌘K | open the module browser |
| F | frame the whole rack |
| Escape | close the browser, or clear the selection |

Both Delete and Backspace are bound, because most Mac keyboards send Backspace
for the key labelled Delete and the forward-delete key is not present at all.
That makes the guard essential rather than defensive: `_keyboard_is_captured`
stands the rack down while the module browser or the save-patch dialog is open,
so typing a patch name costs a character rather than a module.

## Reversible edits

`noodler.history` holds a bounded undo and redo stack. An edit is stored as the
pair of callables that perform it in each direction, rather than as a snapshot
of the whole patch:

```python
_record_edit(
    f"REMOVE {name}",
    undo=lambda: _restore_module_node(runtime, registration, module, routes),
    redo=lambda: _remove_module_node(node, runtime, record=False),
    discard=lambda: _discard_retained_node(runtime, registration),
)
```

Snapshots would have to rebuild the interface on every undo, discarding module
panels that were never touched. Inverse operations only disturb what actually
changed, which is also what makes an undo read as *that edit* being lifted
rather than the patch being replaced.

Recorded today: patching a cable or an output tap, unpatching one, `UNPLUG ALL`,
adding a module, and removing one. Continuous control movements are not
recorded — a knob sweep would fill the history with hundreds of entries, and
double-clicking a control already restores its default.

### Removing a module keeps its panel

A removed module's panel is hidden, not destroyed, and the module object stays
referenced by the edit that removed it. Rebuilding a panel on undo would mean
re-deriving controls that the module's own builder made — and the eight
hand-written starter panels cannot be rebuilt by the generic path at all — so
the cheapest correct restore is the panel that was already there. The module is
the same instance, so every knob the user had set is still set.

What the registries knew about the module is captured as a `NodeRegistration`
and put back on undo: its rack node, rail and position in that rail, accent,
and patch bay. It rejoins its rail through `_place_dynamic_node` rather than
returning to a stale position, because the rack may have been panned, zoomed,
or re-flowed while it was gone.

A retained panel is destroyed only when its edit can never run again — evicted
past the history limit, or stranded on an abandoned redo branch — and only if
the module is still absent from the patch. That is what `Edit.discard` is for.

### What is not covered

Undo is per-rack: `build_ui` clears the history, because the edits describe a
rack that no longer exists. There is no persistence of history across a save
and reopen, and no coalescing of rapid edits into one entry.

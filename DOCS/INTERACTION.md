# Noodler interaction model

**Status:** Proposed, 2026-08-18

The rack does not feel loose because any one gesture is wrong. It feels loose
because no single decision governs them. Features arrived one at a time, each
reasonable, and each brought a key, a button, and a line of the status bar. The
result is an interface with several opinions about the same act.

This document is the missing decision. It is short on purpose.

## What the rack is

From the README: *legibility and touch, not an engineering debugger.* A rack is
a physical surface with things on it. That gives the whole model:

**A gesture means one thing. A thing is done one way.**

Every rule below follows from that, and everything that does not follow from it
should go.

## What is wrong today

**Three ways to pan.** Background drag, Space with movement, Space with a drag.
Each was added to work around the previous one fighting the node editor's box
selection. They now all work, which is three answers to one question.

**Two module browsers.** The empty rack shows an inline pane; the starter rack
opens a 620×700 modal. Same tag, two experiences, and code throughout that has
to ask which one it is looking at.

**Layout has no owner.** Rails snap Y, make room in X, and TIDY packs. Between
them the user gets neither freedom nor order: a module can be placed but not
kept, arranged but not trusted. This has now been through both extremes —
free placement that drifts, and packing that refuses a drag — because the
question "who owns position" was never answered.

**The status bar is a cheat sheet.** It lists eleven gestures because eleven
gestures exist. It is the symptom, not the problem.

## The model

**Position belongs to the user. Order belongs to the patch.**

- A module is where it was put. Dragging moves it; nothing moves it back.
- The rail resolves overlap and owns the lane, and nothing else.
- TIDY is the one act that rearranges, and it is always asked for.

**One gesture per intent.**

- Drag the background to pan. Space is a modifier for reaching a module that is
  under the pointer, not a second pan.
- Box selection needs a modifier because panning is the common case.
- One module browser: the pane. A modal is a second place to learn.

**Nothing is announced twice.** A gesture belongs in the status bar, a tooltip,
or a menu — not all three. The status bar should say what just happened or what
is in hand, not what is possible.

## What this costs

Removals, mostly: the modal browser, the duplicate toolbar path, one of the pan
routes, and roughly half the status bar. The parts worth keeping are the parts
that already answer to the model — module panels derived from the parameter
schema, the library pane, patch documents, undo, and the motion layer, which is
the one piece already built to a single rule.

## What this is not

Not a rewrite of the frontend. The rack, the panels, the browser, and the
persistence layer are sound. What is missing is an editor: someone to decide
which of the three pans survives, and to delete the other two.

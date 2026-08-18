# Noodler interaction model

**Status:** Adopted, 2026-08-18

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

## What was wrong

**Three ways to pan.** Background drag, Space with movement, Space with a drag.
Each was added to work around the previous one fighting the node editor's box
selection. Dragging pans, and Space is the modifier that lets the same drag
start from over a module rather than only from empty background — one gesture
and one modifier, rather than three answers to one question.

**Two module browsers.** The empty rack showed an inline pane; the starter rack
opened a 620×700 modal, under the same tag, with code throughout asking which
one it was looking at. The modal is gone. Because the library is a pane beside
the rack rather than a dialog over it, Escape has nothing to close and simply
clears the selection.

**Layout has no owner.** Rails snap Y, make room in X, and TIDY packs. Between
them the user gets neither freedom nor order: a module can be placed but not
kept, arranged but not trusted. This has now been through both extremes —
free placement that drifts, and packing that refuses a drag — because the
question "who owns position" was never answered.

**The status bar was a cheat sheet.** It listed eleven gestures because eleven
gestures existed, and ran off the edge of the window. Actions and the keys that
reach them now live in the View and Edit menus, where they can be read on
purpose; the status line is for what just happened.

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

## Where the rack starts

Start-up positions were chosen before anything was laid out, against a window
whose size was not yet known, so a coordinate that fitted one machine put the
output past the edge of another. The rack is now centred on the first frame the
viewport is real — once, so it never fights the user afterwards.

The master mixer is exempt, because it is not placed at all. It is pinned to the
top-right corner and the camera does not carry it: the rack pans and zooms
underneath while it stays where it was. Where everything goes should not be
somewhere you can lose, and it was — three separate bug reports were the output
panel having been panned off the edge of the window.

## What this is not

Not a rewrite of the frontend. The rack, the panels, the browser, and the
persistence layer are sound. What is missing is an editor: someone to decide
which of the three pans survives, and to delete the other two.

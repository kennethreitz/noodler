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

## How big a knob is

Dear PyGui's knob widget is drawn at a fixed forty pixels. Its `width`, its
`height` and its font all change nothing about the picture, and asking is not
an error — the number is accepted and ignored. Four separate rounds of "the
knobs are too big" each shrank a constant that was never read.

The knob is now a drawlist: a body, a track, a value arc and a pointer, painted
at exactly the diameter it is asked for and repainted at the new one when the
rack zooms. It has no value of its own — the position lives with the gesture
state and the picture is redrawn from it — which turned out to be how the
interaction layer already treated the widget: as a value store, a picture and
a hover target. Only the picture changed.

The lesson is general enough to write down: when a fix has been applied more
than once and the complaint has not moved, the thing being changed is not the
thing being seen. Measure the screen before adjusting the number.

## Where the rack starts

Start-up positions were chosen before anything was laid out, against a window
whose size was not yet known, so a coordinate that fitted one machine put the
output past the edge of another. The rack is now centred on the first frame the
viewport is real — once, so it never fights the user afterwards.

The console is exempt, because it is not placed at all. The master, eight
channel strips and two returns are pinned in a row along the bottom edge of the
canvas — the channels, then two effect strips that each carry their own send
jack out and return L and R in, so a send and its return are one thing on the
desk; there is no master strip, and the master's level is a dial in the status
bar and the
camera does not carry them: the rack pans and zooms underneath while they stay
where they are. Where everything goes should not be somewhere you can lose,
and it was — three separate bug reports were the output panel having been
panned off the edge of the window.

The strips live *inside* the node editor because that is the only place a
cable can land: DPG draws links between node attributes and nowhere else, so
"drop a cable on a mixer slot" is only possible if the slot is a node. Each
strip is a jack at the top centre, its number with M and S on the title row
(drawn there, over the title bar, and pressed there — a strip has no room for
them below, and a desk keeps them at the top), a level dial whose outer ring
is its meter, and pan, A and B beneath with L/R, FXA, FXB under them in a
small face — dials rather than faders, because a strip a hundred pixels tall
leaves the rack the room it needs. The console keeps its own font
and its dials their own size when the rack zooms: a fader is a fader.

The jack deserves its own paragraph, because it took three tries. Dear PyGui
draws a pin on a node's left or right edge and nowhere else. imnodes has a pin
offset, and it is set on the strips' theme — and does nothing, because pin
positions are computed after every node's styles have been popped, so only an
editor-wide offset applies, and that would drag every module's pins into their
panels. So each jack is a *post*: a separate node with an empty title and one
empty input row, themed invisible, whose left edge — where its pin is drawn —
the console settles onto the strip's middle. The post stands twenty pixels
above the strip, so its pin sits just above the top edge rather than on it:
clicking a node brings it to the front, and a pin drawn over the strip went
under the strip the moment the strip was clicked. Nothing can cover what
stands above the top edge.

Every cable is drawn by hand. imnodes draws a link as a level bezier arriving
at an input from the left, offset by a quarter of its length: a cable dropped
from a module onto a strip below overshoots to the left and hooks back into the
jack, and one between modules lies flat, a wire in a diagram. So the editor's
own links are all made invisible and every cable is drawn on a layer over the
rack: leaving the output to the right and arriving at the input from the
left, as a plug in a jack does, and hanging between the two under its own
weight — the sag grows with the length, from a few pixels to about a hundred —
and into the console from above, with a little droop on the way. The layer
covers the window, so each cable is a polyline along its bezier clipped to the
editor's rectangle. Cables glow with the jack that feeds them; the one under
the pointer lights; a click on one picks it (Shift adds) and Delete removes
it, since the editor's own selection is of a link nobody can see; a
double-click unpatches it.

Collapsing a module — double-click its title, or right-click — leaves its
title and the jacks with cables in them, and puts everything else away: the
controls, the open jacks, the signal-path row. Opening it again shows every
control and every jack. There is no third state; a jack with nothing in it is
hidden by collapsing and shown by opening, which is what the HIDE OPEN toggle
was for, and why it is gone. The book-spine view is gone with it.

The band the console stands in is reserved. Centring, framing and revealing a
new module all reason about "the visible area", and that area is the canvas
*above* the console — otherwise a module is placed where the console is,
which puts it underneath. A hand can still drag a module under there; the
camera never will. The console is also built after a document's modules, so
at first draw it is above them rather than beneath. And there is no minimap:
it cannot leave the console out, and a fixed console shown as blocks that
slide around in it is worse than no map. F frames the rack.

## What lights up

Every output jack glows with its signal, read from the last rendered block
after the audio thread has moved on from it: an oscillator's saw is lit, a
gate blinks, a quiet output goes dim, and everything goes dark when playback
stops. A rack of a hundred jacks costs a handful of repaints a frame, because a
jack is only repainted when it changes step. The knob under the pointer
brightens; the one being turned brightens more. Each strip's ring meter is the
same peak-programme ballistics as the master's, so a channel's level and its
loudness are read in one glance at one dial.

Every cable glows with what is on it, in the same steps as the jack that feeds
it, so a signal can be followed by eye from source to console.

Right-clicking a module asks it the five things done to one: fold, duplicate
(settings and all, never cables — a copy that arrived already patched into the
same places would double every signal), reset its controls, unplug every cable
from it, remove it. Each existed as a gesture or a menu; each was one more thing
to know.

## What this is not

Not a rewrite of the frontend. The rack, the panels, the browser, and the
persistence layer are sound. What is missing is an editor: someone to decide
which of the three pans survives, and to delete the other two.


## What is selected, shown

The node editor's own selection colours were the module's own -- a selected
panel looked like an unselected one -- and its box selector took no colour
from any theme it was offered, so a shift-drag swept out an invisible
rectangle. Both are drawn now on a layer over the rack: a selected module
wears an amber outline with a soft halo, and the marquee is an amber tint
from where the shift-press began to the pointer, for as long as the button
is down. Clipped to the editor, so neither bleeds into the outline pane or
the console.

While at it: the editor reports a zero rectangle for itself, which had left
"is the pointer over empty canvas" always false, so a plain background drag
never panned and only ever box-selected, invisibly. The editor's rectangle is
now taken from its row's bottom-right corner and its own size, and the drag
pans as the table says. A drag pans only if its press armed it; the fallback
that re-decided from a recovered origin now and then turned a click on a
module into a pan, and is gone. And a press is classified once, on its first
frame: Dear PyGui repeats the mouse-down callback every frame the button is
held, and re-reading a press that began on a jack as a press on empty canvas
-- once the cable being drawn out had carried the pointer off the module --
was how dragging one thing dragged everything. The module's hit box for that
test is also its panel, not the content box the editor reports: the jacks
stand astride the panel's edge, outside the content.

## The editor's own pan

Dear PyGui's node editor pans by itself — middle-drag, or a trackpad gesture
that lands there — and that moves every node's picture without changing any
node's position, which is why the console could float away from the bottom
edge. Nothing exposes the offset, so it is measured: a strip's screen
rectangle less its grid position is the grid origin plus the pan, and the pan
is that less what it measured when nothing had been panned. The console is
pinned against it, and centring, framing and revealing subtract it too.

## Clicking a cable

A press on empty canvas — and a cable is empty canvas — used to clear the
selection at once, so a click on a cable could never leave it selected and the
double-click that unpatches it had nothing to act on. Only a press that goes
on to move is a pan now, and only then is the selection let go of.
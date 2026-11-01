---
title: Override protection
parent: Guides
nav_order: 3
permalink: /guides/overrides/
---

# Override protection
{: .no_toc }

Without override protection, a lamp you dim to read by would be set straight back to the curve
at FLARE's next update, within a minute. With it, FLARE leaves a light you've changed yourself
alone until the whole room has been dark. For how FLARE tells your changes from its own, see
[Override protection](../../reference/override-protection/#how-it-works) in the reference.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## What override protection is

FLARE sets each room's lights to the curve at every update, every minute by default. Once
you've changed a light, it's **overridden**, and FLARE's updates leave it as you set it while
the rest of the room carries on following the curve. Once every light in the room is off, FLARE
sets all of them again the next time the room comes on.

For example, you dim the reading lamp at 20:00. All evening the ceiling light keeps following
the curve, getting warmer and dimmer, while the lamp stays at your brightness. At bedtime you
switch everything off, and in the morning the lamp comes on with the rest of the room, set to
the curve.

### What counts as changing a light

Anything other than FLARE changing a light's brightness, its colour, or whether it's on:

- a wall switch or a remote,
- the Home Assistant app, or another app such as Hue or HomeKit,
- a voice assistant,
- another automation, script or scene.

Switching a light off counts too, so a lamp you've switched off stays off while the rest of the
room is lit, rather than coming back on at the next update.

A change too small to notice doesn't count, since bulbs rarely report back exactly what they
were sent. See
[how close counts as a match](../../reference/override-protection/#how-close-counts-as-a-match).

### What it doesn't do

- **It doesn't stop a room switching off when it empties.** Once every sensor has been clear for
  the Wait time, the room's lights go off, including ones you've changed.
- **It doesn't last for ever.** It ends once the room has been dark, or when you press
  **Clear**. See [how a light goes back to the curve](#back-to-the-curve).
- **It doesn't affect lights FLARE isn't running**, such as a lamp left out of the room's
  lights.

Override protection is on for every room by default. To turn it off for a room, see
[turning it off for a room](#turning-it-off-for-a-room).

## Back to the curve

An overridden light goes back to the curve when:

- **the room goes dark**: once every light FLARE is running in the room is off, the next time
  the room comes on, FLARE sets all of them again,
- **you press Clear**, under **FLARE → Settings** or for an area on the
  [dashboard](../../dashboard/), so FLARE sets those lights at its next update,
- **you run the room's automation yourself**, or turn on the room's [flare](../flares/) with no
  brightness or colour.

A restart doesn't send a light back. The
[reference](../../reference/override-protection/#back-to-the-curve) has the
details, such as what happens to a light that goes unavailable.

## Seeing what's going on

- Each light a room names has a **FLARE status** sensor on its device page, showing its status, what FLARE
  last asked it for, and what doesn't match.
- The dashboard's **Overrides** view lists every area's lights with the same details, and a
  **Clear** for each light.
- FLARE's **Activity** shows when a room starts controlling its lights, when it lets them go,
  and when a light is overridden.

[Override protection](../../reference/override-protection/) in the reference lists the
entities, events and options.

## Turning it off for a room

If a room's bulbs report something other than what they show, they'll keep being overridden.
If you turn off **Override Protection** in that room's automation, no light there is ever
overridden: every update sets any light that isn't showing the curve.

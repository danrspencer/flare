---
title: Override protection explained
parent: Guides
nav_order: 3
permalink: /guides/overrides/
---

# Override protection explained
{: .no_toc }

FLARE leaves a light alone once you've changed it yourself, until the whole room has been dark.
This page explains what that means for your lights, then how it works.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## What override protection is

FLARE sets each room's lights to the curve at every update, every minute by default. If that
were all it did, then whenever you changed a light, say dimming a lamp to read by, the next
update would set it straight back to the curve, within a minute.

Override protection stops that. Once you've changed a light, it's **overridden**, and FLARE's
updates leave it as you set it. The rest of the room carries on following the curve. Once
every light in the room is off, FLARE sets all of them again the next time the room comes on.

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
were sent. See [how close counts as a match](#claims).

### What it doesn't do

- **It doesn't stop a room switching off when it empties.** Once every sensor has been clear for
  the Wait time, the room's lights go off, including ones you've changed.
- **It doesn't last for ever.** It ends once the room has been dark, or when you press
  **Clear**. See [how a light goes back to the curve](#how-a-light-goes-back-to-the-curve).
- **It doesn't affect lights FLARE isn't running**, such as a lamp left out of the room's
  lights.

Override protection is on for every room by default. To turn it off for a room, see
[turning it off for a room](#turning-it-off-for-a-room).

## How it works

FLARE tells a light you've changed from one it set by keeping a record of what it last asked
each light for, and comparing the light with it.

### Claims

Each time FLARE sets a light, it records a **claim** for the light: what it asked the light
for. On every update, FLARE compares each light with its claim, and that comparison gives the
light a status:

| The light | Status | What FLARE's updates do |
|---|---|---|
| Matches its claim | `controlled` | Keep setting it to the curve. |
| Has stopped matching its claim, for less than 30 seconds | `mismatched` | Leave it alone for now. |
| Hasn't matched its claim for 30 seconds | `overridden` | Leave it alone. |
| Has no claim | `untracked` | Set it, which gives it a claim. |

"Matches" means close enough to notice no difference: within 5% of the brightness and 5
mireds of the colour temperature by default, since bulbs rarely report back exactly what they
were sent. You can change both under
[**FLARE → Settings → Configure**](../../reference/override-protection/#how-close-counts-as-a-match).

The 30 seconds give a slow bulb time to report back, so a light that's only catching up isn't
counted as overridden.

### Example: dimming a lamp yourself

The living room has a ceiling light and a lamp, and someone's in the room.

| Time | What happens | The lamp's claim | The lamp | Status |
|---|---|---|---|---|
| 19:00 | FLARE sets the room | on, 180, 3000 K | on, 180, 3000 K | `controlled` |
| 19:20 | You dim the lamp in the Home app | on, 180, 3000 K | on, 60, 3000 K | `mismatched` |
| 19:20:30 | | on, 180, 3000 K | on, 60, 3000 K | `overridden` |
| 19:21 | FLARE's next update | on, 180, 3000 K | on, 60, 3000 K | `overridden` |
| 23:00 | You switch both lights off | deleted | off | `off` |
| 07:00 | Motion in the morning | on, 255, 6667 K | on, 255, 6667 K | `controlled` |

From 19:21 the update keeps setting the ceiling light to the curve, but leaves the lamp out,
because it's overridden. So the lamp stays at 60 all evening.

At 23:00 none of the room's lights is on, so the room deletes their claims (see
[how a light goes back to the curve](#how-a-light-goes-back-to-the-curve)). In the morning the
lamp has no claim, so it's `untracked`, and the update sets it with the rest of the room.

### Example: switching a lamp off yourself

Switching a light off counts as changing it, the same as dimming it. With the same room:

| Time | What happens | The lamp's claim | The lamp | Status |
|---|---|---|---|---|
| 19:00 | FLARE sets the room | on, 180, 3000 K | on, 180, 3000 K | `controlled` |
| 20:00 | You switch the lamp off | on, 180, 3000 K | off | `mismatched` |
| 20:00:30 | | on, 180, 3000 K | off | `overridden` |
| 20:01 | FLARE's next update | on, 180, 3000 K | off | `overridden` |

The ceiling light is still on, so the room keeps its claims, and every update leaves the lamp
off. Once you switch the ceiling light off too, the room deletes both claims, and both lights
come on next time.

### Lights FLARE switches off

When FLARE switches a light off itself, it sets the light's claim to off first. The light then
matches its claim, so it's `controlled` rather than overridden, and it comes on again with the
rest of the room. That happens when:

- a light's brightness level is 0, such as a light excluded in the current phase,
- a room empties and Idle Brightness leaves a nightlight on, and the room's other lights are
  switched off.

In that second case the nightlight keeps the room from going dark, so the room keeps its
claims. Because the other lights' claims say off, they come on when someone walks back in.

If your own automation switches lights off, the
[`flare.turn_off` or `light.turn_off`](../../reference/services/#flareturn_off-or-lightturn_off)
comparison shows which to use.

### How a light goes back to the curve

An overridden light goes back to the curve once its claim is gone, or once FLARE sets it
regardless:

- **The room goes dark.** Once none of the room's claimed lights is on, the room deletes all
  their claims. A light that's unavailable counts as off, so one dead bulb can't hold a room's
  claims forever. A light in the room that FLARE has no claim on, such as a lamp another
  automation runs, doesn't count either way.
- **You press Clear.** **Clear** under **FLARE → Settings**, or an area's **Clear** on the
  [dashboard](../../dashboard/), deletes claims, so FLARE sets those lights at its next update.
- **You run the room's automation yourself**, or turn on the room's
  [flare](../flares/) with no brightness or colour. That sets every light, overridden ones
  included, and records new claims.
- **The light goes unavailable.** Its claim is deleted, so it's `untracked` when it comes back.

A restart doesn't send a light back: claims are kept across restarts, and a light still showing
what its claim says is still `controlled`.

When a room's lights come back online together, such as when they're switched on at the wall,
FLARE waits a few seconds before setting them. A bulb starts up at whatever it powers up as and
misses a command sent while it boots, which would leave it not matching its claim.

### Two claims, not one

Each light actually has two claims: the last thing FLARE sent it, and the last thing FLARE saw it
show. A light matching either one is `controlled`. So if a command never reaches a bulb, such as
a dropped Zigbee message, the bulb still matches the older claim and isn't counted as
overridden. FLARE sends the command again at its next update.

### Rooms

Claims belong to the lights, not to any one automation, so two automations setting the same
light don't count each other's changes as overrides. Each room automation names its lights,
and that's what decides which claims are deleted together when the room goes dark. If a light
is in two rooms, its claim is deleted when either room goes dark.

## Seeing what's going on

- Each light a room names has a **FLARE status** sensor on its device page, showing its status, what its
  claim asked for, and what doesn't match.
- The dashboard's **Overrides** view lists every area's lights with the same details, and a
  **Clear** for each light.
- FLARE's **Activity** shows when a room starts controlling its lights, when it lets them go,
  and when a light is overridden.

[Override protection](../../reference/override-protection/) in the reference lists the
entities, events and options.

## Turning it off for a room

If a room's bulbs report something other than what they show, they'll keep being overridden.
Turn off **Override Protection** in that room's automation and FLARE records no claims for it,
so no light there is ever overridden: every update sets any light that isn't showing the curve.

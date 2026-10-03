---
title: Voice assistants and HomeKit
parent: Guides
nav_order: 4
permalink: /guides/flares/
---

# Voice assistants and HomeKit
{: .no_toc }

A flare is a light for a whole room. Turning it on runs the room's automation, so "Hey Siri,
turn on the kitchen" brings the kitchen up the way FLARE would have, at the curve's brightness
and colour, rather than at whatever the bulbs last had.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Adding a flare for a room

Go to **Settings → Devices & Services → FLARE → Flares → Add flare** and choose **A room
automation from the FLARE blueprint**. Pick the room's automation, and FLARE fills in the
rest:

- **Name** starts as the automation's name, and becomes the light's name, so pick what you'd
  say out loud: "Kitchen", not "Kitchen lighting".
- **Area** starts as the automation's area, if it has one. Voice assistants and HomeKit use
  the area to know which room the light is in.
- **Turn off with** is `flare.turn_off`, which is what you want unless you know otherwise.

The flare appears as `light.<name>_flare`, and always has the same lights as the room's
automation. If you add a bulb to the room's area, it joins the flare too.

## Using it from a voice assistant or HomeKit

Expose the flare instead of the room's bulbs. With the HomeKit Bridge, add it to the bridge's
entities. With Alexa or Google Assistant, expose it under **Settings → Voice assistants**.

What each command does:

| You say or tap | What happens |
|---|---|
| "Turn on the kitchen" | The room's automation runs, and the room comes on the way it normally would. |
| "Set the kitchen to 30%" | Every light in the room goes to 30%. FLARE leaves them there until the room is empty and dark. |
| "Turn on the kitchen" again | The room goes back to FLARE: the automation runs, and every light returns to the curve. |
| "Turn off the kitchen" | Every light in the room turns off. |

## Why did the room go dim, or turn off again?

Turning a flare on runs the room's automation, so the room's own rules still apply. If the
room's occupancy sensors haven't detected anyone for its **Wait time**, a room with an
[idle brightness](../../reference/blueprint/#idle-brightness) comes on at the idle level
rather than the curve. A room without one comes on at the curve, but the next regular update
turns it off again, as it would any light left on in an empty room. Motion in the room brings
it up as usual.

## A flare for your own automation

Any automation can have a flare. Choose **Another automation** when adding one:

- If the automation is built from a blueprint, pick the input that holds its lights and, if
  it has one, the input that holds its FLARE zone.
- If it isn't, pick its lights directly.

Turning the flare on runs that automation. The other commands work the same as above. The
[Flares reference](../../reference/flares/) lists every setting.

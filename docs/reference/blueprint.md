---
title: Blueprint
parent: Reference
nav_order: 1
permalink: /reference/blueprint/
redirect_from: /blueprint/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja,
# which shares Liquid's {{ }} delimiters. With Liquid on, those
# examples render as empty strings and nothing errors. That also
# means no relative_url filter here - links are plain relative
# paths, which need no baseurl to be right.
---

# Blueprint
{: .no_toc }

The blueprint is the automation each room runs. This page covers every input and how a room
behaves.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

## Room

| Input | Default | Description |
|---|---|---|
| **Schedule** | required | The FLARE schedule the room follows. |
| **Lights & Occupancy** | required | The room's lights, and the occupancy and motion sensors that turn them on and off. An illuminance sensor picked here, or in its area, drives **Lux Threshold**. |

**Lights & Occupancy** takes an area, a floor, a device, a label, or individual entities. An
area includes lights and sensors added to it later.

FLARE picks the room's lights the same way Home Assistant does when you call `light.turn_on`
on that target:

- A light you pick by name is always included.
- A hidden light is left out if it was picked through an area, floor, device or label.
- A configuration or diagnostic light, such as the indicator light on a wall switch, is left out
  if it was picked through an area, floor or device, or a label on its device or area. If the
  label is on the light itself, it's included.

The room's [flare](../flares/) controls the same lights.

Sensors are `binary_sensor` entities with `device_class: occupancy` or `device_class: motion`;
other binary sensors in the target are ignored. A room can mix both kinds.

To pick an area for its lights but leave some of its sensors out, add them with **Exclude
target** (Home Assistant 2026.11 and later). On earlier versions, turn off
[Sensors From Areas](#sensors-from-areas) and pick the sensors you want by name.

A room with no sensor follows the schedule but never turns its lights on or off.

A room can have two automations, for example one for a lamp and one for the ceiling light.
Each releases the lights it drives once they're all off; a light in both is released when
either room goes dark.

## Sensors and triggers

| Input | Default | Description |
|---|---|---|
| **Wait time** | 120s | How long every sensor must be clear before the room is empty. Only used when the room has sensors. |
| **Lux Threshold** | 0 (off) | Above 0, the room leaves its lights off while every illuminance sensor in it reads above this many lux. |
| **Additional Triggers** | none | Entities that make the room update as soon as they change. |

### Lux Threshold

Illuminance sensors are the `sensor` entities with `device_class: illuminance` in **Lights &
Occupancy** — picked by name, or included through its area, floor, device or label — that
aren't excluded. With [Sensors From Areas](#sensors-from-areas) off, only the ones picked by
name count.

Above `0`, the room counts as bright enough while every one of those sensors reads above that
many lux. A bright room isn't switched on by:

- a sensor detecting someone,
- a [scene](#scenes), unless every light it covers is already on,
- [idle brightness](#idle-brightness).

If someone is still in the room when it stops being bright enough, because one of those sensors
drops to the threshold or below, the lights come on then. Someone counts as in the room if one
of its occupancy or motion sensors is detecting them, or was within the **Wait time**.

Lights already on carry on as before: following the curve, or left to the phase's scene. Nothing
is switched off for being bright. Turning the room on by hand — the automation's
**Run**, the [flare](../flares/), or a voice assistant — ignores the threshold.

A sensor that is unavailable, unknown or not numeric can't say how bright the room is, so it
doesn't count either way, and a room with no illuminance sensor never blocks. The check is off
while **Lux Threshold** is `0`, which is the default.

### Additional triggers

Add any entity a template depends on, such as the TV in a Brightness Template that dims the room
while it's playing. An additional trigger only adjusts lights that are already on. To turn a room
on from something else, see
[lighting a room from a remote](../../guides/examples/#lighting-a-room-from-a-remote).

## Brightness

| Input | Default | Description |
|---|---|---|
| **Lights Off During Morning / Day / Evening / Night** | none | Lights to turn off during that phase. |
| **Brightness Template** | none | A template returning a mapping of entity ID to brightness. Overrides the lists above for the lights it includes. |

Brightness Template values:

| Value | Effect |
|---|---|
| `1`–`255` | Sets the light to this brightness, on the same scale as the phase brightnesses. |
| `0` | Turns the light off. |
| `null` | FLARE leaves the light alone, including when the room empties, and its being on doesn't count as the room being in use. |

A single number instead of a mapping applies to every light in the room, and any light the
template doesn't include follows the schedule. See [Templates](../../guides/templates/#brightness-template).

## Idle brightness

| Input | Default | Description |
|---|---|---|
| **Morning / Day / Evening / Night Idle Brightness** | `0` | The brightness, 0–255, the room's lights dim to when it empties during that phase. `0` turns them off. |
| **Idle Brightness Template** | none | Like Brightness Template, for when the room is empty. Overrides the settings above for the lights it includes. |

For a nightlight whenever it's dark outside, leave the four settings at `0` and set the template
to:

```yaml
{{ 10 if is_state('sun.sun', 'below_horizon') else {} }}
```

An idle brightness is the only way the room's lights come on while it's empty. See
[Templates](../../guides/templates/#idle-brightness-template) for one lamp as the nightlight,
and other variations.

## Scenes

| Input | Default | Description |
|---|---|---|
| **Morning / Day / Evening / Night Scene** | none | A scene the room uses instead of the schedule during that phase. |
| **Scene Template** | none | A template returning a scene's entity ID, or `''` for none. Overrides the per-phase scenes when it returns a scene that exists. |

A scene is only used if every entity it sets is in the room; otherwise the whole room follows
the schedule. When a scene is used, any light in the room that the scene doesn't set still
follows the schedule. See [Scene handoff](../../guides/scenes/).

## Transitions

| Input | Default | Description |
|---|---|---|
| **Motion On Transition** | 1s | Transition when someone comes in, or when you run the automation by hand. |
| **Motion Off Transition** | 15s | Transition when the room empties. |
| **Background Transition** | 5s | Transition for every other update. |

## Settings

| Input | Default | Description |
|---|---|---|
| **Override Protection** | on | Leaves a light alone once something else changes it, until all of the room's lights are off. |
| **Prefer RGB During** | Evening, Night | Phases in which lights that support RGB are sent an RGB colour instead of a colour temperature. |
| **Stored Traces** | 20 | How many of the automation's recent runs keep a trace. |
| **Sensors From Areas** | on | Off, sensors aren't inferred from the areas, floors, devices or labels in **Lights & Occupancy**; only explicitly selected sensors are used. Deprecated: use **Exclude target** instead of turning this off. |

### Override protection

Turn it off for a room [whose bulbs misreport](#turning-override-protection-off).

### Prefer RGB during

Many bulbs give richer warm colours in RGB, but their cool whites can look blue, so the default
leaves Morning and Day on colour temperature.

### Stored traces

A room updates every minute, so the default keeps about the last 20 minutes of runs in the
automation's **Traces**. Raise it while you're tracking down something that happened earlier;
each trace takes memory, so set it back once you're done.

### Sensors from areas

Turn **Sensors From Areas** off and only the sensors you pick by name in **Lights & Occupancy**
count, so you can pick an area for its lights and choose the sensors yourself, such as the
hallway's for a landing. Pick none for a room that only follows the schedule.

**Sensors From Areas is deprecated, and FLARE 3.0 removes it.** From Home Assistant 2026.11,
use **Exclude target** in **Lights & Occupancy** instead of turning it off, to leave out the
sensors you don't want (see Home Assistant's
[excluding targets](https://www.home-assistant.io/docs/automation/targets/#excluding-targets)).
An excluded sensor doesn't count, whether it came from an area, a device, a floor or a label.

## How a room behaves

### When the room updates

A room updates straight away when the phase changes, a sensor detects someone or an Additional
Trigger changes, and a few seconds after its lights come back online. Between those, it updates on the
[tick](../override-protection/#when-rooms-update) of the first area in **Lights & Occupancy**,
which is every minute by default. A room whose **Lights & Occupancy** names no area updates every
minute, on the minute.

### When lights turn on and off

Lights turn on when a sensor detects someone, and turn off once every sensor in the room has
been clear for the **Wait time**.

While every light in **Lights & Occupancy** is off, the only things that turn any of them on are
a sensor detecting someone, running the automation by hand, the room getting dark while someone
is in it (with a [Lux Threshold](#lux-threshold)), and [idle brightness](#idle-brightness). Once
at least one light is on, any update can turn on the others. This means a phase change doesn't light up an empty room, and a bulb that comes back
online stays off if the rest of the room is off.

If a light is still on after the room has been empty for the **Wait time**, the turn-off is sent
again.

Running the automation by hand sets every light in the room, including ones someone else has
changed.

### Why didn't my light change?

- **Someone else changed it.** A light changed from a wall switch, an app, a voice assistant or
  another automation, including being turned off, is left alone until every light in the room is
  off. See [override protection](../override-protection/).
- **The room is empty and the light was off.** See
  [when lights turn on and off](#when-lights-turn-on-and-off).
- **It's already close enough.** Changes smaller than 5% of the brightness or 5 mireds of colour
  temperature aren't sent. You can change both tolerances under **FLARE → Settings → Configure**.
- **It's unavailable.** FLARE sets it once it comes back online.
- **A scene has it**, or **Brightness Template** returns `null` for it.
- **It's at its idle brightness.** See [idle brightness](#idle-brightness).
- **It isn't one of the room's lights.** A hidden light, or a configuration or diagnostic
  light, isn't included through an area, floor, device or label. Pick it directly in
  **Lights & Occupancy** to include it. See [Room](#room).

## Turning override protection off

Override protection works by reading back what each light reports, and checking it against what
FLARE last sent. Bulbs don't always report what they're actually showing. Some send an old value
for a moment after they reconnect, some report a colour in a different form from the one they
were sent, and some settle on a colour outside the range they say they support. When a bulb
reports something FLARE didn't send, it reads as overridden even though nobody touched it, and
FLARE leaves it alone until every light in the room is off.

If a room's lights keep getting stuck like this, you can turn off **Override Protection** in the
room's automation. FLARE then sets the room's lights on every update without checking what they report,
which also means:

- A light someone else changes, from a wall switch, an app or another automation, goes back to
  the curve at the next update.
- A light switched off by hand comes back on at the next update while the room is occupied.
- If you set the room's [flare](../flares/) to a brightness or colour, for example by asking a
  voice assistant for 100%, the room goes back to the curve at the next update. Turning the flare
  on and off works as usual.

A room with override protection off isn't counted in the [Overrides view](../../dashboard/).

If you turn override protection off because of your bulbs, please
[open an issue](https://github.com/danrspencer/flare/issues) with their make and model, so FLARE
can learn to read them properly.

## Updating the blueprint

The blueprint comes with FLARE, so after each FLARE update a repair appears under **Settings →
System → Repairs** offering the new copy. Press **Fix** to install it; your automations keep
their settings. If you've edited
your own copy, ignore the repair, because installing replaces the file.

FLARE installs the blueprint in Home Assistant's language (**Settings → System → General**) when
it has a translation for it, so far German, and in English otherwise. If you change Home
Assistant's language, the same repair offers the blueprint in the new one. Its **Details** links
lead to this page, in English.

The [test trace reports](../../trace-report/) show runs of the blueprint from its tests, with
each step matched to the line of the blueprint it comes from.

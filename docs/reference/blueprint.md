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
| **Zone** | required | The FLARE zone the room belongs to. |
| **Lights & Occupancy** | required | The room's lights, and the occupancy and motion sensors that turn them on and off. |

**Lights & Occupancy** takes an area, a floor, a device, a label, or individual entities. An
area includes lights and sensors added to it later.

Sensors are `binary_sensor` entities with `device_class: occupancy` or `device_class: motion`;
other binary sensors in the target are ignored. A room can mix both kinds.

A room with no sensor follows the schedule but never turns its lights on or off.

If a room has two automations, for example one for a lamp and one for the ceiling light, give
both the same **Zone**.

## Colour

| Input | Default | Description |
|---|---|---|
| **Prefer RGB During** | Evening, Night | Phases in which lights that support RGB are sent an RGB colour instead of a colour temperature. |

Many bulbs give richer warm colours in RGB, but their cool whites can look blue, so the default
leaves Morning and Day on colour temperature.

## Scenes

| Input | Default | Description |
|---|---|---|
| **Morning / Day / Evening / Night Scene** | none | A scene the room uses instead of the schedule during that phase. |
| **Scene Template** | none | A template returning a scene's entity ID, or `''` for none. Overrides the per-phase scenes when it returns a scene that exists. |

A scene is only used if every entity it sets is in the room; otherwise the room follows the
schedule. Lights the scene doesn't set follow the schedule. See [Scenes](../../guides/scenes/).

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
| `null` | FLARE leaves the light alone, including when the room empties. |

A single number instead of a mapping applies to every light in the room. Lights the template
doesn't include follow the schedule. See [Templates](../../guides/templates/#brightness-template).

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

## Timing

| Input | Default | Description |
|---|---|---|
| **Wait time** | 120s | How long every sensor must be clear before the room is empty. |
| **Motion On Transition** | 1s | Transition when someone comes in, or when you run the automation by hand. |
| **Motion Off Transition** | 15s | Transition when the room empties. |
| **Background Transition** | 5s | Transition for every other update. |

## Additional triggers

| Input | Default | Description |
|---|---|---|
| **Additional Triggers** | none | Entities that make the room update as soon as they change. |

Add any entity a template depends on, such as the TV in a Brightness Template that dims the room
while it's playing. An additional trigger only adjusts lights that are already on. To turn a room
on from something else, see
[lighting a room from a remote](../../guides/examples/#lighting-a-room-from-a-remote).

## How a room behaves

### When the room updates

When the phase changes, a sensor detects someone, an Additional Trigger changes, or one of its
lights comes back online. Otherwise on its zone's [tick](../zones/#when-zones-tick), every minute
by default.

The automation finds the tick through the zone's device. Home Assistant leaves hidden entities
out of a device, so hiding a zone's Tick entity stops the room updating.

### When lights turn on and off

Lights turn on when a sensor detects someone, and turn off once every sensor in the room has
been clear for the **Wait time**.

While every light in **Lights & Occupancy** is off, only a sensor detecting someone or running
the automation by hand turns any of them on. Idle brightness is the exception. While at least one
light is on, an update can turn on the others. So a phase change doesn't light an empty room,
and a bulb that comes back online stays off if the rest of the room is off.

If a light is still on after the room has been empty for the **Wait time**, the turn-off is sent
again.

Running the automation by hand sets every light in the room, including ones someone else has
changed.

### Why didn't my light change?

- **Someone else changed it.** A light changed from a wall switch, an app, a voice assistant or
  another automation, including being turned off, is left alone until every light in the room is
  off. See [override protection](../zones/#override-protection).
- **The room is empty and the light was off.** See
  [when lights turn on and off](#when-lights-turn-on-and-off).
- **It's already close enough.** Changes smaller than 5% of the brightness or 5 mireds of colour
  temperature aren't sent. Set these under **FLARE Zones → Configure**.
- **It's unavailable.** It's set when it comes back online.
- **A scene has it**, or **Brightness Template** returns `null` for it.
- **It's at its idle brightness.** See [idle brightness](#idle-brightness).

## Updating the blueprint

When a FLARE update includes a new blueprint, a repair appears under **Settings → System →
Repairs**. Press **Fix** to install it; your automations keep their settings. If you've edited
your own copy, ignore the repair, because installing replaces the file.

The [test trace reports](../../trace-report/) show runs of the blueprint from its tests, with
each step matched to the line of the blueprint it comes from.

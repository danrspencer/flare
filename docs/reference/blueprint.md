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

# The FLARE blueprint
{: .no_toc }

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

The blueprint is the automation each room runs. This page lists its inputs and describes how a
room behaves. To set one up, see the [Quickstart](../../installation/). For examples of the
template inputs, see [Templates](../../guides/templates/).

## Inputs

**Schedule**, **Zone** and **Lights & Occupancy** are required. Everything else has a default.

| Input | Default | Description |
|---|---|---|
| **Schedule** | — | The FLARE schedule the room follows. |
| **Zone** | — | The FLARE zone the room belongs to. See [setting up a room](#setting-up-a-room). |
| **Lights & Occupancy** | — | The room: its lights, and the occupancy sensors that turn them on and off. See [setting up a room](#setting-up-a-room). |
| **Additional Triggers** | none | Entities that make the room update as soon as they change. See [additional triggers](#additional-triggers). |

### Colour
{: .no_toc }

| Input | Default | Description |
|---|---|---|
| **Prefer RGB During** | Evening, Night | Phases in which lights that support RGB are sent an RGB colour instead of a colour temperature. Many bulbs give richer warm colours in RGB, but their cool whites can look blue, so the default leaves Morning and Day on colour temperature. |

### Scene Handoff
{: .no_toc }

| Input | Default | Description |
|---|---|---|
| **Scene Template** | none | A template returning a scene's entity ID, or `''` for none. Overrides the per-phase scenes when it returns a scene that exists. See [Templates](../../guides/templates/#scene-template). |
| **Morning / Day / Evening / Night Scene** | none | A scene the room uses during that phase. |

### Brightness & Exclusions
{: .no_toc }

| Input | Default | Description |
|---|---|---|
| **Brightness Template** | none | A template returning a mapping of entity ID to brightness: `1`–`255` to set that brightness, `0` to turn the light off, `null` to leave the light alone. A single number applies to every light. Overrides the lists below for the lights it names. See [Templates](../../guides/templates/#brightness-template). |
| **Lights Off During Morning / Day / Evening / Night** | none | Lights to turn off during that phase. |

### Idle Brightness
{: .no_toc }

| Input | Default | Description |
|---|---|---|
| **Idle Brightness Template** | none | Like Brightness Template, for when the room is empty. Overrides the settings below for the lights it names. See [Templates](../../guides/templates/#idle-brightness-template). |
| **Morning / Day / Evening / Night Idle Brightness** | `0` | The brightness, 0–255, the room's lights dim to when it's empty during that phase. `0` turns them off. |

### Timing
{: .no_toc }

| Input | Default | Description |
|---|---|---|
| **Wait time** | 120s | How long every occupancy sensor must be clear before the room is empty. |
| **Motion On Transition** | 1s | Transition when someone comes in, or when you run the automation by hand. |
| **Motion Off Transition** | 15s | Transition when the room empties. |
| **Background Transition** | 5s | Transition for the regular update. |

## Setting up a room

The simplest way to set up a room is to choose its area in **Lights & Occupancy**. This includes
every light and occupancy sensor in the area, and any you add to it later. To control only some
of an area's lights, choose them as entities instead. You can also choose a floor, a device or
a label.

Occupancy only counts `binary_sensor` entities with `device_class: occupancy`, so motion
sensors aren't included. To use a motion sensor, create a template occupancy sensor that
follows it, and add that:

```yaml
template:
  - binary_sensor:
      - name: "Hall occupancy"
        device_class: occupancy
        state: "{{ is_state('binary_sensor.hall_motion', 'on') }}"
```

A room with no occupancy sensor follows the schedule, but doesn't turn its lights on or off.

Rooms that need different timing, such as the bedrooms, can use a schedule of their own.

If a room has two automations, for example one for a lamp and one for the ceiling light, give
both the same **Zone**.

## When does the room update?

The room updates when the phase changes, when occupancy is detected, when an Additional Trigger
changes, and when one of its lights comes back online. It also updates on its zone's
[tick](../zones/#when-zones-tick), every minute by default.

{: .note }
> Don't hide a zone's Tick entity. The automation finds it through the zone's device, and Home
> Assistant leaves hidden entities out of a device, so the room would stop updating.

## When lights turn on and off

Lights turn on when occupancy is detected. They turn off when every occupancy sensor in the
room has been clear for the **Wait time**.

While every light in **Lights & Occupancy** is off, only two things turn any of them on:
occupancy being detected, and running the automation by hand. (An
[idle brightness](#leaving-a-room-dimly-lit) is the exception: it turns lights on at its own
level when the room is empty.) While at least one light is on, an update can turn on the
others.

So a phase change doesn't light an empty room, and a bulb that comes back online stays off if
the rest of the room is off.

## Turning lights off during a phase

Use **Lights Off During** the phase. For a dim level instead of off, a condition other than the
phase, or a light FLARE should leave alone, use **Brightness Template**; see
[Templates](../../guides/templates/#brightness-template).

## Handing a room to a scene

Assign a scene to a phase and the room uses it instead of the schedule during that phase, or use
**Scene Template** to choose a scene based on anything else. A scene is only used if every
entity it sets is in the room. See [Scenes](../../guides/scenes/).

## Leaving a room dimly lit

Set **Night Idle Brightness** to 20, for example. When the room empties during Night, its
lights dim to 20 instead of turning off, and they return to the schedule when someone comes in.
Each phase has its own setting; a phase left at `0` turns the lights off as usual.

For a nightlight whenever it's dark outside, leave the four settings at `0` and set **Idle
Brightness Template** to:

```yaml
{{ 10 if is_state('sun.sun', 'below_horizon') else {} }}
```

For one lamp as the nightlight, and other variations, see
[Idle Brightness Template](../../guides/templates/#idle-brightness-template).

## Additional triggers

The room updates as soon as an entity in **Additional Triggers** changes, instead of at its
next tick. Add any entity a template depends on, such as the TV in a template that dims the
room while it's playing.

An additional trigger only adjusts lights that are already on. To turn a room on from
something other than occupancy, see
[lighting a room from a remote](../../guides/examples/#lighting-a-room-from-a-remote).

## Why didn't my light change?

- **Someone else changed it.** A light changed from a wall switch, an app, a voice assistant or
  another automation is left alone until every light in the room is off. That includes
  turning it off. See [override protection](../zones/#override-protection).
- **The room is empty and the light was off.** See
  [when lights turn on and off](#when-lights-turn-on-and-off).
- **It's already close enough.** Changes smaller than 5% of the brightness or 5 mireds of colour
  temperature aren't sent. Set these under **FLARE Zones → Configure**.
- **It's unavailable.** FLARE skips it, and sets it when it comes back.
- **A scene has it**, or the Brightness Template returns `null` for it.
- **It's at its idle brightness.** Check the phase's
  [idle brightness](#leaving-a-room-dimly-lit).

Running the automation by hand sets every light in the room again, including ones someone else
changed.

## Updating the blueprint

When a FLARE update includes a new blueprint, a repair appears under **Settings → System →
Repairs**. Press **Fix** to install it. Your automations keep their settings. If you've edited
your own copy of the blueprint, ignore the repair, because installing replaces the file.

## Other behaviour worth knowing

**Two-step bulbs.** Some bulbs can't change brightness and colour in one command, so FLARE sends
them two. It recognises them by make and model; for one it doesn't recognise, add the label
`no_combined_transition` to the light or its device. See
[two-step bulbs](../services/#two-step-bulbs).

**Retrying turn-offs.** If the room has been empty for the **Wait time** and a light is still
on, FLARE sends the turn-off again.

**Lights that come back online.** When a light comes back online, the room updates straight
away.

## Test trace reports

The [test trace reports](../../trace-report/) show runs of the blueprint from its tests, with
each step matched to the line of the blueprint it comes from.

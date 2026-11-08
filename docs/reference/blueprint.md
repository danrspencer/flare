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

Its settings come in two groups. **Customise** holds what most rooms change: a section for each
phase, and **Custom** for anything more particular. **Fine Tuning** holds what most rooms never
touch. This page follows the same order.

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
target**.

A room with no sensor follows the schedule but never turns its lights on or off.

A room can have two automations, for example one for a lamp and one for the ceiling light.
Each releases the lights it drives once they're all off; a light in both is released when
either room goes dark.

## Phases

**Morning**, **Day**, **Evening** and **Night** each have a section with the same three
settings, which apply while the schedule is in that phase.

| Input | Default | Description |
|---|---|---|
| **Lights Off** | none | Lights in the room that stay off during the phase. |
| **Idle Brightness** | `0` | The brightness, 0–255, the room's lights dim to when it's empty, instead of switching off. `0` turns them off. |
| **Scene** | none | A scene the room uses instead of the schedule during the phase. |

### Idle brightness

An idle brightness turns a room's "off" into a dim glow: a nightlight. It only works in a room
with occupancy or motion sensors, since without them the room is never empty. It's the only way
the room's lights come on while it's empty.

For a nightlight whenever it's dark outside, leave each phase at `0` and set the
[Idle Brightness Template](#custom) to:

```yaml
{{ 10 if is_state('sun.sun', 'below_horizon') else {} }}
```

See [Templates](../../guides/templates/#idle-brightness-template) for one lamp as the nightlight,
and other variations.

### Scenes

A scene is only used if every entity it sets is in the room; otherwise the whole room follows
the schedule. When a scene is used, any light in the room that the scene doesn't set still
follows the schedule. See [Scene handoff](../../guides/scenes/).

## Custom

Templates for when per-phase settings aren't enough, like dimming the room while the TV is on.
Whenever a template returns a value, it overrides the per-phase setting.

| Input | Default | Description |
|---|---|---|
| **Brightness Template** | none | A template returning a mapping of entity ID to brightness, in place of the schedule's. When it returns a light, its value overrides **Lights Off** for that light. |
| **Idle Brightness Template** | none | Like Brightness Template, for when the room is empty. When it returns a light, its value overrides **Idle Brightness** for that light. |
| **Scene Template** | none | A template returning a scene's entity ID, or `''` for none. When it returns a scene that exists, it overrides the phase's **Scene**. |
| **Additional Triggers** | none | Triggers that make the room update as soon as they fire. |

### Brightness template

| Value | Effect |
|---|---|
| `1`–`255` | Sets the light to this brightness, on the same scale as the phase brightnesses. |
| `0` | Turns the light off. |
| `null` | FLARE leaves the light alone, including when the room empties, and its being on doesn't count as the room being in use. |

A single number instead of a mapping applies to every light in the room, and any light the
template doesn't include follows the schedule. See [Templates](../../guides/templates/#brightness-template).

### Additional triggers

Add a trigger for anything a template depends on, such as a **State** trigger on the TV for a
Brightness Template that dims the room while it's playing. They're the same triggers as an
ordinary automation's, so one can be as specific as you need: the TV changing to playing, an
attribute, a button press, a time. An additional trigger only adjusts lights that are already
on, and never switches one on. To turn a room on from something else, see
[lighting a room from a remote](../../guides/examples/#lighting-a-room-from-a-remote).

## Sensors & Conditions

| Input | Default | Description |
|---|---|---|
| **Wait Time** | 120s | How long every occupancy and motion sensor must be clear before the room is empty. |
| **Lux Threshold** | 0 (off) | Above 0, the room stays dark while every illuminance sensor in it reads above this many lux. |
| **Conditions** | none | As in an ordinary automation: all must be met for the room to run. While they aren't, the room is paused. |

### Wait time

Most occupancy and motion sensors clear the moment they stop seeing movement, even with someone
sitting still. The room counts as empty only once every one of them has been clear for the
**Wait Time**. It isn't used in a room without sensors.

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
of its occupancy or motion sensors is detecting them, or was within the **Wait Time**.

Lights already on carry on as before: following the curve, or left to the phase's scene. Nothing
is switched off for being bright. Turning the room on by hand — the automation's
**Run**, the [flare](../flares/), or a voice assistant — ignores the threshold.

A sensor that is unavailable, unknown or not numeric can't say how bright the room is, so it
doesn't count either way, and a room with no illuminance sensor never blocks. The check is off
while **Lux Threshold** is `0`, which is the default.

### Conditions

While any of the **Conditions** isn't met, the room does nothing at all: its lights stay as
they are, sensors don't turn it on or off, and the schedule isn't followed. For a vacation or
guest mode, add a **State** condition on an `input_boolean`. Once every condition is met again,
the room catches up on its next tick: lights that are on move to the schedule, and an empty
room turns off. If a condition reads an entity, add a trigger for it to
[Additional Triggers](#additional-triggers) so the room catches up as soon as it changes.

Running the automation by hand, or turning on its [flare](../flares/), still works while the
room is paused.

A room left on when the pause starts stays on until it ends. To stop only some runs, make a
condition about what started the run, with a **Triggered by** condition on one of the
[trigger IDs](#trigger-ids). For example, so a pet walking through at night doesn't light the
room, while everything else carries on (turning off, following the schedule):

```yaml
condition: not
conditions:
  - condition: and
    conditions:
      - condition: trigger
        id:
          - motion_on
          - lux_dark
      - condition: time
        after: "23:00:00"
        before: "06:00:00"
```

### Trigger IDs

Each of the room's triggers has an ID, which a **Triggered by** condition in **Conditions** can
check. Home Assistant's editor can't list a blueprint's triggers, so the condition shows a
warning and no choices: use **⋮ → Edit in YAML** and type the ID, as in the example above.

| ID | Fires when |
|---|---|
| `phase_change` | the schedule moves to another phase |
| `tick` | the room's regular update, about once a minute |
| `motion_on` | an occupancy or motion sensor detects someone |
| `motion_off` | a sensor has been clear for the **Wait Time** |
| `lux_dark` | the room stops being too bright for **Lux Threshold**, with someone there |
| `recovered` | one of the room's lights comes back online |
| `extra` | an entity in **Additional Trigger Entities** changes (deprecated) |
| your own | one of your **Additional Triggers** fires: the ID you give it, or its position if it has none |

Give each of your Additional Triggers an ID if a condition needs to tell it apart. Whatever ID
you give one, it's still an additional trigger: one named `motion_on` doesn't light the room.
Running the automation by hand has no trigger, and skips **Conditions** anyway.

## Transitions

| Input | Default | Description |
|---|---|---|
| **Turning On** | 1s | How long lights take to fade up when someone comes in, or when you run the automation by hand. |
| **Turning Off** | 15s | How long lights take to fade out once the room is empty. |
| **Everything Else** | 5s | How long every other update takes, such as the schedule moving on. |

## Other settings

| Input | Default | Description |
|---|---|---|
| **Override Protection** | on | Leaves a light alone once something else changes it, until all of the room's lights are off. |
| **Prefer RGB During** | Evening, Night | Phases in which lights that support RGB are sent an RGB colour instead of a colour temperature. |
| **Stored Traces** | 20 | How many of the automation's recent runs keep a trace. |
| **Sensors From Areas** | on | Off, sensors aren't inferred from the areas, floors, devices or labels in **Lights & Occupancy**; only explicitly selected sensors are used. Deprecated: use **Exclude target** instead of turning this off. |
| **Additional Trigger Entities** | none | Entities that make the room update as soon as they change. Deprecated: use **Additional Triggers** instead. |

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

**Sensors From Areas is deprecated, and FLARE 3.0 removes it.** It only shows in a room that
has it turned off. Use **Exclude target** in **Lights & Occupancy** instead of turning it off,
to leave out the sensors you don't want (see Home Assistant's
[excluding targets](https://www.home-assistant.io/docs/automation/targets/#excluding-targets)).
An excluded sensor doesn't count, whether it came from an area, a device, a floor or a label.

### Additional trigger entities

The list of entities **Additional Triggers** used to be: any change to one updates the room,
as a **State** trigger on it in [Additional Triggers](#additional-triggers) does.

**Additional Trigger Entities is deprecated, and FLARE 3.0 removes it.** Move each entity to
**Additional Triggers** as a **State** trigger, then clear this list.

## How a room behaves

### When the room updates

A room updates straight away when the phase changes, a sensor detects someone or an Additional
Trigger changes, and a few seconds after its lights come back online. Between those, it updates on the
[tick](../override-protection/#when-rooms-update) of the first area in **Lights & Occupancy**,
which is every minute by default. A room whose **Lights & Occupancy** names no area updates every
minute, on the minute.

### When lights turn on and off

Lights turn on when a sensor detects someone, and turn off once every sensor in the room has
been clear for the **Wait Time**.

While every light in **Lights & Occupancy** is off, the only things that turn any of them on are
a sensor detecting someone, running the automation by hand, the room getting dark while someone
is in it (with a [Lux Threshold](#lux-threshold)), and [idle brightness](#idle-brightness). Once
at least one light is on, any update can turn on the others. This means a phase change doesn't light up an empty room, and a bulb that comes back
online stays off if the rest of the room is off.

If a light is still on after the room has been empty for the **Wait Time**, the turn-off is sent
again.

Running the automation by hand sets every light in the room, including ones someone else has
changed.

### Why didn't my light change?

- **Someone else changed it.** A light changed from a wall switch, an app, a voice assistant or
  another automation, including being turned off, is left alone until every light in the room is
  off. See [override protection](../override-protection/).
- **The room's [Conditions](#conditions) aren't met**, so it's paused. Its **Traces** show the
  Conditions step that stopped it.
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

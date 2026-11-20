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

**Lights & Occupancy** takes an area, a floor, a device, a label, or individual entities. When you
target an area, floor, device, or label, lights and sensors added to it later are included
automatically.

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

A physical room can have more than one FLARE automation — for example, one for a lamp and another
for the ceiling light. Each automation releases the lights it drives once all of them are off, so
if the same light appears in both automations, its override is cleared when either automation's
lights go dark.

## Phases

**Morning**, **Day**, **Evening** and **Night** each have a section with the same three
settings, which apply while the schedule is in that phase.

| Input | Default | Description |
|---|---|---|
| **Lights Off** | none | Lights in the room that stay off during the phase. |
| **Idle Brightness** | `0` | The brightness, 0–255, the room's lights dim to when it's empty, instead of switching off. `0` turns them off. |
| **Scene** | none | A scene the room uses instead of the schedule during the phase. |

### Idle brightness

An idle brightness turns a room's "off" state into a dim glow, acting as a nightlight. It only
works in a room with occupancy or motion sensors, since a sensorless room never becomes empty.
Outside of running the automation manually, idle brightness is the only way lights come on while
the room is empty.

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
| **Idle Brightness Template** | none | Like Brightness Template, for when the room is empty (except `'x0.5'`). When it returns a light, its value overrides **Idle Brightness** for that light; `0`, `'0%'`, `null`, or `false` turns the light off when empty. |
| **Scene Template** | none | A template returning a scene's entity ID, or `''` for none. When it returns a scene that exists, it overrides the phase's **Scene**. |
| **Additional Triggers** | none | Triggers that make the room update as soon as they fire. |

### Brightness template

| Value | Effect |
|---|---|
| `1`–`255` | Sets the light to this brightness, on the same scale as the phase brightnesses. |
| `'50%'` | Sets the light to this percentage of full brightness: `'100%'` is 255, `'50%'` is 128, as for `light.turn_on`'s `brightness_pct`. |
| `'x0.5'` | Sets the light to the schedule's brightness multiplied by this, so `'x0.5'` is half of it. |
| `0`, `'0%'` or `'x0'` | Turns the light off. |
| `null` or `false` | FLARE leaves the light alone, including when the room empties, and its being on doesn't count as the room being in use. |

A single value instead of a mapping applies to every light in the room, and any light the
template doesn't include follows the schedule. **Idle Brightness Template** accepts the same
values except `'x0.5'`, and returning `0`, `'0%'`, `null`, or `false` turns the light off when
the room empties (unlike **Brightness Template**, `null` here does not leave the light alone).

The templates can read `brightness`: the schedule's brightness right now (0–255), or `none`
while the schedule is unavailable. See [Templates](../../guides/templates/#brightness-template).

### Additional triggers

Add a trigger for anything a template depends on, such as a **State** trigger on the TV for a
Brightness Template that dims the room while it's playing. These are the same triggers as an
ordinary automation's, so each trigger can be as specific as you need: the TV changing to playing,
an attribute, a button press, or a time. An additional trigger only adjusts lights that are
already on, and never switches lights on in an empty dark room. To turn a room on from
something else, see [lighting a room from a remote](../../guides/examples/#lighting-a-room-from-a-remote).

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
aren't excluded. When [Sensors From Areas](#sensors-from-areas) is off, only the sensors picked
by name count.

When **Lux Threshold** is above `0`, the room counts as bright enough while every working
illuminance sensor in it reads above the threshold. While the room is bright enough, FLARE leaves
off lights off even when:

- an occupancy or motion sensor detects someone,
- a [scene](#scenes) applies (unless every light the scene covers is already on), or
- [idle brightness](#idle-brightness) would otherwise dim the room.

If someone is still in the room when the light level drops to the threshold or below, the lights
come on right away. Someone counts as in the room if one of its occupancy or motion sensors is
detecting them, or stopped detecting them within the **Wait Time**.

Lights that are already on continue following the curve or stay in the phase's scene; FLARE never
switches lights off just because a room is bright. Turning the room on by hand — via the
automation's **Run actions**, its [flare](../flares/), or a voice assistant controlling the
flare — ignores **Lux Threshold**.

An illuminance sensor that is unavailable, unknown, or non-numeric is ignored, and a room with
no working illuminance sensors never skips turning on. The threshold check is disabled while
**Lux Threshold** is `0`, which is the default.

### Conditions

While any of the **Conditions** isn't met, the room does nothing at all: its lights stay as
they are, sensors don't turn it on or off, and the schedule isn't followed. For a vacation or
guest mode, add a **State** condition on an `input_boolean`. Once every condition is met again,
the room catches up on its next regular update: lights that are on move to the schedule, and an
empty room turns off. If a condition reads an entity, add a trigger for it to
[Additional Triggers](#additional-triggers) so the room catches up as soon as it changes.

Running the automation by hand, or turning on its [flare](../flares/), still works while the
room is paused.

A room that was already lit when the pause starts stays on until the pause ends (or you switch it
off yourself). To block only specific triggers — for example, so a pet walking through at night
doesn't switch the lights on, while turning off and following the schedule still run — add a
**Triggered by** condition checking one of the [trigger IDs](#trigger-ids):

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

Give each of your Additional Triggers an ID if a condition needs to tell them apart. Whatever ID
you give a custom trigger, it still behaves as an additional trigger — naming a trigger
`motion_on` won't make it switch the lights on. Running the automation by hand has no trigger,
and skips **Conditions** anyway.

## Transitions

| Input | Default | Description |
|---|---|---|
| **Turning On** | 1s | How long lights take to fade up when someone comes in, or when you run the automation by hand. |
| **Turning Off** | 15s | How long lights take to fade out once the room is empty. |
| **Everything Else** | 5s | How long every other update takes, such as the schedule moving on. |

## Other Settings

| Input | Default | Description |
|---|---|---|
| **Override Protection** | on | Leaves a light alone once something else changes it, until all of the room's lights are off. |
| **Prefer RGB During** | Evening, Night | Phases in which lights that support RGB are sent an RGB colour instead of a colour temperature. |
| **Stored Traces** | 20 | How many of the automation's recent runs keep a trace. |
| **Sensors From Areas** | on | When off, sensors aren't inferred from the areas, floors, devices or labels in **Lights & Occupancy**; only explicitly selected sensors are used. Deprecated: use **Exclude target** instead of turning this off. |
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

If you turn **Sensors From Areas** off, only the sensors you pick by name in **Lights &
Occupancy** count, so you can select an area for its lights while picking sensors from elsewhere
(such as the hallway's sensors for a landing). If you pick no sensors at all, the room only
follows the schedule without turning its lights on or off automatically.

**Sensors From Areas is deprecated, and FLARE 3.0 removes it.** It only shows in a room that
has it turned off. Use **Exclude target** in **Lights & Occupancy** instead of turning it off,
to leave out the sensors you don't want (see Home Assistant's
[excluding targets](https://www.home-assistant.io/docs/automation/targets/#excluding-targets)).
An excluded sensor doesn't count, whether it came from an area, a device, a floor or a label.

### Additional trigger entities

A list of entities that trigger a room update whenever any of them changes state, equivalent to
adding **State** triggers for those entities in [Additional Triggers](#additional-triggers).

**Additional Trigger Entities is deprecated, and FLARE 3.0 removes it.** Move each entity to
**Additional Triggers** as a **State** trigger, then clear this list.

## How a room behaves

### When the room updates

A room updates straight away when the phase changes, a sensor detects someone, or an Additional
Trigger fires, and 5 seconds after its lights come back online when the whole room was
unavailable. Between those events, it updates on the
[tick](../override-protection/#when-rooms-update) of the first area in **Lights & Occupancy**,
which is every minute by default. A room whose **Lights & Occupancy** names no area updates every
minute, on the minute.

### When lights turn on and off

Lights turn on when a sensor detects someone, and turn off once every sensor in the room has
been clear for the **Wait Time**.

While every light FLARE controls in **Lights & Occupancy** is off, the only things that turn any
of them on are a sensor detecting someone, running the automation by hand, the room dropping below
**Lux Threshold** while someone is in it, and [idle brightness](#idle-brightness). Once at least
one light is on, any update can turn on the others. That way, a phase change never lights up an
empty room, and a bulb that comes back online stays off if the rest of the room is off. On each
regular update or phase change while the room has been empty for the **Wait Time**, if any light
that shouldn't be idle is still on, FLARE sends the turn-off command again.

Running the automation by hand sets every light in the room, including ones someone else has
changed.

### Why didn't my light change?

- **Someone else changed it.** If a light was changed from a wall switch, an app, a voice
  assistant, or another automation (including being switched off), FLARE leaves it alone until
  every light in the room is off. See [override protection](../override-protection/).
- **The room's [Conditions](#conditions) aren't met**, so it's paused. The automation's
  **Traces** show the Conditions step that stopped it.
- **The room is empty and the light was off.** See
  [when lights turn on and off](#when-lights-turn-on-and-off).
- **The room is above [Lux Threshold](#lux-threshold)**, so off lights stay off even when motion
  is detected.
- **It's already close enough.** Changes smaller than 5% of the brightness or 5 mireds of colour
  temperature aren't sent. You can change both tolerances under **FLARE → Settings → Configure**.
- **It's unavailable.** FLARE sets it once it comes back online.
- **An active [scene](#scenes) covers it**, or **Brightness Template** returns `null` for it.
- **It's at its idle brightness.** See [idle brightness](#idle-brightness).
- **It isn't one of the room's lights.** A hidden light, or a configuration or diagnostic
  light, isn't included through an area, floor, device or label. Pick it directly in
  **Lights & Occupancy** to include it. See [Room](#room).

## Turning override protection off

Override protection works by reading back what each light reports, and checking it against what
FLARE last sent. Bulbs don't always report what they're actually showing: some send an old value
for a moment after reconnecting, some report colour in a different mode from the one they were
sent, and some settle outside the colour range they advertise. When a bulb reports values that
don't match what FLARE sent, it becomes overridden even though nobody touched it, and FLARE
leaves it alone until every light in the room is off.

If a room's lights keep getting stuck like this, first try raising the tolerances under
**FLARE → Settings → Configure** (see [how close counts as a match](../override-protection/#how-close-counts-as-a-match)).
If that doesn't help, you can turn off **Override Protection** in the room's automation. FLARE
then stops tracking overrides for that room and sets any light that isn't already close enough to
the curve on every update, which means:

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
their settings. If you've edited the blueprint file yourself, ignore the repair, because
installing replaces your changes.

FLARE installs the blueprint in Home Assistant's language (**Settings → System → General**) when
it has a translation for it (currently German), and in English otherwise. If you change Home
Assistant's language, the same repair offers the blueprint in the new language. Its **Details**
links lead to this page, in English.

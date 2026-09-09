---
title: Blueprint reference
nav_order: 5
permalink: /blueprint/
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

One automation per room, following the
[four phases of your day](../#four-phases-not-one-curve). To install it,
see the [Quickstart](../installation/); for the services underneath, the
[integration reference](../advanced/reference/).

## Inputs

Only **FLARE Sensor** is required. Everything else has a working default.

| Input | Default | What it does |
|---|---|---|
| **FLARE Sensor** | — | The schedule sensor whose brightness and colour the room follows. See [using your own sensor](#using-your-own-sensor). |
| **Lights & Occupancy** | — | One target for the room. Lights inside it are controlled; occupancy sensors inside it decide when. See [setting up a room](#setting-up-a-room). |
| **Additional Triggers** | none | Extra entities that make the room re-evaluate immediately. See [additional triggers](#additional-triggers). |

### Colour
{: .no_toc }

| Input | Default | What it does |
|---|---|---|
| **Prefer RGB During** | Evening, Night | Phases that send RGB colour rather than colour temperature, to lights that support it. Lights without RGB are unaffected. |

### Scene Handoff
{: .no_toc }

| Input | Default | What it does |
|---|---|---|
| **Scene Template** | none | Template returning a scene's entity_id. Wins over the per-phase pickers whenever it returns a valid scene. |
| **Morning / Day / Evening / Night Scene** | none | A scene to hand the room to during that phase. |

### Brightness & Exclusions
{: .no_toc }

| Input | Default | What it does |
|---|---|---|
| **Brightness Template** | none | Template mapping entity_id to a brightness, 0–255. Wins over the lists below for any light it names. |
| **Lights Off During Morning / Day / Evening / Night** | none | Lights to switch off during that phase. |

### Idle Brightness
{: .no_toc }

| Input | Default | What it does |
|---|---|---|
| **Idle Brightness Template** | none | Template mapping entity_id to a brightness, 0–255, for when the room is empty. Wins over the settings below for any light it names. |
| **Morning / Day / Evening / Night Idle Brightness** | `0` | What the room dims to during that phase instead of switching off, 0–255. `0` means it goes dark. |

### Timing
{: .no_toc }

| Input | Default | What it does |
|---|---|---|
| **Wait time** | 120s | How long after occupancy clears before the lights go off. |
| **Update Interval** | every minute | How often the room re-applies the curve. |
| **Update Jitter** | 15s | Random delay so rooms sharing a sensor don't all command at once. `0` disables it. |
| **Motion On Transition** | | How quickly lights change when someone walks in, or you run the automation by hand. |
| **Motion Off Transition** | | How quickly lights fade when the room empties. |
| **Background Transition** | | How quickly lights change on the regular update — nobody is waiting on these, so they can be slow and smooth. |

## Setting up a room

Point **FLARE Sensor** at a schedule sensor and **Lights & Occupancy**
at the room's area. That's it.

One target does both jobs: every light in that area is controlled, and
every occupancy sensor in it decides when. Lights you add to the area
later are picked up automatically. Pick individual entities instead if
you want to mix and match — your lights plus one sensor from elsewhere,
say.

Occupancy uses Home Assistant's built-in occupancy triggers, which only
count `binary_sensor` entities with `device_class: occupancy`.
Motion-class sensors are not picked up. To drive a room from one, see
[additional triggers](#additional-triggers).

{: .note }
> Lights are only found through entities, devices and areas. A floor or
> label works for occupancy but won't control any lights, so name the
> lights directly if you need one of those.

A room with no occupancy sensor works fine — it simply never switches
anything on by itself.

## When lights turn on and off

Lights come on when occupancy is detected, and go off **Wait time**
after it clears.

Three things — and only these three — may switch on a light that is off:

- occupancy being detected
- running the automation by hand
- the room already being in use, meaning one of its other lights is on

Everything else may only adjust lights that are already on. A phase
changing will never light an empty room, and a bulb that reconnects
after a power cut stays off if the rest of the room is dark.

If a room has several occupancy sensors, it only counts as empty once
**all** of them are clear.

## Turning lights off during a phase

Put them in **Lights Off During Night** (or whichever phase). That's the
whole feature for the common case.

For anything the lists can't express — a specific dim level rather than
off, or a condition unrelated to phase — use **Brightness Template**,
which maps each light to the brightness it should sit at:

| Value | Effect |
|---|---|
| `1`–`255` | That light sits at this brightness. The same scale the phase brightnesses use. |
| `0` | Turns the light off. |
| `null` or `false` | Hands the light over entirely — FLARE never touches it, on or off. |

```yaml
{% if is_state('media_player.tv', 'playing') %}
  {{ {'light.lounge_ceiling': 40, 'light.lounge_lamp': null} }}
{% else %}
  {{ {} }}
{% endif %}
```

A brightness here is **flat**. The light sits at it for as long as the
template returns it, rather than following the curve up and down — so
the lounge ceiling above stays at 40 for as long as the TV is on,
whatever time of day it is. Leave a light out of the template and it
tracks the curve as usual.

`0` and `null` are different. `0` is still FLARE's light, it just wants
it dark right now. `null` means the light belongs to something else, so
it is left out of the turn-off when the room empties too — if you want
it dark then, whatever owns it has to do that.

The template wins over the phase lists for any light it names; the
lists fill in the rest.

## Handing a room to a scene

Pick a scene in **Night Scene** (or whichever phase) and the room uses
that instead of the curve.

For cases a phase alone can't express — a different scene while the TV
is on — use **Scene Template**, which returns a scene's entity_id and
wins whenever it returns a valid one.

A scene is only used if every entity it touches is one this room
controls. A scene reaching outside the room, or one that doesn't exist,
is ignored. Scenes follow the same rule as everything else: a phase
change alone won't light an empty room, so the scene is applied when
someone next walks in.

## Leaving a room dimly lit

Set **Night Idle Brightness** to 20 (or whatever suits) and the room
brightens to the curve when you walk in, then settles back to that
instead of going dark.

It's per phase, so a hall can be a nightlight after dark and an ordinary
room during the day — leave the other three at `0` and empty still means
dark in those phases.

For naming one lamp as the nightlight while the rest of the room goes
out, use **Idle Brightness Template**, which maps each light to its own
level:

```yaml
{{ {'light.landing_lamp': 20} }}
```

The template wins over the phase setting for any light it names; the
phase setting fills in the rest.

This is the one thing that will switch a light on in an empty room, and
only for lights you've given an idle brightness. It waits out the same
**Wait time** as switching off does, so a sensor flickering doesn't make
the room flash. A light you switched off by hand stays off, and one
handed over with a `null` brightness is left alone.

## Keeping a room lit regardless of motion

Different from the above: this keeps the room at the **full** curve
rather than dimming it.

Make a template `binary_sensor` with `device_class: occupancy` and name
it directly in **Lights & Occupancy**. Home Assistant can't tell it from
a real sensor, and because a room is only empty once *all* its sensors
are clear, leaving yours on keeps the room lit however long you like.

```yaml
template:
  - binary_sensor:
      - name: "Landing override"
        device_class: occupancy
        state: "{{ is_state('input_boolean.keep_lit', 'on') }}"
```

Name it as an entity rather than relying on area membership, so it's a
deliberate addition.

## Using your own sensor

**FLARE Sensor** accepts any entity with these attributes, not just
FLARE's own schedule sensors:

| Attribute | Type | Required |
|---|---|---|
| `brightness` | 0–255 | yes |
| `color_temp` | Kelvin | yes |
| `rgb_color` | `[r, g, b]` | only with **Prefer RGB During** |

```yaml
template:
  - sensor:
      - name: "My Room's FLARE"
        state: "{{ 'Evening' if now().hour >= 18 else 'Day' }}"
        attributes:
          brightness: "{{ 180 if now().hour >= 18 else 255 }}"
          color_temp: "{{ 3200 if now().hour >= 18 else 5500 }}"
```

The picker only lists FLARE's own sensors, so point at yours through the
automation's **Edit in YAML** view.

The state can be anything. Only the phase-keyed inputs — **Prefer RGB
During**, the per-phase scenes, the per-phase off lists and the per-phase
idle brightnesses — read a phase name from it.

## Additional triggers

Both templates are re-rendered on every run, so an entity one of them
depends on — the TV in the example above — can go in **Additional
Triggers** to take effect immediately rather than at the next update.

This deliberately cannot light a dark room. If you want an event to
switch lights on, have your own automation call `automation.trigger` on
this room's automation, which counts as running it by hand.

## Why didn't my light change?

Most often, one of these:

- **Somebody else changed it.** A light changed by a wall switch, an
  app, a voice assistant or another automation is left alone until the
  whole room goes dark. Switching a light off by hand counts too — FLARE
  won't turn it back on. See
  [override protection](../advanced/reference/#override-protection).
- **The room is empty and the light was off.** Only occupancy, a manual
  run, or the room already being in use can switch a light on.
- **It's already close enough.** Lights within ±2 brightness or ±10 K of
  the target are left alone, so bulbs that round values off aren't
  fought with every minute.
- **It's unavailable.** Unreachable lights are skipped, and picked up
  when they come back.
- **A scene owns it**, or a **`null` brightness** hands it over.
- **It's dim rather than off on purpose** — check whether that phase
  has an [idle brightness](#leaving-a-room-dimly-lit) set.

To take a light back without switching it off first, call
`flare.apply_lighting` with `force: true`. Running the automation by
hand does the same for the whole room.

## Other behaviour worth knowing

**Two-step transitions.** Some bulbs can't change brightness and colour
in one command. Label the light or its device `no_combined_transition`
and FLARE sends two commands instead. Nothing to set in the blueprint;
if FLARE recognises a bulb that needs it, a repair appears with a Fix
button. See
[two-step transition bulbs](../advanced/reference/#two-step-transition-bulbs).

**Self-healing.** If the room has been empty for the full **Wait time**
but a light is still on, the off command is sent again — recovering from
a command that didn't land. Lights handed over with a `null` brightness
are left out.

**Lights that come back online.** When a light reappears after a
dropout, the room updates straight away rather than waiting for the next
scheduled update.

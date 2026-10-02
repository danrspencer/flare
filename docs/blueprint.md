---
title: Blueprint
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
[integration reference](../reference/integration/).

## Inputs

**Schedule**, **Zone** and **Lights & Occupancy** are required. Everything else has a working default.

| Input | Default | What it does |
|---|---|---|
| **Schedule** | — | The FLARE schedule whose brightness and colour the room follows. |
| **Zone** | — | The FLARE zone the room belongs to: it remembers which lights FLARE is driving. See [setting up a room](#setting-up-a-room). |
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
| **Motion On Transition** | 1s | How quickly lights change when someone walks in, or you run the automation by hand. |
| **Motion Off Transition** | 15s | How quickly lights fade when the room empties. |
| **Background Transition** | 5s | How quickly lights change on the regular update — nobody is waiting on these, so they can be slow and smooth. |

## Setting up a room

Point **Schedule** at a FLARE schedule, **Zone** at the room's zone,
and **Lights & Occupancy** at the room's area. That's it.

One target does both jobs: every light in that area is controlled, and
every occupancy sensor in it decides when. Lights you add to the area
later are picked up automatically. A floor, a device or a label works the
same way, or pick individual entities to mix and match — your lights
plus one sensor from elsewhere, say.

Occupancy uses Home Assistant's built-in occupancy triggers, which only
count `binary_sensor` entities with `device_class: occupancy`.
Motion-class sensors are not picked up. To drive a room from one, see
[additional triggers](#additional-triggers).

A room with no occupancy sensor works fine — it simply never switches
anything on by itself.

**Schedule** is one of FLARE's schedules: Home, unless you've added more
(Settings → Devices & Services → FLARE Schedules). Rooms that should keep
a different rhythm, a floor of bedrooms say, can follow a schedule of
their own.

**Zone** is one of FLARE's zones, usually the one named after the room
(Settings → Devices & Services → FLARE Zones). Two automations sharing
a room — a lamp and a pendant driven separately, say — pick the same
zone.

## When does the room update?

Straight away on a phase change, on motion, on an Additional Trigger,
and when a light comes back online. Between those, it updates whenever
its zone's **Tick** fires: every minute by default, set under
**Settings → Devices & Services → FLARE Zones → Configure**. See
[when zones tick](../reference/integration/#when-zones-tick).

{: .note }
> Don't hide a zone's Tick entity. Home Assistant leaves hidden entities
> out when it looks inside a device, so the room would stop updating.

## When lights turn on and off

Lights come on when occupancy is detected, and go off once every
occupancy sensor in the room has been clear for the **Wait time**.

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

If every light in the room should go to the same brightness, return a
single number instead of a mapping:

```yaml
{{ 40 if is_state('media_player.tv', 'playing') else none }}
```

A brightness here is **flat**. The light sits at it for as long as the
template returns it, rather than following the curve up and down — so
the lounge ceiling above stays at 40 for as long as the TV is on,
whatever time of day it is. Leave a light out of the template and it
tracks the curve as usual.

If you do want one that stays *relative* to the curve — half the room's
brightness, whatever that is right now — read the curve and scale it
yourself:

```yaml
{{ {'light.lounge_ceiling': state_attr('sensor.downstairs_flare', 'brightness') | int * 0.5} }}
```

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

It's per phase — leave the other three at `0` and empty still means dark
in those phases.

{: .warning }
> **Night is a phase, not "night-time".** Setting only **Night Idle
> Brightness** gives you a nightlight from your Night boundary — 22:00 by
> default — and nothing during Evening, when it is already dark outside.
> Set **Evening Idle Brightness** too if you want it lit from dusk, and
> **Morning Idle Brightness** for dark winter mornings.

For naming one lamp as the nightlight while the rest of the room goes
out, use **Idle Brightness Template**, which maps each light to its own
level:

```yaml
{{ {'light.landing_lamp': 20} }}
```

A single number instead of a mapping applies to every light in the room,
which is all a whole-room nightlight needs:

```yaml
{{ 20 }}
```

### A nightlight that follows the sun
{: .no_toc }

**Night** is a phase, not "after dark" — outside midsummer the sun sets
well before your Night boundary. For a hall that lights up whenever it is
genuinely dark outside, leave all four phase settings at `0` and drive the
template from the sun instead:

```yaml
{{ 10 if is_state('sun.sun', 'below_horizon') else {} }}
```

`{}` means "no opinion", so the room goes fully dark while the sun is up,
and the one template covers dusk, the small hours and dark winter
mornings without naming a phase at all.

The hall dims in at the next update after sunset, up to a minute later.
Don't add `sun.sun` to **Additional Triggers** to make it immediate: at
sunrise that would bring the lights up to the curve instead of switching
them off.

The template wins over the phase setting for any light it names; the
phase setting fills in the rest.

{: .note }
> With the phase setting at `0`, the template isn't an override on top of
> anything — it *is* the whole idle set. So a template naming one lamp
> makes that lamp the room's only nightlight and every other light goes
> dark, even if you only meant to give that one a different level. If you
> want the rest of the room dim too, set the phase value as well and let
> the template adjust the one light on top of it.

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
  [override protection](../reference/integration/#override-protection).
- **The room is empty and the light was off.** Only occupancy, a manual
  run, or the room already being in use can switch a light on.
- **It's already close enough.** A change smaller than 5% of the
  brightness or 5 mireds of colour temperature isn't sent, and nor is
  anything within ±2 brightness or ±10 K, so bulbs that round values off
  aren't fought with every minute. The first two are set under **FLARE
  Zones → Configure**.
- **It's unavailable.** Unreachable lights are skipped, and picked up
  when they come back.
- **A scene owns it**, or a **`null` brightness** hands it over.
- **It's dim rather than off on purpose** — check whether that phase
  has an [idle brightness](#leaving-a-room-dimly-lit) set.

To take the room's lights back without switching them off first, run
the automation by hand.

## Updating the blueprint

When a FLARE update comes with a new blueprint, it shows up in **Settings → System →
Repairs**. Press **Fix** to download it; your automations keep their settings. If you've
edited your own copy of the blueprint, ignore the repair instead, since updating replaces
the file.

## Other behaviour worth knowing

**Two-step transitions.** Some bulbs can't change brightness and colour
in one command. FLARE sends those bulbs two commands instead, recognising
them by make and model. For a bulb it doesn't recognise, label the light or its
device `no_combined_transition` by hand. See
[two-step transition bulbs](../reference/integration/#two-step-transition-bulbs).

**Self-healing.** If the room has been empty for the full **Wait time**
but a light is still on, the off command is sent again — recovering from
a command that didn't land. Lights handed over with a `null` brightness
are left out.

**Lights that come back online.** When a light reappears after a
dropout, the room updates straight away rather than waiting for the next
scheduled update.

## Test trace reports

If you want to understand the insides of the blueprint, check out our
[test trace reports](../trace-report/) - a real run of its triggers,
conditions and actions, step by step, each one matched against the
source line it comes from.

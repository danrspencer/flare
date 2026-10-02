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

The automation each room runs. This page covers every input and how a room behaves; to set
one up, see the [Quickstart](../../installation/), and for worked examples of the template
inputs, [Templates](../../guides/templates/).

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
| **Prefer RGB During** | Evening, Night | Phases that send RGB colour rather than colour temperature, to lights that support it. Lights without RGB are unaffected. Many bulbs make richer warm colours in RGB, but their cool whites can look blue, which is why it's off for Morning and Day by default. |

### Scene Handoff
{: .no_toc }

| Input | Default | What it does |
|---|---|---|
| **Scene Template** | none | Template returning a scene's entity ID, or `''` for none. Wins over the per-phase pickers whenever it returns a scene that exists. See [Templates](../../guides/templates/#scene-template). |
| **Morning / Day / Evening / Night Scene** | none | A scene to hand the room to during that phase. |

### Brightness & Exclusions
{: .no_toc }

| Input | Default | What it does |
|---|---|---|
| **Brightness Template** | none | Template returning entity ID → brightness: `1`–`255` to sit at that level, `0` for off, `null` to leave the light alone. A single number applies to the whole room. Wins over the lists below for any light it names. See [Templates](../../guides/templates/#brightness-template). |
| **Lights Off During Morning / Day / Evening / Night** | none | Lights to switch off during that phase. |

### Idle Brightness
{: .no_toc }

| Input | Default | What it does |
|---|---|---|
| **Idle Brightness Template** | none | Like Brightness Template, for when the room is empty. Wins over the settings below for any light it names. See [Templates](../../guides/templates/#idle-brightness-template). |
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

The simplest way to set up a room is to pick its area in **Lights & Occupancy**. That picks up
every light and occupancy sensor in the room, including ones you add to the area later. To
control only some of the lights in an area, pick them as entities instead. A floor, a device
or a label works too.

Occupancy only counts `binary_sensor` entities with `device_class: occupancy`; motion sensors
aren't picked up. To use a motion sensor, make a template occupancy sensor that follows it,
and add that instead:

```yaml
template:
  - binary_sensor:
      - name: "Hall occupancy"
        device_class: occupancy
        state: "{{ is_state('binary_sensor.hall_motion', 'on') }}"
```

A room with no occupancy sensor still follows the curve, but never turns its lights on or off
by itself.

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
[when zones tick](../zones/#when-zones-tick).

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

Put them in **Lights Off During Night** (or whichever phase).

For a dim level instead of off, a light that depends on something other than the phase, or
one handed over to something else, use **Brightness Template** — see
[Templates](../../guides/templates/#brightness-template).

## Handing a room to a scene

Pick a scene in **Night Scene** (or whichever phase) and the room uses it instead of the
curve during that phase. **Scene Template** picks one by template instead. A scene is only
used if everything it touches is in the room. See [Scenes](../../guides/scenes/).

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

For one lamp as the nightlight, a nightlight that follows the sun, and more, see
[Idle Brightness Template](../../guides/templates/#idle-brightness-template).

This is the one thing that will switch a light on in an empty room, and
only for lights you've given an idle brightness. It waits out the same
**Wait time** as switching off does, so a sensor flickering doesn't make
the room flash. A light you switched off by hand stays off, and one
handed over with a `null` brightness is left alone.

## Additional triggers

Entities in **Additional Triggers** make the room update as soon as they change, instead of
at its next update. Use it for anything a template depends on, like the TV in a Brightness
Template that dims the room while it's playing.

An additional trigger only adjusts lights that are already on; it never switches one on. To
have something else switch a room on, see
[lighting a room from something other than occupancy](../../guides/examples/#lighting-a-room-from-something-other-than-occupancy).

## Why didn't my light change?

Most often, one of these:

- **Somebody else changed it.** A light changed by a wall switch, an
  app, a voice assistant or another automation is left alone until the
  whole room goes dark. Switching a light off by hand counts too — FLARE
  won't turn it back on. See
  [override protection](../zones/#override-protection).
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
[two-step transition bulbs](../services/#two-step-bulbs).

**Self-healing.** If the room has been empty for the full **Wait time**
but a light is still on, the off command is sent again — recovering from
a command that didn't land. Lights handed over with a `null` brightness
are left out.

**Lights that come back online.** When a light reappears after a
dropout, the room updates straight away rather than waiting for the next
scheduled update.

## Test trace reports

The [test trace reports](../../trace-report/) show real runs of the blueprint's triggers,
conditions and actions, each step matched to the line of the blueprint it comes from.

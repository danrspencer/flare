---
title: Override protection
parent: Reference
nav_order: 3
permalink: /reference/override-protection/
redirect_from:
  - /reference/zones/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Override protection
{: .no_toc }

FLARE records what it last asked each light for, so it can tell its own changes from anyone
else's and leave alone a light you've changed yourself. Its entities and options are under
**Settings → Devices & Services → FLARE → Settings**.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## FLARE's entities

| Entity | Description |
|---|---|
| `sensor.flare_controlled_lights` | The number of lights FLARE is setting. For information only. |
| `sensor.flare_overridden_lights` | The number of lights something else has changed. For information only. |
| `button.flare_clear` | Discards every claim. |
| `sensor.<light>_flare_status` | One for each light a room has named: its [status](#inspecting-tracked-state), on the light's own device. `rooms` lists the rooms it's in, `claimed` whether FLARE has a claim on it, `asked` what FLARE last asked it for, and `differs` which of that it isn't showing (`state`, `brightness`, `color`), within the tolerances. |

The two counts and each light's status are recorded in history, with long-term statistics for
the counts. `asked` and `differs` aren't recorded, since they change with every update. A light that's
unavailable or has no claim isn't included in either count. The [dashboard](../../dashboard/)
shows the counts and each light for each area too.

FLARE keeps its claims in Home Assistant's own storage, so they're kept across a restart. To see
every claim at once, download the diagnostics from **FLARE → Settings**: they list each light's
claims and each room's lights. They also list the last 50 overrides, each with what FLARE asked
for, what the light reported and what kind of light it is.

A light's status sensor appears the first time a room names the light, under **Diagnostic** on
the light's device page, and stays after its room lets the light go. It's unavailable while the
light is, and it's removed with the light. A light with no device, such as a light group, gets
one named after it instead. An automation can trigger on it:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.kitchen_1_flare_status
    to: overridden
```

**Clear** discards every claim, not only for the overridden lights. FLARE then sets every light
again on its next update.

## How it works

When `flare.apply_lighting` or `flare.turn_off` changes a light, it records a **claim** on the
light. On the next update, FLARE compares the light with its claim. If the light still shows
what FLARE set, FLARE carries on setting it. If it doesn't, something else has changed it, and
FLARE leaves it alone.

Claims are FLARE's, not any one automation's: a light one automation set is FLARE's to every
other automation too. A light that's on and has no claim is always sent what
`flare.apply_lighting` would set, even if it already shows it, and that write claims it. After a
**Clear**, for example, a room's lights are claimed again on their next update. Without a
`room_id`, a light already showing the values isn't sent anything.

### Rooms

Each call that records claims names a **room**, usually the automation making it, and the
room's lights. The blueprint passes its own automation as `room_id` and its
**Lights & Occupancy** lights as `room_entities`. If you call the services yourself, do the same:

```yaml
action: flare.apply_lighting
data:
  entities: [light.kitchen_1, light.kitchen_2]
  brightness: 200
  color_temp_kelvin: 3200
  transition: 2
  room_id: "{{ this.entity_id }}"
  room_entities: [light.kitchen_1, light.kitchen_2, light.kitchen_lamp]
```

- Without `room_id`, `apply_lighting`, `turn_off` and `compute_lighting_groups` set the lights
  but record nothing, and don't leave any light alone.
- `claims_record` and `claims_override` require `room_id`. `claims_check` and `claims_clear`
  don't take one.
- Without `room_entities`, a room's lights are the ones its calls have set.
- `force: true` sets lights even if something else has changed them, and records the claim.
- A light FLARE has no claim on is free for FLARE to set, so a change your own automation makes
  to one isn't left alone unless you mark it with
  [`flare.claims_override`](../services/#flareclaims_override).

If an automation is renamed, its room carries on: FLARE keeps rooms by the automation's entity
registry entry, not its entity ID.

### The two claims

Each tracked light has two claims:

- **`latest`**: the last change FLARE sent to the light.
- **`observed`**: a change FLARE has seen the light report. On its next update, if the light
  reports `latest`'s context, FLARE promotes `latest` to `observed`.

A light matching either claim is FLARE's. So a change that never reaches the light, such as a
dropped Zigbee command, doesn't make FLARE treat the light as changed by someone else; the light
still matches `observed`.

A light matches a claim if it reports the context of that claim's change, or the values in it.
Values are needed because Home Assistant drops a change's context after five seconds, and some
bulbs take longer than that to report back.

### How close counts as a match

A light matches a claim's values if it's within a tolerance of them, so only a change you'd
notice counts as someone else's. Bulbs rarely report back exactly what they were sent: a colour
temperature asked for as 4294 K can come back as 4312 K. You can set the tolerances under
**FLARE → Settings → Configure**:

| Option | Default | Description |
|---|---|---|
| Brightness tolerance | 5% | How far, as a percentage of the brightness FLARE asked for, a light's brightness can be and still match. A dim light always gets at least 2 (of 255). |
| Colour temperature tolerance | 5 mireds | How far a light's colour temperature can be from what FLARE asked for and still match. For a light FLARE sets by RGB, the red, green and blue differences added together can be up to twice this (10 by default). |

The same tolerances decide what's worth sending: a light that close to its target isn't sent
anything.

If lights are marked overridden when nobody has changed them, raise the one that matches the
difference shown on the [dashboard](../../dashboard/). Lower them to catch smaller changes.

Claims are kept across a restart. After a restart every light has a new context, so restored
claims are matched by values only: a light still showing what FLARE set is FLARE's, and any
other light is left alone.

### Turning a light off counts

Turning a light off yourself counts as changing it, so FLARE doesn't turn it back on. FLARE's own
turn-offs record a claim of `{"state": "off"}`, which is how FLARE tells them apart from yours.

### When FLARE sets a light again

**A room discards its claims when none of its claimed lights are on.** This is what normally
ends an override: once the room is dark, FLARE sets every light in it again.

- A light FLARE has no claim on doesn't count, so a lamp in the room that something else runs
  can't keep the room's claims.
- A light that's unavailable counts as off, so one dead bulb can't either.
- After a restart, a room whose claimed lights are all off once they've reported in discards its
  claims too, so a room switched off while Home Assistant was restarting comes on again as
  usual.
- A light in two rooms loses its claim when either of them goes dark.

A light also loses its claim when it goes unavailable, and you can discard claims by hand with
**Clear**, the dashboard's **Clear** for an area, or
[`flare.claims_clear`](../services/#flareclaims_clear).

A light that has just come back online, say switched on at the wall, starts at whatever it
powers up as, and misses a command sent while it boots. So when a room's lights come back
online together, FLARE waits a few seconds before setting them.

## FLARE's events

FLARE says when a room takes its lights, when it lets them go, and when something else changes
one of them. Each event is filed under one of FLARE's entities (its **Controlled** or
**Overridden** count, or **Clear** for a release) and FLARE's device, so they appear in its
Activity. `room` names the automation. FLARE adjusting lights it already has isn't announced.

When a room starts controlling lights it wasn't, such as when it comes on, FLARE fires
`flare_lights_controlled` once for them all, a few seconds after the first, since the bulbs
report back one by one:

```yaml
lights: [light.kitchen_1, light.kitchen_2]   # the lights it took
controlled: 6                                # how many of its lights FLARE is controlling now
room: automation.kitchen_lighting
entity_id: sensor.flare_controlled_lights
device_id: ...                               # FLARE's device
```

> **Controlled lights** Kitchen Lighting is now controlling 6 lights

When a room lets its lights go, because it went dark or you pressed **Clear**, FLARE fires
`flare_lights_released`:

```yaml
lights: [light.kitchen_1, light.kitchen_2]
room: automation.kitchen_lighting
entity_id: button.flare_clear
device_id: ...
```

> **Clear** Kitchen Lighting cleared 6 lights

When something else changes one of FLARE's lights, and it stays changed for 30 seconds, FLARE
fires `flare_light_overridden` for that light:

```yaml
light: light.kitchen_1
rooms: [automation.kitchen_lighting]   # every room it's one of
entity_id: sensor.flare_overridden_lights
device_id: ...
previous_status: controlled
live_context_id: 01M11...
live: { state: on, brightness: 12, color_temp_kelvin: 6500 }   # or rgb_color, for a colour
observed: { context_id: ..., target: {...}, recorded_at: ... }
latest:   { context_id: ..., target: {...}, recorded_at: ... }
```

> **Overridden lights** Kitchen Lighting released Kitchen 1 to something else (last asked for 255/6667, found 12/6500)

`live` is what the light was showing: its brightness and colour temperature, or its `rgb_color`
if it wasn't showing a white. A light reporting its colour as `xy` that's showing a white has its
colour temperature worked out from it.

It fires once when the light changes hands, not again while the light stays overridden, and not
for lights that were already overridden before a restart. To trigger an automation on it:

```yaml
triggers:
  - trigger: event
    event_type: flare_light_overridden
```

## Inspecting tracked state

`flare.claims_check` returns each light's status, and each light's status sensor shows it:

| Status | Meaning |
|---|---|
| `controlled` | FLARE is setting it: it matches one of its claims. |
| `overridden` | It has matched neither claim for at least 30 seconds, so something else has changed it. |
| `mismatched` | It has matched neither claim for less than 30 seconds. Usually it's FLARE's own change still arriving, or a light just back online reporting late, so it isn't counted or announced as overridden yet. It's left alone meanwhile, the same as an overridden light. |
| `untracked` | It's on, and has no claim, or only one FLARE hasn't seen the light report yet. FLARE sets it as usual. |
| `off` | It's off and has no claim. A light FLARE turned off is `controlled`; one someone else turned off is `overridden`. |
| `unavailable` | Home Assistant can't reach it, so its claims aren't checked. It isn't blocked. |

`matched_via` says which claim matched, and how: `latest-context`, `latest-value`,
`observed-context` or `observed-value`. `rooms` lists the rooms the light is one of.

Each claim has a `recorded_at` time and a `context_id`, which you can use to find the change in
Home Assistant's logbook. A light's claim follows it when it's renamed, and goes when it's
deleted from Home Assistant.

## When rooms update

FLARE fires a `flare_tick` event for each area once per update interval, carrying the area as
`area_id`. Areas tick one after another, in name order, a gap apart, so rooms don't all send
commands at the same time. A tick is a plain event, not an entity, so it never appears in
Activity, history or the logbook. You can set the interval and the gap under **FLARE → Settings →
Configure**:

| Option | Default | Description |
|---|---|---|
| Update interval | 1 minute | How often each area ticks, from 1 to 60 minutes. |
| Gap between areas | 1 second | Reduced automatically when the areas wouldn't otherwise fit in the interval. |

A room automation from the blueprint follows the tick of the first area in its
**Lights & Occupancy**. To run your own automation on an area's tick:

```yaml
triggers:
  - trigger: event
    event_type: flare_tick
    event_data:
      area_id: kitchen
```

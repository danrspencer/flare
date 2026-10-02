---
title: Zones
parent: Reference
nav_order: 3
permalink: /reference/zones/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Zones
{: .no_toc }

A zone is FLARE's record of which lights it's driving, usually one per room. It's what lets
FLARE tell its own changes from anyone else's, so a light you change yourself is left alone.
Each zone is a device under **Settings → Devices & Services → FLARE Zones**.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## A zone's entities

| Entity | |
|---|---|
| `sensor.<name>_flare_claims` | The claims themselves. Its state is the number of lights tracked; its `claims` attribute holds each light's records |
| `sensor.<name>_flare_controlled` | How many of the zone's lights FLARE is driving |
| `sensor.<name>_flare_overridden` | How many something else has taken over |
| `button.<name>_flare_clear` | Discards every claim in the zone |
| `event.<name>_flare_tick` | Fires once per update interval — see [when zones tick](#when-zones-tick) |

The `claims` attribute isn't recorded, so it has no history. The two counts are ordinary
numbers with history and long-term statistics.

- **The counts don't add up to the total.** An unavailable light is in neither, and nor is a
  light with no claim.
- **Overridden isn't an error.** It means something else took the light and FLARE stepped
  back.
- **Clear discards every claim in the zone**, not just the overridden ones. Every light in
  the zone is then free for FLARE to set again on its next update.

## Override protection

Every time FLARE writes a light, it records a **claim** on that light in the zone named in
the call. On the next update it compares the light with the claim: if the light still shows
what FLARE asked for, FLARE carries on; if not, something else has changed it, and FLARE
leaves it alone.

The blueprint names its **Zone** input in every call. Calling the services yourself, pass the
zone as `zone_device_id`:

```yaml
action: flare.apply_lighting
data:
  entities: [light.kitchen_1, light.kitchen_2]
  brightness: 200
  color_temp_kelvin: 3200
  transition: 2
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
```

- **Leave `zone_device_id` out** of `apply_lighting`, `turn_off` or `compute_lighting_groups`
  and the light is written but not tracked: no claim is recorded, and nothing is left alone.
- **It's required** on `claims_check`, `claims_record` and `claims_clear`, which only read or
  write claims.
- **An id that isn't one of your zones** is an error, rather than being treated as no zone.
- **Two calls naming the same zone share its claims.** To keep two automations' lights
  separate, give them different zones.
- **`force: true`** writes regardless of who holds the light, and still records the claim.

### The two claims

Each tracked light has two claims in its zone:

- **`observed`** — a state FLARE has seen the light take after one of its own writes.
- **`latest`** — the most recent write FLARE sent, not yet seen.

A light matches if it carries the context of either claim's write, or shows either claim's
values. Values matter because Home Assistant forgets a write's context after five seconds, so
a bulb that's slow to report back arrives under a different one.

Claims survive a restart. A restart gives every light a new context, so restored claims match
on values alone: a light still showing what FLARE asked for is FLARE's, anything else is left
alone.

### Turning a light off counts

Switching a light off yourself is a change like any other, so FLARE leaves the light off
instead of turning it back on at the next update. FLARE's own turn-offs record a claim of
`{"state": "off"}`, which is how it tells its own turn-off from yours.

### When FLARE takes a light back

**A zone releases every claim once none of its lights are on.** That's what normally ends an
override: when the room goes dark, FLARE starts afresh with every light in it.

- **The room is the zone.** A light that isn't in the zone doesn't keep it open.
- **Anything not `on` counts as dark**, unavailable included, so one dead bulb can't keep a
  zone's claims forever.

A light that goes unavailable loses its claim too, and the **Clear** button releases a zone
by hand.

### One zone per light

Two zones driving the same light each see the other's writes as someone else's change, so the
light stops following either. When FLARE sees a light in two zones, it shows a notification
naming the light and the zones. You'll see it once per light; dismissed, it stays away until
Home Assistant restarts, and comes back then only if the light is still in two zones.

## The hand-over event

When a tracked light passes to someone else, FLARE fires `flare_light_overridden` with what it
asked for and what the light was showing:

```yaml
entity_id: light.kitchen_1
zone: Kitchen                        # the zone that lost it
device_id: ...                        # so it appears in that device's Activity
previous_status: controlled
live_context_id: 01M11...
live: { state: on, brightness: 12, color_temp_kelvin: 6500, rgb_color: null }
observed: { context_id: ..., target: {...}, recorded_at: ... }
latest:   { context_id: ..., target: {...}, recorded_at: ... }
```

It fires once when a light changes hands, not again while it stays taken. Lights already taken
before a restart aren't announced again. It also shows in the light's logbook:

> **Kitchen** released this light to something else (last asked for 255/6667, found 12/6500)

```yaml
triggers:
  - trigger: event
    event_type: flare_light_overridden
```

## Inspecting tracked state

`flare.claims_check` reports each light's status, and how it was matched:

| status | meaning |
|---|---|
| `controlled` | FLARE is driving it: it matches one of its claims, by context or by values |
| `overridden` | It matches neither claim. Something else has changed it |
| `unavailable` | There's no state to compare against |
| `off` | It's off and has no claim. A light FLARE turned off is `controlled`; one somebody else turned off is `overridden` |

`matched_via` says which claim matched and how: `latest-context`, `latest-value`,
`observed-context` or `observed-value`.

Each claim records `recorded_at` and a `context_id`, which together find the write in Home
Assistant's logbook. Claims untouched for a day are discarded, which is how a light deleted
from Home Assistant stops being tracked.

## When zones tick

Each zone's `event.<name>_flare_tick` fires an event of type `flare_tick` once per update
interval. The zones fire one after another, in name order, a gap apart, so rooms don't all
send their commands at the same moment. Both are set under **FLARE Zones → Configure**:

| Option | Default | |
|---|---|---|
| Update interval | 1 minute | How often each zone ticks, 1–60 minutes |
| Gap between zones | 1 second | Shrinks when the zones wouldn't otherwise fit in the interval |

To run your own automation on a zone's tick:

```yaml
triggers:
  - trigger: event.received
    target:
      entity_id: event.kitchen_flare_tick
    options:
      event_type: [flare_tick]
```

Targeting the zone's device works too, as the blueprint does. Don't hide the Tick entity:
Home Assistant leaves hidden entities out when it looks inside a device or area.

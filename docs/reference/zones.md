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

A zone records which lights FLARE has set, usually for one room. FLARE uses it to tell its own
changes from anyone else's, so it can leave alone a light you've changed yourself. Zones are
under **Settings → Devices & Services → FLARE → Zones**.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## A zone's entities

| Entity | Description |
|---|---|
| `sensor.<name>_flare_claims` | Where FLARE stores the zone's claims. The state is the number of lights tracked; the `claims` attribute has each light's claims. Don't disable it: without it the zone can't record anything. |
| `sensor.<name>_flare_controlled` | The number of the zone's lights FLARE is setting. For information only. |
| `sensor.<name>_flare_overridden` | The number of the zone's lights something else has changed. For information only. |
| `button.<name>_flare_clear` | Discards every claim in the zone. |

The two counts are recorded in history, with long-term statistics, but the `claims` attribute
isn't. A light that's unavailable or has no claim isn't included in either count.

**Clear** discards every claim in the zone, not only for the overridden lights. FLARE then sets
all of the zone's lights again on their next update.

## Override protection

When `flare.apply_lighting` or `flare.turn_off` changes a light, it records a **claim** on the
light in the zone the call names. On the next update, FLARE compares the light with its claim.
If the light still shows what FLARE set, FLARE carries on setting it. If it doesn't, something
else has changed it, and FLARE leaves it alone.

The blueprint passes its **Zone** input with every call. If you call the services yourself,
pass the zone as `zone_device_id`:

```yaml
action: flare.apply_lighting
data:
  entities: [light.kitchen_1, light.kitchen_2]
  brightness: 200
  color_temp_kelvin: 3200
  transition: 2
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
```

- Without `zone_device_id`, `apply_lighting`, `turn_off` and `compute_lighting_groups` set the
  lights but record nothing, and don't leave any light alone.
- `claims_check`, `claims_record`, `claims_clear` and `claims_override` require
  `zone_device_id`.
- A `zone_device_id` that isn't one of your zones is an error.
- Calls naming the same zone share its claims. To keep two automations' lights separate, give
  them different zones.
- `force: true` sets lights even if something else has changed them, and records the claim.
- A light FLARE has no claim on is free for FLARE to set, so a change your own automation makes
  to one isn't left alone unless you mark it with
  [`flare.claims_override`](../services/#flareclaims_override).

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

Claims are kept across a restart. After a restart every light has a new context, so restored
claims are matched by values only: a light still showing what FLARE set is FLARE's, and any
other light is left alone.

### Turning a light off counts

Turning a light off yourself counts as changing it, so FLARE doesn't turn it back on. FLARE's own
turn-offs record a claim of `{"state": "off"}`, which is how FLARE tells them apart from yours.

### When FLARE sets a light again

**A zone discards all its claims when none of its lights are on.** This is what normally ends an
override: once the room is dark, FLARE sets every light in it again.

- A light that isn't in the zone doesn't count.
- A light that's unavailable counts as off, so one dead bulb can't keep the zone's claims.

A light also loses its claim when it goes unavailable, and you can discard a zone's claims by
hand with its **Clear** button.

### One zone per light

If two zones set the same light, each treats the other's changes as someone else's, and the light
stops following either. When this happens, FLARE shows a notification naming the light and the
zones. It shows this once for each light, and doesn't show it again for that light until Home
Assistant restarts.

## The hand-over events

When something else takes over a tracked light, FLARE fires `flare_light_overridden`:

```yaml
entity_id: light.kitchen_1
zone: Kitchen                        # the zone that lost the light
device_id: ...                        # the zone's device
previous_status: controlled
live_context_id: 01M11...
live: { state: on, brightness: 12, color_temp_kelvin: 6500, rgb_color: null }
observed: { context_id: ..., target: {...}, recorded_at: ... }
latest:   { context_id: ..., target: {...}, recorded_at: ... }
```

It fires once when the light changes hands, not again while the light stays overridden, and not
for lights that were already overridden before a restart. It also appears in the light's
logbook:

> **Kitchen** released this light to something else (last asked for 255/6667, found 12/6500)

To trigger an automation on it:

```yaml
triggers:
  - trigger: event
    event_type: flare_light_overridden
```

When FLARE is setting an overridden light again, because a forced update took it back or it was
put back the way FLARE had it, FLARE fires `flare_light_reclaimed`:

```yaml
entity_id: light.kitchen_1
zone: Kitchen
device_id: ...                        # the zone's device
```

> **Kitchen** is setting this light again

Both appear in the light's logbook and in the zone's own Activity, on its device page.

## Inspecting tracked state

`flare.claims_check` returns each light's status:

| Status | Meaning |
|---|---|
| `controlled` | FLARE is setting it: it matches one of its claims. |
| `overridden` | It matches neither claim, so something else has changed it. |
| `untracked` | It's on, and has no claim, or only one FLARE hasn't seen the light report yet. FLARE sets it as usual. |
| `off` | It's off and has no claim. A light FLARE turned off is `controlled`; one someone else turned off is `overridden`. |
| `unavailable` | Home Assistant can't reach it, so its claims aren't checked. It isn't blocked. |

`matched_via` says which claim matched, and how: `latest-context`, `latest-value`,
`observed-context` or `observed-value`.

Each claim has a `recorded_at` time and a `context_id`, which you can use to find the change in
Home Assistant's logbook. Claims that haven't changed for a day are discarded, so a light
deleted from Home Assistant stops being tracked.

## When zones tick

Each zone fires a `flare_tick` event once per update interval, carrying the zone's device as
`device_id`. Zones fire one after another, in name order, a gap apart, so rooms don't all send
commands at the same time. A tick is a plain event, not an entity, so it never appears in
Activity, history or the logbook. You can set the interval and the gap under **FLARE → Zones →
Configure**:

| Option | Default | Description |
|---|---|---|
| Update interval | 1 minute | How often each zone ticks, from 1 to 60 minutes. |
| Gap between zones | 1 second | Reduced automatically when the zones wouldn't otherwise fit in the interval. |

To run an automation on a zone's tick:

```yaml
triggers:
  - trigger: event
    event_type: flare_tick
    event_data:
      device_id: "<the zone's device ID>"
```

The zone's device ID is in the address of its device page, or
`{{ device_id('sensor.kitchen_flare_claims') }}` in the template editor.

{: .note }
> **Changed in 1.0.0** — the tick was an entity, `event.<name>_flare_tick`, which is removed.
> An automation triggering on it needs the trigger above instead.

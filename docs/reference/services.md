---
title: Services
parent: Reference
nav_order: 4
permalink: /reference/services/
redirect_from:
  - /reference/integration/
  - /advanced/reference/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Services
{: .no_toc }

FLARE's services are Home Assistant actions that any automation or script can call. The
blueprint uses them too. **Developer Tools → Actions** lists every field.

| Service | Description |
|---|---|
| [`flare.apply_lighting`](#flareapply_lighting) | Sets lights to a brightness and colour, leaving alone any that someone else has changed |
| [`flare.turn_off`](#flareturn_off) | Turns lights off, recording that FLARE did it |
| [`flare.compute_lighting_groups`](#flarecompute_lighting_groups) | Works out what `apply_lighting` would send, without sending it |
| [`flare.compute_curve`](#flarecompute_curve) | The curve's brightness and colour for any moment |
| [`flare.claims_check`, `claims_record`, `claims_clear`](#flareclaims_check-claims_record-and-claims_clear) | Override protection on its own, for lights you set yourself |
| [`flare.compute_scene_coverage`](#flarecompute_scene_coverage) | Which of a room's lights a scene covers |
| [`flare.export_schedule`, `import_schedule`](#flareexport_schedule-and-flareimport_schedule) | A schedule's settings as YAML, out and in |

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## `flare.apply_lighting`

Sets lights to a brightness and colour temperature, turning on any that are off. It skips
lights that are unavailable, already close to the target, or changed by something else (see
[override protection](../zones/#override-protection)). Bulbs that need it are sent two commands
(see [two-step bulbs](#two-step-bulbs)).

```yaml
action: flare.apply_lighting
data:
  entities: [light.kitchen_1, light.kitchen_2]
  brightness: 200
  color_temp_kelvin: 3200
  transition: 2
  brightness_multipliers: { light.kitchen_2: 0.5 }  # optional
  prefer_rgb_color: true                          # optional, see RGB colour below
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"  # optional
  force: false                                    # optional
```

To follow a schedule, read the values from its
[schedule sensor](../schedules/#the-schedule-sensor):

```yaml
brightness: "{{ state_attr('sensor.home_flare', 'brightness') }}"
color_temp_kelvin: "{{ state_attr('sensor.home_flare', 'color_temp') }}"
```

`brightness_multipliers` scales the brightness for individual lights:

| Value | Effect |
|---|---|
| A number | Multiplies the brightness. The result is limited to 1–255. |
| `0` | Turns the light off. |
| `null` | Leaves the light alone. |

Lights not listed use `1`.

### RGB colour

With `prefer_rgb_color` on, lights that support RGB are sent `rgb_color` instead of
`color_temp_kelvin`. Other lights still get the colour temperature. The schedule sensor and
`compute_curve` both return `rgb_color`, the colour temperature converted to RGB. Without
`prefer_rgb_color`, `rgb_color` is ignored and can be `null`.

### Leaving small changes alone

A light isn't sent anything if it's within any of these of its target:

| Field | Default | Unit |
|---|---|---|
| `brightness_tolerance` | 2 | Brightness, 0–255 |
| `color_temp_tolerance` | 10 | Kelvin |
| `rgb_color_tolerance` | 10 | Each RGB channel, 0–255 |
| `min_brightness_change` | from **FLARE Zones → Configure** (5) | Percent of the target brightness |
| `min_color_temp_change` | from **FLARE Zones → Configure** (5) | Mireds |

## `flare.turn_off`

Turns lights off and records a claim, so FLARE knows it turned them off and doesn't treat
them as overridden.

```yaml
action: flare.turn_off
data:
  entities: [light.kitchen_1, light.kitchen_2]
  transition: 15                                                   # optional, seconds
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"  # optional
```

It turns off every light it's given, including lights someone else has changed. To turn off
only the lights FLARE is still setting, call `claims_check` first.

## `flare.compute_lighting_groups`

Returns what `apply_lighting` would send, without sending it: the lights that need a command,
grouped by brightness, with two-step bulbs listed separately. It takes the same fields as
`apply_lighting` except `transition`.

```yaml
action: flare.compute_lighting_groups
data:
  entities: [light.kitchen_1, light.kitchen_2]
  brightness: 200
  color_temp_kelvin: 3200
  brightness_multipliers: { light.kitchen_2: 0.5 }
response_variable: plan
# plan.groups -> [{multiplier, brightness, needing_off, combined, two_step, combined_rgb, two_step_rgb}, ...]
```

## `flare.compute_curve`

Returns the phase, brightness, colour temperature and RGB colour for the phase start times
you give it. It uses the current time, or `at` as a timestamp. Curve settings you leave out
use a new schedule's defaults.

```yaml
action: flare.compute_curve
data:
  morning: "{{ today_at('06:00:00') | as_timestamp }}"
  day: "{{ today_at('08:00:00') | as_timestamp }}"
  evening: "{{ today_at('18:00:00') | as_timestamp }}"
  night: "{{ today_at('22:00:00') | as_timestamp }}"
  evening_brightness: 180   # optional, like every curve setting
  night_kelvin: 2700
response_variable: now
# now.phase / now.brightness / now.kelvin / now.rgb_color
```

## `flare.claims_check`, `claims_record` and `claims_clear`

These give you [override protection](../zones/#override-protection) for lights you set
yourself. Each requires `zone_device_id`.

`claims_check` reports whether FLARE would leave each light alone:

```yaml
action: flare.claims_check
data:
  entities: [light.kitchen_1]
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
response_variable: control
# control.results["light.kitchen_1"] ->
#   {"blocked": false, "status": "controlled", "matched_via": "latest-context", "zone": "Kitchen"}
```

`status` and `matched_via` are described under
[inspecting tracked state](../zones/#inspecting-tracked-state).

`claims_record` records a claim, so a later `claims_check` treats your change as FLARE's. Call
it just **before** you change the light, with the values you're about to send:

```yaml
action: flare.claims_record
data:
  entities: [light.kitchen_1]
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
  targets:
    light.kitchen_1: { brightness: 200, color_temp_kelvin: 3000 }
```

Each target needs a brightness and either `color_temp_kelvin` or `rgb_color`. Without
`targets`, a bulb that's slow to report back is treated as changed by someone else.

`claims_clear` discards claims, so FLARE sets the lights again on its next update. Use it for
a light that's overridden in a room that's never fully dark. A zone's **Clear** button does the same for every
light in the zone.

```yaml
action: flare.claims_clear
data:
  entities: [light.kitchen_1]
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
```

## `flare.compute_scene_coverage`

Returns which of a set of lights a scene sets, so you can apply the scene and set the other
lights yourself. If the scene doesn't exist, or sets entities outside `scope_entities`,
`scene_valid` is false and every light is uncovered.

```yaml
action: flare.compute_scene_coverage
data:
  scene_entity_id: scene.kitchen_night
  scope_entities: [light.kitchen_1, light.kitchen_2, light.kitchen_strip]
  target_entities: [light.kitchen_1, light.kitchen_2]
response_variable: coverage
# coverage.scene_active / scene_valid / covered_entities / uncovered_entities
```

`scope_entities` is every entity the scene may set. `target_entities` is the lights to check.

## `flare.export_schedule` and `flare.import_schedule`

Export or apply a schedule's settings, in the YAML format described under
[copying a schedule](../schedules/#copying-a-schedule). Both take the schedule's device as
`schedule_device_id`.

```yaml
action: flare.export_schedule
data:
  schedule_device_id: "{{ device_id('sensor.home_flare') }}"
response_variable: exported
# exported.schedule -> the YAML, as text
```

```yaml
action: flare.import_schedule
data:
  schedule_device_id: "{{ device_id('sensor.home_flare') }}"
  schedule:
    night:
      time: "23:00"
```

`schedule` can be YAML text, or YAML written directly in the call as above. Settings it leaves
out keep their current values. A schedule with an error in it isn't applied.

## Two-step bulbs

Some bulbs can't change brightness and colour temperature in one command: they jump to the new
value, or ignore one of the two. FLARE sends these bulbs two commands, each taking half the
transition. It recognises them in two ways:

- **By make and model**, from a list of patterns under **FLARE Zones → Configure**, one per
  line, matched against `"<manufacturer> <model>"`. Patterns are case-insensitive and take
  `*`, so `*TRADFRI bulb*` and `IKEA*` both work. The box starts with FLARE's own list.
  Clear it and FLARE goes back to that list.
- **By label**: give the light or its device a label created with the name
  `no_combined_transition`. FLARE matches the label's ID, which comes from the name it was
  created with, so renaming another label to this won't work.

Once you've saved your own pattern list, FLARE updates don't add to it. Keep patterns specific:
a bulb that doesn't need two commands transitions less smoothly with them.

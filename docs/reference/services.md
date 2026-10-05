---
title: Services
parent: Reference
nav_order: 5
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

FLARE's services are Home Assistant actions that any automation or script can call, and the
blueprint is built on them. **Developer Tools → Actions** shows the same fields as this page.

| Service | Description |
|---|---|
| [`flare.apply_lighting`](#flareapply_lighting) | Sets lights to a brightness and colour, leaving alone any that someone else has changed |
| [`flare.turn_off`](#flareturn_off) | Turns lights off, recording that FLARE did it |
| [`flare.compute_lighting_groups`](#flarecompute_lighting_groups) | Works out what `apply_lighting` would send, without sending it |
| [`flare.compute_curve`](#flarecompute_curve) | The curve's brightness and colour for any moment |
| [`flare.claims_check`](#flareclaims_check) | Whether FLARE would leave each light alone |
| [`flare.claims_record`](#flareclaims_record) | Records a change you're about to make as FLARE's |
| [`flare.claims_clear`](#flareclaims_clear) | Discards claims, so FLARE sets the lights again |
| [`flare.claims_override`](#flareclaims_override) | Marks lights as changed by someone else, so FLARE leaves them alone |
| [`flare.compute_scene_coverage`](#flarecompute_scene_coverage) | Which of a room's lights a scene sets |
| [`flare.export_schedule`](#flareexport_schedule) | A schedule's settings as YAML |
| [`flare.import_schedule`](#flareimport_schedule) | Sets a schedule from YAML |

In the field tables, a zone or schedule is passed as its **device** ID. In a template,
`device_id()` of any of its entities gives you that, such as
`device_id('sensor.kitchen_flare_claims')` for the Kitchen zone or
`device_id('sensor.home_flare')` for the Home schedule.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## `flare.apply_lighting`

Use this action to set lights to a brightness and colour temperature, turning on any that are
off. It skips lights that are unavailable, already close to the target, or changed by
something else (see [override protection](../zones/#override-protection)).

```yaml
action: flare.apply_lighting
data:
  entities: [light.kitchen_1, light.kitchen_2]
  brightness: "{{ state_attr('sensor.home_flare', 'brightness') }}"
  color_temp_kelvin: "{{ state_attr('sensor.home_flare', 'color_temp') }}"
  transition: 2
  brightness_levels: { light.kitchen_2: 60 }
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
```

This sets both kitchen lights to the Home schedule's current colour temperature, with
`light.kitchen_1` at the schedule's brightness and `light.kitchen_2` at 60.

### Fields

| Field | Required | Description |
|---|---|---|
| `brightness`<br>0–255 | unless every light has a level | The brightness for every light that isn't in `brightness_levels`. `0` turns the lights off, as it does for `light.turn_on`. |
| `brightness_levels`<br>map of entity ID to level | no | A brightness for individual lights, in place of `brightness`. See [brightness levels](#brightness-levels). |
| `brightness_tolerance`<br>0–50; default `2` | no | A light within this much of the target brightness isn't sent anything. |
| `color_temp_kelvin`<br>Kelvin | yes | The colour temperature. |
| `color_temp_tolerance`<br>Kelvin, 0–500; default `10` | no | A light within this many Kelvin of the target isn't sent anything. Two values that convert to the same mired always count as a match. |
| `entities`<br>list of light entity IDs | yes | The lights to set. |
| `force`<br>boolean; default `false` | no | Sets every light, including ones someone else has changed. The change is still recorded as FLARE's. |
| `min_brightness_change`<br>percent, 0–25; default 5, from **FLARE → Zones → Configure** | no | A light within this percentage of the target brightness isn't sent anything. It's never smaller than `brightness_tolerance`. |
| `min_color_temp_change`<br>mireds, 0–50; default 5, from **FLARE → Zones → Configure** | no | A light within this many mireds of the target colour temperature isn't sent anything. |
| `prefer_rgb_color`<br>boolean; default `false` | no | Sends `rgb_color` instead of `color_temp_kelvin` to lights that support RGB. |
| `rgb_color`<br>`[r, g, b]` or `null` | no | The colour for RGB lights when `prefer_rgb_color` is on. The schedule sensor's `rgb_color` attribute is the colour temperature converted to RGB. Ignored if `prefer_rgb_color` is off. |
| `rgb_color_tolerance`<br>0–100; default `10` | no | A light within this much of `rgb_color` on every channel isn't sent anything. |
| `transition`<br>seconds, 0–300 | yes | How long the change takes. Two-step bulbs spend half of it on brightness and half on colour. |
| `two_step_label`<br>label ID; default `no_combined_transition` | no | Lights or devices with this label are sent two commands. See [two-step bulbs](#two-step-bulbs). |
| `zone_device_id`<br>zone device ID | no | The zone to record the change in. Without it, FLARE records nothing and doesn't leave any light alone. |

### Brightness levels

| Value | Effect |
|---|---|
| `1`–`255` | Sets the light to this brightness. |
| `0` | Turns the light off. |
| `null` or `false` | Leaves the light alone, whether it's on or off. |

### Response data

Optional. With `response_variable`, the response is what was sent, in the same shape as
[`compute_lighting_groups`](#flarecompute_lighting_groups) returns.

## `flare.turn_off`

Use this action to turn lights off and record that FLARE did it, so FLARE doesn't treat them
as changed by someone else.

```yaml
action: flare.turn_off
data:
  entities: [light.kitchen_1, light.kitchen_2]
  transition: 15
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
```

### Fields

| Field | Required | Description |
|---|---|---|
| `entities`<br>list of light entity IDs | yes | The lights to turn off. |
| `transition`<br>seconds, 0–300; default `0` | no | How long the change takes. |
| `zone_device_id`<br>zone device ID | no | The zone to record the turn-off in. Without it, FLARE records nothing. |

### Good to know

- It turns off every light it's given, including lights someone else has changed. To turn off
  only the lights FLARE is still setting, call [`claims_check`](#flareclaims_check) first.
- Use it rather than `light.turn_off`, which records nothing, so FLARE would treat the lights
  as switched off by someone else.

## `flare.compute_lighting_groups`

Use this action to find out what [`apply_lighting`](#flareapply_lighting) would send, without
sending it. It takes the same fields as `apply_lighting`, except `transition`.

```yaml
action: flare.compute_lighting_groups
data:
  entities: [light.kitchen_1, light.kitchen_2]
  brightness: 200
  color_temp_kelvin: 3200
  brightness_levels: { light.kitchen_2: 100 }
response_variable: plan
```

### Response data

`groups` is a list with one entry for each brightness being sent, and each entry has these
fields:

- `brightness`: The brightness the group's lights are sent, or `0` for lights being turned
  off.
- `needing_off`: Lights that need turning off.
- `combined`: Lights sent brightness and colour temperature in one command.
- `two_step`: Lights sent brightness and colour temperature as two commands.
- `combined_rgb`, `two_step_rgb`: The same, for lights sent `rgb_color`.

Lights that are unavailable, already close to the target, or changed by someone else aren't
in any list.

```yaml
groups:
  - brightness: 200
    needing_off: []
    combined: [light.kitchen_1]
    two_step: []
    combined_rgb: []
    two_step_rgb: []
  - brightness: 100
    needing_off: []
    combined: []
    two_step: [light.kitchen_2]
    combined_rgb: []
    two_step_rgb: []
```

## `flare.compute_curve`

Use this action to work out the curve's phase, brightness and colour at any moment, for phase
start times and curve settings you give it, without needing a schedule.

```yaml
action: flare.compute_curve
data:
  morning: "{{ today_at('06:00') | as_timestamp }}"
  day: "{{ today_at('08:00') | as_timestamp }}"
  evening: "{{ today_at('18:00') | as_timestamp }}"
  night: "{{ today_at('22:00') | as_timestamp }}"
  evening_brightness: 150
  at: "{{ today_at('20:00') | as_timestamp }}"
response_variable: curve
```

### Fields

| Field | Required | Description |
|---|---|---|
| `at`<br>Unix timestamp; default now | no | The moment to work out the values for. |
| `day`, `evening`, `morning`, `night`<br>Unix timestamp | yes | When each phase starts today. |
| `<phase>_brightness`<br>0–255; default Morning 255, Day 255, Evening 180, Night 80 | no | The phase's brightness. |
| `<phase>_brightness_transition`<br>minutes, 0–1440; default Morning 60, Day 65, Evening 60, Night 30 | no | How long before the phase ends its brightness starts changing to the next phase's. |
| `<phase>_kelvin`<br>Kelvin, 1000–10000; default Morning 6667, Day 6667, Evening 3200, Night 2700 | no | The phase's colour temperature. |
| `<phase>_kelvin_transition`<br>minutes, 0–1440; default Morning 60, Day 1440, Evening 60, Night 30 | no | How long before the phase ends its colour temperature starts changing to the next phase's. |

`<phase>` is `morning`, `day`, `evening` or `night`, so `evening_brightness` is Evening's
brightness. The defaults are the values a new schedule starts with, and
[transitions](../schedules/#transitions) explains how a transition shapes the curve.

### Response data

- `phase`: `Morning`, `Day`, `Evening` or `Night`.
- `brightness`: The brightness, 0–255.
- `kelvin`: The colour temperature, in Kelvin.
- `rgb_color`: The colour temperature converted to RGB, as `[r, g, b]`.

```yaml
phase: Evening
brightness: 150
kelvin: 3200
rgb_color: [255, 184, 123]
```

## `flare.claims_check`

Use this action to find out whether FLARE would leave each light alone, for lights you set
yourself with [override protection](../zones/#override-protection). It changes nothing.

```yaml
action: flare.claims_check
data:
  entities: [light.kitchen_1]
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
response_variable: check
```

### Fields

| Field | Required | Description |
|---|---|---|
| `brightness_tolerance`<br>0–50; default `2` | no | A light within this much of a claimed brightness matches it. |
| `color_temp_tolerance`<br>Kelvin, 0–500; default `10` | no | A light within this many Kelvin of a claimed colour temperature matches it. |
| `entities`<br>list of entity IDs | yes | The entities to check. |
| `rgb_color_tolerance`<br>0–100; default `10` | no | A light within this much of a claimed RGB colour on every channel matches it. |
| `zone_device_id`<br>zone device ID | yes | The zone whose claims to check against. |

### Response data

`results` is keyed by entity ID, and each entry has these fields:

- `blocked`: `true` if FLARE would leave the entity alone.
- `status`: `controlled`, `overridden`, `untracked`, `off` or `unavailable`. See
  [inspecting tracked state](../zones/#inspecting-tracked-state).
- `matched_via`: Which claim the entity matched, and how: `latest-context`, `latest-value`,
  `observed-context` or `observed-value`. `null` if it matched neither.
- `zone`: The zone's name.

```yaml
results:
  light.kitchen_1:
    blocked: false
    status: controlled
    matched_via: latest-context
    zone: Kitchen
```

## `flare.claims_record`

Use this action to record a change you're about to make, so a later
[`claims_check`](#flareclaims_check) treats it as FLARE's. Call it just **before** you change
the entities, with the values you're about to send.

```yaml
action: flare.claims_record
data:
  entities: [light.kitchen_1]
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
  targets:
    light.kitchen_1: { brightness: 200, color_temp_kelvin: 3000 }
```

### Fields

| Field | Required | Description |
|---|---|---|
| `entities`<br>list of entity IDs | yes | The entities you're about to change. |
| `targets`<br>map of entity ID to values | no | What you're about to send each entity: `brightness` and either `color_temp_kelvin` or `rgb_color`. |
| `zone_device_id`<br>zone device ID | yes | The zone to record the claim in. |

### Response data

Optional. `recorded` lists the entities a claim was recorded for.

### Good to know

- Without `targets`, FLARE can only match the change by its context, which Home Assistant
  drops after five seconds. A bulb that's slower than that to report back is then treated as
  changed by someone else.
- A light running an effect that keeps changing its colour won't match its claim. Use a scene
  for it instead, or hand it over with a `null` brightness in the blueprint.

## `flare.claims_clear`

Use this action to discard claims, so FLARE sets the entities again on its next update. It's
for a light that's overridden in a room that never goes fully dark. A zone's **Clear** button
does the same for every light in the zone.

```yaml
action: flare.claims_clear
data:
  entities: [light.kitchen_1]
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
```

### Fields

| Field | Required | Description |
|---|---|---|
| `entities`<br>list of entity IDs | yes | The entities to clear. |
| `zone_device_id`<br>zone device ID | yes | The zone to clear them from. |

### Response data

Optional. `cleared` lists the entities passed in.

## `flare.claims_override`

Use this action to mark lights as changed by someone else, so FLARE leaves them alone.

You don't usually need it. When something other than FLARE changes a light that FLARE is
driving, FLARE notices on its own and leaves the light alone. It's for lights FLARE isn't
driving yet, such as when your automation turns lights on in a dark room and you want FLARE to
leave them as they are. Without it, the room's FLARE automation sets those lights back to the
curve on its next update.

It marks each entity whether it's on or off. A light marked this way stays overridden until its
zone goes dark, its claims are cleared, or a forced `flare.apply_lighting` takes it back.
Flares call it before turning a room off or setting it to a brightness or colour.

```yaml
action: flare.claims_override
data:
  entities: [light.kitchen_1]
  zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
```

### Fields

| Field | Required | Description |
|---|---|---|
| `entities`<br>list of entity IDs | yes | The entities to mark. |
| `zone_device_id`<br>zone device ID | yes | The zone to mark them in. |

### Response data

Optional. `overridden` lists the entities passed in.

## `flare.compute_scene_coverage`

Use this action to find out which of a set of lights a scene sets, so you can apply the scene
and set the other lights yourself.

```yaml
action: flare.compute_scene_coverage
data:
  scene_entity_id: scene.kitchen_night
  scope_entities: [light.kitchen_1, light.kitchen_2, light.kitchen_strip]
  target_entities: [light.kitchen_1, light.kitchen_2]
response_variable: coverage
```

### Fields

| Field | Required | Description |
|---|---|---|
| `scene_entity_id`<br>scene entity ID | yes | The scene to check. |
| `scope_entities`<br>list of entity IDs | yes | Every entity the scene is allowed to set, usually the room's lights and other entities on the same devices. |
| `target_entities`<br>list of entity IDs | yes | The lights to check. |

### Response data

- `scene_valid`: `true` if the scene exists and every entity it sets is in `scope_entities`.
- `scene_active`: The same as `scene_valid`.
- `covered_entities`: The entities the scene sets.
- `uncovered_entities`: The entries in `target_entities` that the scene doesn't set. If
  `scene_valid` is `false`, this is all of them.

```yaml
scene_active: true
scene_valid: true
covered_entities: [light.kitchen_1]
uncovered_entities: [light.kitchen_2]
```

## `flare.export_schedule`

Use this action to get a schedule's settings as YAML, in the format described under
[copying a schedule](../schedules/#copying-a-schedule).

```yaml
action: flare.export_schedule
data:
  schedule_device_id: "{{ device_id('sensor.home_flare') }}"
response_variable: exported
```

### Fields

| Field | Required | Description |
|---|---|---|
| `schedule_device_id`<br>schedule device ID | yes | The schedule to export. |

### Response data

- `schedule`: The schedule as YAML text, keyed by phase.

## `flare.import_schedule`

Use this action to set a schedule from YAML, in the format described under
[copying a schedule](../schedules/#copying-a-schedule).

```yaml
action: flare.import_schedule
data:
  schedule_device_id: "{{ device_id('sensor.home_flare') }}"
  schedule:
    night:
      time: "23:00"
```

This moves the start of Night to 23:00 and leaves every other setting as it is.

### Fields

| Field | Required | Description |
|---|---|---|
| `schedule`<br>YAML text, or YAML written in the call | yes | The settings to apply, keyed by phase. Any setting it leaves out keeps its current value. |
| `schedule_device_id`<br>schedule device ID | yes | The schedule to set. |

### Good to know

- If any part of `schedule` has an error, such as an unknown setting, an invalid time or a
  value out of range, none of it is applied, and the error message says what's wrong.

## Two-step bulbs

Some bulbs can't change brightness and colour temperature in one command: they jump to the new
value, or ignore one of the two. FLARE sends these bulbs two commands, brightness first and
then colour, each taking half the transition. It recognises them in two ways:

- **By make and model**, from the **Two-step bulb models** field under **FLARE → Zones →
  Configure**. It holds one pattern per line, matched case-insensitively against
  `"<manufacturer> <model>"`, and `*` matches anything, so `*TRADFRI bulb*` and `IKEA*` both
  work. The field is pre-filled with FLARE's default patterns. Your saved list replaces those
  defaults entirely, so you can remove a pattern as well as add one. If you save the field
  empty, FLARE uses the defaults again.
- **By label**: give the light or its device a label created with the name
  `no_combined_transition`. FLARE matches the label's ID, which comes from the name it was
  created with, so renaming another label to this won't work.

Once you've saved your own list, a later FLARE release that adds a pattern won't change it,
so you'll need to add new bulbs yourself. Keep patterns specific, because a bulb that doesn't
need two commands transitions less smoothly when it gets them.

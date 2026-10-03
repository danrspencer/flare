---
title: Schedules
parent: Reference
nav_order: 2
permalink: /reference/schedules/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Schedules
{: .no_toc }

A schedule sets when each of the four phases starts, and the brightness and colour temperature
in each phase. Adding FLARE creates your first schedule. You can add more, for example for rooms
that need different timing, under **Settings → Devices & Services → FLARE Schedules → Add
schedule sensor**.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## A schedule's entities

| Entity | Description |
|---|---|
| `sensor.<name>_flare` | The current phase, brightness and colour. See [the schedule sensor](#the-schedule-sensor). |
| `event.<name>_flare_phase` | Fires when the phase changes, including a manual override. The event type is the new phase's name. |
| `select.<name>_flare_phase` | Overrides the phase. `Auto` (the default) follows the schedule; choosing a phase holds it until the schedule reaches its next phase. |
| `switch.<name>_sticky_phase_override` | When on, an override stays until you set the phase back to `Auto`. |
| `time.<name>_morning_time`, `day_time`, `night_time` | When Morning, Day and Night start. Defaults: 06:00, 08:00, 22:00. |
| `time.<name>_evening_earliest_time`, `evening_latest_time` | Evening starts at sunset, but no earlier or later than these. Defaults: 17:00, 20:00. |
| `number.<name>_<phase>_brightness` | The phase's brightness, 0–255. At `0`, the phase turns the lights off. |
| `number.<name>_<phase>_kelvin` | The phase's colour temperature, 1000–10000 K. |
| `number.<name>_<phase>_brightness_transition`, `_kelvin_transition` | The phase's transitions, in minutes. See [transitions](#transitions). |

A change to any of these takes effect within a few seconds. To remove a schedule, delete its
device.

## The schedule sensor

| Attribute | Description |
|---|---|
| state | The phase: `Morning`, `Day`, `Evening` or `Night`. |
| `brightness` | The current brightness, 0–255. |
| `color_temp` | The current colour temperature, in Kelvin. |
| `rgb_color` | The current colour temperature as `[r, g, b]`. |
| `morning_start`, `day_start`, `evening_start`, `night_start` | Today's phase start times, as timestamps. |
| `evening_earliest`, `evening_latest` | Today's earliest and latest Evening start, as timestamps. |
| `points` | The whole day as 289 `{t, brightness, kelvin}` samples, used by the chart. |

The sensor updates every minute. While the phase is overridden, every attribute except `points`
follows the overridden phase.

## Transitions

A phase's transition is how long before the phase ends its brightness or colour starts changing
to the next phase's. The change finishes when the next phase starts: if Morning starts at 06:00,
the lights reach Morning's values at 06:00. For example, `day_kelvin_transition` is how long
before the end of Day the colour starts changing to Evening's.

- A transition of `0` switches at the boundary.
- A transition longer than its phase covers the whole phase.

Brightness and colour have separate transitions. By default, Day's colour transition is 1440
minutes, so its colour changes across the whole of Day, while its brightness changes only in
roughly the last hour.

Night runs past midnight, so its transition is in the minutes before Morning starts.

## Copying a schedule

A schedule's settings can be copied as YAML:

```yaml
morning:
  time: "06:00"
  brightness: 255
  kelvin: 6667
  brightness_transition: 30
  kelvin_transition: 30
evening:
  earliest: "17:00"
  latest: "20:00"
  brightness: 180
night:
  kelvin: 2000
```

Each phase takes `brightness`, `kelvin`, `brightness_transition` and `kelvin_transition`, and a
start `time`. Evening takes `earliest` and `latest` instead of `time`. When you apply a
schedule, settings it leaves out keep their current values.

To copy or apply a schedule, use any of:

- **Copy** and **Paste** at the bottom of each schedule on the [dashboard](../../dashboard/).
- **Reconfigure** in the schedule's three-dot menu under **FLARE Schedules**, which shows the
  schedule as text that you can replace and submit.
- The services [`flare.export_schedule` and `flare.import_schedule`](../services/#flareexport_schedule).
- **Copy schedule** and **Load** in the [curve playground](../../playground/).

A schedule with an error in it, such as an unknown setting, an invalid time or a value out of
range, isn't applied. The error message says what's wrong.

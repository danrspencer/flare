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

A schedule is the day's lighting: when each of the four phases starts, and the brightness and
colour temperature in each. Adding FLARE creates the first one; add more from **Settings →
Devices & Services → FLARE Schedules → Add schedule sensor**, for parts of the house that
should keep a different rhythm.

The name you give a schedule becomes part of its entity IDs (`sensor.home_flare`), and stays
there if you rename the device later.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## A schedule's entities

| Entity | |
|---|---|
| `sensor.<name>_flare` | The current phase, with the brightness and colour for right now — see [its attributes](#the-schedule-sensor) |
| `event.<name>_flare_phase` | Fires with the phase's name each time the phase changes, a manual override included |
| `select.<name>_flare_phase` | Overrides the phase: `Auto` (the default) or a phase to hold. An override lasts until the schedule next moves on — pin Day during Evening and it still becomes Night when Evening would have ended |
| `switch.<name>_sticky_phase_override` | Keeps an override until you set it back to `Auto` yourself |
| `time.<name>_morning_time`, `day_time`, `night_time` | When Morning, Day and Night start. Defaults 06:00, 08:00 and 22:00 |
| `time.<name>_evening_earliest_time`, `evening_latest_time` | Evening starts at sunset, but no earlier and no later than these. Defaults 17:00 and 20:00 |
| `number.<name>_<phase>_brightness` | Each phase's brightness, 0–255 |
| `number.<name>_<phase>_kelvin` | Each phase's colour temperature, 1000–10000 K |
| `number.<name>_<phase>_brightness_transition`, `_kelvin_transition` | How long, in minutes, each phase takes to ease into the next — see [transitions](#transitions) |

Changing any of them takes effect within seconds. The time, number and switch entities sit
under the device's Configuration section; set them from the device page, a dashboard, or an
automation. Removing a schedule means removing its device.

## The schedule sensor

| Attribute | |
|---|---|
| state | The phase: `Morning`, `Day`, `Evening` or `Night` |
| `brightness` | 0–255 |
| `color_temp` | Kelvin |
| `rgb_color` | `[r, g, b]`, the colour temperature as RGB |
| `morning_start`, `day_start`, `evening_start`, `night_start` | Today's phase boundaries, as timestamps |
| `evening_earliest`, `evening_latest` | The limits Evening's start was held between |
| `points` | The whole day, for the chart: 289 `{t, brightness, kelvin}` samples |

It updates every minute. `points` shows the schedule itself, so it ignores a phase override;
everything else follows it.

To act on a phase change, trigger on `event.<name>_flare_phase`.

## Transitions

Each phase holds its own brightness and colour, then eases into the next phase's over the last
few minutes of its own span. The length is named for the phase it runs in:
`day_kelvin_transition` is how long before Day ends to start easing to Evening's colour.

A transition finishes *at* the boundary, so with Morning starting at 06:00 the lights reach
Morning's values at 06:00.

- **`0` is a hard cut**, for a boundary you want to see.
- **A transition longer than its phase covers the whole phase.** Day's colour transition
  defaults to 1440 minutes, which is why the default Day eases from Morning's colour to
  Evening's all afternoon.

Brightness and colour have their own lengths: by default, Day's colour changes all afternoon
while its brightness only changes in the last hour.

{: .note }
> Night runs past midnight, so its transition happens at the end of the early-morning
> stretch: in the minutes before Morning, not before midnight.

## Copying a schedule

A schedule's settings copy out as YAML, keyed by phase:

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

Each phase takes `brightness`, `kelvin`, `brightness_transition` and `kelvin_transition`,
plus its start `time` — or, for Evening, `earliest` and `latest`. When you paste one in,
anything it leaves out keeps its current value.

To copy one out or paste one in:

- **Copy** and **Paste**, at the bottom of each schedule in the [dashboard](../../dashboard/).
- **Reconfigure**, from the schedule's three-dot menu under **FLARE Schedules**, which shows
  the schedule in a text box to copy, or to replace and submit.
- [`flare.export_schedule` and `flare.import_schedule`](../services/#flareexport_schedule-and-flareimport_schedule).
- **Copy schedule** and **Load** in the [curve playground](../../playground/), to try one out
  first.

A schedule with a mistake in it — an unknown phase or setting, a time that isn't a time, a
value out of range — changes nothing, and the message says what's wrong.

---
title: Dashboard
nav_order: 4
permalink: /dashboard/
---

# Dashboard

FLARE comes with two dashboard views. Open the dashboard you want them on, choose **Edit
dashboard**, then **Raw configuration editor** from the three-dot menu, and add:

```yaml
views:
  - title: Lighting
    strategy:
      type: custom:flare-schedule
  - title: Zones
    strategy:
      type: custom:flare-zone
```

- **Lighting** has a section for each schedule: its curve, its phase override, and all its
  settings.
- **Zones** has a section for each zone: which lights FLARE is setting, which ones something
  else has changed, and a **Clear** button.

Both views find their own entities. Schedules and zones you add later appear on their own.

![The FLARE Lighting view: the day's curve, a phase override, the schedule times, and
the curve and transition values for each phase]({{ '/assets/img/dashboard-section.png' | relative_url }})

## One schedule per view

To show one schedule in a view, add `sensor`:

```yaml
views:
  - title: Downstairs
    strategy:
      type: custom:flare-schedule
      sensor: downstairs
  - title: Upstairs
    strategy:
      type: custom:flare-schedule
      sensor: upstairs
```

`sensor` is the part of the schedule sensor's entity ID before `_flare`: `downstairs` for
`sensor.downstairs_flare`. The full entity ID also works. If the schedule doesn't exist, the
view says so and lists the ones that do.

## The chart on its own

To add only the curve chart to a dashboard: on Home Assistant 2026.6 or newer, add a card,
open the **By entity** tab and choose your schedule sensor. **FLARE Curve** is listed under
*Community*. On older versions, add a **Manual** card:

```yaml
type: custom:flare-curve-card
sensor: home
```

## The Lighting view

- **Colours** show the phase: Morning blue, Day yellow, Evening orange, Night indigo.
- **Icons** show the setting: brightness, colour temperature, or an hourglass for a
  transition.

Each row under **Curve** has a phase's colour temperature and brightness. Both sliders are
filled in the colour the phase sets, and the brightness slider's fill shows how bright it is.

**Copy** and **Paste**, at the bottom of each schedule, copy the schedule's settings as text
or apply settings you paste in. See
[copying a schedule](../reference/schedules/#copying-a-schedule).

## Editing the views

Both views are rebuilt each time they load, which is how they pick up new schedules, zones and
changes to FLARE. To edit a view by hand, choose **Take control** from the dashboard's
three-dot menu.

{: .note }
> Take control can't be undone. After it, the view no longer picks up new schedules or zones,
> or changes to FLARE.

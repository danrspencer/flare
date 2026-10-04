---
title: Dashboard
nav_order: 4
permalink: /dashboard/
---

# Dashboard

FLARE comes with a ready-made dashboard, which builds itself from your schedules and zones.
Adding FLARE offers to create it: **Lighting**, in the sidebar, with a view for each schedule
and one for your zones. A schedule or zone you add later appears without you touching it.

To add it later, or to a dashboard of your own, set the dashboard's YAML (**Edit dashboard** →
the three-dot menu → **Raw configuration editor**) to:

```yaml
strategy:
  type: custom:flare
```

## Adding the views to another dashboard

The views it's made of can also go in a dashboard of your own. Open it, then **Edit
dashboard** → the three-dot menu → **Raw configuration editor**, and add:

```yaml
views:
  - title: Lighting
    strategy:
      type: custom:flare-schedule
  - title: Zones
    strategy:
      type: custom:flare-zone
```

- **Lighting** — the day's curve and every schedule and curve setting, one section per
  schedule sensor.
- **Zones** — which lights FLARE is driving, which ones something else has taken
  over, and a Clear button to hand them back.

There's nothing to fill in: both views find their own entities, and a schedule sensor or zone
you add later appears without you touching the dashboard again.

![The FLARE Lighting view: the day's curve, a phase override, the schedule times, and
the curve and transition values for each phase]({{ '/assets/img/dashboard-section.png' | relative_url }})

## One schedule per view

Once you have more than one schedule, a view each often reads better than all of them
stacked. Add `sensor:` to pick one:

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

`sensor` is the part before `_flare` in the schedule sensor's entity ID, such as
`downstairs` for `sensor.downstairs_flare`, though the full entity ID works too. If you name
one that doesn't exist, the view says so and lists the schedules you do have.

## Just the chart

To put the curve chart on a dashboard of your own: on Home Assistant 2026.6 or newer, add a
card, open the **By entity** tab and pick your schedule sensor — **FLARE Curve** appears
under *Community* with a preview. On older versions, add a **Manual** card:

```yaml
type: custom:flare-curve-card
sensor: home
```

`sensor` is the part before `_flare` in the schedule sensor's entity ID.

## Reading the Lighting view

Twenty-five near-identical controls is a lot to scan, so two things are colour-coded:

- **Colour is the phase** — Morning blue, Day yellow, Evening orange, Night indigo,
  wherever that phase appears.
- **Icon is the channel** — brightness, colour temperature, or an hourglass for
  transitions.

Each Curve row is a colour temperature and a brightness, in that order, and together they
preview what the light will look like: both sliders are painted in the colour that phase
sets, and how far the brightness one fills is how bright it will be. It's the same idea as
Home Assistant's own brightness slider for a light.

**Copy or paste**, at the bottom of each schedule, copies that schedule as text, or applies
one you paste in, so a schedule can be backed up, shared, or copied onto another. See
[copying a schedule](../reference/schedules/#copying-a-schedule).

## Changing it

Both views rebuild themselves each time they load, so they pick up changes to FLARE and new
schedules or zones on their own. If you'd rather own the layout and edit it by hand, use
**Take control** from the dashboard's three-dot menu.

{: .note }
> Take control is one-way. Once you've taken control a view stops picking up changes to
> FLARE's layout, and newly added schedule sensors or zones won't appear on their own.

---
title: Dashboard
nav_order: 4
permalink: /dashboard/
---

# Dashboard

FLARE ships two ready-made dashboard views. Add them once and they build themselves.

Open the dashboard you want them on, then **Edit dashboard** → the three-dot menu →
**Raw configuration editor**, and add:

```yaml
views:
  - title: Lighting
    strategy:
      type: custom:flare-schedule
  - title: Tracking
    strategy:
      type: custom:flare-tracking
```

- **Lighting** — the day's curve and every schedule and curve setting, one section per
  schedule sensor.
- **Tracking** — which lights FLARE is driving, which ones something else has taken
  over, and a Clear button to hand them back.

There's nothing to fill in. Both find their own entities, and a schedule or tracking
scope you add later appears without you touching the dashboard again.

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

`sensor` is the part before `_flare` in the schedule sensor's entity ID —
`downstairs` for `sensor.downstairs_flare`. The full entity ID works too. Name one that
doesn't exist and the view says so, and lists the schedules you do have.

## Reading the Lighting view

Twenty-five near-identical controls is a lot to scan, so two things are colour-coded:

- **Colour is the phase** — Morning blue, Day yellow, Evening orange, Night indigo,
  wherever that phase appears. It follows the colour temperature each phase reaches, so
  it lines up with the curve above.
- **Icon is the channel** — brightness, colour temperature, or an hourglass for
  transitions.

Each Curve row is a colour temperature and a brightness, in that order, and together they
preview what the light will look like: the colour temperature slider is painted in the
colour it sets, and the brightness slider beside it takes that same colour and fades it by
how bright it is.

## Changing it

Both views are generated fresh each time they load, which is what keeps them up to date
when FLARE changes. If you'd rather own the layout and edit it by hand, use **Take
control** from the dashboard's three-dot menu.

{: .note }
> Take control is one-way. Once you've taken control a view stops picking up changes to
> FLARE's layout, and newly added schedules or scopes won't appear on their own.

{: .note }
> Upgrading from 0.12 or 0.13? The schedule view was `custom:flare` then. Change the
> type to `custom:flare-schedule` — a view still using the old name shows "Custom
> element doesn't exist".

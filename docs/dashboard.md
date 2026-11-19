---
title: Dashboard
nav_order: 4
permalink: /dashboard/
---

# Dashboard

FLARE comes with a ready-made dashboard: a view for each schedule, and one for your rooms. It
builds itself from your schedules and rooms each time it loads, so any schedule or room you add
later appears on its own.

Add it from **Settings → Dashboards → Add dashboard**: pick **FLARE Lighting**, then give it a
name and an icon. FLARE's logo is in the icon picker as `flare:logo`.

- **A schedule's view** shows the day's curve and every schedule and curve setting.
- **Overrides** shows how many lights FLARE is controlling, which lights have been taken over,
  and the last 24 hours of room activity.

![A schedule's view: the day's curve, a phase override, the schedule times, and
the curve and transition values for each phase]({{ '/assets/img/dashboard-section.png' | relative_url }})

## In your own dashboard

The same views can go in a dashboard of your own. Open it, then **Edit dashboard** → the
three-dot menu → **Raw configuration editor**, and add:

```yaml
views:
  - title: Lighting
    strategy:
      type: custom:flare-schedule
  - title: Overrides
    strategy:
      type: custom:flare-lights
```

Like the ready-made dashboard, both views find their own entities each time they load.
`custom:flare-schedule` shows every schedule, one after another. To give each schedule its own
view instead, add `sensor:`:

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

`sensor` is the part before `_flare` in the schedule sensor's entity ID (such as `downstairs` for
`sensor.downstairs_flare`), or the full entity ID if you've renamed the sensor. If `sensor`
doesn't match any schedule, the view tells you so and lists the schedules you do have.

## Just the chart

To put the curve chart on a dashboard of your own, add a card, open the **By entity** tab, and
pick your schedule sensor — **FLARE Curve** appears under *Community* with a preview. Or add a
**Manual** card in YAML:

```yaml
type: custom:flare-curve-card
sensor: home
```

`sensor` is the part before `_flare` in the schedule sensor's entity ID, or the full entity ID if
you've renamed the sensor.

## Reading a schedule's view

With over twenty controls on a schedule's view, two things are colour-coded so you can scan them
at a glance:

- **Colour is the phase** — Morning blue, Day amber, Evening deep orange, Night indigo,
  wherever that phase appears.
- **Icon is the channel** — brightness, colour temperature, or an hourglass for
  transitions.

Each **Curve** row pairs a colour temperature slider with a brightness slider in that order, so
together they preview what the light will look like: both sliders are painted in the colour that
phase sets, and how far the brightness slider fills shows how bright the light will be.

**Copy or paste**, at the bottom of each schedule, copies that schedule as text or applies one
you paste in, so a schedule can be backed up, shared, or copied onto another schedule. See
[copying a schedule]({{ site.baseurl }}/reference/schedules/#copying-a-schedule).

## Reading the Overrides view

- **All lights** at the top shows how many lights FLARE is controlling across the house, how many
  something else has taken over, and a **Clear all** button to hand every light back to FLARE at
  once.
- **Area cards**, grouped by floor, list each room automation's lights with overridden lights
  first. The card header shows the area's controlled and overridden counts along with **Clear
  all** for that area, and clicking the area's name opens its Home Assistant area page.
- **Each light row** shows its status, what FLARE last asked it for, and what it is currently
  showing (with differing values highlighted in red), plus its own **Clear** button. Values in
  amber with an info icon beside them mean the light isn't showing FLARE's last change yet, but
  isn't overridden either: on a `controlled` light the command is still taking effect and FLARE
  keeps retrying it, while on a `mismatched` light it will become `overridden` if it doesn't
  match again within 30 seconds. Hover over or tap the info icon to see what FLARE asked for,
  what it last saw the light confirm, and what the light is showing. Click the light's name to
  open its more-info dialog. Lights FLARE isn't currently driving stay hidden behind a **Show
  *N* untracked** row at the bottom of the list.
- **Activity** (beside the areas, or on a separate tab on narrow screens) shows the last 24 hours
  of room events. Entries are colour-coded — blue when a room starts controlling its lights, amber
  when something else overrides a light, and grey when a room lets them go — and the filter buttons
  at the top show one kind at a time.

## Changing it

If you'd rather own the layout and edit it by hand, use **Take control** from the dashboard's
three-dot menu.

{: .note }
> Take control is one-way. Once you've taken control, the dashboard no longer rebuilds itself,
> so it won't pick up changes to FLARE's layout, and schedules or rooms you add later won't
> appear on their own.

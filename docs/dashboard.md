---
title: Dashboard
nav_order: 4
permalink: /dashboard/
---

# Dashboard

FLARE ships a ready-made dashboard view. Add it once and it builds itself: one section
per schedule sensor, with the curve, a phase override, the five schedule times, the
eight curve values and the eight transition times.

Open the dashboard you want it on, then **Edit dashboard** → the three-dot menu →
**Raw configuration editor**, and add:

```yaml
views:
  - title: Lighting
    strategy:
      type: custom:flare
```

That's the whole configuration. There's nothing to fill in — it finds your schedule
sensors itself, and a schedule you add later appears without you touching the dashboard
again.

{: .tip }
> **Just want the chart?** On Home Assistant 2026.6 and newer, add a card, open the
> **By entity** tab and pick your schedule sensor — **FLARE Curve** is offered under
> *Community*, with a live preview.

## What you get

- **The curve** — the day's brightness and colour, with a marker at the current time.
- **Override** — force a phase, plus a Sticky switch to hold it until you change it back.
- **Schedule** — the five times that bound the phases. Tap one to set it.
- **Curve** — brightness and colour temperature for each phase, one phase per row. Drag
  to set.
- **Transitions** — how long before each phase ends to start easing into the next. Tap
  one to type a value.

The heading shows the current phase, brightness and colour temperature, and adds a chip
when a manual override is active.

## Reading it at a glance

- **Colour is the phase** — Morning blue, Day yellow, Evening orange, Night indigo,
  wherever that phase appears. It follows the colour temperature each phase reaches, so
  it lines up with the curve above.
- **Icon is the channel** — brightness, colour temperature, or an hourglass for
  transitions.

The colour-temperature sliders are painted in the colour they set, and change colour as
you drag them.

## Changing it

The view is generated fresh each time it loads, which is what keeps it up to date when
FLARE changes. If you'd rather own the layout and edit it by hand, use **Take control**
from the dashboard's three-dot menu — that turns the generated view into ordinary cards
you can rearrange.

{: .note }
> Take control is one-way. Once you've taken control the view stops picking up changes
> to FLARE's layout, and new schedule sensors won't appear on their own.

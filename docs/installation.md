---
title: Quickstart
nav_order: 2
permalink: /installation/
---

# Quickstart
{: .no_toc }

Five minutes to a room running on the curve.

{: .note }
> **Prerequisites** — Home Assistant 2026.4.0 or newer, [HACS](https://hacs.xyz) installed,
> and your lights assigned to areas, so FLARE can set itself up room by room.

1. TOC
{:toc}

---

## Step 1 — install via HACS

[![Open your Home Assistant instance and open FLARE in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=danrspencer&repository=flare&category=integration)

The button opens FLARE in HACS on your Home Assistant, where you can download it.

Or add it by hand: HACS → three-dot menu → **Custom repositories**. Add:

```
https://github.com/danrspencer/flare
```

with type **Integration**. Then find **FLARE** in the HACS list and download it.

## Step 2 — restart, then add FLARE

Restart Home Assistant, then **Settings → Devices & Services → Add Integration → FLARE**.

It asks two things:

- **A name for your first schedule** — Home, unless you change it. A
  [schedule]({{ site.baseurl }}/reference/schedules/) is the day's lighting: when each phase
  starts, and how bright and warm it is. One for the whole house is fine to start with. Pick
  a name you're happy to keep: it becomes part of the schedule's entity IDs.
- **Which rooms to set up** — every area with lights is offered, pre-selected, and each one
  you keep becomes a [zone]({{ site.baseurl }}/reference/zones/), named after the room. A zone
  keeps track of which lights FLARE is driving in that room, which is how it knows to leave
  alone a light you've changed yourself.

You can add more schedules and zones later, from **FLARE Schedules** and **FLARE Zones**.

{: .note }
> A bug in Home Assistant 2026.9 and earlier makes adding another schedule or zone ask you
> to pick between FLARE Schedules and FLARE Zones first. Pick the one that matches what you're
> adding; Home Assistant 2026.10 fixes this.

## Step 3 — install the blueprint and create an automation

FLARE will spot that its blueprint isn't installed and offer it in
**Settings → System → Repairs**. Press **Fix** and it downloads it.

Create an automation from it and fill in three things:

| Input | What to put |
|---|---|
| **Schedule** | The schedule from step 2 — Home, unless you named it something else. |
| **Zone** | The room's zone from step 2 — usually the one named after the room. |
| **Lights & Occupancy** | One target for the room — pick the **area**. Lights inside it get driven; occupancy and motion sensors inside it decide when. |

Those three are all a room needs, because every other input has a working default.

{: .note }
> A room with no occupancy or motion sensor still follows the curve, but never turns its lights on or
> off by itself.

Repeat for each room.

## Step 4 — add the dashboard (optional)

FLARE ships two ready-made views. **Edit dashboard** → the three-dot menu → **Raw
configuration editor**, and add:

```yaml
views:
  - title: Lighting
    strategy:
      type: custom:flare-schedule
  - title: Zones
    strategy:
      type: custom:flare-zone
```

**Lighting** shows the day's curve and every setting of your schedules. **Zones** shows
which lights FLARE is driving and which ones something else has taken over. See
[Dashboard]({{ site.baseurl }}/dashboard/) for more, including adding just the chart.

---

## What now

- Every blueprint input, with defaults: [Blueprint]({{ site.baseurl }}/reference/blueprint/).
- A light not doing what you expect?
  [Why didn't my light change?]({{ site.baseurl }}/reference/blueprint/#why-didnt-my-light-change)
- Want it to behave differently — a weekend lie-in, a holiday schedule?
  [Examples]({{ site.baseurl }}/guides/examples/).

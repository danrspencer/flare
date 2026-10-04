---
title: Quickstart
nav_order: 2
permalink: /installation/
---

# Quickstart
{: .no_toc }

Five minutes to a room running on the curve.

{: .note }
> **Prerequisites** — Home Assistant 2026.10.0 or newer, [HACS](https://hacs.xyz) installed,
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

It asks:

- **How many schedules, and their names.** A [schedule]({{ site.baseurl }}/reference/schedules/)
  is the day's lighting: when each phase starts, and how bright and warm it is. One for the
  whole house is fine to start with; use more if parts of the house should differ, such as one
  per floor. Pick names you're happy to keep: they become part of each schedule's entity IDs.
- **What to set up for each area**, and **which areas**. Every area with lights is listed and
  ticked. With more than one schedule, you pick the schedule each area follows instead.

Each area you set up gets up to three things, named after it. All three is the default, and
what most rooms want:

| | What it does |
|---|---|
| A [zone]({{ site.baseurl }}/reference/zones/) | Keeps track of which lights FLARE is driving there, so it leaves alone a light you've changed yourself. |
| A room automation | Built from the FLARE [blueprint]({{ site.baseurl }}/reference/blueprint/), with the area as its **Lights & Occupancy**: the lights in it follow the schedule, and its occupancy and motion sensors turn them on and off. Called "*Area* Lighting". |
| A [flare]({{ site.baseurl }}/guides/flares/) | A light for the whole room, for voice assistants and HomeKit. |

The zone is always set up. Leave out the flare if you don't use voice assistants or HomeKit,
or the automation too if you'd rather build the room's automation yourself. An area set up
without an automation can be set up again later to add the rest.

With all three, that's everything a room needs. The automation is an ordinary one in **Settings → Automations
& Scenes**, so change any of its other inputs there.

{: .note }
> A room with no occupancy or motion sensor still follows the curve, but never turns its lights on or
> off by itself.

## Step 3 — use your flares (optional)

Expose the flares to HomeKit, Alexa or Google Assistant instead of your bulbs, so "Hey Siri,
turn on the kitchen" brings the kitchen up the way FLARE would. See
[Voice assistants and HomeKit]({{ site.baseurl }}/guides/flares/) for how.

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

## Adding a room later

**Settings → Devices & Services → FLARE → Set up area**. It lists every area with lights that
doesn't have a FLARE automation yet; tick the ones to set up.

The other buttons there add one thing at a time: **Add schedule**, **Add zone** and
**Add flare**.

---

## What now

- Every blueprint input, with defaults: [Blueprint]({{ site.baseurl }}/reference/blueprint/).
- A light not doing what you expect?
  [Why didn't my light change?]({{ site.baseurl }}/reference/blueprint/#why-didnt-my-light-change)
- Want it to behave differently — a weekend lie-in, a holiday schedule?
  [Examples]({{ site.baseurl }}/guides/examples/).
- What each voice command does to a room:
  [Voice assistants and HomeKit]({{ site.baseurl }}/guides/flares/#what-each-command-does).

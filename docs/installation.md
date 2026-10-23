---
title: Quickstart
nav_order: 2
permalink: /installation/
---

# Quickstart
{: .no_toc }

Five minutes to a room running on the curve.

{: .note }
> **Prerequisites** — Home Assistant 2026.10.0 or newer, and [HACS](https://hacs.xyz) installed.
>
> It's best to assign your lights and your occupancy and motion sensors to areas first. FLARE
> works without that, but it sets rooms up area by area, so anything without an area is left out
> until you add it to a room's automation by hand.

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

Restart Home Assistant, then **Settings → Devices & Services → Add Integration → FLARE**, and
choose **Set up schedules and rooms**. (If you'd rather set everything up yourself, or only want
FLARE's parts for your own automations, choose **Skip setup** instead.)

It asks:

- **Your schedules.** A [schedule]({{ site.baseurl }}/reference/schedules/) is the day's
  lighting: when each phase starts, and how bright and warm it is. **One for the whole home**
  (called Home) is the default, and enough for most homes. You can instead choose **one per
  floor** (offered when your home has more than one floor, and named after them), or
  **Custom**, to name the schedules yourself.
  A schedule's name becomes part of its entity IDs, so pick names you're happy to keep.
- **What to set up for each area**, and **which schedule each area follows**. Every area with
  lights is listed, grouped by floor, and starts on the schedule with the same name as its floor,
  or on your first schedule if none matches. To leave an area out, clear its schedule.

None of this is final. You can add or remove schedules later from FLARE's integration page, set
up more areas with **Set up area** (see [Adding a room later](#adding-a-room-later)), and change
which schedule a room follows in its automation.

Each area you set up gets up to three things, named after it. All three is the default, and
what most rooms want:

| | What it does |
|---|---|
| A [zone]({{ site.baseurl }}/reference/zones/) | Keeps track of which lights FLARE is driving there, so it leaves alone a light you've changed yourself. |
| A room automation | Built from the FLARE [blueprint]({{ site.baseurl }}/reference/blueprint/), with the area as its **Lights & Occupancy**: the lights in it follow the schedule, and its occupancy and motion sensors turn them on and off. Called "*Area* Lighting", with a **FLARE** label so you can find them. |
| A [flare]({{ site.baseurl }}/guides/flares/) | A light for the whole room, for voice assistants and HomeKit. |

The zone is always set up. Leave out the flare if you don't use voice assistants and don't
want a light for the whole room. Leave out the automation if you'd rather build it yourself.
The flare is left out with it, because a flare runs the room's automation.

With all three, the room is ready to use. The automation is an ordinary one in **Settings →
Automations & Scenes**, so you can change its inputs there.

{: .note }
> A room with no occupancy or motion sensor still follows the curve, but never turns its lights on or
> off by itself.

## Step 3 — add the dashboard (optional)

**Settings → Dashboards → Add dashboard**, and pick **FLARE Lighting**. It's a dashboard
with a view for each schedule and one for your zones, and it keeps up as you add more. See
[Dashboard]({{ site.baseurl }}/dashboard/).

{: .note }
> **FLARE Lighting** only appears once the page has reloaded after setting FLARE up. Use
> **Reload this page** at the end of setup, or in the repair FLARE raises until a page has loaded
> its dashboard. If it's still missing, reload once more: your browser may show its saved copy of
> the page the first time.

## Adding a room later

**Settings → Devices & Services → FLARE → Set up area**. It lists every area with lights. An area
that already has a zone starts empty, because setting it up again keeps its zone but gives it
another automation and flare, so only pick a schedule for it if it doesn't have them.

The other buttons there add one thing at a time: **Add schedule**, **Add zone** and
**Add flare**.

---

## What now

- Every blueprint input, with defaults: [Blueprint]({{ site.baseurl }}/reference/blueprint/).
- A light not doing what you expect?
  [Why didn't my light change?]({{ site.baseurl }}/reference/blueprint/#why-didnt-my-light-change)
- Want it to behave differently — a weekend lie-in, a holiday schedule?
  [Examples]({{ site.baseurl }}/guides/examples/).
- Using HomeKit, Alexa or Google Assistant? Expose the flares instead of your bulbs:
  [Voice assistants and HomeKit]({{ site.baseurl }}/guides/flares/#exposing-flares-instead-of-your-bulbs).

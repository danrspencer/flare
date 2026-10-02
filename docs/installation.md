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

## Step 1: install with HACS

In HACS, open the three-dot menu, choose **Custom repositories**, and add this repository with
the type **Integration**:

```
https://github.com/danrspencer/flare
```

Then find **FLARE** in HACS and download it.

## Step 2: add FLARE

Restart Home Assistant, then go to **Settings → Devices & Services → Add Integration → FLARE**.
It asks two things:

- **A name for your first schedule.** The default is Home. A
  [schedule]({{ site.baseurl }}/reference/schedules/) sets when each phase starts and how bright
  and warm the light is. One is enough for most homes. The name becomes part of the schedule's
  entity IDs, so pick one you're happy to keep.
- **Which rooms to set up.** Every area with lights is listed and selected. Each one you keep
  becomes a [zone]({{ site.baseurl }}/reference/zones/), named after the room. A zone records
  which lights FLARE is setting, so it can leave alone a light you've changed yourself.

You can add more schedules and zones later under **FLARE Schedules** and **FLARE Zones**.

{: .note }
> A bug in Home Assistant 2026.9 and earlier asks you to choose between FLARE Schedules and
> FLARE Zones when you add another schedule or zone. Choose the one you're adding. Home
> Assistant 2026.10 fixes it.

## Step 3: create a room automation

FLARE offers to install its blueprint under **Settings → System → Repairs**. Press **Fix**.

Then create an automation from the blueprint and fill in:

| Input | What to choose |
|---|---|
| **Schedule** | The schedule from step 2. |
| **Zone** | The room's zone, named after the room. |
| **Lights & Occupancy** | The room's area. FLARE controls the lights in it and uses its occupancy sensors to turn them on and off. |

Everything else has a default. Repeat for each room.

{: .note }
> A room with no occupancy sensor still follows the schedule, but doesn't turn its lights on or
> off.

## Step 4: add the dashboard (optional)

Open a dashboard, choose **Edit dashboard**, then **Raw configuration editor** from the
three-dot menu, and add:

```yaml
views:
  - title: Lighting
    strategy:
      type: custom:flare-schedule
  - title: Zones
    strategy:
      type: custom:flare-zone
```

**Lighting** shows each schedule's curve and settings. **Zones** shows which lights FLARE is
setting and which ones something else has changed. See [Dashboard]({{ site.baseurl }}/dashboard/)
for more.

---

## Next steps

- Every blueprint input and its default: [Blueprint]({{ site.baseurl }}/reference/blueprint/).
- A light not doing what you expect:
  [Why didn't my light change?]({{ site.baseurl }}/reference/blueprint/#why-didnt-my-light-change)
- Changing how FLARE behaves, such as a weekend lie-in or a holiday schedule:
  [Examples]({{ site.baseurl }}/guides/examples/).

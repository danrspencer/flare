---
title: Quickstart
nav_order: 2
permalink: /installation/
---

# Quickstart
{: .no_toc }

Five minutes to a room running on the curve. This covers the standard setup; the
[Reference]({{ site.baseurl }}/reference/) covers everything underneath it.

{: .note }
> **Prerequisites** — Home Assistant 2026.4.0 or newer (the blueprint uses the native
> `occupancy.*` triggers), [HACS](https://hacs.xyz) installed, and your lights assigned to
> areas. Areas aren't strictly required, but FLARE offers to set itself up per room from
> them, which saves most of the work.

1. TOC
{:toc}

---

## Step 1 — install via HACS

HACS → three-dot menu → **Custom repositories**. Add:

```
https://github.com/danrspencer/flare
```

with type **Integration**. Then find **FLARE** in the HACS list and download it.

{: .tip }
> The dashboard card ships inside the integration and registers itself — no Lovelace
> resource to add.

{: .note }
> **Want the beta builds?** FLARE publishes pre-releases between stable versions. You
> won't be offered them unless you ask: HACS adds a **Pre-release** switch for each
> repository you've downloaded, and turning FLARE's on starts offering betas as ordinary
> updates. It ships disabled, so enable the entity first. Leave it alone to stay on
> stable releases only.

## Step 2 — restart, then add FLARE

Restart Home Assistant, then **Settings → Devices & Services → Add Integration → FLARE**.

Adding it once creates both of FLARE's entries, ready to use. It asks two things:

- **A name for your first schedule** (Home, unless you change it), under **FLARE
  Schedules**. A schedule is the day's curve: when each phase starts, and how bright and
  warm the light is. One for the whole house is fine; add more later for parts of the
  house that should keep a different rhythm.
- **Which rooms to set up**, each becoming a zone under **FLARE Zones**. A zone remembers
  which lights FLARE is currently driving, and its **Tick** tells the room's automation
  when to update. Every area containing lights is offered, pre-selected, and each one you
  keep becomes a zone named after it. Trim the list if you like.

Schedules and zones can be added or removed at any time from their entries, and zones renamed.

{: .note }
> On Home Assistant 2026.9 and earlier, adding another schedule sensor or zone shows
> an entry picker offering **both FLARE Schedules and FLARE Zones**, whichever one you
> clicked "Add" from. Pick the one matching what you're adding (Schedules for a schedule
> sensor, Zones for a zone); the other simply fails. Home Assistant 2026.10 goes
> straight to the right one.

Each schedule sensor gets its own device, with the phase boundaries, curve values and
transition durations as ordinary entities you can edit from the device page.

## Step 3 — install the blueprint and create an automation

FLARE will spot that its blueprint isn't installed and offer it in
**Settings → System → Repairs**. Press **Fix** and it downloads it.

Create an automation from it and fill in three things:

| Input | What to put |
|---|---|
| **Schedule** | The schedule from step 2 — Home, unless you named it something else. |
| **Zone** | The room's zone from step 2 — usually the one named after the room. |
| **Lights & Occupancy** | One target for the room — pick the **area**. Lights inside it get driven; occupancy-class binary sensors inside it decide when. |

That's the minimum. Everything else has a working default.

{: .note }
> Building your own automations on FLARE's actions instead? Ignore that repair — the
> blueprint is optional. See the [Reference]({{ site.baseurl }}/reference/).

{: .note }
> **You won't have to remember to update it.** The integration and the blueprint update
> separately, so when a release changes the blueprint FLARE raises a repair in
> **Settings → System → Repairs**. Press Fix and it downloads the new one and reloads
> your automations — they keep their settings. If you've edited your own copy, ignore
> the repair instead, since updating replaces the file.

{: .note }
> Occupancy is optional. With no occupancy sensor in the target, FLARE keeps the room's
> lights on the curve but never turns them on or off by itself.

Repeat per room. Rooms can share a schedule sensor — FLARE only sends a command to a
light that isn't already where it should be, so sharing one costs very little traffic.

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

**Lighting** gives you the day's curve and every schedule and curve setting, a section
per schedule sensor. **Zones** shows which lights FLARE is driving and which ones
something else has taken over. Nothing to fill in — see the
[Dashboard]({{ site.baseurl }}/dashboard/) page for the details.

{: .tip }
> **Just want the chart?** On Home Assistant 2026.6 or newer, add a card, open the
> **By entity** tab and pick your schedule sensor — **FLARE Curve** appears under
> *Community* with a live preview. Or add a **Manual** card with
> `type: custom:flare-curve-card` and `sensor: ground_floor`, the part before `_flare`
> in the sensor's entity ID.

---

## What now

- Lights not behaving as you expect? Each zone has **Controlled** and
  **Overridden** counters and a **Clear** button — see
  [override protection]({{ site.baseurl }}/reference/integration/#override-protection).
- Want a scene to own the room at certain times?
  [Scene handoff]({{ site.baseurl }}/reference/scenes/).
- Want to skip the blueprint entirely?
  [Building without it]({{ site.baseurl }}/reference/custom-automations/).
- Every blueprint input, with defaults: [Blueprint]({{ site.baseurl }}/blueprint/).

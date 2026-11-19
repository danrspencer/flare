---
title: Flares
parent: Reference
nav_order: 4
permalink: /reference/flares/
---

# Flares
{: .no_toc }

A flare is a light entity that sits over an automation. Flares are under **Settings → Devices
& Services → FLARE → Flares**. For setting one up for a voice assistant, see
[Voice assistants](../../guides/flares/).

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Settings

| Setting | Description |
|---|---|
| **Automation** | The automation that turning the flare on runs. If the automation is deleted, the flare becomes unavailable. |
| **Name** | The flare's display name (and what voice assistants hear). Renaming it later doesn't change its entity ID. |
| **Lights input** | For an automation built from a blueprint: the input that holds the lights. The flare reads that input whenever it's used, so changing the automation updates the flare. For an automation from the FLARE blueprint this is **Lights & Occupancy**. |
| **Lights** | For an automation not built from a blueprint: the lights, picked directly. |
| **Area** | Shown only when adding a flare for another automation: the area the flare's device starts in, defaulting to the automation's area. Afterwards, change the device's area the usual way in Home Assistant. |

**Set up area** offers a flare for each area it sets up, named after the area. Adding flares from
**Rooms from the FLARE blueprint** creates a flare for each room picked, named after its
automation. In both cases, the new flare is placed in its automation's area.

**Reconfigure flare** (in the flare's three-dot menu) shows which automation the flare runs, and
lets you change its **Name** and either its **Lights** or **Lights input**. It can't switch a
flare to a different automation — add a new flare if you need that.

## The flare's light

`light.<name>_flare` reports the combined state of its lights, as a Home Assistant light group
does: on if any of them is on, with their average brightness and colour. Its `entity_id`
attribute lists the lights.

| Call | What it does |
|---|---|
| `light.turn_on` with no brightness, colour or effect | Runs the automation, as **Run actions** does. A `transition` on its own is ignored. |
| `light.turn_on` with a brightness, colour or effect | Marks every light as overridden for that automation's room via [`flare.claims_override`](../services/#flareclaims_override), then sends the values to the lights as a light group does. FLARE leaves them alone until the room is empty and dark. |
| `light.turn_off` | Marks every light as overridden in the same way, then turns them off. They stay off until the room's automation next turns them on, such as when it detects motion. |

For an automation built from a blueprint, the flare's lights match the automation's target as
described under [Room](../blueprint/#room). A light that belongs to another flare is always
excluded.

## Flares and the room's automation

A flare's own light is never one of a room's lights: the FLARE blueprint and FLARE's services
skip it, even when it sits in the room's area.

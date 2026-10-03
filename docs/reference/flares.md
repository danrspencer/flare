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
[Voice assistants and HomeKit](../../guides/flares/).

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Settings

| Setting | Description |
|---|---|
| **Automation** | The automation that turning the flare on runs. If the automation is deleted, the flare is unavailable. |
| **Lights input** | For an automation built from a blueprint: the input that holds the lights. The flare reads it whenever it's used, so a change to the automation changes the flare. For an automation from the FLARE blueprint this is **Lights & Occupancy**. |
| **Zone input** | Optional. For an automation built from a blueprint: the input that holds its FLARE zone. `flare.turn_off` records the turn-off in that zone. For an automation from the FLARE blueprint this is **Zone**. |
| **Lights** | For an automation not built from a blueprint: the lights, picked directly. |
| **Turn off with** | `flare.turn_off` (the default) records the turn-off in the zone, so FLARE knows the lights were switched off by FLARE and not by hand. `light.turn_off` records nothing. |
| **Area** | Only when adding: the area the flare's device starts in, which defaults to the automation's area. After that, the device's area is set the usual way. |

Reconfigure changes the name, **Turn off with**, and the lights or inputs. The automation
can't be changed: add a new flare instead.

## The flare's light

`light.<name>_flare` reports the combined state of its lights, as a Home Assistant light group
does: on if any of them is on, with their average brightness and colour. Its `entity_id`
attribute lists the lights.

| Call | What it does |
|---|---|
| `light.turn_on` with no brightness, colour or effect | Runs the automation, as **Run actions** does. A `transition` on its own is ignored. |
| `light.turn_on` with a brightness, colour or effect | Sends them to every light, as a light group does. The lights then count as an override. |
| `light.turn_off` | Calls the service set in **Turn off with** for every light. If `flare.turn_off` isn't available, because the Zones entry isn't loaded, it uses `light.turn_off`. |

The flare's lights are found the way a service call's target is. A light that is hidden, or
belongs to another flare, isn't one of them.

## Flares and the room's automation

A flare's own light is never one of a room's lights: the FLARE blueprint and FLARE's services
skip it, even when it sits in the room's area.

---
title: Voice assistants and HomeKit
parent: Guides
nav_order: 4
permalink: /guides/flares/
---

# Voice assistants and HomeKit
{: .no_toc }

A flare is a light for a whole room. Turning it on runs the room's automation, so "Hey Siri,
turn on the kitchen" brings the kitchen up the way FLARE would have, at the curve's brightness
and colour, rather than at whatever the bulbs last had.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Adding flares for your rooms

Every area set up with **Set up area**, including when you first add FLARE, already has a
flare, named after the area.

For a room automation you made yourself, go to **Settings → Devices & Services → FLARE → Add
flare** and choose **Rooms from the FLARE blueprint**. Every room automation that doesn't have
a flare yet is listed and ticked, so you can add a flare for every room at once, or untick the
ones you don't want. Each one is named after its automation.

A flare is placed in its automation's area. It appears as `light.<name>_flare` and always has
the same lights as its room's automation, so if you add a bulb to the room's area, it joins the
flare too.

### Name it the way you'll say it

A flare's name is what Siri, Alexa and Google hear. Automations often have names like
"Kitchen lighting" or "Garden Lights Adaptive", which nobody says out loud, so rename a flare
named after one to the room's plain name, "Kitchen" or "Garden", with **Reconfigure** in the flare's
three-dot menu. Renaming a flare doesn't change its entity ID. If the flare is already in the
Home app or the Alexa app, rename it there too, because they can keep the name they first saw.

## What each command does

| You say or tap | What happens |
|---|---|
| "Turn on the kitchen" | The room's automation runs, and the room comes on the way it normally would. |
| "Set the kitchen to 30%", or a colour | Every light in the room is set to that. FLARE leaves them there until the room is empty and dark. |
| "Turn on the kitchen" again | The room goes back to FLARE: the automation runs, and every light returns to the curve. |
| "Turn off the kitchen" | Every light in the room turns off, and stays off until the room's sensors next detect motion. |

## Exposing flares instead of your bulbs

Expose each room's flare and stop exposing its bulbs. If you expose both, every room shows up
twice, and "turn on the kitchen" may go to the bulbs, which come on at whatever they last had
instead of following the room. The bulbs keep working in Home Assistant either way.

### HomeKit

FLARE names every flare `light.<name>_flare`, so if your HomeKit Bridge is set up in YAML, one
pattern exports every flare, including ones you add later:

```yaml
homekit:
  filter:
    include_entity_globs:
      - light.*_flare
```

Leave out `include_domains: light` if you have it, or the bulbs are exported as well. Home
Assistant reads this when it starts, so restart after changing it. If you set the bridge up
from the UI instead, use **Configure** on the HomeKit Bridge integration, choose to include
entities, and pick the flares.

HomeKit doesn't use Home Assistant's areas, so put each flare in its room in the Home app. If
the bridge used to export your bulbs, they stay in the Home app as "Not Responding" until you
remove the bridge from the Home app and pair it again.

### Alexa and Google Assistant

With Home Assistant Cloud, go to **Settings → Voice assistants → Expose**, expose the flares
and un-expose the bulbs. If **Expose new entities** is on, the flares are already exposed, but
so is every bulb.

Google Assistant puts each flare in the room matching its Home Assistant area. Alexa doesn't
use areas, so put each flare in a group for its room in the Alexa app.

If you set up exposure in YAML instead, the same `include_entity_globs` pattern works in the
`filter:` under `cloud: alexa:`, `cloud: google_actions:` and a manual `alexa: smart_home:`.
A manual `google_assistant:` setup has no filter, so expose the flares there with
`entity_config` instead.

### Assist

Assist uses the same **Expose** list. Expose the flares and un-expose the bulbs, and "turn on
the kitchen" turns on the flare. If you'd rather keep the flare's name as it is, add the room's
name as an alias on the flare instead, under **Voice assistants** in its settings.

## A flare for your own automation

Any automation can have a flare. Choose **Another automation** when adding one:

- If the automation is built from a blueprint, pick the input that holds its lights and, if
  it has one, the input that holds its FLARE zone. Without a zone, a brightness or colour you
  set from the flare isn't protected: if FLARE wasn't already driving a light, the
  automation's next update can set it back.
- If it isn't, pick its lights directly.

Turning the flare on runs that automation. The other commands work the same as above. The
[Flares reference](../../reference/flares/) lists every setting.

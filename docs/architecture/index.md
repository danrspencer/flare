---
title: Architecture
nav_order: 8
has_children: true
permalink: /architecture/
---

# How FLARE works inside
{: .no_toc }

{: .internals }
> **Nobody needs to read this to use FLARE.** This section is for people who want to change
> FLARE's code, or who just like to know how things work. Installing, setting up and using FLARE
> are all covered without it: start at [Installation]({{ site.baseurl }}/installation/).

What runs where, how FLARE hooks into Home Assistant, and how the pieces
talk to each other. These pages describe the system as it is. The reasons
behind its decisions are in
[CLAUDE.md](https://github.com/danrspencer/flare/blob/main/CLAUDE.md), in
the repository.

## Reading order

| Page | What it covers |
|---|---|
| [The big picture]({{ site.baseurl }}/architecture/#the-big-picture) (below) | The two halves, and what happens when a room updates |
| [Code layout]({{ site.baseurl }}/architecture/layout/) | Packages, the dependency rule, config entries, devices and entities |
| [The event loop]({{ site.baseurl }}/architecture/event-loop/) | Every place FLARE hooks into Home Assistant: setup order, listeners, timers, storage, contexts |
| [Schedules and the curve]({{ site.baseurl }}/architecture/schedules/) | How a schedule becomes a phase, a brightness and a colour |
| [The room automation]({{ site.baseurl }}/architecture/room-automation/) | The blueprint: triggers, the variables chain, the one gate that switches lights on |
| [Services and grouping]({{ site.baseurl }}/architecture/services/) | `flare.apply_lighting` from call to bulb, and the other eleven services |
| [Claims and override protection]({{ site.baseurl }}/architecture/claims/) | How FLARE tells its own writes from anyone else's |
| [Flares]({{ site.baseurl }}/architecture/flares/) | The light that fronts a room automation |
| [Setup and upgrades]({{ site.baseurl }}/architecture/setup/) | Config flows, area setup, the blueprint repairs, migrations |
| [The dashboard]({{ site.baseurl }}/architecture/frontend/) | How the JavaScript gets into the page, the strategies and the cards |

## The big picture

FLARE is two pieces, and the dependency runs one way.

- **The integration** (`custom_components/flare/`) is Python running
  inside Home Assistant. It works out what lights should look like (the
  *schedule* and its *curve*), sends that to bulbs efficiently, and
  remembers which writes were its own (*claims*) so it can leave a light
  alone once someone else changes it. Everything it does is an entity or a
  service.
- **The blueprint** (`custom_components/flare/blueprints/flare.yaml`)
  is the room automation built on those services. It decides *when* a room
  updates and *whether* a light may come on. Each room is one automation
  made from it.

```mermaid
flowchart TB
    subgraph BP["Room automation"]
        direction LR
        T["Triggers:<br/>phase change, area tick,<br/>motion, lights back online"] --> V["Variables:<br/>the room's lights, occupancy,<br/>levels, allow_turn_on"] --> A["Action:<br/>turn off, idle, scene,<br/>apply the curve"]
    end
    subgraph INT["Integration (Python)"]
        direction LR
        S["Schedule:<br/>coordinator + entities"]
        TK["Area ticker"]
        SV["Services: flare.*"]
        C["Claim registry"]
    end
    L["Bulbs (light.*)"]
    S -- "Phase event,<br/>schedule sensor" --> T
    TK -- "flare_tick" --> T
    A -- "resolve_target,<br/>apply_lighting, turn_off" --> SV
    SV -- "records claims" --> C
    SV -- "light.turn_on / turn_off" --> L
    L -- "state_changed" --> C
```

### One room update, end to end

The commonest path: an area's tick fires, and the room drifts with the
curve.

```mermaid
sequenceDiagram
    autonumber
    participant TK as TickScheduler
    participant AU as Room automation
    participant SV as flare services
    participant CR as ClaimRegistry
    participant B as Bulbs
    TK->>AU: flare_tick {area_id: kitchen}
    AU->>SV: flare.resolve_target(room_target)
    SV-->>AU: room entities
    Note over AU: variables render once:<br/>levels, occupancy, allow_turn_on
    AU->>SV: flare.apply_lighting(lights, brightness, kelvin, room_id)
    SV->>CR: classify each light (claims vs live state)
    Note over SV: build_groups: bucket by brightness,<br/>drop overridden lights, skip claimed lights<br/>already close enough, split two-step
    SV->>CR: async_record (before sending)
    SV->>B: light.turn_on, one call per group
    B-->>CR: state_changed under the call's context
    Note over CR: context matches the claim:<br/>the light stays "controlled"
```

Every other path is a variation on this one. Motion uses a shorter
transition and may switch lights on. A room emptying calls
`flare.turn_off`. A phase change also moves scenes on. Someone changing a
light by hand shows up at step 10 as a context and values that match no
claim, and from then on step 5 leaves that light out.

## Words used here

These pages use the code's own terms. The rest of this site doesn't; the
lexicon in [DOCUMENTATION.md](https://github.com/danrspencer/flare/blob/main/DOCUMENTATION.md) lists the ones it keeps out.

| Term | Meaning |
|---|---|
| schedule | One "sensor" subentry of the Schedules entry: five boundary times and sixteen curve values, each its own entity. |
| phase | Morning, Day, Evening or Night. |
| curve | Brightness and Kelvin over the day, easing between phases. |
| room | Who's writing, for override protection: a `room_id` (the automation) and its lights. |
| claim | A record of FLARE's write to one light: the context it used and what it asked for. |
| tick | `flare_tick`, a plain bus event fired for each area once per interval. |
| flare | A `light` entity fronting a room automation, for voice assistants and HomeKit. |
| context | Home Assistant's `Context`: every state change carries the id of whatever caused it. |
| group | One `build_groups` output: lights sharing a brightness, split by how they're sent. |

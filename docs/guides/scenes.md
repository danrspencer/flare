---
title: Scenes
parent: Guides
nav_order: 3
permalink: /guides/scenes/
redirect_from:
  - /reference/scenes/
  - /advanced/scenes/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Scenes
{: .no_toc }

A room can use one of your scenes instead of the schedule, either for a whole phase or when a
template chooses one.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Using a scene in a room

Choose a scene in the blueprint's **Night Scene**, or whichever phase, and the room uses it
during that phase. To choose a scene based on something else, such as the TV being on, use
[Scene Template](../templates/#scene-template). It overrides the per-phase scenes whenever it
returns one.

A scene is only used if every entity it sets is in the room. If a scene sets anything outside
the room, or doesn't exist, the room follows the schedule.

Lights in the room that the scene doesn't set follow the schedule as usual.

## When the scene is applied

The scene is applied when the room's automation runs because the phase changed, occupancy was
detected, an Additional Trigger changed, a light came back online, or you ran it by hand. It
isn't applied on the regular tick, so changes you make while the scene is on aren't undone.

A scene doesn't turn on the lights in an empty room. If the phase changes while the room is
empty, the scene is applied when someone next comes in.

When the scene's phase ends, the room goes back to the schedule.

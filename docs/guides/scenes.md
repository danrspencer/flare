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

A room can follow a scene of yours instead of the curve: one per phase, or one chosen by a
template. FLARE applies the scene, lights anything it doesn't cover from the curve, and takes
the room back when the scene no longer applies.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Handing a room to a scene

Assign a scene to a phase in the blueprint and the room uses it instead of the curve during
that phase. To pick a scene based on anything else, such as the TV being on, use
[Scene Template](../templates/#scene-template), which wins over the per-phase scenes whenever it
returns one.

A scene is only used if every entity it touches is in the room. A scene that reaches into
another room, or doesn't exist, is ignored and the room follows the curve.

Lights in the room that the scene doesn't cover carry on following the curve, so a scene
naming half the room leaves the other half to FLARE.

## When the scene is applied

The scene is applied when the room's automation runs for a phase change, for motion, for an
Additional Trigger, when you run it by hand, or when a light comes back online — but not on
the regular update. Re-applying it every minute would undo anything you changed by hand while
it was on.

Like the curve, a scene never lights an empty room. If the phase changes while nobody's there,
the scene is applied when someone next walks in.

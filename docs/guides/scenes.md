---
title: Scene handoff
parent: Guides
nav_order: 4
permalink: /guides/scenes/
redirect_from:
  - /reference/scenes/
  - /advanced/scenes/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Scene handoff
{: .no_toc }

If you've already made a scene for how a room should look at night, or while you're watching a
film, a room can use it, either one scene per phase or one chosen by a template.

The scene only takes over the lights it sets. Every other light in the room keeps following the
curve, and FLARE carries on adjusting it as usual. So a scene that sets just the TV backlight
and one lamp leaves the rest of the room to FLARE. When the scene no longer applies, FLARE takes
its lights back too.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Handing a room to a scene

If you pick a scene in the blueprint's **Night Scene** (or whichever phase), the room uses it
during that phase. For anything a phase can't express — a different scene
while the TV is on — use [Scene Template](../templates/#scene-template), which wins over the
per-phase pickers whenever it returns a scene.

A scene is only used if every entity it touches is in the room. A scene that reaches into
another room, or doesn't exist, is ignored and the room follows the curve.

## When the scene is applied

The scene is applied when the room's automation runs for a phase change, for motion, for an
Additional Trigger, when you run it by hand, or when a light comes back online — but not on
the regular update. Re-applying it every minute would undo anything you changed by hand while
it was on.

Like the curve, a scene never lights an empty room. If the phase changes while nobody's there,
the scene is applied when someone next walks in.

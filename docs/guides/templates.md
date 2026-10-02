---
title: Templates
parent: Guides
nav_order: 2
permalink: /guides/templates/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Templates
{: .no_toc }

The blueprint's three template inputs cover what its other settings can't: a light that
depends on something other than the phase, or a single light treated differently from the
rest of the room. This page covers how each one works, with examples. The
[Blueprint](../../reference/blueprint/) page lists what each one accepts.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Brightness Template

Returns the brightness each light should sit at, as a mapping from entity ID to a level:

| Value | Effect |
|---|---|
| `1`–`255` | The light sits at this brightness, on the same scale as the phase brightnesses |
| `0` | The light is turned off |
| `null` or `false` | FLARE leaves the light alone entirely, on or off |

A light the template doesn't mention follows the curve as usual, so return `{}` when the
template has nothing to change.

### Dimming a light while the TV is on

```yaml
{{ {'light.lounge_ceiling': 40} if is_state('media_player.tv', 'playing') else {} }}
```

While the TV plays, the ceiling light sits at 40 and the rest of the room follows the curve.
Add `media_player.tv` to **Additional Triggers** so the room changes as soon as the TV starts
or stops, rather than at the next update.

### Dimming some lights in the evening

```yaml
{% set phase = states('sensor.home_flare') %}
{% if phase == 'Evening' %}
  {{ {'light.kitchen_1': 20, 'light.kitchen_2': 20} }}
{% elif phase == 'Night' %}
  {{ {'light.kitchen_1': 5, 'light.kitchen_2': 5} }}
{% else %}
  {{ {} }}
{% endif %}
```

The rest of the kitchen follows the curve; these two sit lower once Evening starts.

### Leaving a light to another automation

```yaml
{{ {'light.kitchen_strip': none} if states('sensor.home_flare') in ['Evening', 'Night'] else {} }}
```

In the evening another automation runs a gradient on the kitchen strip, so this hands the
strip over during Evening and Night and FLARE leaves it alone. FLARE won't turn it off when
the room empties either; the other automation needs to do that.

### One level for the whole room

A single number applies to every light in the room:

```yaml
{{ 40 if is_state('media_player.tv', 'playing') else none }}
```

`none` here means "no opinion", so the room follows the curve when the TV is off.

### A level that follows the curve

A level is fixed: the light stays at it for as long as the template returns it, whatever the
time of day. To keep a light at, say, half the room's brightness, read the curve and scale it:

```yaml
{{ {'light.lounge_ceiling': state_attr('sensor.home_flare', 'brightness') | int * 0.5} }}
```

### `0` or `null`?

`0` turns the light off but keeps it FLARE's, so it comes back on with the rest of the room.
`null` hands the light over completely: FLARE doesn't touch it at all, so it isn't turned off
when the room empties either, and whatever controls it has to do that instead.

The template wins over the **Lights Off During** lists for any light it names.

## Idle Brightness Template

Returns what each light dims to when the room is empty, instead of going dark. It takes the
same values as Brightness Template, and wins over the per-phase **Idle Brightness** settings
for any light it names.

### One lamp as the nightlight

```yaml
{{ {'light.landing_lamp': 20} }}
```

With the phase settings at `0`, this lamp stays at 20 when the landing empties and every other
light goes out.

{: .note }
> When a phase's setting is `0`, only the lights the template names have an idle brightness in
> that phase. So a template naming one lamp makes that lamp the room's only nightlight, even if
> you only meant to give it a different level from the rest. To keep the rest dim too, set the
> phase's Idle Brightness as well, and use the template for the one light.

### A whole-room nightlight

A single number applies to every light in the room:

```yaml
{{ 20 }}
```

### A nightlight that follows the sun

The Night phase starts at a fixed time, not at dark. For a hall that stays dimly lit
whenever it's dark outside, leave the four phase settings at `0` and use the sun:

```yaml
{{ 10 if is_state('sun.sun', 'below_horizon') else {} }}
```

`{}` means "no opinion", so the hall goes fully dark while the sun is up. The hall picks up the
change at the next update after sunset, which can be up to a minute later. Don't add `sun.sun` to
**Additional Triggers** to make it immediate: at sunrise that would bring the lights up to
the curve instead of turning them off.

## Scene Template

Returns a scene's entity ID, to hand the room to that scene instead of the curve. It wins over
the per-phase scene pickers whenever it returns a scene that exists.

```yaml
{{ 'scene.lounge_movie' if is_state('media_player.tv', 'playing') else '' }}
```

Return `''` for no scene. See [Scenes](../scenes/) for how a room shares itself with a scene.

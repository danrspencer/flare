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
[Blueprint](../../blueprint/#inputs) page lists what each one accepts.

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

A light the template doesn't mention follows the curve as usual. Return `{}` when you have
nothing to say.

### Dimming a light while the TV is on

```yaml
{% if is_state('media_player.tv', 'playing') %}
  {{ {'light.lounge_ceiling': 40, 'light.lounge_lamp': none} }}
{% else %}
  {{ {} }}
{% endif %}
```

While the TV plays, the ceiling light sits at 40 and the lamp is left to whatever else
controls it. Add `media_player.tv` to **Additional Triggers** so the room changes as soon as
the TV starts or stops, rather than at the next update.

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

`0` keeps the light FLARE's: it's off for now, and comes back with the room. `null` hands the
light over: FLARE doesn't touch it at all, so it isn't turned off when the room empties
either. Whatever owns it has to do that.

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
> With a phase setting at `0`, the template *is* the whole idle set. A template naming one
> lamp makes that lamp the room's only nightlight, even if you only meant to give it a
> different level from the rest. To keep the rest dim too, set the phase's Idle Brightness as
> well, and use the template for the one light.

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

`{}` means "no opinion", so the hall goes fully dark while the sun is up. It picks up the
change at the next update after sunset, up to a minute later. Don't add `sun.sun` to
**Additional Triggers** to make it immediate: at sunrise that would bring the lights up to
the curve instead of turning them off.

## Scene Template

Returns a scene's entity ID, to hand the room to that scene instead of the curve. It wins over
the per-phase scene pickers whenever it returns a scene that exists.

```yaml
{{ 'scene.lounge_movie' if is_state('media_player.tv', 'playing') else '' }}
```

Return `''` for no scene. See [Scenes](../scenes/) for how a room shares itself with a scene.

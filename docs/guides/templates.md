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

The blueprint has three template inputs for cases its other settings don't cover, such as a
light that depends on something other than the phase. This page explains each one, with
examples. The [Blueprint](../../reference/blueprint/#inputs) reference lists what each accepts.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## Brightness Template

Returns a mapping of entity ID to brightness:

| Value | Effect |
|---|---|
| `1`–`255` | The light is set to this brightness, on the same scale as the phase brightnesses. |
| `0` | The light is turned off. |
| `null` or `false` | FLARE doesn't touch the light. |

Lights the template doesn't include follow the schedule. Return `{}` to leave every light on
the schedule.

### Dimming a light while the TV is on

```yaml
{{ {'light.lounge_ceiling': 40} if is_state('media_player.tv', 'playing') else {} }}
```

While the TV is playing, the ceiling light is set to 40. Add `media_player.tv` to **Additional
Triggers** so the light changes as soon as the TV starts or stops.

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

The other kitchen lights follow the schedule. These two are set to 20 during Evening and 5
during Night.

### Leaving a light to another automation

```yaml
{{ {'light.kitchen_strip': none} if states('sensor.home_flare') in ['Evening', 'Night'] else {} }}
```

In the evening a separate automation runs a colour gradient on the kitchen strip, so FLARE
leaves the strip alone during Evening and Night. It doesn't turn the strip off when the room
empties either; the other automation has to do that.

### One brightness for the whole room

A single number applies to every light in the room:

```yaml
{{ 40 if is_state('media_player.tv', 'playing') else none }}
```

`none` means no value, so the room follows the schedule while the TV is off.

### A brightness relative to the schedule

A brightness from the template is fixed: the light stays at it for as long as the template
returns it. To keep a light at half the schedule's brightness, read the schedule sensor:

```yaml
{{ {'light.lounge_ceiling': state_attr('sensor.home_flare', 'brightness') | int * 0.5} }}
```

The template overrides the **Lights Off During** lists for the lights it includes.

## Idle Brightness Template

Returns the brightness each light dims to when the room is empty, instead of turning off. It
takes the same values as Brightness Template, and overrides the per-phase **Idle Brightness**
settings for the lights it includes.

### One lamp as the nightlight

```yaml
{{ {'light.landing_lamp': 20} }}
```

With the phase settings at `0`, the lamp dims to 20 when the landing is empty and the other
lights turn off.

{: .note }
> If a phase's Idle Brightness is `0`, only the lights in the template stay on. To dim the rest
> of the room as well, set the phase's Idle Brightness, and use the template for the lights that
> need a different level.

### A whole-room nightlight

A single number applies to every light in the room:

```yaml
{{ 20 }}
```

### A nightlight while it's dark outside

Night starts at a fixed time, not at dark. For a hall that stays dimly lit whenever the sun is
down, leave the four phase settings at `0` and use:

```yaml
{{ 10 if is_state('sun.sun', 'below_horizon') else {} }}
```

`{}` means no value, so the hall turns off when empty while the sun is up. The change happens at
the next update after sunset or sunrise, up to a minute later. Don't add `sun.sun` to
**Additional Triggers**: at sunrise, that would set the lights to the schedule instead of
turning them off.

## Scene Template

Returns a scene's entity ID. The room uses that scene instead of the schedule. It overrides the
per-phase scenes whenever it returns a scene that exists.

```yaml
{{ 'scene.lounge_movie' if is_state('media_player.tv', 'playing') else '' }}
```

Return `''` for no scene. See [Scenes](../scenes/).

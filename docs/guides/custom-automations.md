---
title: Building without the blueprint
parent: Guides
nav_order: 6
permalink: /guides/custom-automations/
redirect_from:
  - /reference/custom-automations/
  - /advanced/custom-automations/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Building without the blueprint
{: .no_toc }

If your lights already run on automations of your own, or in Node-RED or AppDaemon, you don't
have to replace them with the blueprint to get the curve and have hand-set lights left alone.
FLARE's [services](../../reference/services/) are ordinary Home Assistant actions, so anything
that can call an action can use them, and the blueprint is just one automation built on them.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## The smallest automation

You need a [schedule](../../reference/schedules/) for the values. If you want FLARE to leave
hand-set lights alone, pass the automation itself as the
[room](../../reference/override-protection/#rooms). This keeps the kitchen on the curve:

```yaml
alias: Kitchen lighting
triggers:
  - trigger: event
    event_type: flare_tick
    event_data:
      area_id: kitchen
conditions:
  - condition: template
    value_template: "{{ area_entities('kitchen') | select('match', '^light\\.') | select('is_state', 'on') | list | count > 0 }}"
actions:
  - action: flare.apply_lighting
    data:
      entities: "{{ area_entities('kitchen') | select('match', '^light\\.') | select('is_state', 'on') | list }}"
      brightness: "{{ state_attr('sensor.home_flare', 'brightness') }}"
      color_temp_kelvin: "{{ state_attr('sensor.home_flare', 'color_temp_kelvin') }}"
      transition: 5
      room_id: "{{ this.entity_id }}"
      room_entities: "{{ area_entities('kitchen') | select('match', '^light\\.') | list }}"
```

It runs on the kitchen's [tick](../../reference/override-protection/#when-rooms-update) and only passes
lights that are on, since `apply_lighting` turns on everything it's given. Turning the room on and off is left to you.

## Sending the commands yourself

If you want to send `light.turn_on` yourself and still have FLARE leave hand-set lights alone:

1. `flare.claims_check` to find out whether someone else has changed the light.
2. `flare.claims_record` with what you're about to send, so FLARE recognises it next time.
3. Your own `light.turn_on`.

For example, this script sets the porch light to a warm 60%, unless someone has changed it
since the script last set it:

```yaml
alias: Porch light warm
sequence:
  - action: flare.claims_check
    data:
      entities: [light.porch]
    response_variable: check
  - condition: template
    value_template: "{{ not check.results['light.porch'].blocked }}"
  - action: flare.claims_record
    data:
      entities: [light.porch]
      room_id: "{{ this.entity_id }}"
      targets:
        light.porch: { brightness: 153, color_temp_kelvin: 2200 }
  - action: light.turn_on
    target:
      entity_id: light.porch
    data:
      brightness: 153
      color_temp_kelvin: 2200
```

`targets` needs the brightness and either `color_temp_kelvin` or `rgb_color` you're sending.
FLARE checks the light against it later, so a light running an effect that keeps changing its
colour won't be recognised. For that, use a scene or hand the light over with a `null`
brightness in the blueprint instead.

When your automation turns lights off, such as when the room empties, use `flare.turn_off`
rather than `light.turn_off` if any of the room's lights stay on. It sets the lights' claims to
off, so they still match and come on with the room next time. With `light.turn_off` their claims
still say on, so they're `overridden` and stay off until the whole room has been dark. See
[`flare.turn_off` or `light.turn_off`?](../../reference/services/#flareturn_off-or-lightturn_off).

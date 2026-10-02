---
title: Building without the blueprint
parent: Guides
nav_order: 4
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

The blueprint is one way to use FLARE's [services](../../reference/services/). Anything that
can call a Home Assistant action — an automation, a script, Node-RED, AppDaemon — can use them
directly.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## The smallest automation

You need a [schedule](../../reference/schedules/) for the values and, if you want FLARE to
leave hand-set lights alone, a [zone](../../reference/zones/) for the lights. This keeps the
kitchen on the curve:

```yaml
alias: Kitchen lighting
triggers:
  - trigger: event.received
    target:
      entity_id: event.kitchen_flare_tick
    options:
      event_type: [flare_tick]
conditions:
  - condition: template
    value_template: "{{ area_entities('kitchen') | select('match', '^light\\.') | select('is_state', 'on') | list | count > 0 }}"
actions:
  - action: flare.apply_lighting
    data:
      entities: "{{ area_entities('kitchen') | select('match', '^light\\.') | select('is_state', 'on') | list }}"
      brightness: "{{ state_attr('sensor.home_flare', 'brightness') }}"
      color_temp_kelvin: "{{ state_attr('sensor.home_flare', 'color_temp') }}"
      transition: 5
      zone_device_id: "{{ device_id('sensor.kitchen_flare_claims') }}"
```

It runs on the kitchen zone's tick and only passes lights that are on, since `apply_lighting`
turns on everything it's given. Turning the room on and off is left to you.

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
      zone_device_id: "{{ device_id('sensor.porch_flare_claims') }}"
    response_variable: check
  - condition: template
    value_template: "{{ not check.results['light.porch'].blocked }}"
  - action: flare.claims_record
    data:
      entities: [light.porch]
      zone_device_id: "{{ device_id('sensor.porch_flare_claims') }}"
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

To turn lights off, use `flare.turn_off` rather than `light.turn_off`: it records the turn-off
too, so it isn't mistaken for someone switching the lights off by hand.

`flare.compute_lighting_groups` gives you what `apply_lighting` would send, grouped, without
sending it, if you want a starting point for sending it yourself.

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

The blueprint uses FLARE's [services](../../reference/services/), and so can your own
automations, scripts, Node-RED flows or AppDaemon apps.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## The smallest automation

You need a [schedule](../../reference/schedules/) for the values and, for override
protection, a [zone](../../reference/zones/). This automation keeps the kitchen's lights on the
schedule:

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

It runs on the kitchen zone's tick. It only passes lights that are on, because `apply_lighting`
turns on every light it's given. It doesn't turn the room on or off.

## Sending the commands yourself

To send `light.turn_on` yourself and still use FLARE's override protection:

1. Call `flare.claims_check` to find out whether FLARE would leave the light alone.
2. If it wouldn't, call `flare.claims_record` with the values you're about to send.
3. Send your command.

This script sets the porch light to a warm 60%, unless someone else has changed it since the
script last set it:

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

`targets` must have the brightness and either `color_temp_kelvin` or `rgb_color` you're about
to send. FLARE compares the light with them later to recognise the change as its own. An effect
that keeps changing the light's colour can't be recognised this way.

To turn lights off, use `flare.turn_off` rather than `light.turn_off`. It records the turn-off,
so it isn't mistaken for someone turning the lights off by hand.

`flare.compute_lighting_groups` returns what `apply_lighting` would send, grouped by brightness,
without sending it. Use it as a starting point for sending the commands yourself.

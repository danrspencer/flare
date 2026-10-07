---
title: Examples
parent: Guides
nav_order: 1
permalink: /guides/examples/
redirect_from: /examples/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Examples
{: .no_toc }

Almost everything in FLARE is an ordinary Home Assistant entity or event. That means you can
trigger your own automations from it, or use automations to change it. These are starting
points: each one is a complete automation to paste in and adjust.

They use a schedule called **Home**, so its entities are `time.home_…`, `number.home_…`
and `sensor.home_flare`. Swap in your own schedule's name, and your own rooms, lights and
sensors.

<details open markdown="block">
  <summary>On this page</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

## A weekend lie-in

Morning starts later on Saturday and Sunday.

```yaml
alias: Weekend lie-in
triggers:
  - trigger: state
    entity_id: event.home_flare_phase
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'Night' }}"
actions:
  # Friday and Saturday nights set up a lie-in for the next morning;
  # every other night sets the weekday times back.
  - variables:
      lie_in: "{{ now().weekday() in [4, 5] }}"
  - action: time.set_value
    target:
      entity_id: time.home_morning_time
    data:
      time: "{{ '08:00:00' if lie_in else '06:00:00' }}"
  - action: time.set_value
    target:
      entity_id: time.home_day_time
    data:
      time: "{{ '09:30:00' if lie_in else '08:00:00' }}"
```

The schedule only checks Morning's start time when the morning comes round, so the trick is
to change it the night **before**. This runs when Night starts: after today's morning, and
before tomorrow's.

- **It runs every night**, not just at the weekend, so the weekday times come back on Sunday
  night without a second automation.
- **Day moves with Morning.** Morning lasts until Day starts, so moving Morning to 08:00
  while Day still starts at 08:00 would leave no Morning at all.
- **If your Night starts after midnight**, use `[5, 6]`: by then it's already Saturday.

## A holiday schedule

Switch the whole house to a holiday schedule, with later mornings and later nights, from a
toggle, and back again when the holiday's over.

First create a **Toggle** helper called *Holiday mode* (Settings → Devices & Services →
Helpers → Create helper → Toggle). Then:

```yaml
alias: Holiday schedule
triggers:
  - trigger: state
    entity_id: input_boolean.holiday_mode
actions:
  - if: "{{ is_state('input_boolean.holiday_mode', 'on') }}"
    then:
      - action: flare.import_schedule
        data:
          schedule_device_id: "{{ device_id('sensor.home_flare') }}"
          schedule: |
            morning:
              time: "08:30"
            day:
              time: "10:00"
            night:
              time: "23:30"
    else:
      - action: flare.import_schedule
        data:
          schedule_device_id: "{{ device_id('sensor.home_flare') }}"
          schedule: |
            morning:
              time: "06:00"
            day:
              time: "08:00"
            night:
              time: "22:00"
```

Each schedule lists only what changes; everything else stays as it is. A schedule can hold
any of its settings, so for bigger changes, set your schedule up the way you want it, press
**Copy** in its dashboard section, and paste the result in.

## Movie night

Hold the house at Night while the TV is on, and hand back to the schedule when it goes
off.

```yaml
alias: Movie night
triggers:
  - trigger: state
    entity_id: media_player.living_room_tv
    to: playing
    id: start
  - trigger: state
    entity_id: media_player.living_room_tv
    from: playing
    id: stop
actions:
  - action: select.select_option
    target:
      entity_id: select.home_flare_phase
    data:
      option: "{{ 'Night' if trigger.id == 'start' else 'Auto' }}"
```

The phase override applies to **every room on that schedule**. To dim one room only, give
it a schedule of its own, or use the blueprint's
[Brightness Template](../templates/#brightness-template) instead.

## Lighting a room from a remote

Turn the hall lights on from a button on a remote, at the right level for the time of day.

```yaml
alias: Hall lights from the remote
triggers:
  - trigger: state
    entity_id: event.hall_remote_action
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'on' }}"
actions:
  - action: automation.trigger
    target:
      entity_id: automation.hallway_lights
```

If the hall has a [flare](../flares/), you can turn that on instead, like any other light. It
runs the room's automation in the same way:

```yaml
actions:
  - action: light.turn_on
    target:
      entity_id: light.hallway_lights_flare
```

## Something else at a phase change

Close the blinds when Night starts.

```yaml
alias: Blinds at Night
triggers:
  - trigger: state
    entity_id: event.home_flare_phase
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'Night' }}"
actions:
  - action: cover.close_cover
    target:
      area_id: living_room
```

The Phase event fires each time the phase changes, including a manual override, with the
new phase as its `event_type`.

## Being told when a light is taken over

A notification when FLARE stops driving a light because something else changed it.

```yaml
alias: Tell me when FLARE lets go of a light
triggers:
  - trigger: event
    event_type: flare_light_overridden
actions:
  - action: notify.notify
    data:
      message: >
        {{ state_attr(trigger.event.data.light, 'friendly_name') }} in
        {{ trigger.event.data.zone }} was changed by something else, so FLARE has
        stopped driving it until the room goes dark.
```

The event also carries what FLARE last asked for and what the light was actually showing —
see [the zone's events](../../reference/zones/#the-zones-events).

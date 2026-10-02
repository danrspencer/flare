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

Most of FLARE is Home Assistant entities and events, so you can trigger your own automations
from it, or change it with them. Each example below is a complete automation to copy and
adjust.

The examples use a schedule called **Home**, whose entities are `time.home_…`,
`number.home_…` and `sensor.home_flare`. Replace these, and the rooms, lights and sensors, with
your own.

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

The schedule uses Morning's start time when the morning arrives, so the automation changes it
the night before. It runs when Night starts, which is after today's morning and before
tomorrow's.

- It runs every night, so on Sunday night it sets the weekday times back.
- It moves Day as well as Morning. Morning ends when Day starts, so moving only Morning to 08:00
  would leave no Morning at all.
- If your Night starts after midnight, use `[5, 6]`, because by then it's already Saturday.

## A holiday schedule

Switch the house to later mornings and later nights with a toggle, and back again when you
turn it off.

First create a **Toggle** helper called *Holiday mode* (**Settings → Devices & Services →
Helpers → Create helper → Toggle**). Then:

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

Each schedule lists only the settings it changes; the others keep their values. A schedule
can include any setting. To change more, set the schedule up the way you want it, press
**Copy** in its dashboard section, and paste the result in.

## Movie night

Hold the schedule at Night while the TV is playing, and go back to the schedule when it
stops.

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

The phase override applies to every room on the schedule. To dim one room only, use the
blueprint's [Brightness Template](../templates/#brightness-template) instead.

## Keeping a room lit regardless of motion

Keep the landing lit while a toggle is on, even when nobody is there.

```yaml
template:
  - binary_sensor:
      - name: "Landing kept lit"
        device_class: occupancy
        state: "{{ is_state('input_boolean.keep_landing_lit', 'on') }}"
```

Add this to `configuration.yaml`, then add `binary_sensor.landing_kept_lit` to the landing
automation's **Lights & Occupancy**. It's an occupancy sensor that's on while the toggle is on,
and the room isn't empty while any of its occupancy sensors is on.

## Lighting a room from a remote

Turn the hall lights on from a button on a remote, at the level for the time of day.

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

This runs the room's automation, which counts as running it by hand, so it can turn the lights
on. It also sets any light someone changed back to the schedule. **Additional Triggers** can't
do this, because they only adjust lights that are already on.

## Closing the blinds at Night

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

The Phase event fires each time the phase changes, including a manual override. Its
`event_type` is the new phase.

## A notification when a light is changed

Send a notification when something else changes a light, so FLARE stops setting it.

```yaml
alias: Tell me when FLARE lets go of a light
triggers:
  - trigger: event
    event_type: flare_light_overridden
actions:
  - action: notify.notify
    data:
      message: >
        {{ state_attr(trigger.event.data.entity_id, 'friendly_name') }} in
        {{ trigger.event.data.zone }} was changed by something else. FLARE won't
        set it again until the room is dark.
```

The event also includes what FLARE last set and what the light was showing. See
[the hand-over event](../../reference/zones/#the-hand-over-event).

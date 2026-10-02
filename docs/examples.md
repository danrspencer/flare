---
title: Examples
nav_order: 6
permalink: /examples/
render_with_liquid: false
# Liquid is off for this page: it contains Home Assistant Jinja, which
# shares Liquid's {{ }} delimiters. With Liquid on, those examples render
# as empty strings and nothing errors - see tests/checks/test_docs_site.py.
---

# Examples
{: .no_toc }

Every schedule setting is an entity, everything FLARE is doing shows up as an entity or
an event, and everything it does is an action. So most changes to how it behaves are an
ordinary automation, with nothing in FLARE to configure. These are starting points: each
one is a complete automation to paste in and adjust.

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
  - trigger: time
    at: "21:00:00"
actions:
  # Friday and Saturday evenings set up a lie-in for the next morning;
  # every other evening sets the weekday times back.
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

The part that takes some thinking about is *when* it runs. The schedule reads
`morning_time` afresh each time, so all that matters is what it says when the morning
comes round. Set it the evening **before** a lie-in, and set it back the evening before a
weekday.

- **It runs every evening**, not just at the weekend. The weekday times come back on Sunday
  evening without a second automation, and a missed run is put right the next evening.
- **Day moves with Morning.** Morning runs until Day starts, so pushing Morning to 08:00
  while Day still starts at 08:00 would leave no Morning at all.
- **Run it well clear of the boundaries it moves.** Changing a start time that has just
  passed moves the current phase too: set Morning to 08:00 at 07:00 and the house goes back
  to Night for an hour.

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
              brightness: 255
              kelvin: 6667
              brightness_transition: 60
              kelvin_transition: 60
            day:
              time: "10:00"
              brightness: 255
              kelvin: 6667
              brightness_transition: 65
              kelvin_transition: 1440
            evening:
              earliest: "17:00"
              latest: "20:00"
              brightness: 180
              kelvin: 3200
              brightness_transition: 60
              kelvin_transition: 60
            night:
              time: "23:30"
              brightness: 80
              kelvin: 2700
              brightness_transition: 30
              kelvin_transition: 30
    else:
      - action: flare.import_schedule
        data:
          schedule_device_id: "{{ device_id('sensor.home_flare') }}"
          schedule: |
            morning:
              time: "06:00"
              brightness: 255
              kelvin: 6667
              brightness_transition: 60
              kelvin_transition: 60
            day:
              time: "08:00"
              brightness: 255
              kelvin: 6667
              brightness_transition: 65
              kelvin_transition: 1440
            evening:
              earliest: "17:00"
              latest: "20:00"
              brightness: 180
              kelvin: 3200
              brightness_transition: 60
              kelvin_transition: 60
            night:
              time: "22:00"
              brightness: 80
              kelvin: 2700
              brightness_transition: 30
              kelvin_transition: 30
```

Each schedule is a whole export, so switching sets every setting at once and switching
back puts everything as it was. To make your own, set the schedule up the way you want it,
press **Copy** in its dashboard section, and paste the result in place of one of the
schedules above; then do the same for the other.

A schedule can also leave settings out: anything it doesn't mention keeps its current
value.

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
[Brightness Template](../blueprint/#brightness--exclusions) instead.

## Lighting a room from something other than occupancy

Turn the hall lights on when the front door opens, at the right level for the time of day.

```yaml
alias: Hall lights for the front door
triggers:
  - trigger: state
    entity_id: binary_sensor.front_door
    to: "on"
actions:
  - action: automation.trigger
    target:
      entity_id: automation.hallway_lights
```

The room's automation can't be turned on by **Additional Triggers** — they only update
lights that are already on — but running it from another automation counts as running it
by hand, which can. Running it by hand also brings back to the curve any light in the room
someone set themselves.

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

The Phase event fires each time the phase changes, a manual override included, with the
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
        {{ state_attr(trigger.event.data.entity_id, 'friendly_name') }} in
        {{ trigger.event.data.zone }} was changed by something else, so FLARE has
        stopped driving it until the room goes dark.
```

The event also carries what FLARE last asked for and what the light was actually showing —
see [the hand-over event](../reference/integration/#the-hand-over-event).

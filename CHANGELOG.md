# Changelog

Notable changes per release. Versions follow [semantic versioning](https://semver.org):
from 1.0.0, breaking changes bump the major version. Before 1.0, they landed in minor bumps.

The version in `custom_components/flare/manifest.json` is what
HACS shows as installed, so it and the release tag are checked against each other in
CI — see `.github/workflows/release.yml`.

## [1.0.0] - Unreleased

### Breaking

- **Needs Home Assistant 2026.10.0 or newer.** Earlier versions ask you to pick between
  Schedules, Zones and Flares whenever you add a schedule, zone or flare, which is a Home
  Assistant bug fixed in 2026.10, and the Zones view's Activity uses 2026.10's logbook. HACS
  won't offer this release to an older Home Assistant.
- **Every blueprint automation needs a Zone.** The blueprint has a new required
  **Zone** input: the FLARE zone the room belongs to. It decides which lights FLARE
  remembers driving, and the room's regular update follows the zone's Tick, replacing
  the guess the blueprint used to make from areas. Until one is picked, an automation
  stops with "Missing input zone". **Update Interval** is gone; the zone's timing
  replaces it. **Lights & Occupancy** is now required too.
- **Schedule is now a device, and "bring your own sensor" is gone.** The blueprint's
  **Schedule** input (the `schedule` key, was `adaptive_sensor`) picks a FLARE schedule's
  device rather than its sensor, the same way **Zone** does. A sensor from elsewhere can
  no longer be used; build your own automation on FLARE's services for that.
- **`tracking_device_id` is now `zone_device_id`** on every service that takes it, and
  `flare.claims_check`'s response and the `flare_light_overridden` event name the zone
  in `zone`, not `scope`. Only affects automations of your own; the blueprint is updated.
- **Each zone's claims sensor is now `sensor.<name>_flare_claims`** (was
  `sensor.<name>_flare_tracking`). A new entity is created; delete the old one, which
  shows as unavailable.
- **The zone dashboard view is `custom:flare-zone`** (was `custom:flare-tracking`). Change
  `type:` in your dashboard's YAML.
- **The blueprint ships with the integration.** FLARE's repairs install and update it from
  the integration's own files instead of downloading it from GitHub, so they work offline
  and always install the blueprint that matches your FLARE. It now lives at
  `custom_components/flare/blueprints/flare.yaml`; the repo's `blueprints/` folder is gone.
  It installs to `blueprints/automation/flare/flare.yaml`.
- **A zone's tick is a plain `flare_tick` event, not an entity.** `event.<name>_flare_tick`
  is removed, so ticks no longer fill every zone's Activity and history. An automation of
  your own triggering on it needs an `event` trigger on `flare_tick` with the zone's
  `device_id` instead; the blueprint is updated.
- **`flare_light_overridden` names its light in `light`.** `entity_id` is now the zone's
  `sensor.<zone>_flare_overridden`, which files the event under the zone, so it shows in
  the zone's Activity. Read `trigger.event.data.light` instead.
- **`brightness_multipliers` is now `brightness_levels`** on `flare.apply_lighting` and
  `flare.compute_lighting_groups`. Each light's value is the brightness it's set to, 0–255,
  rather than a multiple of `brightness`, the same way the blueprint's Brightness Template
  already worked. `0` still turns a light off and `null` still leaves it alone. Lights
  without a level get `brightness`, which is now only required if some light has no level.
  A `brightness` of `0` now turns those lights off, as it does for `light.turn_on`; it
  used to set them as dim as they go. So a schedule phase at brightness 0 now turns the
  room's lights off during it.
  `compute_lighting_groups` returns one group per brightness, without the `multiplier`
  field. Only affects automations of your own; the blueprint is updated.

### Added

- **The Zones view's Activity is coloured and filterable.** Each entry's dot is blue when a
  zone takes its lights, amber when something else overrides one, and grey when a zone lets
  them go; buttons at the top show one kind at a time; and selecting an entry opens that
  zone's device page. The entries are Home Assistant's own logbook rows.
- **An All zones row at the top of the Zones view**, laid out like each zone's, with a
  **Clear** for every zone at once. Its counts are two new sensors,
  `sensor.flare_controlled_lights` and `sensor.flare_overridden_lights`, totalling every zone.
- **Room automations that setup creates carry a FLARE label**, so they're easy to find.
- **Flares: a light for each room, for voice assistants and HomeKit.** A flare is a light
  entity over an automation. Turning it on runs the automation, so "turn on the kitchen"
  brings the room up the way FLARE would; turning it on with a brightness or colour sets
  every light in the room to it, and turning it off turns the room off. Add one under the
  new **Flares** entry, picking a room automation from the blueprint, or any other
  automation. Existing installs get the **Flares** entry on the next restart.
- **`flare.claims_override`** marks lights as changed by someone else, so FLARE leaves
  them alone whether or not it was driving them. The opposite of `flare.claims_clear`.
- **Motion sensors work in Lights & Occupancy.** Binary sensors with `device_class: motion`
  now turn a room on and off exactly like occupancy sensors, on their own or alongside them.
  Before, only `device_class: occupancy` sensors were picked up.
- **Adding FLARE sets your rooms up.** Setup asks how many schedules you want and their
  names, then which areas to set up, and with more than one schedule, which one each follows.
  Each area gets a zone, a room automation from the blueprint and a flare, all named after
  it, so there's nothing left to do by hand. You can choose just the zone, or the zone and
  the automation, instead. It finishes with a summary of what it created.
- **Set up area**, the button at the top of FLARE's integration page, does the same for an
  area added later. Every area with lights is listed, with those that don't have a zone yet
  ticked.
- **A ready-made dashboard.** **FLARE Lighting** is now in **Settings → Dashboards → Add
  dashboard**: a view for each schedule and one for your zones, which keeps up as you add
  more. It's the new `custom:flare` dashboard strategy. FLARE's logo is available as an icon,
  `flare:logo`, for its sidebar entry.
- **A redesigned Zones view.** The house's totals at the top, then each zone by floor and
  area, laid out like Home Assistant's Lights dashboard with Clear where that has "All
  off" and the zone's counts where that has lights, and an Activity feed beside them like
  the Security dashboard's. A zone's counts are coloured while they have lights, Controlled blue and Overridden
  amber, and grey at none.
- **A zone's Activity says what it's doing.** "Kitchen now controlling 6 lights"
  (`flare_lights_controlled`) when a zone takes its lights, once per room coming on rather
  than per bulb, and "Kitchen cleared 6 lights" (`flare_lights_released`) when it lets them
  go, as the room goes dark or Clear is pressed. Only an override names a single light.
- **Copy and paste a schedule.** A schedule's times and curve values can be copied out
  as YAML and pasted into another schedule: from the schedule view's new Copy and Paste
  buttons, the schedule's Reconfigure, the curve playground on the docs site, or the new
  `flare.export_schedule` and `flare.import_schedule` services. A pasted schedule with a
  mistake changes nothing and says what's wrong.
- **Floors and labels in Lights & Occupancy control lights.** They used to drive
  occupancy only. A floor covers every area on it; a label covers the lights, devices
  and areas carrying it.
- **A warning when a light is in two zones.** Two zones driving the same light each read
  the other's changes as an override, so the light stops following either. FLARE now
  shows a notification naming the light and the zones when it happens, once per light
  until Home Assistant restarts.
- **Each schedule has a Phase event** (`event.<name>_flare_phase`), fired with the phase
  name whenever the phase changes, a manual override included.
- **Rooms take turns updating.** Every zone now has a **Tick**
  (`event.<name>_flare_tick`), and FLARE fires them one after another, a second apart,
  instead of every room updating on the same second of every minute. A blueprint
  automation updates on its Zone's Tick. The interval and the gap are under **FLARE
  Zones → Configure**.
- **Changes too small to notice aren't sent.** A light within 5% of its target brightness,
  or 5 mireds of its colour temperature, is left alone, which cuts the steady stream of
  tiny updates through a long evening fade. Both are adjustable under **FLARE Zones →
  Configure**, and per call with `min_brightness_change` / `min_color_temp_change` on
  `flare.apply_lighting` and `flare.compute_lighting_groups`.

### Fixed

- **Lights already at the curve are claimed.** After a **Clear**, lights already showing what
  FLARE would set got no change, so they had no claim: they weren't counted as controlled, and
  a change made to them wasn't noticed. `flare.apply_lighting` now claims them as they are.
- **A white light reporting in `xy` is no longer read as overridden.** Some bulbs asked for a
  colour temperature beyond their range report the colour as `xy`. FLARE compared it by RGB,
  and Home Assistant's two conversions to RGB disagree near daylight white, so a bulb showing
  exactly what FLARE asked for read as overridden. A white reported in `xy` is now compared as
  a colour temperature.
- **Renaming a FLARE entity no longer breaks anything.** A schedule kept reading a renamed
  time or curve value's old entity ID and quietly fell back to its default, and the
  dashboard lost renamed entities. Both now find them however they're named. The cards'
  `sensor:` option takes the full entity ID of a renamed schedule sensor.
- **Setup says so when automations.yaml can't be read**, rather than blaming
  configuration.yaml.
- **A light switched on at the wall now follows the schedule.** It used to boot at its own
  default while FLARE's first command was lost, and FLARE then treated it as changed by
  hand and left it alone. A light that has just come back online is now sent the command
  again until it takes.
- **A room with several occupancy sensors no longer goes dark while you're in it.**
  Each sensor timed its Wait time on its own, so the room turned off when the first
  one's ran out, even if another had seen motion since. It now turns off only once
  every sensor has been clear for the full Wait time. A sensor that is unavailable
  no longer counts as occupied, so a dead sensor can't keep a room lit.
- **`flare.claims_check` reports an unreachable light as `unavailable`.** It used to
  judge an unavailable or unknown light against its claims as if it were off, so just
  after a restart it could answer `overridden` and `blocked: true` while the zone's
  sensors showed the same light as unavailable.

### Changed

- **`flare_lights_released` is filed under the zone's Clear button** (`entity_id:
  button.<zone>_flare_clear`) rather than its Controlled count.
- **A light only counts as overridden once it has stayed changed for 30 seconds.** Until then
  it's `mismatched`: left alone, as an overridden light is, but not counted or announced. Most
  short-lived mismatches are FLARE's own change still arriving, a light just back online
  reporting late, or a room being switched off light by light by another automation, which
  used to log an override for every light. `flare.claims_check` reports the new status.
- **FLARE's entries are called Schedules, Zones and Flares**, without the "FLARE" in front.
- **The blueprint's first three inputs are Schedule, Zone and Lights & Occupancy**, in
  that order. **Schedule** is what was labelled **FLARE Sensor**; nothing to re-enter.
- **A zone no longer has a "Lights, devices or areas" field.** It only put the zone's
  device in an area, and nothing uses that now. Existing zones keep whatever area their
  device is in; set one on the device page if you want it.
- **FLARE Tracking is now FLARE Zones, and tracking scopes are zones**, now that they
  do more than track. An existing entry keeps its title; rename it from the entry's
  menu if you like.

## [0.17.0] - 2026-09-22

### Breaking

- **Update the blueprint together with the integration.** The blueprint now turns
  lights off with `flare.turn_off`, which earlier versions of the integration do not
  have, so a new blueprint against an old integration fails with "service not found".
  The blueprint-update repair fetches the version that matches the integration, so
  updating through it keeps the two in step.

### Added

- **`flare.turn_off`.** Turns lights off and records that as FLARE's own doing, so a
  turn-off is not later mistaken for somebody else switching the light off. It takes
  `entities`, an optional `transition` and an optional `tracking_device_id`, and does
  no override protection: it turns off exactly what it is given, including lights
  someone set by hand. The blueprint uses it for its own turn-offs.

### Fixed

- **A light no longer stops following the schedule after an update is cut short.**
  If a room's automation was restarted part-way through changing its lights - a new
  motion event arriving while a two-step bulb was between its two steps, or one
  light's command failing while its neighbours' succeeded - the lights that had
  already changed were treated as if somebody else had set them, and were left alone
  until the room next went dark. Nothing was logged; the light simply stopped
  following the curve. FLARE now records what it is about to send before it sends it,
  so an interrupted update leaves the lights recognisably its own.

### Changed

- **The blueprint turns lights off with one call.** It used to call `light.turn_off`
  and then `flare.claims_record` as two steps, in an order that had the same problem
  as above. Behaviour is otherwise unchanged.
- **`flare.claims_record` is now documented as something to call *before* you write
  your lights, not after.** If you built your own automation on `claims_check` and
  `claims_record`, move the record ahead of your write.

## [0.16.0] - 2026-09-20

### Fixed

- **Leaving a phase that had an idle brightness no longer turns the lights
  up.** A hall set to a 10% nightlight overnight went to full brightness at
  the morning boundary, and only switched off a minute later. The lights
  were still on, which made the room look occupied, so the curve took over
  before anything noticed the room was empty. It now switches them off at
  the boundary itself.

- **Motion into a room sitting at its idle brightness now brightens it
  immediately.** It used to wait for the next scheduled update — up to a
  minute — and then fade in at the background transition rather than the
  motion one. A short walk through often didn't brighten the room at all.

  The cause was a check that skipped the motion run when nothing in the
  room was off, which stopped being a fair question once a room's "off"
  could be dim.

- **Two-step bulbs reporting back in a different colour mode, or sitting
  at their own colour-temperature ceiling, no longer get released as
  "overridden."** A bulb that echoed its actual colour via `rgb_color`/
  `xy` instead of `color_temp_kelvin` (a live incident: IKEA TRADFRI
  spots, after ~89 minutes unavailable) could never match a
  colour-temperature claim by value at all, and a bulb correctly
  settling at its own advertised maximum colour temperature - asked for
  something above what it can produce - was compared only against the
  raw, un-clamped target. Both now compare correctly, so a bulb behaving
  exactly as commanded no longer reads as if someone else had grabbed it.

### Added

- **Two-step transition bulbs are now detected automatically, by device
  manufacturer/model, with no label required.** Getting the
  `no_combined_transition` label onto a known-bad bulb (like an IKEA
  TRADFRI) used to depend on a repair being noticed and its Fix button
  pressed - and if it wasn't, the bulb kept misbehaving. Any light whose
  device matches a pattern in the (still-configurable, Settings →
  Devices & Services → FLARE → Configure) model list is now routed into
  two-step transitions directly. The label still works as a manual
  override for anything the pattern list doesn't cover.

### Removed

- **Update Jitter is gone.** It spread each room's updates over a random
  0–15s delay so rooms sharing a schedule sensor wouldn't all command at
  once. The problem is that it delayed the *decision*, not the write:
  the blueprint works out whether a room may be lit at trigger time, so
  for up to 15 seconds of every minute each room was acting on a stale
  answer — and a light switched off by hand inside that window got
  turned straight back on.

  Nothing replaces it. FLARE only sends a command to a light that isn't
  already where it should be, which is the mitigation that was doing the
  real work; the jitter was added as a precaution and there is no
  evidence it was preventing anything.

  You don't need to do anything. An `update_jitter` left in a room's
  configuration is simply ignored.

- **The "bulbs missing the two-step label" repair is gone.** It only
  ever existed to get you to label a bulb the pattern list could
  already identify - now that matching happens automatically (see
  Added, above), there was nothing left for it to usefully suggest.

### Changed

- **Brightness Template and Idle Brightness Template now accept a single
  number**, meaning "every light in this room", so a whole-room dim level
  no longer has to name each light. Returning a mapping of light to
  brightness works exactly as before.

- **Overrides now survive a restart.** A light somebody else had taken —
  set by hand, from an app, by another automation — used to be handed back
  to FLARE every time Home Assistant restarted, and put straight back on
  the curve. FLARE now remembers who had each light across a restart. A
  light still showing what FLARE last asked for is picked up as normal; one
  showing anything else is left alone until the room next goes dark.

- **Brightness Multiplier Template is now Brightness Template, and takes a
  brightness rather than a multiplier.** It was the only place in FLARE
  where you had to think in multiples of the curve instead of in the
  brightness you actually wanted, and it showed: getting a fixed level out
  of it meant dividing by the curve's current brightness, and getting
  "flat out" meant passing an absurd multiplier and relying on the clamp.

  A value is now a plain 0-255 brightness — the same scale the per-phase
  brightness numbers already use — and it is flat: the light sits at that
  brightness whatever the curve is doing, rather than tracking the curve
  scaled down.

  `0` (turn it off) and `null`/`false` (hands off entirely) are unchanged.

  **This is breaking, and it fails loudly rather than silently.** The input
  was renamed, so a room automation still setting `brightness_multiplier_template`
  raises a `Missing input` repair rather than quietly reading an old
  multiplier as a brightness — `0.4` would otherwise have become "brightness
  0.4", i.e. off. To migrate, replace the old input with `brightness_template`
  and rewrite each value as the brightness you want:

  | Was | Now |
  |---|---|
  | `0.1` while the curve is at 50 | `5` |
  | `10 / state_attr(sensor, 'brightness')` | `10` |
  | `255` (a multiplier, meaning "clamp to maximum") | `255` |
  | `0` | `0` |
  | `null` | `null` |

  A light that should stay *relative* to the curve is still expressible —
  read the curve and scale it yourself:
  `{{ state_attr('sensor.downstairs_flare', 'brightness') | int * 0.5 }}`.

- **Idle Brightness levels are unchanged at 0-255** — they were already on
  that scale, and now match the Brightness Template exactly. Both are
  absolute brightnesses, so a level means the same thing whether the room
  is in use or idle.

- **The blueprint's internal trigger and variable names dropped their
  "adaptive_" prefix** (`adaptive` → `phase_change`, `adaptive_tick` →
  `tick`, `adaptive_target_entities` → `target_entities`), and its
  comments were trimmed throughout for readability. Purely internal - no
  input was renamed, and behaviour is unchanged - but re-importing the
  blueprint (as the version-check repair will offer) picks it up.

## [0.15.7] - 2026-09-08

### Added

- **Idle Brightness — a room's "off" can now be dim rather than dark.**
  Set **Night Idle Brightness** on a hall and it brightens to the curve
  when you walk through, then settles back to a dim glow instead of
  going out. There's an **Idle Brightness Template** too, for naming one
  lamp as the nightlight while the rest of the room goes dark.

  This is the one thing in the blueprint that can switch a light on in
  an empty room, and only for lights you've explicitly given an idle
  brightness. Everything else still can't: a phase change will never
  light an empty room.

  Set it per phase, so a hall can be a nightlight at night and an
  ordinary room the rest of the day. Leave it unset and nothing changes.

## [0.15.6] - 2026-09-08

### Added

- **FLARE now tells you when its blueprint isn't installed, and offers to
  install it.** The integration on its own doesn't drive any lights — an
  automation does, and the ready-made one is the blueprint. If it isn't
  there, a repair appears in **Settings → System → Repairs** and Fix
  downloads it. You'll still create the automation yourself.

  If you'd rather call FLARE's actions from automations you write, ignore
  the repair — the blueprint is optional and Home Assistant remembers an
  ignored repair across updates.

## [0.15.5] - 2026-09-08

### Changed

- **"State device" is now called a "tracking scope" everywhere.** The
  setup screen used to say "Add state device" and then define it, one
  sentence later, as "a named tracking scope" — two names for the same
  thing, on the same screen. Only the wording changes; nothing is
  renamed, moved or reconfigured, and existing scopes are untouched.

### Docs

- The blueprint page leads with its input table instead of ending with
  it, and is organised around what you're trying to do rather than which
  part of FLARE does it. It also named an input that doesn't exist — it
  called **Lights & Occupancy** "Room".
- New "Why didn't my light change?" section, covering the handful of
  reasons FLARE deliberately leaves a light alone.

## [0.15.4] - 2026-09-08

### Fixed

- **The integration's icon had a white square behind it.** The PNGs Home
  Assistant serves were rendered by a thumbnailer that composites onto
  white, so the rounded tile's corners were opaque white instead of
  transparent. They're now drawn directly, with the corners actually
  transparent.

  The icon also shifts very slightly: it is generated from `curve.py`'s
  own defaults, and the generator had been unable to run since the
  integration was renamed, so the shipped icon was drawn from older
  values than the ones FLARE actually uses.

## [0.15.3] - 2026-09-08

### Added

- **FLARE now tells you when your blueprint is out of date, and offers to
  update it.** The integration and the blueprint install separately, so
  it was easy to end up running an old blueprint against new services
  with nothing to say so. When they drift, a repair appears in Settings;
  pressing Fix downloads the matching blueprint and reloads the
  automations using it. Your automations keep their settings.

  The repair only appears when the blueprint itself has actually
  changed, so a release that only touches the integration won't ask you
  to re-import an identical file. It also ignores copies no automation
  is using, which Home Assistant leaves lying around forever.

  If you've edited your own copy of the blueprint, ignore the repair
  rather than submitting it - updating overwrites the file.

## [0.15.2] - 2026-09-07

### Added

- **Beta releases.** FLARE now publishes pre-release builds between stable
  versions. You will not be offered them unless you ask: HACS adds a
  **Pre-release** switch for each repository you have downloaded, and turning
  FLARE's on starts offering betas as ordinary updates. It ships disabled, so
  enable the entity first. Leave it alone to stay on stable releases only.

### Changed

- **The `main` branch is no longer offered as a downloadable version.** It was
  never meant to be installed - it is whatever landed last, including work that
  has not been released - and HACS was listing it alongside the real releases.

### Docs

- The homepage now opens with what FLARE actually does, including two things
  that were not written down anywhere: that it works with lights cut at a
  physical wall switch, and that brightness multipliers, per-phase scenes and
  templates for both exist at all.
- The README shows the dashboard, so what this looks like is visible without
  leaving the repository.
- The Morning research citation was wrong. It described the participants as
  office workers; they were twelve college students, and the sample size was
  never mentioned. Corrected, and no longer written as if it needs defending.

## [0.15.1] - 2026-09-07

### Changed

- **The brightness slider no longer fades with its value.** It's now a
  solid fill in that phase's colour, with how far it fills carrying the
  brightness — the same way Home Assistant's own brightness slider works
  for a light. The fade said what the fill's width already said, and the
  only thing it added was making a dim setting harder to see.

## [0.15.0] - 2026-09-07

### Changed

- **A Curve row now previews the light.** The brightness slider takes its
  colour from that phase's colour temperature and fades it by how bright
  the setting is — so hue comes from the temperature, intensity from the
  brightness, and the two sliders read as one thing rather than two.

- **Colour temperature now sits to the left of brightness**, in both the
  Curve and Transitions groups. The colour is decided on the left and
  carried into the slider on the right, so left-to-right is the order
  they're read in.

  The dashboard view regenerates itself, so there's nothing to do — but
  the two columns have swapped round from what you're used to.

- The brightness feature takes an optional `tint_from` pointing at a
  colour-temperature entity. Without one it falls back to the theme's
  accent colour, so it still works on its own.

## [0.14.3] - 2026-09-07

### Changed

- **The brightness slider's unfilled track is neutral again.** It was
  tinted with the tile's phase colour, which put a phase indicator
  underneath a value indicator and read as two things fighting. It now
  falls through to Home Assistant's own default for a slider — a neutral
  grey that follows the theme — leaving the fill to carry the value and
  the tile's icon to carry the phase.

## [0.14.2] - 2026-09-07

### Changed

- **The brightness sliders now show their value, not just their phase.**
  They took their colour from the tile, so they showed which phase a
  control belonged to and said nothing about the setting — while the
  colour-temperature slider beside them was already painted in the value
  it sets. The two disagreed about what colour meant.

  Brightness has no colour of its own, so the value is carried by
  intensity instead: the theme's accent colour, faded in proportion, so
  it reads as a dimmer. The unfilled part of the track still carries the
  phase colour, so a row is still identifiable at a glance.

### Fixed

- The **Curve playground** link on the documentation home page was dead —
  the page had no permalink, so it only answered at `/playground.html`.
- The home page's description of what "reconciliation" means described
  sharing a room with other automations, which is only half of it. It now
  leads with the part the name is actually about: FLARE knows what every
  light it drives should be showing and keeps working to get it there, so
  a command lost on first send is simply sent again.

## [0.14.1] - 2026-09-07

### Fixed

- **A stale browser cache could serve an old card or feature after an
  update**, showing "Configuration error" where a FLARE card should be
  until the cache expired on its own. The front-end files are now served
  from a URL carrying the integration's version, so every release is a
  new URL and a cached copy from an older one can't be mistaken for the
  current file.

  If you've been hard-refreshing after updates, you shouldn't need to
  any more.

## [0.14.0] - 2026-09-07

### Changed — breaking

- **The schedule dashboard view is now `custom:flare-schedule`**, not
  `custom:flare`. It was named while it was the only strategy; with a
  tracking view alongside it, the bare name gives no hint which of the
  two you get, and the pair now reads as a set.

  **If you added the view, update its type:**

  ```yaml
  views:
    - title: Lighting
      strategy:
        type: custom:flare-schedule   # was: custom:flare
  ```

  A view still using the old name shows "Custom element doesn't exist"
  until it's updated. Nothing else changes — the `sensor:` option and
  everything the view builds are unaffected.

## [0.13.0] - 2026-09-07

### Added

- **A tracking dashboard view**, showing what FLARE is currently driving
  rather than what it's scheduled to do:

  ```yaml
  views:
    - title: Tracking
      strategy:
        type: custom:flare-tracking
  ```

  One section per tracking scope: how many lights FLARE is controlling,
  how many something else has taken over, and a **Clear tracking** button
  that hands them back. When a light has been taken over the section
  names it, so the "which light stopped following, and what took it"
  question is answerable from the dashboard instead of the device page.

  The overridden list stays hidden while the count is zero, so a healthy
  house shows three tidy lines per room.

## [0.12.1] - 2026-09-07

### Added

- **The dashboard view can now show a single schedule**, which reads
  better than all of them stacked once you have more than one:

  ```yaml
  views:
    - title: Downstairs
      strategy:
        type: custom:flare
        sensor: downstairs
    - title: Upstairs
      strategy:
        type: custom:flare
        sensor: upstairs
  ```

  `sensor` is the part before `_flare` in the schedule sensor's entity
  ID, the same value the curve card takes. A full entity ID works too.
  Leave it out and you get every schedule, as before.

  Name a schedule that doesn't exist and the view says so and lists the
  ones that do, rather than rendering blank.

## [0.12.0] - 2026-09-07

### Added

- **FLARE now ships its dashboard.** Add one line to any dashboard and it
  builds itself — a section per schedule sensor, with the curve, the
  phase override, the schedule times, the curve values and the
  transitions:

  ```yaml
  views:
    - title: Lighting
      strategy:
        type: custom:flare
  ```

  There is nothing to fill in. It finds your schedule sensors itself, and
  a schedule you add later appears without you touching the dashboard
  again. Because the view is generated on each load, layout improvements
  now arrive with an update instead of needing anything re-pasted.

  If you'd rather own the layout, Home Assistant's **Take control** turns
  the generated view into ordinary cards you can edit. That's one-way:
  the view then stops tracking FLARE's layout and new schedules won't
  appear on their own.

### Removed

- **The docs site's dashboard generator.** The view strategy above
  replaces it and needs no slug, no copying and no re-pasting. Sections
  you already pasted keep working exactly as they are — they're ordinary
  cards, and nothing about them changed.

## [0.11.0] - 2026-09-07

### Changed

- **The curve chart is no longer blocky.** It was drawing each of its 289
  five-minute samples as a separate flat-topped column, so every
  brightness ramp rendered as a visible staircase and the colour changed
  in hard vertical bands. It is now a single filled shape whose top edge
  runs through the sample points, filled with one smooth gradient.

  Straight lines between samples are exact rather than an approximation,
  since the underlying curve is already piecewise linear in time — so
  this is strictly more faithful than what it replaced, not a smoothing
  fudge.

- **Corners where a ramp meets a flat are now very slightly eased.** The
  one deliberate inaccuracy, and it can only ever round a corner off,
  never overshoot it: the easing is a quadratic whose control point sits
  on the corner itself, so it is mathematically contained within the
  corner it cuts. An interpolating spline would have invented brightness
  the schedule never asks for.

- The chart's markup shrank considerably as a side effect — the curve's
  shape went from 289 elements to a single path of a few hundred bytes.

## [0.10.7] - 2026-09-07

### Reverted

- **The drag-handle recolour from 0.10.6 has been removed.** Home
  Assistant's slider hardcodes its handle to white with no CSS custom
  property and no `part` exposed, so the only way to change it was to
  inject a rule into the slider's own shadow root. That coupled the
  feature to an internal class name, and in practice it silently did
  nothing at all — so it bought fragility and delivered no fix.

  The slider is now exactly the native one again, with only its colour
  substituted. At the pale end of the scale the handle blends into the
  fill, but the fill edge stays readable: the filled portion is solid
  and the remainder is the same colour at 20% opacity.

## [0.10.6] - 2026-09-07

### Fixed

- **The colour-temperature slider's drag handle is no longer invisible at
  pale settings.** Home Assistant's slider draws its handle in white,
  which works against a warm fill but disappears once the colour
  temperature approaches white — around 6667 K, the Day default, white
  contrasts with the fill at 1.03:1, i.e. not at all.

  The handle now flips to near-black at the point where white stops
  being visible (a 1.6:1 contrast floor, which lands near 3500 K). It
  stays white everywhere white still works, so a warm slider is
  unchanged and still matches the brightness slider beside it.

## [0.10.5] - 2026-09-07

### Changed

- **The whole colour-temperature slider now tracks the value, not just
  the fill.** The unfilled remainder takes the same colour as the fill,
  faded — at the same 0.2 opacity Home Assistant's own slider uses, so
  only the hue comes from FLARE. Previously the remainder kept the
  tile's phase colour, which meant the two halves of one control
  disagreed about what they were showing.

  The built-in slider points both `--control-slider-color` and
  `--control-slider-background` at the tile's colour; FLARE now points
  both at the colour temperature. The tile's phase colour still shows on
  the icon, so a row stays identifiable at a glance.

  No configuration change: the feature type is unchanged.

## [0.10.4] - 2026-09-07

### Changed

- **The colour-temperature slider is now literally the native slider.**
  It renders `ha-control-slider` — the element Home Assistant's own
  `numeric-input` feature uses — configured the same way, so the drag
  handle, the rounded fill cap, the tooltip and the keyboard behaviour
  all come from Home Assistant instead of being reimplemented here. The
  only thing FLARE changes is the fill colour, which tracks the colour
  temperature the slider is set to.

  0.10.3 hand-rolled the bar from an `<input type="range">`. The colour
  was right, but it had no handle and no rounded cap on the fill, so it
  visibly didn't match the brightness slider beside it.

  Because the unfilled track once again takes the tile's own colour, as
  the built-in does, a Curve row reads as its phase at a glance with the
  temperature in front of it.

  No configuration change: the feature type is unchanged, so existing
  dashboards pick this up as-is.

## [0.10.3] - 2026-09-06

### Changed

- **The colour-temperature slider now looks like an ordinary slider.**
  0.10.2 painted its whole track as a warm-to-cool Kelvin gradient with
  a thumb and a value label. That read as a colour picker rather than as
  one of a column of matching controls. It is now visually identical to
  the built-in `numeric-input` slider — same height, same corner radius,
  a solid fill to the current value, no thumb, no label — with the fill
  painted in the colour temperature it is set to, changing colour as you
  drag it.

  Its one deliberate difference from the built-in is that the *unfilled*
  remainder is neutral rather than a dimmed tint of the fill, and the bar
  carries a hairline border. An honest orange-to-blue ramp passes through
  white in the middle — 6667 K, the Day default, is very nearly white —
  so a white fill above a white-tinted remainder on a white tile would be
  an invisible control.

  No configuration change: the feature type is unchanged, so existing
  dashboards pick this up as-is.

## [0.10.2] - 2026-09-06

### Added

- **Colour-temperature sliders are now painted in the colour they set.**
  A new card feature, **FLARE Colour temperature**, renders any
  Kelvin-valued `number` entity as a slider whose track runs through the
  actual colour temperature across the entity's own range, with the
  value shown on it. It ships and self-registers inside the integration,
  so there is nothing extra to install, and it is offered in the tile
  card editor for any `number` entity measured in `K` — FLARE's or
  anyone else's.

  The built-in `numeric-input` slider cannot do this: it paints itself
  from `--feature-color`, which the tile card sets to the tile's own
  colour, and a tile's `color` accepts no template. So on the generated
  dashboard section, where a tile's colour encodes which *phase* a
  control belongs to, the slider had no way to also carry the value.
  Now the icon keeps the phase colour and the track carries the
  temperature.

  The gradient uses the same Kelvin-to-RGB conversion the curve card
  draws with, so a slider and the curve above it in the same section
  always agree.

### Changed

- The generated dashboard section uses the new feature for its four
  colour-temperature controls. Re-generate from the
  [Dashboard Generator](https://danrspencer.github.io/flare/dashboard/)
  to pick it up; existing sections keep working unchanged.

## [0.10.1] - 2026-09-02

### Added

- **The curve card is now suggested when you pick a schedule sensor.**
  Home Assistant 2026.6 rebuilt the card picker around entities — pick a
  thing in your home and it offers the cards that fit it. On the **By
  entity** tab, selecting a FLARE schedule sensor now offers **FLARE
  Curve** under *Community*, with a live preview and already sized to
  fill its section, so the card no longer has to be added by hand. Older
  Home Assistant versions ignore this and are unaffected.

### Fixed

- **A card added from the picker's "By card" tab pointed at a sensor
  that no longer exists.** With no configuration the card fell back to
  `sensor.default_flare` — the auto-seeded "Default" sensor the config
  flow deliberately stopped creating — and rendered an error instead of a
  chart. It now picks the first real schedule sensor it can find.

## [0.10.0] - 2026-08-28

### Breaking

- **`check_control`/`record_write`/`clear_claims` are renamed to
  `claims_check`/`claims_record`/`claims_clear`.** All three exist only to
  read or write override-protection claims, and previously used three
  different nouns for the same underlying thing ("control", "write",
  "claims") - unified to one, and prefixed so the three sort and group
  together in Developer Tools -> Actions. Re-import the blueprint
  alongside this release; without it, its own `claims_record`/`claims_clear`
  calls (the turn-off and scene-handoff steps) fail outright, since the
  old service names no longer exist.

### Changed

- **A state device's `target` no longer has any bearing on which lights
  get tracked - it only decides where the device's own entry lands in
  the Area registry.** Which lights a scope tracks was already entirely
  decided by whichever caller (typically the blueprint, via
  `room_target`) names that scope's `tracking_device_id` on a call -
  `target`'s only other job, an implicit area/device/entity fallback for
  the handful of call sites with no caller to ask (`scope_for()`),
  turned out to be dead code: every one of those call sites already
  required an entity to be claimed *somewhere* before it would even
  reach that fallback, which the direct claims lookup always found
  first. Removed rather than fixed, since it never had an effect to
  preserve. The setup form's own description was rewritten to match -
  it previously implied `target` decided claim ownership, which it
  never actually did once caller-supplied scope shipped in 0.7.0.

## [0.9.3] - 2026-08-28

### Fixed

- **Overriding the day phase now shows that phase's own values, not the
  next phase's.** `_value_at()`'s ramp-easing math computed the
  interpolation factor from the real clock relative to the requested
  phase's own natural time span, then clamped it to `[0, 1]` - which
  stops the ramp extrapolating past the next phase's value, but doesn't
  stop it sliding all the way *to* that value once the real time is
  anywhere past the phase's own end. Forcing `select.<slug>_flare_phase`
  to "Night" during actual evening real time showed Morning's
  brightness/colour (255/7000K) instead of Night's own (80/2700K); the
  same happened forcing any other phase. Fixed by holding the phase's
  own value once real time is strictly past its span's end, rather than
  falling through to the ramp/clamp computation.

## [0.9.2] - 2026-08-28

### Fixed

- **The per-scope Clear button now clears every light in one press.**
  `async_clear` built its "did anything change" check as
  `any(store.claims.pop(...) is not None for ...)` - `any()` short-circuits
  on the first `True`, and `.pop()` is what actually clears each claim, so
  the moment the first entity's claim came back non-`None`, every entity
  after it in the list was silently left untouched. A room with several
  tracked lights needed one press per light instead of clearing the whole
  scope at once.

## [0.9.1] - 2026-08-28

### Fixed

- **The curve card's "now" marker is legible against any colour.** It
  used to be a filled dot on the chart itself, which all but vanished
  whenever the current colour temperature came out pale - a cold white
  sits close to the chart's own background. Replaced with a colour
  swatch on the "Now HH:MM · ..." label instead, matching the swatch
  the hover tooltip already used. Both swatches now carry a black
  border so a pale swatch stays visible against a light card background,
  dropped entirely in dark mode.

## [0.9.0] - 2026-08-28

### Changed

- **`scope_device_id` is renamed to `tracking_device_id`** across all
  five services. It was reusing "scope" for an unrelated concept already
  spoken for by `compute_scene_coverage`'s own `scope_entities` field -
  the exact collision the blueprint's Jinja variable
  (`tracking_scope_device_id`) was already renamed once to avoid.
  Re-import the blueprint alongside this release; without it, every
  automation still sending the old field name stops tracking its lights
  (they still get driven correctly, just without override protection)
  until it's updated.
- **`compute_scene_coverage`'s `scene_entity_id` is now required.** The
  service answers a question about one specific scene, and with no
  candidate scene this tick the caller already knows the answer
  (nothing's covered) without asking - same reasoning as the
  `check_control`/`record_write`/`clear_claims` change in 0.8.0. The
  blueprint doesn't call this service today (it keeps its own inline
  Jinja version), so this has no effect on the shipped automation - it
  only affects direct callers.
- Two `services.yaml` selector fixes found in the same review:
  `compute_scene_coverage`'s `target_entities` now correctly declares
  `multiple: true` (it was rendering as a single-entity picker in
  Developer Tools -> Actions despite the backend requiring a list), and
  `record_write`'s `targets` field no longer declares `object:
  multiple: true`, aligning it with the structurally identical
  `brightness_multipliers` field - both are maps, not lists.

## [0.8.0] - 2026-08-28

### Changed

- **`scope_device_id` is now required on `check_control`, `record_write`
  and `clear_claims`.** Each of those exists only to read or write
  tracking claims, so a call naming nothing has nothing useful to do -
  the schema now rejects a missing/null scope outright rather than
  always answering "untracked" or silently recording/clearing nothing.
  `apply_lighting`/`compute_lighting_groups` are unaffected - both stay
  optional, since either still does something useful (dispatch/plan
  lights) with no scope at all.
- The blueprint's own `record_write`/`clear_claims` calls are now
  skipped, not sent, when Room Target resolves to no tracking scope -
  the turn-off/hand-off still happens, it just isn't recorded. Re-import
  the blueprint alongside this release; without it, a room with no
  resolvable scope would otherwise send a now-invalid call and fail its
  tick.

## [0.7.0] - 2026-08-28

### Changed

- **Override-protection services now take an explicit `scope_device_id`**
  instead of resolving which state device owns a light by searching every
  configured one. Pass the tracking scope's own device (a picker in
  Developer Tools -> Actions) on `apply_lighting`, `compute_lighting_groups`,
  `check_control`, `record_write` or `clear_claims`. **Omitting it now
  writes the light but tracks nothing** - no claim is recorded, and
  nothing is excluded as already externally-set - where it previously
  searched by entity, device and area to find a scope automatically.
  A `scope_device_id` naming something other than one of your own
  tracking scopes raises rather than being silently ignored.
- The blueprint resolves this for you from Room Target - no new input,
  and no behaviour change for rooms whose Room Target already names an
  area. Re-import the blueprint alongside this release; without it,
  every automation still calling the old-shaped services stops tracking
  its lights (they still get driven correctly, just without override
  protection) until it's updated.

## [0.6.0] - 2026-08-28

### Changed

- **Switching a light off is now an override.** FLARE used to ignore it
  and relight the light on the next tick; it now leaves it off. The
  claim is released when every light in its tracking scope is off, so
  a room that empties comes back under FLARE's control on its own.
  Anything not reporting `on` counts as off, unavailable included.
- A turn-off records `{"state": "off"}` as its target, so FLARE's own
  off is distinguishable from anyone else's once the write's context
  expires.
- The blueprint records its own turn-offs. Re-import it alongside this
  release — without that step every light in a room reads as externally
  switched off each time the room empties.

### Fixed

- `overridden` now has an automatic way out. Previously only the Clear
  button or a device drop could end it.

## [0.5.1] - 2026-08-28

### Changed

- The curve card names itself after the schedule sensor it is pointed
  at, rather than always reading "FLARE" — so two cards on one
  dashboard are told apart without configuring a title. An explicit
  `title: ""` still suppresses the header entirely.

### Fixed

- Documentation: seven broken links, entity ids in the reference table
  that still carried the old domain (`sensor.<name_>adaptive_lighting`
  rather than `sensor.<name>_flare`), and a copy-paste dashboard
  snippet that still set `day_end_kelvin` and omitted the transition
  entities. Contributing has moved to `CONTRIBUTING.md` in the
  repository.

## [0.5.0] - 2026-08-28

### Changed

- Adding FLARE now creates both entries in one pass. It was two trips
  through Add Integration, once per entry; two entries is a grouping
  decision and never implied two trips to get there. The flow asks the
  one thing there is to ask - which rooms to track - and raises the
  other entry itself. Either half is still creatable on its own, so
  deleting one and adding it back works.
- The documentation site uses the FLARE icon: favicon, sidebar, and
  link previews. The README leads with it too, which is the one surface
  HACS renders for us.

### Fixed

- The repository had no description, which is exactly what HACS shows
  under a store listing's name. Set, along with topics.

## [0.4.2] - 2026-08-28

### Changed

- Transition defaults tuned: an hour at most boundaries, half an hour
  into Morning, and a full-phase colour slide across Day. Only affects
  new schedule sensors - existing ones keep whatever they are set to.

### Fixed

- The sixteen curve defaults live in `curve.py`, `curve.js` and
  `services.yaml`, and nothing compared the three. Both copies are now
  pinned against `curve.py`, so a stale playground default or a stale
  number in Developer Tools -> Actions fails the build.

## [0.4.1] - 2026-08-28

### Fixed

- The dashboard card's default title was still "Adaptive Lighting".
- The curve playground drew nothing: its `buildPoints` still called
  `targetsForPhase` with the pre-transitions signature, so every point
  came out NaN. The parity test drives the two per-phase functions
  directly and never exercised `buildPoints`, so nothing caught it -
  that gap is now covered.
- Transition durations were displayed with the time-of-day formatter,
  which wraps at 1440, so a whole-phase transition read as "00:00".

## [0.4.0] - 2026-08-28

Every phase transition is now configurable, and Day is no longer a
special case.

### Breaking

- **`day_end_kelvin` is replaced by `day_kelvin`**, which is Day's own
  colour rather than the value it ramped toward. It defaults to Morning's
  (6667), because Day's default transition covers the whole phase. Any
  `compute_curve` caller passing `day_end_kelvin` must rename it.
- **Evening's opening colour ramp moved before the boundary.** The change
  now happens in Day's tail, so the Evening boundary *is* the evening
  colour rather than the start of a ramp toward it.
- **Evening's brightness fade lost its 1.6x ratio**, which made it reach
  the night value about 22 minutes early and hold. It now lands exactly
  on the boundary.

### Added

- **Eight transition durations per schedule sensor** - one per phase per
  channel, in minutes, named for the phase the transition runs in.
  `0` is a hard cut; a duration longer than its phase covers the whole
  phase. Exposed as `number.*` config entities and as `compute_curve`
  fields.
- The curve playground gains a Transitions panel.

## [0.3.1] - 2026-08-28

### Fixed

- Every GitHub and documentation-site URL now points at the renamed
  `danrspencer/flare` repository, including the HACS custom-repository
  URL and the blueprint import badge. The site is published at
  `/flare/`.
- The README - which HACS renders as the store page - was still
  describing "Adaptive Lighting" and linking to a documentation page the
  restructure had removed.

## [0.3.0] - 2026-08-28

Renamed to **FLARE** (Flexible Lighting Automation & Reconciliation Engine).

### Breaking

- **The domain is now `flare`.** Every service is `flare.apply_lighting`,
  `flare.check_control` and so on. Home Assistant keys config entries by
  domain and cannot migrate across one, so FLARE installs as a new
  integration: add it, then remove the old one. Deleting the old
  `custom_components/adaptive_lighting_helpers/` directory is part of the
  upgrade - left in place, its code keeps loading alongside and registers
  its own services against its own entries.
- **The card is `custom:flare-curve-card`**, and the blueprint is
  `flare.yaml` - re-import it and repoint your automations.
- **Entity ids** drop "adaptive" for "flare": `sensor.<name>_flare` for a
  schedule sensor, and `sensor.<name>_flare_tracking` / `_controlled` /
  `_overridden` plus `button.<name>_flare_clear` for a tracking scope.
  The schedule's own time.* and number.* config entities keep their ids.

### Changed

- The documentation site is restructured into three tiers - Home,
  Quickstart, and a Power users section carrying the integration
  reference, scene handoff, and building without the blueprint.

## [0.2.0] - 2026-08-27

A large release. Override protection was rebuilt around user-configured
tracking scopes, and the integration now installs as two config entries.
Both halves — integration and blueprint — must be deployed together.

### Breaking

- **`owner_id` is gone** from every service and from the blueprint. Which
  scope tracks a light is resolved from configuration, not declared by the
  caller, so two automations driving one room now co-operate instead of
  each reading the other's write as an override.
- **Services renamed** to match what they actually do, now that nothing is
  "owned" by a caller: `check_ownership` → `check_control`,
  `record_ownership` → `record_write`, `clear_ownership` → `clear_claims`.
- **`check_control` no longer takes `force`.** As a question it had one
  possible answer; forcing is something a write does.
- **Two config entries** instead of one — *Schedules* and *Tracking* — so
  the integration page stops flattening both kinds of thing into one list.
  The services live with Tracking. Migrated automatically: the existing
  entry becomes Schedules, keeping every schedule time and curve value.
- **Claims are no longer persisted.** They live on each state device's
  tracking entity and are lost on restart, which leaves every light
  manageable — the state the old startup resync existed to reconstruct.
- **The `adaptive-lighting-write-tracking` card and its global sensor are
  removed**, replaced by per-scope entities that need no custom card.

### Added

- **State devices**: named tracking scopes with an area/device/entity
  target, seeded per area at setup and on upgrade. Each carries a
  `_flare_tracking` sensor holding the claims, `_flare_controlled`
  and `_flare_overridden` counters, and a Clear button.
- **`EVENT_LIGHT_OVERRIDDEN`**, described in the logbook, carrying the
  scope's `device_id` so hand-overs appear in that device's Activity.
- `check_control` reports the `scope` tracking each light, or null when
  nothing does.

### Fixed

- `record_write` reported every entity passed in as recorded, including
  ones skipped for matching no scope.
- Kelvin churn on bulbs whose advertised colour-temperature range is
  narrower than what they actually report.
- The Evening→Night Kelvin fade was not clamped.
- Scope counters went stale until a claim changed, so a light could be
  reported overridden long after it had been turned off.

## [0.1.0]

Initial version, unreleased and untagged — everything before the above.

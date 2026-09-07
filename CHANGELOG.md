# Changelog

Notable changes per release. Versions follow [semantic versioning](https://semver.org),
with the 0.x caveat that a **minor** bump is where breaking changes land until 1.0.

The version in `custom_components/flare/manifest.json` is what
HACS shows as installed, so it and the release tag are checked against each other in
CI — see `.github/workflows/release.yml`.

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

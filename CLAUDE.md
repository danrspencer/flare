# CLAUDE.md

Context for working on this repo. README.md is the user-facing pitch;
this file is how the code is shaped and why. It records current
architecture and the decisions behind it, not history - git is the
changelog. A fact belongs here once it has stayed true.

## What this is

FLARE is two pieces, and the dependency runs one way:

- **The integration** (`custom_components/flare/`, installed through
  HACS): curve maths, grouping and override protection, exposed as plain
  Home Assistant services anyone can call from their own automation.
  Write and document the services as standalone tools, never as if the
  blueprint were their only caller.
- **The blueprint** (`custom_components/flare/blueprints/flare.yaml`,
  name "FLARE"): triggers, conditions and target resolution, built on
  those services. It does nothing without them. It is a worked example of
  wiring the services up the way most rooms want, not an independent
  piece - don't describe it as "loosely coupled" or "independently
  useful".

It began as one Jinja-heavy blueprint (`adaptive_lighting_unified.yaml`,
still live on the author's HA under `danspencer/`) whose computational
parts were moved into Python. pyscript was tried first and abandoned; it
is gone from the repo and the host. FLARE's blueprint has a different file
name and `name:` from that original so the two can never collide (see
lesson 3).

**Documentation**: README.md is the only Markdown at the root besides
CLAUDE.md, CONTRIBUTING.md (for people working on the code) and
DOCUMENTATION.md (the docs style guide and lexicon - read it before
touching `docs/`). Everything else is the site in `docs/`, published to
<https://danrspencer.github.io/flare/> (see "Versioned docs"): the
quickstart, playground and dashboard pages, `guides/` (how to do more,
with worked examples) and `reference/` (the contract only).
`jekyll-redirect-from` keeps old URLs working, so keep the
`redirect_from` lines. These are **site pages, not GitHub pages**: front
matter goes straight in the files, with no build-time generation step.

**Design rationale never goes on a site page.** It has happened three
times (`dashboard.html`, the homepage, `blueprint.md` grown to 300 lines
of rationale ahead of its reference table). A decision worth recording
goes in a code comment or here.

The Morning research citation ([He et al., 2023](https://pubmed.ncbi.nlm.nih.gov/36058557/),
J Sleep Res) is a small study: twelve college students, 1.5h of morning
light at 1000 lux/6500 K against office light at 300 lux/4000 K for a
week, sleep efficiency 83.8% vs 80.4%. It has been misdescribed once
("office workers", n omitted); cite it as what it is, and re-verify any
factual claim before revising it. Its bright condition is 6500 K, which
DEFAULT_MORNING_KELVIN's 6667 already matches - there's no evidence here
for going cooler.

## The architectural split

**In the blueprint (Jinja/YAML):** triggers, conditions, target
resolution (`resolved_entities`), occupancy (`occupied` and the native
`occupancy.*`/`motion.*` triggers and conditions) and the action
structure. The reason is lesson 1: a `condition:` cannot call a service,
so anything a condition needs must be a template or a native condition.
These parts also get real value from HA's trace UI.

- Scene compatibility (`scene_active`/`scene_valid`) also exists as the
  `compute_scene_coverage` service, but the blueprint keeps its own Jinja
  copy because a `condition:` reads it. See "Parked: scene handling".
- Override protection is in Python, re-checked against live state on
  every call, never a one-shot trigger check (lesson 2).
- **The blueprint knows phase names in three inputs** - `rgb_phases`,
  the four scene pickers and the four exclude lists - a deliberate
  exception, because a Jinja template is poor UI for something this
  simple. In both templated cases the template wins and the per-phase
  pick fills in what it doesn't cover.

Blueprint input mechanics:

- Inputs are grouped with `sections:`; nesting doesn't change an input's
  name for `!input`.
- `homeassistant.min_version: 2026.4.0` is what `occupancy.*` needs.
- **Schedule and Zone are device selectors** (`integration: flare`,
  `model: Schedule` / `model: Zone`). The blueprint finds the schedule's
  sensor in `variables:`. Triggers can't do that lookup, hence the
  schedule's Phase `event` entity. There is no "bring your own sensor":
  anything different is someone's own automation on the services.
- **Input renames are breaking**: a stored input stops matching, so every
  room automation needs the old key removed outright.

**In the integration:** reachability, brightness bucketing, the
tolerance-based "already set" check, override protection and two-step /
RGB routing (`grouping.py`) - the genuinely gnarly part, untestable in
Jinja; the day curve (`curve.py`); scene-coverage gap filling
(`scenes.py`, generic, nothing lighting-specific).

**Everything is an entity or an action, so a default can be replaced
rather than configured.** Schedule settings are `time`/`number`
entities, live state is sensors and events, and everything FLARE does is
a service. Most "can it do X differently?" answers are an automation
changing an entity or calling a service. Keep new behaviour in that shape
- an entity or a service before a config option. The homepage's "Made of
ordinary Home Assistant parts" section promises it. (The Zones entry's
options - tick timing, minimum change, two-step models - are the
exception: entry-wide plumbing.)

## Hard-won lessons (don't repeat these)

1. **HA `condition:` blocks cannot call services.** This is the
   constraint that shaped the split above.

2. **A trigger firing once is not a standing invariant.** A one-shot
   trigger-level check blocks only the run it fires in. Override
   protection re-checks the light's current state on every call, which
   is why room-empty, light-off and recovery releases all fall out of it.

3. **A same-named blueprint can take out every room at once.** Linking
   this repo's blueprint over the live `adaptive_lighting_unified.yaml`'s
   filename broke all 15 room automations using it. FLARE's blueprint has
   its own filename and `name:`; don't reintroduce a collision.

4. **Jinja macros return text, never a list.** A macro handing back a
   list within one template must round-trip through
   `to_json`/`from_json`. Shared `custom_templates/*.jinja` macros were
   abandoned for this and lesson 5.

5. **`custom_templates/*.jinja` files are scanned only at startup.** A
   new file needs a full restart, not a reload.

6. **A stray directory under `custom_components/` with the same
   `domain:` in its manifest breaks the integration** (a bare
   `404 Invalid handler specified`), because HA discovers integrations by
   manifest, not by directory name. Removing it needs a restart too.
   Clean up backups promptly.

7. **Wrong-but-similar arguments and missing `@callback`s sit dormant
   until a real event loop runs them.** Seen twice: a coordinator given a
   string where a `Logger` was expected, and a state listener without
   `@callback` calling `async_create_task` from the worker pool. Unit
   tests can't catch either; check `core.py`'s
   `get_hassjob_callable_job_type` before trusting a fix.

8. **`sun.sun`'s `next_setting` is the *next* sunset**, tomorrow's once
   today's has passed. `curve.py` projects its local time of day onto
   today instead of using the timestamp.

9. **A branch-name `raw.githubusercontent.com` URL can serve a stale
   copy for minutes after a push**, while the fetching tool reports
   success. Pin to a commit SHA and confirm what landed with
   `ha_read_file`.

10. **`ha_import_blueprint` derives the install path from the URL**
    (`<owner>/<file>`), never the path in use, so it lands beside it.
    FLARE's blueprint lives at `flare/flare.yaml`, which no URL import
    produces: write it with `ha_manage_blueprints(action="save", ...,
    overwrite=True)`. An unused copy elsewhere is harmless.

11. **A `target:` selector's `entity:` is the filter list itself**
    (`target: {entity: [{domain: light}, ...]}`), unlike the plain
    `entity:` selector's `filter:` key, which fails import under a target
    with `extra keys not allowed` (`TargetSelectorConfig.entity` in
    `helpers/selector.py`).

12. **In a sections view, a card doesn't fill its section just because
    the section is wide.** A nested `grid` card or a custom card without
    `getLayoutOptions()` renders at its natural size; give it
    `grid_options: {columns: full}`.

13. **A blueprint input with no `default:` is required**, whatever its
    name says. Four new optional inputs without one broke all 15 room
    automations at the next import (`Missing input ...`, 15
    `validation_failed_blueprint` repairs at once). Every optional input
    needs an explicit default.

## Current status

### Code layout (`custom_components/flare/`)

Grouped by **concept**, not by how something is exposed. Grouping by
exposure (entities / services) tangled, because the schedule and the
claims are each exposed through both.

- `schedule/` - what lights should look like: `curve.py`,
  `coordinator.py` (`ScheduleInstance`, `TIME_KEYS`, `CURVE_KEYS`),
  `transfer.py` (YAML export/import).
- `zone/` - who owns a light (`override_protection.py`, `claims.py`),
  the zone device (`instance.py`) and when each zone ticks (`ticker.py`).
- `flares/` - lights over automations: reading an automation's inputs
  (`automation.py`), what counts as a bare turn-on (`bare.py`), the flare
  (`instance.py`). The entity is the root `light.py`.
- `services/` - `handlers.py` (the claims and lighting services),
  `schedules.py` (export/import) and the planning behind them:
  `grouping.py`, `scenes.py`, `two_step.py`.
- package root - what HA dictates: `__init__`, `config_flow` (the main
  flow; `subentry_flows` and `options_flow` hold the rest), `repairs`,
  `logbook`, `const`, and the eight entity platform modules, which
  **cannot** move into a folder (HA imports
  `custom_components.flare.<platform>`). Also `area_setup`, which needs
  zones, flares and the blueprint at once. `services.yaml`,
  `strings.json` and `translations/` stay at the root; `www/` is the
  dashboard.

**Dependencies run one way**: `schedule/`, `zone/` and `flares/` import
only `const.py`; `services/` may use `schedule/` and `zone/`; the root
may use everything. `tests/checks/test_layering.py` enforces it.
`services/__init__.py` holds no imports.

**`strings.json` is the source and `translations/en.json` a copy**, which
is what HA shows for a custom integration. They had drifted;
`tests/checks/test_translations.py` keeps them identical. **Placeholders
must be plain `{name}`s**: hassfest parses each string with Python's
formatter and rejects ICU plurals, though HA's frontend would format them.
The same test applies hassfest's rule, so word a count so it needs no
plural form ("Flares added: {count}").

### Services

Eleven, all tested. Field contracts are in `docs/reference/services.md`
and `services.yaml`, not repeated here.

- `compute_lighting_groups` / `compute_curve` / `compute_scene_coverage`
  - pure planners.
- `apply_lighting` - writes. Takes `brightness`/`color_temp_kelvin`/
  `rgb_color` as **plain values**, not a sensor, so any source works;
  don't move the sensor read into the service.
- `turn_off` - records `{"state": "off"}`, THEN calls `light.turn_off`,
  as one operation, with **no** override protection (a room emptying
  takes hand-set lights too). The order and that private encoding are
  why it exists; **don't split it back into two steps in a caller.**
- `claims_check` / `claims_record` / `claims_clear` / `claims_override` -
  override protection on its own. `claims_clear` is the escape hatch for
  a light stuck `overridden`; `claims_override` marks lights as someone
  else's (what flares use).
- `export_schedule` / `import_schedule` - see "Schedules". Registered in
  `async_setup`, not by an entry: they need only a schedule's entities.

`rgb_color` accepts an explicit `None`, since a caller templating it from
a missing attribute renders a literal null.

### Override protection

Each tracked light carries two claims, `observed` (a write seen landing)
and `latest` (the most recent attempt). The model and why it needs two
are in `claims.py`'s docstring; the decision table is
`override_protection.classify()`; the user-facing contract is
`docs/reference/zones.md`. **Everything judges a light through
`classify_state()`** - `grouping.py`'s `externally_set()`, the sensors'
`_classify_tracked()` and `claims_check` - because they drifted apart
twice when each did its own. `tests/checks/test_one_classifier_adapter.py`
fails if anything else calls `classify()`.

Facts verified against HA core:

- **`context.id`, not `context.user_id`**: every call in one automation
  run shares the run's context, so user_id can't tell FLARE's write from
  another automation's.
- **`Entity._context` expires 5 seconds after the call**, so a slow
  device reports back under an unrelated context while echoing what was
  asked. Claims therefore record a `target`, and `classify()` also
  compares values against either claim's target.
- **Zigbee bulbs speak mireds**, and HA's Kelvin/mired conversions both
  `floor()`. Two Kelvin values flooring to the same mired are the same to
  the device, so `_color_temp_matches` treats them as equal.
- **A bulb's advertised colour range isn't always honest**
  (`light.utility_spot_1` claims max 4000K and reports 5813K), so
  `_already_set` accepts the raw target or the clamped one.
- **The minimum change (`min_brightness_change` %, `min_color_temp_change`
  mireds) lives only in `_already_set`**, never in `classify()`: it
  decides what's worth sending, and widening override matching by the
  same amount would let a hand-set light near the curve read as FLARE's.
  Colour is in mireds because a flat Kelvin gap is ~4x coarser at 6500K.
  Defaults 5/5, on the Zones entry's options; a call can override them.
- **`force` is the only bypass.** A light's claims belong to whatever
  zone a caller names.

**Zone is caller-supplied, never resolved.** Every claims service takes
`zone_device_id` (a zone's device), which `resolve_zone_device()` turns
into a subentry id. It is optional only on `apply_lighting` /
`compute_lighting_groups` ("write, track nothing"), and required on
`claims_check` / `claims_record` / `claims_clear`, which have nothing to
do without one. A device that isn't one of this entry's zones raises
`ServiceValidationError`. Nothing guesses a zone from areas or devices -
removed at the user's direction: *"there's just too much weird behaviour
if it gets the wrong one"*.

**Being switched off is an override.** `classify()` doesn't
short-circuit on off. A FLARE turn-off records `{"state": "off"}` as its
target, which is what tells FLARE's off from anyone else's after the
context expires; without it a room turned off at bedtime could never come
on again. The blueprint's own turn-offs are `flare.turn_off`, never a
bare `light.turn_off`.

**Claims are recorded before the write, never after.** `apply_lighting`
and `turn_off` call `async_record` before dispatching. Recording after
lost the claim whenever a run didn't finish - a group's call raising, or
`mode: restart` cancelling the call while a two-step bulb slept between
steps (a real `Script` does cancel a running blocking call) - and the
light then silently read `overridden`. It's safe because a write that
never lands leaves the light matching its previous `observed` claim. So
the two-step contexts are created up front, and `async_record` has no
awaits inside. **"Seen landing" means a context match only.** Pinned by
`tests/functional/component/test_interrupted_writes.py`.
`flare.claims_record` is documented as call-before-your-write for the same
reason.

**A light claimed in two zones raises a persistent notification**
(`flare_light_in_two_zones_<entity_id>`; a notification, not a repair,
at the user's direction), once per light per run. Each zone would read
the other's writes as overrides. Detected at write time, so it covers
service callers too.

**A zone releases every claim once none of its lights is `on`**
(`_release_if_dark`). Anything not `on` counts as dark, unavailable
included, or one dead entity would block the release forever. "The room"
is the zone: an untracked light holds nothing open. It fires only on a
transition from a real on/off state (see below).

**Known limitation, partly mitigated:** an `overridden` light is excluded
from every group, so it never gets a fresher claim, and on a ramping
curve the value match drifts further away. The zone going dark clears it;
`claims_clear` and the Clear button cover a room that never fully does.

### Claims across restarts and reconnects

The claims sensor (`_ZoneClaimsSensor`) is a `RestoreEntity`; its claims
are its `extra_restore_state_data`, restored before it registers.
Persistence was tried once and reverted: a restart gives every entity a
fresh context, and with context-only matching every light read
`overridden`. The value fallback above is what makes it safe now: a
restored claim can't match on context, but a light still showing what
FLARE asked for matches on value.

Two listener rules, pinned in `test_claim_persistence.py`:

- **No "recovery re-baseline".** Replacing `observed` with the live
  context whenever a light arrived from unavailable/unknown only ever
  fired on restarts, and would mark every override `controlled` moments
  after the restore. `restored: True` can't gate it, because MQTT lights
  reach `on` from their own untagged `unknown`. Don't rebuild it.
- **`went_off` needs a real starting state.** Lights reconnect one at a
  time; the first back being `off` while its siblings are `unknown` must
  not release the zone.

A restart is not an escape hatch for a light stuck `overridden`. Known
residuals, both ending when the room goes dark: a bulb that power-cycled
while HA was down, and a write that dropped just before a restart on a
light with no confirmed write. Restore state is saved every 15 minutes
and at shutdown, so a crash loses up to 15 minutes of claims, failing
open.

**Reconnects** (`classify_state`'s `reconnected_at`; `claims.py` notes
when a light goes unavailable/unknown -> on/off, and forgets it once a
FLARE write is seen landing):

- **A command lost as a light comes back is resent, not an override.**
  Found live: a Hue bulb on a wall switch booted at its default, the
  `recovered` trigger's write 26ms later never took, and it read
  `overridden` every evening. A light that would read `overridden` is
  `untracked` while it came back, was last updated within
  `RECONNECT_SETTLE` (30s) of that, and FLARE's latest write was recorded
  after it came back. That last condition keeps a real override real: a
  light someone changed before it dropped out has its last FLARE write
  from before. Note `latest` can't stand in for "landed": it's promoted
  only at the next write.
- **Otherwise, within 30s of coming back, it's `settling`**: blocked like
  an override, but counted in neither sensor and not announced. A bulb's
  first report after reconnecting is often stale (seen live after a
  restart: 10/8130 on a bulb at 204/8105, corrected 0.4s later), and the
  zone announced overrides that never were. The claims sensor rechecks
  once it has settled. It's a status of `classify_state`, so
  `claims_check` and `apply_lighting` agree with the sensors.
- Still parked: the same loss when FLARE wrote *before* the reconnect
  (needed three restarts in fifteen minutes, which ordinary use doesn't).

**Testing restore needs a real entity add.** The usual harnesses attach
the claims sensor with a capturing `async_add_entities`, so
`async_added_to_hass` never runs. `test_claim_persistence.py` adds it
through `MockEntityPlatform` with `mock_restore_cache_with_extra_data`,
and saves through `async_mock_restore_state_shutdown_restart`.

### Three config entries

FLARE installs as **three** entries: *Schedules*, *Zones* (the services,
the claim registry, the tick scheduler and the zones) and *Flares*. HA's
integration page renders one section per subentry with no way to group
them by type (`ha-config-entry-row.ts`), so one entry flattened 19
schedules and zones into a single list; the entry is the only level that
can group them. The services live with zones because they're all about
which lights are driven by whom and need the claim registry.

- **Entry titles have no "FLARE" prefix** (the page already says FLARE);
  docs write the path as **FLARE → Zones**. User's call.
- **The stored values can't follow the user-facing names**:
  `ENTRY_TYPE_ZONES` is `"tracking"` and `SUBENTRY_TYPE_ZONE` is
  `"state"`, because HA can't retype a subentry and recreating zones
  would change their device ids.
- Schedules and Zones both use the sensor platform; each platform module
  branches on `entry.data[CONF_ENTRY_TYPE]`. **`async_setup_entry` treats
  anything that isn't Zones or Flares as Schedules**, so a new entry type
  must branch before that fallthrough.

**One "Add Integration" sets FLARE up ready to use, rooms included** -
the goal, at the user's direction, is a painless first install. The main
flow asks how many schedules and their names, then which areas to set
up, creates each missing entry through `SOURCE_IMPORT`, and hands the
areas to `area_setup.async_set_up_areas`. Each entry can still be added
alone, so deleting one and adding it back works.

**The flow ends on an abort carrying a summary, never on an entry**,
because HA's "integration added" dialog (`step-flow-create-entry.ts`)
puts every device of the entry the flow completes on through a
rename/area form. It's gated on the flow's own `showDevices` (false for
options flows) and filtered to the completing entry's devices, so only
the main flow at entry creation is affected; subentry flows creating
devices later are fine. Re-verified against the frontend once, after an
overstated version of this caused a wrong call.

**Once every entry exists, the main flow is "Set up area"**
(`config.initiate_flow.user`). The integration page's top row is the main
flow's button and then one Add button per subentry type, so it reads Set
up area, Add schedule, Add zone, Add flare. The main flow is the only one
not tied to an entry, and area setup touches all three.

**Area setup** (`area_setup.py`), per area: a zone (reused if one has
the area's name), an automation from the blueprint, and a flare named
after the area. **For each area, set up** picks zone / + automation /
+ flare for the whole run (per area it would crowd each area's schedule
dropdown; Set up area can just be run again).

- **The automation is written to automations.yaml as HA's automation
  editor does** (`components/config/automation.py`): load, append, dump,
  `write_utf8_file_atomic`, reload. There's no public API. Each is
  validated with `async_validate_config_item` first. If the reload
  doesn't produce the entities, configuration.yaml doesn't include the
  file, and the original text is restored byte for byte. An unreadable
  file (not YAML, or not a list) is left alone with its own message. A
  successful write drops comments in the file, as the editor does.
- **Each automation gets the "FLARE" label** (created the first time), at
  the user's request, so they're easy to find and manage.
- **Not yet handled: a failure partway leaves what was created.** Zones
  (and on first setup the entries) exist before automations.yaml is
  written. Deliberately left for a decision of its own.
- **The zone's device is created by `area_setup`**, since the automation
  needs its id now; the entry's reload finds it by identifiers. The tick
  trigger matches on the device id alone, so the automation works before
  the zone's entities exist.
- **"Already set up" means a zone with the area's name exists**, which
  only unticks the area; every area with lights is listed (user's call,
  after reading automations' targets proved unreliable). Re-running an
  area reuses its zone but adds another automation and flare.
- **With several schedules each area is a field named after it**: the
  dialog falls back to a field's name when it has no translation, the
  only way to label fields made at runtime.
- **The flare is part of the default**, the one exception to "nothing
  creates flares automatically" - the user is choosing to set the area up.

**The dashboard is offered, not created**: `custom:flare` is listed in
**Settings → Dashboards → Add dashboard** through the frontend's public
`window.customStrategies`. Creating it from setup was built and dropped
at the user's direction: HA keeps the dashboards collection private, and
the only way in was unwrapping a websocket handler. Don't bring it back.

### Flares

A flare (`light.<slug>_flare`, `light.py` + `flares/`) is a light over an
automation, so voice assistants, HomeKit and dashboards can switch a room
without bypassing it - a hand "on" from Siri reads as an override and
leaves the room wherever the bulbs restored to.

- **A bare turn-on is `automation.trigger`.** How a room comes on is the
  automation's decision, and a manual run already passes `allow_turn_on`
  and `force`, so "on" again also hands an overridden room back. "Bare"
  is no keys but `transition` (`flares/bare.py`); HA strips `transition`
  unless the light supports it, hence the test's `supports_transition`
  bulbs.
- **On with values, and off, mark the lights overridden first**
  (`flare.claims_override`, in the zone named by the zone input), then
  forward as `LightGroup` does. Without it an unclaimed light - every
  light once a room goes dark - is `untracked`, and the run the change
  itself triggers took it over, dimming Siri's "100%" back to the curve,
  live. The override claim has a fresh context and no target, so it never
  matches; a bare "on" takes it back.
- **Off is a plain `light.turn_off`**, never `flare.turn_off`: a flare's
  off is the user's. `flare.turn_off` shipped once as the default, and a
  run landing while the room was half-off relit it.
  `test_a_room_turned_off_from_its_flare_stays_off_when_a_light_change_runs_the_automation`
  pins it, with `reports_off_late` bulbs.
- **A flare stores the automation (by entity-registry id, so a rename
  doesn't orphan it) and the NAMES of the inputs holding its lights and
  zone**, read live - `room_target`/`zone` for our blueprint
  (`BLUEPRINT_*_INPUT`, pinned by `tests/checks/test_flare_inputs.py`). A
  plain automation stores a target instead.
- **The inputs come from the automation entity's private
  `_blueprint_inputs`** (`raw_config` is the substituted config). An
  accepted risk, kept to `flares/automation.py:blueprint_inputs`; the
  behaviour tests break if HA changes it.
- **Add Flare lists only automations from our blueprint** (user's call);
  any other automation goes through the custom path, which offers only
  inputs that can hold lights. Room flares are added in bulk, all
  ticked, each with `async_add_subentry`; `_async_reload_entry` coalesces
  the listeners queued together into one reload.
- **Every flare's Reconfigure shows the same fields**, however it was
  added.
- **Nothing creates flares automatically** except area setup: a HomeKit
  bridge including `light`, or Alexa/Google exposing new entities, would
  put every room in the Home app after an update.
- **The flare's device is placed in the automation's area once, at
  creation** (`_place_in_area`), never again. Not
  `DeviceInfo.suggested_area`, which is deprecated.
- **Membership is `async_track_target_selector_state_change_event`**,
  re-resolved on registry changes, `automation_reloaded` and HA start
  (automations load after FLARE). It skips hidden and categorised lights,
  unlike the blueprint's `area_entities`.
- **A flare must never be one of a room's lights**, or the room's tick
  would send it the curve and it would pass that on as an override.
  Three layers: the blueprint rejects `integration_entities('flare')`,
  the services drop flare lights (`_without_flares`), and a flare's own
  filter drops other flares (or it recurses forever). Blueprint tests need
  a real `MockEntityPlatform` entity for `integration_entities`
  (`add_flare_light`).
- **The light platform is only forwarded when the entry has flares**, or
  an empty entry sets up `light` early and breaks the behaviour tests'
  fake bulbs.

### Schedules

Each schedule is a "sensor" subentry of the Schedules entry, with its own
device. `schedule_instances(entry)` is the one place enumerating them.
Every entity has `has_entity_name=True`, so renaming the device renames
them all.

- `sensor.<slug>_flare` - the phase as state; `brightness`/`color_temp`/
  `rgb_color`, today's boundaries and `points` (289 samples, what the
  chart reads) as attributes. `points` is too big for the recorder:
  `_unrecorded_attributes`.
- `select.<slug>_flare_phase` - a manual phase override, clearing itself
  at the next natural boundary unless `switch.<slug>_sticky_phase_override`
  is on (compared against the phase computed at override time, not a
  timer).
- Five `time.*` boundaries and sixteen `number.*` curve values, all
  `entity_category: config`.

**Config lives in entity state, not `subentry.data`**: a subentry data
change reloads the whole entry. A missing entity falls back to the
default it will report moments later, so `phase_at()` never sees a gap.
**Entities are read by unique ID** (`ScheduleInstance.current_id()` and
its wrappers), never by the ID they were created with, so a user renaming
one doesn't silently fall back to defaults.

**Every FLARE entity's translation key is its role** (its unique ID's
suffix: `schedule`, `morning_time`, `night_kelvin`, `claims`, `clear`
...). The dashboard finds entities by device and role through it
(`flare-entities.js`), so renamed entities still show.
`tests/functional/component/test_entity_roles.py` ties the keys to the
roles the dashboard's test fixtures (`tests/support/registry.py`) assume.

**A schedule exports and imports as YAML** (`schedule/transfer.py`),
keyed by phase, through the two services, Reconfigure, the transfer card
and the docs playground.

- Parsed with PyYAML's `BaseLoader` (every scalar a string): YAML 1.1
  reads an unquoted `06:30` as the base-60 number 390.
- `dump()` writes text by hand so every time is quoted.
  `docs/assets/js/schedule-yaml.js` is the playground's copy, held to it
  by `test_schedule_yaml_parity.py`.
- Import sets values through `time.set_value` / `number.set_value`, after
  parsing everything first; Reconfigure aborts rather than updating the
  subentry, so there's no reload. Times needn't be in order.

### Curve math (`curve.py`)

Every literal is a keyword-only parameter with a named default
(`DEFAULT_CURVE_VALUES`, `DEFAULT_SCHEDULE_HOURS`).

- The brightness fade spans **1.6x the evening-to-night window**, as a
  ratio so a custom range keeps the same shape.
- `day_phase` is a **parameter**, not derived from the time, because a
  manual override passes a phase the clock disagrees with. Every ramp
  clamps its factor for that reason.
- `kelvin_to_rgb` **delegates to HA's `color_temperature_to_rgb`**
  (measured identical to the copy it replaced, 1000-10000K). Ours is only
  the round-half-up wrapper, matching the card's `Math.round`; today
  `round()` would pass every test (no integer Kelvin lands on .5), so
  it's kept deliberately. HA clamps to 1000-40000K;
  `test_below_1000k_clamps` is a dependency contract, not a logic test.
- **Don't re-add `night_floor_kelvin` or `kelvin_rgb`** - both cut at the
  user's direction. RGB is just Kelvin converted.

### Blueprint (`custom_components/flare/blueprints/flare.yaml`)

**It ships inside the integration**, and both blueprint repairs install
it from there (see "Blueprint version checking"). HA never auto-installs
a custom integration's blueprints. It has no `source_url`, so HA's
"Re-import" (which would fetch `main`, lesson 9) isn't offered.

**Every `condition:` and every `choose:` branch has an `alias:`**, so the
trace viewer has something readable to show (HA accepts `alias` on all of
them). The top-level `condition:` uses the explicit form
(`condition: or`, `conditions: [...]`), not the `or:` shorthand: the
viewer's `resolveYamlPath()` recognises shorthand as a single-key map, so
an `alias` beside it would break path resolution.

**`room_target`** is one entity/device/area/floor/label target doing
double duty: lights in it are controlled, and occupancy- and motion-class
`binary_sensor`s in it drive occupancy through HA's native `occupancy`
and `motion` triggers (each filters by its own device class, so there's
a detected and a cleared trigger for each, sharing the `motion_on` /
`motion_off` ids). It's resolved once into `target_named_entities` and
`target_expanded_entities`, kept apart because a directly named light
pulls in its device's siblings for scene scope while the expanded half
already holds them. Floors resolve to areas, labels to their entities,
devices and areas. The `recovered` trigger repeats the resolution, since
a trigger template can't read `variables:`.

`room_occupancy_entities` exists only to know whether the room has a
sensor at all: `occupancy.is_detected` over zero entities is vacuously
**false**, so a light-only room would otherwise always read empty.

**Triggers:** `phase_change` (`event.received` on the schedule's Phase
entity, fired only on a real phase change, and once after setup so a
restart repaints rooms), `tick` (an `event` trigger on `flare_tick` with
the zone's `device_id`), `extra`, `motion_on` / `motion_off`, and
`recovered`.

- **Zone ticks stop every room writing in the same second.** All rooms'
  `time_pattern`s fired within 0.2s of :00, and Zigbee route failures
  clustered in seconds 0-4 of each minute. `zone/ticker.py` fires each
  zone's tick a gap apart, in title order. The decision is still made
  fresh at trigger time, so this is not the removed jitter.
- **The tick is a plain bus event, not an entity** (user's call): as an
  event entity it logged every minute in every zone's Activity and
  history. Undescribed bus events never reach the logbook. Nothing then
  cancels the scheduler at shutdown, hence the explicit
  `EVENT_HOMEASSISTANT_STOP` listener (the tests fail on lingering timers
  without it). One recorder row per zone per interval, accepted.
- **The zone is its own input**: Lights & Occupancy's target picker lists
  a device only if it has an entity passing the light/sensor filter
  (`getDevices`), which a zone doesn't.
- `tick` exists because the curve ramps within a phase while
  `phase_change` only fires at boundaries.
- `recovered` arms on "at least one of our lights is reachable". The
  inverse lets one dead light disable recovery for the room forever. A
  flaky bulb beside healthy ones waits for the tick. Its template **can't
  reference `trigger.*`** (only `trigger_variables` are in scope), or it
  never fires.

**There is no delay anywhere in `action:`, and there must not be.**
`variables:` render once, at trigger time, so anything after a delay acts
on a snapshot. A 0-15s jitter delay made a light switched off by hand
inside the window get relit by a run that had already decided the room
was in use. Override protection can't catch it: turning off the zone's
last light rightly releases every claim, so the only thing saying no is
`allow_turn_on`, and a delay makes that stale. Pinned by
`test_nothing_delays_the_action_before_it_decides`.

**`condition:` doesn't check occupancy.** Occupancy's only jobs are
turning a room on (with `allow_turn_on`) and off; gating ticks on it
skipped lights that were already on.

**`allow_turn_on` = `manual_run or trigger.id == 'motion_on' or
occupied`. It must never gain a new way to become true without the user
explicitly asking for it in so many words** - not implied, not inferred
as reasonable. This is the user's emphatic, standing position. Note
`automation.trigger` from another automation counts as a manual run, so
anyone wanting an event to light a room writes their own automation.

**It's one structural gate.** Exactly two things can switch a light on,
`scene.turn_on` and `flare.apply_lighting`, and both sit inside one
`if allow_turn_on` block in `default:`; anything new that can switch a
light on goes there too.
`test_no_trigger_reaching_default_can_light_a_dark_empty_room` sweeps
every trigger. Before this the rule was enforced two ways and the scene
path not at all, and a phase change lit an empty dining room nightly.
**Don't re-add the per-entity `reject('is_state', 'off')` filter**: a
false `allow_turn_on` already means nothing in the room is on.

**Idle Brightness** makes a room's "off" dim rather than dark - the
nightlight. Four per-phase inputs plus `idle_brightness_template`, with
the template winning (`dict(phase_base, **template_result)`). **It's the
one thing that can switch a light on outside `allow_turn_on`**, at the
user's explicit request (*"its a nightlight so it can turn on (because
we're redefining what 'off' means)"*); `allow_turn_on` itself is
unchanged.

- **The curve's gate is `allow_turn_on and not room_is_idle`.** An idle
  light being on makes `occupied`, and so `allow_turn_on`, true, and the
  next tick would ramp the nightlight back up. Mutation testing found it;
  `test_an_idle_light_does_not_ramp_itself_back_up`.
- The idle branch must not be gated on `occupied` or `allow_turn_on`,
  both true once an idle light is lit.
- `room_occupancy_entities | length > 0` is required (vacuous false
  again), or a light-only room sits idle forever.
- `occupancy_clear_for_wait` is shared with self-heal, so idle respects
  Wait time with flapping PIR sensors.
- `entities_still_on` excludes idle lights, or self-heal fights the idle
  branch every tick.
- `condition:`'s motion_on check ("is anything off?") also passes when
  `idle_entities` is non-empty - **not** `room_is_idle`, which is false
  the instant motion fires. Otherwise motion into an idle room did nothing
  until the next tick. `test_motion_into_an_already_lit_idle_room_brightens_it`
  asserts the transition, which pins which trigger did it.
- A template level with the phase value at 0 is the whole idle set, so it
  makes that lamp the room's only nightlight and `room_is_idle` true for
  everything (`test_a_template_level_alone_makes_that_lamp_the_only_nightlight`).
- A `null` level outranks an idle one.

**Self-heal** shares `tick`. Its checks are its `choose:` branch's own
`conditions:`, so a tick that doesn't qualify falls through to
`default:`. It stays exclusive of `default:`, since both work from lists
computed before `action:`. It requires occupancy clear for the full Wait
time, by a hand-written `now() - last_changed` template: the native
`for:` needs the recorder to prime it, unreliable after a restart.

**Brightness levels are absolute 0-255**, not multipliers, in
`brightness_template`, the idle inputs and the services'
`brightness_levels` alike (user's call: pinning a light at a level was
awkward otherwise). Rules, all in `grouping.target_brightness()`, which
the blueprint test harness also calls:

- A light without a level gets `brightness`; the service only requires
  `brightness` when some light lacks a level.
- **`0` is off**, for `brightness` and levels alike, as with
  `light.turn_on`. Anything else clamps to 1-255.
- **`0` and `null` differ**: `null`/`false` means "hands off, something
  else owns it", excluded from the turn-offs too. In Jinja `0 == false`,
  so use the identity form `level is none or level is sameas false`, never
  `in [none, false]`.

Other blueprint facts:

- **`variables:` render top to bottom and fail silently** (`x | length`
  on an undefined name is 0). The level chain sits near the top because
  the turn-off lists depend on it.
- Phase-keyed lookups use `.get(key, default)`: the schedule sensor can
  be `unknown`, and indexing would crash the tick.
- The schedule sensor's values are guarded on the one action step that
  needs them, not in `condition:`, since turn-offs need nothing from it.
- **`device_class: occupancy` doesn't mean presence.** Most sensors here
  are PIR: clear the moment motion stops, flapping by design. Wait time
  turns that into "the room is empty", and is sized for PIR everywhere.
  A template `binary_sensor` with `device_class: occupancy` in
  `room_target` is all a custom "occupied" signal needs.
- **`docs/reference/blueprint.md`'s anchors are tested**:
  `test_every_referenced_blueprint_anchor_exists` derives kramdown's
  slugs, after a restructure silently broke six deep links.

### Standing decisions - don't re-propose without new information

- **Target resolution as a service or a shared Jinja macro.** Conditions
  can't call services; a `custom_templates` macro needs a restart and a
  manual install step (lessons 4-5); a global Jinja function means
  monkey-patching HA. Deduplicating within `variables:` is what's done.
- **Condition/action selector inputs replacing the template inputs.** A
  blueprint input's default can't reference another input, brightness
  returns a value no selector can produce, and scene handoff would lose
  gap-fill.
- **`activating_triggers`** (Additional Triggers allowed to turn lights
  on). Built, shipped, reverted: "something that someone can just do via
  another automation".
- **Jitter, in any form.** It caused the relight bug above, while the
  tolerance check already keeps routine ticks nearly silent. The observed
  congestion was answered with zone ticks: deterministic spacing before
  the decision. If congestion shows up again, the shape is a rate limiter
  at dispatch, never a delay before the decision. (Zigbee's general
  answer is group addressing.)
- **`night_floor_kelvin` / `kelvin_rgb`** - see Curve math.
- **Virtual per-phase `light` entities** in place of the curve numbers.
  A phase has no off, so `turn_off` would lie, and `light.turn_off` with
  `entity_id: all` reaches it whatever its category; an always-on light
  also counts as on in every `states.light` template. The frontend gates
  light controls on the entity ID's domain prefix, so a bespoke domain
  gets none of them, and an empty light group is unavailable. Revisit only
  if HA adds a colour-picker card feature or features for non-light
  entities - which is why `flare-kelvin-feature.js`,
  `flare-brightness-feature.js` and `flare-value-slider.js` exist.

### Parked: scene handling in `apply_lighting`

Not built; recorded so it isn't re-derived.

1. **Straight port**: `apply_lighting` takes `scene_entity_id` /
   `scope_entities`, calls `compute_scene_coverage`, then `scene.turn_on`
   plus dispatch on the uncovered lights. Cost: the tick no longer stops
   at `condition:` while a scene owns the room. Accepted if picked up.
2. **Bigger**: feed a scene's stored values through the grouping
   pipeline, so a level could scale a scene. But a scene captures
   whichever colour mode was active (`xy`/`hs`/`color_temp`), may carry
   `effect` and other domains, and reading stored scenes is a less-trodden
   surface. Its own decision, not a prerequisite for 1.

### Two-step transition detection

Some bulbs (IKEA TRADFRI) need brightness and colour sent as two steps.
A light is routed that way if its device's `"<manufacturer> <model>"`
matches a case-insensitive glob in `CONF_TWO_STEP_MODELS` (the Zones
entry's options, read fresh per call), **or** it carries the
`no_combined_transition` label. `two_step.py` holds only the pure
matching. The option is seeded with the shipped defaults and holds the
whole list, so deleting a shipped pattern works; an empty field falls
back to the defaults.

Matching is automatic because a repair suggesting the label could only
nag, and live bulbs kept misbehaving while it went unapplied. The repair
was removed rather than kept beside it: it would only flag bulbs already
working. **Trade-off**: once someone saves the field they own it and miss
later shipped patterns, and a broad custom pattern immediately changes
real dispatch - keep patterns narrow.

### Blueprint version checking

`blueprint_version.py` is pure (the stamp constant and parsing),
`blueprint_check.py` the HA side, `repairs.py` the fix flows.

- **`BLUEPRINT_VERSION` is the integration's version**: the blueprint is
  versioned with FLARE (user's call, reversing a separate blueprint
  version as confusing). So every release, betas included, raises the
  outdated repair even when the blueprint didn't change. Accepted; don't
  reintroduce the decoupling.
- **Nobody bumps it.** `scripts/release.py` writes the release's version
  into the constant, the blueprint's description stamp and the manifest
  (only the manifest holds a placeholder in source). What source holds for
  the other two just has to agree.
- **The repair code knows nothing about dev builds** (user's call). On a
  dev install the constant and stamp agree, so it stays quiet even when
  the blueprint changed; update the blueprint there by hand.
- **The stamp lives in the blueprint's `description`**: the `blueprint:`
  block is a closed schema (`blueprint/schemas.py`), and description
  survives every import route and shows in the editor.
- **Two repairs, mutually exclusive**: `blueprint_not_installed` when no
  copy of ours exists, `outdated_blueprint` when an in-use copy is stale.
  `async_check` clears whichever it isn't raising.
- **The missing check doesn't ask whether anything uses it** (user's
  call): someone arriving from HACS should be told a blueprint exists.
  `IssueSeverity` has no INFO, so the wording says the blueprint is
  optional.
- **Ours is recognised by name only** ("FLARE"), and only copies an
  automation uses count as outdated: HA never removes an unused copy, and
  a repair about one nobody reads can't be silenced.
- **It installs to `flare/flare.yaml`** (`INSTALL_PATH`, user's call).
  The install uses `allow_override=False` (it's only for the no-blueprint
  case); the update writes the shipped file over each stale copy where it
  was found, with `allow_override=True`, which reloads the automations.
- **The check runs via `async_at_started`**, from the Zones entry only:
  during setup automations haven't loaded, so every blueprint looks
  unused.
- A blueprint that fails to load comes back from `async_get_blueprints()`
  as the exception, hence `isinstance`, not a `None` check.
- **Don't reintroduce an import badge** in the quickstart: it went
  through `my.home-assistant.io` to a `main` raw URL - lessons 9 and 10 in
  one link.
- `release.yml` checks a hand-pushed tag's constant and stamp equal the
  tag, since disagreeing ones would raise a repair Fix can never clear.

**The functional tests install the blueprint as a COPY**
(`tests/functional/conftest.py`), never a symlink: tests write blueprint
files, and a symlink once wrote junk blueprints into the repo.

### Releases

- **Automated, in three tiers** (set up 2026-09-21 at the user's
  request): `dev` is the churn branch; a push of `dev` to `main` cuts
  `vX.Y.Z-beta.N` (`cut-beta.yml`); a daily job promotes a version's
  newest beta to `vX.Y.Z` once it's 7 days old (`promote.yml`). `X.Y.Z`
  comes from `CHANGELOG.md`'s top `## [x.y.z]` heading. An open issue
  labelled `release-blocker` stops a promotion - that's the user's veto.
  Soak is per version (a later beta of the same version restarts its
  clock), and nothing at or below the highest stable is promoted.
- **Nothing is committed to a branch for a release.** The manifest's
  source version is `0.0.0-dev`; `scripts/release.py` builds each release
  as a commit on top of its source commit with the real version written
  in, tagged and on no branch (`Source:` in its message is how a
  promotion finds what to rebuild). A bot committing bumps to `main`
  would leave `dev` behind and need back-merges under linear history.
  GitHub shows "not on any branch" on release commits, and `main`'s
  changelog headings are never re-dated.
- **A tag pushed with `GITHUB_TOKEN` starts no other workflow**, so
  `release.yml` (which polices hand-pushed tags) never runs for automated
  releases. That's deliberate; don't "fix" it with a PAT.
- **`git push origin dev:main` must be a fast-forward**: `main` requires
  linear history.
- `tests/checks/test_versions.py` pins the placeholder and a parseable
  changelog heading. Full flow in CONTRIBUTING.md.

### Versioned docs

At the user's direction, every release's docs are kept and selectable:
`/flare/` is the latest release (so existing links land on it), each
release is also at `/flare/v/<version>/`, and the newest beta is at
`/flare/beta/`, never the default and overwritten until its release.
Until the first release, the beta is also the root.

- Pages serves one upload, so the built versions live on the `docs-site`
  branch; `scripts/docs_site.py` puts each new build in place and the
  whole branch is uploaded.
- `cut-beta.yml` and `promote.yml` call `docs.yml` after pushing their
  tag. A push to `main` starting it directly raced the tag and labelled
  the beta with the previous number.
- The version picker is added to pages when the site is assembled, not
  in the Jekyll source, so stored old versions get today's picker. It
  lives in `docs/_versions/`, which Jekyll skips.
- The trace report (`scripts/trace_viewer.py --export`) is rebuilt with
  each beta and published at `/flare/trace-report/`, front-matter-free
  and linked from nowhere - "you have to already know the URL" is the
  point, at the user's request.

### Getting a build onto the live instance

- **HACS has no dev channel, and the default branch isn't one.** HACS 2.x
  offers only GitHub releases in its version list (hacs/integration#4009);
  `hide_default_branch` and the default branch do nothing. Don't propose
  them again. What does work: `hacs/repository/download` accepts any
  `version`, including a 40-character commit SHA, and nothing reports it
  as an update afterwards.
- **While developing, install the working commit; never publish a
  version to test it** (user's direction). A beta is what testers are
  offered, not a scratch build.
  1. Push the branch - HACS downloads from GitHub.
  2. `ha_manage_hacs(action="download", repository_id="danrspencer/flare",
     version="<full commit SHA>")`. The full SHA: a short one is refused.
  3. Confirm with `ha_read_file` that the installed files match, then
     restart. (`www/` can't be read that way; check a `.py` file that
     changed with it.)
  4. If the blueprint changed, save
     `custom_components/flare/blueprints/flare.yaml` at that SHA with
     `ha_manage_blueprints(action="save", path="flare/flare.yaml",
     overwrite=True)` (lesson 10). The repair can't tell, since the stamps
     agree. If the branch changed how rooms tick, the old blueprint stops
     them ticking until this is done.
  - **A dev build doesn't stay put**: applying a HACS update installs the
    release over it, and the blueprint repair then appears. Re-install
    the SHA rather than pressing Fix.
  - To get back onto a release, download that tag.
- A merged change, or a release: HACS `update_information` then
  `download`, check the installed files, restart. The blueprint updates
  through the repair's Fix.

### The front end (`custom_components/flare/www/`)

**Served from the integration.** `async_setup` registers one static path
for the directory and `add_extra_js_url`s each module that registers
something; modules that register nothing (`flare-entities.js`,
`flare-section.js`, `flare-zone-section.js`, `flare-value-slider.js`,
`flare-clear-card.js`, `flare-activity-card.js`) are pulled in by the
imports of those that do.

- **The URL carries a fingerprint of the files**
  (`/flare_static/<hash>/`, `www_fingerprint()`), cached hard. The
  integration version wasn't enough, since a dev build is always
  `0.0.0-dev` and Safari kept serving a stale strategy. An unversioned
  URL with `cache_headers=False` still gets *heuristic* caching from
  `Last-Modified` - Safari rendered "Configuration error" until it lapsed.
- **It must be a path segment, not `?v=`**: the modules import each other
  relatively, and a relative import inherits the path but not a query, so
  `?v=` would load a module twice and the second `customElements.define`
  would throw. `tests/checks/test_static_imports.py` pins relative imports.

**The dashboard is Lovelace strategies**, regenerated on every load, so
an update is the whole migration and a new schedule or zone just appears.
"Take control" is the one-way escape hatch. (It replaced a docs-site YAML
generator whose layout changed five times in a session.)

- `custom:flare` (`ll-strategy-dashboard-flare`) is the dashboard: a view
  per schedule, then Zones. The views are `custom:flare-schedule` and
  `custom:flare-zone`, kept separate because a house has one zone per
  room against a few schedules.
- **Entities are found by device and role** (`flare-entities.js`:
  `flareDevices()` from `hass.entities`, using each entry's platform and
  translation key), never by building entity IDs, so renamed entities
  still show. The cards' `sensor:` option takes the short name
  (`sensor: home` for `sensor.home_flare`) or any entity ID.
- `flare-section.js` is a schedule's section and `flare-zone-section.js`
  the zone layout: plain config objects, no DOM.
- The sidebar icon `flare:logo` is registered on `window.customIcons` by
  `flare-icon.js`, a glyph generated from the logo by
  `brand/generate_icon.py`.

**The schedule view's sliders** (`flare-kelvin-feature.js`,
`flare-brightness-feature.js`, sharing `flare-value-slider.js`) are card
features rendering the frontend's own `ha-control-slider`, with a copy of
its `cardFeatureStyles` differing only in colour: the fill is the value's
colour. They exist because a tile's slider takes `--feature-color` from
the tile's `color`, which takes no template, and card-mod was rejected as
a third-party dependency. Depending on `ha-control-slider`, a frontend
internal, is an accepted risk; if it breaks, follow
`hui-numeric-input-card-feature.ts`. Card features register on
`window.customCardFeatures` (not `customCards`, nor the older
`customTileFeatures`). The kelvin feature imports `kelvinToRgb` from the
curve card, so a slider's colour and the chart agree by construction.

- **The drag handle can't be recoloured**: it's hardcoded white with no
  custom property or `part`. Injecting a rule into its shadow root
  shipped in 0.10.6 and was reverted (it coupled to an internal class and
  silently did nothing). Don't retry it without a supported hook.
- Tried and dropped, recorded in the file header: a warm-to-cool gradient
  track (looks like a colour picker), a hand-rolled range input (didn't
  match), a value-faded fill, and a white-to-transparent fill.
- Brightness borrows its colour from the same phase's Kelvin entity
  (`tint_from`), as HA's own light feature does with a bulb's colour,
  which is why colour temperature sits left of brightness. Without one it
  falls back to the stock slider's `--primary-color`. The unfilled track
  is the element's own `--disabled-color`.

**The chart is one filled path** (`curveFillSvg`, `simplifyPolyline`,
`roundedTopEdge`, covered by `tests/unit/dashboard/test_curve_chart.py`).
Only the geometry is simplified; the gradient keeps a stop per sample.
Corner easing uses a quadratic whose control point is the corner, so it
only cuts inward; **don't use an interpolating spline**, which would
overshoot and draw brightness the schedule never asks for.

**The Zones view** copies HA's Light dashboard (`light-view-strategy.ts`):
a section per floor, a heading per zone, and on wide screens Clear where
that has "All off", with the zone's Controlled and Overridden counts
beside it.

- The counts share one `grid` card: with the Activity sidebar taking one
  of `max_columns: 2`, a zone section is always 12 columns, and a tile's
  `min_columns` is 6, so loose tiles wrapped under Clear.
- **Each count is two tiles**, one shown at a time - Controlled blue,
  Overridden amber while above zero, grey at zero - because a tile's
  `color` takes no template. It's how a zone with overrides is spotted.
  Left for later, at the user's direction, to let the view settle: a list
  of overridden lights under the totals, tiles for the lights themselves,
  and a Clear per light.
- **Clear is `custom:flare-clear-card`**, drawn like the "All off"
  toggle-group (no card, a round icon, a label): a tile looked like one
  more count, and `toggle-group` is always a power icon with on/off
  counts. On narrow screens it's a button badge on the heading.
- A zone's area is its device's, else the area named after it; it takes
  the area's name unless two zones share the area.
- **The totals are an "All zones" row built like a zone's**, at the
  user's direction: the Zones entry's device-less total sensors
  (`sensor.flare_{controlled,overridden}_lights`, translation keys
  `all_controlled`/`all_overridden`, found by `flareTotals()`) as its
  tiles, and a Clear card pressing every zone's Clear button at once (the
  card takes a list). A markdown line of sums came first, and a stacked
  statistics graph before that was dropped as ugly.
- **The Activity sidebar is `custom:flare-activity-card`**, rendering the
  entries itself from the logbook's public `logbook/event_stream`
  subscription for the zones' devices, so it can colour them by kind (the
  tiles' blue/amber/grey) and filter by kind, at the user's request.
  HA's own pieces can't: the logbook card asks for a device target's
  entities only, never `deviceIds` (`hui-logbook-card.ts`), and the
  logbook server drops sensors with a unit from that list
  (`async_filter_entities`), so zone events never showed; and
  `ha-logbook-entry` colours a dot from the entry's category alone, with
  no per-entry colour its renderer passes through. An event's kind is the
  zone entity it's filed under (below). The card shows only entries with a
  message, which leaves out the Clear button's own state change.
  It relies only on the logbook's websocket feed rather than the internal
  `ha-logbook`, so its look doesn't follow HA's logbook automatically.
  **It should still look like HA's logbook** (user's call): visual drift
  is a bug to fix, not an accepted cost. When HA restyles its logbook
  (`ha-logbook-renderer.ts`, `ha-logbook-entry.ts`: date headers, row
  spacing, the dot, fonts), bring this card's styles back in line. Don't
  move it back onto `ha-logbook` without a way to keep the colours and
  filter.

**Zone events** (`flare_lights_controlled`, `flare_lights_released`,
`flare_light_overridden`) carry a zone entity as `entity_id` - the
Controlled count, the Overridden count, or the Clear button for a release
(`_zone_data`) - and the zone's `device_id`, with the lights in
`light`/`lights`, so they show on the zone's device page and in its
Activity, and the Activity card can tell the three apart. The logbook
matches events to entities only through `entity_id`, so they can't also
be on each light's timeline; the user chose the zone.

- The zone speaks for the room (user's call): "now controlling 7 lights",
  "cleared 7 lights" (the room going dark or Clear; not the blueprint's
  bookkeeping `claims_clear`). Only an override names a single light. A
  light becoming controlled again after an override is silent; an event
  for it was built and removed as churn.
- **`flare_lights_controlled` gathers for `CONTROLLED_GATHER_SECONDS`**,
  because a room's bulbs confirm one by one, and names only lights that
  are on (a turn-off claims lights too: "now controlling 0 lights"). A
  light back from unavailable or settling isn't counted as taken, or
  every room announced itself after a restart.
- A settling light isn't announced as overridden (see "Claims across
  restarts and reconnects").

### Other operational notes

- **The integration icon lives in the integration's folder**
  (`custom_components/flare/brand/`, HA 2026.3+), since
  `home-assistant/brands` no longer takes custom integrations; HA serves
  it when the folder exists. Root `brand/` is authoring tooling, and the
  served PNGs are re-rendered by hand. **HACS ignores it everywhere**
  ([hacs/integration#5171](https://github.com/hacs/integration/issues/5171)):
  it points at `brands.home-assistant.io`, which returns a grey
  placeholder for any domain, so nothing here can fix the HACS store card
  or Settings → Updates. The README, which HACS renders, carries the icon.
- **The docs site previews the card without HA**: `docs/playground.html`
  loads the real `flare-curve-card.js` with sliders for every value.
  Build the site and serve `docs/_preview/` (`.claude/launch.json`'s
  `docs-site`), which symlinks `flare` -> `_site` for the `/flare`
  baseurl. Read the rendered shadow DOM rather than trusting screenshots.

## Testing

`pip install pytest pytest-homeassistant-custom-component && pytest` from
the repo root (see CONTRIBUTING.md). Python 3.14, the floor of the HA
release pytest-homeassistant-custom-component pins. `pip install -e .`
doesn't work and isn't needed: nothing is distributed as a Python package.

Three layers: `tests/unit/` (no Home Assistant), `tests/checks/` (the repo
agreeing with itself) and `tests/functional/` (a real HA). Shared helpers
are in `tests/support/` and each functional directory's `harness.py`; a
test module never imports another.

- Component tests call `async_setup_entry` directly, or stub `frontend`
  (`stub_entry_setup`), rather than load the frontend package.
- `tests/functional/blueprint/` is the only layer that catches the
  blueprint's own wiring going wrong: it mocks FLARE's services and
  asserts on the calls; its classes mirror `docs/reference/blueprint.md`.
  `tests/functional/behaviour/` runs the real blueprint, schedule and
  services with only the bulbs faked, on a pinned day (sunset 18:00,
  clock from 19:00).
- `tests/functional/conftest.py` symlinks `custom_components/` into a
  throwaway config dir and copies the blueprint in.
- The dashboard's JavaScript runs under node (`tests/support/node.py`);
  `tests/support/registry.py` builds `hass.entities` for its fixtures.

**Practices worth keeping:**

- **Mutation-verify every behavioural change**: break the fix, confirm
  exactly the intended tests fail, restore. It has repeatedly caught tests
  passing for the wrong reason. Commit first - `git checkout <file>` to
  undo a mutation discards uncommitted work in that file.
- Timing tests use the `frozen_time` fixture
  (`freeze_time(..., real_asyncio=True)`) and its `.tick()`/`.move_to()`.
  **Never nest a `freeze_time`, and never freeze without
  `real_asyncio=True`**: plain freezing mocks `time.monotonic()`, the
  event loop's clock, and the loop hangs or fires timers out of order.
- `async_fire_time_changed` trips timers but doesn't advance `now()`; a
  template comparing `now() - last_changed` needs the frozen clock moved.
  It can also run a timer ~0.1s early, which is why `test_ticks.py`
  spaces zones 10s apart.
- Move time relative to `utcnow()`, never to an absolute
  `.replace(minute=N)`, which can land in the past.
- Two identical `hass.states.async_set` calls collapse into one
  `state_reported`, dropping the second's `context=`. Echo a slightly
  different value when a test needs a real change.
- **Waiting out real time doesn't work here**: under `frozen_time` a
  nonzero `await asyncio.sleep(...)` in the test hangs, and
  `async_block_till_done()` can return before a delayed call lands. A
  zero-length `asyncio.sleep(0)` is safe for letting a task start.
- A test whose timer outlives it fails on lingering timers; cancel it
  (remove the entity, or stop the scheduler) before the test ends.

# CLAUDE.md

Context for working on this repo. README.md is the user-facing pitch;
`docs/architecture/` is how the code works; this file is why it's shaped this
way and what not to do again. It records current decisions, not history -
git is the changelog. A fact belongs here once it has stayed true.

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
with worked examples), `reference/` (the contract only) and
`architecture/` (**Architecture**: the internals, with Mermaid diagrams,
for contributors and the curious; called that, not "How it works", so
casual readers don't click it - user's call). It describes the system as
it is, links to CLAUDE.md for the why, and changes with the code it
describes. Each of its pages opens with a banner saying nobody needs it to
use FLARE. **It may link out to the rest of the site and to code, but
nothing else on the site links in** (user's call);
`test_no_user_page_links_into_architecture` enforces it.
`jekyll-redirect-from` keeps old URLs working, so keep the
`redirect_from` lines. These are **site pages, not GitHub pages**: front
matter goes straight in the files, with no build-time generation step.

**Design rationale never goes on a user-facing site page** (Architecture
may say why a mechanism is shaped as it is). It has happened three
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

**In the blueprint (Jinja/YAML):** triggers, conditions, occupancy
(`occupied` and the native `occupancy.*`/`motion.*` triggers and
conditions) and the action structure. The reason is lesson 1: a
`condition:` cannot call a service, so anything a condition needs must be
a template or a native condition. These parts also get real value from
HA's trace UI.

- **Which entities are the room's is HA's rule, through
  `flare.resolve_target`** (`helpers/target.py`, as `light.turn_on
  area_id:` and a flare's membership use it). Templates can't apply it:
  they can see `is_hidden_entity` but not `entity_category`, and
  `device_entities()` misses child devices. So the action's first step
  calls the service, and everything built from the room's entities is an
  action-level `variables:` step after it. The one top-level
  `condition:` reads only inputs (Sensors From Areas, below). The `recovered` trigger keeps a plain Jinja expansion (it
  only makes a room catch up early, so close enough is fine - user's
  call).
- Scene coverage is the `compute_scene_coverage` service, called in
  `default:` only when a scene is chosen (`scene_entity_id` is required).
  Choosing the scene (`desired_scene`) and its scope (`scope_entities`)
  stay in the blueprint, built on `resolve_target`'s entities. Nothing
  before `default:` reads coverage. See "Parked: scene handling".
- Override protection is in Python, re-checked against live state on
  every call, never a one-shot trigger check (lesson 2).
- **The blueprint knows phase names in three inputs** - `rgb_phases`,
  the four scene pickers and the four exclude lists - a deliberate
  exception, because a Jinja template is poor UI for something this
  simple. In both templated cases the template wins and the per-phase
  pick fills in what it doesn't cover.

Blueprint input mechanics:

- Inputs are grouped with `sections:`; nesting doesn't change an input's
  name for `!input`, so regrouping isn't breaking. Only what's required is
  at the top level (Schedule, Lights & Occupancy); everything optional is
  collapsed, so input names carry no "(Optional)" (user's call). Sections
  hold what a room may want tweaked (**Sensors & Triggers**: Wait time,
  Lux Threshold, Additional Triggers; then Brightness, Idle Brightness, Scenes,
  Transitions); **Settings**, last, holds what most rooms never touch
  (Override Protection, Sensors From Areas, Prefer RGB During, Stored
  Traces).
  `docs/reference/blueprint.md` follows the same grouping.
- `homeassistant.min_version: 2026.4.0` is what `occupancy.*` needs.
- **Schedule is a device selector** (`integration: flare`,
  `model: Schedule`). The blueprint finds the schedule's
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
ordinary Home Assistant parts" section promises it. (The Settings entry's
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

The tree, the entries and where each entity sits are in
`docs/architecture/layout.md`. What has to stay true:

- **Grouped by concept, not by how something is exposed.** Grouping by
  exposure (entities / services) tangled, because the schedule and the
  claims are each exposed through both.
- The eight entity platform modules **cannot** move into a folder (HA
  imports `custom_components.flare.<platform>`).
- **Dependencies run one way**: `schedule/`, `tracking/` and `flares/`
  import only `const.py`; `services/` may use those and
  `flares/identity.py`; the root may use everything.
  `tests/checks/test_layering.py` enforces it. `services/__init__.py`
  holds no imports.
- **One definition each, shared rather than copied** (reachability, what a
  light shows, the classifier, which lights are flares, a target's
  entities, a schedule's values; listed in `docs/architecture/layout.md`).
  Copies drifted before each was pulled together - a light with no state
  was reachable to grouping and unavailable to override protection - and a
  check test fails on a new copy where one is practical.

**`strings.json` is the source and `translations/en.json` a copy**, which
is what HA shows for a custom integration. They had drifted;
`tests/checks/test_translations.py` keeps them identical. **Placeholders
must be plain `{name}`s**: hassfest parses each string with Python's
formatter and rejects ICU plurals, though HA's frontend would format them.
The same test applies hassfest's rule, so word a count so it needs no
plural form ("Flares added: {count}").

**Other languages** (`translations/de.json`, from stefanr09 in
danrspencer/flare#301) must have exactly strings.json's keys and
placeholders; the same test fails on a missing, stale or mistyped one, so
a changed English string needs its translations revisited too.

**The dashboard translates itself** (`www/flare-i18n.js`, see
`docs/architecture/frontend.md`): HA's translations only reach an
integration's backend strings. Phase names stay English as data (they
match the schedule sensor's states) and are translated only when shown.
Cards that build before `hass` arrives fill their text in once it does;
the contributor's first version rewrote the page's text every two seconds
instead - don't go back to that. Not translated: errors a card throws from
`setConfig` (no `hass` yet) and the card picker's descriptions.

### Services

Twelve, all tested. Field contracts are in `services.yaml` and
`docs/reference/services.md`; how they work is `docs/architecture/services.md`.

- `apply_lighting` takes `brightness`/`color_temp_kelvin`/`rgb_color` as
  **plain values**, not a sensor, so any source works; don't move the
  sensor read into the service.
- `turn_off` records `{"state": "off"}`, THEN calls `light.turn_off`, as
  one operation, with **no** override protection (a room emptying takes
  hand-set lights too). The order and that private encoding are why it
  exists; **don't split it back into two steps in a caller.**
- `resolve_target`, `export_schedule` and `import_schedule` are registered
  in `async_setup`, not by an entry: they need nothing an entry holds.
- `rgb_color` accepts an explicit `None`, since a caller templating it
  from a missing attribute renders a literal null.

### Override protection

Each tracked light carries two claims, `observed` (a write seen landing)
and `latest` (the most recent attempt). The model and why it needs two
are in `claims.py`'s docstring; the decision table is
`override_protection.classify()`; the user-facing contract is
`docs/reference/override-protection.md`. **Everything judges a light through
`classify_state()`** - `grouping.py`'s `externally_set()`, and through
`ClaimRegistry.status()` the sensors and `claims_check` - because they drifted apart
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
  the device, so `matching.shows` treats them as equal.
- **A bulb's advertised colour range isn't always honest**
  (`light.utility_spot_1` claims max 4000K and reports 5813K), so
  `matching.shows` accepts the raw target or the clamped one.
- **What a light shows is decided in one place, `tracking/matching.py`**:
  `shows()` (override matching, `_already_set`), `reported_kelvin()` and
  `shown()` (adoption, the override event's `live`). Its docstring is the
  rule set: Kelvin from `color_temp_kelvin`, else from a white's `xy_color`
  (within `MAX_WHITE_DUV` of the locus), never by RGB, since HA's
  Kelvin->RGB and xy->RGB conversions differ by ~13 in red at 6500K; RGB
  only against an RGB target; the target as asked or clamped to the
  advertised range. Separate copies had drifted (the bathroom spots read
  as overridden while showing 6575K for 6578K).
  `tests/checks/test_one_value_matcher.py` fails if anything else reads a
  light's colour or imports `homeassistant.util.color` (the curve's
  Kelvin->RGB for sending excepted).
- **The minimum change (`min_brightness_change` %, `min_color_temp_change`
  mireds) is only ever set by grouping** (`Tolerance`), never by
  `classify()`: it
  decides what's worth sending, and widening override matching by the
  same amount would let a hand-set light near the curve read as FLARE's.
  Colour is in mireds because a flat Kelvin gap is ~4x coarser at 6500K.
  Defaults 5/5, on the Settings entry's options; a call can override them.
- **`force` is the only bypass.**

**Claims are FLARE's; rooms only say when to let go** (2.0, replacing
zones). There's one claim per light, whichever caller wrote it, so two
automations driving a light never read each other's writes as overrides.
A caller tracks its writes by naming a **room**: `room_id` (the blueprint
passes `this.entity_id`) and `room_entities` (its picker's lights,
`resolved_entities`). No `room_id` means "write, track nothing", and such
a call doesn't read claims either: it's the opt-out (the blueprint's
**Override Protection** input). `claims_record` / `claims_override`
require a room; `claims_check` / `claims_clear` take none. A room is keyed
by its entity's registry id (`room_key()`), so renaming the automation
keeps it. A room's lights are the latest `room_entities`, plus what it
wrote and any light it still claims (`_join`), so every claim it made can
be released with it. Rooms are caller-supplied, never resolved: guessing
a zone from areas was removed at the user's direction (*"there's just too
much weird behaviour if it gets the wrong one"*), and a picker can split
an area across automations anyway.

The model was `owner_id` once (2026-08): per-caller *ownership*, which
made two automations in one room read each other as intruders, spawned
devices from arbitrary strings and kept claims in a hidden Store. The
room is the caller identifying itself without owning anything; don't let
it grow ownership back.

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
the two-step contexts are created up front, and `async_record` is a
`@callback`, like the registry's other writers, so it can't await. **"Seen landing" means a context match only.** Pinned by
`tests/functional/component/test_interrupted_writes.py`.
`flare.claims_record` is documented as call-before-your-write for the same
reason.

**A room releases its claims once none of its claimed lights is `on`**
(`_release_if_dark`, per room containing the light that changed).
Deleting them is the point: a light that then comes on unclaimed, by hand
or back from unavailable, is `untracked`, so FLARE grabs it and sets it to
the curve. Holding a dark room's lights at FLARE's off ("dark claims", so
a hand switch-on read as an override) was built and reverted at the
user's direction for that reason; keeping your own brightness in a dark
room is what a room's flare is for.
Anything not `on` counts as dark, unavailable included, or one dead
entity would block the release forever. Only claimed lights count, so a
lamp in the picker that something else runs (a TV backlight, a `null`
level) can't hold a room open. A light in two rooms is released when
either goes dark - accepted and documented, not detected. It fires only
on a transition from a real on/off state (see below).

**A mismatch is an override only once it has lasted** (`MISMATCH_GRACE`,
30s), at the user's direction. Until then the light is `mismatched`:
blocked like an override, but counted in neither sensor and not
announced. Each claim record carries `mismatch_since`, set when the light
first stops matching and cleared when it matches again or can't be
reached. `ClaimRegistry.note_mismatch` keeps it, from the state listener,
each write, and every status refresh by the claim events (which also
catches a restored claim's), so it lives with the claim, not in loose state. It's
persisted with the claims, so an override from before a restart is still
one. A new write starts afresh. `claims_override` sets it already expired,
since someone said so. Short-lived mismatches seen live, all now silent:
a bulb's stale first report after a reconnect (10/8130 on a bulb at
204/8105, corrected 0.4s later), FLARE's own write still landing on a bulb
whose previous write was never confirmed, and another automation
switching a room off light by light (the room goes dark and releases them
first). The claim events recheck once the grace has passed.

**A light already showing what `apply_lighting` would send is adopted**
(`ClaimRegistry.adopt`): no write goes to it, so if it's on and unclaimed
it gets an `observed` claim of its current context and values, and joins
the room. Otherwise a Clear in a lit room left most lights unclaimed, and a
hand change to one went unnoticed.

**Each room light has a status sensor** (`sensor.<light>_flare_status`),
at the user's direction, so tracked state is visible in HA's own UI
without storing it on anything per room. It's how FLARE's state is shown,
as the Store is where it's kept: it reads the registry and holds nothing.
The dashboard reads these, not the registry. It shows the raw status (so
`untracked` stays `untracked`, unlike the counts), outlives its claims so
its history carries on, and is keyed by the light's registry id so a
rename keeps it.

- **It sits on the light's own device** through `device_entry`, as HA's
  own helpers link to a source device. `DeviceInfo` with the device's
  identifiers doesn't: since HA 2026.9 identifiers are unique per config
  entry, so it registers a second device of FLARE's own.
- It follows its light's own state changes as well as the claims: an
  unclaimed light changes status without any claim changing.

**Known limitation, partly mitigated:** an `overridden` light is excluded
from every group, so it never gets a fresher claim, and on a ramping
curve the value match drifts further away. The room going dark clears it;
`claims_clear` and the Clear buttons cover a room that never fully does.

### Claims across restarts and reconnects

**The registry holds the claims and rooms, saved in a `Store`**
(`.storage/flare.claims`, `SAVE_DELAY` seconds after each change, and at
shutdown), loaded before the platforms. Without the rooms, nothing would
release a restored claim. They lived on a `RestoreEntity` claims sensor
until 2.0, at the user's direction moved out: where the data lives matters
less than how it's shown (the status sensors, counts, events and the
Settings entry's diagnostics), and an entity holding it broke FLARE when
disabled and lost up to 15 minutes in a crash. `owner_id`'s Store was
dropped for being hidden; the status sensors are what make this one not.

**The claim events aren't an entity** (`sensor.ClaimEvents`). There's no
poll: every change that moves a count reaches the registry's listener,
and the grace is the only timed change, with its own recheck. They seed
the statuses when they start, and a room restored dark is released and
stale claims pruned only after that, so the release is announced. The
wiring is in `docs/architecture/event-loop.md`.

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
  not release the room.
- **Nothing a light reports while HA is stopping counts**
  (`hass.is_stopping`). MQTT marks its lights unavailable as its
  connection closes in its stop listener, and the drop rule then deleted
  every claim just before the Store's final save, so overridden lights
  came back `untracked` and were taken to the curve (found in the live
  instance's history, where MQTT lights go unavailable seconds before
  every restart).
- **A room restored dark lets go of its claims**
  (`release_settled_dark_rooms`), checked once setup has loaded them and
  whenever a claimed light reports in from none/unavailable/unknown, once
  *every* claimed light reports on or off and none is on. Lights that went
  off while HA wasn't watching (switched off during a restart, FLARE's own
  turn-off racing a shutdown, a restore) never send an on -> off, so the
  room stayed claimed with every light `overridden` and motion ignored
  until Clear (seen live: 18 lights in three rooms after a restore). A
  claimed light that never reports holds it, as the rule above requires.

A restart is not an escape hatch for a light stuck `overridden`. Known
residuals, both ending when the room goes dark: a bulb that power-cycled
while HA was down, and a write that dropped just before a restart on a
light with no confirmed write. A crash loses the last `SAVE_DELAY`
seconds of claims, failing open.

**A light coming back online isn't written to until it has booted.**
Found live: a Hue bulb on a wall switch booted at its default, the
`recovered` trigger's write 26ms later never took, and it read
`overridden` every evening. The fix is upstream, the `recovered`
trigger's `for:` (5s), not override protection: a 30s "reconnect settle"
rule in `classify_state` that forgave a lost write was built and removed
for it. Still parked: the same loss when FLARE wrote *before* the
reconnect (needed three restarts in fifteen minutes, which ordinary use
doesn't).

**Testing restore needs a real setup.** The component harness forwards
platforms without the frontend, so they fail and the claim events never
start. `test_claim_persistence.py` sets the entry up through HA over
`stub_entry_setup`, preloading `hass_storage[STORAGE_KEY]`, and reads what
was saved back out of `hass_storage` after moving time past `SAVE_DELAY`.

### Three config entries

FLARE installs as **three** entries: *Schedules*, *Settings* (the
services, the claim registry, the area ticks and the options) and
*Flares*. HA's integration page renders one section per subentry with no
way to group them by type (`ha-config-entry-row.ts`); the entry is the
only level that can group them. Settings has no subentries since 2.0
removed zones; its entities (the totals and
`button.flare_clear`) sit on one "FLARE" service device
(`settings_device_info`), so their events can be filed on a device (see
"Claim events").

- **Entry titles have no "FLARE" prefix** (the page already says FLARE);
  docs write the path as **FLARE → Settings**. User's call.
- **The stored value can't follow the user-facing name**:
  `ENTRY_TYPE_SETTINGS` is `"tracking"`.
- **2.0's migration is minor version 2** (`async_migrate_entry`): it
  removes the old zone subentries (`SUBENTRY_TYPE_ZONE`, `"state"`), which
  takes their devices, entities and claims, and retitles a "Zones" entry
  "Settings". Dropping the claims fails open: FLARE takes every room back
  on its next update. Old automations' stored `zone` input is ignored
  (blueprint validation only checks for missing inputs), and a flare's
  stored `zone_input` is dropped on its next Reconfigure.
- **`async_setup_entry` treats anything that isn't Settings or Flares as
  Schedules**, and each platform module branches on
  `entry.data[CONF_ENTRY_TYPE]`, so a new entry type must branch before
  that fallthrough.

**One "Add Integration" sets FLARE up ready to use, rooms included** -
the goal, at the user's direction, is a painless first install. The flow
itself is drawn in `docs/architecture/setup.md`. Each entry can still be added
alone, so deleting one and adding it back works.

- **It opens straight on the schedules, always** (user's call). An
  opening "set up or **Skip setup**" menu that created the entries empty
  was dropped for it.
- **Room automations are the one skippable question** (`automations`
  menu, first setup only, after the schedules, skipped with no areas with
  lights): **Skip for now** (`schedules_only`) creates the entries and
  schedules and nothing else, for someone whose own automations already
  drive their lights, to move a room at a time with Set up area. At the
  user's direction, after feedback that setup did too much and confused
  people.

- **Schedules are a choice of shape, not a count** (user's call, after a
  number box and names that had to match the floors exactly felt fiddly):
  one called Home (always the default: one is enough for most homes,
  user's call), one per floor (offered with two or more floors, its label
  listing them, so it isn't translated), or Custom: a list of names,
  starting as just Home (not the floors; that's what per floor is for). The areas step's
  start-on-the-floor's-schedule rule then matches per floor exactly.
  Floor names that fail the name checks land on the names step.

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
up area, Add schedule, Add flare. The main flow is the only one
not tied to an entry, and area setup touches all three.

**Area setup** (`area_setup.py`), per area: an automation from the
blueprint. **Flares are a page of their own after it** (user's call,
replacing a per-run automation / + flare dropdown on the areas form): a
`flares` menu saying what a flare is, with **Skip**, then `flare_rooms`,
the rooms just set up in Add flare's all-ticked list, each flare named
after its area. Set up area can just be run again.

- **The automation is written to automations.yaml as HA's automation
  editor does** (`components/config/automation.py`), since there's no
  public API. If the reload doesn't produce the entities, configuration.yaml
  doesn't include the file, and the original text is restored byte for
  byte. An unreadable file is left alone with its own message. A
  successful write drops comments in the file, as the editor does.
- **Each automation gets the "FLARE" label** (created the first time, in
  amber), at the user's request, so they're easy to find and manage.
- **Not yet handled: a failure partway leaves what was created.** On
  first setup the entries exist before automations.yaml is written.
  Deliberately left for a decision of its own.
- **"Already set up" means an automation with the FLARE label sits in
  the area** (`areas_set_up`; setup puts its automations there), which
  only unticks the area; every area with lights is listed (user's call,
  after reading automations' targets proved unreliable). Re-running an
  area adds another automation and flare. An area "has lights" by HA's
  rule (`services/targets.target_entities`, as `resolve_target`), so an
  area holding only hidden or categorised lights isn't listed.
- **Each area is an optional dropdown of schedules named after it** (the
  dialog falls back to a field's name when it has no translation, the
  only way to label fields made at runtime), and an empty one isn't set
  up (user's call, over a "-- Don't set up --" choice). Its schedule is a
  suggested value, not a default, or a cleared area would be filled back
  in. It starts on the schedule named like the area's floor, else the
  first, or empty if the area is already set up. One field per area so it can't be set up
  wrong. They sit in a `data_entry_flow.section` per floor, lowest first
  (user's call: rooms organised by floor whatever the schedules), keyed
  by the floor's name, which the dialog shows as the heading when there's
  no translation; floorless areas come last under **Other areas**, or
  under **Areas** when no area has a floor (fixed keys, translated). The
  step's description, not a section's, explains the dropdowns, since the
  floors' sections can't carry translated text. Tried and dropped: radios (three rows per area), HA's area
  picker (closes after every pick), and a checkbox list per schedule
  (always expanded, and an area could be ticked under two schedules).
- **Flares are offered, not made** (user's call, from the same feedback),
  and the one exception to "nothing creates flares automatically": the
  user picks the rooms.

**The dashboard is offered, not created**: `custom:flare` is listed in
**Settings → Dashboards → Add dashboard** through the frontend's public
`window.customStrategies`. Creating it from setup was built and dropped
at the user's direction: HA keeps the dashboards collection private, and
the only way in was unwrapping a websocket handler. Don't bring it back.

- **It needs a page reload after first setup, sometimes two.** The
  frontend (2026.10) reads `add_extra_js_url` modules only from the page
  HTML at load, never from `frontend/subscribe_extra_js`, and HA's service
  worker serves the first reload stale on HTTPS or `localhost`. Nothing
  server-side can reload a page, so `dashboard_reload.py` links to one
  that bypasses both, and a beacon clears the repair (mechanics in
  `docs/architecture/frontend.md`). The beacon isn't under `/api/`, where HA's
  CORS check rejects the `Origin` a module import always sends, and it has
  no auth, since module scripts are fetched without credentials.

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
  (`flare.claims_override`, with the automation as the room, so the
  room going dark hands them back), then
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
  doesn't orphan it) and the NAME of the input holding its lights**, read
  live - `room_target` for our blueprint (`BLUEPRINT_LIGHTS_INPUT`, pinned
  by `tests/checks/test_flare_inputs.py`). A plain automation stores a
  target instead.
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
  (automations load after FLARE). The same HA rule as
  `flare.resolve_target`, so a flare's members are its room's lights;
  `test_a_flare_and_its_room_leave_out_the_same_hidden_and_categorised_lights`
  pins it.
- **A flare must never be one of a room's lights**, or the room's tick
  would send it the curve and it would pass that on as an override.
  Three layers: the blueprint rejects `integration_entities('flare')`,
  the services drop flare lights (`flares/identity.without_flares`), and a flare's own
  filter drops other flares (or it recurses forever). Blueprint tests need
  a real `MockEntityPlatform` entity for `integration_entities`
  (`add_flare_light`).
- **The light platform is only forwarded when the entry has flares**
  (`entry.runtime_data` says whether, for the unload); an empty entry has
  nothing to put on it. `test_a_flares_entry_with_no_flares_loads_no_light_platform_and_unloads`
  pins it.

### Schedules

Each schedule is a "sensor" subentry of the Schedules entry, with its own
device; its entities and how they become a phase and a colour are in
`docs/architecture/schedules.md`. `schedule_instances(entry)` is the one place
enumerating them. The phase override clears at the next natural boundary
(compared against the phase computed when it was set), not on a timer.

**Config lives in entity state, not `subentry.data`**: a subentry data
change reloads the whole entry. A missing entity falls back to the
default it will report moments later, so `phase_at()` never sees a gap.
**Entities are read by unique ID** (`ScheduleInstance.current_id()` and
its wrappers), never by the ID they were created with, so a user renaming
one doesn't silently fall back to defaults.

**Every FLARE entity's translation key is its role** (its unique ID's
suffix: `schedule`, `morning_time`, `night_kelvin`, `status`, `clear`
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

- **Each phase eases to the next over its own transition** (minutes,
  per phase and per brightness/Kelvin), ending at the boundary.
- **A Night earlier than Morning is after midnight** (`_night_clock`):
  it's tomorrow's boundary, and Evening runs through midnight to it.
  Boundaries are otherwise today's, so a 01:00 Night skipped Evening and
  started Night at sunset. Strictly earlier: Night equal to Morning keeps
  the out-of-order meaning (`phase_marks`). The card and the docs'
  `curve.js` mirror it, held by `test_js_parity.py`.
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
them). Use the explicit form (`condition: or`, `conditions: [...]`), not
the `or:` shorthand: the viewer's `resolveYamlPath()` recognises
shorthand as a single-key map, so an `alias` beside it would break path
resolution.

**`room_target`** is one entity/device/area/floor/label target doing
double duty: lights in it are controlled, and occupancy- and motion-class
`binary_sensor`s in it drive occupancy through HA's native `occupancy`
and `motion` triggers (each filters by its own device class, so there's
a detected and a cleared trigger for each, sharing the `motion_on` /
`motion_off` ids). `flare.resolve_target` resolves it once, into
`room_entities` (every domain); `resolved_entities` is its lights minus
flares. Scene scope is those entities plus every entity on each light's
device. Through an area, device, floor or label, a hidden or categorised
light isn't the room's; one named directly always is. The `recovered` trigger keeps its own
Jinja expansion, since a trigger template can't read `variables:` or
call a service.

**Sensors From Areas** (`use_area_sensors`) off keeps only sensors named in `room_target`'s
`entity_id`. The native triggers can't be narrowed (`!input` inserts a
whole input, and a trigger's `target:` takes no templates), so they still
fire for every sensor and the top-level `condition:` drops those from
sensors not named; `room_occupancy_entities` applies the same filter.
Named means the raw `entity_id` list, which needs no resolution.

`room_occupancy_entities` exists only to know whether the room has a
sensor at all: `occupancy.is_detected` over zero entities is vacuously
**false**, so a light-only room would otherwise always read empty.
It leaves out unavailable and unknown sensors, so a room whose only
sensor is dead counts as sensorless, not empty: only `on` is occupied,
so a dead sensor would otherwise read as clear forever and self-heal
would switch off every light turned on there.

**Triggers** are listed, with the action drawn as a flowchart, in
`docs/architecture/room-automation.md`. The decisions behind them:

- **Area ticks stop every room writing in the same second.** All rooms'
  `time_pattern`s fired within 0.2s of :00, and Zigbee route failures
  clustered in seconds 0-4 of each minute. `tracking/ticker.py` fires each
  area's tick a gap apart, in name order, for every area in the area
  registry (kept in step with it). The decision is still made fresh at
  trigger time, so this is not the removed jitter.
- **A room follows its first area's tick** (`tick_area`, a trigger
  variable: the first `area_id` in `room_target`, string or list). Trigger
  templates are *limited*, so they can read trigger variables but can't
  call `area_devices()` and friends - hence matching on `area_id` rather
  than looking up a device. `this` is available there too, but ticking per
  automation would need FLARE to know every automation, and a brand-new
  automation's `this` can be empty when its triggers attach; ticking areas
  just works (user's call). A picker naming no area (lights, devices, a
  floor, a label) gets a `time_pattern` with the same `tick` id instead,
  chosen by trigger `enabled:` templates on `tick_area`, so the two never
  both run.
- **The tick is a plain bus event, not an entity** (user's call): as an
  event entity it logged every minute in every Activity and history.
  Undescribed bus events never reach the logbook. Nothing then cancels the
  scheduler at shutdown, hence the explicit `EVENT_HOMEASSISTANT_STOP`
  listener (the tests fail on lingering timers without it). One recorder
  row per area per interval, accepted.
- **Override Protection** (`override_protection`, default on, at the
  user's request): the escape hatch for a room whose bulbs report
  something other than what they show. Off makes `room_id` none, which
  `apply_lighting`/`turn_off` take as "track nothing", and skips the
  `claims_clear` step.
- `tick` exists because the curve ramps within a phase while
  `phase_change` only fires at boundaries.
- `recovered` arms on "at least one of our lights is reachable". The
  inverse lets one dead light disable recovery for the room forever. A
  flaky bulb beside healthy ones waits for the tick. Its template **can't
  reference `trigger.*`** (only `trigger_variables` are in scope), or it
  never fires. Its `for:` gives a bulb powered up at the wall time to boot
  before it's sent anything; a trigger's hold isn't an action delay, since
  `variables:` render after it.

**There is no delay anywhere in `action:`, and there must not be.**
`variables:` render once, at trigger time, so anything after a delay acts
on a snapshot. A 0-15s jitter delay made a light switched off by hand
inside the window get relit by a run that had already decided the room
was in use. Override protection can't catch it: turning off the room's
last light rightly releases every claim, so the only thing saying no is
`allow_turn_on`, and a delay makes that stale. Pinned by
`test_nothing_delays_the_action_before_it_decides`.

**Nothing before the action decides on occupancy.** Occupancy's only jobs are
turning a room on (with `allow_turn_on`) and off; gating ticks on it
skipped lights that were already on.

**`allow_turn_on` = `manual_run or trigger.id == 'motion_on' or
occupied`, or `lux_dark` while someone is in the room. It must never gain
a new way to become true without the user explicitly asking for it in so
many words** - not implied, not inferred as reasonable. This is the
user's emphatic, standing position. `lux_dark` is the one the user asked
for (*"if the lux drops below the threshold and someone is there it
should come on"*): a room Lux Threshold kept dark has no other way to
light for someone sitting there, since the motion_on it blocked doesn't
fire again while the sensor stays on. "Someone there" is a sensor on or
within the Wait time, as for the room emptying. Note
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
- The motion_on stop ("is anything off?", an `if`/`stop` after the
  variables step, since it needs the room's lights) also lets the run
  through when `idle_entities` is non-empty - **not** `room_is_idle`, which is false
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
- **The Lux Threshold drops off lights from the call, not from `allow_turn_on`.**
  The `apply_lighting` step carries lights that are already on, so gating
  `allow_turn_on` would freeze a lit room. `lux_blocked_entities` is subtracted
  from `target_entities` and from `idle_entities` instead. While it's too
  bright a scene is activated only if every light it covers is already on, so
  a phase change still moves a lit scene on; `scene_active` isn't touched, so
  its lights stay the scene's, or the next tick would take an already-lit scene
  onto the curve. A manual run bypasses the check by definition. The `lux_dark`
  trigger expands the target in Jinja like `recovered`, as a wake-up only;
  the action re-checks `too_bright` and occupancy on the resolved room.
- **`device_class: occupancy` doesn't mean presence.** Most sensors here
  are PIR: clear the moment motion stops, flapping by design. Wait time
  turns that into "the room is empty", and is sized for PIR everywhere.
  A template `binary_sensor` with `device_class: occupancy` in
  `room_target` is all a custom "occupied" signal needs.
- **`docs/reference/blueprint.md`'s anchors are tested**:
  `test_every_referenced_blueprint_anchor_exists` derives kramdown's
  slugs, after a restructure silently broke six deep links.

### Standing decisions - don't re-propose without new information

- **Target resolution in Jinja, a shared macro or a template function.**
  Jinja can't see `entity_category`, so it can't match HA's rule; a
  `custom_templates` macro has the same blind spot and needs a restart
  and a manual install step (lessons 4-5); a global Jinja function means
  monkey-patching HA's private template environment. Hence
  `flare.resolve_target` in the action. The cost, accepted: a motion_on
  with nothing to do now starts a run (and, under `mode: restart`,
  cancels one in progress) before it stops, which a top-level
  `condition:` would drop first.
- **Condition/action selector inputs replacing the template inputs.** A
  blueprint input's default can't reference another input, brightness
  returns a value no selector can produce, and scene handoff would lose
  gap-fill.
- **`activating_triggers`** (Additional Triggers allowed to turn lights
  on). Built, shipped, reverted: "something that someone can just do via
  another automation".
- **Jitter, in any form.** It caused the relight bug above, while the
  tolerance check already keeps routine ticks nearly silent. The observed
  congestion was answered with area ticks: deterministic spacing before
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

### Parked: an empty room switching off lights someone switched on

Not built; parked at the user's direction, recorded so it isn't re-derived.

Once every sensor has been clear for the Wait time, the room switches off
all its lights (motion_off and self-heal, `flare.turn_off`, no claims
checked), hand-set ones included. With PIR, someone sitting still after
switching a lamp on by hand loses it, and nothing tells that apart from
having switched it on and left.

- **Who turned a light on isn't recorded today**: a dark room's lights
  have no claim, so a light switched on there reads `untracked`, the same
  as one FLARE has never had. Tracking it would need a record that
  survives the room going dark without making the light an override (see
  the dark claims note under Override protection).
- The user's direction if it's picked up: track who turned each light on
  (FLARE vs by hand) and act on that.
- Considered and not built: a second, longer wait for hand-set lights
  (the blueprint splitting the room's lit lights with `flare.claims_check`,
  self-heal taking the hand-set ones once the longer wait passes), the
  usual "manual override timeout". Turning off only FLARE's lights alone
  would leave a forgotten lamp in an empty room on forever.
  Presence (mmWave) sensors remove the cause, but that's hardware.

### Parked: scene handling in `apply_lighting`

Not built; recorded so it isn't re-derived.

1. **Folding activation in**: `apply_lighting` takes `scene_entity_id` /
   `scope_entities` and does the coverage, `scene.turn_on` and dispatch on
   the uncovered lights itself. The blueprint already gets coverage from
   the service, so this only moves `scene.turn_on`; it would need a way to
   skip re-activation on a tick (`scene_recheck_due`).
2. **Bigger**: feed a scene's stored values through the grouping
   pipeline, so a level could scale a scene. But a scene captures
   whichever colour mode was active (`xy`/`hs`/`color_temp`), may carry
   `effect` and other domains, and reading stored scenes is a less-trodden
   surface. Its own decision, not a prerequisite for 1.

### Two-step transition detection

Some bulbs (IKEA TRADFRI) need brightness and colour sent as two steps.
A light is routed that way if its device's `"<manufacturer> <model>"`
matches a case-insensitive glob in `CONF_TWO_STEP_MODELS` (the Settings
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
- **Nobody bumps it.** All three hold `0.0.0-dev` in source, and
  `scripts/release.py` writes the release's version into each release's
  zip (see Releases).
- **The repair code knows nothing about dev builds** (user's call). A dev
  blueprint's `0.0.0-dev` stamp never matches a release's constant, so the
  outdated repair shows on a house running dev files; update the blueprint
  there by hand and ignore it.
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
- **The check runs via `async_at_started`**, from the Settings entry only:
  during setup automations haven't loaded, so every blueprint looks
  unused.
- A blueprint that fails to load comes back from `async_get_blueprints()`
  as the exception, hence `isinstance`, not a `None` check.
- **Don't reintroduce an import badge** in the quickstart: it went
  through `my.home-assistant.io` to a `main` raw URL - lessons 9 and 10 in
  one link.

**The functional tests install the blueprint as a COPY**
(`tests/functional/conftest.py`), never a symlink: tests write blueprint
files, and a symlink once wrote junk blueprints into the repo.

### Releases

- **Automated, in three tiers** (set up 2026-09-21 at the user's
  request): `dev` is the churn branch; a push of `dev` to `main` cuts
  `vX.Y.Z-beta.N` (`cut-beta.yml`); a daily job promotes a version's
  newest beta to `vX.Y.Z` once it's 7 days old (`promote.yml`). `X.Y.Z`
  comes from `CHANGELOG.md`'s top `## [x.y.z]` heading; a change under
  `custom_components/` while that names a released version fails, on the
  pull request (`release.py check`) and in the beta job. An open issue
  labelled `release-blocker` stops a promotion - that's the user's veto.
  Soak is per version (a later beta of the same version restarts its
  clock), and nothing at or below the highest stable is promoted.
- **A push to `release/**` patches the current release, skipping the beta**
  (`patch-release.yml`, at the user's request): `release.py patch` builds vX.Y.(Z+1) only,
  from a commit descended from vX.Y.Z's source whose changelog names the patch. That
  changelog check, not the ancestry, is what keeps main's beta work out, since main descends
  from the source too. Fixes go in as pull requests into the branch, which `tests.yml` and
  `release-preview.yml` treat as patches (`--patch`) by their `release/*` base; merging one
  cuts the patch. Each branch runs its own copy of the workflows and script; a manual run
  using main's tooling against a branch was tried first and dropped as unconventional.
- **No version is ever committed; HACS installs a zip** (user's call,
  2026-10-29, replacing release commits built on the side). Source holds
  `0.0.0-dev` in the manifest, `BLUEPRINT_VERSION` and the blueprint's
  stamp. `scripts/release.py` tags the source commit (annotated, so the
  soak counts from the tag) and builds `flare.zip` from it with the
  version written into all three; the workflow attaches it, and
  `hacs.json`'s `zip_release` makes HACS install it. A beta and its
  release are one commit, tagged twice. Releases before the zip were a
  commit on top of their source, named by `Source:` in its message, which
  `source_of()` still reads.
- **HACS reads `hacs.json` at the version being installed**, so releases
  from before the zip still install from their files. Any version that
  isn't a release with a zip, a commit SHA included, fails to install
  (`download_zip_files` in HACS's `repositories/base.py`).
- **HACS's download count** is the current release's first asset's count,
  not a total, so it restarts with every beta.
- **A tag pushed with `GITHUB_TOKEN` starts no other workflow**, so
  `release.yml` (which packages hand-pushed tags) never runs for automated
  releases. That's deliberate; don't "fix" it with a PAT.
- **`git push origin dev:main` must be a fast-forward**: `main` requires
  linear history.
- **The integration needs HA 2026.10.0** (`hacs.json`'s `homeassistant`):
  earlier releases make every subentry's Add button ask which entry type
  first, a frontend bug that would read as ours, and the Activity card
  needs 2026.10's `ha-logbook-entry`. The blueprint's own floor stays at
  what it needs.
- `tests/checks/test_versions.py` pins the placeholders and a parseable
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
- **A release's docs follow `main` while its code does**: built from
  `main` whenever nothing under `custom_components/` has changed since
  the release's source (`release.py docs-source`), else from the tag,
  and republished by `cut-beta.yml` on such a push. Building them from
  the tag alone left a docs fix merged after the last beta out of the
  release until the next code change.
- The version picker is added to pages when the site is assembled, not
  in the Jekyll source, so stored old versions get today's picker. It
  lives in `docs/_versions/`, which Jekyll skips.
- The trace report (`scripts/trace_viewer.py --export`) is rebuilt with
  each beta and published at `/flare/trace-report/`, front-matter-free
  and linked from nowhere - "you have to already know the URL" is the
  point, at the user's request.

### Getting a build onto the live instance

- **HACS can't install unreleased code.** HACS 2.x offers only GitHub
  releases (hacs/integration#4009), `hide_default_branch` and the default
  branch do nothing, and with `zip_release` a commit SHA has no zip to
  fetch. Don't propose them again.
- **While developing, write the files over a release; never publish a
  version to test it** (user's direction). A beta is what testers are
  offered, not a scratch build. ha-mcp writes to `custom_components/flare`
  only once it's added as a custom write directory in ha-mcp's settings
  (the user's to do).
  1. Install the newest release through HACS, so every file is there,
     the brand PNGs included (`ha_write_file` writes text only).
  2. Write each file `git diff --name-only <that tag> -- custom_components/flare`
     names with `ha_write_file(overwrite=True)`; delete removed ones with
     `ha_delete_file`. Leave `manifest.json` and `blueprint_version.py`
     as the zip wrote them unless they really changed.
  3. Confirm with `ha_read_file`, then restart.
  4. If the blueprint changed, save it with
     `ha_manage_blueprints(action="save", path="flare/flare.yaml",
     overwrite=True)` (lesson 10). If the branch changed how rooms tick,
     the old blueprint stops them ticking until this is done. Its
     `0.0.0-dev` stamp raises the outdated repair; ignore it.
  - **A dev build doesn't stay put**: a HACS update installs the release
    over it. Write the files again rather than pressing Fix.
  - To get back onto a release, download that tag.
- A merged change, or a release: HACS `update_information` then
  `download`, check the installed files, restart. The blueprint updates
  through the repair's Fix.

### The front end (`custom_components/flare/www/`)

**Served from the integration** through one module, `flare-loader.js`,
which imports each module that registers something; the rest come in
through their imports (`test_every_module_that_registers_something_is_loaded`).
How it gets into the page, and what registers what, is in
`docs/architecture/frontend.md`.

- **The loader waits for `<home-assistant>` to be defined before
  importing anything.** HA's frontend (2026.10) installs a scoped custom
  element registry polyfill, replacing `window.customElements` and
  `window.HTMLElement`, while it loads integrations' modules in parallel.
  A module that won the race defined its elements in the browser's own
  registry, where HA never looks, so the dashboard was listed but timed
  out when picked ("Timeout waiting for strategy element"), at random.
  The page has `<home-assistant>` in its HTML before any script runs;
  outside HA (the docs playground loads the card directly) there's
  nothing to wait for.

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
- **Any other fingerprint redirects to the current one**
  (`dashboard_reload.OldFingerprintView`, a 302, never a cached 301). A page
  served before an update (the service worker's stale copy, the companion
  app) asks for the old one; a 404 there means no strategy registers at
  all. A redirect rather than serving the files there: a module's relative
  imports resolve against where it landed, so the page gets one version,
  cached hard.

**The dashboard is Lovelace strategies**, regenerated on every load, so
an update is the whole migration and a new schedule or room just appears.
"Take control" is the one-way escape hatch. (It replaced a docs-site YAML
generator whose layout changed five times in a session.)

- `custom:flare-zone` still answers, as `custom:flare-lights`, for
  dashboards someone took control of.
- **Entities are found by device and role** (`flare-entities.js`:
  `flareDevices()` from `hass.entities`, using each entry's platform and
  translation key), never by building entity IDs, so renamed entities
  still show. The cards' `sensor:` option takes the short name
  (`sensor: home` for `sensor.home_flare`) or any entity ID.
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

- **A slider's colour has 15% of `--primary-text-color` mixed in**
  (`color-mix`), so a near-white shows on a light card and the theme
  decides which way it moves. Measuring the card's background in JS and
  darkening to a contrast ratio shipped once and was replaced by it.

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

**The Overrides view** copies HA's Light dashboard (`light-view-strategy.ts`):
an "All lights" totals row (the counts and Clear all; a line naming the
overridden lights under it was dropped at the user's direction), then a
section per floor and a heading per area holding a room
light (any light whose status sensor names a room), with the area's lights
under it. Called "Overrides" (user's call, after "Rooms" and "Lights"); its
strategy type and files kept the name `lights`.

- **The totals' counts are two tiles each**, one shown at a time -
  Controlled blue, Overridden amber while above zero, grey at zero -
  because a tile's `color` takes no template. **Clear all is a third
  tile** (user's call: a bare round icon beside the counts looked odd),
  pressing `button.flare_clear` through `tap_action`. All three share one
  3-column `grid` card: with the Activity sidebar taking one of
  `max_columns: 2`, a section is always 12 columns, and a loose tile's
  `min_columns` is 6, so loose tiles wrapped.
- **An area is one `custom:flare-area-lights-card`**, worked out live in
  the browser from each light's area (`claimsByArea()`): there are no
  per-area entities, and per-room devices would repeat `owner_id`'s
  devices-from-arbitrary-strings problem. A small header carries the
  area's Controlled and Overridden counts (blue/amber dots, grey at zero)
  and Clear all (`flare.claims_clear` on its claimed lights, `claimedIn()`,
  not announced in Activity); it replaced a Clear card and two count cards
  per area, at the user's direction. Then each light (`areaLights()`),
  overridden and mismatched first: its status, what FLARE last asked for
  (`asked`), both from its status sensor, beside what it shows, and a Clear
  for that light. Its name opens the light's more-info. `off` (no claim,
  light off) is labelled Untracked like `untracked` (user's call); only the
  icon says it's off. The counts come
  from the same statuses as the list, so the two agree.
- **`custom:flare-clear-card`** (a round icon and a label, like the "All
  off" toggle-group, pressing `entity:` or a list of buttons) isn't used
  by the views any more; it's still loaded for dashboards someone took
  control of.
- **The Activity sidebar is `custom:flare-activity-card`**: it subscribes
  to the logbook's `logbook/event_stream` for FLARE's device itself,
  filters by kind, and renders each entry as HA's own `ha-logbook-entry`
  with `nodeColor` (2026.10+) set to the kind's colour (the tiles'
  blue/amber/grey), so rows look exactly like HA's logbook. Only the list
  around them - day headings and the scrolling box - is ours, copied from
  `ha-logbook-renderer`, which can't colour rows individually. Selecting a
  row (`logbook-entry-selected`) opens FLARE's device page. An event's
  kind is the entity it's filed under (below); entries without a
  message, i.e. the Clear button's own state change, are left out.
  - Why not HA's logbook card, as the Security dashboard uses: it asks for
    a device target's entities only, never `deviceIds`
    (`hui-logbook-card.ts`), and the logbook server drops sensors with a
    unit from that list (`async_filter_entities`), so the count sensors'
    events never showed; and it can't colour or filter rows. That's also
    why the Settings entities have a device at all.
  - `ha-logbook-entry` is a frontend internal, lazy-loaded (the card has
    `loadCardHelpers` create a logbook card first, which imports it). An
    accepted risk like `ha-control-slider`; its properties were the same
    from 2026.9 to dev apart from `nodeColor`, new in 2026.10. **It should
    look like HA's logbook** (user's call): if HA restyles
    `ha-logbook-renderer`'s day headings or container, follow them.

**Claim events** (listed in `docs/architecture/claims.md`) carry one of
FLARE's entities as `entity_id` (`_filed_under`) and FLARE's `device_id`,
so they show in FLARE's Activity and the Activity card can tell the three
apart. A logbook row shows the `entity_id`'s name ("Controlled lights"),
not the describer's, so each message starts with the room's name
("Kitchen Lighting is now controlling 7 lights"). The logbook matches
events to entities only through `entity_id`, so they can't also be on
each light's timeline.

- The room speaks for itself (user's call): "is now controlling 7
  lights", "cleared 7 lights" (the room going dark or Clear; not the blueprint's
  bookkeeping `claims_clear`). Only an override names a single light. A
  light becoming controlled again after an override is silent; an event
  for it was built and removed as churn.
- **`flare_lights_controlled` gathers for `CONTROLLED_GATHER_SECONDS`**,
  because a room's bulbs confirm one by one, and names only lights that
  are on (a turn-off claims lights too: "now controlling 0 lights"). A
  light back from unavailable or mismatched isn't counted as taken, or
  every room announced itself after a restart.
- A mismatched light isn't announced as overridden (see "Override
  protection").

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
- **The sandbox** (`mise run sandbox`, `scripts/sandbox.py`) is a real
  HA (`hacs.json`'s minimum unless `SANDBOX_HA_VERSION` says otherwise) on
  `SANDBOX_PORT` running this checkout's FLARE over a fake house
  (`sandbox/`), already onboarded. It's for trying setup and the UI as a
  new user would before touching the live instance, not a test layer.
  `--reset` gives a brand-new house. `mise run sandbox:hacs` is a second
  house (`.sandbox-hacs/`) with HACS and no FLARE, for installing from the
  store as a user does; it never links this checkout, since HACS would
  write through the link into it. `mise run sandbox:record` records the
  docs' walkthrough videos and the README's GIF (see CONTRIBUTING.md); the
  GIF is linked by raw `main` URL, since GitHub and HACS show a README's
  images but not video.
- **Use the sandbox by default** whenever a change can be checked there
  cheaply. Each bulb's **Power** switch and each room's **Wall switch**
  make bulbs drop out and come back booting at their default, for anything
  touching reconnects.

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
  spaces areas 10s apart.
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

# CLAUDE.md

Context for resuming work on this repo in a fresh session. See README.md
for the user-facing description; this file is about *how* to work on it
and *why* it's shaped the way it is. This file documents current
architecture and decisions, not a session-by-session change log - the
git history is the changelog; a fact only belongs here once it's stayed
true.

## Where this came from

This started as a single Home Assistant blueprint - still live, at
`blueprints/automation/danspencer/adaptive_lighting_unified.yaml` on
the actual HA instance - that grew ~150 lines of namespace-loop Jinja
for target resolution, reachability filtering, multiplier bucketing,
tolerance-based "already correct" checks, and manufacturer-based
two-step transition detection. It worked, but became unreadable and
hard to change safely. This repo is the migration of the genuinely
computational parts (not triggers/conditions) out of Jinja, while
keeping the blueprint native for the parts HA already does well.

That migration went through two different backends. The first attempt
moved the computation into pyscript - working, unit-tested Python, but
getting it to actually *load* inside pyscript cost an entire session
chasing dormant bugs that all looked identical from the outside
("nothing happens, no error") - see lesson 8 below. That experience is
why the computation now lives in
`custom_components/flare/` instead - a real Home
Assistant integration that registers its own services directly, with no
pyscript dependency and none of that machinery to go wrong. **pyscript
is entirely gone from this repo now** - lesson 8 is kept only in case
pyscript comes up again in some other project.

**This repo is now two pieces, and the dependency between them runs one
way** (see "The architectural split" below): the
`flare` HACS integration (curve math + grouping
logic, exposed as plain HA services anyone can call from their own
automation) and the `flare` blueprint
(triggers/conditions/target-resolution, built on top of those services).

Be precise about that asymmetry, because it is easy to describe wrongly
and the docs did for a while. The **integration** stands alone: the
services are documented and useful from any automation, and should be
written that way, not as if the blueprint is their only consumer. The
**blueprint** does not stand alone - it depends on the services
entirely and does nothing without them. What it is is a worked example:
an off-the-shelf automation wiring the services up the way most rooms
want them, which anyone can take, change, or rip apart to build
something different on the same services. "Loosely coupled" is the
wrong phrase for it, and "independently useful" is simply untrue of the
blueprint half.

This repo's blueprint is named `flare.yaml` (blueprint name "FLARE").
It was previously `adaptive_lighting.yaml`, deliberately not
`adaptive_lighting_unified`
- different file, different in-UI name, so it can be installed and
tested alongside the live `adaptive_lighting_unified.yaml` without
touching it, and rooms migrated over individually. Linking the two
blueprints to the same filename is exactly what caused the incident
in lesson 6 below - don't reintroduce that collision.

**Documentation layout: README.md, and then the site.** README.md is
the only Markdown left at the repo root, and it is the pitch - why this
project exists, why the day is divided into four named phases
(Morning/Day/Evening/Night) rather than a single continuous
sun-elevation curve the way most adaptive-lighting tools work - plus
links onward. Everything else lives in `docs/` and is published to
<https://danrspencer.github.io/flare/>: `installation.md` (quickstart),
the `playground.html` interactive curve, `dashboard.md`, then two
sections. `docs/guides/` ("Guides") is how to do more: `examples.md`
(automations using only ordinary HA actions, each run against a real
schedule before it went in), `templates.md` (the blueprint's template
inputs with worked examples), `scenes.md` and `custom-automations.md`.
`docs/reference/` ("Reference") is the technical docs: `blueprint.md`
(the inputs and how a room behaves - the contract only, worked examples
go in Guides), `schedules.md`, `zones.md` and `services.md`. The section
was "Power users" at `/advanced/`, renamed as exclusionary, and the
blueprint page lived at `/blueprint/`; `jekyll-redirect-from` keeps old
URLs working, so don't drop the `redirect_from` lines. Contributing
lives at the repo root as `CONTRIBUTING.md` (repo layout, tests, how to
build the site) - it is for people working on the code, who are already
on GitHub, so it is not a site page.

**The rules for writing docs, and the lexicon of terms, live in
`DOCUMENTATION.md`** - one home, so a style guide doesn't end up in
three places disagreeing. Read it before touching `docs/`. What belongs
here rather than there is the *history*: this has gone wrong three
times. `docs/dashboard.html` once grew to ~145 lines explaining
`--feature-color`, `cardFeatureStyles`, `ha-control-slider` internals,
`column_span` arithmetic and why card-mod was rejected. The homepage
carried the same class of thing. Most recently `docs/blueprint.md` had
grown to 300 lines of design rationale with its actual reference table
last, and naming an input ("Room") that does not exist in the UI. The
pattern each time is the same: a decision felt worth writing down, and
it went onto a site page instead of into a code comment or this file.

These pages are **site pages, not files meant to be read on GitHub** -
that distinction is load-bearing. An earlier arrangement kept
`docs/blueprint.md`/`docs/helpers.md` pristine for GitHub readers and
generated front-matter'd copies at build time, because GitHub renders a
front matter block as a metadata table. Once they became site-only, the
front matter went straight into the files and the whole generation step
(`docs/_build/prepare.py`, plus its link rewriting) was deleted. Don't
reintroduce it without reintroducing the reason.

The Morning-phase research citation
([He et al., 2023](https://pubmed.ncbi.nlm.nih.gov/36058557/), J Sleep
Res - twelve college students, 1.5h of morning light at 1000 lux/6500 K
vs regular office light at 300 lux/4000 K for one working week, sleep
efficiency 83.8% vs 80.4%) was verified via a live web search before
being added, not recalled from memory - worth re-verifying rather than
trusting as-is if it's ever revised, same standard any factual claim in
these docs should meet.

**It has already been described wrongly once**, which is why the numbers
are spelled out here: README.md and docs/index.md both called the
participants "office workers" (they were students who worked in a
university office) and omitted that n=12. Cite it as the small study it
is. Note also that its bright condition is **6500 K** - so FLARE's
DEFAULT_MORNING_KELVIN of 6667 already sits at the researched figure,
and there is no evidence here for going cooler than that.

## The architectural split (deliberate, not arbitrary)

**Stays in the blueprint (Jinja/YAML):**
- All triggers, conditions, target resolution (`resolved_entities`),
  occupancy detection (`occupied`, plus the native `occupancy.*`
  trigger/condition path - see "Current status" below), and the action
  *structure* (which service to call, on what target).
- Scene compatibility checking (`scene_active`/`scene_valid`) is a
  partial exception - the *logic* also exists as a standalone service
  (`compute_scene_coverage`), but the blueprint's own inline Jinja
  version is deliberately left in place rather than rewired to call it.
  Reason: it's read by a `condition:` block (see lesson 4 - conditions
  can't call services at all), and moving it server-side would mean
  losing that `condition:`-level suppression (the tick would still fire
  and call `apply_lighting`/`scene.turn_on` every time as an idempotent
  no-op instead of not running at all - functionally harmless, not
  behaviourally identical). See "Parked: scene handling in
  apply_lighting" below for the full design if this gets picked back up.
- Override protection lives in `grouping.py`/`override_protection.py`,
  not in a trigger. A one-shot trigger-level check can't provide a
  standing invariant (lesson 5); the real check re-evaluates against
  live state on every call. See "Override protection" under Current
  status.
- **The blueprint knows phase names in three places** - `rgb_phases`,
  the four per-phase scene pickers, and the four per-phase exclude
  lists. A deliberate exception to "the blueprint doesn't know phase
  names", chosen explicitly because editing a Jinja template in the HA
  UI is poor ergonomics for something this simple. Precedence in both
  templated cases: the *template* wins, the per-phase picker is the
  fallback for what it doesn't cover.
- Why any of this stays in Jinja at all: HA `condition:` blocks cannot
  call a service - only `action:` steps can - so anything
  condition:-gating must stay template-based. These pieces are also
  compact and get real value from HA's native trace UI
  (`ha_get_automation_traces`), used heavily to diagnose issues live.

Blueprint input mechanics worth knowing:

- Inputs are grouped with `sections:` (HA 2024.6.0+). Nesting an input
  in a section does **not** change its name for `!input` purposes.
- The blueprint declares `homeassistant.min_version: 2026.4.0` - what
  the `occupancy.*` triggers require, not `sections`' lower floor.
- **Schedule and Zone are both device selectors** (`integration: flare`,
  `model: Schedule` / `model: Zone`). The blueprint finds the schedule
  device's one `sensor` in `variables:`. A trigger can't do that lookup
  (trigger templates can't read the registry, and a `state` trigger only
  takes entity IDs), which is why each schedule has a Phase `event`
  entity: `phase_change` is `event.received` on the device. There is no
  "bring your own sensor": anyone wanting something
  different builds their own automation on the services.
- **Input renames are breaking.** A stored input simply stops matching
  any input the blueprint declares, so every already-migrated room
  automation needs the old key removed outright, not left blank, as
  part of deploying a rename.

**Lives in `custom_components/flare/` (a standalone
HACS integration - see Current status for the services):**
- Reachability filtering, brightness bucketing, the tolerance-based
  "already at target" check, override protection, and
  two-step-vs-combined / RGB-vs-colour-temp label routing
  (`grouping.py`). This was the genuinely gnarly part - nested namespace
  loops, nothing pytest-testable in Jinja, and a real correctness gap
  (exact-match comparisons that silently stopped skipping for any bulb
  with device-side rounding quirks).
- Day-phase brightness/Kelvin curve math (`curve.py`) - not because it
  was complicated, but because it's a small, reusable, independently
  useful piece of logic that belongs as a documented service.
- Scene-coverage gap filling (`scenes.py`) - explicitly generic;
  nothing about it is specific to lighting.

All services are deliberately written and documented as standalone
tools, useful to anyone building their own automation, not just to the
blueprint in this repo. Keep them that way.

**Everything is an entity or an action, so a default can be replaced
rather than configured.** Schedule settings are `time`/`number` entities,
FLARE's live state is sensors and events (phase, tick, counts, the
zone events), and everything it does is a service. That is the answer to most
"can it do X differently?" requests: an automation changing an entity, or
calling a service, needs no new option. Keep new behaviour in that shape -
an entity or a service before a config field - and the docs homepage's
"Made of ordinary Home Assistant parts" section is the user-facing promise
of it. (Zone options - tick interval and gap, minimum change, two-step
models - are the exception: entry-wide plumbing, not schedule settings.)

## Hard-won lessons (don't repeat these)

1. **Jinja macros can only return rendered text, never a native Python
   list.** `{% macro x() %}{{ some_list }}{% endmacro %}` returns a
   *string* that looks like a list. If a macro needs to hand back a
   real list to be used *within the same template*, round-trip through
   `to_json`/`from_json`. This is why an earlier attempt at a shared
   `custom_templates/*.jinja` macro for target resolution was abandoned
   in favour of duplicating that logic inline in the blueprint - not
   worth re-attempting without a strong reason.

2. **`custom_templates/*.jinja` files are scanned once at HA startup,
   not on a config/automation reload.** Adding a *new* file there and
   then reloading core config will NOT pick it up — it needs a full HA
   restart. This broke every automation sharing the blueprint in
   production for about a minute before being caught and reverted.

3. **Symlinks for deployment must be created on the HA host itself, not
   through a Samba/SMB mount from another machine.** A symlink's target
   is just a string; if it's written from macOS via a mounted share,
   the target needs to be a path meaningful to *Home Assistant's own
   filesystem* (e.g. `/config/...`), not the mounting machine's path.
   Simplest correct approach: clone this repo directly on the HA host
   and symlink from there.

4. **HA `condition:` blocks cannot call services.** This is *the*
   constraint that shaped the architectural split above — any value a
   `condition:` needs must be computed via template (or a native
   condition type - see the `occupancy.is_detected` note in "Current
   status"), not via a service call.

5. **A trigger firing once does not mean protection persists.** A
   one-shot trigger-level check (the blueprint's old `manual` trigger,
   context.user_id-based, since removed entirely - see the
   architectural-split note above) is not the same as a standing
   invariant later code respects - it only blocked the one automation
   run where it fired, not a later independent `phase_change` tick. Fixed
   properly in `grouping.py`'s `EntityLookup` (originally
   `manually_set()`, later renamed `externally_set()` when the
   underlying check moved from `context.user_id` to `context.id`
   equality - see "Current status"): instead of remembering that an
   override happened, it re-checks the entity's *current* state on
   every call - room-empty, light-off, and device-recovery release
   conditions all fall out for free from that. The one piece that
   *does* now need persisted state, contrary to this lesson's original
   framing, is knowing what to compare the current state against -
   `claims.py`'s in-memory record of what context.id this
   integration itself last wrote each entity with. The lesson still
   holds where it always mattered: a trigger's one-shot firing is not a
   substitute for a check performed fresh on every tick.

6. **A same-named blueprint can take out every room at once.** This
   repo's blueprint used to share a filename with the live, already-
   deployed `adaptive_lighting_unified.yaml`, which 15 room automations
   referenced by that exact path - symlinking a materially different
   blueprint over it broke every one of them at once. Fixed at the root
   by giving this repo's blueprint a different file name *and* a
   different in-blueprint `name:`, so the two install side by side with
   zero interaction. Related: when a Samba-mounted view of `/config`
   disagrees with itself during recovery (a file `ls` won't show but
   which still blocks writes - consistent with a symlink Samba isn't
   surfacing but is still enforcing), stop trying to fix it through that
   mount and go to the host directly.

7. **A symlink's target is only meaningful from the shell session that
   created it.** A working symlink (right path, right name) can still
   fail every read with an opaque error indistinguishable from a
   permissions/sandboxing problem - `dirname "$0"` + `pwd` inside a
   deploy script bakes in whatever path *that* shell session happens to
   see (e.g. `/root/config/...` from an SSH-session alias), which is
   meaningless to a different process reading the same symlink back
   later, even on "the same host". `scripts/link_into_ha.sh` copies the
   blueprint and pyscript-era files instead of symlinking them (see its
   `copy()` function) specifically to sidestep this, not because
   symlinks are fundamentally broken. The dashboard card is still
   symlinked; if it ever shows the same failure mode, this is why.

8. **pyscript-specific loading gotchas (pyscript is no longer part of
   this repo - kept only in case pyscript resurfaces elsewhere):** a
   folder-based app only autoloads from a file named exactly
   `__init__.py` (any other filename is silently skipped, no error at
   any log level); an app can't share its name with a module package it
   imports from (identical names send pyscript's import resolution into
   infinite recursion until Python's recursion limit raises
   `RecursionError`, not a normal import error); and a pyscript app
   needs an explicit entry (even empty) under `pyscript: apps:` in YAML
   config, or it's silently skipped at debug-log level only, invisible
   at the default WARNING level. All three present identically from the
   outside: "nothing happens, no error."

9. **A stray `.bak-<timestamp>` directory under `custom_components/`
   isn't inert - it can break the domain it's a backup of.** Home
   Assistant discovers custom integrations by scanning every directory
   under `custom_components/` for a `manifest.json` and reading its
   `domain` key, not by the directory's own name - a leftover backup
   directory with the same `domain:` in its manifest broke config-flow
   resolution with a bare, unhelpful `404 Invalid handler specified`
   until the stray directory was found (only via grepping
   `home-assistant.log` for the domain name) and removed, and even then
   the fix needed a *second* full restart to take effect - HA's
   flow-handler registry is built once at startup, so un-discovering a
   directory needs the same "restart to rescan" treatment as
   discovering a new one. Clean up `link_into_ha.sh`'s `.bak-*` backups
   promptly, especially under `custom_components/`.

10. **A wrong-but-similarly-shaped constructor argument or a missing
    `@callback` decorator can sit dormant through months of "working"
    code, because unit tests never exercise the real HA event loop.**
    Two real instances in this integration: `DataUpdateCoordinator.__init__`
    was passed `__name__` (a plain string) where a `logging.Logger` was
    expected - fine until the coordinator's own refresh cycle actually
    called `self.logger.isEnabledFor(...)`, which only happened once a
    real schedule instance existed to refresh. Separately, a state-change
    listener called `hass.async_create_task()` without `@callback` -
    fine until it was registered against live entities and actually
    invoked, then raised a thread-safety `RuntimeError` (a plain `def`
    with no `@callback` marker runs in the worker thread pool, where
    `async_create_task` isn't safe to call - confirm via
    `homeassistant/core.py`'s `get_hassjob_callable_job_type` before
    trusting a fix here). Neither could have been caught without a live
    HA event loop actually exercising the code path.

11. **`sun.sun`'s `next_setting` attribute is exactly that - *next* -
    not "today's sunset."** The moment today's sunset passes,
    `next_setting` points at tomorrow's, roughly 24h ahead. Comparing a
    boundary directly against it (`max(earliest, min(next_setting,
    latest))`) silently clamps to the *latest* bound the instant sunset
    passes, instead of holding today's actual sunset time - `curve.py`'s
    boundary computation projects the sunset's local time-of-day onto
    today instead of using the absolute timestamp directly.

12. **A branch-name `raw.githubusercontent.com` URL can serve a stale,
    cached copy for a few minutes after a push, even when the fetching
    tool reports success.** Re-importing a blueprint immediately after
    pushing can silently install the *previous* commit's content -
    `ha_import_blueprint`'s own "re-imported successfully" response is
    not proof of freshness; confirm with `ha_read_file` against what
    actually landed. A commit-SHA-pinned raw URL
    (`.../blob/<full-sha>/...`) is immune to this, since GitHub treats
    that URL as immutable and never serves it stale - use one when
    testing a just-pushed change against a live instance.

13. **`ha_import_blueprint` derives the installed path from the GitHub
    URL's *owner* and *file name*** (`<owner>/<file>`, `importer.py`),
    never the path a house already uses. So importing by URL lands at a
    second path beside the one in use (`overrides_existing: false` is
    the tell), the same class of collision as lesson 6. FLARE installs
    to `flare/flare.yaml`, which no URL import can produce; write to it
    with `ha_manage_blueprints(action="save", path=..., overwrite=True)`
    instead. An unused copy
    at an old path is harmless (not domain-scanned, unlike lesson 9's
    `.bak-*`); repoint `use_blueprint.path` rather than editing
    `blueprints/`, which is read-only through every file tool.

14. **A `target:` selector's `entity:` sub-key has a different schema
    from the plain (non-target) `entity:` selector - the multi-filter
    list goes directly under `entity:`, with no nested `filter:` key.**
    `selector: entity: filter: [...]` is correct for a standalone entity
    selector (`EntitySelectorConfig.filter`), but the identical shape
    under a `target:` selector (`selector: target: entity: filter: [...]`)
    fails blueprint import outright with `extra keys not allowed` -
    `TargetSelectorConfig.entity` (`homeassistant/helpers/selector.py`)
    *is* the list of filters itself:
    `selector: target: entity: [{domain: light}, {domain: binary_sensor,
    device_class: occupancy}]`. Confirmed against HA core source before
    fixing, not guessed from the error text alone - caught immediately
    by a live blueprint import failing, not by any local validation
    (plain `yaml.safe_load` has no opinion on selector schemas).

15. **In a `sections`-view dashboard, a card doesn't inherit its
    section's full width just because the section itself is
    full-width.** Each section is its own 12-column grid, and only
    some card types claim all 12 by default (`heading` cards do); a
    nested `type: grid` card and a custom card without a
    `getLayoutOptions()` implementation don't, and render at whatever
    their own natural size is - about a third of the section, in
    practice - even with `column_span` correctly maxed out on the
    section around them. Caught live: `column_span: 4` on both floor
    sections measured correctly via `getBoundingClientRect()` (1120px
    of 1184px available), yet the curve card and every nested tile
    grid inside them measured only 368px - the section was genuinely
    full-width, its content just wasn't using it. Fixed with
    `grid_options: {columns: full}` on each of those cards
    individually (not on the section) - confirmed via the same
    `getBoundingClientRect()` check, now 1120px across the board. This
    is a general `sections`-view behavior, not anything specific to
    this project's custom card - documented in
    `home-assistant-best-practices`'s dashboard-guide.md under "Card
    Sizing and Responsive Layout" once found, but not something a
    plain `column_span` fix on the section makes you suspect exists.

16. **A blueprint input with no `default:` is required, regardless of
    "(Optional)" in its own `name:`.** Adding four new entity-selector
    inputs (`morning_scene`/`day_scene`/`evening_scene`/`night_scene`)
    without a `default:` key broke every one of the 15 dependent room
    automations on the very next re-import - none of them set these new
    inputs (they're meant to be optional), so HA's blueprint
    substitution failed to generate any of them at all:
    `Failed to generate automation from blueprint: Missing input
    day_scene, evening_scene, morning_scene, night_scene`, confirmed via
    the live error log (`ha_get_logs(source="error_log")`), not just
    suspected. `ha_get_overview`'s `repair_count` going from 0 to 15 in
    one step was the first signal - all 15 `validation_failed_blueprint`
    repairs, all created within the same second. Every other optional
    input in this blueprint already had an explicit default (`""`,
    `"{{ {} }}"`, `[]`) - these four were the only ones missing it,
    added in the same change as several that did have one, which is
    presumably why it wasn't caught in review. Fixed with `default: null`
    on each; the downstream Jinja already treated an unset value
    correctly (falsy, falls through to a fallback branch) - only the
    blueprint schema itself was wrong. Restored live service by
    importing directly from the fix branch's own commit SHA rather than
    waiting for a PR merge - a pushed commit is immediately fetchable by
    SHA regardless of merge state, and this is a case where minimizing
    outage time mattered more than the normal branch-then-PR-then-merge
    sequencing.

## Current status

Everything below describes how the system works *now*. Per-change
history lives in git; this file only carries what stays true, plus the
decisions and constraints that aren't recoverable from the code.

### Code layout (`custom_components/flare/`)

Grouped by **concept**, not by how something is exposed, and that
distinction is the whole reason for the shape. The obvious grouping
(integration / services / entities / dashboard) tangles: the schedule
and the claims are each exposed through BOTH entities and services, so
`entities` and `services` imported each other in both directions
(`services` used `coordinator.CURVE_KEYS` and `curve`; `sensor`/`button`
used the claims and `override_protection`). Those are two concepts,
and they match the two config entries, Schedules and Zones.

- `schedule/` - what lights should look like: `curve.py`,
  `coordinator.py` (`ScheduleInstance`, `TIME_KEYS`, `CURVE_KEYS`).
- `zone/` - zones: who owns a light (`override_protection.py`,
  `claims.py`), the zone device itself (`instance.py`,
  `ZoneInstance`; it lived in `coordinator.py` next to
  `ScheduleInstance` until the split, one file holding two concepts),
  and when each zone ticks (`ticker.py`).
- `flares/` - lights over automations: reading an automation's inputs
  (`automation.py`), what counts as a bare turn-on (`bare.py`), and the
  flare itself (`instance.py`). The entity is the root `light.py`.
- `services/` - `handlers.py` (the nine services) and the planning
  behind them: `grouping.py`, `scenes.py`, `two_step.py`.
- package root - what Home Assistant dictates: `__init__`, `config_flow`,
  `repairs`, `logbook`, `const`, and the seven entity platform modules;
  plus `area_setup`, which needs zones, flares and the blueprint at once.
  Platform modules **cannot** move into a folder (HA imports
  `custom_components.flare.<platform>`), which is why "entities" is not a
  folder here. `services.yaml` must stay at the root too. `www/` is the
  dashboard.

**Dependencies run one way**: `schedule/`, `zone/` and `flares/` import
only `const.py`; `services/` may use `schedule/` and `zone/`; the root may
use everything.
`tests/checks/test_layering.py` enforces it from the source, so it cannot drift
silently. `services/__init__.py` holds no imports; the root imports
`.services.handlers` directly.

Logger names follow the module path (e.g.
`custom_components.flare.schedule.coordinator`). Everything, tests and
`brand/generate_icon.py` included, imports through the package.

### Services (`custom_components/flare/services/handlers.py`)

Nine, all tested, and all but `claims_override` confirmed working live. Full field contracts
in `docs/reference/integration.md` and `services.yaml` - not repeated here.

- `compute_lighting_groups` / `compute_curve` / `compute_scene_coverage`
  - pure planners, no side effects.
- `apply_lighting` - the only side-effecting one; wraps the same
  grouping logic and issues `light.turn_on`/`turn_off`. Takes
  `brightness`/`color_temp_kelvin`/`rgb_color` as **plain values**, not
  a sensor entity_id, so it stays usable with any source of values.
  Don't move the sensor read into the service: the blueprint picks the
  schedule, and voluptuous's required fields already fail hard on a
  missing value.
- `turn_off` - the turn-off counterpart of `apply_lighting`:
  records `{"state": "off"}`, THEN calls `light.turn_off`, as one
  operation. Takes no brightness/colour and does **no** override
  protection - it turns off exactly what it is given, since a room
  emptying is meant to take hand-set lights along too. It exists because
  the blueprint used to do this as a bare `light.turn_off` plus a
  `claims_record` step, hand-building `{"state": "off"}` - this
  integration's own private encoding of an off claim - in Jinja. Both the
  order and that encoding were the caller's to get right, and the order
  was wrong (see "Claims are recorded before the write"). **Don't split
  it back into two steps in a caller.**
- `claims_check` / `claims_record` / `claims_clear` / `claims_override`
  - override protection exposed standalone, for callers that want it
  without any curve/brightness logic. `claims_clear` is the manual
  escape hatch for a light stuck `overridden`; `claims_override` is its
  opposite, marking lights as someone else's (what flares use).

`rgb_color` on both `apply_lighting` and `compute_lighting_groups`
accepts an explicit `None`, not just an omitted key (`vol.Any(None,
...)`): a caller templating it from a sensor attribute that may be
missing renders a literal null rather than omitting the key.

### Override protection

Each tracked entity carries two claims - `confirmed` (a write an earlier
call observed landing) and `pending` (the most recent attempt). The full
model, and why two rather than one, lives in `claims.py`'s module
docstring; the decision table lives in `override_protection.classify()`;
the user-facing contract lives in `docs/reference/integration.md`. Three consumers
share that one table - `grouping.py`'s `externally_set()`, `sensor.py`'s
diagnostic status, and `claims_check` - deliberately, because they
previously drifted. They share its input side too: each passes a live
`State` and a claim record to `classify_state()`, which owns the
unavailable check and reads the attributes, so only how a status is
*used* differs between them. They had drifted there as well - `claims_check`
judged an unavailable light as off. `tests/checks/test_one_classifier_adapter.py`
fails if anything else calls `classify()` directly.

Facts worth knowing before touching it, each verified against HA core
rather than assumed:

- `context.id`, not `context.user_id`: every service call in one
  automation run shares that run's context (`helpers/script.py`), so
  user_id can't tell our write from another automation's.
- `Entity._context` expires 5 seconds after the service call that set it
  (`core.py`), so a device whose confirmation takes longer reports back
  under an unrelated context while echoing exactly what was asked for.
  That's why claims also record a `target` and `classify()` falls back
  to comparing values against *either* claim's target.
- Zigbee bulbs speak **mireds**, and HA's Kelvin↔mired conversions are
  both lossy `floor()`. Two Kelvin values flooring to the same mired are
  indistinguishable to the device, so `_color_temp_matches` treats them
  as equal on top of the plain tolerance.
- A bulb's advertised `min/max_color_temp_kelvin` is **not always
  honest** - `light.utility_spot_1` advertises max 4000 and reports
  5813. So `_already_set` accepts the raw target *or* the range-clamped
  one, never only the clamped one.
- **The minimum change (`min_brightness_change` %, `min_color_temp_change`
  mireds) lives only in `_already_set`**, never in `classify()`. It
  decides what's worth sending; widening override protection's value
  matching by the same amount would let a hand-set light near the curve
  read as ours. Brightness is a percentage floored at the tolerance so a
  dim target still tracks closely; colour is in mireds because a flat
  Kelvin gap is ~4x coarser at 6500K than at 2700K. Defaults (5 / 5) sit
  on the Zones entry's options; a call can override them.
- `force` is the only bypass. There is no caller-supplied owner: a
  light's claims belong to whatever zone the caller names, so any
  caller naming that zone writes through it.
- **Zone is caller-supplied, not resolved.** Every claims service
  (`apply_lighting`, `compute_lighting_groups`, `claims_check`,
  `claims_record`, `claims_clear`) takes `zone_device_id` - a real HA
  device, one per zone (`ZoneInstance.device_info`).
  `ClaimRegistry.resolve_zone_device()` turns that into a subentry_id.
  **Optional only on `apply_lighting`/`compute_lighting_groups`** -
  both do something useful (dispatch/plan lights) with no zone at
  all, so omitting it means "write, but track nothing" (no claim,
  nothing excluded as externally-set). **Required on `claims_check`,
  `claims_record`, `claims_clear`** - each exists only to read or write
  claims, so a call with nothing to name has nothing useful
  to do; the schema rejects a missing/null value outright (`vol.Required`,
  not `vol.Any(None, ...)`) rather than always silently answering
  "untracked" or recording nothing. A device_id that *is* given but
  isn't one of this entry's own zones raises
  `ServiceValidationError` on any of the five, rather than behaving
  like it was omitted. **Nothing resolves a zone implicitly** - not
  from areas, not from a light's device. A zone is just a name, and the
  blueprint's required **Zone** input (a device selector filtered to
  `integration: flare, model: Zone`) is passed straight through as
  `zone_device_id`. Guessing was removed at the user's direction:
  *"there's just too much weird behaviour if it gets the wrong one"*. A
  deleted zone makes the service reject the call, loudly.
- **Being switched off is an override.** `classify()` does *not*
  short-circuit on `not is_on`; an off light is judged against its
  claims like any other. A turn-off records `{"state": "off"}` as its
  target, which is what tells our own off from anyone else's once the
  context expires - without it a room turned off at bedtime classifies
  as `overridden` and can never be turned on again. That trap is the
  whole reason the recording exists, so don't drop it as redundant.
- **The blueprint's own turn-offs are `flare.turn_off` calls**,
  which record the `{"state": "off"}` claim themselves. A bare
  `light.turn_off` records nothing, so every light in the room would
  read as externally switched off each time the room empties, firing
  `flare_light_overridden` for each of them.
- **Claims are recorded before the write, never after.** `apply_lighting`
  and `turn_off` call `async_record` before dispatching anything.
  It used to run once the writes had been awaited, so a run that never
  got that far - one group's call raising inside the `asyncio.gather`,
  or the blueprint's `mode: restart` cancelling the service call while a
  two-step bulb slept between its steps - left lights that HAD changed
  with no claim explaining it, and the next tick classified them
  `overridden`. Silent: the light just stops following the curve.
  Reproduced against a real `Script` in `mode: restart`, which does
  cancel a running blocking service call (`helpers/script.py`'s
  `_async_run_long_action`; `async_call` has no `shield`). Safe because
  the two-claim model already tolerates an intent that never lands:
  `observed` is replaced only by a state a bulb was actually seen in, so
  a write that never arrives leaves the light matching its previous,
  confirmed claim. Consequences: the two-step contexts are created by
  `apply_lighting` and passed into `_two_step_turn_on` (ids must exist
  before either step is sent), and `async_record` has no awaits inside,
  so the planning decision and its record are one uninterrupted step.
  **"Seen" means a context match only** - promotion never compares
  values, so a bulb that echoes under a fresh context after HA's 5s
  expiry is never promoted. Pinned by
  `tests/functional/component/test_interrupted_writes.py`.
- **`flare.claims_record` is documented as call-BEFORE-your-write** for
  the same reason, for anyone composing their own automation.
- **A light claimed in two zones raises a persistent notification**
  (`flare_light_in_two_zones_<entity_id>`, from `ClaimRegistry.async_record`) -
  a notification, not a repair, at the user's direction. Recording into one zone never
  touches another's claim, so both keep one: each reads the other's
  writes as overrides, and the listener only ever consults the first
  zone it finds. Detected at write time rather than by reading
  automation configs, so it covers service callers too and needs no
  copy of the blueprint's target expansion. It's raised once per light
  per run (`_warned`), since the conflict re-records on every write and a
  dismissed warning shouldn't reappear a minute later; notifications don't
  survive a restart, so a fixed setup never leaves a stale one.
- **A zone releases every claim once none of its lights report `on`**
  (`ClaimRegistry._release_if_dark`). Anything not `on` counts as dark,
  unavailable included - requiring an explicit `off` would let one
  permanently unavailable entity veto the release forever, the same
  trap the blueprint's `recovered` trigger avoids. Note "the room" is
  the *zone*: an untracked light being on holds nothing open. It fires
  only on a transition that STARTS from a real on/off state - see
  "Claims survive a restart" below for why `unknown -> off` mustn't.

**Known limitation, partly mitigated.** Once `classify()` returns
`overridden`, `build_groups()` excludes the entity from every group, so
nothing ever records a fresher `latest` for it - and on a ramping curve
its recorded target only gets staler, so the value-rescue can't recover
it either. The zone-goes-dark release now clears this automatically
whenever the room empties, which covers the ordinary case; `claims_clear`
(and the Clear button) remains the escape hatch for a room that never
fully goes dark. The underlying rot is unchanged: an excluded entity
never gets a refreshed claim.

### Claims survive a restart

The claims sensor (`_ZoneClaimsSensor`) is a `RestoreEntity`: its
claims are its `extra_restore_state_data`, restored in
`async_added_to_hass` before it registers. One source of truth, on the
entity - which is what #99 wanted when it deleted the old `Store`.

**This was tried once and reverted, so the history matters.** Claims
were `Store`-persisted from 2026-08-14. A restart gives every entity a
fresh `context.id`, matching was context-only then, and so every restart
excluded all 57 tracked lights (#69). A startup resync patched that, then
raced (#70, which added a "recovery" re-baseline to the listener), and
#99 deleted persistence outright. What makes it safe now is #78's value
fallback (2026-08-22): a restored claim can't match on context, but a
light still showing what FLARE asked for matches on value and reads
`controlled`.

Two listener rules changed with it, both pinned in
`tests/functional/component/test_claim_persistence.py`:

- **No recovery re-baseline.** The listener used to replace `observed`
  with the live context whenever a light arrived in a real state from
  unavailable/unknown/nothing. A genuine dropout has its claim popped
  first, so that branch only ever fired on restarts and reloads - and
  with claims restored it would mark every override `controlled` moments
  after the restore. Deleted rather than gated: HA's `restored: True`
  placeholder attribute can't gate it, because MQTT lights reach `on`
  from their own untagged `unknown` (unavailable -> unknown -> on,
  confirmed live on `light.landing_pendant_1`).
- **`went_off` needs a real starting state.** Lights reconnect one at a
  time; if the first back is `off`, its siblings are still `unknown`,
  which `_release_if_dark` counts as dark, and the whole zone's restored
  claims would go. Only a real on/off -> off releases.

The setup-time prune in `__init__.py` runs before any claims sensor
exists, so the restore prunes for itself.

**A restart is no longer an escape hatch** for a light stuck `overridden`
(see the known limitation above) - the room going dark, or the Clear
button, are. Known residuals, both ending when the room goes dark: a bulb
that power-cycles while HA is down comes back at its default and reads
`overridden`; and a write that dropped just before a restart, on a light
with no confirmed write yet (its only `observed` is the target-less
first-write baseline), reads `overridden`. HA saves restore state every
15 minutes and at shutdown, so a crash loses up to 15 minutes of claims,
which fail open.

**A command lost as a light comes back online is resent, not an
override** (`classify_state`'s `reconnected_at`). Found live on
2026-10-04: the Study Pendant, a Hue bulb on a wall switch, booted at its
own 2702K default; the blueprint's `recovered` trigger wrote the evening
colour 26ms later, the bulb never acted on it, and the light read
`overridden` all evening - every evening. `classify()` judges live values
against the claims, never how the light got there. So `claims.py`'s
listener notes when any light comes back online (unavailable/unknown ->
on/off; not from no state, which is every light on a fresh start and in
every test) and forgets it once a FLARE write is seen landing (the light
reports under `latest`'s context). A light that would read `overridden`
is `untracked` instead while all three hold: it came back online, its
state was last updated within `RECONNECT_SETTLE` (30s) of that, and
FLARE's latest write was recorded after it came back. The last is what
keeps a real override real: a light someone changed before it dropped
out (a restart, a blip) has its last FLARE write from before, and stays
theirs - `test_reconnecting_after_a_restart_does_not_take_the_light_back`
is the guard, and the "recovery re-baseline" deleted in #70/#99 is the
thing not to rebuild. Note `latest` can't stand in for "landed": it's
promoted to `observed` only at the next write, so between writes it
always looks unconfirmed.

Still parked: the same loss when FLARE wrote *before* the reconnect
(`light.dining_room_7` on 2026-10-04: a write at 15:47, a restart, back
as `off` at 15:50). That needed three restarts in fifteen minutes, which
ordinary use doesn't do.

**Testing it needs a real entity add.** The other harnesses attach the
claims sensor with a capturing `async_add_entities`, so
`async_added_to_hass` never runs and nothing is ever saved or restored.
`test_claim_persistence.py` adds it through the plugin's
`MockEntityPlatform` and seeds `mock_restore_cache_with_extra_data`; the
save side goes through `async_mock_restore_state_shutdown_restart`, which
also proves a claim survives HA's JSON encoder.

### Three config entries

The integration installs as **three** entries, not one: *Schedules*
(day-phase/curve sensors), *Zones* (the services, the claim registry,
the zone scheduler, and the zones) and *Flares* (light facades over
automations - see "Flares" below).

**Entry titles carry no "FLARE" prefix**, at the user's direction: the
integration page already says FLARE above them, so "FLARE Zones" read as
silly. Docs write the path as **FLARE → Zones**. Entries still titled
the old defaults are renamed in `async_setup_entry`
(`LEGACY_ENTRY_TITLES`); a title the user changed is left alone.

**User-facing names: "Zones" and "zone"**, the entry named after
what it holds, and the code says zone too. The stored values can't
follow: `ENTRY_TYPE_ZONES` is `"tracking"` in each entry's data and
`SUBENTRY_TYPE_ZONE` is `"state"`, because HA has no way to retype a
subentry and recreating zones would give them new device ids. Schedules
and Zones both use the sensor platform; each platform module branches on
`entry.data[CONF_ENTRY_TYPE]`. **`async_setup_entry` treats anything
that isn't Zones or Flares as Schedules**, so a new entry type must
branch before that fallthrough.

Why: HA's integration page renders **one section per subentry** with no
hook to group them by type (`subEntries.map(...)` in
`ha-config-entry-row.ts`), so a single entry flattened schedules and
zones into one long list of peers - 19 of them on this house. The entry
is the only level at which the distinction can be expressed. Flares got
their own entry for the same reason rather than being a second subentry
type on Zones.

The services live with **zones**, not schedules: every one of them is
about which lights are being driven and by whom, and they need the claim
registry that entry owns.

**One "Add Integration" sets FLARE up ready to use**, rooms included -
the goal, at the user's direction, is a painless first install. Separate
entries are a grouping decision, never an argument for several trips
through the flow. The main flow asks how many schedules and their names,
then which areas to set up (`async_step_areas`), creates each missing
entry through `SOURCE_IMPORT`, and hands the areas to
`area_setup.async_set_up_areas`. It ends on an abort carrying a summary.
Each entry is still creatable alone, so deleting one and adding it back
works. An install from before
Flares existed gets the entry from `async_setup`
(`_ensure_flares_entry`), only when another FLARE entry already exists,
so a fresh install never sprouts entries unasked.

**Once every entry exists, the main flow is "Set up area".** The
integration page's top row is the main flow's button (labelled by
`config.initiate_flow.user`) followed by one Add button per subentry type
across all entries (`ha-config-integration-page.ts`), so the row reads
Set up area, Add schedule, Add zone, Add flare. A subentry type of its
own would have given the button too, but the main flow is the only one
that isn't tied to an entry, and area setup touches all three.

**Area setup** (`area_setup.py`), per area: a zone (reused if one has the
area's name), an automation from the blueprint, and a flare named after
the area. The form's **For each area, set up** field picks zone / zone +
automation / all three for the whole run, not per area: per area it would
sit beside each area's schedule dropdown, and Set up area can simply be
run again for the odd ones out. Things worth knowing:

- **The automation is written to automations.yaml the way HA's
  automation editor does** (`components/config/automation.py` +
  `view.py`): load, append, dump, `write_utf8_file_atomic`, reload. There
  is no public API. Each is validated with `async_validate_config_item`
  before anything is written. If the reload doesn't produce the
  entities, configuration.yaml doesn't include the file, and the
  original text is restored byte for byte. A successful write drops any
  comments in the file, exactly as the editor does.
- **The zone's device is created by `area_setup`, not by the entry's
  reload**, because the automation needs its id now; the reload finds it
  by its identifiers. Nothing waits for that reload: the tick trigger
  matches `flare_tick` on the device id alone, so the automation works
  before the zone's entities exist.
- **"Already set up" means a zone with the area's name exists**, and it
  only unticks the area; every area with lights is always listed. At the
  user's direction, after reading automations' Lights & Occupancy proved
  unreliable: it only saw areas named by `area_id`, so rooms targeted by
  entity (this house's Bedroom Hall) looked unset. Re-running an area
  reuses its zone but adds another automation and flare.
- **With several schedules, each area is a field named after it**: the
  dialog falls back to a field's name when it has no translation
  (`renderShowFormStepFieldLabel`), which is the only way to label
  fields made at runtime.
- **The flare is part of the default set-up**, at the user's direction.
  That is the one exception to "nothing creates flares automatically"
  below: the user is choosing to set the area up, not updating.

**The dashboard is offered, not created.** `custom:flare`
(`ll-strategy-dashboard-flare`, a view per schedule plus Zones) is listed
in **Settings → Dashboards → Add dashboard** through the frontend's public
`window.customStrategies` hook; nothing opens the dialog itself. Creating
it from setup was built and dropped at the user's direction: HA keeps the
dashboards collection private, and the only way in was unwrapping the
`lovelace/dashboards/create` websocket handler to its bound method. Don't
bring that back. The sidebar icon `flare:logo` is registered on
`window.customIcons` by `www/flare-icon.js`, a glyph generated from the
logo's bars by `brand/generate_icon.py`.

**The flow ends on an abort, never on an entry,** because of HA's
"integration added" dialog (`step-flow-create-entry.ts`). It shows a
device-rename + area-picker form for every device on the entry the flow
completes on, with no way to suppress it. Both entries now have devices
from the start, so completing on either would put the schedule or every
zone through that form. An abort has no entry, so no dialog; HA's own
`reconfigure_successful` is the same pattern.

### Flares

A flare (`light.<slug>_flare`, `light.py` + `flares/`) is a light over an
automation, so voice assistants, HomeKit and dashboards can switch a room
without bypassing it. Built because a hand "on" from Siri/Alexa reads as
an override and leaves the room at whatever the bulbs restored to.

- **A bare turn-on is `automation.trigger`.** How a room comes on is the
  automation's decision (allow_turn_on, templates, idle levels, scenes),
  and a manual run already passes `allow_turn_on` and `force`, so it
  also reclaims overridden lights: "on" again hands the room back.
  `allow_turn_on` is untouched. "Bare" is no keys but `transition`
  (`flares/bare.py`); note HA strips `transition` before the entity
  sees it unless the light supports it, which is why the behaviour test
  needs `supports_transition` bulbs.
- **On with values, and off, mark the lights overridden first**
  (`flare.claims_override`, in the zone named by the zone input), then
  forward as `LightGroup` does. Without the mark, a light with no claim
  - every light, once a room goes dark and the zone releases them - is
  "untracked", which apply_lighting treats as free: the run the change
  itself triggers (an Additional Trigger on a room light, or a tick)
  took it over and dimmed Siri's "100%" back to the curve, live. The
  override claim is an `observed` under a fresh context with no target,
  so it never matches by context or value, on or off; the room's forced
  manual run (a bare "on") takes it back as usual.
- **Off is a plain `light.turn_off`**, never `flare.turn_off`. A
  flare's off is the user's, so it must read as an override.
  `flare.turn_off` claims the off as FLARE's, and that shipped once as
  the default: a run landing while the room was half-off (an Additional
  Trigger on one of the room's own lights, fired by the first bulb
  reporting off) relit the off lights instantly. Pinned by
  `test_a_room_turned_off_from_its_flare_stays_off_when_a_light_change_runs_the_automation`,
  which needs `reports_off_late` bulbs to reproduce the half-off moment.
- **The zone input is for `claims_override` only.** It was removed with
  the turn-off setting and brought back for the override; without one a
  flare can't protect a light FLARE wasn't already driving.
- **A flare stores the automation and the NAME of the input holding its
  lights** (and of the one holding its zone), read live - not a light
  list. For our blueprint that's `room_target`/`zone`
  (`BLUEPRINT_*_INPUT`, pinned
  by `tests/checks/test_flare_inputs.py`). A plain automation (no
  inputs) stores a target instead. The automation is stored as its
  entity-registry id so a rename doesn't orphan it.
- **The inputs come from the automation entity's private
  `_blueprint_inputs`** - `raw_config` is the substituted config, so
  it's the only place they survive. Accepted risk, kept to
  `flares/automation.py:blueprint_inputs`; the behaviour tests break if
  HA changes its shape.
- **Only automations from our blueprint are listed** in Add Flare - not
  every automation calling a FLARE service, at the user's direction.
  Any other automation goes through the custom path, which offers only
  inputs that can hold lights (a light-filtered entity selector, a
  target, area/floor/label, or a device selector not limited to FLARE's
  own Schedule/Zone devices).
- **Room flares are added in bulk**: the blueprint step lists every
  room automation without a flare, all ticked, and adds one per pick
  with `async_add_subentry` (named after the automation, in its area),
  ending on an abort. One flare at a time was a pain across a house.
  Each add fires the update listener, so `_async_reload_entry` coalesces
  listeners queued together into one reload (yield once, then clear the
  mark before reloading so a later change still gets its own).
- **Every flare's Reconfigure shows the same fields** - the automation
  (in the description, since it can't change) and its lights/zone
  inputs or target - however it was added. Hiding a room flare's
  inputs made the two paths look like different kinds of thing.
- **Nothing creates flares automatically**, except setting an area up
  (see "Area setup" above). A HomeKit Bridge including the `light`
  domain, or Alexa/Google with expose-new-entities on, would put every
  room in the Home app after an update.
- **The flare's device is placed in the automation's area once, at
  creation** (`_place_in_area`, gated on the device not existing yet),
  never again, so a user moving it isn't undone. Not
  `DeviceInfo.suggested_area`, which is deprecated and takes a name.
- **Membership tracking is `async_track_target_selector_state_change_event`**,
  replacing GroupEntity's fixed list; it re-resolves on registry
  changes. It skips hidden and entity-category lights (HA's primary-
  entity rule), which differs from the blueprint's `area_entities`. It
  retracks on `automation_reloaded`, on automation registry changes, and
  once HA has started (automations load after FLARE).
- **A flare must never be one of a room's lights.** In its room's area
  the blueprint would send it the curve and it would forward that to
  every light as an override, every tick. Three layers: the blueprint's
  `resolved_entities` and `recovered` reject
  `integration_entities('flare')`; the services drop flare-platform
  lights (`_without_flares`); and a flare's own filter drops other
  flares (without it, a flare containing itself recurses forever).
  `integration_entities` reads live entity *sources*, not the registry,
  so blueprint tests need a real `MockEntityPlatform` entity
  (`add_flare_light`).
- **The light platform is only forwarded when the entry has flares**, so
  an empty Flares entry doesn't set up `light` early (which broke every
  behaviour test registering its fake bulbs afterwards).

### Multi-sensor schedule architecture

The schedules entry registers no services and carries no schedule of its
own; each schedule is a subentry.

**That constraint is narrower than it was once written up here**, and
the overstated version caused a wrong call once - re-verified against
home-assistant/frontend rather than recalled:

- The dialog is gated on the flow's own `showDevices`.
  `show-dialog-options-flow.ts` sets it **false**, so an options flow
  never renders it however many devices exist. The main config flow and
  `config_subentries_flow` set it true.
- `dialog-data-entry-flow.ts` then filters `hass.devices` by
  `device.config_entries.includes(entry_id)`, with `entry_id` taken from
  the flow *result* - so it is the completing flow's own entry, not any
  device anywhere.

Net: only the **main config flow, at entry creation** is affected, which
is what ending setup on an abort avoids. Devices created later, by a
subentry flow, are fine.

Every schedule is a named "sensor" subentry (Settings → Devices &
Services → Add Sensor). `schedule_instances(entry)` in `coordinator.py`
is the single place enumerating them; every other module iterates its
output. Each subentry gets its own device, and every entity uses
`has_entity_name=True`, so renaming the device renames every entity's
displayed name for free.

Per sensor:

- `sensor.<slug>_flare` - state is the phase name;
  `brightness`/`color_temp`/`rgb_color`, today's boundary timestamps,
  and `attributes.points` (289 samples, what the dashboard card reads)
  all live on this one entity. `points` is too large for the recorder,
  which `_unrecorded_attributes = frozenset({"points"})` handles - a
  plain per-attribute-name class field, needing no separate entity.
- `select.<slug>_flare_phase` - manual phase override,
  self-clearing at the next natural phase boundary unless
  `switch.<slug>_sticky_phase_override` is on. Implemented by comparing
  against the phase computed at override time on every refresh, not a
  timer.
- Five `time.*` boundaries and eight `number.*` curve values, as live
  `entity_category: config` entities.

**A schedule exports and imports as YAML** (`schedule/transfer.py`),
keyed by phase, through `flare.export_schedule` / `flare.import_schedule`,
the schedule's Reconfigure step, the schedule view's transfer card and the
docs playground. Things worth knowing:

- Parsed with PyYAML's `BaseLoader`, which reads every scalar as a string:
  YAML 1.1 reads an unquoted `06:30` as the base-60 number 390.
- `dump()` writes the text by hand so every time is quoted;
  `yaml.safe_dump` quotes a time only when it looks like a 1.1 number.
  `docs/assets/js/schedule-yaml.js` is the playground's copy of both
  halves, held to it by `test_schedule_yaml_parity.py`.
- Import sets the entities through `time.set_value` / `number.set_value`,
  so Reconfigure aborts rather than updating the subentry (no reload).
  Everything is parsed before anything is set.
- Times aren't required to be in order, because the entities aren't
  (`phase_marks` handles it).
- The two services are registered in `async_setup`, not by an entry:
  they need only a schedule's entities, and the Zones entry may not exist.

**Config lives in entity state, not `subentry.data`** - `coordinator.py`
reads `hass.states.get(...)` for each. Writing back into `subentry.data`
was rejected: every subentry data change triggers a full entry reload,
recreating every coordinator and entity just to tweak one number. A
genuinely-missing entity falls back to the same default the entity
itself will report moments later, so `phase_at()` never sees a missing
boundary.

### Curve math (`curve.py`)

Every brightness/Kelvin literal is a keyword-only parameter with a named
default (`DEFAULT_CURVE_VALUES`, `DEFAULT_SCHEDULE_HOURS`). Non-obvious
facts:

- The brightness fade's span is **1.6× the nominal evening-to-night
  window**, not 1:1 - kept as a ratio so a custom brightness range
  keeps the same timing shape.
- The Kelvin evening tail is
  `evening_kelvin + (night_kelvin - evening_kelvin) * t`, continuous by
  construction.
- `day_phase` is a **parameter**, not derived from `now_ts` -
  `coordinator.py` passes a manually-overridden phase alongside the real
  time, so phase and instant can legitimately disagree. Every ramp
  clamps its interpolation factor for that reason.
- `kelvin_to_rgb` **delegates to
  `homeassistant.util.color.color_temperature_to_rgb`** rather than
  carrying its own copy. HA's is Tanner Helland's approximation (its own
  docstring says so) and was measured identical to the hand-written copy
  it replaced across 1000-10000K - zero units of difference on any
  channel. Don't reimplement it again.
  What is still ours is the round-half-up wrapper
  (`math.floor(x+0.5)`), matching the card's `Math.round` rather than
  Python's banker's rounding. **Measured, that is currently
  unobservable** - no integer Kelvin in range lands on an exact .5, and
  `kelvin_for_phase` only ever passes integers - so `round()` would pass
  every test today. It is kept deliberately, and the docstring says as
  much so nobody "simplifies" it on the assumption the equivalence is
  permanent. Truncating instead DOES break three tests including both
  parity tests.
  One behaviour change came with the delegation: HA clamps input to
  1000-40000K where the old copy extrapolated. The `number` entities are
  bounded 1000-10000, but `compute_curve`'s schema is not.
  `test_below_1000k_clamps` pins it - and note
  that test is a **dependency contract**, not a logic test: the clamping
  is HA's code, so there is nothing of ours to mutate against it.

**Do not re-add `night_floor_kelvin` or `kelvin_rgb`.** Both were cut
deliberately at the user's direction. RGB is just the Kelvin→RGB
conversion of `kelvin`; there is no separate RGB curve.

### Blueprint (`custom_components/flare/blueprints/flare.yaml`)

**The blueprint ships inside the integration**, and both repairs install
it from there. It used to live at the repo root and the repairs
downloaded it from the release's GitHub tag; that was only ever because
the blueprint once had its own version. Once it was versioned with FLARE
(see "Blueprint version checking"), the file HACS had just installed was
the one being downloaded. HA itself never loads it: only built-in
integrations get their blueprints auto-installed. It has no
`source_url`, so HA's "Re-import" (which would fetch `main`, lesson 12)
isn't offered; the repair is how it updates.

**Every `condition:` (leaf and composite - `and`/`or`/`not`/`trigger`/
`template`/`occupancy.is_detected`) and every `choose:` branch carries
an `alias:`.** Purely cosmetic - HA ignores it for evaluation, confirmed
against `CONDITION_BASE_SCHEMA`/`_SCRIPT_CHOOSE_SCHEMA` in
`homeassistant/helpers/config_validation.py`, both of which accept it
as `vol.Optional`. It exists because the trace viewer (see "The
blueprint trace viewer..." above) otherwise has nothing but a bare
`condition: trigger`/`condition: and` to show for a step with no
alias, which is unreadable at a glance - added at the user's request
once the viewer's own alias-preference made the gap in the blueprint
obvious. **The one place this couldn't be additive:** the top-level
`condition:` block used `or:`/`and:`/`not:` *shorthand* (a single-key
map, e.g. `{or: [...]}`), and the viewer's `resolveYamlPath()` detects
that shape by checking the map has exactly one key - adding a sibling
`alias:` key would have broken that detection for every path
underneath it. Rewritten to the explicit form (`condition: or,
conditions: [...]`) instead, which HA normalizes shorthand to
internally anyway (same trace paths either way - confirmed, this is
why `trace_viewer.py`'s own docstring already knew about the
normalization), so the alias could be added as an ordinary sibling of
a real `conditions:` key with no risk to path resolution. No other
`and`/`or`/`not` in the blueprint uses shorthand, so this was a one-time
fix, not a pattern to repeat elsewhere.

**`room_target`** is a single entity/device/area/floor/label `target`
doing double duty: lights within it are controlled, and occupancy- and
motion-class `binary_sensor`s within it govern occupancy via HA's native
`occupancy` and `motion` integrations (both 2026.4). Each filters
strictly by its own device class, so the blueprint has a detected and a
cleared trigger for each, sharing the `motion_on` / `motion_off` ids.
Motion support was added late: the blueprint only listened to occupancy
for a long time, on the mistaken belief that motion needed hand-written
triggers. The schemas require `target:` to be present, and `room_target`
is a required input with no default.

`room_target` is resolved **once**, into `target_named_entities` +
`target_expanded_entities`, which the three consumers filter:
`resolved_entities` (lights), `room_occupancy_entities`
(occupancy- and motion-class binary_sensors), `scope_entities` (scene scope). The
halves are kept apart because a *directly named* light also pulls in its
device's siblings while the device/area halves already return those -
merging them would silently widen scene scope. Floors resolve to their
areas (`floor_areas`), and labels to their labelled entities (named),
devices and areas (`label_entities`/`label_devices`/`label_areas`). The
`recovered` trigger repeats this resolution, since a trigger template
can't read `variables:`.

`room_occupancy_entities` exists only to decide *whether* the room has
an occupancy sensor at all. That matters because
`occupancy.is_detected`'s `any`-across-target semantics are vacuously
**false** over a target matching zero entities - so a light-only room
would otherwise permanently fail the condition.

**Triggers:** `phase_change` (`event.received` on the Schedule device's
Phase), `tick`
(an `event` trigger on `flare_tick` with the Zone's `device_id`), `extra`, `motion_on` /
`motion_off` (`occupancy.detected`/`cleared`), `recovered`.

**Zone ticks exist to stop every room writing in the same second.**
Observed 2026-09-27: all rooms' `time_pattern` fired within ~0.2s of
:00, and Z2M's `ROUTE_ERROR_MANY_TO_ONE_ROUTE_FAILURE`s clustered in
seconds 0-4 of the minute (90 vs 10-30 in any other 5s window), with
command timeouts landing at :10 - sent at :00. `zone/ticker.py`
fires each zone's `flare_tick` bus event a gap apart (title order),
starting on each interval boundary; the blueprint's decision still
happens fresh at trigger time, so this is NOT the jitter that was
removed (see Standing decisions). Every room has a zone, so there is no
`time_pattern` fallback.

- **The tick is a plain bus event, `flare_tick` with `{"device_id": ...}`,
  not an entity** (`__init__.py`'s `_ticker`), at the user's direction:
  as an event entity it logged every minute in every zone's Activity and
  history, burying the events that matter. Undescribed bus events never
  reach the logbook. It was an event entity (`event.<slug>_flare_tick`)
  until 1.0.0; setup deletes any left in the registry. With no entity,
  nothing cancels the scheduler at shutdown, hence the explicit
  `EVENT_HOMEASSISTANT_STOP` listener - without it the tests fail on
  lingering timers.
- **Lights & Occupancy's selector has no device filter**, so the zone
  can't be picked there: the frontend only lists a device in a target
  picker if it ALSO has an entity passing the entity filter
  (`getDevices` in `src/data/device/device_picker.ts`). Hence the
  separate Zone input.
- A tick is still one recorder row per zone per interval, in the events
  table. Accepted: the schedule sensor already writes one per minute.

- `phase_change` is the schedule's Phase event, which `event.py` fires
  only when the phase actually changes (a manual override included) and
  once on the first refresh after setup, so a restart still repaints
  rooms. Attribute-only updates never fire it.
- `tick` exists because `phase_change` fires only at a phase boundary,
  while the curve ramps within Evening and lights drift between
  boundaries.
- `recovered` arms on "at least one of our lights is reachable", firing
  as the first bulb returns. The inverse ("none unavailable") is wrong:
  one permanently-unavailable orphan holds it false forever and disables
  recovery for the whole room. Accepted blind spot: one flaky bulb
  recovering beside healthy siblings doesn't move the aggregate;
  `tick` mops that up.
- `recovered`'s `value_template` **cannot reference `trigger.*`** - HA
  renders it with only `trigger_variables` in scope, injecting `trigger`
  afterwards for the fired action only; a reference there means it never
  fires.

**There is no delay anywhere in `action:`, and there must not be.**
`variables:` render once, at trigger time, so anything reached after a
delay acts on a snapshot. `update_jitter` (a 0-15s `delay:` step, first
in `action:`) is why: it made every room hold a stale answer for up to a
quarter of each minute, and a light switched off by hand inside that
window was relit by a run that had already decided the room was in use.
`test_nothing_delays_the_action_before_it_decides` pins this.

Note what could NOT save it, because it is the obvious wrong answer:
override protection. Turning off the last light in a zone releases every
claim it holds (`_release_if_dark`, from the state_changed listener),
which is correct - it is what stops a room being locked out forever - so
there is no claim left to judge the hand turn-off against. The only thing
that says no at that point is `allow_turn_on`, and a delay is precisely
what makes it stale. Anything reintroducing a delay must re-derive the
whole gate after it, not rely on the integration to catch the mistake.

**`condition:`** only decides whether the tick is relevant at all. It
does **not** check occupancy: occupancy's only two jobs are turning a
room on (`motion_on` + `allow_turn_on`) and off once empty. Gating
adaptive ticks on it just meant an already-on light got skipped.

**`allow_turn_on` = `manual_run or trigger.id == 'motion_on' or
occupied`. This must never gain a new way to become true without the
user explicitly asking for it in so many words** - not implied, not
inferred as reasonable. The user's position on this is emphatic and
standing. Note `automation.trigger` from another automation counts as a
manual run (`trigger` is defined, `trigger.id` isn't), so anyone wanting
an event to light a room writes their own automation that calls it - no
blueprint input needed.

**It is a single structural gate, not a rule each path re-implements.**
Exactly two things in the blueprint can switch a light on -
`scene.turn_on` and `flare.apply_lighting` - and both sit inside one
`if allow_turn_on` block in `default:`. Nothing else in `action:` ever
writes an "on" state (the rest is two `flare.turn_off` calls and
one `claims_clear` bookkeeping step). Anything added later that can switch a
light on belongs in that same block; `tests/functional/blueprint/test_occupancy.py`'s
`test_no_trigger_reaching_default_can_light_a_dark_empty_room` sweeps
every trigger reaching `default:` to enforce it.

This shape was arrived at the hard way. The rule used to be enforced two
different ways - `apply_lighting` by filtering its own
`target_entities` list, and the scene not at all - so a phase
change lit an empty Dining Room's 14 fixtures at 23:00 and self-heal
undid it 9 seconds later, every night. **Do not re-add the per-entity
filter** (`reject('is_state', 'off')` when `allow_turn_on` is false): it
was redundant, not load-bearing. `occupied` ("a light is on") is itself
one of the three ways `allow_turn_on` becomes true, so a false
`allow_turn_on` already means nothing in the room is on - the filter
could only ever return `unavailable`/`unknown` entities, which
`grouping.py` drops as unreachable. Answering a room-level permission
question per-entity is exactly what let the scene path miss it.

**Idle Brightness** lets a room's "off" be dim rather than dark - the
nightlight feature. Four per-phase `*_idle_brightness` inputs plus
`idle_brightness_template`, same precedence idiom as Brightness Template
(`dict(phase_base, **template_result)`).

**This is the one thing in the blueprint that can switch a light on
outside `allow_turn_on`**, added at the user's explicit request - *"yes
its a nightlight so it can turn on (because we're redefining what 'off'
means)"* - which is the standard CLAUDE.md sets for widening that rule.
`allow_turn_on` itself is untouched: the idle gate is `room_is_idle`,
which is *narrower*, so the curve still cannot light an empty room.

- **`room_is_idle` is load-bearing and non-obvious.** An idle light
  being on makes `occupied` true, which makes `allow_turn_on` true,
  which would let the curve apply full brightness on the very next tick
  - the nightlight ramps itself back up and quietly stops being one. So
  the curve's gate is `allow_turn_on and not room_is_idle`, and the two
  branches in `default:` are mutually exclusive. **Mutation testing
  found this**: the first version had the bug and every test passed,
  because they each only ran a single tick.
  `test_an_idle_light_does_not_ramp_itself_back_up` is the regression.
- **It must not be gated on `occupied` or `allow_turn_on`** for the same
  reason - both are true the moment an idle light is lit.
- **`room_occupancy_entities | length > 0` is required**, because
  `occupancy.is_detected` is vacuously false over zero sensors, so a
  light-only room would read as permanently empty, sit at the idle level
  forever and never reach the curve.
- **`occupancy_clear_for_wait`** was extracted from the self-heal
  branch's inline condition so both use one rule. The idle branch runs
  on every tick, so without it a room would dim within a minute of
  motion stopping, ignoring Wait time - and these are PIR sensors, which
  flap by design.
- `entities_still_on` excludes `idle_entities`, or self-heal retries
  turning off the light the idle branch just turned on, every tick.
- **`condition:`'s motion_on efficiency check had to learn about idle
  too.** It asks "is anything off?" as a proxy for "is there anything to
  do?", which an idle room breaks: everything is ON, at the idle level,
  and motion is exactly when it should go up to the curve. The run
  aborted there, so the room brightened only on the next `tick`
  - up to a minute late and with `background_transition` instead of
  `motion_on_transition`, since `script_transition` keys off the trigger
  id; a brief passage never brightened it at all. Fixed with
  `or idle_entities | length > 0`. It must be `idle_entities`, NOT
  `room_is_idle` - the latter includes `occupancy_clear_for_wait`, false
  the instant motion fires, so it would still abort. Reported live;
  `test_motion_into_an_already_lit_idle_room_brightens_it` is the
  regression, and it asserts the TRANSITION, which is what pins which
  trigger the call came from.
- **A template level with the phase value at 0 is the whole idle set,
  not an override on top of one** - so it silently makes that lamp the
  room's only nightlight, and `room_is_idle` goes true for the whole
  room on the strength of it, suppressing the curve for every other
  light. Working as documented, but it caught out this repo's own
  landing config, where a template written to make one pendant *dimmer*
  quietly became "this is the only nightlight" in every phase with no
  value set. `test_a_template_level_alone_makes_that_lamp_the_only_nightlight`
  pins it.
- A `null` level outranks an idle level - "something else owns this"
  wins over "stay dimly lit".
- **Levels travel to the service as levels** - see "Brightness levels"
  below, which both paths share.

**Inbound doc links are now tested.** `docs/reference/blueprint.md`'s headings are
deep-linked from the blueprint's own input descriptions and from every
test class docstring, and the #172 restructure silently broke six of
them. `tests/checks/test_docs_site.py::test_every_referenced_blueprint_anchor_exists`
derives kramdown's slugs and fails on a dead anchor.

**Self-heal** shares `tick` rather than its own interval. Its
eligibility checks sit in the `choose:` branch's own `conditions:`, so a
tick that doesn't qualify falls through to `default:` and reapplies
lighting normally. It stays **exclusive** of `default:` deliberately:
`entities_still_on`/`target_entities` are computed once before
`action:` runs, so reapplying in the same run risks `apply_lighting`
turning a just-turned-off light straight back on. It requires occupancy
continuously clear for the full Wait time, checked with a hand-written
`now() - last_changed` template rather than
`occupancy.is_not_detected`'s native `for:` - that needs the recorder to
prime a duration already satisfied before the condition started
watching, which isn't reliable right after a restart.

**Phase names appear in three inputs** - `rgb_phases`, the four
per-phase scene pickers, and the four per-phase exclude lists. A
deliberate exception to "the blueprint doesn't know phase names",
explicitly chosen. All phase-keyed dict lookups use `.get(key, default)`,
never direct indexing: the schedule sensor can legitimately be
`unknown`/`unavailable`, and direct indexing would crash the whole tick.
`scene_template` wins over the per-phase pick whenever it returns a valid
scene; `brightness_template`'s per-entity values likewise win over the
phase exclude lists (`dict(phase_base, **template_result)`).

**Brightness levels are ABSOLUTE 0-255, not multipliers of the curve.**
`brightness_template` and the four `*_idle_brightness` inputs all name
the brightness a light sits at, on the same scale as the per-phase
brightness `number` entities. Chosen at the user's direction: a
multiplier of the curve made pinning a light at a fixed level awkward.

**The services take levels too** (`brightness_levels`, since 1.0.0). They
used to take per-entity *multipliers* of `brightness`, and the blueprint
converted every level to `level/255` against a brightness of 255. Changed
at the user's direction so the service and the blueprint speak the same
units; the blueprint now passes its levels straight through. Rules,
all in `grouping.target_brightness()`, which the blueprint test harness
also calls so its expectations can't drift from the service:

- **A light without a level gets `brightness`**, which is why the service
  only requires `brightness` when some light lacks a level - the idle
  calls send levels alone.
- **`0` is off, for `brightness` and levels alike**, matching
  `light.turn_on` (`homeassistant/components/light/__init__.py`). So a
  schedule phase at brightness 0 turns the room's lights off during it.
  It used to mean "as dim as this goes", and was changed at the user's
  direction so the two fields don't disagree. Anything else clamps into
  1-255, so 0.4 lands on 1.

**`0` and `null` levels are not the same thing.** `0` means "turn this
light off"; `null`/`false` means "hands off, something else owns it" -
excluded from the turn-off paths too, not just the adaptive step. Both
are sentinels `grouping.py` matches on identity. In Jinja as in
Python `0 == false`, so membership tests like `in [none, false]` silently
swallow every `0`; the identity form `level is none or level is sameas
false` is required, mirroring `grouping.py`'s own bucketing.

**`variables:` renders strictly top to bottom**, each key seeing only
those above it, and failures are silent (`x | length` on an undefined
name returns `0` with no log and no trace entry). The brightness-level
chain sits near the top specifically because the turn-off lists depend on
it.

**Sensor reads are guarded before dispatch.** `brightness`/
`color_temp_kelvin` are plain `state_attr()` reads and `apply_lighting`
requires both, so an unavailable or renamed sensor would fail validation
every tick. The guard wraps that one action step rather than
`condition:`, because `motion_off` and self-heal turn lights *off* and
need nothing from the sensor.

**`device_class: occupancy` does not mean the sensor can tell whether
someone is still in the room.** Most sensors here are plain PIR motion
sensors: they report clear the moment motion stops, including while
someone sits still, then flip back on the next movement. Rapid on/off
flapping is normal, not a fault. `no_motion_wait` exists to turn "motion
stopped a moment ago" into a usable proxy for "the room is empty". Only
a couple of sensors here are genuine mmWave presence sensors, and the
blueprint can't tell the two apart - both just present as
`device_class: occupancy` - so Wait time is sized for the PIR case
everywhere.

Nightlight-style overrides need no dedicated mechanism: a template
`binary_sensor` with `device_class: occupancy`, named directly in
`room_target`, gets full native `occupancy.*` support, since the
trigger/condition machinery only looks at entity state, not origin.

### Standing decisions - don't re-propose without new information

- **Extracting target resolution into a service or a Jinja macro.**
  `condition:` can't call services and runs before `action:`; a
  `custom_templates/*.jinja` macro needs a full HA restart to load
  (lesson 2) and would add a manual install step to an otherwise
  self-contained blueprint; registering a global Jinja function means
  monkey-patching the shared template engine. Deduplicating *within*
  `variables:` has none of those blockers and is what's actually done.
- **Condition/action-selector inputs replacing `scene_template` /
  `brightness_template`.** Investigated properly against
  `blueprint/models.py` and `annotatedyaml`. A blueprint input's
  `default:` cannot reference another input's value (the `blueprint:`
  key is discarded before substitution). Brightness has no viable
  selector at all - it returns a *value*, which neither `action` nor
  `condition` can produce. Scene handoff is convertible only by giving
  up gap-fill, since a native condition evaluates structurally too late
  to feed the single Jinja pass that computes it.
- **`activating_triggers`** (a second Additional Triggers input allowed
  to turn lights on). Built, shipped, then reverted: "added complexity
  for something that someone can just do via another automation".
- **Jitter, in any form** - removed in 0.16.0, don't reintroduce it
  without new evidence. (Congestion was later observed, 2026-09-27, and
  answered with zone ticks: deterministic trigger-side spacing, with the
  decision made after the trigger - see Triggers above. The reasoning
  below still rules out a delay anywhere after the decision.) It was added preventively in #73 with no observed
  congestion, and the evidence against keeping it was concrete: it caused
  a live relight bug (see the no-delay rule above), `grouping.py`'s
  tolerance check already suppresses most writes so a routine tick sends
  almost nothing, and 11h of this house's log showed zero Zigbee command
  failures across 72 MQTT lights. The alternatives were all worse: a
  delay anywhere in the decision path needs `allow_turn_on` re-derived
  after it; moving it into `apply_lighting` cannot work, because the
  service has no concept of room-level permission and so cannot re-check
  the half that actually matters; and trigger-side jitter (`for:` on the
  `phase_change` state trigger) covers phase changes only -
  `time_pattern` has no offset, so it misses `tick`, which is where the
  exposure is. If congestion is ever actually observed, the right shape
  is a bounded rate limiter at dispatch, not a random pre-decision delay.
  Note also the general Zigbee mitigation is group addressing, not
  spreading unicasts.
- **`night_floor_kelvin` / `kelvin_rgb`** - see Curve math above.
- **Virtual per-phase `light` entities** replacing the eight curve
  `number`s, so a phase is set from a normal light card (and gains RGB).
  Rejected on Liskov: a phase target has no off state, so `turn_off`
  would have to lie - and it must, because `light.turn_off` with
  `entity_id: all` reaches it regardless of `entity_category` or
  `hidden_by` (`helpers/service.py`'s `target_all_entities` branch is
  `return list(entities.values())`; `all` skips target resolution by
  definition). An always-on light also reports `on` in every
  `states.light` template.
  **Revisit if HA changes either half of that** - a colour-picker card
  feature, or card features usable on a non-light entity. Today all
  three light features gate on `computeDomain(...) === "light"` and
  write via `light.turn_on`, and there is no colour-picker feature at
  all (the wheel lives only in `ha-more-info-light`) - which is the
  whole reason `flare-kelvin-feature.js` /
  `flare-brightness-feature.js` / `flare-value-slider.js` exist.
  **The gate is always the entity_id's domain PREFIX** - `computeDomain()`
  in the features, and again when more-info picks its control element
  (no aliasing, no fallback for an unknown domain). Python class
  hierarchy, `device_class` and state attributes are all invisible to
  it, so a bespoke `virtual_light` domain inheriting `LightEntity` gets
  none of these controls. An empty light group is not a route either:
  `group/light.py` derives every attribute from its members and
  *forwards* `turn_on` to them, so with none it stores nothing, offers
  `{ColorMode.ONOFF}` and reports unavailable.

### Parked: scene handling in `apply_lighting`

Not implemented; recorded so it isn't re-derived. Two designs:

1. **Straight port** - `apply_lighting` gains optional
   `scene_entity_id`/`scope_entities`, calls `compute_scene_coverage`
   internally, then `scene.turn_on` plus dispatch on
   `uncovered_entities`. Known cost: loses the `condition:`-level
   suppression that stops the tick running while a scene owns the room.
   Accepted as fine if picked up.
2. **Bigger idea** - read a scene's *stored* per-entity values and feed
   them through the grouping/multiplier pipeline, so a brightness
   multiplier could scale a scene's own brightness (which it explicitly
   cannot today). `ha_config_get_scene` does expose full per-entity
   attributes, but: a scene captures whichever colour mode was active
   when recorded (`xy`/`hs`/`color_temp` can all appear in one scene,
   and `apply_lighting` understands only colour-temp and RGB), reading
   stored scene config is a less-trodden surface than the
   `hass.states`/registry trio used everywhere else, and scenes can
   carry `effect` and non-light domains. Treat as its own decision, not
   a prerequisite for (1).

### Two-step transition detection

Routed two ways, OR'd together - `grouping.py`'s `EntityLookup.
matches_two_step_pattern()` compares a light's device
`"<manufacturer> <model>"` against a configurable list of
case-insensitive globs (`CONF_TWO_STEP_MODELS`, read fresh per call via
`services/handlers.py`'s `_two_step_model_patterns()`), **or** the entity/device
carries the `no_combined_transition` label (`EntityLookup.tags()`,
unchanged). `two_step.py` holds only the pure matching primitives
(`model_matches`, `parse_patterns`, `DEFAULT_TWO_STEP_MODEL_PATTERNS`,
`TWO_STEP_LABEL_ID`) - no HA imports, same split as curve.py/
grouping.py/scenes.py. The options field is **seeded with the shipped
defaults and holds the whole list** - a saved value replaces them
outright, so deleting a shipped pattern takes effect. An
empty/whitespace field falls back to the defaults, so clearing the box
can't silently disable matching.

**Why direct pattern matching, not just the label:** this used to be
label-only, with a repair (`two_step_check.py`'s issue-raising +
`repairs.py`'s `MissingTwoStepLabelRepairFlow`) comparing manufacturer/
model against the same pattern list and *suggesting* the label via a
Fix button. Live IKEA TRADFRI bulbs kept misbehaving because the label
wasn't reliably applied - a missed repair, a bulb re-paired without it
- and a repair can only nag, never fix behaviour, until a human acts on
it. Since the pattern list was already enough to know which bulbs need
this, comparing it directly at routing time makes correct behaviour the
default with no manual step; the label stays as a manual escape hatch
for anything a pattern doesn't (yet) cover. The repair was removed
entirely rather than kept alongside the live check: once matching is
automatic, it would only ever nag about bulbs already working fine
without the label - a permanent false positive, not a temporary one.

**Accepted trade-off, higher-stakes than it sounds:** once a user saves
the field they own it, and a later release adding a newly-discovered
bulb won't reach them - chosen for consistency over reach, same as
before. But a bad or overly broad custom pattern now has an *immediate*
live effect (routes real dispatch into two-step transitions), not just
a repair suggestion someone can ignore - keep patterns narrow.

### Blueprint version checking

`blueprint_version.py` is pure (the stamp constant + parsing),
`blueprint_check.py` is the HA adapter, `repairs.py` carries the fix
flow - the same pure/adapter/fix-flow split used elsewhere in this
integration (e.g. curve.py/coordinator.py/sensor.py).

**`BLUEPRINT_VERSION` is the integration's version - the blueprint is
versioned WITH FLARE.** It used to be the version the blueprint last
changed in, chosen so a release touching only Python would not tell
every user to re-import an identical file. Reversed at the user's
direction on 2026-09-21 as confusing: two version numbers with different
meanings, and a release script that had to work out which one moved. The
cost is accepted and worth knowing - every release, betas included,
raises the out-of-date repair for anyone using the blueprint, even when
it did not change. Don't reintroduce the decoupling without new
information; the pieces that supported it (comparing against the
previous release's blueprint, the three "does the stamp name a real
tag" guards) were deleted.

**Nobody bumps it.** `scripts/release.py` writes the release's version
into that release's own copy of the constant and of the description's
stamp, along with the manifest's (only the manifest is a placeholder in
source, `0.0.0-dev`). So what source holds for those two is just the
last value anyone set by hand: it goes stale, and nothing minds,
provided the two agree. The hand-bump was the one step whose omission
failed silently - no repair, no error, nobody hears about the update -
and the `blueprint-stamp` CI job that policed it was deleted along with
it.

**The repair code deliberately knows nothing about dev builds.** It was
briefly taught to stand down on a placeholder version, and that was
removed at the user's direction: shipped code should not special-case a
development workflow. On a dev install the constant and the stamp both
hold whatever they last held, so they agree and the repair stays quiet
even when the blueprint changed - it is updated there with a direct
`ha_import_blueprint`. Fix is safe there too: it installs the file
shipped beside the integration under test.

**The stamp lives in the blueprint's `description`** because there is
nowhere else. `blueprint/schemas.py` validates the `blueprint:` block
against a CLOSED voluptuous schema (name/description/domain/source_url/
author/homeassistant/input), so there is no custom key; a top-level key
alongside `blueprint:` lands in the generated *automation* config
instead. `description` is free text, survives any import route, is
readable via `Blueprint.metadata` with no filesystem access, and shows
the version to the user in the automation editor.

**Two repairs, mutually exclusive.** `blueprint_not_installed` fires
when no copy of our blueprint exists at all; `outdated_blueprint` when
an in-use copy is stale. `async_check` clears whichever it isn't
raising, so a house moving between the two states leaves nothing behind.

- **The missing check deliberately does NOT ask whether anyone is using
  it.** Chosen at the user's direction over a narrower "FLARE is set up
  and nothing is driving it" guard, and the reasoning is the point:
  someone can arrive from the HACS store with no idea a blueprint
  exists, install the integration, and reasonably wonder why nothing
  happened. An installed-but-unused blueprint still counts as installed
  (mid-setup, not stuck), which is the one case where the two checks
  genuinely differ. Anyone going services-only ignores it, which HA
  remembers across version bumps.
- **`IssueSeverity` has no INFO level** - WARNING is the floor, which is
  why the wording carries the "the blueprint is optional" line rather
  than the severity carrying it.
- **The install path is `flare/flare.yaml`** (`INSTALL_PATH`), at the
  user's direction - it was `danrspencer/flare.yaml`, the path a GitHub
  import derives, back when importing by URL was a supported route.
- **The quickstart's import badge is gone**, replaced by this repair -
  at the user's direction. Don't reintroduce it: it went through
  `my.home-assistant.io` to a `main` raw URL, which is lessons 12 and 13
  in a single link.
- **The install uses `allow_override=False`**, unlike the update path:
  it exists only for the no-blueprint case, and silently overwriting
  something that appeared between the check and the Fix press is what
  the other repair is for.
- **Only blueprints an automation actually uses are reported**
  (`automations_with_blueprint`). HA never removes an unreferenced
  blueprint, and lesson 13's owner-vs-folder mismatch means a house can
  hold an orphan at a second path forever - a repair about a file
  nothing reads is noise the user can't silence.
- **The fix writes the shipped file** to whatever path the stale copy
  was found at, rather than the path HA would derive. `async_add_blueprint(..., allow_override=True)`
  reloads the consuming automations itself.
- **The check runs via `async_at_started`, not during setup** -
  automations decide whether a blueprint is in use, and during setup
  they may not have loaded, so checking early finds every blueprint
  orphaned and reports nothing. Zones entry only, so a house with
  more than one entry doesn't run it twice.
- A blueprint that fails to load comes back from
  `async_get_blueprints()` as the **exception**, not a `Blueprint` -
  hence the `isinstance` check, not a `None` check.
- **The stamp is the release's own version.** `scripts/release.py`
  writes it, so it is right by construction; `release.yml` checks it
  for a tag pushed by hand (constant and description must both equal
  the tag), because a constant and stamp that disagree would raise the
  outdated repair on every install, with a Fix that can never clear it.

**The functional tests install the blueprint as a COPY**
(`tests/functional/conftest.py`), never a symlink: tests write
blueprint files, and a symlink writes them into the actual repo - which
happened once, and four junk blueprints were staged before it was
caught.

### Deployment / operational notes

- **Releases are automated, in three tiers** (set up 2026-09-21 at the
  user's request - it replaces the earlier rule, from 2026-09-08, that a
  stable tag happened only on his say-so; the hold below is what keeps
  his veto):
  `dev` (the churn branch) -> a push of `dev` to `main` cuts
  `vX.Y.Z-beta.N` (`cut-beta.yml`) -> a daily job promotes a version's
  newest beta to `vX.Y.Z` once it is 7 days old (`promote.yml`).
  `X.Y.Z` is read from the top `## [x.y.z]` heading of `CHANGELOG.md`.
  An open issue labelled `release-blocker` stops a promotion; nothing
  else does. Soak is per version (a fresh `0.0.2-beta.1` does not hold
  back a week-old `0.0.1-beta.4`, but a later beta of the same version
  restarts its clock), and a version at or below the highest stable is
  never promoted.
- **Nothing is committed to a branch for a release.** The manifest's
  version in source is the placeholder `0.0.0-dev`, and `scripts/release.py` builds
  each release as a commit on top of its source commit - real version
  written into `manifest.json`, `BLUEPRINT_VERSION` and the blueprint
  stamp - tagged and reachable from no branch. Chosen over a bot
  committing bumps to `main` because that leaves `dev` without the
  bump, so every release needs a back-merge (and `main` requires linear
  history). A promotion rebuilds the beta's own source commit, recorded
  as `Source:` in the release commit's message; a hand-made tag has none
  and cannot be promoted. Consequences worth knowing: GitHub shows a "not on any branch" banner on release commits;
  and `main`'s changelog section is never re-dated, so headings carry
  whatever a person wrote.
- **A tag pushed by a workflow does not trigger another workflow**
  (GITHUB_TOKEN events don't), so `release.yml` never runs for the
  automated releases. That is fine and deliberate: its checks police a
  tag typed by hand, and the script's tags agree with their manifests
  by construction. Don't "fix" it with a PAT to make it run.
- **`git push origin dev:main` must be a fast-forward.** `main`'s
  ruleset requires linear history, so a pull request's squash or rebase
  would give `main` commits `dev` never sees.
- **Versioning**: `manifest.json`'s `version` is what HACS reports, read
  out of the release's own tag. `tests/checks/test_versions.py` pins that the
  source holds the placeholder and the changelog's top heading is
  parseable; `release.yml` re-checks tag/manifest agreement for tags
  made by hand. Full flow in CONTRIBUTING.md.
- **HACS has no dev channel, and the default branch is NOT one.** An
  earlier version of this section (and of what was proposed to the user)
  claimed HACS offers a repo's default branch in its version dropdown,
  tracked by commit, unless `hacs.json` sets `hide_default_branch`. That
  is the pre-2.0 behaviour, and it is what hacs.xyz still documents. HACS
  2.x removed it (hacs/integration#4009, closed as not planned): the
  frontend's "different version" list comes only from
  `hacs/repository/releases` (GitHub releases), and never reads
  `hide_default_branch`. Commit-tracking of the default branch applies
  only to repositories that publish NO releases. So flipping the default
  branch or dropping `hide_default_branch` achieves nothing - don't
  propose it again. Found by the user asking to see the docs; the claim
  had come from reading the backend's `pending_update`, which still has
  the case, without checking that the UI can reach it.
  What does exist, and is how work-in-progress gets onto the live
  instance: `hacs/repository/download` accepts any `version` string.
  The download URL is `archive/<sha>.zip` for a 40-character commit SHA
  and otherwise falls back from `refs/tags/X.zip` to `refs/heads/X.zip`.
  Nothing is reported as an update afterwards.
- **While developing, install the working commit from HACS directly -
  do not publish a version to test it.** Setting this out as the
  standing way to work, at the user's direction on 2026-09-21: no tag, no
  beta, no release, and never cut one just to get code onto the
  instance (a beta is what testers are offered, so it is not a scratch
  build). The steps:
  1. Push the branch. HACS downloads from GitHub, not from a local
     checkout, so unpushed work cannot be installed.
  2. `ha_manage_hacs(action="download", repository_id="danrspencer/flare",
     version="<full commit SHA>")`. Prefer the SHA to a branch name: it
     is immutable (lesson 12's reasoning) and skips branch resolution.
  3. Confirm with `ha_read_file` that the deployed files match that
     commit before restarting, then restart.
  4. If the blueprint changed: `ha_manage_blueprints(action="save",
     path="flare/flare.yaml", overwrite=True)` with
     `custom_components/flare/blueprints/flare.yaml` at that SHA (not
     `ha_import_blueprint`, which would land under `danrspencer/` -
     lesson 13). The repair can't tell, since the stamps agree. **To get back onto a release**,
  download `version` = the release tag. **Not yet exercised against
  this integration:** it is read from HACS's source, not seen working.
  The first time it is used, check the result and HACS's log; if HACS
  refuses the ref, stop and say so rather than falling back to tagging.
- **Integration (a merged change, or getting back onto a release)**:
  HACS. `update_information` then `download`, confirm the deployed file
  matches the merge with `ha_read_file` before restarting (see lesson
  12), then restart.
- **Blueprint**: ships with the integration; a release raises the
  outdated repair, and its Fix installs it.
- **The dashboard front-end files ship inside the integration**
  (`custom_components/flare/www/`) and self-register
  via `async_setup` → `async_register_static_paths` +
  `add_extra_js_url`. Two of them now: `flare-curve-card.js` (a card)
  and `flare-kelvin-feature.js` (a *card feature* - registered on
  `window.customCardFeatures`, not `customCards`; the older
  `customTileFeatures` name is not used). One StaticPathConfig serves
  the directory, so each new file needs only its own
  `add_extra_js_url`. The feature imports `kelvinToRgb` from the card
  rather than copying it, so its fill colour and the chart agree by
  construction - ES modules are per-URL singletons, so the shared
  import costs nothing. It renders `ha-control-slider` - the frontend's
  own element, the one the built-in `numeric-input` feature uses -
  styled with a copy of the frontend's `cardFeatureStyles` block for it,
  differing only in the two colour properties: the built-in points both
  `--control-slider-color` and `--control-slider-background` at
  `--feature-color`, this points both at the colour of the value, so
  the fill is solid and the remainder is that same colour at the same
  native 0.2 opacity. So the handle, rounded fill cap, tooltip and
  keyboard behaviour are HA's, and only the hue is ours; the tile's
  phase colour still shows on the icon. **The drag handle cannot be recoloured**:
  `ha-control-slider` hardcodes it to white on
  `.slider .slider-track-bar::after`, with no custom property and no
  `part=`, so at the pale end of the ramp (near 6667K the colour *is*
  nearly white) it blends into the fill. Injecting a rule into the
  slider's own shadow root was built, shipped in 0.10.6 and reverted in
  0.10.7 at the user's direction: it coupled to an internal class name,
  and it silently did nothing in practice because a Lit element only
  has a `shadowRoot` once connected, which the test stub (attaching in
  its constructor) was too forgiving to catch. **Don't re-attempt it
  without a supported hook.** **Two earlier versions are
  recorded in the file's header so they aren't re-attempted:** a
  full warm-to-cool gradient track (reads as a colour picker, not as one
  of a column of sliders), then a hand-rolled `<input type="range">`
  (right colour, but reimplemented the handle and fill cap and visibly
  didn't match). Depending on `ha-control-slider` is an accepted risk,
  taken at the user's direction - it is a frontend internal with no
  compatibility promise, so if it breaks, follow whatever
  `hui-numeric-input-card-feature.ts` does next. **`flare-value-slider.js`
  holds everything the two features share** (waiting for
  `ha-control-slider`, the `cardFeatureStyles` copy, commit-on-changed /
  repaint-on-moved); kelvin and brightness differ only in which entities
  they accept and what colour a value maps to. Brightness has no colour
  of its own, so it BORROWS one: `tint_from` names a colour-temperature
  entity (the section passes the same phase's Kelvin entity) and the
  fill is that colour, SOLID, with the fill's width carrying the value -
  which is what HA's own `light-brightness` feature does with a bulb's
  colour. Hence colour temperature sits LEFT of brightness in both pair
  grids: the colour is decided there and carried across. With no
  readable `tint_from` it falls back to `--primary-color`, which is also
  `ha-control-slider`'s own default fill, so it degrades to the stock
  slider. **Two fill treatments were tried and dropped**: fading the
  fill by value (redundant - the width already says it, and it only
  made a dim setting harder to see) and white-to-transparent (invisible
  at full brightness on a light theme). The unfilled track is left
  to the element's own `--disabled-color`, NOT the tile colour that
  `cardFeatureStyles` uses: a phase-tinted track under a value-tinted
  fill reads as two things fighting. It exists because a tile's slider takes
  its colour from `--feature-color`, which `hui-tile-card` sets to
  `var(--tile-color)`, and a tile `color` accepts no template - so the
  built-in `numeric-input` cannot show a value as a colour while the
  tile colour means something else. card-mod can, and was rejected: the
  generator's promise is paste-and-go with no third-party dependency.
  Built on `<input type="range">` rather than `ha-control-slider` for
  the same reason - no dependency on frontend internals. **The URL carries a fingerprint of the
  files** (`/flare_static/<hash>/...`, `www_fingerprint()`: sha256 of every
  file's path and bytes) with `cache_headers=True`. It carried the
  integration version until a dev build (always `0.0.0-dev`) kept serving a
  stale strategy from Safari's cache through Empty Caches; the hash changes
  exactly when the files do, for dev builds and releases alike, so it's not
  dev-only code. Before that it was an
  unversioned path with `cache_headers=False`, which **does not do what
  it sounds like**: that only omits `Cache-Control`, leaving `ETag` and
  `Last-Modified`, so browsers fall back to *heuristic* caching (roughly
  10% of the age since `Last-Modified`). Safari applies that keenly -
  confirmed live, where a just-deployed card and feature both rendered
  as "Configuration error" until the window lapsed, then "fixed
  themselves". With a URL per change a cached copy can never be taken
  for the current one, so caching hard is correct rather than merely
  tolerable. **It must be a path segment, not `?v=`**: these
  modules import each other relatively, and a relative import resolves
  against the importing module's own URL - a path is inherited by those
  imports, a query is not, so `?v=` would load the card twice under two
  URLs and the second `customElements.define` would throw. That
  relative-import invariant is pinned by
  `tests/checks/test_static_imports.py`. This replaced a separate symlink path
  that silently went stale for over a week.
- `scripts/link_into_ha.sh` was **deleted**, not fixed - once the cards
  travel with the integration there was nothing left for it to do, and
  untested deploy tooling nobody runs is a liability (lesson 7).
- **The integration icon must live inside the integration's own folder**
  (`custom_components/flare/brand/`, HA 2026.3.0+),
  not the repo root. `home-assistant/brands` no longer accepts custom
  integrations. Root `brand/` is authoring tooling only; the served PNGs
  need re-rendering by hand after a design change. HA serves them from
  `/api/brands/integration/flare/icon.png`, gated on `has_branding` -
  which is just `"brand" in top_level_files` (`loader.py`), so the
  directory existing in the installed folder is the whole requirement,
  no manifest key.

  **Every HACS-rendered surface ignores that and is not fixable from
  here** ([hacs/integration#5171](https://github.com/hacs/integration/issues/5171)).
  Verified rather than assumed: HACS sets its update entity's
  `entity_picture` to `https://brands.home-assistant.io/_/flare/icon.png`
  outright, and that CDN returns **200 for any domain at all** - a
  generated grey placeholder - so there is no 404 to detect and nothing
  a repo-side change can influence. That covers both the HACS store card
  and Settings -> System -> Updates, since the latter renders HACS's
  entity. HA's own integrations page uses the local path and is
  unaffected. The one HACS surface we *can* reach is the README, which
  it renders in the repository panel - hence the icon at the top of it.
- pyscript is fully gone from both this repo and the live host.
- **The dashboard ships as a Lovelace VIEW STRATEGY, not as pasted
  YAML.** `views: - strategy: {type: custom:flare}` resolves to
  `ll-strategy-view-flare` (`flare-view-strategy.js`), which builds one
  section per schedule sensor from `flare-section.js`. That file is the
  single definition of the layout and is a plain config OBJECT, not a
  string, because a strategy hands HA objects. It registers nothing, so
  it has no `add_extra_js_url` of its own - the strategy's import pulls
  it in.
  **This replaced a generator on the docs site** that emitted the same
  section as YAML to copy-paste. The generator, its CSS and its tests
  were deleted outright. Reason: the layout changed five times in a
  single session, and each change meant every user re-generating and
  re-pasting a section per schedule; a strategy is regenerated on every
  dashboard load, so a HACS update is the whole migration, and a newly
  added schedule sensor simply appears. The escape hatch for someone who
  wants to own the YAML is HA's own "Take control", which is one-way.
  When the port landed, `sectionConfig()`'s output was diffed against
  the generator's last output and was byte-identical - worth repeating
  if this is ever restructured again.
- **Two view strategies, not one**: `custom:flare-schedule` and
  `custom:flare-zone`, registered as
  `ll-strategy-view-flare-schedule` and
  `ll-strategy-view-flare-zone`. Kept
  apart because a house has one zone per room against a handful of
  schedules, so merging would bury the schedules, and they answer
  different questions - what a light should be doing versus who
  currently owns it. **The suffix test matters**: a zone's sensor is
  `sensor.<slug>_flare_claims`, which ends with `_flare` *plus more*,
  so `endsWith('_flare')` is load-bearing - `includes('_flare')` would
  put every zone in the schedule view. Both enumerators also require a
  distinguishing attribute (`points` / `claims`) so a name alone is
  never enough.
- **The Zones view has an Activity sidebar**, copied from HA's Security
  dashboard (`security-view-strategy.ts`), but not its `logbook` card:
  that card resolves a device target to the device's entities and asks
  for those only (`hui-logbook-card.ts` passes `entityIds`, never
  `deviceIds`, in 2026.9, 2026.10 and the frontend's dev branch), and the
  logbook server drops "continuous" sensors (any with a unit or state
  class) from that list (`logbook/helpers.py`, `async_filter_entities`),
  so the zone events filed under a count sensor never showed - only
  Clear presses did. `custom:flare-activity-card`
  (`www/flare-activity-card.js`) renders the frontend's own `ha-logbook`
  with the zones' entities AND `deviceIds`, exactly as a device page
  does. `ha-logbook` is lazy-loaded, so the card has `loadCardHelpers`
  create a built-in logbook card first, which imports it. Depending on
  `ha-logbook` is an accepted risk, like `ha-control-slider`: if it
  breaks, follow what `ha-config-device-page.ts` does next. Also
  weighed with the user and not taken: filing events under the Clear
  button (the zone page then labels every entry "Clear"), or the claims
  sensor with a fixed-word state.
- **The Zones view copies HA's Light dashboard** (`light-view-strategy.ts`,
  the user's screenshot): a section per floor (`column_span: 2`, by level),
  a subtitle heading per zone, and on wide screens Clear in the left third
  where that has "All off", with the zone's Controlled and Overridden
  tiles beside it where that has the lights (the screenshot was for layout
  only: lights there were a misreading, built and removed). Clear is
  FLARE's own `custom:flare-clear-card` (`www/flare-clear-card.js`), drawn
  like the "All off" `toggle-group` card: no card around it, a round icon
  and a label. A tile was tried and looked like one more tile in the grid;
  `toggle-group` itself can't be used, since its icon is always the power
  symbol and its text always on/off counts. On narrow screens Clear is a
  button badge on the heading (the `view_columns` conditions are HA's
  own). A zone's area is its device's, else the area named after it; it
  takes the area's name unless two zones share the area. The totals at
  the top are a markdown template summing the zones' counts, at the
  user's direction: a stacked statistics graph was tried and dropped as
  ugly, and so were total sensors.
- **FLARE's zone events** (`flare_lights_controlled`,
  `flare_lights_released`, `flare_light_overridden`) carry one of the
  zone's count sensors as `entity_id` and the zone's `device_id`, with the
  light(s) in `light`/`lights`, so they show on the zone's device page,
  labelled Controlled or Overridden. At the user's direction the zone
  speaks in whole-room terms - "now controlling 7 lights", "cleared 7
  lights" (`flare_lights_released`: dark release or the Clear button, not
  the `claims_clear` service, which the blueprint runs as bookkeeping) -
  and only an override names one light. A light becoming controlled
  again after an override is silent: a `flare_light_reclaimed` event was
  built and removed as churn. The logbook matches events to entities only
  through `entity_id`, so they can't also stay on the light's own
  timeline; the user chose the zone. The count sensors have units, so the
  logbook leaves their own state changes out - and, for the same reason,
  drops them from a logbook card's entity list, which is why the Zones
  view has its own Activity card (see the Zones view Activity notes).
- **`flare_lights_controlled` gathers for `CONTROLLED_GATHER_SECONDS`**
  before firing, because a room's bulbs confirm one by one and each
  confirmation is a separate status refresh (announced per light it was
  one entry per bulb), and names only lights that are on: a turn-off
  claims lights too, and announced it read "now setting 0 lights". A
  light coming back from unavailable isn't taken either, or every room
  announced itself after a restart.
- **The chart is one filled path, not a bar per sample.** It used to
  draw a `<rect>` per five-minute sample, which made every ramp a
  staircase. `curveFillSvg`/`simplifyPolyline`/`roundedTopEdge` in the
  card are exported and covered by `tests/unit/dashboard/test_curve_chart.py`. Only
  the GEOMETRY is simplified (the curve is piecewise linear, so most
  sample points are redundant as shape) - the gradient still carries a
  stop per sample, because colour moves continuously where brightness
  does not. Corner easing uses a quadratic whose **control point is the
  corner itself**, which is contained within the corner and so can only
  cut inward; do not replace it with an interpolating spline
  (Catmull-Rom and friends), which would overshoot the flat tops and
  draw brightness the schedule never asks for.
- **The docs site is how the card gets previewed without HA.**
  `docs/playground.html` loads the real
  `flare-curve-card.js` and feeds it the state shape a live
  HA would, with sliders for every schedule and curve value. Build the
  site and serve `docs/_preview/` (`.claude/launch.json`'s `docs-site`),
  which symlinks `flare` -> `_site` so the site's `/flare` baseurl
  resolves. Verify by reading the rendered
  shadow DOM directly; screenshot capture has been unreliable here.
  This replaced `dashboard/preview.html` + `generate_preview_data.py`
  and a `render_preview_svg.py` that rendered a static SVG for the
  README - all three deleted. The SVG renderer was a third copy of the
  chart's drawing logic and had already drifted from the card.
- **The blueprint trace viewer is also published to the docs site, main
  builds only, with no link to it anywhere.** `scripts/trace_viewer.py`
  is normally a local dev tool (a Python server backing `/api/yaml`,
  `/api/traces`, `/api/trace/<name>` for its own HTML). `--export DIR`
  writes the same three responses to disk once instead of serving them
  - this works with zero HTML changes because the page already fetches
  those three paths *relative to itself*, not as absolute `/api/...`
  URLs, so the identical file works unmodified whether "itself" is the
  server's own root or a docs-site subdirectory. `.github/workflows/
  docs.yml` runs `tests/functional/behaviour` fresh for the commit being built,
  then exports into `docs/trace-report/`, gated to `push` on `main`
  (same condition as `deploy`) so a PR's preview build doesn't pay for
  a full `pytest-homeassistant-custom-component` install for a page
  that build never serves. Deliberately front-matter-free (`tests/
  checks/test_docs_site.py`'s `_BUILD_DIRS` excludes it) so Jekyll copies it
  through as-is rather than theming it into the nav/search - "you have
  to already know the URL" is the point, at the user's own request.

## Testing

`pip install pytest pytest-homeassistant-custom-component && pytest`
from the repo root (see `CONTRIBUTING.md`). Python 3.14 - the floor
tracks whatever pytest-homeassistant-custom-component's pinned HA
release requires, since this only ever runs inside a real HA install.
`pip install -e ".[dev]"` does *not* work here and isn't used anywhere:
the flat repo layout isn't set up for setuptools discovery and doesn't
need to be, since nothing is distributed as a Python package. `dev` in
`pyproject.toml` is a versions reference only.

Three layers, laid out in CONTRIBUTING.md: `tests/unit/` (no running
Home Assistant), `tests/checks/` (the repo agreeing with itself) and
`tests/functional/` (a real HA via pytest-homeassistant-custom-component).
Shared helpers live in `tests/support/` and each functional directory's
`harness.py`; a test module never imports another test module.

- The component functional tests call `async_setup_entry` directly (or
  stub `frontend`) rather than `hass.config_entries.async_setup()`,
  which would load the large `home-assistant-frontend` package.
- `tests/functional/blueprint/` is the **only** layer that can catch a
  bug in the blueprint's own trigger/condition/action wiring -
  syntactically fine, wrong only at runtime. It mocks FLARE's services
  and asserts on what the blueprint calls; its classes mirror
  `docs/reference/blueprint.md`'s headings. `tests/functional/behaviour/` runs the
  real blueprint, schedule and services with only the bulbs faked, and
  asserts on the bulbs' final state. The day is pinned (sunset 18:00,
  clock from 19:00), and a phase change means moving the clock.
- `tests/functional/conftest.py` overrides the plugin's `hass_config_dir`
  to symlink this repo's `custom_components/` into a throwaway
  `tmp_path`, and copies the blueprint into its `blueprints/`.

**Practices this repo relies on, worth keeping:**

- **Mutation-verify every behavioural change**: break the fix
  deliberately, confirm *exactly* the intended test(s) fail, restore.
  This has repeatedly caught tests that passed for the wrong reason.
  Commit before mutating - `git checkout <file>` to undo a mutation
  will silently discard uncommitted work in that file.
- Timing tests use the `frozen_time` fixture
  (`freeze_time(..., real_asyncio=True)`, autouse in the blueprint and
  behaviour suites) and call `.tick()`/`.move_to()` on it. **Never open a nested `freeze_time`**, and never freeze without
  `real_asyncio=True`: plain `freeze_time` also mocks
  `time.monotonic()`, which is the clock asyncio's event loop uses for
  every timer, and a live loop does not tolerate that - it hangs, or
  fires timers wildly out of order.
- `async_fire_time_changed` fires the event that trips a `time_pattern`
  trigger but does **not** advance `now()`. A template comparing
  `now() - last_changed` needs frozen time ticked forward explicitly.
- Advance time relative to `utcnow()`, never to an absolute
  `.replace(minute=N)` - the latter can target a time in the past
  depending on real wall-clock alignment at run time.
- Two consecutive `hass.states.async_set` calls with identical values
  collapse into one `state_reported` event, and the second call's
  explicit `context=` is silently discarded. Echo a *slightly*
  different value when a test needs a real state change.
- **Waiting out real elapsed time in this harness does not work**, found
  while testing the since-removed jitter delay and kept because it will
  bite anything else that waits. Under the file-wide `frozen_time`, a
  nonzero `await asyncio.sleep(...)` in the test's own coroutine (not an
  HA-tracked task) hangs indefinitely - confirmed with a minimal repro.
  `hass.async_block_till_done()` intermittently returns early with the
  delayed call never having landed. And force-firing a delay's own timer
  with a second `async_fire_time_changed` can also match a freshly
  rescheduled `time_pattern` boundary, causing a spurious `mode: restart`
  - confirmed via the trace log showing an unwanted second "Restarting".
  A zero-length `await asyncio.sleep(0)` is safe (routed via `call_soon`,
  not `call_later`) and is the way to let a task start.
- **`async_fire_time_changed` can run a point-in-time timer ~0.1s
  early** - observed with the zone scheduler, a timer due at :01.0 fired
  when the clock was moved to :00.9. So `test_ticks.py` spaces zones 10s
  apart and checks well clear of each boundary, rather than asserting
  sub-second ordering.
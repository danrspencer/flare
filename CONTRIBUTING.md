# Contributing

Not needed just to install and use this — see [README.md](README.md) for that. This is for working on the
code itself.

## Repository layout

```
custom_components/flare/
    __init__.py    registers the four services against real HA state
    coordinator.py shared schedule computation behind the sensors/select
                   below - one instance per sensor added via the
                   integration's "Add Sensor" flow
    sensor.py      day-phase/curve sensors (see the integration reference)
    select.py      phase-override select (same reference)
    number.py      brightness/colour-temperature curve config, as
                   entities (same reference)
    time.py        schedule boundary times, as entities (same reference)
    switch.py      sticky-phase-override toggle, as an entity (same reference)
    curve.py       brightness/colour-temperature schedule + Kelvin -> RGB
    grouping.py    reachability, multiplier bucketing, tolerance checks,
                   externally-set protection, two-step/combined and
                   RGB-vs-colour-temp routing
    scenes.py      scene-coverage gap filling (apply a scene, then a
                   default for whatever it doesn't cover)
    write_tracking.py
                   which state device tracks each light, and what
                   context.id this integration last wrote it with - the
                   record grouping.py's externally_set() compares
                   against. Deliberately not persisted: the claims live
                   on each state device's tracking entity and die with a
                   restart, which leaves every light manageable
    manifest.json, config_flow.py, services.yaml, strings.json,
    translations/  standard HA integration/HACS scaffolding
    brand/icon.png, brand/icon@2x.png
                   the integration's icon (256/512, alpha) - HA reads
                   this directly from the integration's own folder
                   (since HA 2026.3.0), no external submission needed
    www/flare-curve-card.js
                   the day-phase/curve dashboard card
    Served and auto-loaded by the integration itself (see
    __init__.py's async_setup) - it ships and updates with the
    integration, no manual Lovelace resource registration needed
    curve.py, grouping.py, and scenes.py are pure Python, no Home
    Assistant dependency - testable directly, and usable from anywhere
    that wants the math without the HA service/sensor wrapper around
    it. __init__.py, coordinator.py, sensor.py, select.py, number.py,
    time.py, switch.py, button.py, and write_tracking.py are the only
    files that touch `hass`.

hacs.json
    HACS repository metadata for the integration.

brand/
    generate_icon.py  renders brand/icon.svg from the real curve module
                      (same pattern as the dashboard preview generators):
                      the icon is the day's actual brightness/colour
                      curve as bars. Design/authoring tooling only - the
                      PNGs HA actually reads live at
                      custom_components/flare/brand/
                      (rendered from icon.svg, not scripted yet)
    icon.svg          the icon's source of truth, regenerate with
                      generate_icon.py after changing the curve defaults

blueprints/automation/danspencer/flare.yaml
    The automation blueprint: triggers, conditions, target resolution,
    and the action sequence (which service to call, with what target).

dashboard/
    house-settings-card.yaml   the curve card alone, to drop into a view.
                               The fuller section is built at runtime by
                               the view strategy in
                               custom_components/flare/www/ - see
                               flare-section.js, not committed as YAML.

tests/
    pytest suite for curve.py, grouping.py, and scenes.py.

docs/
    index.md          the pitch, and what the four phases are for
    installation.md   quickstart: HACS, blueprint, dashboard card
    dashboard.md      how to add the view strategy, and what it builds
    playground.html   the interactive curve, running the real card
    blueprint.md      full feature/input reference for the blueprint
    advanced/         power-user reference: services, scene handoff,
                      building without the blueprint
```

Triggers, conditions, and target resolution stay in the blueprint; Home Assistant `condition:` blocks can't call
a service, so anything a condition depends on has to remain template-based. Multiplier bucketing, tolerance
checks, and transition routing are implemented in the integration and unit tested. See `CLAUDE.md` for further
implementation notes, including the (fairly involved) history of getting a custom integration to load correctly
at all.

## Previewing the dashboard card

The [curve playground](https://danrspencer.github.io/flare/playground/) on this site renders the real card against synthetic data, with no
Home Assistant instance involved — the page loads
`custom_components/flare/www/flare-curve-card.js` itself and feeds it the state
shape a live Home Assistant would. Build the site locally (below) to exercise a change to the card.

## The documentation site

Everything except `README.md` lives here, published at
<https://danrspencer.github.io/flare/> from `docs/` and built with Jekyll and the `just-the-docs`
theme by `.github/workflows/docs.yml`. Pull requests build the site but don't publish it; only a push to `main`
deploys.

```bash
cd docs && bundle install && bundle exec jekyll build
```

To preview locally, note the site has a `baseurl` of `/flare`, so `_site` has to be served one
directory *below* the web root or every asset 404s. `.claude/launch.json`'s `docs-site` entry handles that via
`docs/_preview/`, which symlinks `flare` → `_site`:

```bash
python3 -m http.server 8935 --directory docs/_preview
# open http://localhost:8935/flare/
```

Two things about it are less obvious than they look:

- **Jekyll 4, not the `github-pages` gem.** The reference pages contain Home Assistant Jinja in their YAML
  examples, and Liquid uses the same `{{ }}` delimiters. Jekyll's default lax filter handling renders an unknown
  filter as an empty string, so those examples would publish blank with no build error. Each affected page sets
  `render_with_liquid: false`, which is a Jekyll 4 feature that GitHub Pages' own (Jekyll 3) builder doesn't
  have. Those pages therefore can't use the `relative_url` filter either, so their links are plain relative
  paths — which need no baseurl to be correct.

- **The playground runs the real dashboard card.** `docs/playground.html` loads the actual
  `flare-curve-card.js`, copied in by the workflow rather than committed twice. The schedule maths
  behind the sliders is `docs/assets/js/curve.js`, a port of `curve.py`; `tests/test_curve_js_parity.py` runs
  both it and the card itself under node against a grid of inputs and fails if either drifts from `curve.py`.

Every page needs front matter — Jekyll only renders a file as a *page* if it has a literal front matter block,
and copies it through verbatim otherwise. `tests/test_docs_site.py` checks that.

## Testing

```bash
pip install pytest pytest-homeassistant-custom-component
pytest
```

Two layers, both under `tests/`:

- `test_curve.py`/`test_grouping.py`/`test_scenes.py` - pure logic, no Home Assistant dependency at all.
  `tests/fakes.py` provides a fake state/registry lookup, and `tests/conftest.py` imports `curve.py`/`grouping.py`
  directly (bypassing the integration's `__init__.py`, which does need `homeassistant` — see its own comment for
  why).
- `tests/integration/` - real Home Assistant, via
  [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component).
  `test_services.py` exercises the actual registered services (`__init__.py`, `write_tracking.py`) end to end;
  `test_state_devices.py` covers scope resolution and the per-scope entities that hold the claims;
  `test_blueprint.py` loads the real blueprint file into a test automation and fires real triggers - the only
  place bugs living in the blueprint's own trigger/condition/action wiring can be caught at all, as opposed to
  pure YAML/template checks that are syntactically fine but wrong at runtime (see its own module docstring for
  the two real incidents this suite exists to guard against).

This is also why `pyproject.toml`'s `requires-python` floor is 3.14, not something lower: pytest-homeassistant-
custom-component pins a specific Home Assistant release, which itself pins the Python it needs — since this repo
only ever runs inside a real HA install, tracking that floor is the right target, not a separate, broader
compatibility matrix. CI (`.github/workflows/tests.yml`) runs the full suite on push and PR.

## Status

The pure-Python core (`curve.py`, `grouping.py`, `scenes.py`) and the integration wrapping it as HA services
are both written, unit tested, and **installed via HACS and confirmed working against a live Home Assistant
instance** — `compute_lighting_groups`/`compute_curve`/`compute_scene_coverage` verified registered and
functionally correct, the blueprint's full compute-groups-then-turn-on-lights path exercised end to end
against real hardware, the day-phase/curve sensors deployed and iterated on live (multi-sensor subentries,
per-sensor devices), `apply_lighting`'s RGB colour support (`prefer_rgb_color`) confirmed live end to end -
both the routing decision (a real bulb correctly bucketed by its actual `supported_color_modes`) and the
`light.turn_on` dispatch itself (a real bulb landing in `xy` colour mode with the expected `rgb_color`) - and
`apply_lighting`'s context.id-based override protection confirmed live too: a foreign write is correctly left
alone, our own write correctly isn't, and `force: true` correctly writes through regardless. See CLAUDE.md's "Current status" section for the full rundown.

## Writing the docs

`DOCUMENTATION.md` has the rules and the lexicon - who each page is for,
what belongs on a site page versus in a code comment, and the one
correct word for each concept. Read it before changing anything under
`docs/`.

The short version: site pages are for end users, they describe what is
true now rather than what changed, reference tables come before prose,
headings are the reader's question, and inputs are named exactly as the
UI labels them.

## Cutting a release

HACS reads the version out of `manifest.json`, not out of the tag, so the two must
agree or the version people see installed isn't the one they downloaded. That's
checked twice: `tests/test_version.py` runs on every PR, and
`.github/workflows/release.yml` re-checks at tag time and refuses to publish a
mismatch.

### Beta by default

**A release is tagged as a beta unless it has been explicitly promoted.**
`vX.Y.Z-beta.N` is the normal thing to push; `vX.Y.Z` is a deliberate
decision someone makes about a build that has had some use.

That is the whole point of the channels: FLARE has beta testers now, so
a stable tag reaches other people's houses. Betas let this iterate at
the pace it actually iterates at without that.

Promoting means moving the three versions below to the bare `X.Y.Z` and
tagging it. The release workflow refuses a prerelease stamp on a stable
tag, so a half-done promotion fails the build rather than shipping a
beta blueprint to everyone.

### Two channels

The tag decides, and nothing else does:

| Tag | Published as | Who sees it |
|---|---|---|
| `v0.16.0` | a normal release | everyone |
| `v0.16.0-beta.1` | a GitHub **pre-release** | only people who opted in |

HACS filters on GitHub's own pre-release flag rather than on the tag text — see
`custom_components/hacs/repositories/base.py`, which skips a release when
`release.prerelease and not prerelease` — and that filter is driven by the
per-repository **Pre-release** switch HACS creates for each downloaded repository.
So a beta is invisible by default and arrives as an ordinary update to anyone who
turned that switch on. No second branch, no second repository.

`hacs.json` sets `hide_default_branch: true` so nobody can sidestep the channels by
downloading `main` directly.

To follow the betas on your own instance, turn on the **Pre-release** switch for
FLARE under the HACS integration's entities. It ships registry-disabled, so you'll
need to enable the entity before you can turn it on.

### Steps

1. Bump `version` in `custom_components/flare/manifest.json`.
   Breaking changes bump the **minor** while below 1.0. A beta carries the version it
   is working toward plus a suffix — `0.16.0-beta.1` — and that is the default; see
   **Beta by default** above.
2. Add a `## [x.y.z] - YYYY-MM-DD` section to `CHANGELOG.md`, calling out anything
   breaking explicitly — this integration ships in two halves (integration and
   blueprint) that deploy separately, so "you must deploy both" is a real
   instruction, not boilerplate.

   Betas are matched on their **base** version, so `0.16.0-beta.3` is described by the
   `## [0.16.0]` section. Write that section once, before the first beta, and keep
   adding to it. A section per beta would make the changelog a build log.
3. **If the blueprint changed**, bump `BLUEPRINT_VERSION` in
   `custom_components/flare/blueprint_version.py` and the matching line in the
   blueprint's own `description` to the version you're about to release. A pull
   request touching `blueprints/` without moving the stamp fails CI, and a stable
   release whose stamp still carries a beta suffix - or names a tag that was never
   cut - fails the release workflow. Both matter because the stamp is the URL the
   out-of-date repair's Fix button downloads from.
4. Merge, then tag the merge commit and push it:

   ```bash
   git tag v0.16.0-beta.1 && git push origin v0.16.0-beta.1
   ```

   Promote when it's had some use, by tagging the same content without the suffix:

   ```bash
   git tag v0.16.0 && git push origin v0.16.0
   ```

The workflow validates and creates the GitHub release, marking it a pre-release when
the tag carries a suffix.

**Merge, then verify, then tag — as three separate steps.** Chaining them means a
failed merge still tags, which has happened: a `wip` commit went out as a release
because the tag was chained onto a merge that hadn't landed.

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

- **A hidden trace report is published at `/trace-report/`, main builds only.** `.github/workflows/docs.yml`
  runs `tests/behaviour` fresh for the commit being built, then `scripts/trace_viewer.py --export
  docs/trace-report` (also runnable locally as `mise run trace-export`) writes a static snapshot of the
  interactive trace viewer — no Python server needed, since the exported `index.html` fetches its data as
  plain files (`api/yaml`, `api/traces`, `api/trace/*.json`) relative to its own location rather than from
  a live server. It carries no nav entry, isn't in the search index, and nothing else on the site links to
  it — reachable only to someone who already has the URL. Gated to `push` on `main` (the same condition
  `deploy` uses below) so a PR's docs preview build doesn't pay for a full
  `pytest-homeassistant-custom-component` install just to produce a page that build never serves anyway.

Every page needs front matter — Jekyll only renders a file as a *page* if it has a literal front matter block,
and copies it through verbatim otherwise. `tests/test_docs_site.py` checks that (`docs/trace-report/` is
excluded from that check the same way `_site`/`_preview`/etc. are — it's deliberately front-matter-free).

## Testing

Via [mise](https://mise.jdx.dev) (`mise.toml` pins Python 3.14 and manages a `.venv`):

```bash
mise run install   # pip install pytest pytest-homeassistant-custom-component, into .venv
mise run test       # pytest
mise run test:behaviour   # tests/behaviour only, captures blueprint traces into trace-dumps/
mise run traces      # render captured traces (run test:behaviour first)
```

Without mise:

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

## Releases

Three tiers, each following a branch or a tag rather than a person deciding:

| Tier | Who it is for | Where it comes from | HACS |
|---|---|---|---|
| **dev** | you, churning | the `dev` branch | not offered - see [Following dev in HACS](#following-dev-in-hacs) |
| **beta** | testers who don't mind instability | `vX.Y.Z-beta.N` pre-releases | turn on FLARE's **Pre-release** switch |
| **release** | everyone else | `vX.Y.Z` releases | the default |

Pull requests target `dev`. Nothing about a release is typed by hand: not the
version, not the tag, not the blueprint stamp.

### Cutting a beta

Push `dev` to `main`:

```bash
git push origin dev:main
```

That has to be a fast-forward. `main`'s ruleset requires linear history, so a squash or rebase
merge from a pull request would give it new commits that `dev` never sees.

`.github/workflows/cut-beta.yml` then runs the test suite on that commit and, if it
passes, cuts `vX.Y.Z-beta.N` as a GitHub pre-release. **`X.Y.Z` is whatever the top
`## [x.y.z]` heading of `CHANGELOG.md` says** - that heading is the one place anyone
says what version is being worked toward, and it is already required, so write it
before the first change that should ship. Breaking changes bump the **minor** while
below 1.0, and say so in the section, because this ships in two halves (integration
and blueprint) that deploy separately.

A push cuts nothing, and stays green, when the top heading is a version that has already
been released, or when nothing under `custom_components/` or `blueprints/` changed since
the last beta. So docs, test and CI changes can go to `main` freely; a change that should
ship but forgot its heading is the thing to watch for. A heading *below* an existing
beta fails the run - that would reach testers as a downgrade.

### Promoting a beta

Nothing to do. `.github/workflows/promote.yml` runs daily and releases the newest beta
of a version once it is **seven days old**. It is judged per version: a fresh
`0.17.1-beta.1` does not hold back a week-old `0.17.0-beta.4`, but a newer beta of the
*same* version restarts that version's clock, since what ships is that beta's contents. It
will never promote a version at or below the highest existing release, so tags made out of
order cannot ship a downgrade.

**To hold a release back**, open an issue labelled `release-blocker`. While any is
open the promotion is refused; close it and the next daily run carries on. The issue is
also where "why isn't this shipping" gets answered.

**To promote early**, run the workflow with `force` ticked:

```bash
gh workflow run promote.yml -f force=true
```

That skips the seven days but not the `release-blocker` check.

### How a release is built

The source carries a placeholder (`0.0.0-dev`) as the manifest's version, the blueprint
stamp and `BLUEPRINT_VERSION`. HACS reads the version out of the `manifest.json` inside
the tag it downloads, so `scripts/release.py` builds each release **on the side**: a commit
on top of the source commit with the real version written into those three places,
tagged, and reachable from no branch. Nothing is committed to `dev` or `main`, so they
never drift apart over version bumps. A release is the same source commit as the beta it
came from, with different numbers written in - which is what "promote" means.

The blueprint stamp is worked out, not bumped: if the blueprint is unchanged since the
previous release it keeps that release's stamp, so a release touching only Python doesn't
tell everyone to re-import an identical file.

GitHub shows a "does not belong to any branch" banner on these commits. That is expected.
The release commit's message records its `Source:` commit.

A development build carries the placeholder version and serves the front-end files from a
URL derived from their content rather than from the version, since the version never
changes there. The blueprint repair has no special handling for it: import the blueprint from
the same commit as the integration and both carry the placeholder, so they agree. Update it
with a direct import rather than the repair's Fix button.

### Two channels

The tag decides, and nothing else does:

| Tag | Published as | Who sees it |
|---|---|---|
| `v0.16.0` | a normal release | everyone |
| `v0.16.0-beta.1` | a GitHub **pre-release** | only people who opted in |

HACS filters on GitHub's own pre-release flag rather than on the tag text - see
`custom_components/hacs/repositories/base.py`, which skips a release when
`release.prerelease and not prerelease` - and that filter is driven by the
per-repository **Pre-release** switch HACS creates for each downloaded repository.
So a beta is invisible by default and arrives as an ordinary update to anyone who
turned that switch on. Enable the entity first: it ships registry-disabled.

### Following dev in HACS

HACS has no dev channel. Its download dialog (2.x) lists only a repository's GitHub
releases, and shows pre-releases only while the **Pre-release** switch is on. The docs
still describe offering the default branch as well, but that was removed in 2.0
([hacs/integration#4009](https://github.com/hacs/integration/issues/4009), closed as not
planned), and a repository's default branch is only tracked by commit when it publishes no
releases at all. So changing the default branch or `hide_default_branch` does nothing here.

What exists: HACS's `hacs/repository/download` websocket call takes any string as its
`version`, and the download code falls back from `refs/tags/<name>.zip` to
`refs/heads/<name>.zip`, so naming `dev` should install that branch. It is not offered in the
UI and no update is ever reported for it, so it is a manual step each time. That has not been
tried against this integration; until it has, treat it as unverified and follow the beta
channel for anything you want to see through HACS.

### Tagging by hand

Still possible, for a hotfix or when a workflow is unavailable. Set the three versions
yourself in a checkout, tag it, and push the tag: `.github/workflows/release.yml` checks
the tag against the manifest, that the blueprint stamp suits the channel and names a tag
that exists, and that the changelog has a section for it, then publishes. (A tag pushed by
the workflows above does not trigger it - GitHub does not let a workflow's own events start
another - and needs no such check, since `scripts/release.py` wrote the version and the tag
together.)

**Merge, then verify, then tag - as separate steps.** Chaining them means a failed merge
still tags, which has happened: a `wip` commit went out as a release because the tag was
chained onto a merge that hadn't landed.

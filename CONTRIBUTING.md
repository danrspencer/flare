# Contributing

Not needed just to install and use this — see [README.md](README.md) for that. This is for working on the
code itself.

## Repository layout

```
custom_components/flare/
    __init__.py, config_flow.py, repairs.py, logbook.py, const.py
                   the integration itself: setting up the three config
                   entries, the blueprint repairs, the logbook
                   descriptions, the dashboard front-end files
    subentry_flows.py, options_flow.py
                   adding and reconfiguring schedules, zones and
                   flares; the Zones entry's options
    area_setup.py  setting up an area: a zone, a room automation written
                   to automations.yaml, and a flare
    sensor.py, select.py, number.py, time.py, switch.py, button.py,
    event.py, light.py
                   the entities. Home Assistant requires platform
                   modules at this level, so they can't live in a folder
                   (see the integration reference for what each is)

    schedule/      what the lights should look like
        curve.py         brightness/colour-temperature schedule, Kelvin -> RGB
        coordinator.py   the schedule computation behind the schedule
                         entities - one per sensor added via "Add Sensor"
        transfer.py      a schedule as YAML, for export and import
    zone/          zones: who owns a light, and when each zone ticks
        override_protection.py
                         classify_state(): controlled / overridden /
                         settling / untracked / off / unavailable
        claims.py
                         the claims: what context.id and target this
                         integration last wrote each light with. They live
                         on each zone's entity and are restored across a
                         restart
        instance.py      the zone device itself (one per room, usually)
        ticker.py        fires each zone's tick in turn, a gap apart
    flares/        flares: a light over each room's automation (the entity
                   itself is light.py)
        automation.py    reads an automation's lights and zone from its
                         blueprint inputs
        bare.py          what counts as a bare turn-on, which runs the
                         automation
        instance.py      the flare device itself
    services/      the services, and the planning behind them
        handlers.py      the zone services (lighting and claims), registered
                         against real HA state
        schedules.py     export_schedule / import_schedule, registered for the
                         domain rather than by either entry
        grouping.py      reachability, brightness bucketing, tolerance checks,
                         override protection, two-step/combined and
                         RGB-vs-colour-temp routing
        scenes.py        scene-coverage gap filling (apply a scene, then a
                         default for whatever it doesn't cover)
        two_step.py      which bulb models need two-step transitions

    blueprints/flare.yaml
                   the automation blueprint: triggers, conditions, target
                   resolution, and the action sequence (which service to
                   call, with what target). Ships with the integration;
                   the blueprint repairs install and update it from here
    manifest.json, services.yaml, strings.json, translations/
                   standard HA integration/HACS scaffolding (services.yaml
                   has to sit at this level)
    brand/icon.png, brand/icon@2x.png
                   the integration's icon (256/512, alpha) - HA reads
                   this directly from the integration's own folder
                   (since HA 2026.3.0), no external submission needed
    www/           the dashboard: the strategies and the sections they
                   build, the curve, Clear, Activity and transfer cards,
                   the slider card features, and the flare:logo sidebar
                   icon. Entities are found by device and role (their
                   translation keys), never by entity ID. Served and auto-loaded by
                   the integration itself (see __init__.py's async_setup),
                   so it ships and updates with the integration with no
                   manual Lovelace resource registration

The four folders are grouped by concept rather than by how something is exposed, because the
schedule and the claims are each exposed through both entities and services - so neither could
live with either. Imports run one way: `schedule/`, `zone/` and `flares/` import nothing but
`const.py`, `services/` may use `schedule/` and `zone/`, and everything at the package root may
use all of them.
`tests/checks/test_layering.py` enforces it.

`schedule/`, `zone/` and most of `services/` are never handed a `hass` - testable with plain
values or fakes. (`curve.py` and `override_protection.py` each import one colour helper from
`homeassistant.util.color`.) `services/handlers.py`, the entity platforms and the rest of the
package root are the Home Assistant side: they take `hass` or an entry, and read or write real state.

hacs.json
    HACS repository metadata for the integration.

brand/
    generate_icon.py  draws the icon from the real curve module (the
                      day's brightness/colour curve as bars) and writes
                      icon.svg plus the PNGs HA serves from
                      custom_components/flare/brand/. Rerun it after
                      changing the curve defaults

tests/
    unit/        no running Home Assistant: the pure modules, the
                 dashboard JS (under node), and scripts/
    checks/      consistency of the repo itself: docs, versions,
                 services.yaml, import layering
    functional/  a real Home Assistant instance: the integration,
                 the blueprint (services mocked), and behaviour
                 (end to end, only the bulbs faked)
    support/     shared paths, fakes and the node runner

docs/
    index.md          the pitch, and what the four phases are for
    installation.md   quickstart: HACS, blueprint, flares, dashboard
    dashboard.md      how to add the view strategy, and what it builds
    playground.html   the interactive curve, running the real card
    guides/           how to do more: examples, the blueprint's template
                      inputs, scenes, voice assistants and HomeKit,
                      building without the blueprint
    reference/        the technical docs: the blueprint's inputs,
                      schedules, zones, flares and services
```

Triggers, conditions, and target resolution stay in the blueprint; Home Assistant `condition:` blocks can't call
a service, so anything a condition depends on has to remain template-based. Brightness bucketing, tolerance
checks, and transition routing are implemented in the integration and unit tested. See `CLAUDE.md` for further
implementation notes.

## Previewing the dashboard card

The [curve playground](https://danrspencer.github.io/flare/playground/) on this site renders the real card against synthetic data, with no
Home Assistant instance involved — the page loads
`custom_components/flare/www/flare-curve-card.js` itself and feeds it the state
shape a live Home Assistant would. Build the site locally (below) to exercise a change to the card.

## The documentation site

Everything except `README.md` lives here, published at
<https://danrspencer.github.io/flare/> from `docs/` and built with Jekyll and the `just-the-docs`
theme by `.github/workflows/docs.yml`. Pull requests build the site but don't publish it.

The site keeps a version of the docs per release, with a picker in the header:

- `/flare/` is the latest release, published by `promote.yml` along with the release, which is also kept
  at `/flare/v/<version>/`.
- `/flare/beta/` is the newest beta, published by `cut-beta.yml` on every push to `main`, and offered only
  while it's newer than the latest release. Until the first release it's the root too.

Each version is built once and kept, built, on the `docs-site` branch; `scripts/docs_site.py` puts a new
build in place and adds the picker (`docs/_versions/picker.js`) to every page, and the whole branch is
what Pages serves. To republish a release's docs, run the docs workflow by hand with its tag.

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

- **A hidden trace report is published at `/trace-report/`, beta builds only.** `.github/workflows/docs.yml`
  runs `tests/behaviour` fresh for the commit being built, then `scripts/trace_viewer.py --export
  docs/trace-report` (also runnable locally as `mise run trace-export`) writes a static snapshot of the
  interactive trace viewer — no Python server needed, since the exported `index.html` fetches its data as
  plain files (`api/yaml`, `api/traces`, `api/trace/*.json`) relative to its own location rather than from
  a live server. It carries no nav entry, isn't in the search index, and nothing else on the site links to
  it — reachable only to someone who already has the URL. Beta builds only, so a PR's docs build doesn't pay
  for a full
  `pytest-homeassistant-custom-component` install just to produce a page that build never serves anyway.

Every page needs front matter — Jekyll only renders a file as a *page* if it has a literal front matter block,
and copies it through verbatim otherwise. `tests/checks/test_docs_site.py` checks that (`docs/trace-report/` is
excluded from that check the same way `_site`/`_preview`/etc. are — it's deliberately front-matter-free).

## Testing

Via [mise](https://mise.jdx.dev) (`mise.toml` pins Python 3.14 and manages a `.venv`):

```bash
mise run install   # pip install pytest pytest-homeassistant-custom-component, into .venv
mise run test              # everything
mise run test:unit         # tests/unit and tests/checks - fast, no Home Assistant instance
mise run test:functional   # tests/functional
mise run test:behaviour    # tests/functional/behaviour only; captures blueprint traces into trace-dumps/
mise run traces      # render captured traces (run test:behaviour first)
```

Without mise:

```bash
pip install pytest pytest-homeassistant-custom-component
pytest
```

Three layers under `tests/`:

- `unit/` - no running Home Assistant. `component/` tests the pure modules (curve, grouping, override
  protection, scenes, two-step, the blueprint stamp), `dashboard/` runs the front-end modules under node,
  and `scripts/` covers the release and CI-summary scripts.
- `checks/` - the repository agreeing with itself: docs pages and anchors, versions, services.yaml, the
  static imports and the package layering.
- `functional/` - a real Home Assistant, via
  [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component).
  `component/` covers the integration (services, claims, zones, schedules, config flows, repairs);
  `blueprint/` runs the real blueprint with FLARE's services mocked, to test what it decides to call;
  `behaviour/` runs the real blueprint, schedule and services end to end on a pinned day, with only the bulbs
  faked, and asserts on the state the bulbs end up in.

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
below 1.0, and say so in the section.

A push cuts nothing, and stays green, when the top heading is a version that has already
been released, or when nothing under `custom_components/` changed since
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

The manifest's version in source is a placeholder (`0.0.0-dev`). HACS reads the version out of the `manifest.json` inside
the tag it downloads, so `scripts/release.py` builds each release **on the side**: a commit
on top of the source commit with the real version written into those three places,
tagged, and reachable from no branch. Nothing is committed to `dev` or `main`, so they
never drift apart over version bumps. A release is the same source commit as the beta it
came from, with different numbers written in - which is what "promote" means.

The blueprint is versioned with FLARE: its stamp (and `BLUEPRINT_VERSION`) is always the
release's own version, written by the same script. So every release, betas included, raises
the out-of-date-blueprint repair for anyone using it, even if the blueprint itself did not
change.

GitHub shows a "does not belong to any branch" banner on these commits. That is expected.
The release commit's message records its `Source:` commit.

Shipped code has no special handling for a development build, on purpose. One thing follows:
the blueprint's stamp in source is whatever it last held, so a changed blueprint raises no
repair. Copy the
changed file over your installed `blueprints/automation/flare/flare.yaml` yourself.

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
the tag against the manifest, that both blueprint stamps equal the tag, and that the
changelog has a section for it, then publishes. (A tag pushed by
the workflows above does not trigger it - GitHub does not let a workflow's own events start
another - and needs no such check, since `scripts/release.py` wrote the version and the tag
together.)

**Merge, then verify, then tag - as separate steps.** Chaining them means a failed merge
still tags, which has happened: a `wip` commit went out as a release because the tag was
chained onto a merge that hadn't landed.

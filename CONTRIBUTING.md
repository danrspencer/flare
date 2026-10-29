# Contributing

Not needed just to install and use this — see [README.md](README.md) for that. This is for working on the
code itself. For how the code works inside, with diagrams, start at [architecture/](architecture/README.md).

## Repository layout

```
custom_components/flare/
    __init__.py, config_flow.py, repairs.py, logbook.py, const.py
                   the integration itself: setting up the three config
                   entries, the blueprint repairs, the logbook
                   descriptions, the dashboard front-end files
    subentry_flows.py, options_flow.py
                   adding and reconfiguring schedules and flares; the
                   Settings entry's options
    area_setup.py  setting up an area: a room automation written to
                   automations.yaml, and flares for the rooms picked
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
    tracking/      who owns a light, and when each area ticks
        override_protection.py
                         classify_state(): controlled / overridden /
                         mismatched / untracked / off / unavailable
        claims.py
                         the claims: what context.id and target this
                         integration last wrote each light with, and each
                         room's lights, saved in HA's storage
                         (.storage/flare.claims) across a restart
        matching.py      what a light shows, against what was asked for
        ticker.py        fires each area's tick in turn, a gap apart
    flares/        flares: a light over each room's automation (the entity
                   itself is light.py)
        automation.py    reads an automation's lights from its blueprint
                         inputs
        bare.py          what counts as a bare turn-on, which runs the
                         automation
        instance.py      the flare device itself
    services/      the services, and the planning behind them
        handlers.py      the lighting and claims services, registered
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
live with either. Imports run one way: `schedule/`, `tracking/` and `flares/` import nothing but
`const.py`, `services/` may use `schedule/` and `tracking/`, and everything at the package root may
use all of them.
`tests/checks/test_layering.py` enforces it.

`schedule/`, `tracking/` and most of `services/` are never handed a `hass` - testable with plain
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
                      schedules, override protection, flares and
                      services
```

Triggers, conditions, and target resolution stay in the blueprint; Home Assistant `condition:` blocks can't call
a service, so anything a condition depends on has to remain template-based. Brightness bucketing, tolerance
checks, and transition routing are implemented in the integration and unit tested. See `CLAUDE.md` for further
implementation notes.

## A sandbox Home Assistant

To try FLARE end to end without touching a real house, run a throwaway Home Assistant with this checkout's FLARE
in it:

```bash
mise run sandbox
```

It opens on <http://127.0.0.1:8124>, already logged in, with no FLARE set up yet, so the first thing to do is
**Add Integration → FLARE**, just as a new user would. To get back to a brand-new house, run:

```bash
mise run sandbox:reset
```

- `mise run sandbox:install` (which both run first) installs Home Assistant into `.venv-sandbox/`, with the
  Python and uv from `mise.toml`. By default that's the oldest release FLARE supports, `hacs.json`'s
  `homeassistant`. To try another, set `SANDBOX_HA_VERSION` (`SANDBOX_HA_VERSION=2026.11.0 mise run sandbox`).
  It reinstalls only when the version changes, and the first install takes a few minutes. A house saved by a
  newer release may not load in an older one; use `sandbox:reset` after going back.
- The port is `SANDBOX_PORT` in `mise.toml`'s `[env]`.
- The house is `sandbox/configuration.yaml`'s `sandbox_house:` block: floors and rooms, their icons, and how
  many bulbs each room has. Every room also gets a sensor with an occupancy `binary_sensor` and a **Presence**
  switch to set it, so you walk into the kitchen by turning on `switch.kitchen_sensor_presence`, and an
  illuminance `sensor` with a **Daylight** number to set it (0 lx until you move it). Bulbs (`light.kitchen_bulb_1` ...)
  take brightness and colour temperature and keep their state across restarts. Each bulb's **Power** switch
  (`switch.kitchen_bulb_1_power`) and its room's **Wall switch** (`switch.kitchen_wall_switch`) cut its power,
  making it unavailable; when power comes back it boots on at 255 and 2700K and ignores commands for a second,
  as a real bulb does. A room with `tv: true` also
  gets a TV that only turns on and off (`media_player.living_room_tv`). The fake devices are
  `sandbox/custom_components/sandbox_house/`.
- Home Assistant runs from `.sandbox/`, rebuilt from `sandbox/` on every start (FLARE and the fake house are
  symlinked in). Restart it to pick up a change to FLARE's Python, from the terminal or from Home Assistant's
  own Restart. Whatever stops Home Assistant, the sandbox starts it again; only stopping `mise run sandbox`
  itself (Ctrl-C) ends it.
- The owner account is `sandbox` / `sandbox`, for when you need to log in from another device.
- FLARE is linked in, not installed through HACS, so HACS isn't part of what the sandbox tests. For that, use
  the HACS sandbox below.

### Installing through HACS

To try installing FLARE as a user does, from the HACS store, run:

```bash
mise run sandbox:hacs
```

It's a second house, kept in `.sandbox-hacs/`, with HACS installed and no FLARE at all. Add HACS under
**Settings → Devices & services** (it signs in to GitHub with a device code), then find FLARE in HACS and
download a release. To start again from a brand-new house, run `mise run sandbox:hacs:reset`.

- It installs whatever HACS downloads from GitHub, not this checkout, so a change has to be pushed (and
  released, for HACS to offer it) before it shows up here.
- The HACS release is `SANDBOX_HACS_VERSION` in `mise.toml`'s `[env]`. HACS is copied in fresh on every
  start, so updating it from its own UI lasts only until the next start.
- It uses the same port as the other sandbox, so run one at a time.

### Recording walkthroughs

With the sandbox stopped, run:

```bash
mise run sandbox:record
```

It records two videos:

- `setup.mp4` adds FLARE with one schedule per floor, adds its dashboard, shows the automations it made, and ends
  on the dashboard.
- `customise.mp4` carries on from there. It adjusts both schedules with their graphs in view, gives the Bedroom a
  nightlight, and gives the Living Room a Scene Template that picks a movie-night scene while the TV is on in the
  evening, with its result shown in the template preview.

It starts its own brand-new sandbox, clears the notifications and repairs a new install shows, and plays each video
in a fresh browser at 1280×1000, tall enough for a schedule's graph and all its sliders, with a visible pointer.

Once both have recorded, it writes what the docs and README show, ready to commit:

- `docs/assets/video/setup.mp4` and `customise.mp4`, on the Quickstart and Guides pages, each with a still frame
  (`.jpg`) shown before it plays;
- `docs/assets/img/setup.gif`, at the top of the README. GitHub and HACS show images in a README but not video,
  and the README links it from `main`, so it shows once merged.

Re-record whenever setup or the dashboard changes, and commit the new files. If a scene fails, nothing is written,
and a screenshot of the failed step is left in `sandbox/recordings/` with the working files. The scenes are in `scripts/sandbox_record.py`: re-run it whenever the setup changes. The first run installs
Playwright, its Chromium and ffmpeg into `.venv-record/`.

## Translations

FLARE has two sets of text, and a language needs both:

- **The integration's** (setup, options, repairs): `custom_components/flare/strings.json` is the English, copied to
  `translations/en.json`; a language is `translations/<code>.json` with the same keys.
- **The dashboard's**: `custom_components/flare/www/translations/en.js`; a language is `<code>.js` beside it, added
  to `LANGUAGES` in `www/flare-i18n.js`.

`tests/checks/test_translations.py` and `tests/unit/dashboard/test_i18n.py` fail if a language is missing a key, has
one English no longer uses, or fills in different placeholders, so change a translation whenever its English
changes. German came from @stefanr09 in [#301](https://github.com/danrspencer/flare/issues/301).

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
- A release's docs come from `main`, not its tag, while nothing under `custom_components/` has changed
  since the release (`scripts/release.py docs-source`). So a docs fix after the last beta reaches the
  latest release: `cut-beta.yml` republishes it on such a push, as well as the beta.
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
  `flare-curve-card.js`, copied in by the workflow rather than committed twice, with `flare-i18n.js` and
  `translations/`, which it imports its text from. Copy those three into `docs/assets/js/` to preview the
  playground locally. The schedule maths
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
  `component/` covers the integration (services, claims, rooms, schedules, config flows, repairs);
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

A push cuts nothing, and stays green, when nothing under `custom_components/` changed
since the last beta, or since the release its top heading names. So docs, test and CI
changes can go to `main` freely. A change under `custom_components/` while the top heading
is a version that's already out fails, on the pull request (the `changelog` job in
`tests.yml`, `scripts/release.py check`) and again in the beta job: add a section for the
next version. A heading *below* an existing beta fails too - that would reach testers as a
downgrade.

Each pull request gets a comment from `release-preview.yml` naming the beta it would ship in if
merged now, with that beta's release notes, or saying why it would ship in none. It's updated
on every push.

Release notes are GitHub's generated list of merged pull requests, minus any labelled `repo`
(`.github/release.yml`). That label is applied automatically, from `.github/labeler.yml`, to
a pull request whose every file is repo plumbing - CI, scripts, tests, contributor docs - and
removed again if it later touches anything else. Docs and README changes stay in. To leave
out any other pull request, label it once it's merged; before then the next push re-checks it.

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

### Patching the current release

A fix for the current release, say `v1.2.0`, can ship as `v1.2.1` straight away, with no beta
and without whatever is in beta on `main`. It goes through a release branch cut from the
release's tag:

```bash
git switch -c release/1.2.x v1.2.0
```

Releases made before the zip (below) are a commit of their own on top of their source: cut
those branches from the commit named on the `Source:` line of `git log -1 --format=%B v1.2.0`.

```bash
git push origin release/1.2.x
```

Pushing the new branch releases nothing, since nothing has changed yet. Then raise the fix as
a pull request into `release/1.2.x`, usually a `git cherry-pick -x` of the fix from `main`,
with a `## [1.2.1]` section above `[1.2.0]` in the changelog. The pull request is checked as
a patch: the `changelog` job runs `scripts/release.py check --patch`, and the release-preview
comment names `v1.2.1`.

Merging it pushes to the branch, which runs `.github/workflows/patch-release.yml`: the tests,
then `scripts/release.py patch` builds and publishes the release and its docs. It refuses
anything but the next patch of the current release, a branch not built on that release's
source, and a changelog whose top section isn't the patch. A change to nothing shipped needs
no section and releases nothing. A later patch is another pull request into the same branch,
under a new changelog section.

Each branch runs its own copy of the workflows and `scripts/release.py`, from the release it
was cut from, so a fix to them reaches an older branch only if it's cherry-picked there.
`release/1.1.x` predates them; every release from 1.2.0 carries them.

Land the fix on `main` too, with the same `[1.2.1]` section under its top one, or the next
version ships without it.

### How a release is built

Source never holds a real version. The manifest, `BLUEPRINT_VERSION` and the blueprint's
description stamp all say `0.0.0-dev`. `scripts/release.py` tags the source commit and
builds `flare.zip` from it, the integration's folder with the real version written into
those three places, and the workflow attaches it to the GitHub release. HACS installs that
zip (`zip_release` in `hacs.json`), never the tagged files. Nothing is committed to `dev` or
`main`, so they never drift apart over version bumps. A beta and the release it becomes are
the same commit, tagged twice, which is what "promote" means.

The blueprint is versioned with FLARE: its stamp (and `BLUEPRINT_VERSION`) is always the
release's own version, written by the same script. So every release, betas included, raises
the out-of-date-blueprint repair for anyone using it, even if the blueprint itself did not
change.

Shipped code has no special handling for a development build, on purpose. One thing follows:
a dev build's blueprint stamp is `0.0.0-dev`, which never matches a release's, so the repair
appears until you copy the changed file over your installed
`blueprints/automation/flare/flare.yaml` yourself.

### Two channels

The tag decides, and nothing else does:

| Tag | Published as | Who sees it |
|---|---|---|
| `v2.1.0` | a normal release | everyone |
| `v2.1.0-beta.1` | a GitHub **pre-release** | only people who opted in |

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

HACS can't install a branch or commit either: with `zip_release` it fetches `flare.zip` from
a release for any version but the default branch, and the default branch is hidden. To run
unreleased code, copy `custom_components/flare/` into your Home Assistant config and restart.

### Tagging by hand

Still possible, when a workflow is unavailable. For a hotfix, see "Patching the current release" above. Tag the
commit and push the tag: `.github/workflows/release.yml` checks the changelog has a section
for it, builds its `flare.zip` with `scripts/release.py package`, and publishes. (A tag
pushed by the workflows above does not trigger it - GitHub does not let a workflow's own
events start another - and needs none of this, since those workflows attach their own zip.)

**Merge, then verify, then tag - as separate steps.** Chaining them means a failed merge
still tags, which has happened: a `wip` commit went out as a release because the tag was
chained onto a merge that hadn't landed.

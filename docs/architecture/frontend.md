---
title: Dashboard internals
parent: How it works
nav_order: 9
permalink: /architecture/frontend/
---

# Dashboard internals
{: .no_toc }

{: .internals }
> Part of [How it works]({{ site.baseurl }}/architecture/), for contributors and the curious.
> Nothing here is needed to use FLARE.

The dashboard is plain JavaScript modules in `custom_components/flare/www/`,
served by the integration itself. There's no build step and no
dependency. It's made of Lovelace **strategies**, which generate the
dashboard's config on every load, plus a handful of custom cards and card
features.

## Getting into the page

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant HA as HA http
    participant L as flare-loader.js
    participant M as FLARE modules
    Note over HA: async_setup:<br/>static path /flare_static/#lt;hash#gt;/ → www/,<br/>add_extra_js_url(loader)
    B->>HA: GET / (page HTML lists extra modules)
    B->>HA: GET /flare_static/#lt;hash#gt;/flare-loader.js
    HA-->>B: the loader (cached hard)
    B->>L: run
    L->>L: await customElements.whenDefined('home-assistant')
    L->>M: import icon, curve card, features,<br/>transfer card, view strategy
    M-->>B: customElements.define,<br/>window.customStrategies / customCards /<br/>customCardFeatures / customIcons
    L->>HA: import /flare_static/frontend_loaded.js
    Note over HA: the beacon: clears the<br/>"reload for dashboard" repair
```

**The fingerprint.** The static path carries a hash of every file under
`www/` (`www_fingerprint()`), and is served with long-lived cache headers.
Any change to any file is a new URL. A version number wasn't enough: a dev
build is always `0.0.0-dev`, and Safari kept serving a stale strategy.

- It's a **path segment**, not `?v=`. The modules import each other
  relatively, and a relative import inherits the path but not a query, so
  `?v=` would load a module twice and the second `customElements.define`
  would throw. `test_static_imports.py` pins relative imports.
- **Any other fingerprint redirects** (302) to the current one
  (`OldFingerprintView`). A page served before an update, such as the
  service worker's stale copy or the companion app, still asks for the old
  hash, and a 404 would mean no dashboard at all.

**Waiting for `<home-assistant>`.** As it boots, HA's frontend installs a
scoped custom-element registry polyfill, replacing
`window.customElements`, while it loads integrations' modules in
parallel. A module that defined its elements first put them in the
browser's own registry, where HA never looks. The dashboard was then
listed but timed out when picked. So the loader waits for HA's own element
before importing anything. Outside HA, as in the docs playground, there's
nothing to wait for.

**A page open during first setup.** The frontend reads extra modules
only from the page HTML at load time, so a page open while FLARE is set up
never gets them. On HTTPS or `localhost`, the service worker serves the
first reload from its stale cache too. `dashboard_reload.py` handles both:
setup's summary and a repair link to a reload with a one-off query token,
a URL the service worker has never cached, with `target="_self"` so it's
a real page load. The beacon, imported last by the loader, clears the
repair. It sits under `/flare_static/` rather than `/api/` because HA's
CORS check rejects the `Origin` header a module import always sends.

## What registers what

```mermaid
flowchart TB
    loader["flare-loader.js"] --> icon["flare-icon.js<br/>window.customIcons: flare:logo"]
    loader --> curve["flare-curve-card.js<br/>custom:flare-curve-card"]
    loader --> kf["flare-kelvin-feature.js<br/>card feature"]
    loader --> bf["flare-brightness-feature.js<br/>card feature"]
    loader --> tc["flare-schedule-transfer-card.js<br/>custom:flare-schedule-transfer-card"]
    loader --> vs["flare-view-strategy.js<br/>custom:flare (dashboard),<br/>custom:flare-schedule,<br/>custom:flare-lights (views)"]
    kf --> vsl["flare-value-slider.js"]
    bf --> vsl
    bf --> kf
    kf --> curve
    vs --> ent["flare-entities.js"]
    vs --> sec["flare-section.js"]
    vs --> ls["flare-lights-section.js"]
    vs --> alc["flare-area-lights-card.js<br/>custom:flare-area-lights-card"]
    vs --> act["flare-activity-card.js<br/>custom:flare-activity-card"]
    vs --> clr["flare-clear-card.js<br/>(only for taken-over dashboards)"]
    sec --> i18n["flare-i18n.js<br/>translations/#lt;lang#gt;.js"]
    ls --> i18n
```

Only modules that register something are imported by the loader. The rest
come in through their imports. `test_every_module_that_registers_something_is_loaded`
follows the imports from the loader.

## The strategies

`custom:flare` is listed under **Settings → Dashboards → Add dashboard**
through `window.customStrategies`. FLARE never creates the dashboard
itself: HA keeps the dashboards collection private.

```mermaid
flowchart LR
    D["custom:flare<br/>(dashboard strategy)"] --> V1["custom:flare-schedule<br/>one view per schedule"]
    D --> V2["custom:flare-lights<br/>Overrides view,<br/>once the Settings entry exists"]
    V1 --> S1["sectionConfig():<br/>curve card, override,<br/>boundaries, sliders, transfer"]
    V2 --> S2["totalsSection():<br/>counts and Clear all"]
    V2 --> S3["areaSections():<br/>a flare-area-lights-card per area,<br/>grouped by floor"]
    V2 --> S4["flare-activity-card<br/>(sidebar)"]
```

Strategies regenerate on every load, so an update is the whole migration
and a new schedule or room just appears. **Take control** turns it into
ordinary YAML and is the one-way escape hatch.

**Entities are found by device and role, never by building ids.**
`flareDevices()` groups `hass.entities` by device, keyed by each entry's
translation key, which is its role (`morning_kelvin`, `schedule`,
`status`...). A renamed entity still shows. `flare-section.js` and
`flare-lights-section.js` return plain config objects, with no DOM, which
is what makes them testable under node.

## The cards

| Card | Reads | Notes |
|---|---|---|
| `flare-curve-card` | the schedule sensor's `points` and boundaries | one filled SVG path, simplified; corner easing never overshoots |
| `flare-kelvin-feature`, `flare-brightness-feature` | a `number` entity | HA's own `ha-control-slider`, filled with the value's colour |
| `flare-schedule-transfer-card` | `flare.export_schedule` / `import_schedule` | holds no copy of the YAML format |
| `flare-area-lights-card` | each light's status sensor | an area's lights, counts and Clear, worked out live in the browser |
| `flare-activity-card` | the logbook's `logbook/event_stream` for FLARE's device | rows are HA's own `ha-logbook-entry`, coloured by kind |

Two frontend internals are used knowingly, as accepted risks:
`ha-control-slider` (follow `hui-numeric-input-card-feature.ts` if it
breaks) and `ha-logbook-entry` (lazy-loaded, by having card helpers create
a logbook card first).

**Slider colour** is the curve's colour for the value, with 15 % of
`--primary-text-color` mixed in through `color-mix`. A near-white then
shows on a light card, and the theme decides which way it moves.

## Translations

HA's translations only reach an integration's backend strings, so the
cards carry their own: `flare-i18n.js` looks text up by key in
`www/translations/<lang>.js`, by the user's language, then its base
language ("de" for "de-CH"), then English. Composed names are patterns
(`{phase} colour temp`), since languages order words differently. Phase
names stay English as data, because they match the schedule sensor's
states, and are translated only for display.
`tests/unit/dashboard/test_i18n.py` holds every table to English's keys
and placeholders.

## Testing it

The dashboard's JavaScript runs under node in `tests/unit/dashboard/`, and
`tests/support/registry.py` builds `hass.entities` for its fixtures. For
the real thing, use the sandbox: add the FLARE dashboard and look.

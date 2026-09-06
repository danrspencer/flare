/**
 * Drives the docs site's dashboard section generator (docs/dashboard.html).
 *
 * Every schedule sensor produces the same 25-entity dashboard section -
 * only the slug changes. This just does the substitution client-side and
 * hands back copy-pasteable YAML; it doesn't talk to a live Home
 * Assistant instance at all (unlike playground.js, which renders the
 * real card against synthetic data).
 */

const slugInput = document.getElementById('dgen-slug');
const titleInput = document.getElementById('dgen-title');
const output = document.getElementById('dgen-yaml');
const copyButton = document.getElementById('dgen-copy');
const status = document.getElementById('dgen-status');

// Matches slugify() in custom_components/flare/__init__.py closely enough
// for this purpose: lowercase, spaces/dashes to underscores, drop
// anything else. Not required to be byte-identical - this only has to
// produce entity IDs that look right, the source of truth for what a
// schedule is actually named is the sensor itself.
function slugify(raw) {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '');
}

function titleCase(slug) {
  return slug
    .split('_')
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ');
}

// The section is built from data rather than 21 hand-written near-identical
// tile blocks: every tile now carries a colour, an icon and a feature
// position on top of its entity/name/width, and spelling that out per tile
// would be ~350 lines of copy-paste for four phases x two channels x two
// groups - precisely the shape that drifts when one of them is edited and
// its seven siblings aren't.
//
// COLOUR encodes the PHASE and ICON encodes the CHANNEL, so the Curve and
// Transitions groups can be scanned two ways at once: all of Morning is
// one colour wherever it appears, and every colour-temperature control
// carries the same icon whichever phase it belongs to.
//
// The palette tracks the COLOUR TEMPERATURE the curve actually reaches in
// each phase, not the time of day: Morning ramps to the coldest, bluest
// light of the day (10000K by default - the whole point of the phase, per
// the Xiao et al. morning-light research in the README), Day sits warmer
// and yellower, Evening warmer still, Night warmest. So Morning is blue
// and Day is yellow, which reads backwards against a sunrise/sunset
// mental model and is right against the curve sitting directly above it.
//
// A tile's `color` reaches its slider, not just its icon - hui-tile-card
// sets `--feature-color: var(--tile-color)`. It only applies while
// stateActive() is true, which for a `number` is always (the domain has no
// special case and falls through to true, so even a transition set to 0
// stays coloured). The one deliberate exception is Sticky: a `switch` that
// is off counts as inactive, so it greys out on its own, which is the
// right signal for an override that isn't engaged.
const PHASES = [
  { key: 'morning', label: 'Morning', color: 'blue', icon: 'mdi:weather-sunset-up' },
  { key: 'day', label: 'Day', color: 'yellow', icon: 'mdi:weather-sunny' },
  { key: 'evening', label: 'Evening', color: 'orange', icon: 'mdi:weather-sunset-down' },
  { key: 'night', label: 'Night', color: 'indigo', icon: 'mdi:weather-night' },
];

const BRIGHTNESS_ICON = 'mdi:brightness-6';
const KELVIN_ICON = 'mdi:temperature-kelvin';
// Transitions are durations, not levels, so they take a timing icon rather
// than repeating the channel icons from the Curve group above - the two
// groups otherwise use identical tile names ("Morning brightness" appears
// in both) and only the unit in the value distinguishes them.
const TRANSITION_ICON = 'mdi:timer-sand';

// The five schedule boundaries, in the order the day runs. Evening takes
// both of its bounds, which is why the phase list above doesn't map 1:1.
const SCHEDULE_TIMES = [
  { entity: 'morning_time', name: 'Morning', phase: 'morning' },
  { entity: 'day_time', name: 'Day', phase: 'day' },
  { entity: 'evening_earliest_time', name: 'Evening (earliest)', phase: 'evening' },
  { entity: 'evening_latest_time', name: 'Evening (latest)', phase: 'evening' },
  { entity: 'night_time', name: 'Night', phase: 'night' },
];

const phase = (key) => PHASES.find((p) => p.key === key);

// grid_options.columns is out of the SECTION's own grid (see CLAUDE.md
// lesson 15), which is 12 wide times the section's column_span - so the
// values here (6 for the Override pair, 4 for the five schedule times)
// buy several cards sharing a row, but only approximately: the exact
// number per row moves with the window. That is fine for those two
// groups, where nothing depends on which cards are adjacent, and not
// fine for Curve and Transitions - see pairGrid below.
//
// features_position: inline puts the control on the same row as the name
// instead of below it, roughly halving each tile's height - which matters
// on a section carrying 25 entities. Only the FIRST feature goes inline
// (frontend's computeCardFeatureLayout slices at 1); every tile here has
// exactly one, so all of them qualify.
function tile({ entity, name, icon, color, columns, features, indent = '  ' }) {
  const k = `${indent}  `;
  const lines = [
    `${indent}- type: tile`,
    `${k}entity: ${entity}`,
    `${k}name: ${name}`,
  ];
  if (icon) lines.push(`${k}icon: ${icon}`);
  if (color) lines.push(`${k}color: ${color}`);
  if (features) {
    lines.push(`${k}features_position: inline`);
    lines.push(`${k}features:`);
    lines.push(
      ...features.map((f) =>
        `${k}  - type: ${f.type}`.concat(f.style ? `\n${k}    style: ${f.style}` : '')
      )
    );
  }
  // Omitted inside a nested grid card, which lays its own children out -
  // a grid_options on a card the section's grid never sees does nothing.
  if (columns) lines.push(`${k}grid_options:`, `${k}  columns: ${columns}`);
  return lines.join('\n');
}

// Curve and Transitions are laid out as a nested grid card at two columns,
// so a row is always exactly one phase: brightness beside colour, Morning
// then Day then Evening then Night. Reading down a column then gives you
// one channel across the whole day.
//
// This is the one place a nested grid earns its keep over per-tile
// grid_options. `columns` there is out of the SECTION's own grid, and a
// spanned section's grid widens with the span - this section is
// column_span: 4, so on a wide screen its grid is 48 columns, not 12, and
// any fixed per-tile value lands on a different number of tiles per row
// at different window widths. A grid card's own `columns` is absolute, so
// two-up holds everywhere, which is the entire point of the grouping.
//
// grid_options: {columns: full} on the grid card itself is still required:
// a nested grid implements no getLayoutOptions(), so without it the whole
// group renders at roughly a third of the section's width - CLAUDE.md
// lesson 15, measured live.
function pairGrid(tiles) {
  return [
    '  - type: grid',
    '    columns: 2',
    '    square: false',
    '    grid_options:',
    '      columns: full',
    '    cards:',
    ...tiles,
  ].join('\n');
}

const heading = (text, style, extra = '') =>
  `  - type: heading\n    heading: ${text}\n    heading_style: ${style}${extra}`;

// The eight curve values and eight transition minutes are each a tile
// carrying the numeric-input feature (style: slider) - a first attempt used
// gauge cards instead, on the theory that seeing where today's value sits
// in a fixed range (brightness 0-255, colour temperature 1000-10000 Kelvin,
// transition 0-1440 minutes - see number.py's _CurveNumber) was the point
// of glancing at this section. Wrong in practice: a gauge is read-only in
// Home Assistant, tapping it only opens the more-info dialog - and this
// section is a control panel, not a readout, so losing the drag was a real
// regression. numeric-input restores it, and reads the entity's own
// configured min/max/step directly, so unlike the gauge version this
// generator carries no hardcoded ranges of its own to drift from
// number.py's if they ever change. style: slider overrides the entity's own
// mode: "box" more-info preference deliberately - fast drag-to-set on the
// dashboard and precise typed entry (still mode: box, via the entity's own
// more-info dialog) are two different, both still available, ways to set
// the same value.
//
// THE TRANSITIONS GROUP DELIBERATELY GETS NO FEATURE AT ALL. Its entities
// run 0-1440 minutes (number.py again: a whole day, so that "always be
// transitioning" is expressible rather than an error), while every value
// anyone actually sets is under an hour - so a slider spends ~96% of its
// travel on values nobody wants, and a single pixel is several minutes.
// The feature takes no min/max or scaling of its own (its whole config is
// {type, style}), so there is nothing to narrow, and style: buttons steps
// by the entity's native_step of 1, i.e. 45 taps to reach 45 minutes.
// A plain tile falls through to the more-info dialog, which these
// entities already render as a TYPED BOX rather than another slider
// (_attr_mode = "box"), so the precise path is the only path - which for
// a duration is the right one. It also halves the group's height.
const SLIDER = [{ type: 'numeric-input', style: 'slider' }];

// The colour-temperature values get FLARE's own feature instead of the
// built-in slider, so the track is painted in the temperature it sets.
// The built-in one cannot do that: a tile's slider takes its colour from
// --feature-color, which hui-tile-card sets to the tile's own --tile-color
// - one knob for two jobs, and this section already spends the tile's
// `color` on encoding the phase. A tile `color` takes no template either,
// so "tint it by the current value" is not expressible there at all.
//
// It ships and self-registers inside the integration exactly as the curve
// card does, so pasting this section still requires nothing extra to be
// installed - and the tile's own `color` goes back to meaning only the
// icon, which is what keeps the phase colour readable alongside it.
const KELVIN_SLIDER = [{ type: 'custom:flare-kelvin-feature' }];

export function buildYaml(slug, title) {
  const NESTED = '      ';

  const curve = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: `number.${slug}_${p.key}_brightness`,
        name: `${p.label} brightness`,
        icon: BRIGHTNESS_ICON,
        color: p.color,
        features: SLIDER,
        indent: NESTED,
      }),
      tile({
        entity: `number.${slug}_${p.key}_kelvin`,
        name: `${p.label} colour temp`,
        icon: KELVIN_ICON,
        color: p.color,
        features: KELVIN_SLIDER,
        indent: NESTED,
      }),
    ])
  );

  const transitions = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: `number.${slug}_${p.key}_brightness_transition`,
        name: `${p.label} brightness`,
        icon: TRANSITION_ICON,
        color: p.color,
        indent: NESTED,
      }),
      tile({
        entity: `number.${slug}_${p.key}_kelvin_transition`,
        name: `${p.label} colour`,
        icon: TRANSITION_ICON,
        color: p.color,
        indent: NESTED,
      }),
    ])
  );

  const times = SCHEDULE_TIMES.map((t) =>
    tile({
      entity: `time.${slug}_${t.entity}`,
      name: t.name,
      icon: phase(t.phase).icon,
      color: phase(t.phase).color,
      columns: 4,
    })
  );

  return `type: grid
column_span: 4
cards:
${heading(title, 'title', `
    icon: mdi:chart-bell-curve
    badges:
      - type: entity
        entity: sensor.${slug}_flare
        show_state: true
        show_icon: true
        name: Phase
      - type: entity
        entity: sensor.${slug}_flare
        state_content: brightness
        icon: ${BRIGHTNESS_ICON}
        name: Brightness
      - type: entity
        entity: sensor.${slug}_flare
        state_content: color_temp
        icon: ${KELVIN_ICON}
        name: Colour
      - type: entity
        entity: select.${slug}_flare_phase
        show_state: true
        icon: mdi:hand-back-right
        name: Override
        visibility:
          - condition: state
            entity: select.${slug}_flare_phase
            state_not: Auto`)}
  - type: custom:flare-curve-card
    sensor: ${slug}
    grid_options:
      columns: full
    title: ''
${heading('Override', 'subtitle')}
${tile({
  entity: `select.${slug}_flare_phase`,
  name: 'Phase',
  columns: 6,
  features: [{ type: 'select-options' }],
})}
${tile({
  entity: `switch.${slug}_sticky_phase_override`,
  name: 'Sticky',
  columns: 6,
  features: [{ type: 'toggle' }],
})}
${heading('Schedule', 'subtitle')}
${times.join('\n')}
${heading('Curve', 'subtitle')}
${curve}
${heading('Transitions', 'subtitle')}
  - type: markdown
    text_only: true
    grid_options:
      columns: full
    content: >-
      How long before each phase ends to start easing into the next one, in
      minutes. 0 is a hard cut. Values are clamped to the phase, so anything
      longer than the phase itself means "ease across the whole phase".
${transitions}
`;
}

// The title field tracks the slug field automatically until someone
// actually types into it themselves - after that their own text wins,
// same "auto until touched" pattern a lot of slug/name pairs use.
let titleTouched = false;
titleInput.addEventListener('input', () => {
  titleTouched = true;
  render();
});

// Matches the placeholder text shown in both empty inputs, so the
// output box always shows a coherent worked example - not a generic
// stand-in the placeholders never mention - until something real is typed.
const EXAMPLE_SLUG = 'downstairs';

function render() {
  const slug = slugify(slugInput.value) || EXAMPLE_SLUG;
  if (!titleTouched) {
    titleInput.value = titleCase(slug);
  }
  const title = titleInput.value.trim() || titleCase(slug);
  output.textContent = buildYaml(slug, title);
}

slugInput.addEventListener('input', render);

copyButton.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(output.textContent);
    status.textContent = 'Copied.';
  } catch {
    status.textContent = "Couldn't copy automatically - select the text above and copy it by hand.";
  }
  setTimeout(() => {
    status.textContent = '';
  }, 2500);
});

render();

/**
 * The dashboard section for one FLARE schedule, as a plain config object.
 *
 * Consumed by flare-view-strategy.js, which turns it into a live view.
 *
 * This layout used to live in a generator on the docs site that emitted
 * YAML for people to paste, which put every subsequent layout change on
 * the user: re-generate, re-paste, once per schedule. That generator is
 * gone. Keeping the layout as a config OBJECT rather than a string is
 * what makes that possible - a strategy hands Home Assistant objects.
 *
 * No DOM and no Home Assistant imports - data in, config out - so the
 * strategy and the tests can both use it anywhere.
 */

// COLOUR encodes the PHASE and ICON encodes the CHANNEL, so the Curve and
// Transitions groups can be scanned two ways at once: all of Morning is
// one colour wherever it appears, and every colour-temperature control
// carries the same icon whichever phase it belongs to.
//
// The palette tracks the COLOUR TEMPERATURE the curve actually reaches in
// each phase, not the time of day: Morning ramps to the coldest, bluest
// light of the day, and each phase after it is warmer. So Morning is blue
// and Day is yellow, which reads backwards against a sunrise/sunset
// mental model and is right against the curve sitting directly above it.
export const PHASES = [
  { key: 'morning', label: 'Morning', color: 'blue', icon: 'mdi:weather-sunset-up' },
  { key: 'day', label: 'Day', color: 'yellow', icon: 'mdi:weather-sunny' },
  { key: 'evening', label: 'Evening', color: 'orange', icon: 'mdi:weather-sunset-down' },
  { key: 'night', label: 'Night', color: 'indigo', icon: 'mdi:weather-night' },
];

const BRIGHTNESS_ICON = 'mdi:brightness-6';
const KELVIN_ICON = 'mdi:temperature-kelvin';
// Transitions are durations, not levels, so they take a timing icon
// rather than repeating the channel icons from the Curve group - the two
// groups otherwise use identical tile names.
const TRANSITION_ICON = 'mdi:timer-sand';

// The five schedule boundaries, in the order the day runs. Evening takes
// both of its bounds, which is why the phase list doesn't map 1:1.
const SCHEDULE_TIMES = [
  { entity: 'morning_time', name: 'Morning', phase: 'morning' },
  { entity: 'day_time', name: 'Day', phase: 'day' },
  { entity: 'evening_earliest_time', name: 'Evening (earliest)', phase: 'evening' },
  { entity: 'evening_latest_time', name: 'Evening (latest)', phase: 'evening' },
  { entity: 'night_time', name: 'Night', phase: 'night' },
];

const phase = (key) => PHASES.find((p) => p.key === key);

const SLIDER = [{ type: 'numeric-input', style: 'slider' }];

// Colour temperature gets FLARE's own feature rather than the built-in
// slider: the built-in takes its colour from the tile's, which this
// section spends on encoding the phase, and a tile `color` accepts no
// template. See flare-kelvin-feature.js.
const KELVIN_SLIDER = [{ type: 'custom:flare-kelvin-feature' }];

const TRANSITIONS_NOTE =
  'How long before each phase ends to start easing into the next one, in ' +
  'minutes. 0 is a hard cut. Values are clamped to the phase, so anything ' +
  'longer than the phase itself means "ease across the whole phase".';

// features_position: inline puts the control on the same row as the name
// instead of below it, roughly halving each tile's height - which matters
// on a section carrying 25 entities. Only the FIRST feature goes inline
// (the frontend's computeCardFeatureLayout slices at 1); every tile here
// has exactly one, so all of them qualify.
function tile({ entity, name, icon, color, columns, features }) {
  const card = { type: 'tile', entity, name };
  if (icon) card.icon = icon;
  if (color) card.color = color;
  if (features) {
    card.features = features;
    card.features_position = 'inline';
  }
  // Omitted inside a pairGrid, which lays its own children out - a
  // grid_options on a card the section's grid never sees does nothing.
  if (columns) card.grid_options = { columns };
  return card;
}

const heading = (text, style, extra = {}) => ({
  type: 'heading',
  heading: text,
  heading_style: style,
  ...extra,
});

// Curve and Transitions are laid out as a nested grid card at two
// columns, so a row is always exactly one phase: brightness beside
// colour, Morning then Day then Evening then Night. Reading down a
// column then gives one channel across the whole day.
//
// This has to be the grid card's own `columns`, not per-tile
// grid_options. The latter counts against the SECTION's grid, which is
// 12 wide times its column_span (4 here), so a fixed per-tile value
// lands on a different number of tiles per row at different window
// widths - fine where nothing depends on which cards are adjacent, and
// not fine for a layout that is entirely about which two tiles sit
// together.
//
// grid_options: {columns: full} on the grid card itself is still
// required: a nested grid implements no getLayoutOptions(), so without
// it the whole group renders at roughly a third of the section's width.
const pairGrid = (cards) => ({
  type: 'grid',
  columns: 2,
  square: false,
  grid_options: { columns: 'full' },
  cards,
});

/**
 * The whole section for one schedule, given its slug and a heading.
 *
 * `slug` is the schedule sensor's entity_id minus the `sensor.` prefix
 * and `_flare` suffix - the same value the curve card's `sensor:`
 * shorthand takes.
 */
export function sectionConfig(slug, title) {
  const curve = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: `number.${slug}_${p.key}_brightness`,
        name: `${p.label} brightness`,
        icon: BRIGHTNESS_ICON,
        color: p.color,
        features: SLIDER,
      }),
      tile({
        entity: `number.${slug}_${p.key}_kelvin`,
        name: `${p.label} colour temp`,
        icon: KELVIN_ICON,
        color: p.color,
        features: KELVIN_SLIDER,
      }),
    ])
  );

  // No feature at all on a transition: they run 0-1440 minutes while any
  // value anyone sets is under an hour, so a slider spends ~96% of its
  // travel out of reach. Tapping falls through to the more-info dialog,
  // which these entities already render as a typed box.
  const transitions = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: `number.${slug}_${p.key}_brightness_transition`,
        name: `${p.label} brightness`,
        icon: TRANSITION_ICON,
        color: p.color,
      }),
      tile({
        entity: `number.${slug}_${p.key}_kelvin_transition`,
        name: `${p.label} colour`,
        icon: TRANSITION_ICON,
        color: p.color,
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

  const sensor = `sensor.${slug}_flare`;
  const select = `select.${slug}_flare_phase`;

  return {
    type: 'grid',
    column_span: 4,
    cards: [
      heading(title, 'title', {
        icon: 'mdi:chart-bell-curve',
        badges: [
          { type: 'entity', entity: sensor, show_state: true, show_icon: true, name: 'Phase' },
          {
            type: 'entity',
            entity: sensor,
            state_content: 'brightness',
            icon: BRIGHTNESS_ICON,
            name: 'Brightness',
          },
          {
            type: 'entity',
            entity: sensor,
            state_content: 'color_temp',
            icon: KELVIN_ICON,
            name: 'Colour',
          },
          {
            type: 'entity',
            entity: select,
            show_state: true,
            icon: 'mdi:hand-back-right',
            name: 'Override',
            // It reads "Auto" the vast majority of the time, which is
            // noise on a header whose job is to show what is happening.
            visibility: [{ condition: 'state', entity: select, state_not: 'Auto' }],
          },
        ],
      }),
      { type: 'custom:flare-curve-card', sensor: slug, grid_options: { columns: 'full' }, title: '' },
      heading('Override', 'subtitle'),
      tile({ entity: select, name: 'Phase', columns: 6, features: [{ type: 'select-options' }] }),
      tile({
        entity: `switch.${slug}_sticky_phase_override`,
        name: 'Sticky',
        columns: 6,
        features: [{ type: 'toggle' }],
      }),
      heading('Schedule', 'subtitle'),
      ...times,
      heading('Curve', 'subtitle'),
      curve,
      heading('Transitions', 'subtitle'),
      { type: 'markdown', text_only: true, grid_options: { columns: 'full' }, content: TRANSITIONS_NOTE },
      transitions,
    ],
  };
}

const SENSOR_PREFIX = 'sensor.';
const SCHEDULE_SUFFIX = '_flare';

// Only reached when a schedule sensor has no friendly_name, which is
// rare - the device name normally supplies one. Worth doing anyway: a
// section headed "loft" sitting beside one headed "Downstairs" reads as
// a bug rather than as a name someone chose.
function titleCase(slug) {
  return slug
    .split('_')
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * The slug for whatever someone put in a `sensor:` option.
 *
 * Accepts the slug itself (`downstairs`, matching the curve card's own
 * `sensor:` shorthand) or the full entity_id (`sensor.downstairs_flare`),
 * because both are things people reasonably write and neither is wrong.
 * Returns null for an empty value, which callers read as "no filter".
 */
export function normaliseSlug(value) {
  if (typeof value !== 'string') return null;
  let slug = value.trim();
  if (!slug) return null;
  if (slug.startsWith(SENSOR_PREFIX)) slug = slug.slice(SENSOR_PREFIX.length);
  if (slug.endsWith(SCHEDULE_SUFFIX)) slug = slug.slice(0, -SCHEDULE_SUFFIX.length);
  return slug || null;
}

/**
 * Every FLARE schedule sensor in `hass`, as {slug, title} pairs, in a
 * stable order.
 *
 * Identified the same way the curve card's picker suggestion does: the
 * name shape, plus the `points` attribute only a schedule sensor
 * publishes. The tracking entities (`_flare_tracking`, `_flare_controlled`,
 * `_flare_overridden`) end in something else and fall out on the suffix,
 * so no exclusion list is needed that could go stale.
 */
export function scheduleSensors(hass) {
  const states = (hass && hass.states) || {};
  return Object.keys(states)
    .filter((id) => id.startsWith(SENSOR_PREFIX) && id.endsWith(SCHEDULE_SUFFIX))
    .filter((id) => states[id] && states[id].attributes && 'points' in states[id].attributes)
    .map((id) => {
      const slug = id.slice(SENSOR_PREFIX.length, -SCHEDULE_SUFFIX.length);
      const friendly = states[id].attributes.friendly_name;
      return { slug, title: friendly || titleCase(slug) };
    })
    .filter((s) => s.slug)
    .sort((a, b) => a.title.localeCompare(b.title));
}

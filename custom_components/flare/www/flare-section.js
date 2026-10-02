/**
 * The dashboard section for one FLARE schedule, as a config object for
 * flare-view-strategy.js. No DOM or HA imports.
 */

// Colour encodes the phase and icon the channel. Colours follow the
// temperature each phase reaches, so Morning (coldest) is blue.
export const PHASES = [
  { key: 'morning', label: 'Morning', color: 'blue', icon: 'mdi:weather-sunset-up' },
  { key: 'day', label: 'Day', color: 'yellow', icon: 'mdi:weather-sunny' },
  { key: 'evening', label: 'Evening', color: 'orange', icon: 'mdi:weather-sunset-down' },
  { key: 'night', label: 'Night', color: 'indigo', icon: 'mdi:weather-night' },
];

const BRIGHTNESS_ICON = 'mdi:brightness-6';
const KELVIN_ICON = 'mdi:temperature-kelvin';
const TRANSITION_ICON = 'mdi:timer-sand';

// Evening has both of its bounds.
const SCHEDULE_TIMES = [
  { entity: 'morning_time', name: 'Morning', phase: 'morning' },
  { entity: 'day_time', name: 'Day', phase: 'day' },
  { entity: 'evening_earliest_time', name: 'Evening (earliest)', phase: 'evening' },
  { entity: 'evening_latest_time', name: 'Evening (latest)', phase: 'evening' },
  { entity: 'night_time', name: 'Night', phase: 'night' },
];

const phase = (key) => PHASES.find((p) => p.key === key);

// FLARE's own sliders, since the built-in one takes the tile's (phase)
// colour. Colour temperature comes first in each row: brightness borrows
// its colour via tint_from.
const KELVIN_SLIDER = [{ type: 'custom:flare-kelvin-feature' }];
const brightnessSlider = (kelvinEntity) => [
  { type: 'custom:flare-brightness-feature', tint_from: kelvinEntity },
];

const TRANSITIONS_NOTE =
  'How long before each phase ends to start easing into the next one, in ' +
  'minutes. 0 is a hard cut. Values are clamped to the phase, so anything ' +
  'longer than the phase itself means "ease across the whole phase".';

// Puts the control on the name's row, halving tile height.
function tile({ entity, name, icon, color, columns, features }) {
  const card = { type: 'tile', entity, name };
  if (icon) card.icon = icon;
  if (color) card.color = color;
  if (features) {
    card.features = features;
    card.features_position = 'inline';
  }
  // Omitted inside a pairGrid, which lays out its own children.
  if (columns) card.grid_options = { columns };
  return card;
}

const heading = (text, style, extra = {}) => ({
  type: 'heading',
  heading: text,
  heading_style: style,
  ...extra,
});

// A two-column nested grid, so each row is one phase. It has to be the
// grid's `columns`: per-tile grid_options count against the section's
// grid and wrap differently at different widths. `columns: full` because
// a nested grid otherwise renders at a third of the section's width.
const pairGrid = (cards) => ({
  type: 'grid',
  columns: 2,
  square: false,
  grid_options: { columns: 'full' },
  cards,
});

/**
 * The section for one schedule. `slug` is the sensor's entity_id minus
 * `sensor.` and `_flare`.
 */
export function sectionConfig(slug, title) {
  const curve = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: `number.${slug}_${p.key}_kelvin`,
        name: `${p.label} colour temp`,
        icon: KELVIN_ICON,
        color: p.color,
        features: KELVIN_SLIDER,
      }),
      tile({
        entity: `number.${slug}_${p.key}_brightness`,
        name: `${p.label} brightness`,
        icon: BRIGHTNESS_ICON,
        color: p.color,
        features: brightnessSlider(`number.${slug}_${p.key}_kelvin`),
      }),
    ])
  );

  // No feature on transitions: 0-1440 minutes makes a slider useless for
  // the values people set. Tapping opens the more-info box instead.
  const transitions = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: `number.${slug}_${p.key}_kelvin_transition`,
        name: `${p.label} colour`,
        icon: TRANSITION_ICON,
        color: p.color,
      }),
      tile({
        entity: `number.${slug}_${p.key}_brightness_transition`,
        name: `${p.label} brightness`,
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
            // Almost always "Auto", so not worth showing.
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
// Also ends with SCHEDULE_SUFFIX plus more, hence the exact suffix test.
const CLAIMS_SUFFIX = '_flare_claims';

// Only when a sensor has no friendly_name.
function titleCase(slug) {
  return slug
    .split('_')
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * The slug from a `sensor:` option, which may be the slug or the full
 * entity_id. null for empty ("no filter").
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
 * Every schedule sensor as {slug, title}, in a stable order. Identified by
 * the name suffix and the `points` attribute.
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


/**
 * The section for one zone, sized to flow several to a row.
 * `controlled` + `overridden` needn't equal the total tracked.
 */
export function zoneSectionConfig(slug, title) {
  const controlled = `sensor.${slug}_flare_controlled`;
  const overridden = `sensor.${slug}_flare_overridden`;
  const clear = `button.${slug}_flare_clear`;

  return {
    type: 'grid',
    cards: [
      heading(title, 'title', { icon: 'mdi:eye-outline' }),
      tile({ entity: controlled, name: 'Controlled', columns: 6 }),
      tile({ entity: overridden, name: 'Overridden', columns: 6 }),
      // Hidden while zero, which is almost always.
      {
        type: 'markdown',
        text_only: true,
        grid_options: { columns: 'full' },
        content:
          `{% set lights = expand(state_attr('${overridden}', 'lights') or []) %}` +
          `Overridden: {{ lights | map(attribute='name') | join(', ') }}`,
        visibility: [{ condition: 'numeric_state', entity: overridden, above: 0 }],
      },
      // Explicit, so an upstream default change can't turn it into more-info.
      {
        type: 'tile',
        entity: clear,
        name: 'Clear claims',
        icon: 'mdi:backup-restore',
        grid_options: { columns: 'full' },
        tap_action: {
          action: 'perform-action',
          perform_action: 'button.press',
          target: { entity_id: clear },
        },
      },
    ],
  };
}

/**
 * Every zone as {slug, title}, identified by the `claims`
 * attribute. The title drops the trailing "Claims".
 */
export function listZones(hass) {
  const states = (hass && hass.states) || {};
  return Object.keys(states)
    .filter((id) => id.startsWith(SENSOR_PREFIX) && id.endsWith(CLAIMS_SUFFIX))
    .filter((id) => states[id] && states[id].attributes && 'claims' in states[id].attributes)
    .map((id) => {
      const slug = id.slice(SENSOR_PREFIX.length, -CLAIMS_SUFFIX.length);
      const friendly = states[id].attributes.friendly_name || '';
      const title = friendly.replace(/\s*Claims$/, '') || titleCase(slug);
      return { slug, title };
    })
    .filter((s) => s.slug)
    .sort((a, b) => a.title.localeCompare(b.title));
}

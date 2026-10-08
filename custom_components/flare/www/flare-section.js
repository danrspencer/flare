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
 * The section for one schedule, from scheduleSensors(): its title and its
 * entities by role.
 */
export function sectionConfig({ title, entities }) {
  const id = (role) => entities[role];
  const curve = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: id(`${p.key}_kelvin`),
        name: `${p.label} colour temp`,
        icon: KELVIN_ICON,
        color: p.color,
        features: KELVIN_SLIDER,
      }),
      tile({
        entity: id(`${p.key}_brightness`),
        name: `${p.label} brightness`,
        icon: BRIGHTNESS_ICON,
        color: p.color,
        features: brightnessSlider(id(`${p.key}_kelvin`)),
      }),
    ])
  );

  // No feature on transitions: 0-1440 minutes makes a slider useless for
  // the values people set. Tapping opens the more-info box instead.
  const transitions = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: id(`${p.key}_kelvin_transition`),
        name: `${p.label} colour`,
        icon: TRANSITION_ICON,
        color: p.color,
      }),
      tile({
        entity: id(`${p.key}_brightness_transition`),
        name: `${p.label} brightness`,
        icon: TRANSITION_ICON,
        color: p.color,
      }),
    ])
  );

  const times = SCHEDULE_TIMES.map((t) =>
    tile({
      entity: id(t.entity),
      name: t.name,
      icon: phase(t.phase).icon,
      color: phase(t.phase).color,
      columns: 4,
    })
  );

  const sensor = id('schedule');
  const select = id('phase_override');

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
      { type: 'custom:flare-curve-card', sensor, grid_options: { columns: 'full' }, title: '' },
      heading('Override', 'subtitle'),
      tile({ entity: select, name: 'Phase', columns: 6, features: [{ type: 'select-options' }] }),
      tile({
        entity: id('sticky_phase_override'),
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
      heading('Copy or paste', 'subtitle'),
      { type: 'custom:flare-schedule-transfer-card', sensor },
    ],
  };
}

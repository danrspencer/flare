/**
 * The dashboard section for one FLARE schedule, as a config object for
 * flare-view-strategy.js. No DOM or HA imports.
 */

import { localize } from './flare-i18n.js';

// Colour encodes the phase and icon the channel. Colours follow the
// temperature each phase reaches, so Morning (coldest) is blue.
export const PHASES = [
  { key: 'morning', color: 'blue', icon: 'mdi:weather-sunset-up' },
  { key: 'day', color: 'amber', icon: 'mdi:weather-sunny' },
  { key: 'evening', color: 'deep-orange', icon: 'mdi:weather-sunset-down' },
  { key: 'night', color: 'indigo', icon: 'mdi:weather-night' },
];

const BRIGHTNESS_ICON = 'mdi:brightness-6';
const KELVIN_ICON = 'mdi:temperature-kelvin';
const TRANSITION_ICON = 'mdi:timer-sand';

// Evening has both of its bounds.
const SCHEDULE_TIMES = [
  { entity: 'morning_time', name: 'phase.morning', phase: 'morning' },
  { entity: 'day_time', name: 'phase.day', phase: 'day' },
  { entity: 'evening_earliest_time', name: 'schedule.evening_earliest', phase: 'evening' },
  { entity: 'evening_latest_time', name: 'schedule.evening_latest', phase: 'evening' },
  { entity: 'night_time', name: 'phase.night', phase: 'night' },
];

const phase = (key) => PHASES.find((p) => p.key === key);

// FLARE's own sliders, since the built-in one takes the tile's (phase)
// colour. Colour temperature comes first in each row: brightness borrows
// its colour via tint_from.
const KELVIN_SLIDER = [{ type: 'custom:flare-kelvin-feature' }];
const brightnessSlider = (kelvinEntity) => [
  { type: 'custom:flare-brightness-feature', tint_from: kelvinEntity },
];

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
 * entities by role, in hass's language.
 */
export function sectionConfig({ title, entities }, hass) {
  const id = (role) => entities[role];
  const t = (key, values) => localize(hass, key, values);
  const label = (p) => t(`phase.${p.key}`);
  const curve = pairGrid(
    PHASES.flatMap((p) => [
      tile({
        entity: id(`${p.key}_kelvin`),
        name: t('schedule.curve_kelvin', { phase: label(p) }),
        icon: KELVIN_ICON,
        color: p.color,
        features: KELVIN_SLIDER,
      }),
      tile({
        entity: id(`${p.key}_brightness`),
        name: t('schedule.curve_brightness', { phase: label(p) }),
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
        name: t('schedule.transition_kelvin', { phase: label(p) }),
        icon: TRANSITION_ICON,
        color: p.color,
      }),
      tile({
        entity: id(`${p.key}_brightness_transition`),
        name: t('schedule.transition_brightness', { phase: label(p) }),
        icon: TRANSITION_ICON,
        color: p.color,
      }),
    ])
  );

  const times = SCHEDULE_TIMES.map((time) =>
    tile({
      entity: id(time.entity),
      name: localize(hass, time.name),
      icon: phase(time.phase).icon,
      color: phase(time.phase).color,
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
          { type: 'entity', entity: sensor, show_state: true, show_icon: true, name: t('schedule.badge_phase') },
          {
            type: 'entity',
            entity: sensor,
            state_content: 'brightness',
            icon: BRIGHTNESS_ICON,
            name: t('schedule.badge_brightness'),
          },
          {
            type: 'entity',
            entity: sensor,
            state_content: 'color_temp_kelvin',
            icon: KELVIN_ICON,
            name: t('schedule.badge_colour'),
          },
          {
            type: 'entity',
            entity: select,
            show_state: true,
            icon: 'mdi:hand-back-right',
            name: t('schedule.badge_override'),
            // Almost always "Auto", so not worth showing.
            visibility: [{ condition: 'state', entity: select, state_not: 'Auto' }],
          },
        ],
      }),
      { type: 'custom:flare-curve-card', sensor, grid_options: { columns: 'full' }, title: '' },
      heading(t('schedule.override'), 'subtitle'),
      tile({ entity: select, name: t('schedule.override_phase'), columns: 6, features: [{ type: 'select-options' }] }),
      tile({
        entity: id('sticky_phase_override'),
        name: t('schedule.override_sticky'),
        columns: 6,
        features: [{ type: 'toggle' }],
      }),
      heading(t('schedule.times'), 'subtitle'),
      ...times,
      heading(t('schedule.curve'), 'subtitle'),
      curve,
      heading(t('schedule.transitions'), 'subtitle'),
      { type: 'markdown', text_only: true, grid_options: { columns: 'full' }, content: t('schedule.transitions_note') },
      transitions,
      heading(t('schedule.transfer'), 'subtitle'),
      { type: 'custom:flare-schedule-transfer-card', sensor },
    ],
  };
}

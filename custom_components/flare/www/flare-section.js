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

const SENSOR_PREFIX = 'sensor.';
const SCHEDULE_SUFFIX = '_flare';
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

// A sensor's entity_id minus `sensor.` and, if it has it, `suffix`.
function slugOfSensor(entityId, suffix) {
  const name = entityId.slice(SENSOR_PREFIX.length);
  return name.endsWith(suffix) ? name.slice(0, -suffix.length) : name;
}

/**
 * Each FLARE device's entities by role: device_id -> {role: entity_id}.
 * The role is the entity's translation key, which a rename leaves alone.
 */
export function flareDevices(hass) {
  const devices = new Map();
  for (const entry of Object.values((hass && hass.entities) || {})) {
    if (entry.platform !== 'flare' || !entry.device_id || !entry.translation_key) continue;
    if (!devices.has(entry.device_id)) devices.set(entry.device_id, {});
    devices.get(entry.device_id)[entry.translation_key] = entry.entity_id;
  }
  return devices;
}

// Every FLARE device with an entity in `role`, as {slug, title, device,
// entities}, sorted by title.
function devicesWith(hass, role, suffix, title) {
  const states = (hass && hass.states) || {};
  return [...flareDevices(hass)]
    .filter(([, entities]) => entities[role])
    .map(([device, entities]) => {
      const sensor = entities[role];
      const slug = slugOfSensor(sensor, suffix);
      const friendly = states[sensor]?.attributes?.friendly_name;
      return { slug, title: title(friendly) || titleCase(slug), device, entities };
    })
    .sort((a, b) => a.title.localeCompare(b.title));
}

/** Every schedule, by its sensor. */
export function scheduleSensors(hass) {
  return devicesWith(hass, 'schedule', SCHEDULE_SUFFIX, (friendly) => friendly);
}

/** Every zone, by its claims sensor. The title drops the trailing "Claims". */
export function listZones(hass) {
  return devicesWith(hass, 'claims', CLAIMS_SUFFIX, (friendly) => (friendly || '').replace(/\s*Claims$/, ''));
}

/** Each zone's device. */
export function zoneDevices(hass, zones = listZones(hass)) {
  return zones.map((zone) => zone.device);
}

// Home Assistant's slugify, near enough for area names.
const slugOf = (name) =>
  String(name || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');

// The Light dashboard's screen-size conditions (view-columns-conditions.ts).
const LARGE_SCREEN = { condition: 'view_columns', min: 2 };
const SMALL_SCREEN = { condition: 'view_columns', max: 1 };

const pressClear = (clear) => ({
  action: 'perform-action',
  perform_action: 'button.press',
  target: { entity_id: clear },
});

/** A zone's area: its device's, or else the area named after it. */
export function zoneArea(hass, zone) {
  const devices = (hass && hass.devices) || {};
  const areas = (hass && hass.areas) || {};
  const device = devices[zone.device];
  if (device?.area_id && areas[device.area_id]) return areas[device.area_id];
  return Object.values(areas).find((area) => slugOf(area.name) === slugOf(zone.title)) || null;
}

/**
 * One zone's row, laid out like Home Assistant's Light dashboard: a heading
 * (linking to the zone's device page), then on wide screens Clear where the
 * Light dashboard has "All off", with the zone's two counts beside it, and on
 * narrow ones Clear as a button on the heading. The overridden lights are
 * named underneath while there are any.
 */
export function zoneCards(zone, title) {
  const { controlled, overridden, clear } = zone.entities;
  const cards = [
    {
      type: 'heading',
      heading: title,
      heading_style: 'subtitle',
      tap_action: { action: 'navigate', navigation_path: `/config/devices/device/${zone.device}` },
      badges: [
        { type: 'button', icon: 'mdi:backup-restore', text: 'Clear', tap_action: pressClear(clear), visibility: [SMALL_SCREEN] },
      ],
    },
    { type: 'custom:flare-clear-card', entity: clear, visibility: [LARGE_SCREEN], grid_options: { columns: 3, rows: 1 } },
  ];
  // Each count is coloured while it has lights and grey at none, so a
  // zone with overrides stands out. Two tiles, one shown at a time: a
  // tile's colour takes no template.
  const any = (entity) => ({ condition: 'numeric_state', entity, above: 0 });
  const anyOverridden = any(overridden);
  const count = (entity, name, color) => [
    { type: 'tile', entity, name, color, visibility: [any(entity)] },
    { type: 'tile', entity, name, color: 'grey', visibility: [{ condition: 'not', conditions: [any(entity)] }] },
  ];
  // The counts share one card, so they stay beside Clear: a tile is never
  // narrower than half a 12-column section.
  const counts = (columns, visibility) => ({
    type: 'grid',
    columns: 2,
    square: false,
    cards: [...count(controlled, 'Controlled', 'blue'), ...count(overridden, 'Overridden', 'amber')],
    grid_options: { columns },
    visibility: [visibility],
  });
  cards.push(counts(9, LARGE_SCREEN), counts('full', SMALL_SCREEN));
  cards.push({
    type: 'markdown',
    text_only: true,
    grid_options: { columns: 'full' },
    content:
      `{% set lights = expand(state_attr('${overridden}', 'lights') or []) %}` +
      `Overridden: {{ lights | map(attribute='name') | join(', ') }}`,
    visibility: [anyOverridden],
  });
  return cards;
}

/** The house's totals, from every zone's counts. */
export function zoneTotalsSection(zones) {
  const sum = (status) =>
    `{{ ${JSON.stringify(zones.map(({ entities }) => entities[status])).replace(/"/g, "'")}` +
    ` | map('states') | map('int', 0) | sum }}`;
  return {
    type: 'grid',
    column_span: 2,
    cards: [
      { type: 'heading', heading: 'Zones', heading_style: 'title', icon: 'mdi:lightbulb-group' },
      {
        type: 'markdown',
        text_only: true,
        grid_options: { columns: 'full' },
        content: `**${sum('controlled')}** lights controlled · **${sum('overridden')}** overridden`,
      },
    ],
  };
}

/**
 * Every zone, grouped by floor and then area like the Light dashboard. A
 * zone named after its area takes the area's name; two in one area keep
 * their own. Zones with no area come last.
 */
export function zoneSections(hass, zones) {
  const floors = (hass && hass.floors) || {};
  const byArea = new Map();
  const unplaced = [];
  for (const zone of zones) {
    const area = zoneArea(hass, zone);
    if (!area) unplaced.push(zone);
    else byArea.set(area.area_id, { area, zones: [...(byArea.get(area.area_id)?.zones || []), zone] });
  }
  const rows = (entries) =>
    entries
      .sort((a, b) => a.area.name.localeCompare(b.area.name))
      .flatMap(({ area, zones: inArea }) =>
        inArea.flatMap((zone) =>
          zoneCards(zone, inArea.length === 1 ? area.name : zone.title)
        )
      );
  const section = (heading, icon, cards) => ({
    type: 'grid',
    column_span: 2,
    cards: [{ type: 'heading', heading, ...(icon ? { icon } : {}) }, ...cards],
  });

  const entries = [...byArea.values()];
  const floorIds = [...new Set(entries.map(({ area }) => area.floor_id).filter((id) => id && floors[id]))].sort(
    (a, b) => (floors[a].level ?? 0) - (floors[b].level ?? 0) || floors[a].name.localeCompare(floors[b].name)
  );
  const sections = floorIds.map((id) =>
    section(floors[id].name, floors[id].icon || 'mdi:home-floor-0', rows(entries.filter(({ area }) => area.floor_id === id)))
  );
  const floorless = entries.filter(({ area }) => !floorIds.includes(area.floor_id));
  if (floorless.length) sections.push(section(sections.length ? 'Other areas' : 'Areas', null, rows(floorless)));
  if (unplaced.length) {
    sections.push(
      section(
        'Other zones',
        null,
        unplaced.sort((a, b) => a.title.localeCompare(b.title)).flatMap((zone) => zoneCards(zone, zone.title))
      )
    );
  }
  return sections;
}

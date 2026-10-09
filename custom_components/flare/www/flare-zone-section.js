/**
 * The Zones view's sections, as config objects for flare-view-strategy.js.
 * No DOM or HA imports.
 */

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
      ...(zone.device
        ? { tap_action: { action: 'navigate', navigation_path: `/config/devices/device/${zone.device}` } }
        : {}),
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

/**
 * The house's totals, as a row like each zone's: Clear presses every
 * zone's Clear, and the counts are the totals across zones (flareTotals()).
 */
export function zoneTotalsSection(zones, totals) {
  const everything = {
    device: null,
    entities: {
      controlled: totals.controlled,
      overridden: totals.overridden,
      clear: zones.map((zone) => zone.entities.clear).filter(Boolean),
    },
  };
  return {
    type: 'grid',
    column_span: 2,
    cards: [
      { type: 'heading', heading: 'Zones', heading_style: 'title', icon: 'mdi:lightbulb-group' },
      ...zoneCards(everything, 'All zones'),
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

/**
 * The Rooms view's sections, as config objects for flare-view-strategy.js.
 * No DOM or HA imports.
 */

// The Light dashboard's screen-size conditions (view-columns-conditions.ts).
const LARGE_SCREEN = { condition: 'view_columns', min: 2 };
const SMALL_SCREEN = { condition: 'view_columns', max: 1 };

/**
 * The house's totals, laid out like Home Assistant's Light dashboard: Clear
 * where that has "All off", pressing the Clear button, then the two totals.
 * Each count is coloured while it has lights and grey at none, so overrides
 * stand out. Two tiles, one shown at a time: a tile's colour takes no
 * template. The overridden lights are named underneath while there are any.
 */
export function totalsSection(totals) {
  const { controlled, overridden, clear } = totals;
  const any = (entity) => ({ condition: 'numeric_state', entity, above: 0 });
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
  return {
    type: 'grid',
    column_span: 2,
    cards: [
      { type: 'heading', heading: 'Rooms', heading_style: 'title', icon: 'mdi:lightbulb-group' },
      { type: 'heading', heading: 'All rooms', heading_style: 'subtitle' },
      { type: 'custom:flare-clear-card', entity: clear, grid_options: { columns: 3, rows: 1 } },
      counts(9, LARGE_SCREEN),
      counts('full', SMALL_SCREEN),
      {
        type: 'markdown',
        text_only: true,
        grid_options: { columns: 'full' },
        content:
          `{% set lights = expand(state_attr('${overridden}', 'lights') or []) %}` +
          `Overridden: {{ lights | map(attribute='name') | join(', ') }}`,
        visibility: [any(overridden)],
      },
    ],
  };
}

/**
 * One area's row: a heading linking to the area's page, Clear for its
 * claimed lights, and its counts, worked out live (flare-area-card.js).
 */
export function areaCards(area) {
  return [
    {
      type: 'heading',
      heading: area.name,
      heading_style: 'subtitle',
      tap_action: { action: 'navigate', navigation_path: `/config/areas/area/${area.area_id}` },
    },
    { type: 'custom:flare-clear-card', area: area.area_id, grid_options: { columns: 3, rows: 1 } },
    { type: 'custom:flare-area-card', area: area.area_id, grid_options: { columns: 9 }, visibility: [LARGE_SCREEN] },
    { type: 'custom:flare-area-card', area: area.area_id, grid_options: { columns: 'full' }, visibility: [SMALL_SCREEN] },
  ];
}

/**
 * Every area holding a room light, grouped by floor (lowest first) like the
 * Light dashboard, areas on no floor last.
 */
export function areaSections(hass, areaIds) {
  const floors = (hass && hass.floors) || {};
  const areas = areaIds.map((id) => hass.areas && hass.areas[id]).filter(Boolean);
  const rows = (inSection) =>
    inSection.sort((a, b) => a.name.localeCompare(b.name)).flatMap((area) => areaCards(area));
  const section = (heading, icon, cards) => ({
    type: 'grid',
    column_span: 2,
    cards: [{ type: 'heading', heading, ...(icon ? { icon } : {}) }, ...cards],
  });

  const floorIds = [...new Set(areas.map((area) => area.floor_id).filter((id) => id && floors[id]))].sort(
    (a, b) => (floors[a].level ?? 0) - (floors[b].level ?? 0) || floors[a].name.localeCompare(floors[b].name)
  );
  const sections = floorIds.map((id) =>
    section(floors[id].name, floors[id].icon || 'mdi:home-floor-0', rows(areas.filter((area) => area.floor_id === id)))
  );
  const floorless = areas.filter((area) => !floorIds.includes(area.floor_id));
  if (floorless.length) sections.push(section(sections.length ? 'Other areas' : 'Areas', null, rows(floorless)));
  return sections;
}

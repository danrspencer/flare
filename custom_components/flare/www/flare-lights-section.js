/**
 * The Lights view's sections, as config objects for flare-view-strategy.js.
 * No DOM or HA imports.
 */

/**
 * The house's totals: the two counts and Clear all, three tiles in a row.
 * Each count is coloured while it has lights and grey at none, so overrides
 * stand out. Two tiles, one shown at a time: a tile's colour takes no
 * template. Clear all presses the Clear button.
 */
export function totalsSection(totals) {
  const { controlled, overridden, clear } = totals;
  const any = (entity) => ({ condition: 'numeric_state', entity, above: 0 });
  const count = (entity, name, color) => [
    { type: 'tile', entity, name, color, visibility: [any(entity)] },
    { type: 'tile', entity, name, color: 'grey', visibility: [{ condition: 'not', conditions: [any(entity)] }] },
  ];
  const press = { action: 'perform-action', perform_action: 'button.press', target: { entity_id: clear } };
  return {
    type: 'grid',
    column_span: 2,
    cards: [
      { type: 'heading', heading: 'Lights', heading_style: 'title', icon: 'mdi:lightbulb-group' },
      { type: 'heading', heading: 'All lights', heading_style: 'subtitle' },
      {
        // One card, so the three stay in a row: a loose tile is never
        // narrower than half a 12-column section.
        type: 'grid',
        columns: 3,
        square: false,
        cards: [
          ...count(controlled, 'Controlled', 'blue'),
          ...count(overridden, 'Overridden', 'amber'),
          {
            type: 'tile',
            entity: clear,
            name: 'Clear all',
            icon: 'mdi:backup-restore',
            hide_state: true,
            tap_action: press,
            icon_tap_action: press,
          },
        ],
        grid_options: { columns: 'full' },
      },
    ],
  };
}

/**
 * One area's row: a heading linking to the area's page, then its lights,
 * under its counts and Clear all (flare-area-lights-card.js).
 */
export function areaCards(area) {
  return [
    {
      type: 'heading',
      heading: area.name,
      heading_style: 'subtitle',
      tap_action: { action: 'navigate', navigation_path: `/config/areas/area/${area.area_id}` },
    },
    { type: 'custom:flare-area-lights-card', area: area.area_id, grid_options: { columns: 'full' } },
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

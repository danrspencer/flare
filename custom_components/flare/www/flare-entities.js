/**
 * Finding FLARE's schedules and claims, and their entities, for the
 * dashboard. No DOM or HA imports.
 */

const SENSOR_PREFIX = 'sensor.';
const SCHEDULE_SUFFIX = '_flare';

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

/**
 * The Settings entry's entities, on FLARE's own device: the totals and
 * Clear. {device, controlled, overridden, clear}, each an id or undefined.
 */
export function flareTotals(hass) {
  const roles = { all_controlled: 'controlled', all_overridden: 'overridden', clear: 'clear' };
  const totals = {};
  for (const entry of Object.values((hass && hass.entities) || {})) {
    if (entry.platform !== 'flare' || !roles[entry.translation_key]) continue;
    totals[roles[entry.translation_key]] = entry.entity_id;
    if (entry.device_id) totals.device = entry.device_id;
  }
  return totals;
}

/** A light's area: its own, else its device's. */
export function lightArea(hass, entityId) {
  const entry = (hass && hass.entities && hass.entities[entityId]) || {};
  if (entry.area_id) return entry.area_id;
  const device = entry.device_id && hass.devices && hass.devices[entry.device_id];
  return (device && device.area_id) || null;
}

/**
 * Each light's status sensor, by light: light -> {status, claimed, asked,
 * differs, rooms}. Only lights a room names or FLARE claims: a light whose room has
 * let it go keeps its sensor, but isn't a room light any more.
 */
export function lightStatuses(hass) {
  const lights = new Map();
  for (const entry of Object.values((hass && hass.entities) || {})) {
    if (entry.platform !== 'flare' || entry.translation_key !== 'status') continue;
    const state = hass.states && hass.states[entry.entity_id];
    const attributes = (state && state.attributes) || {};
    const rooms = attributes.rooms || [];
    if (!attributes.light || !(rooms.length || attributes.claimed)) continue;
    lights.set(attributes.light, {
      status: state.state,
      claimed: Boolean(attributes.claimed),
      asked: attributes.asked || null,
      differs: attributes.differs || [],
      rooms,
    });
  }
  return lights;
}

/** Every room light by area: area_id -> {lights}, a sorted list of entity_ids. */
export function claimsByArea(hass) {
  const byArea = new Map();
  for (const light of [...lightStatuses(hass).keys()].sort()) {
    const area = lightArea(hass, light);
    if (!area) continue;
    if (!byArea.has(area)) byArea.set(area, { lights: [] });
    byArea.get(area).lights.push(light);
  }
  return byArea;
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

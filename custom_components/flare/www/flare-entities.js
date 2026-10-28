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
 * The Settings entry's entities, on FLARE's own device: the claims sensor,
 * the totals and Clear. {device, claims, controlled, overridden, clear},
 * each an id or undefined.
 */
export function flareTotals(hass) {
  const roles = { claims: 'claims', all_controlled: 'controlled', all_overridden: 'overridden', clear: 'clear' };
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
 * Every room light by area, from the claims sensor: area_id -> {lights,
 * claimed, controlled, overridden}, each a sorted list of entity_ids. A
 * room light is one some automation named; claimed ones have a status.
 */
export function claimsByArea(hass) {
  const claims = flareTotals(hass).claims;
  const attributes = (claims && hass.states && hass.states[claims] && hass.states[claims].attributes) || {};
  const statuses = attributes.statuses || {};
  const lights = new Set(Object.keys(statuses));
  for (const room of Object.values(attributes.rooms || {})) (room.lights || []).forEach((l) => lights.add(l));
  const byArea = new Map();
  for (const light of [...lights].sort()) {
    const area = lightArea(hass, light);
    if (!area) continue;
    if (!byArea.has(area)) byArea.set(area, { lights: [], claimed: [], controlled: [], overridden: [] });
    const entry = byArea.get(area);
    entry.lights.push(light);
    if (statuses[light]) entry.claimed.push(light);
    if (statuses[light] === 'controlled') entry.controlled.push(light);
    if (statuses[light] === 'overridden') entry.overridden.push(light);
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

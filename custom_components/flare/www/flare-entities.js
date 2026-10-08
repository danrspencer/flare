/**
 * Finding FLARE's schedules and zones, and each one's entities, for the
 * dashboard. No DOM or HA imports.
 */

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

/**
 * The totals across every zone, which belong to no device:
 * {controlled, overridden}, each an entity_id or undefined.
 */
export function flareTotals(hass) {
  const totals = {};
  for (const entry of Object.values((hass && hass.entities) || {})) {
    if (entry.platform !== 'flare') continue;
    if (entry.translation_key === 'all_controlled') totals.controlled = entry.entity_id;
    if (entry.translation_key === 'all_overridden') totals.overridden = entry.entity_id;
  }
  return totals;
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

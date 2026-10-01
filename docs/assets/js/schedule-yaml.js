/**
 * A schedule as the YAML document flare.export_schedule writes and
 * flare.import_schedule reads. The port of schedule/transfer.py's dump()
 * and parse(), held to it by tests/unit/docs/test_schedule_yaml.py.
 *
 * Values are keyed like the entities: "morning_time" ("HH:MM:SS"),
 * "morning_brightness", ... Parsing YAML text is the caller's (the page
 * loads js-yaml); this takes the parsed object.
 */

const PHASES = ['morning', 'day', 'evening', 'night'];
const TIME_FIELDS = {
  morning: { time: 'morning_time' },
  day: { time: 'day_time' },
  evening: { earliest: 'evening_earliest_time', latest: 'evening_latest_time' },
  night: { time: 'night_time' },
};
const NUMBER_FIELDS = ['brightness', 'kelvin', 'brightness_transition', 'kelvin_transition'];

/** [phase, field, key, isTime] in document order. */
export const FIELDS = PHASES.flatMap((phase) => [
  ...Object.entries(TIME_FIELDS[phase]).map(([field, key]) => [phase, field, key, true]),
  ...NUMBER_FIELDS.map((field) => [phase, field, `${phase}_${field}`, false]),
]);

/** Matches curve.py's value_range(). */
export function valueRange(key) {
  if (key.endsWith('_transition')) return [0, 1440];
  if (key.endsWith('_brightness')) return [0, 255];
  return [1000, 10000];
}

const shortTime = (t) => (t.length === 8 && t.endsWith(':00') ? t.slice(0, 5) : t);

export function scheduleYaml(values) {
  const lines = [];
  for (const phase of PHASES) {
    const fields = FIELDS.filter(([p, , key]) => p === phase && key in values);
    if (!fields.length) continue;
    lines.push(`${phase}:`);
    for (const [, field, key, isTime] of fields) {
      lines.push(isTime ? `  ${field}: "${shortTime(values[key])}"` : `  ${field}: ${values[key]}`);
    }
  }
  return `${lines.join('\n')}\n`;
}

/** The parsed document into values, or an Error saying what's wrong. */
export function scheduleValues(doc) {
  if (!doc || typeof doc !== 'object' || Array.isArray(doc) || !Object.keys(doc).length) {
    throw new Error('Expected phases (morning, day, evening, night), each with its settings.');
  }
  const values = {};
  for (const [phase, fields] of Object.entries(doc)) {
    if (!PHASES.includes(phase)) {
      throw new Error(`Unknown phase '${phase}'. Expected one of: ${PHASES.join(', ')}.`);
    }
    if (!fields || typeof fields !== 'object' || Array.isArray(fields)) {
      throw new Error(`'${phase}' should hold settings like brightness and kelvin.`);
    }
    for (const [field, raw] of Object.entries(fields)) {
      const match = FIELDS.find(([p, f]) => p === phase && f === field);
      if (!match) {
        const known = FIELDS.filter(([p]) => p === phase).map(([, f]) => f);
        throw new Error(`Unknown setting '${phase}.${field}'. Expected one of: ${known.join(', ')}.`);
      }
      const [, , key, isTime] = match;
      values[key] = isTime ? parseTime(phase, field, raw) : parseNumber(phase, field, key, raw);
    }
  }
  return values;
}

function parseTime(phase, field, raw) {
  const m = typeof raw === 'string' && /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(raw);
  if (m) {
    const [h, min, s] = [Number(m[1]), Number(m[2]), Number(m[3] || 0)];
    if (h < 24 && min < 60 && s < 60) {
      return [h, min, s].map((n) => String(n).padStart(2, '0')).join(':');
    }
  }
  throw new Error(`'${phase}.${field}' should be a time like "06:30", not ${JSON.stringify(raw)}.`);
}

function parseNumber(phase, field, key, raw) {
  const [low, high] = valueRange(key);
  const n = typeof raw === 'number' ? raw : typeof raw === 'string' && /^[+-]?\d+$/.test(raw.trim()) ? Number(raw) : NaN;
  if (!Number.isInteger(n) || n < low || n > high) {
    throw new Error(`'${phase}.${field}' should be a whole number from ${low} to ${high}, not ${JSON.stringify(raw)}.`);
  }
  return n;
}

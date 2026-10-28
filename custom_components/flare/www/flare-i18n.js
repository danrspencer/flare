/**
 * The dashboard's own text in the user's Home Assistant language, from
 * translations/<language>.js; English for anything a language lacks.
 * Home Assistant's own translations only reach an integration's backend
 * strings, so the cards and views carry theirs.
 *
 *   localize(hass, 'curve.kelvin', { phase: localize(hass, 'phase.morning') })
 */

import en from './translations/en.js';
import de from './translations/de.js';

export const LANGUAGES = { en, de };

/** The language to show: the user's, else its base ("de" for "de-CH"), else English. */
export function language(hass) {
  const tag = String((hass && ((hass.locale && hass.locale.language) || hass.language)) || 'en').toLowerCase();
  if (LANGUAGES[tag]) return tag;
  const base = tag.split('-')[0];
  return LANGUAGES[base] ? base : 'en';
}

/** The text for `key`, with each {name} filled in from `values`. */
export function localize(hass, key, values = {}) {
  const text = LANGUAGES[language(hass)][key] ?? en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (placeholder, name) => (name in values ? String(values[name]) : placeholder));
}

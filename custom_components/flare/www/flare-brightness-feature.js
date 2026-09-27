/**
 * Card feature: a brightness `number` as HA's own slider, filled with the
 * colour the light will be - like HA's own `light-brightness` feature.
 * Brightness has no colour, so it borrows one from `tint_from`, a
 * colour-temperature entity:
 *
 *   features:
 *     - type: custom:flare-brightness-feature
 *       tint_from: number.downstairs_morning_kelvin
 *
 * Without a readable `tint_from` it falls back to `--primary-color`, the
 * stock slider's colour.
 */

import { kelvinToRgb } from './flare-curve-card.js';
import { defineValueSlider } from './flare-value-slider.js';

/** The Kelvin to borrow a colour from, or null for the theme colour. */
export function tintKelvin(config, hass) {
  const entityId = config && config.tint_from;
  const stateObj = entityId && hass && hass.states ? hass.states[entityId] : undefined;
  if (!stateObj) return null;
  const kelvin = Number(stateObj.state);
  return Number.isNaN(kelvin) ? null : kelvin;
}

/** Solid fill in the tinting entity's colour; the width carries the value. */
export function brightnessColor(config, hass) {
  const kelvin = tintKelvin(config, hass);
  if (kelvin === null) return 'var(--primary-color)';
  const [r, g, b] = kelvinToRgb(kelvin);
  return `rgb(${r}, ${g}, ${b})`;
}

/** A unit-less number with a 0-255 range, like FLARE's brightness entities. */
export function supportsBrightnessFeature(hass, context) {
  const entityId = context && context.entity_id;
  const stateObj = entityId && hass && hass.states ? hass.states[entityId] : undefined;
  if (!stateObj) return false;
  if (!entityId.startsWith('number.')) return false;
  const attrs = stateObj.attributes || {};
  if (attrs.unit_of_measurement) return false;
  return attrs.min === 0 && attrs.max === 255;
}

defineValueSlider({
  tag: 'flare-brightness-feature',
  name: 'FLARE Brightness',
  supported: supportsBrightnessFeature,
  fillFor: (value, attrs, config, hass) => brightnessColor(config, hass),
  // No trackFor: the remainder stays the slider's neutral default.
});

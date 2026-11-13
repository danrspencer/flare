/**
 * Card feature: a Kelvin `number` as HA's own slider, filled with the
 * colour it's set to. The built-in feature can't do this: its fill is the
 * tile's colour, which the FLARE section uses for the phase.
 *
 * The drag handle is hardcoded white in `ha-control-slider`, with no hook
 * to recolour it, so it blends into the fill near 6667K.
 */

import { kelvinToRgb } from './flare-curve-card.js';
import { defineValueSlider } from './flare-value-slider.js';

// Keyed on the unit, so any Kelvin number entity works, not just FLARE's.
const KELVIN_UNIT = 'K';

export function supportsKelvinFeature(hass, context) {
  const entityId = context && context.entity_id;
  const stateObj = entityId && hass && hass.states ? hass.states[entityId] : undefined;
  if (!stateObj) return false;
  if (!stateObj.entity_id.startsWith('number.')) return false;
  return (stateObj.attributes || {}).unit_of_measurement === KELVIN_UNIT;
}

// The most of the theme's text colour a near-white gets, and how fast that
// falls off as the colour saturates: an orange or blue already shows.
const MAX_TEXT_MIX = 15;
const MIX_FALLOFF = 6;

/**
 * The curve card's colour for a Kelvin, with the theme's text colour mixed
 * in by how pale it is, so a near-white still shows on a light card.
 */
export function sliderColor(kelvin) {
  const [r, g, b] = kelvinToRgb(kelvin);
  const paleness = Math.min(r, g, b) / Math.max(r, g, b);
  const mix = Math.round(MAX_TEXT_MIX * paleness ** MIX_FALLOFF);
  return `color-mix(in srgb, rgb(${r}, ${g}, ${b}) ${100 - mix}%, var(--primary-text-color))`;
}

defineValueSlider({
  tag: 'flare-kelvin-feature',
  name: 'FLARE Colour temperature',
  supported: supportsKelvinFeature,
  // Fill solid and remainder at the native 0.2 opacity, both in the value's
  // colour.
  fillFor: sliderColor,
  trackFor: sliderColor,
});

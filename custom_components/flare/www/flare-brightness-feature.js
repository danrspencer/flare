/**
 * A card feature that renders a brightness `number` as Home Assistant's
 * own slider, whose fill gets stronger as the value does.
 *
 * The dashboard section used to leave brightness on the built-in
 * slider, which takes its colour from the tile - so it showed which
 * PHASE the control belonged to and said nothing about the value.
 * Colour temperature already carried its value in its colour, and the
 * two sliders sitting side by side disagreed about what colour meant.
 *
 * Brightness has no colour of its own, so the value is carried by
 * INTENSITY instead: the theme's own accent colour, faded in proportion
 * to the value. It reads as a dimmer, which is what it is.
 *
 * Deliberately not white-fading-to-transparent, which is the most
 * literal reading of "brightness" and looked best on a dark card: at
 * full brightness on a LIGHT theme a white fill is invisible against the
 * card. That is the same trap the colour-temperature slider hits at
 * 6667K, where the temperature genuinely is near-white - and there it is
 * unavoidable, so there is no reason to introduce it a second time
 * somewhere it is a free choice.
 *
 * The colour comes from `--primary-color` via color-mix rather than a
 * hardcoded value, so it follows the user's theme.
 */

import { defineValueSlider } from './flare-value-slider.js';

// Below this the fill would be indistinguishable from the unfilled
// track, and a slider that vanishes at its low end looks broken rather
// than dim. The value is also carried by the fill's WIDTH, so this only
// has to stay visible, not encode the number on its own.
const MIN_STRENGTH = 0.1;

/**
 * How strongly to paint the fill, 0.1 to 1, across the entity's own
 * range.
 *
 * Scaled from min/max rather than assuming 0-255, so it is still right
 * for a light's brightness (0-255), a percentage (0-100), or anything
 * else someone points it at.
 */
export function fillStrength(value, { min = 0, max = 255 } = {}) {
  const span = max - min;
  const fraction = span > 0 ? (value - min) / span : 1;
  const clamped = Math.min(Math.max(fraction, 0), 1);
  return MIN_STRENGTH + (1 - MIN_STRENGTH) * clamped;
}

export function brightnessColor(value, attrs) {
  const percent = (fillStrength(value, attrs) * 100).toFixed(1);
  return `color-mix(in srgb, var(--primary-color) ${percent}%, transparent)`;
}

/**
 * Brightness is a plain `number` with no unit - which is exactly how
 * FLARE's own brightness entities are defined (number.py gives the
 * Kelvin values "K" and the transitions "min", and leaves these bare).
 *
 * A unit-less number is a weak signal, so this deliberately does NOT
 * offer itself for every such entity: it also requires the 0-255 range
 * a brightness actually has. Without that it would turn up in the card
 * editor for any unit-less number in the house.
 */
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
  fillFor: brightnessColor,
  // No trackFor: the unfilled remainder keeps the tile's own colour, as
  // the built-in slider does. Fading that too would leave a dim value
  // with almost no visible control at all, and the phase colour is
  // still worth carrying somewhere in the row.
});

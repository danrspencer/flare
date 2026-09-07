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
 * INTENSITY: the fill fades in proportion to it. It reads as a dimmer,
 * which is what it is.
 *
 * The HUE comes from somewhere else. Point `tint_from` at a
 * colour-temperature entity and the fill takes that colour, so the two
 * sliders in a row together preview what the light will actually look
 * like - hue from the temperature, intensity from the brightness:
 *
 *   features:
 *     - type: custom:flare-brightness-feature
 *       tint_from: number.downstairs_morning_kelvin
 *
 * Named `tint_from` rather than color_from/colour_from because this repo
 * writes "colour" and Home Assistant's own config keys write "color",
 * and a key someone has to type is a bad place to make them guess which.
 * It also says what it does.
 *
 * The entity is NAMED rather than derived from the brightness entity's
 * own id. The two are a fixed rename apart in FLARE's own naming
 * (`..._brightness` / `..._kelvin`), so deriving it would work here -
 * and would silently do nothing for anyone pointing this at their own
 * entities, which the unit-free check below deliberately allows.
 *
 * With no `tint_from`, or one pointing at something unreadable, the fill
 * falls back to the theme's accent at the same fading, so the feature
 * still works standalone.
 *
 * Deliberately not white-fading-to-transparent, which is the most
 * literal reading of "brightness" and looked best on a dark card: at
 * full brightness on a LIGHT theme a white fill is invisible against the
 * card. That is the same trap the colour-temperature slider hits at
 * 6667K, where the temperature genuinely is near-white - and there it is
 * unavoidable, so there is no reason to introduce it a second time
 * somewhere it is a free choice.
 *
 * The fallback colour comes from `--primary-color` via color-mix rather
 * than a hardcoded value, so it follows the user's theme - and that is
 * also ha-control-slider's own default fill, so an untinted one looks
 * like the stock slider, only fading.
 */

import { kelvinToRgb } from './flare-curve-card.js';
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

/**
 * The colour temperature this slider should borrow its hue from, or null
 * if there is none to borrow.
 *
 * Null covers every way that can go wrong - no `tint_from`, an entity
 * that does not exist, one that is unavailable - because they all want
 * the same answer: fall back to the theme colour rather than render
 * something arbitrary.
 */
export function tintKelvin(config, hass) {
  const entityId = config && config.tint_from;
  const stateObj = entityId && hass && hass.states ? hass.states[entityId] : undefined;
  if (!stateObj) return null;
  const kelvin = Number(stateObj.state);
  return Number.isNaN(kelvin) ? null : kelvin;
}

export function brightnessColor(value, attrs, config, hass) {
  const strength = fillStrength(value, attrs);
  const kelvin = tintKelvin(config, hass);
  if (kelvin === null) {
    return `color-mix(in srgb, var(--primary-color) ${(strength * 100).toFixed(1)}%, transparent)`;
  }
  const [r, g, b] = kelvinToRgb(kelvin);
  return `rgba(${r}, ${g}, ${b}, ${strength.toFixed(3)})`;
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
  // No trackFor: the unfilled remainder falls back to
  // ha-control-slider's own default, a neutral grey. Not the tile's
  // colour, which is what the built-in feature uses - a phase-tinted
  // track under a value-tinted fill reads as two different things
  // fighting, and the phase is still carried by the tile's icon.
});

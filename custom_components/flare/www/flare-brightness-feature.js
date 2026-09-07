/**
 * A card feature that renders a brightness `number` as Home Assistant's
 * own slider, in the colour the light will actually be.
 *
 * This is how HA's own `light-brightness` feature works: a solid slider
 * in the bulb's current colour, with the fill's WIDTH carrying the
 * value. Brightness has no colour of its own, so it borrows one.
 *
 * The dashboard section used to leave brightness on the built-in
 * `numeric-input` slider, which takes its colour from the tile - so it
 * showed which PHASE the control belonged to and said nothing about the
 * setting, while the colour-temperature slider beside it was already
 * painted in the value it sets.
 *
 * Point `tint_from` at a colour-temperature entity and the fill takes
 * that colour, so the two sliders in a row together preview the light -
 * the colour from the temperature, how far it fills from the brightness:
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
 * falls back to `--primary-color`, which is also ha-control-slider's own
 * default - so an untinted one is exactly the stock slider rather than
 * something odd.
 *
 * AN EARLIER VERSION ALSO FADED THE FILL by the value, floored at 0.1
 * opacity. It is recorded here because it looked reasonable and was
 * still wrong: the fill's width already says how bright, so the fade
 * said it a second time, and the only thing it added was making a dim
 * setting harder to see.
 */

import { kelvinToRgb } from './flare-curve-card.js';
import { defineValueSlider } from './flare-value-slider.js';

/**
 * The colour temperature this slider should borrow its colour from, or
 * null if there is none to borrow.
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

/**
 * The fill colour: solid, and the same colour the tinting entity's own
 * slider shows.
 *
 * Deliberately takes no value: the factory's colour functions are called
 * with (value, attributes, config, hass) and this needs only the last
 * two, because how bright it is is already carried by how far the fill
 * reaches.
 */
export function brightnessColor(config, hass) {
  const kelvin = tintKelvin(config, hass);
  if (kelvin === null) return 'var(--primary-color)';
  const [r, g, b] = kelvinToRgb(kelvin);
  return `rgb(${r}, ${g}, ${b})`;
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
  fillFor: (value, attrs, config, hass) => brightnessColor(config, hass),
  // No trackFor: the unfilled remainder falls back to
  // ha-control-slider's own default, a neutral grey. Not the tile's
  // colour, which is what the built-in feature uses - a phase-tinted
  // track under a value-coloured fill reads as two different things
  // fighting, and the phase is still carried by the tile's icon.
});

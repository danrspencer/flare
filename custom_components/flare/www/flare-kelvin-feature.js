/**
 * A card feature that renders a Kelvin-valued `number` as Home
 * Assistant's own slider, filled with the colour temperature it is set
 * to. Drag it and the fill changes colour with the value.
 *
 * Why it has to exist: `ha-control-slider` takes its fill from
 * `--control-slider-color`, which the built-in `numeric-input` feature
 * sets to `--feature-color`, which `hui-tile-card` sets to the tile's
 * own colour. That is one knob for two jobs - the FLARE dashboard
 * section spends a tile's `color` on encoding which PHASE a control
 * belongs to, so the slider cannot also carry the value. A tile card's
 * `color` takes no template either, so "tint it by the current value" is
 * not expressible in the built-in feature at all.
 *
 * It renders the frontend's own `ha-control-slider`, so handle, fill cap
 * and keyboard behaviour match the sliders beside it; only the colour is
 * ours. The drag handle CANNOT be recoloured: it is hardcoded to white on
 * `.slider .slider-track-bar::after` with no custom property and no
 * `part=`, so near the pale end of the ramp (around 6667K) it blends into
 * the fill. Reaching into the slider's shadow root would couple to an
 * internal class name, so it is left alone. card-mod is not used for the
 * same reason, and because it is a third-party dependency.
 */

import { kelvinToRgb } from './flare-curve-card.js';
import { defineValueSlider } from './flare-value-slider.js';

// Matches number.py's _CurveNumber, which sets this unit on the Kelvin
// values and no others. Keyed on the unit rather than the entity_id
// shape on purpose - it makes the feature useful for any Kelvin-valued
// number entity, not just FLARE's, and it cannot go stale if this
// integration's own naming changes.
const KELVIN_UNIT = 'K';

export function supportsKelvinFeature(hass, context) {
  const entityId = context && context.entity_id;
  const stateObj = entityId && hass && hass.states ? hass.states[entityId] : undefined;
  if (!stateObj) return false;
  if (!stateObj.entity_id.startsWith('number.')) return false;
  return (stateObj.attributes || {}).unit_of_measurement === KELVIN_UNIT;
}

/**
 * The slider's colour for a given colour temperature.
 *
 * Uses the card's own kelvinToRgb, already parity-tested against
 * curve.py, so the bar and the curve drawn above it in the same
 * dashboard section agree by construction rather than by a second copy
 * of the conversion.
 */
export function sliderColor(kelvin) {
  const [r, g, b] = kelvinToRgb(kelvin);
  return `rgb(${r}, ${g}, ${b})`;
}

defineValueSlider({
  tag: 'flare-kelvin-feature',
  name: 'FLARE Colour temperature',
  supported: supportsKelvinFeature,
  // Both halves take the value's colour - the fill solid, the remainder
  // the same colour at the native 0.2 opacity - because here the colour
  // IS the entity's identity. The built-in points both at the tile's
  // colour; this points both at the temperature.
  fillFor: sliderColor,
  trackFor: sliderColor,
});

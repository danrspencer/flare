/**
 * A custom card feature that renders a `number` entity measured in Kelvin
 * as an ordinary Home Assistant slider whose SOLID COLOUR is the colour
 * temperature it is currently set to. Slide it and the whole bar changes
 * colour with the value.
 *
 * Visually it is the built-in `numeric-input` slider and nothing more: a
 * solid fill from the left to the current value, same height, same
 * corner radius, no thumb, no text of its own (the tile already shows
 * the value). The only difference is where the colour comes from - and
 * the remainder, see TRACK below.
 *
 * Why it can't be the built-in one: that slider takes its colour from
 * `--feature-color`, which hui-tile-card sets to `var(--tile-color)`.
 * That is one knob for two jobs - the FLARE dashboard section spends a
 * tile's `color` on encoding which PHASE a control belongs to, so the
 * slider can't also carry the value. A tile card's `color` takes no
 * template either (no Lovelace core card renders Jinja), so "tint it by
 * the current Kelvin" is not expressible there at all. This feature
 * paints itself and never reads `--feature-color`, so both can be true
 * at once: the icon keeps the phase colour, the bar shows the value.
 *
 * An earlier version painted the track as a full Kelvin GRADIENT, warm
 * to cool across the entity's range, with a thumb and a value label. It
 * worked and it looked wrong - a rainbow bar reads as a colour picker,
 * not as one of a column of matching sliders. Matching the built-in
 * exactly, and changing only the colour, is the whole point. Don't
 * reintroduce the gradient. See TRACK below for the one place this
 * deliberately does NOT match the built-in, and why.
 *
 * The alternative was card-mod, which can template `--feature-color`
 * independently - rejected because the docs generator's promise is
 * paste-and-go with no third-party dependencies, and card-mod works by
 * patching frontend shadow-DOM internals, a well-known source of
 * breakage across Home Assistant upgrades. This file ships inside the
 * integration and self-registers exactly like flare-curve-card.js, so it
 * costs the user nothing to have.
 *
 * Deliberately built on a plain <input type="range"> rather than Home
 * Assistant's own ha-control-slider, which is an internal frontend
 * element with no compatibility promise - avoiding exactly the class of
 * dependency card-mod was rejected for. The native input brings pointer
 * drag, keyboard stepping, focus and correct ARIA semantics with no
 * code, and is sized from the documented --feature-* variables.
 */

import { kelvinToRgb } from './flare-curve-card.js';

// Matches number.py's _CurveNumber, which sets this unit on the Kelvin
// values and no others. Keyed on the unit rather than the entity_id
// shape on purpose - it makes the feature useful for any Kelvin-valued
// number entity, not just FLARE's, and it cannot go stale if the
// integration's own naming changes.
const KELVIN_UNIT = 'K';

// The unfilled remainder, and the hairline around the whole bar.
//
// The built-in slider tints its remainder with its own colour, and that
// is wrong here for a reason worth recording: an honest orange-to-blue
// colour-temperature ramp HAS to pass through white in the middle -
// 6667K, FLARE's own Day default, is very nearly white - and a white
// fill on a white tile with a white-tinted remainder is an invisible
// control. Dimming the whole ramp to compensate was tried and looks
// worse still: the middle goes muddy grey-brown and stops reading as
// warm white at all.
//
// So the colour stays physically true and the CONTRAST is fixed
// instead. A neutral remainder plus a hairline means the fill edge is
// legible at every temperature, including the pale ones. One fixed
// grey works in both themes - it is barely-there over a light card and
// a soft lift over a dark one. Verified in both.
const TRACK = 'rgba(128, 128, 128, 0.18)';

export function supportsKelvinFeature(hass, context) {
  const entityId = context && context.entity_id;
  const stateObj = entityId && hass && hass.states ? hass.states[entityId] : undefined;
  if (!stateObj) return false;
  if (!stateObj.entity_id.startsWith('number.')) return false;
  return (stateObj.attributes || {}).unit_of_measurement === KELVIN_UNIT;
}

/** How far along its own range the value sits, clamped to 0..1. */
export function valueFraction(value, min, max) {
  if (!(max > min)) return 0;
  return Math.min(Math.max((value - min) / (max - min), 0), 1);
}

/**
 * The slider's background: solid colour to the fill point, neutral
 * beyond it.
 *
 * Two hard stops at the same position rather than a blend, so the edge
 * is crisp - this is a fill level, not a gradient. The colour is a
 * single sample at the CURRENT VALUE, which is what makes the whole bar
 * change colour as it moves.
 *
 * Uses the card's own kelvinToRgb, already parity-tested against
 * curve.py, so the bar and the curve drawn above it in the same
 * dashboard section agree by construction rather than by a second copy
 * of the conversion.
 */
export function sliderBackground(kelvin, fraction) {
  const [r, g, b] = kelvinToRgb(kelvin);
  const fill = `rgb(${r}, ${g}, ${b})`;
  const stop = `${(Math.min(Math.max(fraction, 0), 1) * 100).toFixed(2)}%`;
  return `linear-gradient(to right, ${fill} 0%, ${fill} ${stop}, ${TRACK} ${stop}, ${TRACK} 100%)`;
}

class FlareKelvinFeature extends HTMLElement {
  static getStubConfig() {
    return { type: 'custom:flare-kelvin-feature' };
  }

  setConfig(config) {
    if (!config) throw new Error('Invalid configuration');
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set context(context) {
    this._context = context;
    this._render();
  }

  get _stateObj() {
    const entityId = this._context && this._context.entity_id;
    if (!this._hass || !entityId) return undefined;
    return this._hass.states[entityId];
  }

  _build() {
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        input {
          -webkit-appearance: none;
          appearance: none;
          display: block;
          margin: 0;
          padding: 0;
          width: 100%;
          height: var(--feature-height, 42px);
          border-radius: var(--feature-border-radius, 12px);
          cursor: pointer;
          /* See TRACK above: without this a near-white fill has no
             visible edge against a light tile. */
          box-shadow: inset 0 0 0 1px rgba(120, 120, 120, 0.35);
          /* Only ever seen for an unavailable entity - every other path
             sets a real background before paint. */
          background: var(--disabled-color, #bdbdbd);
        }
        input:focus-visible {
          outline: 2px solid var(--primary-color, #03a9f4);
          outline-offset: 2px;
        }
        /* No visible thumb: the built-in slider has none, and the fill
           edge is the indicator. Kept 2px wide rather than 0 so the
           browser still has something to grab for the drag. */
        input::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 2px;
          height: var(--feature-height, 42px);
          background: transparent;
        }
        input::-moz-range-thumb {
          width: 2px;
          height: var(--feature-height, 42px);
          border: none;
          background: transparent;
        }
      </style>
      <input type="range" />
    `;
    this._input = this.shadowRoot.querySelector('input');
    // `change` rather than `input`: `input` fires continuously through a
    // drag, which would be one service call per pixel.
    this._input.addEventListener('change', (ev) => this._setValue(ev.target.value));
    // `input` too, but only to repaint - so the colour follows the drag
    // live instead of snapping when the state comes back.
    this._input.addEventListener('input', (ev) => this._paint(Number(ev.target.value)));
  }

  _setValue(raw) {
    const stateObj = this._stateObj;
    if (!stateObj) return;
    this._hass.callService('number', 'set_value', {
      entity_id: stateObj.entity_id,
      value: Number(raw),
    });
  }

  _paint(kelvin) {
    this._input.style.background = sliderBackground(
      kelvin,
      valueFraction(kelvin, this._min, this._max)
    );
  }

  _render() {
    const stateObj = this._stateObj;
    if (!this._config || !this._hass || !stateObj) return;
    if (!this.shadowRoot) this._build();

    const attrs = stateObj.attributes || {};
    this._min = Number(attrs.min ?? 1000);
    this._max = Number(attrs.max ?? 10000);
    const value = Number(stateObj.state);

    this._input.min = this._min;
    this._input.max = this._max;
    this._input.step = Number(attrs.step ?? 1);
    this._input.setAttribute('aria-label', attrs.friendly_name || stateObj.entity_id);
    // An unavailable/unknown entity parses to NaN, which a range input
    // silently snaps to its own minimum - painting a confident 1000 K
    // bar for a value we do not have. Disable and go grey instead.
    if (Number.isNaN(value)) {
      this._input.disabled = true;
      this._input.style.background = '';
      return;
    }
    this._input.disabled = false;
    this._input.value = value;
    this._paint(value);
  }
}

customElements.define('flare-kelvin-feature', FlareKelvinFeature);

window.customCardFeatures = window.customCardFeatures || [];
window.customCardFeatures.push({
  type: 'flare-kelvin-feature',
  name: 'FLARE Colour temperature',
  // Keeps the feature out of the editor's list for entities it cannot
  // render - without it, it is offered on every entity in the house.
  isSupported: supportsKelvinFeature,
});

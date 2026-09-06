/**
 * A custom card feature that renders a `number` entity measured in Kelvin
 * as a slider whose track IS the colour temperature it sets.
 *
 * Why this exists rather than the built-in `numeric-input` feature: the
 * built-in slider paints itself in the tile's own colour, because
 * hui-tile-card sets `--feature-color: var(--tile-color)`. That is one
 * knob for two jobs - the FLARE dashboard section uses a tile's `color`
 * to encode which PHASE a control belongs to, so the slider can't also
 * carry the value. A tile card's `color` takes no template either (no
 * Lovelace core card renders Jinja), so "tint it by the current Kelvin"
 * is not expressible in the built-in feature at all.
 *
 * This feature paints its own track and never reads `--feature-color`,
 * which is what lets both things be true at once: the icon keeps the
 * phase colour, and the slider shows the colour.
 *
 * The alternative was card-mod, which can template `--feature-color`
 * independently - rejected because the docs generator's whole promise is
 * paste-and-go with no third-party dependencies, and card-mod works by
 * patching frontend shadow-DOM internals, a well-known source of
 * breakage across Home Assistant upgrades. This file ships inside the
 * integration and self-registers exactly like flare-curve-card.js, so it
 * costs the user nothing to have.
 *
 * Deliberately built on a plain <input type="range"> rather than Home
 * Assistant's own ha-control-slider. ha-control-slider is an internal
 * frontend element with no compatibility promise, and the whole point of
 * not using card-mod was to avoid depending on internals. A native range
 * input brings pointer drag, keyboard stepping, focus and correct ARIA
 * semantics with no code, and is styled below to match the built-in
 * features' dimensions via the documented --feature-* variables.
 */

import { kelvinToRgb, rgbToHex } from './flare-curve-card.js';

// Matches number.py's _CurveNumber, which sets this unit on the Kelvin
// values and no others. Keyed on the unit rather than the entity_id
// shape on purpose - it makes the feature useful for any Kelvin-valued
// number entity, not just FLARE's, and it cannot go stale if the
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
 * A CSS gradient sampling kelvinToRgb across the entity's own range.
 *
 * Sampled rather than interpolated between two endpoints because the
 * Kelvin -> RGB curve is not linear in RGB space - a straight blend from
 * the 1000K red to the 10000K blue would pass through purple, which is
 * not a colour any temperature on that scale actually is. Sixteen stops
 * is comfortably past the point where the banding is visible at slider
 * widths, and CSS interpolates between them.
 *
 * Uses the card's own kelvinToRgb so the slider and the curve drawn
 * above it in the same dashboard section agree by construction - that
 * function is already parity-tested against curve.py's Python version.
 */
export function kelvinGradient(min, max, stops = 16) {
  const lo = Math.min(min, max);
  const hi = Math.max(min, max);
  const parts = [];
  for (let i = 0; i < stops; i += 1) {
    const t = stops === 1 ? 0 : i / (stops - 1);
    parts.push(`${rgbToHex(kelvinToRgb(lo + (hi - lo) * t))} ${(t * 100).toFixed(2)}%`);
  }
  return `linear-gradient(to right, ${parts.join(', ')})`;
}

/**
 * Whether to draw the value label dark or light.
 *
 * The track spans deep amber to pale blue, so a single fixed label
 * colour is unreadable at one end whichever end you pick. Rec. 601 luma
 * of the colour actually under the label, thresholded at mid-grey.
 *
 * Called with the colour temperature AT THE LABEL'S POSITION, which is
 * the low end of the range - the label is pinned to the left of the
 * track, it does not ride the thumb. Passing the current value instead
 * looks right in a screenshot at the bottom of the range and picks dark
 * text on deep amber everywhere else, which was the first version.
 */
export function labelIsDark(kelvin) {
  const [r, g, b] = kelvinToRgb(kelvin);
  return 0.299 * r + 0.587 * g + 0.114 * b > 140;
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
        .wrap { position: relative; height: var(--feature-height, 42px); }
        input {
          -webkit-appearance: none;
          appearance: none;
          margin: 0;
          padding: 0;
          width: 100%;
          height: 100%;
          border-radius: var(--feature-border-radius, 12px);
          cursor: pointer;
          /* The gradient is set per-render; this is only the fallback
             for the moment before the entity's range is known. */
          background: var(--disabled-color, #bdbdbd);
        }
        input:focus-visible {
          outline: 2px solid var(--primary-color, #03a9f4);
          outline-offset: 2px;
        }
        /* A thin full-height bar rather than a round knob: at 42px tall
           a circular thumb reads as a separate control sitting on the
           track, where the built-in features read as one solid object. */
        input::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 6px;
          height: var(--feature-height, 42px);
          border-radius: 3px;
          background: #ffffff;
          box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35);
        }
        input::-moz-range-thumb {
          width: 6px;
          height: var(--feature-height, 42px);
          border: none;
          border-radius: 3px;
          background: #ffffff;
          box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35);
        }
        .value {
          position: absolute;
          top: 0;
          left: 12px;
          height: 100%;
          display: flex;
          align-items: center;
          font-size: 14px;
          font-weight: 500;
          /* Never eat the pointer - the input underneath owns every
             interaction, including a click that lands on the text. */
          pointer-events: none;
        }
      </style>
      <div class="wrap">
        <input type="range" />
        <span class="value"></span>
      </div>
    `;
    this._input = this.shadowRoot.querySelector('input');
    this._label = this.shadowRoot.querySelector('.value');
    // `change` rather than `input`: `input` fires continuously through a
    // drag, which would be one service call per pixel.
    this._input.addEventListener('change', (ev) => this._setValue(ev.target.value));
    // Still track `input` so the label and thumb follow the drag live,
    // without committing anything.
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
    this._label.textContent = `${Math.round(kelvin)} K`;
    this._label.style.color = labelIsDark(this._labelKelvin)
      ? 'rgba(0,0,0,0.85)'
      : 'rgba(255,255,255,0.95)';
  }

  _render() {
    const stateObj = this._stateObj;
    if (!this._config || !this._hass || !stateObj) return;
    if (!this.shadowRoot) this._build();

    const attrs = stateObj.attributes || {};
    const min = Number(attrs.min ?? 1000);
    const max = Number(attrs.max ?? 10000);
    const step = Number(attrs.step ?? 1);
    const value = Number(stateObj.state);

    this._input.min = min;
    this._input.max = max;
    this._input.step = step;
    this._input.setAttribute('aria-label', attrs.friendly_name || stateObj.entity_id);
    // An unavailable/unknown entity parses to NaN, which a range input
    // silently snaps to its own minimum - showing a confident 1000 K for
    // a value we do not have. Disable instead.
    if (Number.isNaN(value)) {
      this._input.disabled = true;
      this._input.style.background = '';
      this._label.textContent = '—';
      return;
    }
    this._input.disabled = false;
    this._input.value = value;
    this._input.style.background = kelvinGradient(min, max);
    this._labelKelvin = Math.min(min, max);
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

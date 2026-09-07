/**
 * A custom card feature that renders a `number` entity measured in Kelvin
 * as Home Assistant's own slider, filled with the colour temperature it
 * is currently set to. Drag it and the fill changes colour with the value.
 *
 * It IS the native slider: `ha-control-slider`, the same element the
 * built-in `numeric-input` feature uses, configured the same way, so the
 * handle, the rounded fill cap, the tooltip, the pointer and keyboard
 * behaviour and the a11y semantics all come from Home Assistant rather
 * than from here. The CSS block below is a copy of the frontend's own
 * `cardFeatureStyles` rule for `ha-control-slider` - deliberately
 * identical, because the point is to look like its neighbour in the row,
 * not merely similar. Exactly ONE declaration differs:
 * `--control-slider-color`, the fill, which _render sets per value.
 *
 * Two earlier versions got this wrong and are worth recording so they
 * are not re-attempted. The first painted the whole track as a
 * warm-to-cool Kelvin GRADIENT with a thumb and a value label - a
 * rainbow bar reads as a colour picker, not as one of a column of
 * matching sliders. The second was a hand-rolled <input type="range">
 * with a solid fill: it got the colour right, but had to reimplement the
 * handle and the rounded fill cap and visibly did not match the slider
 * beside it. Reusing the native element is what retires that whole class
 * of problem.
 *
 * Why the feature has to exist at all: `ha-control-slider` takes its
 * fill from `--control-slider-color`, which the built-in feature sets to
 * `--feature-color`, which `hui-tile-card` sets to the tile's own
 * `--tile-color`. That is one knob for two jobs - the FLARE dashboard
 * section spends a tile's `color` on encoding which PHASE a control
 * belongs to, so the slider cannot also carry the value. A tile card's
 * `color` takes no template either (no Lovelace core card renders
 * Jinja), so "tint it by the current Kelvin" is not expressible in the
 * built-in feature at all. Here the tile's colour still drives the icon
 * and the slider's unfilled TRACK - so the row still reads as its phase
 * - while the fill carries the temperature.
 *
 * `ha-control-slider` is a frontend internal with no compatibility
 * promise, and that is a real cost: a breaking change upstream lands
 * here. Taken deliberately, at the user's direction, over reimplementing
 * a slider - and note the rejected alternative, card-mod, is *also*
 * coupled to frontend internals AND a third-party dependency the docs
 * generator's paste-and-go promise cannot take. If it ever does break,
 * the fix is to follow whatever `hui-numeric-input-card-feature.ts` does
 * next, since this deliberately mirrors it.
 */

import { kelvinToRgb } from './flare-curve-card.js';

// Matches number.py's _CurveNumber, which sets this unit on the Kelvin
// values and no others. Keyed on the unit rather than the entity_id
// shape on purpose - it makes the feature useful for any Kelvin-valued
// number entity, not just FLARE's, and it cannot go stale if the
// integration's own naming changes.
const KELVIN_UNIT = 'K';

const SLIDER_TAG = 'ha-control-slider';

export function supportsKelvinFeature(hass, context) {
  const entityId = context && context.entity_id;
  const stateObj = entityId && hass && hass.states ? hass.states[entityId] : undefined;
  if (!stateObj) return false;
  if (!stateObj.entity_id.startsWith('number.')) return false;
  return (stateObj.attributes || {}).unit_of_measurement === KELVIN_UNIT;
}

/**
 * The slider's fill colour for a given colour temperature.
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

/**
 * Resolve `ha-control-slider` before first render.
 *
 * In practice it is already defined - any tile feature in the same view
 * pulls it in, and the generated dashboard section always has built-in
 * brightness sliders beside these. But relying on a sibling card to have
 * loaded your dependency is not a guarantee, and an undefined custom
 * element renders as an empty inline box with no error anywhere.
 * `loadCardHelpers` is the standard way a custom card forces the
 * Lovelace bundle in, which registers it along with everything else.
 *
 * Awaited once per page rather than per element: `whenDefined` never
 * resolves if the element genuinely never arrives, so a per-instance
 * promise would leave one pending promise per tile.
 */
let sliderReady;
function ensureSlider() {
  if (!sliderReady) {
    sliderReady = (async () => {
      if (customElements.get(SLIDER_TAG)) return;
      if (typeof window.loadCardHelpers === 'function') {
        try {
          await window.loadCardHelpers();
        } catch (err) {
          // Nothing useful to do here - fall through to whenDefined,
          // which still resolves if something else registers it later.
        }
      }
      await customElements.whenDefined(SLIDER_TAG);
    })();
  }
  return sliderReady;
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

  async _build() {
    this.attachShadow({ mode: 'open' });
    await ensureSlider();

    const style = document.createElement('style');
    // Copied from the frontend's cardFeatureStyles, minus
    // --control-slider-color which _render sets per value. Keep it that
    // way: any divergence here is a divergence from the slider sitting
    // next to this one in the same row.
    style.textContent = `
      :host { display: block; }
      ${SLIDER_TAG} {
        --control-slider-background: var(--feature-color);
        --control-slider-background-opacity: 0.2;
        --control-slider-thickness: var(--feature-height);
        --control-slider-border-radius: var(--feature-border-radius);
        width: 100%;
      }
    `;

    this._slider = document.createElement(SLIDER_TAG);
    // `value-changed` is the commit - once, on release.
    this._slider.addEventListener('value-changed', (ev) => this._setValue(ev.detail.value));
    // `slider-moved` fires continuously through a drag. Repaint only;
    // committing here would be one service call per pixel.
    this._slider.addEventListener('slider-moved', (ev) => this._paint(ev.detail.value));

    this.shadowRoot.append(style, this._slider);
    this._render();
  }

  _setValue(value) {
    const stateObj = this._stateObj;
    if (!stateObj || value == null) return;
    this._hass.callService('number', 'set_value', {
      entity_id: stateObj.entity_id,
      value: Number(value),
    });
  }

  _paint(kelvin) {
    if (kelvin == null || Number.isNaN(Number(kelvin))) return;
    this._slider.style.setProperty('--control-slider-color', sliderColor(Number(kelvin)));
  }

  _render() {
    const stateObj = this._stateObj;
    if (!this._config || !this._hass || !stateObj) return;
    if (!this._built) {
      this._built = this._build();
      return;
    }
    // Still resolving ha-control-slider; _build re-renders once it lands.
    if (!this._slider) return;

    const attrs = stateObj.attributes || {};
    const parsed = Number(stateObj.state);
    // Matches hui-numeric-input-card-feature: an unavailable/unknown
    // entity passes `undefined` rather than NaN, which the slider
    // renders as empty instead of snapping to its own minimum.
    const value = Number.isNaN(parsed) ? undefined : parsed;

    this._slider.value = value;
    this._slider.min = attrs.min;
    this._slider.max = attrs.max;
    this._slider.step = attrs.step;
    this._slider.unit = attrs.unit_of_measurement;
    this._slider.locale = this._hass.locale;
    this._slider.disabled = value === undefined;
    if (value !== undefined) this._paint(value);
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

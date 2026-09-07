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
 * not merely similar. Only the two COLOUR properties differ, and _paint
 * sets them per value: the built-in points both at `--feature-color`,
 * this points both at the colour of the value, so the fill is solid and
 * the remainder is that same colour at the same native 0.2 opacity.
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
 * built-in feature at all. Here the tile's colour still drives the icon,
 * so the row still reads as its phase, while the whole slider carries
 * the temperature.
 *
 * The one exception to "everything else is HA's" is the drag handle,
 * which the slider hardcodes to white with no property and no `part=`
 * to override - so a near-white fill leaves it invisible. See
 * _adoptHandleRule: one declaration injected into that instance's own
 * shadow root, which fails soft back to stock white if upstream renames
 * the class.
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

// ha-control-slider hardcodes its handle to `background-color: white`
// (`.slider .slider-track-bar::after`) - no custom property, and the
// element exposes no `part=`, so there is nothing to override from
// outside. Hence _adoptHandleRule below, which is the one place this
// file reaches into someone else's shadow DOM.
const HANDLE_LIGHT = '#ffffff';
// Near-black rather than black: a pure #000 slab on a pale fill reads as
// a hole punched in the bar. This is about the value of HA's own dark
// surfaces.
const HANDLE_DARK = '#1f1f1f';

// Below this contrast ratio against the fill, the white handle stops
// being findable - at 6667K (very nearly white) it is 1.03, i.e. gone.
//
// A minimum rather than "whichever contrasts more" on purpose: near-black
// beats white at EVERY colour temperature on this ramp, even deep amber
// (5.0 vs 3.5 at 1000K), so maximising would flip every handle dark and
// diverge from the built-in slider everywhere. The white handle is the
// native look and is kept wherever it still works; 1.6 puts the crossover
// around 3500K, so a saturated warm fill keeps white (2700K sits at 1.92,
// 3200K at 1.69) and only the pale end flips.
const WHITE_MIN_CONTRAST = 1.6;

const _channel = (c) => {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
};

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function relativeLuminance([r, g, b]) {
  return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b);
}

/**
 * The handle colour for a given colour temperature: white while that is
 * still visible against the fill, near-black once it isn't.
 */
export function handleColor(kelvin) {
  const luminance = relativeLuminance(kelvinToRgb(kelvin));
  const whiteContrast = 1.05 / (luminance + 0.05);
  return whiteContrast < WHITE_MIN_CONTRAST ? HANDLE_DARK : HANDLE_LIGHT;
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
    // Copied from the frontend's cardFeatureStyles, minus the two
    // colour properties, which _paint sets per value. Keep the rest
    // identical: any divergence here is a divergence from the slider
    // sitting next to this one in the same row.
    style.textContent = `
      :host { display: block; }
      ${SLIDER_TAG} {
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
    await this._adoptHandleRule();
    this._render();
  }

  /**
   * Recolour the slider's drag handle from inside its own shadow root.
   *
   * This is the one place the file reaches into another component's
   * internals, and it is not done lightly. The handle is
   * `.slider .slider-track-bar::after` with `background-color: white`
   * written in literally - there is no custom property for it, and
   * ha-control-slider exposes no `part=`, so no supported hook exists.
   * Without this, a fill anywhere near white leaves the handle invisible,
   * which is the whole reason for the change.
   *
   * Deliberately the smallest possible reach: one declaration, on one
   * instance we created ourselves, pointing at a variable we then set
   * from _paint. It is scoped to this element - nothing global is
   * patched, which is the substantive difference from card-mod.
   *
   * FAILS SOFT. If the internal class name changes upstream, the
   * selector simply matches nothing and the handle goes back to the
   * stock white - no error, no broken slider, just the old behaviour
   * back. Appended as a <style> after Lit's own adopted stylesheets so
   * it wins the cascade at equal specificity.
   */
  async _adoptHandleRule() {
    // Lit builds the shadow root on first update, so wait for it.
    if (this._slider.updateComplete) await this._slider.updateComplete;
    const root = this._slider.shadowRoot;
    if (!root) return;
    const patch = document.createElement('style');
    patch.textContent = `
      .slider .slider-track-bar::after {
        background-color: var(--flare-handle-color, #ffffff);
      }
    `;
    root.appendChild(patch);
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
    const color = sliderColor(Number(kelvin));
    this._slider.style.setProperty('--flare-handle-color', handleColor(Number(kelvin)));
    // Both halves of the bar take the value's colour: the fill solid,
    // the unfilled remainder the same colour at the native 0.2 opacity.
    // The built-in feature points BOTH of these at --feature-color, so
    // this is still one substitution rather than a restyle - the whole
    // control tracks the temperature instead of the tile's phase.
    this._slider.style.setProperty('--control-slider-color', color);
    this._slider.style.setProperty('--control-slider-background', color);
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

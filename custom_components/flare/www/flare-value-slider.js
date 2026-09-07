/**
 * The shared machinery behind FLARE's card features: Home Assistant's own
 * slider, coloured from the value it is set to rather than from the
 * tile.
 *
 * Two features are built on this - colour temperature and brightness -
 * and they differ only in which entities they accept and what colour a
 * value maps to. Everything else is identical, and was identical by
 * copy-paste for exactly one release before this existed. A second copy
 * of "wait for ha-control-slider, mirror cardFeatureStyles, commit on
 * value-changed but only repaint on slider-moved" is a second place for
 * that to drift.
 *
 * It renders `ha-control-slider`, the element the built-in
 * `numeric-input` feature uses, with a copy of the frontend's own
 * `cardFeatureStyles` rule for it. Only the colour properties differ,
 * and only those are set per value.
 *
 * `ha-control-slider` is a frontend internal with no compatibility
 * promise, which is an accepted cost taken deliberately over
 * reimplementing a slider - see the discarded designs recorded in
 * flare-kelvin-feature.js. If it breaks, follow whatever
 * `hui-numeric-input-card-feature.ts` does next, since this mirrors it.
 */

const SLIDER_TAG = 'ha-control-slider';

/**
 * Resolve `ha-control-slider` before first render.
 *
 * In practice it is already defined - any tile feature in the same view
 * pulls it in. But relying on a sibling card to have loaded your
 * dependency is not a guarantee, and an undefined custom element renders
 * as an empty inline box with no error anywhere. `loadCardHelpers` is
 * the standard way a custom card forces the Lovelace bundle in.
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
          // Nothing useful to do - fall through to whenDefined, which
          // still resolves if something else registers it later.
        }
      }
      await customElements.whenDefined(SLIDER_TAG);
    })();
  }
  return sliderReady;
}

/**
 * Define a card feature that renders the native slider, coloured by
 * value.
 *
 *   tag       custom element name, used as `custom:<tag>` in a config
 *   name      what the card editor calls it
 *   supported (hass, context) => boolean - which entities it is offered
 *             for, and which it refuses to render
 *   fillFor   (value, attributes) => CSS colour for the filled part
 *   trackFor  optional; the same for the unfilled remainder. Omit it and
 *             the remainder falls through to ha-control-slider's own
 *             default, a neutral grey - which is what you want when the
 *             fill's colour is not itself the entity's identity, and
 *             tinting the track would just add a second meaning.
 */
export function defineValueSlider({ tag, name, supported, fillFor, trackFor }) {
  class FlareValueSlider extends HTMLElement {
    static getStubConfig() {
      return { type: `custom:${tag}` };
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
      // The frontend's cardFeatureStyles rule for ha-control-slider,
      // minus its two COLOUR properties.
      //
      // cardFeatureStyles points both of those at --feature-color, the
      // tile's own colour. Neither is wanted here: the fill is the
      // value's, and the unfilled track is deliberately left to
      // ha-control-slider's own default - --disabled-color at 0.2, a
      // neutral grey that moves with the theme. Tinting the track with
      // the tile's colour is what made a brightness slider read as a
      // phase indicator with a bar on it.
      //
      // So --control-slider-background is never declared statically: a
      // feature that wants it sets it per value, and one that does not
      // gets Home Assistant's default. Declaring it here as well would
      // mean the per-value feature has it set twice, where whichever
      // wins depends silently on specificity.
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

    _paint(value) {
      if (value == null || Number.isNaN(Number(value))) return;
      const attrs = (this._stateObj || {}).attributes || {};
      this._slider.style.setProperty('--control-slider-color', fillFor(Number(value), attrs));
      if (trackFor) {
        this._slider.style.setProperty('--control-slider-background', trackFor(Number(value), attrs));
      }
    }

    _render() {
      const stateObj = this._stateObj;
      if (!this._config || !this._hass || !stateObj) return;
      if (!supported(this._hass, this._context)) return;
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

  customElements.define(tag, FlareValueSlider);

  window.customCardFeatures = window.customCardFeatures || [];
  window.customCardFeatures.push({
    type: tag,
    name,
    // Keeps the feature out of the editor's list for entities it cannot
    // render - without it, it is offered on every entity in the house.
    isSupported: supported,
  });
}

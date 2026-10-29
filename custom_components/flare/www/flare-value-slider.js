/**
 * Shared by FLARE's card features: HA's own `ha-control-slider`, coloured
 * from its value rather than the tile. The features differ only in which
 * entities they accept and what colour a value maps to.
 *
 * `ha-control-slider` is a frontend internal with no compatibility
 * promise. If it breaks, follow `hui-numeric-input-card-feature.ts`,
 * which this mirrors.
 */

const SLIDER_TAG = 'ha-control-slider';

/**
 * Load `ha-control-slider` before first render: an undefined element
 * renders as an empty box with no error. Once per page, since whenDefined
 * may never resolve.
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
          // whenDefined still resolves if something registers it later.
        }
      }
      await customElements.whenDefined(SLIDER_TAG);
    })();
  }
  return sliderReady;
}

/**
 * Define a card feature rendering the native slider, coloured by value.
 *
 *   tag       custom element name (`custom:<tag>`)
 *   name      what the card editor calls it
 *   supported (hass, context) => boolean
 *   fillFor   (value, attributes, config, hass) => CSS colour of the fill
 *   trackFor  optional, the same for the remainder; omitted, it's the
 *             slider's neutral default
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
      // The frontend's cardFeatureStyles rule for ha-control-slider, minus its
      // colour properties: the fill is set per value, and the track is left to
      // the slider's own default unless a feature sets it.
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
      this._slider.addEventListener('value-changed', (ev) => this._setValue(ev.detail.value));
      // Fires through a drag: repaint only.
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
      const args = [Number(value), attrs, this._config, this._hass];
      this._slider.style.setProperty('--control-slider-color', fillFor(...args));
      if (trackFor) {
        this._slider.style.setProperty('--control-slider-background', trackFor(...args));
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
      // undefined, not NaN, renders an unavailable entity as empty.
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
    // Keeps the feature out of the editor for entities it can't render.
    isSupported: supported,
  });
}

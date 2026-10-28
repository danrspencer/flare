/**
 * A Clear control, drawn like the "All off" control on Home Assistant's
 * Lights dashboard (hui-toggle-group-card): no card around it, a round icon
 * you press, and a label beside it. That card can't be reused: its icon is
 * always the power symbol and its text always on/off counts.
 *
 *   type: custom:flare-clear-card
 *   entity: button.flare_clear   # pressed; or a list, pressed together
 *
 *   type: custom:flare-clear-card
 *   area: kitchen                # clears that area's claimed lights
 */

import { claimsByArea } from './flare-entities.js';

class FlareClearCard extends HTMLElement {
  setConfig(config) {
    const entity = config && config.entity;
    const hasEntity = entity && !(Array.isArray(entity) && !entity.length);
    if (!hasEntity && !(config && config.area)) throw new Error('entity or area is required');
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  getGridOptions() {
    return { columns: 3, rows: 1 };
  }

  _press() {
    if (!this._hass) return;
    if (this._config.entity) {
      this._hass.callService('button', 'press', { entity_id: this._config.entity });
      return;
    }
    const claimed = (claimsByArea(this._hass).get(this._config.area) || {}).claimed || [];
    if (claimed.length) this._hass.callService('flare', 'claims_clear', { entities: claimed });
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; }
        .row { display: flex; align-items: center; gap: 10px; height: 100%; padding: 0 10px; }
        button {
          width: 36px; height: 36px; border-radius: 50%; border: none; padding: 0;
          display: flex; align-items: center; justify-content: center; cursor: pointer;
          color: var(--state-inactive-color, var(--secondary-text-color));
          background: color-mix(in srgb, var(--state-inactive-color, var(--secondary-text-color)) 20%, transparent);
          --mdc-icon-size: 24px;
        }
        button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
        .name { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
      </style>
      <div class="row">
        <button aria-label="Clear"><ha-icon icon="mdi:backup-restore"></ha-icon></button>
        <span class="name"></span>
      </div>
    `;
    this.shadowRoot.querySelector('.name').textContent = this._config.name || 'Clear';
    this.shadowRoot.querySelector('button').addEventListener('click', () => this._press());
  }
}

if (!customElements.get('flare-clear-card')) {
  customElements.define('flare-clear-card', FlareClearCard);
}

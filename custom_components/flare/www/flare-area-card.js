/**
 * An area's Controlled and Overridden counts, worked out live from FLARE's
 * claims sensor, as the totals' tiles show them: blue and amber while
 * above zero, grey at zero. The overridden lights are named underneath
 * while there are any.
 *
 *   type: custom:flare-area-card
 *   area: kitchen
 */

import { claimsByArea } from './flare-entities.js';

const COUNTS = [
  { key: 'controlled', name: 'Controlled', icon: 'mdi:lightbulb-group', color: 'var(--blue-color, #2196f3)' },
  { key: 'overridden', name: 'Overridden', icon: 'mdi:lightbulb-alert-outline', color: 'var(--amber-color, #ffc107)' },
];
const GREY = 'var(--grey-color, #9e9e9e)';

/** The area's counts and overridden lights' names, as the card shows them. */
export function areaSummary(hass, area) {
  const entry = claimsByArea(hass).get(area) || { controlled: [], overridden: [] };
  const name = (entityId) => hass.states?.[entityId]?.attributes?.friendly_name || entityId;
  return {
    controlled: entry.controlled.length,
    overridden: entry.overridden.length,
    overriddenNames: entry.overridden.map(name),
  };
}

class FlareAreaCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.area) throw new Error('area is required');
    this._config = config;
    this._key = null;
  }

  set hass(hass) {
    this._hass = hass;
    const summary = areaSummary(hass, this._config.area);
    const key = JSON.stringify(summary);
    if (key === this._key) return;
    this._key = key;
    this._render(summary);
  }

  getGridOptions() {
    return { columns: 9, rows: 1 };
  }

  _render(summary) {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .counts { display: grid; grid-template-columns: 1fr 1fr; gap: var(--ha-space-2, 8px); }
        ha-card { display: flex; align-items: center; gap: 10px; padding: 10px; height: 100%; box-sizing: border-box; }
        .icon {
          width: 36px; height: 36px; border-radius: 50%; flex: none;
          display: flex; align-items: center; justify-content: center; --mdc-icon-size: 24px;
        }
        .text { display: flex; flex-direction: column; min-width: 0; }
        .name { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
        .value { font-size: 12px; color: var(--secondary-text-color); }
        .overridden { margin: 8px 4px 0; font-size: 14px; color: var(--primary-text-color); }
      </style>
      <div class="counts"></div>
    `;
    const counts = this.shadowRoot.querySelector('.counts');
    for (const count of COUNTS) {
      const value = summary[count.key];
      const color = value > 0 ? count.color : GREY;
      const tile = document.createElement('ha-card');
      tile.innerHTML = `
        <div class="icon"><ha-icon></ha-icon></div>
        <div class="text"><span class="name"></span><span class="value"></span></div>
      `;
      const icon = tile.querySelector('.icon');
      icon.style.color = color;
      icon.style.background = `color-mix(in srgb, ${color} 20%, transparent)`;
      tile.querySelector('ha-icon').setAttribute('icon', count.icon);
      tile.querySelector('.name').textContent = count.name;
      tile.querySelector('.value').textContent = `${value} ${value === 1 ? 'light' : 'lights'}`;
      counts.append(tile);
    }
    if (summary.overriddenNames.length) {
      const line = document.createElement('div');
      line.className = 'overridden';
      line.textContent = `Overridden: ${summary.overriddenNames.join(', ')}`;
      this.shadowRoot.append(line);
    }
  }
}

if (!customElements.get('flare-area-card')) {
  customElements.define('flare-area-card', FlareAreaCard);
}

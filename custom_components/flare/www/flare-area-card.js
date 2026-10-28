/**
 * An area's claims, worked out live from FLARE's claims sensor and each
 * light's status sensor.
 *
 *   type: custom:flare-area-card          # Controlled and Overridden counts,
 *   area: kitchen                         # as the totals' tiles show them
 *
 *   type: custom:flare-area-lights-card   # each light: its status, what FLARE
 *   area: kitchen                         # asked for, what it shows, Clear
 */

import { claimsByArea, flareTotals } from './flare-entities.js';

const BLUE = 'var(--blue-color, #2196f3)';
const AMBER = 'var(--amber-color, #ffc107)';
const GREY = 'var(--grey-color, #9e9e9e)';
const COUNTS = [
  { key: 'controlled', name: 'Controlled', icon: 'mdi:lightbulb-group', color: BLUE },
  { key: 'overridden', name: 'Overridden', icon: 'mdi:lightbulb-alert-outline', color: AMBER },
];
const STATUSES = {
  overridden: { label: 'Overridden', color: AMBER, icon: 'mdi:lightbulb-alert-outline' },
  mismatched: { label: 'Mismatched', color: AMBER, icon: 'mdi:lightbulb-question-outline' },
  controlled: { label: 'Controlled', color: BLUE, icon: 'mdi:lightbulb-auto-outline' },
  untracked: { label: 'Untracked', color: GREY, icon: 'mdi:lightbulb-outline' },
  off: { label: 'Off', color: GREY, icon: 'mdi:lightbulb-off-outline' },
  unavailable: { label: 'Unavailable', color: GREY, icon: 'mdi:lightbulb-off-outline' },
};
// The order lights are listed in: what needs a look first.
const ORDER = ['overridden', 'mismatched', 'controlled', 'untracked', 'off', 'unavailable'];

const nameOf = (hass, entityId) => hass.states?.[entityId]?.attributes?.friendly_name || entityId;

/**
 * The area's counts, as the card shows them: from the same statuses as its
 * lights, so the two agree. Like the totals, a claimed light FLARE hasn't
 * seen report yet counts as controlled.
 */
export function areaSummary(hass, area) {
  const lights = areaLights(hass, area);
  const controlled = (l) => l.status === 'controlled' || (l.status === 'untracked' && l.claimed);
  return {
    controlled: lights.filter(controlled).length,
    overridden: lights.filter((l) => l.status === 'overridden').length,
  };
}

/** Light -> status, from each light's status sensor. */
function lightStatuses(hass) {
  const statuses = {};
  for (const entry of Object.values(hass.entities || {})) {
    if (entry.platform !== 'flare' || entry.translation_key !== 'status') continue;
    const state = hass.states?.[entry.entity_id];
    if (state?.attributes?.light) statuses[state.attributes.light] = state.state;
  }
  return statuses;
}

/**
 * Brightness as a percentage, then colour: "78% · 3000K", "off", or null
 * for nothing to say.
 */
export function describe(values) {
  if (!values) return null;
  if (values.state === 'off') return 'off';
  const parts = [];
  if (values.brightness != null) parts.push(`${Math.round((values.brightness / 255) * 100)}%`);
  if (values.color_temp_kelvin != null) parts.push(`${values.color_temp_kelvin}K`);
  else if (Array.isArray(values.rgb_color)) parts.push(`RGB ${values.rgb_color.join(', ')}`);
  return parts.length ? parts.join(' · ') : null;
}

function showing(state) {
  if (!state) return null;
  if (state.state !== 'on') return state.state;
  return describe(state.attributes) || 'on';
}

/**
 * Each of the area's room lights, as the lights card lists them:
 * {entity_id, name, status, claimed, asked, showing}, overridden and
 * mismatched first. `asked` is FLARE's last write, null with none or when
 * the light was marked as someone else's.
 */
export function areaLights(hass, area) {
  const entry = claimsByArea(hass).get(area);
  if (!entry) return [];
  const claimsSensor = flareTotals(hass).claims;
  const attributes = hass.states?.[claimsSensor]?.attributes || {};
  const claims = attributes.claims || {};
  const claimed = attributes.statuses || {};
  const sensors = lightStatuses(hass);
  return entry.lights
    .map((entityId) => {
      const claim = claims[entityId];
      const target = claim && ((claim.latest && claim.latest.target) || (claim.observed && claim.observed.target));
      return {
        entity_id: entityId,
        name: nameOf(hass, entityId),
        status: sensors[entityId] || claimed[entityId] || 'untracked',
        claimed: Boolean(claim),
        asked: describe(target),
        showing: showing(hass.states?.[entityId]),
      };
    })
    .sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || a.name.localeCompare(b.name));
}

/** A light's line under its name: "Asked 78% · 3000K, showing 20% · 3000K". */
export function detail(light) {
  if (light.asked && light.showing) return `Asked ${light.asked}, showing ${light.showing}`;
  if (light.asked) return `Asked ${light.asked}`;
  return light.showing ? `Showing ${light.showing}` : '';
}

function badge(icon, color) {
  const wrap = document.createElement('div');
  wrap.className = 'icon';
  wrap.style.color = color;
  wrap.style.background = `color-mix(in srgb, ${color} 20%, transparent)`;
  const haIcon = document.createElement('ha-icon');
  haIcon.setAttribute('icon', icon);
  wrap.append(haIcon);
  return wrap;
}

const BADGE_STYLE = `
  .icon {
    width: 36px; height: 36px; border-radius: 50%; flex: none;
    display: flex; align-items: center; justify-content: center; --mdc-icon-size: 24px;
  }
  .text { display: flex; flex-direction: column; min-width: 0; }
  .name { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
  .value { font-size: 12px; color: var(--secondary-text-color); }
`;

class FlareAreaCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.area) throw new Error('area is required');
    this._config = config;
    this._key = null;
  }

  set hass(hass) {
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
        ${BADGE_STYLE}
      </style>
      <div class="counts"></div>
    `;
    const counts = this.shadowRoot.querySelector('.counts');
    for (const count of COUNTS) {
      const value = summary[count.key];
      const tile = document.createElement('ha-card');
      tile.append(badge(count.icon, value > 0 ? count.color : GREY));
      tile.insertAdjacentHTML('beforeend', '<div class="text"><span class="name"></span><span class="value"></span></div>');
      tile.querySelector('.name').textContent = count.name;
      tile.querySelector('.value').textContent = `${value} ${value === 1 ? 'light' : 'lights'}`;
      counts.append(tile);
    }
  }
}

class FlareAreaLightsCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.area) throw new Error('area is required');
    this._config = config;
    this._key = null;
  }

  set hass(hass) {
    this._hass = hass;
    const lights = areaLights(hass, this._config.area);
    const key = JSON.stringify(lights);
    if (key === this._key) return;
    this._key = key;
    this._render(lights);
  }

  getGridOptions() {
    return { columns: 'full' };
  }

  _moreInfo(entityId) {
    this.dispatchEvent(new CustomEvent('hass-more-info', { detail: { entityId }, bubbles: true, composed: true }));
  }

  _clear(entityId) {
    this._hass?.callService('flare', 'claims_clear', { entities: [entityId] });
  }

  _render(lights) {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 4px 0; }
        .row { display: flex; align-items: center; gap: 10px; padding: 6px 10px; }
        .text { flex: 1; cursor: pointer; }
        .status { font-size: 12px; font-weight: 500; flex: none; }
        button {
          width: 32px; height: 32px; border-radius: 50%; border: none; padding: 0; flex: none;
          display: flex; align-items: center; justify-content: center; cursor: pointer;
          color: var(--secondary-text-color); background: none; --mdc-icon-size: 20px;
        }
        button:hover { background: color-mix(in srgb, var(--secondary-text-color) 15%, transparent); }
        button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
        button[hidden] { visibility: hidden; display: flex; }
        ${BADGE_STYLE}
      </style>
      <ha-card></ha-card>
    `;
    const card = this.shadowRoot.querySelector('ha-card');
    for (const light of lights) {
      const look = STATUSES[light.status] || STATUSES.untracked;
      const row = document.createElement('div');
      row.className = 'row';
      row.append(badge(look.icon, look.color));
      row.insertAdjacentHTML(
        'beforeend',
        '<div class="text"><span class="name"></span><span class="value"></span></div><span class="status"></span>' +
          '<button aria-label="Clear"><ha-icon icon="mdi:backup-restore"></ha-icon></button>'
      );
      row.querySelector('.name').textContent = light.name;
      row.querySelector('.value').textContent = detail(light);
      const status = row.querySelector('.status');
      status.textContent = look.label;
      status.style.color = look.color;
      const clear = row.querySelector('button');
      clear.hidden = !light.claimed;
      clear.title = `Clear ${light.name}`;
      clear.addEventListener('click', () => this._clear(light.entity_id));
      row.querySelector('.text').addEventListener('click', () => this._moreInfo(light.entity_id));
      card.append(row);
    }
  }
}

if (!customElements.get('flare-area-card')) {
  customElements.define('flare-area-card', FlareAreaCard);
}
if (!customElements.get('flare-area-lights-card')) {
  customElements.define('flare-area-lights-card', FlareAreaLightsCard);
}

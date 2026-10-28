/**
 * An area's lights, worked out live from each light's status sensor: a header with the area's Controlled and Overridden
 * counts and Clear all, then each light with its status, what FLARE asked
 * for, what it shows, and its own Clear.
 *
 *   type: custom:flare-area-lights-card
 *   area: kitchen
 */

import { claimsByArea, lightStatuses } from './flare-entities.js';

const BLUE = 'var(--blue-color, #2196f3)';
const AMBER = 'var(--amber-color, #ffc107)';
const GREY = 'var(--grey-color, #9e9e9e)';
const COUNTS = [
  { key: 'controlled', name: 'controlled', color: BLUE },
  { key: 'overridden', name: 'overridden', color: AMBER },
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
 * lights, so the two agree. Like the totals, only lit lights count as
 * controlled, and a claimed light FLARE hasn't seen report yet does.
 */
export function areaSummary(hass, area) {
  return summarise(areaLights(hass, area));
}

/** What Clear all clears: the lights FLARE holds a claim on. */
export function claimedIn(lights) {
  return lights.filter((light) => light.claimed).map((light) => light.entity_id);
}

function summarise(lights) {
  const controlled = (l) => l.lit && (l.status === 'controlled' || (l.status === 'untracked' && l.claimed));
  return {
    controlled: lights.filter(controlled).length,
    overridden: lights.filter((l) => l.status === 'overridden').length,
  };
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
 * {entity_id, name, status, claimed, lit, asked, showing}, overridden and
 * mismatched first. `asked` is FLARE's last write, null with none or when
 * the light was marked as someone else's.
 */
export function areaLights(hass, area) {
  const entry = claimsByArea(hass).get(area);
  if (!entry) return [];
  const lights = lightStatuses(hass);
  return entry.lights
    .map((entityId) => {
      const { status, claimed, asked } = lights.get(entityId);
      return {
        entity_id: entityId,
        name: nameOf(hass, entityId),
        status,
        claimed,
        lit: hass.states?.[entityId]?.state === 'on',
        asked: describe(asked),
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

  _clear(entityIds) {
    if (entityIds.length) this._hass?.callService('flare', 'claims_clear', { entities: entityIds });
  }

  _render(lights) {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 4px 0; }
        .header {
          display: flex; align-items: center; gap: 12px; padding: 4px 10px 8px 16px;
          border-bottom: 1px solid var(--divider-color);
        }
        .counts { flex: 1; display: flex; flex-wrap: wrap; gap: 4px 14px; }
        .count { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--secondary-text-color); }
        .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
        .header button.clear-all {
          width: auto; height: 32px; border-radius: 16px; padding: 0 12px 0 8px; gap: 6px;
          font: inherit; font-size: 13px; font-weight: 500; color: var(--primary-text-color);
        }
        .header button.clear-all:disabled { cursor: default; color: var(--disabled-text-color); background: none; }
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
    const summary = summarise(lights);
    const header = document.createElement('div');
    header.className = 'header';
    header.innerHTML =
      '<div class="counts"></div>' +
      '<button class="clear-all"><ha-icon icon="mdi:backup-restore"></ha-icon><span>Clear all</span></button>';
    for (const count of COUNTS) {
      const value = summary[count.key];
      const item = document.createElement('span');
      item.className = 'count';
      item.innerHTML = '<span class="dot"></span><span></span>';
      item.querySelector('.dot').style.background = value > 0 ? count.color : GREY;
      item.lastChild.textContent = `${value} ${count.name}`;
      header.querySelector('.counts').append(item);
    }
    const claimed = claimedIn(lights);
    const clearAll = header.querySelector('.clear-all');
    clearAll.disabled = !claimed.length;
    clearAll.addEventListener('click', () => this._clear(claimed));
    card.append(header);
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
      clear.addEventListener('click', () => this._clear([light.entity_id]));
      row.querySelector('.text').addEventListener('click', () => this._moreInfo(light.entity_id));
      card.append(row);
    }
  }
}

if (!customElements.get('flare-area-lights-card')) {
  customElements.define('flare-area-lights-card', FlareAreaLightsCard);
}

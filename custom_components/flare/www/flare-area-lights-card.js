/**
 * An area's lights, worked out live from each light's status sensor: a header with the area's Controlled and Overridden
 * counts and Clear all, then each light with its status, what FLARE asked
 * for, what it shows (any value that differs in red), and its own Clear.
 * Untracked lights sit behind a row that shows them.
 *
 *   type: custom:flare-area-lights-card
 *   area: kitchen
 */

import { claimsByArea, lightStatuses } from './flare-entities.js';
import { language, localize } from './flare-i18n.js';

const BLUE = 'var(--blue-color, #2196f3)';
const AMBER = 'var(--amber-color, #ffc107)';
const GREY = 'var(--grey-color, #9e9e9e)';
const COUNTS = [
  { key: 'controlled', color: BLUE },
  { key: 'overridden', color: AMBER },
];
const STATUSES = {
  overridden: { label: 'status.overridden', color: AMBER, icon: 'mdi:lightbulb-alert-outline' },
  mismatched: { label: 'status.mismatched', color: AMBER, icon: 'mdi:lightbulb-question-outline' },
  controlled: { label: 'status.controlled', color: BLUE, icon: 'mdi:lightbulb-auto-outline' },
  untracked: { label: 'status.untracked', color: GREY, icon: 'mdi:lightbulb-outline' },
  // No claim either way: the icon says whether it's on.
  off: { label: 'status.untracked', color: GREY, icon: 'mdi:lightbulb-off-outline' },
  unavailable: { label: 'status.unavailable', color: GREY, icon: 'mdi:lightbulb-off-outline' },
};
/** How a status is shown, in hass's language: {label, color, icon}. */
export function statusLook(status, hass) {
  const look = STATUSES[status] || STATUSES.untracked;
  return { ...look, label: localize(hass, look.label) };
}

// A light's on/off/unavailable, in hass's language; values pass through.
const WORDS = new Set(['on', 'off', 'unavailable']);
const word = (hass, text) => (WORDS.has(text) ? localize(hass, `overrides.${text}`) : text);

// The order lights are listed in: what needs a look first.
const ORDER = ['overridden', 'mismatched', 'controlled', 'untracked', 'off', 'unavailable'];

const nameOf = (hass, entityId) => hass.states?.[entityId]?.attributes?.friendly_name || entityId;

/**
 * The area's counts, as the card shows them: from the same statuses as its
 * lights, so the two agree. Like the totals, a claimed light FLARE hasn't
 * seen report yet counts as controlled.
 */
export function areaSummary(hass, area) {
  return summarise(areaLights(hass, area));
}

/** What Clear all clears: the lights FLARE holds a claim on. */
export function claimedIn(lights) {
  return lights.filter((light) => light.claimed).map((light) => light.entity_id);
}

function summarise(lights) {
  const controlled = (l) => l.status === 'controlled' || (l.status === 'untracked' && l.claimed);
  return {
    controlled: lights.filter(controlled).length,
    overridden: lights.filter((l) => l.status === 'overridden').length,
  };
}

/**
 * Brightness as a percentage, then colour, as parts naming the value each
 * shows: [{value: 'brightness', text: '78%'}, {value: 'color', text:
 * '3000K'}], [{value: 'state', text: 'off'}], or null for nothing to say.
 */
export function parts(values) {
  if (!values) return null;
  if (values.state === 'off') return [{ value: 'state', text: 'off' }];
  const found = [];
  if (values.brightness != null) {
    found.push({ value: 'brightness', text: `${Math.round((values.brightness / 255) * 100)}%` });
  }
  if (values.color_temp_kelvin != null) found.push({ value: 'color', text: `${values.color_temp_kelvin}K` });
  else if (Array.isArray(values.rgb_color)) found.push({ value: 'color', text: `RGB ${values.rgb_color.join(', ')}` });
  return found.length ? found : null;
}

/** parts() as one line: "78% · 3000K", "off", or null. */
export function describe(values) {
  const found = parts(values);
  return found && found.map((part) => part.text).join(' · ');
}

function showing(state) {
  if (!state) return null;
  if (state.state !== 'on') return [{ value: 'state', text: state.state }];
  return parts(state.attributes) || [{ value: 'state', text: 'on' }];
}

// Parts with on/off/unavailable in hass's language.
const translated = (hass, found) => found && found.map((part) => ({ ...part, text: word(hass, part.text) }));

/** A light that isn't FLARE's: kept behind the card's "untracked" row. */
export const isUntracked = (light) => !light.claimed && (light.status === 'untracked' || light.status === 'off');

/**
 * Each of the area's room lights, as the lights card lists them:
 * {entity_id, name, status, claimed, asked, showing, differs}, overridden
 * and mismatched first. `asked` and `showing` are parts(); `asked` is
 * FLARE's last write, null with none or when the light was marked as
 * someone else's. `differs` names the values it shows that aren't what was
 * asked, by the same rule as override protection.
 */
export function areaLights(hass, area) {
  const entry = claimsByArea(hass).get(area);
  if (!entry) return [];
  const lights = lightStatuses(hass);
  return entry.lights
    .map((entityId) => {
      const { status, claimed, asked, differs } = lights.get(entityId);
      return {
        entity_id: entityId,
        name: nameOf(hass, entityId),
        status,
        claimed,
        asked: translated(hass, parts(asked)),
        showing: translated(hass, showing(hass.states?.[entityId])),
        differs,
      };
    })
    .sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || a.name.localeCompare(b.name));
}

/**
 * The lines under a light's name, each {label, parts}: what FLARE asked
 * for, then what it shows, its parts marked `differs` where they aren't what
 * was asked.
 */
export function detail(light, hass) {
  const lines = [];
  if (light.asked) lines.push({ label: localize(hass, 'overrides.asked'), parts: light.asked });
  if (light.showing) {
    const differs = new Set(light.differs);
    lines.push({
      label: localize(hass, 'overrides.showing'),
      parts: light.showing.map((part) => ({ ...part, differs: differs.has(part.value) || differs.has('state') })),
    });
  }
  return lines;
}

// The lines as a two-column grid, so each line's values start together.
function detailLines(lines) {
  const grid = document.createElement('div');
  grid.className = 'values';
  for (const { label, parts: found } of lines) {
    const name = document.createElement('span');
    name.textContent = label;
    const line = document.createElement('span');
    found.forEach((part, index) => {
      if (index) line.append(' · ');
      const text = document.createElement('span');
      text.textContent = part.text;
      if (part.differs) text.className = 'differs';
      line.append(text);
    });
    grid.append(name, line);
  }
  return grid;
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
  .values {
    display: grid; grid-template-columns: auto 1fr; column-gap: 6px;
    font-size: 12px; color: var(--secondary-text-color);
  }
  .values .differs { color: var(--error-color, #db4437); font-weight: 500; }
`;

class FlareAreaLightsCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.area) throw new Error('area is required');
    this._config = config;
    this._key = null;
    this._showUntracked = false;
  }

  set hass(hass) {
    this._hass = hass;
    const lights = areaLights(hass, this._config.area);
    const key = JSON.stringify([language(hass), lights, this._showUntracked]);
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
        ha-card { padding: 4px 0; overflow: hidden; }
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
        .untracked {
          display: flex; align-items: center; gap: 10px; width: 100%; height: auto; border-radius: 0;
          padding: 8px 16px; font: inherit; font-size: 13px; color: var(--secondary-text-color);
          border-top: 1px solid var(--divider-color);
        }
        .untracked:hover { background: color-mix(in srgb, var(--secondary-text-color) 8%, transparent); }
        .untracked:focus-visible { outline-offset: -2px; }
        /* Last in the card: down to its edge, clipped to its corners. */
        .untracked:last-child { margin-bottom: -4px; }
        .untracked span { flex: 1; text-align: left; }
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
      '<button class="clear-all"><ha-icon icon="mdi:backup-restore"></ha-icon><span></span></button>';
    header.querySelector('.clear-all span').textContent = localize(this._hass, 'overrides.clear_all');
    for (const count of COUNTS) {
      const value = summary[count.key];
      const item = document.createElement('span');
      item.className = 'count';
      item.innerHTML = '<span class="dot"></span><span></span>';
      item.querySelector('.dot').style.background = value > 0 ? count.color : GREY;
      item.lastChild.textContent = localize(this._hass, `overrides.count_${count.key}`, { count: value });
      header.querySelector('.counts').append(item);
    }
    const claimed = claimedIn(lights);
    const clearAll = header.querySelector('.clear-all');
    clearAll.disabled = !claimed.length;
    clearAll.addEventListener('click', () => this._clear(claimed));
    card.append(header);
    const untracked = lights.filter(isUntracked);
    for (const light of lights.filter((l) => !isUntracked(l))) card.append(this._row(light));
    if (!untracked.length) return;
    const toggle = document.createElement('button');
    toggle.className = 'untracked';
    toggle.setAttribute('aria-expanded', String(this._showUntracked));
    toggle.innerHTML = '<span></span><ha-icon></ha-icon>';
    toggle.querySelector('span').textContent = localize(
      this._hass,
      this._showUntracked ? 'overrides.hide_untracked' : 'overrides.show_untracked',
      { count: untracked.length }
    );
    toggle.querySelector('ha-icon').setAttribute('icon', this._showUntracked ? 'mdi:chevron-up' : 'mdi:chevron-down');
    toggle.addEventListener('click', () => {
      this._showUntracked = !this._showUntracked;
      this.hass = this._hass;
    });
    card.append(toggle);
    if (this._showUntracked) for (const light of untracked) card.append(this._row(light));
  }

  _row(light) {
    const look = statusLook(light.status, this._hass);
    const row = document.createElement('div');
    row.className = 'row';
    row.append(badge(look.icon, look.color));
    row.insertAdjacentHTML(
      'beforeend',
      '<div class="text"><span class="name"></span></div><span class="status"></span>' +
        '<button><ha-icon icon="mdi:backup-restore"></ha-icon></button>'
    );
    row.querySelector('.name').textContent = light.name;
    row.querySelector('.text').append(detailLines(detail(light, this._hass)));
    const status = row.querySelector('.status');
    status.textContent = look.label;
    status.style.color = look.color;
    const clear = row.querySelector('button');
    clear.hidden = !light.claimed;
    clear.title = localize(this._hass, 'overrides.clear_light', { name: light.name });
    clear.setAttribute('aria-label', clear.title);
    clear.addEventListener('click', () => this._clear([light.entity_id]));
    row.querySelector('.text').addEventListener('click', () => this._moreInfo(light.entity_id));
    return row;
  }
}

if (!customElements.get('flare-area-lights-card')) {
  customElements.define('flare-area-lights-card', FlareAreaLightsCard);
}

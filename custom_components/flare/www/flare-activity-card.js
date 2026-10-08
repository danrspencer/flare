/**
 * The zones' Activity: what each zone did, from the logbook's live stream
 * for the zones' devices, coloured and filtered by kind. An event's kind is
 * the zone entity it's filed under (sensor.py's _zone_data): its
 * Controlled or Overridden count, or Clear for a release.
 *
 *   type: custom:flare-activity-card
 *   device_id: [<zone device id>, ...]
 *   hours_to_show: 24   # optional
 */

import { flareDevices } from './flare-entities.js';

const DEFAULT_HOURS_TO_SHOW = 24;
const FILTER_KEY = 'flare-activity-filter';

// The tiles' colours, so an entry matches the count it changed.
export const KINDS = [
  { key: 'controlled', role: 'controlled', label: 'Controlled', color: 'var(--blue-color, #2196f3)' },
  { key: 'overridden', role: 'overridden', label: 'Overridden', color: 'var(--amber-color, #ffc107)' },
  { key: 'cleared', role: 'clear', label: 'Cleared', color: 'var(--grey-color, #9e9e9e)' },
];

/** entity_id -> {kind, device} for the zones' devices. */
export function entityKinds(hass, deviceIds) {
  const devices = flareDevices(hass);
  const kinds = {};
  for (const device of deviceIds) {
    const roles = devices.get(device) || {};
    for (const kind of KINDS) {
      if (roles[kind.role]) kinds[roles[kind.role]] = { kind: kind.key, device };
    }
  }
  return kinds;
}

/**
 * The entries to show, newest first: FLARE's own events (a Clear press is
 * also logged as the button's state change, which has no message) of the
 * chosen kind, from `since` on.
 */
export function visibleEntries(entries, kinds, chosen, since) {
  return entries
    .filter((e) => e.message && kinds[e.entity_id] && e.when >= since)
    .filter((e) => chosen === 'all' || kinds[e.entity_id].kind === chosen)
    .sort((a, b) => b.when - a.when);
}

const escape = (text) =>
  String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

function readFilter() {
  try {
    return window.localStorage.getItem(FILTER_KEY) || 'all';
  } catch {
    return 'all';
  }
}

function saveFilter(value) {
  try {
    window.localStorage.setItem(FILTER_KEY, value);
  } catch {
    // Remembering it is only a convenience.
  }
}

class FlareActivityCard extends HTMLElement {
  constructor() {
    super();
    this._entries = [];
    this._filter = readFilter();
  }

  setConfig(config) {
    const devices = config && config.device_id;
    if (!Array.isArray(devices) || !devices.length) throw new Error('device_id is required');
    this._config = config;
    this._unsubscribe();
    this._entries = [];
    this._subscribe();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._subscribe();
      this._render();
    }
  }

  connectedCallback() {
    this._subscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  // Fills the space it's given; rows: 'auto' leaves the height to its CSS.
  getGridOptions() {
    return { columns: 12, rows: 'auto' };
  }

  _hours() {
    return this._config.hours_to_show || DEFAULT_HOURS_TO_SHOW;
  }

  _subscribe() {
    if (this._subscription || !this._hass || !this._config) return;
    const start = new Date(Date.now() - this._hours() * 3600 * 1000).toISOString();
    this._subscription = this._hass.connection.subscribeMessage((message) => this._received(message), {
      type: 'logbook/event_stream',
      start_time: start,
      device_ids: this._config.device_id,
    });
  }

  _unsubscribe() {
    const subscription = this._subscription;
    this._subscription = null;
    if (subscription) subscription.then((unsub) => unsub()).catch(() => {});
  }

  _received(message) {
    if (message && Array.isArray(message.events) && message.events.length) {
      this._entries = this._entries.concat(message.events);
    }
    this._render();
  }

  _formatTime(when) {
    const language = this._hass && this._hass.locale && this._hass.locale.language;
    return new Date(when * 1000).toLocaleTimeString(language, { hour: '2-digit', minute: '2-digit' });
  }

  _formatDay(when) {
    const language = this._hass && this._hass.locale && this._hass.locale.language;
    const date = new Date(when * 1000);
    const day = date.toLocaleDateString(language, { day: 'numeric', month: 'long' });
    return date.toDateString() === new Date().toDateString() ? `Today · ${day}` : day;
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: 'open' });
      this.shadowRoot.addEventListener('click', (ev) => this._clicked(ev));
    }
    const kinds = entityKinds(this._hass, this._config.device_id);
    const since = Date.now() / 1000 - this._hours() * 3600;
    const entries = visibleEntries(this._entries, kinds, this._filter, since);
    const colour = Object.fromEntries(KINDS.map((k) => [k.key, k.color]));

    const chips = [{ key: 'all', label: 'All' }, ...KINDS]
      .map(
        (k) =>
          `<button class="chip" data-filter="${k.key}" aria-pressed="${this._filter === k.key}">` +
          (k.color ? `<span class="dot" style="background:${k.color}"></span>` : '') +
          `${escape(k.label)}</button>`
      )
      .join('');

    let day = null;
    const rows = entries
      .map((e) => {
        const thisDay = this._formatDay(e.when);
        const header = thisDay !== day ? `<h4 class="day">${escape(thisDay)}</h4>` : '';
        day = thisDay;
        const { kind, device } = kinds[e.entity_id];
        return (
          `${header}<div class="entry" role="link" tabindex="0" data-device="${escape(device)}">` +
          `<span class="dot" style="background:${colour[kind]}"></span>` +
          `<span class="text"><b>${escape(e.name)}</b> ${escape(e.message)}</span>` +
          `<time>${escape(this._formatTime(e.when))}</time></div>`
        );
      })
      .join('');

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card {
          display: flex; flex-direction: column;
          height: max(385px, calc(100vh - var(--header-height, 56px) - 120px));
        }
        .chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 16px 4px; }
        .chip {
          display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
          font: inherit; font-size: 13px; padding: 4px 12px; border-radius: 16px;
          border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
        }
        .chip[aria-pressed="true"] { background: rgba(var(--rgb-primary-color), 0.15); border-color: var(--primary-color); }
        .list { flex: 1; min-height: 0; overflow-y: auto; padding: 0 0 12px; }
        .day { margin: 12px 16px 4px; font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
        .entry { display: flex; align-items: baseline; gap: 10px; padding: 6px 16px; cursor: pointer; border-radius: 8px; }
        .entry:hover { background: rgba(var(--rgb-primary-text-color), 0.04); }
        .entry:focus-visible { outline: 2px solid var(--primary-color); }
        .dot { flex: none; width: 10px; height: 10px; border-radius: 50%; }
        .entry .dot { transform: translateY(1px); }
        .text { flex: 1; color: var(--primary-text-color); }
        time { flex: none; font-size: 12px; color: var(--secondary-text-color); }
        .empty { padding: 16px; color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="chips">${chips}</div>
        <div class="list">${rows || `<div class="empty">Nothing in the last ${this._hours()} hours.</div>`}</div>
      </ha-card>
    `;
  }

  _clicked(ev) {
    const path = ev.composedPath ? ev.composedPath() : [ev.target];
    const chip = path.find((el) => el && el.dataset && el.dataset.filter);
    if (chip) {
      this._filter = chip.dataset.filter;
      saveFilter(this._filter);
      this._render();
      return;
    }
    const entry = path.find((el) => el && el.dataset && el.dataset.device);
    if (entry) {
      window.history.pushState(null, '', `/config/devices/device/${entry.dataset.device}`);
      window.dispatchEvent(new CustomEvent('location-changed'));
    }
  }
}

if (!customElements.get('flare-activity-card')) {
  customElements.define('flare-activity-card', FlareActivityCard);
}

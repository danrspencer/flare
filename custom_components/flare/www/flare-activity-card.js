/**
 * The zones' Activity: what each zone did, from the logbook's live stream
 * for the zones' devices, coloured and filtered by kind. An event's kind is
 * the zone entity it's filed under (sensor.py's _zone_data): its
 * Controlled or Overridden count, or Clear for a release.
 *
 * Each row is Home Assistant's own `ha-logbook-entry`, with its dot in the
 * kind's colour (`nodeColor`, HA 2026.10), so the card looks like HA's
 * logbook. The list around the rows - day headings and a scrolling box -
 * copies `ha-logbook-renderer`, which can't colour rows individually.
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

const dayOf = (when) => new Date(when * 1000).setHours(0, 0, 0, 0);

/**
 * The list as `ha-logbook-renderer` lays it out: a heading before each
 * day's first entry, and each entry told whether it's first or last of its
 * day (which trims the timeline's rail), with its kind's colour.
 */
export function plan(entries, kinds) {
  const colour = Object.fromEntries(KINDS.map((k) => [k.key, k.color]));
  const rows = [];
  entries.forEach((item, index) => {
    const firstOfDay = index === 0 || dayOf(item.when) !== dayOf(entries[index - 1].when);
    const lastOfDay = index === entries.length - 1 || dayOf(item.when) !== dayOf(entries[index + 1].when);
    if (firstOfDay) rows.push({ day: item.when });
    const { kind, device } = kinds[item.entity_id];
    rows.push({ item, device, nodeColor: colour[kind], firstOfDay, lastOfDay });
  });
  return rows;
}

/** "Today · 8 October 2026", as `ha-logbook-renderer` heads a day. */
export function dayHeading(when, language) {
  const date = new Date(when * 1000);
  const full = date.toLocaleDateString(language, { day: 'numeric', month: 'long', year: 'numeric' });
  const diffDays = Math.round((dayOf(Date.now() / 1000) - dayOf(when)) / 86400000);
  if (diffDays !== 0 && diffDays !== 1) return full;
  const relative = new Intl.RelativeTimeFormat(language, { numeric: 'auto' }).format(-diffDays, 'day');
  return `${relative[0].toUpperCase()}${relative.slice(1)} · ${full}`;
}

// ha-logbook-entry is loaded with the built-in logbook card, not up front.
async function loadLogbookEntry() {
  if (customElements.get('ha-logbook-entry')) return;
  const helpers = await window.loadCardHelpers();
  helpers.createCardElement({ type: 'logbook', target: { entity_id: [] } });
  await customElements.whenDefined('ha-logbook-entry');
}

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

const STYLE = `
  :host { display: block; height: 100%; }
  ha-card { display: flex; flex-direction: column; height: 100%; }
  .chips { display: flex; flex-wrap: wrap; gap: var(--ha-space-2, 8px); padding: var(--ha-space-3, 12px) var(--ha-space-4, 16px) 0; }
  .chip {
    display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
    font: inherit; font-size: var(--ha-font-size-s, 12px); padding: 4px 12px; border-radius: 16px;
    border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
  }
  .chip[aria-pressed="true"] { background: rgba(var(--rgb-primary-color), 0.15); border-color: var(--primary-color); }
  .dot { width: 8px; height: 8px; border-radius: 50%; }
  /* ha-logbook-renderer's container and day heading. */
  .list { flex: 1; min-height: 0; overflow-y: auto; padding-bottom: var(--ha-space-4, 16px); }
  .date {
    margin: var(--ha-space-2, 8px) 0 0;
    padding: var(--ha-space-2, 8px) var(--logbook-horizontal-padding, var(--ha-space-4, 16px)) 0;
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .empty { padding: var(--ha-space-4, 16px); text-align: center; color: var(--secondary-text-color); }
`;

class FlareActivityCard extends HTMLElement {
  constructor() {
    super();
    this._entries = [];
    this._filter = readFilter();
    this._rows = [];
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
    for (const row of this._rows) row.hass = hass;
    if (first) {
      this._subscribe();
      this._loading = loadLogbookEntry().then(() => this._render());
    }
  }

  connectedCallback() {
    this._subscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  getGridOptions() {
    return { columns: 12, rows: 6, min_rows: 3 };
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

  _skeleton() {
    if (this.shadowRoot) return;
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="chips"></div><div class="list"></div></ha-card>`;
    this.shadowRoot.addEventListener('click', (ev) => this._chipClicked(ev));
    // A row fires this when selected, as it does inside HA's logbook.
    this.shadowRoot.addEventListener('logbook-entry-selected', (ev) => this._entrySelected(ev));
  }

  _render() {
    if (!this._config || !this._hass || !customElements.get('ha-logbook-entry')) return;
    this._skeleton();
    const language = this._hass.locale && this._hass.locale.language;
    const kinds = entityKinds(this._hass, this._config.device_id);
    const since = Date.now() / 1000 - this._hours() * 3600;
    this._kinds = kinds;

    const chips = this.shadowRoot.querySelector('.chips');
    chips.innerHTML = [{ key: 'all', label: 'All' }, ...KINDS]
      .map(
        (k) =>
          `<button class="chip" data-filter="${k.key}" aria-pressed="${this._filter === k.key}">` +
          (k.color ? `<span class="dot" style="background:${k.color}"></span>` : '') +
          `${k.label}</button>`
      )
      .join('');

    const list = this.shadowRoot.querySelector('.list');
    list.replaceChildren();
    this._rows = [];
    const rows = plan(visibleEntries(this._entries, kinds, this._filter, since), kinds);
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = this._hass.localize('ui.components.logbook.entries_not_found');
      list.append(empty);
      return;
    }
    for (const row of rows) {
      if (row.day !== undefined) {
        const heading = document.createElement('h4');
        heading.className = 'date';
        heading.textContent = dayHeading(row.day, language);
        list.append(heading);
        continue;
      }
      const entry = document.createElement('ha-logbook-entry');
      Object.assign(entry, {
        hass: this._hass,
        item: row.item,
        narrow: true,
        noIcon: true,
        nodeColor: row.nodeColor,
        firstOfDay: row.firstOfDay,
        lastOfDay: row.lastOfDay,
      });
      list.append(entry);
      this._rows.push(entry);
    }
  }

  _chipClicked(ev) {
    const chip = ev.composedPath().find((el) => el && el.dataset && el.dataset.filter);
    if (!chip) return;
    this._filter = chip.dataset.filter;
    saveFilter(this._filter);
    this._render();
  }

  _entrySelected(ev) {
    ev.stopPropagation();
    const item = ev.detail && ev.detail.item;
    const zone = item && this._kinds && this._kinds[item.entity_id];
    if (!zone) return;
    window.history.pushState(null, '', `/config/devices/device/${zone.device}`);
    window.dispatchEvent(new CustomEvent('location-changed'));
  }
}

if (!customElements.get('flare-activity-card')) {
  customElements.define('flare-activity-card', FlareActivityCard);
}

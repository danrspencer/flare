/**
 * The zones' Activity: Home Assistant's own logbook, asked for by device
 * as a device page asks, so it shows the same entries as each zone's page.
 * The built-in logbook card asks by entity only, and the logbook leaves
 * out sensors with units, which is where FLARE files a zone's events.
 *
 *   type: custom:flare-activity-card
 *   device_id: [<zone device id>, ...]
 *   hours_to_show: 24   # optional
 */

const DEFAULT_HOURS_TO_SHOW = 24;

// ha-logbook is loaded with the built-in logbook card, not up front.
async function loadLogbook() {
  if (customElements.get('ha-logbook')) return;
  const helpers = await window.loadCardHelpers();
  helpers.createCardElement({ type: 'logbook', target: { entity_id: [] } });
  await customElements.whenDefined('ha-logbook');
}

// What a device page passes: the devices' entities, and the devices.
export function devicesEntities(hass, deviceIds) {
  const wanted = new Set(deviceIds);
  return Object.values((hass && hass.entities) || {})
    .filter((entry) => wanted.has(entry.device_id))
    .map((entry) => entry.entity_id)
    .sort();
}

class FlareActivityCard extends HTMLElement {
  setConfig(config) {
    const devices = config && config.device_id;
    if (!Array.isArray(devices) || !devices.length) throw new Error('device_id is required');
    this._config = config;
    if (this._logbook) this._configure();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._logbook) {
      this._logbook.hass = hass;
      this._configure();
    } else if (!this._loading) {
      this._loading = loadLogbook().then(() => this._render());
    }
  }

  getGridOptions() {
    return { columns: 12, rows: 6, min_rows: 3 };
  }

  _configure() {
    const deviceIds = this._config.device_id;
    const entityIds = devicesEntities(this._hass, deviceIds);
    // A new array makes ha-logbook resubscribe, so only on a real change.
    if (String(entityIds) !== String(this._logbook.entityIds)) this._logbook.entityIds = entityIds;
    if (String(deviceIds) !== String(this._logbook.deviceIds)) this._logbook.deviceIds = [...deviceIds];
    const recent = (this._config.hours_to_show || DEFAULT_HOURS_TO_SHOW) * 60 * 60;
    if (!this._logbook.time || this._logbook.time.recent !== recent) this._logbook.time = { recent };
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; }
        ha-card { height: 100%; display: flex; flex-direction: column; }
        .content { flex: 1; min-height: 0; padding: 16px 0; }
        ha-logbook { display: block; height: 100%; }
      </style>
      <ha-card><div class="content"></div></ha-card>
    `;
    const logbook = document.createElement('ha-logbook');
    logbook.narrow = true;
    logbook.virtualize = true;
    logbook.noIcon = true;
    logbook.hass = this._hass;
    this._logbook = logbook;
    this._configure();
    this.shadowRoot.querySelector('.content').appendChild(logbook);
  }
}

if (!customElements.get('flare-activity-card')) {
  customElements.define('flare-activity-card', FlareActivityCard);
}

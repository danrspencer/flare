/**
 * FLARE Schedule Transfer card: copy a schedule out as YAML, or paste one
 * in. The text comes from and goes to flare.export_schedule /
 * flare.import_schedule, so the card holds no copy of the format.
 *
 *   type: custom:flare-schedule-transfer-card
 *   sensor: downstairs   # the schedule sensor's slug
 *
 * Pasting goes through a text box rather than reading the clipboard,
 * which browsers only allow over HTTPS.
 */

/** The schedule's device, through its sensor's registry entry. */
export function scheduleDeviceId(hass, slug) {
  const entry = hass && hass.entities && hass.entities[`sensor.${slug}_flare`];
  return (entry && entry.device_id) || null;
}

export async function exportSchedule(hass, deviceId) {
  const result = await hass.callService(
    'flare',
    'export_schedule',
    { schedule_device_id: deviceId },
    undefined,
    false,
    true
  );
  return result.response.schedule;
}

export async function importSchedule(hass, deviceId, text) {
  await hass.callService('flare', 'import_schedule', { schedule_device_id: deviceId, schedule: text }, undefined, false);
}

/**
 * HA's own copy helper, in short: the Clipboard API where the page is
 * allowed it, otherwise a hidden textarea and execCommand, which works
 * over plain HTTP. False if neither did.
 */
export async function copyText(text, root) {
  if (globalThis.navigator && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Not allowed here; try the fallback.
    }
  }
  const el = document.createElement('textarea');
  el.value = text;
  el.setAttribute('readonly', '');
  el.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
  root.appendChild(el);
  el.select();
  let copied = false;
  try {
    copied = document.execCommand('copy');
  } catch {
    copied = false;
  }
  root.removeChild(el);
  return copied;
}

const STYLE = `
  ha-card { padding: 12px 16px; }
  .row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .label { flex: 1; min-width: 10em; color: var(--secondary-text-color); }
  button {
    font: inherit; padding: 6px 14px; border-radius: 18px; cursor: pointer;
    border: 1px solid var(--divider-color); background: none; color: var(--primary-color);
  }
  button.primary { background: var(--primary-color); color: var(--text-primary-color); border-color: transparent; }
  textarea {
    box-sizing: border-box; width: 100%; min-height: 12em; margin-top: 8px;
    font-family: var(--code-font-family, monospace); font-size: 0.9em;
    background: var(--code-editor-background-color, var(--card-background-color));
    color: var(--primary-text-color); border: 1px solid var(--divider-color); border-radius: 8px; padding: 8px;
  }
  .status { margin-top: 8px; color: var(--secondary-text-color); white-space: pre-wrap; }
  .status.error { color: var(--error-color); }
  [hidden] { display: none !important; }
`;

class FlareScheduleTransferCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.sensor) throw new Error('Set `sensor` to a FLARE schedule sensor, e.g. sensor: downstairs');
    this._config = config;
    if (!this.shadowRoot) this._build();
  }

  set hass(hass) {
    this._hass = hass;
  }

  getCardSize() {
    return 1;
  }

  getGridOptions() {
    return { columns: 'full', rows: 'auto' };
  }

  _build() {
    const root = this.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="row">
          <span class="label">Copy this schedule to keep or share, or paste one in.</span>
          <button id="copy">Copy</button>
          <button id="paste">Paste</button>
        </div>
        <div id="editor" hidden>
          <textarea id="text" spellcheck="false" placeholder="Paste a schedule here"></textarea>
          <div class="row">
            <span class="label"></span>
            <button id="cancel">Cancel</button>
            <button id="apply" class="primary">Apply</button>
          </div>
        </div>
        <div id="status" class="status" hidden></div>
      </ha-card>`;
    const $ = (id) => root.getElementById(id);
    $('copy').addEventListener('click', () => this._copy());
    $('paste').addEventListener('click', () => this._openEditor(''));
    $('cancel').addEventListener('click', () => this._closeEditor());
    $('apply').addEventListener('click', () => this._apply());
    this._$ = $;
  }

  _deviceId() {
    const id = scheduleDeviceId(this._hass, this._config.sensor);
    if (!id) this._status(`No FLARE schedule called sensor.${this._config.sensor}_flare.`, true);
    return id;
  }

  async _copy() {
    const deviceId = this._deviceId();
    if (!deviceId) return;
    try {
      const text = await exportSchedule(this._hass, deviceId);
      if (await copyText(text, this.shadowRoot)) {
        this._closeEditor();
        this._status('Copied.');
      } else {
        // Nothing would copy: show it to select by hand.
        this._openEditor(text);
        this._$('text').select();
        this._status('Copy the schedule from the box above.');
      }
    } catch (err) {
      this._status(err.message || String(err), true);
    }
  }

  async _apply() {
    const deviceId = this._deviceId();
    if (!deviceId) return;
    try {
      await importSchedule(this._hass, deviceId, this._$('text').value);
      this._closeEditor();
      this._status('Schedule imported.');
    } catch (err) {
      this._status(err.message || String(err), true);
    }
  }

  _openEditor(text) {
    this._$('text').value = text;
    this._$('editor').hidden = false;
    this._status('');
  }

  _closeEditor() {
    this._$('editor').hidden = true;
  }

  _status(text, isError = false) {
    const el = this._$('status');
    el.textContent = text;
    el.hidden = !text;
    el.classList.toggle('error', isError);
  }
}

customElements.define('flare-schedule-transfer-card', FlareScheduleTransferCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'flare-schedule-transfer-card',
  name: 'FLARE Schedule Transfer',
  description: 'Copy a FLARE schedule out as YAML, or paste one in.',
  documentationURL: 'https://danrspencer.github.io/flare/dashboard/',
});

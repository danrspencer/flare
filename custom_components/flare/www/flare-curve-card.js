/**
 * FLARE Curve card: the day's brightness and colour-temperature curve,
 * drawn in the colour it renders. Reads the schedule sensor's `points`
 * rather than recomputing the curve. The "now" values follow a phase
 * override; the curve doesn't.
 */

const DEFAULT_ENTITIES = {
  // Fallback when a card has neither `sensor` nor `entities`.
  phase: 'sensor.default_flare',
  brightness_now: 'sensor.default_flare',
  kelvin_now: 'sensor.default_flare',
  sun: 'sun.sun',
};

// Re-render interval, and the granularity of "now" in the render cache.
const RENDER_INTERVAL_MS = 30000;

let _instanceCount = 0;

const VB_W = 960;
const VB_H = 220;
const PAD_L = 34;
const PAD_R = 12;
const PAD_TOP = 24;
const PAD_BOTTOM = 26;
const CHART_W = VB_W - PAD_L - PAD_R;
const CHART_H = VB_H - PAD_TOP - PAD_BOTTOM;
const BASELINE_Y = VB_H - PAD_BOTTOM;
const RANGE_TICK = 6;

function clamp(v, lo, hi) {
  return Math.min(Math.max(v, lo), hi);
}

// Tanner Helland's Kelvin -> RGB approximation, as HA's own is.
export function kelvinToRgb(kelvin) {
  const temp = kelvin / 100;
  let r, g, b;

  if (temp <= 66) {
    r = 255;
  } else {
    r = clamp(329.698727446 * Math.pow(temp - 60, -0.1332047592), 0, 255);
  }

  if (temp <= 66) {
    g = clamp(99.4708025861 * Math.log(temp) - 161.1195681661, 0, 255);
  } else {
    g = clamp(288.1221695283 * Math.pow(temp - 60, -0.0755148492), 0, 255);
  }

  if (temp >= 66) {
    b = 255;
  } else if (temp <= 19) {
    b = 0;
  } else {
    b = clamp(138.5177312231 * Math.log(temp - 10) - 305.0447927307, 0, 255);
  }

  return [Math.round(r), Math.round(g), Math.round(b)];
}

export function rgbToHex([r, g, b]) {
  return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('');
}

// Mirrors curve.py's phase_at(). Exported (like the other pure helpers
// below) so tests can run it under node.
export function phaseAt(t, morning, day, evening, night) {
  if (t < morning) return 'Night';
  if (t < day) return 'Morning';
  if (t < evening) return 'Day';
  if (t < night) return 'Evening';
  return 'Night';
}

const PHASE_ORDER = ['Morning', 'Day', 'Evening', 'Night'];

// Mirrors curve.py's phase_marks(): which phases actually occur, and when
// each really starts, given boundaries that may be out of order.
export function phaseMarks(morning, day, evening, night) {
  const effectiveStarts = [];
  let running = null;
  for (const ts of [morning, day, evening, night]) {
    running = running === null ? ts : Math.max(running, ts);
    effectiveStarts.push(running);
  }

  const marks = [];
  for (let i = 0; i < PHASE_ORDER.length - 1; i++) {
    if (effectiveStarts[i] < effectiveStarts[i + 1]) {
      marks.push([PHASE_ORDER[i], effectiveStarts[i]]);
    }
  }
  if (marks.length) {
    marks.push(['Night', effectiveStarts[effectiveStarts.length - 1]]);
  }
  return marks;
}

// Nudges phase labels apart so they don't overlap on a narrow card: sweep
// right pushing each clear of the last, then back left from the right
// edge. Labels that can't fit at all are dropped, latest first. The lines
// never move, and each label keeps its exact time as a `title`.
export function layoutBoundaryLabels(desired, widths, containerWidth, gap = 6) {
  const total = (count) =>
    widths.slice(0, count).reduce((sum, w) => sum + w, 0) + gap * Math.max(0, count - 1);

  let visible = desired.length;
  while (visible > 0 && total(visible) > containerWidth) {
    visible -= 1;
  }

  const centres = desired.slice(0, visible);

  // The left clamp goes first, so the sweep carries its displacement along.
  if (visible > 0) centres[0] = Math.max(centres[0], widths[0] / 2);

  for (let i = 1; i < visible; i++) {
    const min = centres[i - 1] + widths[i - 1] / 2 + gap + widths[i] / 2;
    if (centres[i] < min) centres[i] = min;
  }

  // Can't undo the left clamp: `visible` was chosen so the run fits.
  if (visible > 0) {
    centres[visible - 1] = Math.min(centres[visible - 1], containerWidth - widths[visible - 1] / 2);
  }
  for (let i = visible - 2; i >= 0; i--) {
    const max = centres[i + 1] - widths[i + 1] / 2 - gap - widths[i] / 2;
    if (centres[i] > max) centres[i] = max;
  }

  return desired.map((_, i) => ({
    centre: i < visible ? centres[i] : desired[i],
    hidden: i >= visible,
  }));
}

// title unset: the sensor's name. title: "": no header. "FLARE" only when
// there's no entity to name.
function cardHeader(config, stateObj) {
  if (config.title === '') return '';
  if (config.title) return config.title;
  const name = stateObj && stateObj.attributes && stateObj.attributes.friendly_name;
  return name || 'FLARE';
}

// Reads the attribute, or .state for a separate plain-value sensor.
function numFromAttrOrState(stateObj, attrName) {
  if (!stateObj) return undefined;
  const attrVal = stateObj.attributes && stateObj.attributes[attrName];
  return attrVal !== undefined ? Number(attrVal) : Number(stateObj.state);
}

function fmtTime(tSec) {
  const d = new Date(tSec * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// next_rising/next_setting roll over to tomorrow once passed, so shift a
// day back into the chart's window.
function sunTimeInWindow(isoString, dayStart, dayEnd) {
  if (!isoString) return null;
  let t = new Date(isoString).getTime() / 1000;
  if (t < dayStart) t += 86400;
  else if (t >= dayEnd) t -= 86400;
  return t;
}

const SENSOR_PREFIX = 'sensor.';
const SCHEDULE_SUFFIX = '_flare';

/**
 * The slug of a FLARE schedule sensor, or null. The `points` attribute is
 * what identifies one; the exact `_flare` suffix makes the slug slice
 * correct (`_flare_tracking` must not match).
 */
export function scheduleSensorSlug(hass, entityId) {
  if (typeof entityId !== 'string') return null;
  if (!entityId.startsWith(SENSOR_PREFIX) || !entityId.endsWith(SCHEDULE_SUFFIX)) return null;
  const state = hass && hass.states && hass.states[entityId];
  if (!state || !state.attributes || !('points' in state.attributes)) return null;
  return entityId.slice(SENSOR_PREFIX.length, -SCHEDULE_SUFFIX.length) || null;
}

/**
 * The card picker's (2026.6+) suggestion for a schedule sensor.
 * `columns: 'full'` because a card in a sections view doesn't inherit its
 * section's width.
 */
export function entitySuggestion(hass, entityId) {
  const slug = scheduleSensorSlug(hass, entityId);
  if (!slug) return null;
  return {
    config: {
      type: 'custom:flare-curve-card',
      sensor: slug,
      grid_options: { columns: 'full' },
    },
  };
}

// Corner rounding radius in viewBox units. Cosmetic.
const CORNER_RADIUS = 4;

// Collinearity tolerance, in viewBox units - well under one brightness step.
const COLLINEAR_EPSILON = 0.3;

/**
 * Drop points on the straight line between their neighbours. The curve is
 * piecewise linear, so most samples are redundant as geometry; this is
 * what lets the corner rounding be sized sensibly. The gradient still gets
 * every sample.
 */
export function simplifyPolyline(points, epsilon = COLLINEAR_EPSILON) {
  if (points.length < 3) return points.slice();
  const out = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const a = out[out.length - 1];
    const b = points[i];
    const c = points[i + 1];
    const dx = c.x - a.x;
    const dy = c.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const dist = Math.abs((b.x - a.x) * dy - (b.y - a.y) * dx) / len;
    if (dist > epsilon) out.push(b);
  }
  out.push(points[points.length - 1]);
  return out;
}

/**
 * The top edge as an SVG path with rounded corners: a quadratic Bezier
 * per corner, with the control point ON the corner, so it can only cut
 * inside it and never overshoot (an interpolating spline would draw
 * brightness the schedule never asks for). r is capped at half of each
 * adjacent segment so fillets can't overlap.
 */
export function roundedTopEdge(points, radius = CORNER_RADIUS) {
  if (points.length < 2) return '';
  const xy = (p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`;
  if (points.length === 2) return `M${xy(points[0])}L${xy(points[1])}`;

  let d = `M${xy(points[0])}`;
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1];
    const v = points[i];
    const next = points[i + 1];
    const inLen = Math.hypot(v.x - prev.x, v.y - prev.y);
    const outLen = Math.hypot(next.x - v.x, next.y - v.y);
    const r = Math.min(radius, inLen / 2, outLen / 2);
    if (!(r > 0.05)) {
      d += `L${xy(v)}`;
      continue;
    }
    const from = { x: v.x + ((prev.x - v.x) * r) / inLen, y: v.y + ((prev.y - v.y) * r) / inLen };
    const to = { x: v.x + ((next.x - v.x) * r) / outLen, y: v.y + ((next.y - v.y) * r) / outLen };
    d += `L${xy(from)}Q${xy(v)} ${xy(to)}`;
  }
  return `${d}L${xy(points[points.length - 1])}`;
}

/**
 * The curve: one filled path through the samples, with a gradient stop
 * per sample. Straight lines between samples are exact, since the curve
 * is piecewise linear.
 */
export function curveFillSvg(samples, xOf, hOf, dayStart, span, gradientId) {
  if (!samples || samples.length < 2) return '';
  const points = samples.map((s) => ({ x: xOf(s.t), y: BASELINE_Y - hOf(s.brightness) }));
  const top = roundedTopEdge(simplifyPolyline(points));
  const area =
    `${top}L${xOf(samples[samples.length - 1].t).toFixed(2)},${BASELINE_Y}` +
    `L${xOf(samples[0].t).toFixed(2)},${BASELINE_Y}Z`;
  // objectBoundingBox spans exactly the day, so an offset is the position
  // through it.
  const stops = samples
    .map((s) => {
      const offset = (((s.t - dayStart) / span) * 100).toFixed(3);
      return `<stop offset="${offset}%" stop-color="${rgbToHex(kelvinToRgb(s.kelvin))}"/>`;
    })
    .join('');
  return (
    `<defs><linearGradient id="${gradientId}" x1="0" y1="0" x2="1" y2="0">${stops}</linearGradient></defs>` +
    `<path d="${area}" fill="url(#${gradientId})" />`
  );
}

class FlareCurveCard extends HTMLElement {
  // Points a new card at a schedule sensor that exists.
  static getStubConfig(hass) {
    const entityId = Object.keys((hass && hass.states) || {}).find((id) =>
      scheduleSensorSlug(hass, id)
    );
    return entityId ? { sensor: scheduleSensorSlug(hass, entityId) } : {};
  }

  setConfig(config) {
    this._config = config || {};
    if (this._instanceId === undefined) {
      _instanceCount += 1;
      this._instanceId = _instanceCount;
    }
    // `sensor: living_room` points every entity at that schedule sensor's.
    // `entities` overrides individual ids.
    const fromSensor = {};
    if (this._config.sensor) {
      const base = `sensor.${this._config.sensor}_flare`;
      fromSensor.phase = base;
      fromSensor.brightness_now = base;
      fromSensor.kelvin_now = base;
    }
    this._entities = { ...DEFAULT_ENTITIES, ...fromSensor, ...(this._config.entities || {}) };
    this._cacheKey = null;
    this._samples = [];
    if (!this.shadowRoot) {
      this.attachShadow({ mode: 'open' });
    }
  }

  getCardSize() {
    return 4;
  }

  connectedCallback() {
    this._timer = setInterval(() => this._render(), RENDER_INTERVAL_MS);
    // Label collisions depend on width, which changes without a state change.
    if (typeof ResizeObserver !== 'undefined') {
      this._resizeObserver = new ResizeObserver(() => this._layoutLabels());
      this._resizeObserver.observe(this);
    }
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    if (this._resizeObserver) this._resizeObserver.disconnect();
  }

  set hass(hass) {
    this._hass = hass;
    const e = this._entities;
    const get = (id) => hass.states[id];

    const phase = get(e.phase);
    if (!phase) {
      this._renderError(`Missing entity: ${e.phase}`);
      return;
    }

    const sun = get(e.sun);
    const brightnessNow = get(e.brightness_now);
    const kelvinNow = get(e.kelvin_now);

    const boundaries = {
      morning: Number(phase.attributes.morning_start),
      day: Number(phase.attributes.day_start),
      evening: Number(phase.attributes.evening_start),
      night: Number(phase.attributes.night_start),
      // Null if the bounds aren't configured.
      eveningEarliest: phase.attributes.evening_earliest != null ? Number(phase.attributes.evening_earliest) : null,
      eveningLatest: phase.attributes.evening_latest != null ? Number(phase.attributes.evening_latest) : null,
    };

    const pointsRaw = phase.attributes.points;
    const brightnessNowValue = numFromAttrOrState(brightnessNow, 'brightness');
    const kelvinNowValue = numFromAttrOrState(kelvinNow, 'color_temp');

    // "now" is in the key because the card reads the clock itself; without it
    // a flat stretch of curve would freeze the marker. Bucketed to the render
    // interval so the cache can still hit.
    const nowBucket = Math.floor(Date.now() / RENDER_INTERVAL_MS);

    const cacheKey = JSON.stringify([
      boundaries,
      phase && phase.state,
      sun && sun.attributes.next_setting,
      sun && sun.attributes.next_rising,
      pointsRaw,
      brightnessNowValue,
      kelvinNowValue,
      nowBucket,
      // The swatch border depends on it.
      !!(hass.themes && hass.themes.darkMode),
    ]);

    if (cacheKey === this._cacheKey) {
      return;
    }
    this._cacheKey = cacheKey;

    this._boundaries = boundaries;
    this._phaseState = phase && phase.state;
    this._sun = sun;
    this._brightnessNow = brightnessNowValue;
    this._kelvinNow = kelvinNowValue;

    if (pointsRaw) {
      // The attribute may arrive as a list or a JSON string.
      let parsed = null;
      if (Array.isArray(pointsRaw)) {
        parsed = pointsRaw;
      } else if (typeof pointsRaw === 'string') {
        try {
          parsed = JSON.parse(pointsRaw);
        } catch (err) {
          // Keep the last good samples.
          parsed = null;
        }
      }
      if (Array.isArray(parsed) && parsed.length > 1) {
        this._samples = parsed;
      }
    }

    this._render();
  }

  // Applies layoutBoundaryLabels using real measured widths, once per render.
  _layoutLabels() {
    const root = this.shadowRoot;
    if (!root) return;
    const wrap = root.querySelector('.chart-wrap');
    const labels = [...root.querySelectorAll('.boundary-label')];
    if (!wrap || !labels.length) return;

    const width = wrap.clientWidth;
    // Not laid out yet; leave the labels at their inline positions.
    if (!width) return;

    // A hidden label measures zero wide.
    labels.forEach((el) => {
      el.style.display = '';
    });

    const desired = labels.map((el) => Number(el.dataset.xFrac) * width);
    const widths = labels.map((el) => el.getBoundingClientRect().width);

    layoutBoundaryLabels(desired, widths, width).forEach((placed, i) => {
      labels[i].style.left = `${placed.centre.toFixed(1)}px`;
      if (placed.hidden) labels[i].style.display = 'none';
    });
  }

  _header() {
    return cardHeader(this._config, this._hass && this._hass.states[this._entities.phase]);
  }

  _renderError(message) {
    this.shadowRoot.innerHTML = `
      <ha-card header="${this._header()}">
        <div style="padding: 16px; color: var(--error-color, red);">${message}</div>
      </ha-card>
    `;
  }

  _eveningNote() {
    const b = this._boundaries;
    if (!b) return '';
    const eveningTime = fmtTime(b.evening);
    if (b.eveningEarliest == null || b.eveningLatest == null || !this._sun || !this._sun.attributes.next_setting) {
      return `Evening starts at ${eveningTime}.`;
    }
    const earliestTs = b.eveningEarliest;
    const latestTs = b.eveningLatest;
    const sunsetTs = new Date(this._sun.attributes.next_setting).getTime() / 1000;

    let reason;
    if (Math.abs(b.evening - latestTs) < 60 && sunsetTs > latestTs) {
      reason = `capped at its latest bound (${fmtTime(latestTs)}) — tonight's sunset is later, at ${fmtTime(sunsetTs)}`;
    } else if (Math.abs(b.evening - earliestTs) < 60 && sunsetTs < earliestTs) {
      reason = `capped at its earliest bound (${fmtTime(earliestTs)}) — tonight's sunset is earlier, at ${fmtTime(sunsetTs)}`;
    } else {
      reason = `following tonight's sunset`;
    }
    return `Evening starts at ${eveningTime}, ${reason}.`;
  }

  _render() {
    if (!this._boundaries) return;
    const b = this._boundaries;
    const samples = this._samples;
    const haveSamples = samples && samples.length > 1;

    // Fall back to a midnight-anchored window before the samples arrive.
    let dayStart;
    let dayEnd;
    if (haveSamples) {
      dayStart = samples[0].t;
      dayEnd = samples[samples.length - 1].t;
    } else {
      const anchor = new Date(b.morning * 1000);
      anchor.setHours(0, 0, 0, 0);
      dayStart = anchor.getTime() / 1000;
      dayEnd = dayStart + 86400;
    }
    const span = dayEnd - dayStart;

    const xOf = (t) => PAD_L + ((t - dayStart) / span) * CHART_W;
    const hOf = (brightness) => (brightness / 255) * CHART_H;

    const curveFill = haveSamples
      ? curveFillSvg(samples, xOf, hOf, dayStart, span, `flare-curve-fill-${this._instanceId}`)
      : '';

    // HTML rather than SVG <text>, because the SVG is stretched horizontally
    // (preserveAspectRatio="none") and would squash the glyphs.
    const hourLabels = [];
    for (let h = 0; h <= 24; h += 3) {
      const t = dayStart + h * 3600;
      const leftPct = ((xOf(t) / VB_W) * 100).toFixed(2);
      hourLabels.push(`<span class="axis-label" style="left:${leftPct}%">${String(h).padStart(2, '0')}:00</span>`);
    }

    // Phase names as HTML text for the same reason, only for phases that
    // occur. The exact time is a `title` tooltip.
    const marks = phaseMarks(b.morning, b.day, b.evening, b.night);

    const topLabels = marks
      .map(([name, t]) => {
        const frac = xOf(t) / VB_W;
        // The desired position, so layout can rerun at any width.
        return `<span class="boundary-label" style="left:${(frac * 100).toFixed(2)}%" data-x-frac="${frac.toFixed(5)}" title="${fmtTime(t)}">${name}</span>`;
      })
      .join('');

    // Evening's earliest/latest bounds, as two ticks below the x-axis.
    let eveningRange = '';
    if (b.eveningEarliest != null && b.eveningLatest != null) {
      const xEarliest = xOf(b.eveningEarliest);
      const xLatest = xOf(b.eveningLatest);
      eveningRange = `
        <g class="evening-range">
          <title>Evening window: ${fmtTime(b.eveningEarliest)} – ${fmtTime(b.eveningLatest)}</title>
          <line x1="${xEarliest.toFixed(1)}" y1="${BASELINE_Y}" x2="${xEarliest.toFixed(1)}" y2="${BASELINE_Y + RANGE_TICK}" />
          <line x1="${xLatest.toFixed(1)}" y1="${BASELINE_Y}" x2="${xLatest.toFixed(1)}" y2="${BASELINE_Y + RANGE_TICK}" />
        </g>
      `;
    }

    // Drawn after the sun markers: Evening often starts exactly at sunset,
    // and the dashes let both lines show.
    const boundaryLines = marks
      .map(([, t]) => `<line x1="${xOf(t).toFixed(1)}" y1="${PAD_TOP}" x2="${xOf(t).toFixed(1)}" y2="${BASELINE_Y}" class="boundary-line" />`)
      .join('');

    const sunriseTs = this._sun && sunTimeInWindow(this._sun.attributes.next_rising, dayStart, dayEnd);
    const sunsetTs = this._sun && sunTimeInWindow(this._sun.attributes.next_setting, dayStart, dayEnd);
    const sunMarkers = [
      sunriseTs != null ? ['Sunrise', sunriseTs] : null,
      sunsetTs != null ? ['Sunset', sunsetTs] : null,
    ]
      .filter(Boolean)
      .map(([, t]) => {
        const x = xOf(t).toFixed(1);
        return `
          <line x1="${x}" y1="${PAD_TOP}" x2="${x}" y2="${BASELINE_Y}" class="sun-line" />
          <circle cx="${x}" cy="${PAD_TOP}" r="3" class="sun-dot" />
        `;
      })
      .join('');
    const sunLabel = [
      sunriseTs != null ? `Sunrise ${fmtTime(sunriseTs)}` : null,
      sunsetTs != null ? `Sunset ${fmtTime(sunsetTs)}` : null,
    ]
      .filter(Boolean)
      .join(' · ');

    const now = Date.now() / 1000;
    const nowInWindow = now >= dayStart && now <= dayEnd;
    const haveNow = nowInWindow && Number.isFinite(this._brightnessNow) && Number.isFinite(this._kelvinNow);
    const nowX = xOf(now).toFixed(1);
    // Just a line; the current colour is the label's swatch.
    const nowMarker = nowInWindow
      ? `<line x1="${nowX}" y1="${PAD_TOP - 4}" x2="${nowX}" y2="${BASELINE_Y}" class="now-line" />`
      : '';

    const svg = `
      <div class="chart-wrap">
        <svg viewBox="0 0 ${VB_W} ${VB_H}" preserveAspectRatio="none" class="chart">
          ${curveFill}
          ${sunMarkers}
          ${boundaryLines}
          ${nowMarker}
          <line x1="${PAD_L}" y1="${BASELINE_Y}" x2="${VB_W - PAD_R}" y2="${BASELINE_Y}" class="axis-line" />
          ${eveningRange}
        </svg>
        ${topLabels}
        ${hourLabels.join('')}
      </div>
    `;

    // HA's theme dark mode, not the OS preference.
    const darkMode = !!(this._hass && this._hass.themes && this._hass.themes.darkMode);
    const swatchBorder = darkMode ? 'none' : '1px solid #000';
    const swatch = (hex) => `<span class="swatch" style="background:${hex};border:${swatchBorder};"></span>`;

    const nowLabel = haveNow
      ? `Now ${fmtTime(now)} · ${this._brightnessNow} bri · ${this._kelvinNow}K${this._phaseState ? ` · ${this._phaseState}` : ''} ${swatch(rgbToHex(kelvinToRgb(this._kelvinNow)))}`
      : this._phaseState || '';

    const footnote = haveSamples
      ? this._eveningNote()
      : `${this._eveningNote()} (curve still populating — it refreshes every minute)`;

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { overflow: hidden; }
        .card-content { padding: 8px 16px 12px; position: relative; }
        .now-label {
          font-size: 0.85em;
          color: var(--secondary-text-color);
          margin-bottom: 2px;
        }
        .chart-wrap { position: relative; }
        .chart { width: 100%; height: 220px; display: block; }
        .axis-line { stroke: var(--divider-color, #888); stroke-width: 1; }
        .axis-label {
          position: absolute;
          bottom: 6px;
          transform: translateX(-50%);
          color: var(--secondary-text-color);
          font-size: 11px;
          white-space: nowrap;
        }
        .evening-range line {
          stroke: var(--secondary-text-color);
          stroke-width: 1.5;
          opacity: 0.7;
        }
        .boundary-line {
          stroke: var(--secondary-text-color);
          stroke-width: 1;
          stroke-dasharray: 3 3;
          opacity: 0.6;
        }
        .boundary-label {
          position: absolute;
          top: 2px;
          transform: translateX(-50%);
          color: var(--secondary-text-color);
          font-size: 11px;
          white-space: nowrap;
          cursor: default;
        }
        .now-line { stroke: var(--primary-text-color); stroke-width: 1.5; }
        .swatch {
          display: inline-block;
          width: 10px;
          height: 10px;
          border-radius: 2px;
          vertical-align: middle;
          box-sizing: border-box;
        }
        .sun-line { stroke: #f5a623; stroke-width: 1.5; opacity: 0.85; }
        .sun-dot { fill: #f5a623; }
        .sun-label { font-size: 0.78em; color: var(--secondary-text-color); margin-bottom: 2px; }
        .footnote {
          font-size: 0.78em;
          color: var(--secondary-text-color);
          margin-top: 6px;
        }
        .tooltip {
          position: absolute;
          pointer-events: none;
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          padding: 4px 8px;
          font-size: 0.78em;
          color: var(--primary-text-color);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,0.3));
          display: none;
          white-space: nowrap;
          z-index: 2;
        }
      </style>
      <ha-card header="${this._header()}">
        <div class="card-content">
          <div class="now-label">${nowLabel}</div>
          ${sunLabel ? `<div class="sun-label">${sunLabel}</div>` : ''}
          ${svg}
          <div class="tooltip"></div>
          <div class="footnote">${footnote}</div>
        </div>
      </ha-card>
    `;

    this._svgEl = this.shadowRoot.querySelector('svg.chart');
    this._tooltipEl = this.shadowRoot.querySelector('.tooltip');
    this._dayStart = dayStart;
    this._span = span;

    // Labels are drawn whether or not samples have arrived.
    this._layoutLabels();

    if (!haveSamples) return;

    const onMove = (ev) => {
      const rect = this._svgEl.getBoundingClientRect();
      const clientX = ev.touches ? ev.touches[0].clientX : ev.clientX;
      const frac = clamp((clientX - rect.left) / rect.width, 0, 1);
      const t = this._dayStart + frac * this._span;
      let idx = 0;
      let bestDiff = Infinity;
      for (let i = 0; i < samples.length; i++) {
        const diff = Math.abs(samples[i].t - t);
        if (diff < bestDiff) {
          bestDiff = diff;
          idx = i;
        }
      }
      const s = samples[idx];
      const hex = rgbToHex(kelvinToRgb(s.kelvin));
      const phase = phaseAt(s.t, b.morning, b.day, b.evening, b.night);
      // Already shifted into the display window.
      const sunState = sunriseTs != null && sunsetTs != null ? (s.t >= sunriseTs && s.t < sunsetTs ? 'Sun up' : 'Sun down') : '';
      this._tooltipEl.style.display = 'block';
      this._tooltipEl.style.left = `${clamp((clientX - rect.left), 0, rect.width - 170)}px`;
      this._tooltipEl.style.top = '4px';
      this._tooltipEl.innerHTML = `<b>${phase} · ${fmtTime(s.t)}${sunState ? ` · ${sunState}` : ''}</b><br>${s.brightness} bri &nbsp; ${s.kelvin}K ${swatch(hex)}`;
    };
    const onLeave = () => {
      this._tooltipEl.style.display = 'none';
    };

    this._svgEl.addEventListener('pointermove', onMove);
    this._svgEl.addEventListener('pointerleave', onLeave);
    this._svgEl.addEventListener('touchmove', onMove, { passive: true });
    this._svgEl.addEventListener('touchend', onLeave);
  }
}

customElements.define('flare-curve-card', FlareCurveCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'flare-curve-card',
  name: 'FLARE Curve',
  description: 'Live brightness and rendered-colour curve for a FLARE schedule.',
  preview: true,
  documentationURL: 'https://danrspencer.github.io/flare/',
  // The card picker's entity suggestion (2026.6+; ignored before).
  getEntitySuggestion: entitySuggestion,
});

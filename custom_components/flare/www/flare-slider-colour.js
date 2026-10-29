/**
 * Colours for FLARE's slider features: a Kelvin's colour, darkened (or
 * lightened, on a dark card) just enough to show against the card. The
 * curve card draws the true colour; this is only for the sliders.
 */

import { kelvinToRgb } from './flare-curve-card.js';

// The least contrast a slider colour keeps against the card: enough to see
// the bar, little enough that pale Kelvins stay pale.
export const MIN_CARD_CONTRAST = 1.3;

// HA's own fallback for ha-card's background.
const DEFAULT_CARD_BACKGROUND = [255, 255, 255];

const toLinear = (c) => {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
};
const fromLinear = (l) => {
  const s = l <= 0.0031308 ? l * 12.92 : 1.055 * Math.pow(l, 1 / 2.4) - 0.055;
  return Math.round(Math.min(Math.max(s, 0), 1) * 255);
};
const luminanceOf = ([r, g, b]) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

/** WCAG relative luminance of an sRGB colour. */
export function relativeLuminance(rgb) {
  return luminanceOf(rgb.map(toLinear));
}

/** WCAG contrast ratio between two sRGB colours. */
export function contrastRatio(a, b) {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * `rgb` unchanged unless it's too close to `background`, else moved away
 * from it just enough to reach `minContrast`. Darkening scales linear
 * light, so the hue holds.
 */
export function displayRgb(rgb, background = DEFAULT_CARD_BACKGROUND, minContrast = MIN_CARD_CONTRAST) {
  if (contrastRatio(rgb, background) >= minContrast) return rgb;
  const linear = rgb.map(toLinear);
  const lum = luminanceOf(linear);
  const bgLum = relativeLuminance(background);
  if (bgLum > lum || bgLum > 0.5) {
    const target = (bgLum + 0.05) / minContrast - 0.05;
    if (target <= 0) return [0, 0, 0];
    const k = lum > 0 ? target / lum : 0;
    return linear.map((l) => fromLinear(l * k));
  }
  const target = minContrast * (bgLum + 0.05) - 0.05;
  if (target >= 1) return [255, 255, 255];
  // Mixing toward white moves luminance linearly with t.
  const t = (target - lum) / (1 - lum);
  return linear.map((l) => fromLinear(l + t * (1 - l)));
}

/** A Kelvin as a slider's CSS colour, on a card of `background`. */
export function kelvinCss(kelvin, background) {
  const [r, g, b] = displayRgb(kelvinToRgb(kelvin), background);
  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * The background of the card `el` sits on, as ha-card resolves it, read
 * through the canvas so any CSS colour parses. White outside a browser.
 */
export function cardBackgroundRgb(el) {
  if (typeof getComputedStyle !== 'function' || typeof document === 'undefined' || !el) {
    return DEFAULT_CARD_BACKGROUND;
  }
  const style = getComputedStyle(el);
  const value =
    style.getPropertyValue('--ha-card-background').trim() ||
    style.getPropertyValue('--card-background-color').trim();
  if (!value) return DEFAULT_CARD_BACKGROUND;
  const ctx = document.createElement('canvas').getContext('2d');
  if (!ctx) return DEFAULT_CARD_BACKGROUND;
  ctx.fillStyle = '#000';
  ctx.fillStyle = value;
  const parsed = ctx.fillStyle;
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(parsed);
  if (hex) return hex.slice(1).map((h) => parseInt(h, 16));
  const rgba = /^rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(parsed);
  return rgba ? rgba.slice(1).map(Number) : DEFAULT_CARD_BACKGROUND;
}

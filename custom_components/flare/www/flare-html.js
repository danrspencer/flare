/**
 * Escaping for text from entities and card options that goes into markup
 * built as a string. No DOM or HA imports.
 */

const ENTITIES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

// Safe as element text and inside a quoted attribute.
export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ENTITIES[c]);
}

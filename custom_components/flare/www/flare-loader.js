// FLARE's one entry point in Home Assistant's page, loading the modules
// that register something. HA's frontend swaps in a scoped custom element
// registry and its own HTMLElement as it boots, at the same time as it
// loads integrations' modules; an element defined before that is never
// found. So inside HA, wait for HA's own element first.
if (document.querySelector('home-assistant')) {
  await customElements.whenDefined('home-assistant');
}

await Promise.all([
  import('./flare-icon.js'),
  import('./flare-curve-card.js'),
  import('./flare-kelvin-feature.js'),
  import('./flare-brightness-feature.js'),
  import('./flare-schedule-transfer-card.js'),
  import('./flare-view-strategy.js'),
]);

// Tells FLARE a page has its dashboard, clearing the reload repair. A view,
// not a file here, so its URL isn't relative to this one.
const BEACON = '/flare_static/frontend_loaded.js';
import(BEACON).catch(() => {});

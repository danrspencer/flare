/**
 * Two Lovelace view strategies: `custom:flare-schedule` (what lights are
 * scheduled to do) and `custom:flare-tracking` (what FLARE is driving).
 *
 *   views:
 *     - title: Lighting
 *       strategy:
 *         type: custom:flare-schedule
 *         sensor: downstairs   # optional: one schedule per view
 *
 * `sensor` is the schedule sensor's slug or entity_id. Regenerated on
 * every load, so layout changes arrive with an update.
 */

import {
  sectionConfig,
  scheduleSensors,
  normaliseSlug,
  trackingSectionConfig,
  trackingScopes,
} from './flare-section.js';

const view = (sections) => ({ type: 'sections', max_columns: 4, sections });

// A view explaining what's wrong, rather than a blank one.
const notice = (body) =>
  view([
    {
      type: 'grid',
      cards: [
        { type: 'heading', heading: 'FLARE', heading_style: 'title' },
        { type: 'markdown', content: body },
      ],
    },
  ]);

class FlareScheduleViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const all = scheduleSensors(hass);
    const wanted = normaliseSlug(config && config.sensor);

    if (!all.length) {
      return notice(
        'No FLARE schedules found yet.\n\nAdd one under **Settings → Devices & ' +
          'Services → FLARE Schedules → Add schedule sensor**, and it will appear ' +
          'here automatically.'
      );
    }

    if (!wanted) return view(all.map(({ slug, title }) => sectionConfig(slug, title)));

    const match = all.find((s) => s.slug === wanted);
    if (!match) {
      // List the slugs that exist, so a typo is fixable.
      const available = all.map((s) => `- \`${s.slug}\``).join('\n');
      return notice(
        `No FLARE schedule called \`${wanted}\`.\n\nAvailable schedules:\n\n${available}`
      );
    }

    return view([sectionConfig(match.slug, match.title)]);
  }
}

customElements.define('ll-strategy-view-flare-schedule', FlareScheduleViewStrategy);

/**
 * The tracking view: one section per zone, with its counts, its
 * overridden lights and the Clear button.
 *
 *   views:
 *     - title: Tracking
 *       strategy:
 *         type: custom:flare-tracking
 */
class FlareTrackingViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const scopes = trackingScopes(hass);

    if (!scopes.length) {
      return notice(
        'No FLARE zones found yet.\n\nAdd one under **Settings → Devices ' +
          '& Services → FLARE Control → Add zone**, and it will appear here ' +
          'automatically.'
      );
    }

    return view(scopes.map(({ slug, title }) => trackingSectionConfig(slug, title)));
  }
}

customElements.define('ll-strategy-view-flare-tracking', FlareTrackingViewStrategy);

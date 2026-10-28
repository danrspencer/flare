/**
 * Two Lovelace view strategies: `custom:flare-schedule` (what lights are
 * scheduled to do) and `custom:flare-rooms` (what FLARE is driving), and a
 * dashboard strategy, `custom:flare`, made of them.
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

import { scheduleSensors, normaliseSlug, flareTotals, claimsByArea } from './flare-entities.js';
import { sectionConfig } from './flare-section.js';
import { areaSections, totalsSection } from './flare-rooms-section.js';
import './flare-clear-card.js';
import './flare-area-card.js';
import './flare-activity-card.js';

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
          'Services → FLARE → Add schedule**, and it will appear here automatically.'
      );
    }

    if (!wanted) return view(all.map(sectionConfig));

    // The slug, or the sensor's entity_id, renamed or not.
    const asGiven = typeof config.sensor === 'string' ? config.sensor.trim() : null;
    const match = all.find((s) => s.slug === wanted || s.entities.schedule === asGiven);
    if (!match) {
      // List the slugs that exist, so a typo is fixable.
      const available = all.map((s) => `- \`${s.slug}\``).join('\n');
      return notice(
        `No FLARE schedule called \`${wanted}\`.\n\nAvailable schedules:\n\n${available}`
      );
    }

    return view([sectionConfig(match)]);
  }
}

customElements.define('ll-strategy-view-flare-schedule', FlareScheduleViewStrategy);

/**
 * The rooms view: the totals, then every area holding a room light, laid
 * out by floor like Home Assistant's Light dashboard, and an Activity
 * sidebar, as HA's Security dashboard has: FLARE's device's logbook
 * (flare-activity-card.js).
 *
 *   views:
 *     - title: Rooms
 *       strategy:
 *         type: custom:flare-rooms
 */
class FlareRoomsViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const totals = flareTotals(hass);
    if (!totals.claims) {
      return notice(
        'FLARE\'s **Settings** entry isn\'t set up, so nothing is tracking ' +
          'which lights FLARE controls. Add FLARE under **Settings → Devices ' +
          '& Services**.'
      );
    }
    const areas = [...claimsByArea(hass).keys()];
    const roomsView = { type: 'sections', max_columns: 2, sections: [totalsSection(totals), ...areaSections(hass, areas)] };
    if (!areas.length) {
      roomsView.sections.push({
        type: 'grid',
        column_span: 2,
        cards: [
          {
            type: 'markdown',
            content:
              'No rooms yet. A room appears here once its automation has set ' +
              'its lights, grouped by the lights\' areas.',
          },
        ],
      });
    }
    const hasLogbook = (hass.config?.components || []).includes('logbook');
    if (!hasLogbook || !totals.device) return roomsView;
    return {
      ...roomsView,
      sidebar: {
        sections: [
          {
            type: 'grid',
            cards: [
              { type: 'heading', heading: 'Activity', heading_style: 'title' },
              { type: 'custom:flare-activity-card', device_id: [totals.device], hours_to_show: 24 },
            ],
          },
        ],
        content_label: 'Rooms',
        sidebar_label: 'Activity',
      },
    };
  }
}

customElements.define('ll-strategy-view-flare-rooms', FlareRoomsViewStrategy);
// Its name before 2.0, for dashboards someone took control of.
customElements.define('ll-strategy-view-flare-zone', class extends FlareRoomsViewStrategy {});

/**
 * The whole dashboard: a view per schedule, then Rooms once FLARE tracks
 * claims.
 *
 *   strategy:
 *     type: custom:flare
 */
class FlareDashboardStrategy extends HTMLElement {
  // What Add dashboard pre-fills: its title, and from that its URL.
  static getCreateSuggestions() {
    return { title: 'FLARE', icon: 'flare:logo' };
  }

  static async generate(config, hass) {
    const schedules = scheduleSensors(hass).map(({ slug, title }) => ({
      title,
      path: slug,
      strategy: { type: 'custom:flare-schedule', sensor: slug },
    }));
    const rooms = flareTotals(hass).claims
      ? [{ title: 'Rooms', path: 'rooms', strategy: { type: 'custom:flare-rooms' } }]
      : [];
    const views = [...schedules, ...rooms];
    // The schedule view explains an empty install.
    return { views: views.length ? views : [{ title: 'Lighting', strategy: { type: 'custom:flare-schedule' } }] };
  }
}

customElements.define('ll-strategy-dashboard-flare', FlareDashboardStrategy);

// Lists it under Settings → Dashboards → Add dashboard.
window.customStrategies = window.customStrategies || [];
window.customStrategies.push({
  type: 'flare',
  strategyType: 'dashboard',
  name: 'FLARE Lighting',
  description: 'A view for each FLARE schedule, and one for your rooms. Keeps up as you add more.',
  documentationURL: 'https://danrspencer.github.io/flare/dashboard/',
});

/**
 * Two Lovelace view strategies: `custom:flare-schedule` (what lights are
 * scheduled to do) and `custom:flare-zone` (what FLARE is driving), and a
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

import {
  sectionConfig,
  scheduleSensors,
  normaliseSlug,
  zoneSections,
  zoneTotalsSection,
  listZones,
  zoneDevices,
} from './flare-section.js';
import './flare-clear-card.js';
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
 * The zone view: the totals, then every zone laid out by floor and area
 * like Home Assistant's Light dashboard, and an Activity sidebar, as HA's
 * Security dashboard has: the zones' devices' logbook, the same entries
 * as each zone's own page (flare-activity-card.js).
 *
 *   views:
 *     - title: Zones
 *       strategy:
 *         type: custom:flare-zone
 */
class FlareZoneViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const zones = listZones(hass);

    if (!zones.length) {
      return notice(
        'No FLARE zones found yet.\n\nAdd one under **Settings → Devices ' +
          '& Services → FLARE → Add zone**, and it will appear here ' +
          'automatically.'
      );
    }

    const zoneView = { type: 'sections', max_columns: 2, sections: [zoneTotalsSection(zones), ...zoneSections(hass, zones)] };
    const devices = zoneDevices(hass, zones);
    const hasLogbook = (hass.config?.components || []).includes('logbook');
    if (!hasLogbook || !devices.length) return zoneView;
    return {
      ...zoneView,
      sidebar: {
        sections: [
          {
            type: 'grid',
            cards: [
              { type: 'heading', heading: 'Activity', heading_style: 'title' },
              { type: 'custom:flare-activity-card', device_id: devices, hours_to_show: 24 },
            ],
          },
        ],
        content_label: 'Zones',
        sidebar_label: 'Activity',
      },
    };
  }
}

customElements.define('ll-strategy-view-flare-zone', FlareZoneViewStrategy);

/**
 * The whole dashboard: a view per schedule, then Zones if there are any.
 *
 *   strategy:
 *     type: custom:flare
 */
class FlareDashboardStrategy extends HTMLElement {
  static async generate(config, hass) {
    const schedules = scheduleSensors(hass).map(({ slug, title }) => ({
      title,
      path: slug,
      strategy: { type: 'custom:flare-schedule', sensor: slug },
    }));
    const zones = listZones(hass).length
      ? [{ title: 'Zones', path: 'zones', strategy: { type: 'custom:flare-zone' } }]
      : [];
    const views = [...schedules, ...zones];
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
  description: 'A view for each FLARE schedule, and one for your zones. Keeps up as you add more.',
  documentationURL: 'https://danrspencer.github.io/flare/dashboard/',
});

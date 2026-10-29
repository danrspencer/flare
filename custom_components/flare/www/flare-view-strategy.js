/**
 * Two Lovelace view strategies: `custom:flare-schedule` (what lights are
 * scheduled to do) and `custom:flare-lights` (what FLARE is driving), and a
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
import { localize } from './flare-i18n.js';
import { sectionConfig } from './flare-section.js';
import { areaSections, totalsSection } from './flare-lights-section.js';
// Not used by these views any more, but dashboards someone took control of
// may name custom:flare-clear-card.
import './flare-clear-card.js';
import './flare-area-lights-card.js';
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
      return notice(localize(hass, 'view.no_schedules'));
    }

    if (!wanted) return view(all.map((schedule) => sectionConfig(schedule, hass)));

    // The slug, or the sensor's entity_id, renamed or not.
    const asGiven = typeof config.sensor === 'string' ? config.sensor.trim() : null;
    const match = all.find((s) => s.slug === wanted || s.entities.schedule === asGiven);
    if (!match) {
      // List the slugs that exist, so a typo is fixable.
      const available = all.map((s) => `- \`${s.slug}\``).join('\n');
      return notice(localize(hass, 'view.unknown_schedule', { name: wanted, available }));
    }

    return view([sectionConfig(match, hass)]);
  }
}

customElements.define('ll-strategy-view-flare-schedule', FlareScheduleViewStrategy);

/**
 * The Overrides view: the totals, then every area holding a room light, laid
 * out by floor like Home Assistant's Light dashboard, and an Activity
 * sidebar, as HA's Security dashboard has: FLARE's device's logbook
 * (flare-activity-card.js).
 *
 *   views:
 *     - title: Overrides
 *       strategy:
 *         type: custom:flare-lights
 */
class FlareLightsViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const totals = flareTotals(hass);
    if (!totals.controlled) {
      return notice(localize(hass, 'view.no_settings'));
    }
    const areas = [...claimsByArea(hass).keys()];
    const lightsView = { type: 'sections', max_columns: 2, sections: [totalsSection(totals, hass), ...areaSections(hass, areas)] };
    if (!areas.length) {
      lightsView.sections.push({
        type: 'grid',
        column_span: 2,
        cards: [
          {
            type: 'markdown',
            content: localize(hass, 'view.no_lights'),
          },
        ],
      });
    }
    const hasLogbook = (hass.config?.components || []).includes('logbook');
    if (!hasLogbook || !totals.device) return lightsView;
    return {
      ...lightsView,
      sidebar: {
        sections: [
          {
            type: 'grid',
            cards: [
              { type: 'heading', heading: localize(hass, 'view.activity'), heading_style: 'title' },
              { type: 'custom:flare-activity-card', device_id: [totals.device], hours_to_show: 24 },
            ],
          },
        ],
        content_label: localize(hass, 'view.overrides'),
        sidebar_label: localize(hass, 'view.activity'),
      },
    };
  }
}

customElements.define('ll-strategy-view-flare-lights', FlareLightsViewStrategy);
// Its name before 2.0, for dashboards someone took control of.
customElements.define('ll-strategy-view-flare-zone', class extends FlareLightsViewStrategy {});

/**
 * The whole dashboard: a view per schedule, then Overrides once FLARE tracks
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
    const lights = flareTotals(hass).controlled
      ? [{ title: localize(hass, 'view.overrides'), path: 'overrides', strategy: { type: 'custom:flare-lights' } }]
      : [];
    const views = [...schedules, ...lights];
    // The schedule view explains an empty install.
    return {
      views: views.length ? views : [{ title: localize(hass, 'view.lighting'), strategy: { type: 'custom:flare-schedule' } }],
    };
  }
}

customElements.define('ll-strategy-dashboard-flare', FlareDashboardStrategy);

// Lists it under Settings → Dashboards → Add dashboard.
window.customStrategies = window.customStrategies || [];
window.customStrategies.push({
  type: 'flare',
  strategyType: 'dashboard',
  name: 'FLARE Lighting',
  description: 'A view for each FLARE schedule, and one for the lights it drives. Keeps up as you add more.',
  documentationURL: 'https://danrspencer.github.io/flare/dashboard/',
});

/**
 * Two Lovelace VIEW strategies: `custom:flare-schedule` for what the
 * lights are scheduled to do, and `custom:flare-tracking` (further down)
 * for what FLARE is currently driving.
 *
 * Neither is called plain `custom:flare`. It was, while there was only
 * one, and the rename came with the second: "flare" gives no hint which
 * of the two you get, and the pair reads as a set.
 *
 * Every schedule, one view:
 *
 *   views:
 *     - title: Lighting
 *       strategy:
 *         type: custom:flare-schedule
 *
 * Or one schedule per view, which is usually what you want once there is
 * more than one:
 *
 *   views:
 *     - title: Downstairs
 *       strategy:
 *         type: custom:flare-schedule
 *         sensor: downstairs
 *     - title: Upstairs
 *       strategy:
 *         type: custom:flare-schedule
 *         sensor: upstairs
 *
 * `sensor` is the schedule sensor's slug - the same value the curve card
 * takes, and the reason it is called `sensor` rather than `target`:
 * `target` in Home Assistant means a service target (entity, device or
 * area), which this is not. A full entity_id works too.
 *
 * This exists because the alternative - a generator emitting the same
 * section as YAML to paste - puts every future layout change on the
 * user, who would have to re-generate and re-paste a section per
 * schedule each time. A strategy is regenerated on every dashboard load
 * from flare-section.js, which ships inside the integration, so a HACS
 * update is the whole migration.
 *
 * The generator is deliberately gone rather than kept alongside: two
 * definitions of the layout and the one people see is whichever was
 * edited last. Home Assistant's own "Take control" is the route for
 * anyone who wants to own the YAML, and it is one-way.
 *
 * Registered as `ll-strategy-view-flare-schedule`, which is the name Home
 * Assistant resolves `custom:flare-schedule` to for a view strategy.
 */

import {
  sectionConfig,
  scheduleSensors,
  normaliseSlug,
  trackingSectionConfig,
  trackingScopes,
} from './flare-section.js';

const view = (sections) => ({ type: 'sections', max_columns: 4, sections });

// A view that says what is wrong and what to do about it. Better than an
// empty one: a blank screen is the same symptom for "no schedules yet"
// and "you typed the slug wrong", and neither is guessable from it.
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
      // Listing what does exist turns "nothing rendered" into a fixable
      // typo - the available slugs are the one thing the user needs and
      // cannot see from the dashboard.
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
 * A second view strategy, for what FLARE is currently DRIVING rather
 * than what it is scheduled to do:
 *
 *   views:
 *     - title: Tracking
 *       strategy:
 *         type: custom:flare-tracking
 *
 * One section per tracking scope - how many lights it is controlling,
 * how many something else has taken, which ones those are, and the Clear
 * button that hands them back.
 *
 * Separate from the schedule view rather than a section appended to it:
 * a house has one scope per room (sixteen here) against a handful of
 * schedules, so merging them would bury the schedules, and the two
 * answer different questions - "what should the light be doing" versus
 * "who currently owns it".
 */
class FlareTrackingViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const scopes = trackingScopes(hass);

    if (!scopes.length) {
      return notice(
        'No FLARE tracking scopes found yet.\n\nAdd one under **Settings → Devices ' +
          '& Services → FLARE Tracking → Add state device**, and it will appear here ' +
          'automatically.'
      );
    }

    return view(scopes.map(({ slug, title }) => trackingSectionConfig(slug, title)));
  }
}

customElements.define('ll-strategy-view-flare-tracking', FlareTrackingViewStrategy);

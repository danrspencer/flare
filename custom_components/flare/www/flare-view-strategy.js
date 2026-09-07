/**
 * A Lovelace VIEW strategy that builds a FLARE settings view.
 *
 * Every schedule, one view:
 *
 *   views:
 *     - title: Lighting
 *       strategy:
 *         type: custom:flare
 *
 * Or one schedule per view, which is usually what you want once there is
 * more than one:
 *
 *   views:
 *     - title: Downstairs
 *       strategy:
 *         type: custom:flare
 *         sensor: downstairs
 *     - title: Upstairs
 *       strategy:
 *         type: custom:flare
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
 * Registered as `ll-strategy-view-flare`, which is the name Home
 * Assistant resolves `custom:flare` to for a view strategy.
 */

import { sectionConfig, scheduleSensors, normaliseSlug } from './flare-section.js';

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

class FlareViewStrategy extends HTMLElement {
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

customElements.define('ll-strategy-view-flare', FlareViewStrategy);

/**
 * A Lovelace VIEW strategy that builds a FLARE settings view.
 *
 * Add one line to a dashboard and it fills itself in, one section per
 * schedule sensor:
 *
 *   views:
 *     - strategy:
 *         type: custom:flare
 *
 * This exists because the alternative - the docs site's generator, which
 * emits the same section as YAML to paste - puts every future layout
 * change on the user. They would have to re-generate and re-paste a
 * section per schedule each time. A strategy is regenerated on every
 * dashboard load from flare-section.js, which ships inside the
 * integration, so a HACS update is the whole migration.
 *
 * It also means a new schedule sensor simply appears, rather than
 * needing a second trip through the generator.
 *
 * The generator is deliberately kept: a strategy view is not
 * hand-editable until you use Home Assistant's "Take control", which is
 * one-way, so the generator remains the route for someone who wants to
 * own and change the YAML. Both build from the same sectionConfig(), so
 * they cannot disagree about the layout.
 *
 * Registered as `ll-strategy-view-flare`, which is the naming Home
 * Assistant resolves `custom:flare` to for a view strategy.
 */

import { sectionConfig, scheduleSensors } from './flare-section.js';

class FlareViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    const sensors = scheduleSensors(hass);

    if (!sensors.length) {
      // Better than an empty view: this is exactly the state someone is
      // in if they add the view before adding a schedule, and a blank
      // screen gives them nothing to act on.
      return {
        type: 'sections',
        max_columns: 4,
        sections: [
          {
            type: 'grid',
            cards: [
              { type: 'heading', heading: 'FLARE', heading_style: 'title' },
              {
                type: 'markdown',
                content:
                  'No FLARE schedules found yet.\n\nAdd one under **Settings → ' +
                  'Devices & Services → FLARE Schedules → Add schedule sensor**, ' +
                  'and it will appear here automatically.',
              },
            ],
          },
        ],
      };
    }

    return {
      type: 'sections',
      max_columns: 4,
      sections: sensors.map(({ slug, title }) => sectionConfig(slug, title)),
    };
  }
}

customElements.define('ll-strategy-view-flare', FlareViewStrategy);

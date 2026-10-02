<img src="https://raw.githubusercontent.com/danrspencer/flare/main/custom_components/flare/brand/icon.png" alt="" width="88">

# FLARE

**F**lexible **L**ighting **A**utomation & **R**econciliation **E**ngine.

Lighting for Home Assistant that changes through the day. By default it's bright and cool in the morning to
help you wake up, warms through the afternoon, dims in the evening, and stays low and warm overnight. You can
change all of it.

Rooms turn their lights on when someone comes in and off once they're empty, or dim to a nightlight. A room can
be handed to one of your scenes, and a light you change yourself is left alone until the room is next dark.

[![The FLARE Lighting dashboard view: the day's curve, a phase override, the schedule times, and the curve and transition values for each phase](https://raw.githubusercontent.com/danrspencer/flare/main/docs/assets/img/dashboard-section.png)](https://danrspencer.github.io/flare/dashboard/)

## 📖 [Read the documentation](https://danrspencer.github.io/flare/)

To see how the settings shape the day, try the
**[curve playground](https://danrspencer.github.io/flare/playground/)**.

- **[Quickstart](https://danrspencer.github.io/flare/installation/)**: HACS, the blueprint, and the dashboard
- **[Dashboard](https://danrspencer.github.io/flare/dashboard/)**: the two ready-made views, added with a few lines of config
- **[Guides](https://danrspencer.github.io/flare/guides/)**: examples, templates, scenes, and building your own automations
- **[Reference](https://danrspencer.github.io/flare/reference/)**: every blueprint input, schedule and zone entity, and service
- **[Contributing](CONTRIBUTING.md)**: repository layout and the test suite

## Why four phases

Most adaptive lighting follows the sun's position. In winter that means evening lighting from 4pm; in summer,
bright light until 9pm. FLARE follows your day instead, in four phases. With the default settings:

- **Morning** helps you wake up. It starts at a fixed time rather than at sunrise, because work and school
  don't start at sunrise either. Bright, cool light wakes you up better, and there is
  [some research](https://pubmed.ncbi.nlm.nih.gov/36058557/) to back that up. Mostly, though, very cool light
  is just enough eyeball caffeine to get you as far as the coffee machine.
- **Day** stays bright and warms slowly towards evening, so the change to Evening isn't sudden.
- **Evening** is warmer and dimmer. It's the one phase that follows the sun: it starts at sunset, but no
  earlier and no later than two times you set. A 4pm winter sunset doesn't start the evening while you're
  still at work, and a 10pm summer sunset doesn't delay it until bedtime.
- **Night** is low and warm, for when everyone's asleep: the light you want at 3am.

## How it fits together

Install FLARE from HACS, add it, and create an automation for each room from its blueprint. If the blueprint
doesn't do what you need, everything it uses is a Home Assistant entity or action, so you can change it with
your own automations; see the [examples](https://danrspencer.github.io/flare/guides/examples/).

## Acknowledgements

| | |
|---|---|
| [Home Assistant](https://www.home-assistant.io) | The whole platform. FLARE has no runtime dependencies beyond it, and uses its colour utilities for the Kelvin→RGB and mired conversions. |
| [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component) | Runs the integration tests against a real Home Assistant. |
| [just-the-docs](https://just-the-docs.com) | The documentation site's Jekyll theme. |
| [He et al., 2023](https://pubmed.ncbi.nlm.nih.gov/36058557/) | The morning-light research cited above. |

## AI disclosure

Written with [Claude Code](https://claude.com/claude-code). Commits carry a
`Co-Authored-By` trailer where Claude wrote them.

## License

[MIT](LICENSE)

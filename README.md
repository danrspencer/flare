<img src="https://raw.githubusercontent.com/danrspencer/flare/main/custom_components/flare/brand/icon.png" alt="" width="88">

# FLARE

**F**lexible **L**ighting **A**utomation & **R**econciliation **E**ngine.

Lighting for Home Assistant that follows the shape of your day. By default it's bright and cool to help you wake
up, warms through the afternoon, dims as evening comes, and sits low and warm once the house is asleep — and
every one of those is yours to change.

Rooms light up as people come in and go dark once they've left, or dim to a nightlight instead of going out.
Hand a room to a scene and FLARE fills in whatever the scene doesn't cover, and a light you change yourself is
left alone until the room next goes dark.

[![The FLARE Lighting dashboard view: the day's curve, a phase override, the schedule times, and the curve and transition values for each phase](https://raw.githubusercontent.com/danrspencer/flare/main/docs/assets/img/dashboard-section.png)](https://danrspencer.github.io/flare/dashboard/)

## 📖 [Read the documentation](https://danrspencer.github.io/flare/)

The quickest way to see what this actually does is the
**[interactive curve playground](https://danrspencer.github.io/flare/playground/)**: move the schedule and
curve settings around and watch the day's lighting change.

- **[Quickstart](https://danrspencer.github.io/flare/installation/)** — HACS, the blueprint, and the dashboard
- **[Dashboard](https://danrspencer.github.io/flare/dashboard/)** — the two ready-made views, added with a few lines of config
- **[Blueprint](https://danrspencer.github.io/flare/blueprint/)** — every input, feature by feature
- **[Examples](https://danrspencer.github.io/flare/examples/)** — automations that change how FLARE behaves
- **[Reference](https://danrspencer.github.io/flare/reference/)** — every service and entity, scene handoff, and building without the blueprint
- **[Contributing](CONTRIBUTING.md)** — repository layout and the test suite

## Why four phases, not a continuous curve

Adaptive lighting usually computes one continuous curve from the sun's position — brightness and colour
temperature interpolated smoothly between sunrise and sunset. That follows the daylight closely, but the
daylight isn't your schedule, and the two drift furthest apart in the months you spend most of the day indoors.
FLARE works from your schedule instead, using four named phases. With the default settings they work like this:

- **Morning** is there to help you wake up, so it starts at a fixed time before you'd normally be up rather than
  moving with sunrise — the same wake-up light in December as in June. Bright, cool-white light in the morning
  wakes you up better, and there is [some research](https://pubmed.ncbi.nlm.nih.gov/36058557/) to back that up.
  Mostly, though, it's that very cool light is just enough eyeball caffeine to get me as far as the coffee
  machine.
- **Day** is the long middle stretch, gradually warming as it runs toward evening so the eventual transition
  doesn't feel abrupt.
- **Evening** is when relaxed, warm lighting takes over — the one phase that *does* track the sun (sunset), so
  your indoor lighting shifts in step with what's actually happening outside. It's clamped between an earliest
  and latest bound, though, so a 4pm winter sunset doesn't start the evening while you're still at work, and a
  10pm midsummer sunset doesn't mean evening never really arrives.
- **Night** isn't tied to any solar event at all — it's just what the house should look like once everyone's
  asleep: dim and warm, the lighting you want on at 3am without waking yourself up further.

## How it fits together

Install FLARE from HACS, add it, and create an automation for each room from its blueprint. The blueprint covers
what most rooms want; if it doesn't do what you need, everything it uses is an ordinary Home Assistant entity or
action, so you can change it or write your own — see the
[examples](https://danrspencer.github.io/flare/examples/).

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

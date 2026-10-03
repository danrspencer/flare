---
title: Home
nav_order: 1
---

# FLARE
{: .no_toc }

**F**lexible **L**ighting **A**utomation & **R**econciliation **E**ngine — phase-based
circadian lighting for Home Assistant, with scene handoff and override protection
built in.
{: .fs-6 .fw-300 }

[Quickstart (5 mins)]({{ site.baseurl }}/installation/){: .btn .btn-primary .mr-2 }
[Curve playground]({{ site.baseurl }}/playground/){: .btn .mr-2 }
[GitHub](https://github.com/danrspencer/flare){: .btn }

---

## What it does

FLARE sets your lights through the day, and leaves alone any light you change yourself.

- **It keeps every light on the curve.** Every minute it checks each light, and corrects
  any that have drifted or missed a command.
  [See how →]({{ site.baseurl }}/reference/blueprint/#when-the-room-updates)
- **It works with lights on a physical wall switch.** If you cut the power to a room and
  restore it, FLARE puts each bulb on the current phase as soon as it shows up in Home
  Assistant again, instead of leaving it at whatever it powered up as.
  [See how →]({{ site.baseurl }}/reference/blueprint/#when-the-room-updates)
- **Each room can be different.** Give a light its own brightness, hand the room to a
  scene in any phase, or use a template when a fixed value isn't enough.
  [See how →]({{ site.baseurl }}/guides/)
- **It can leave a nightlight on.** When a room empties it can dim to a low level instead
  of going dark.
  [See how →]({{ site.baseurl }}/reference/blueprint/#idle-brightness)
- **It leaves your changes alone.** If you change a light yourself, from an app, a wall
  switch or another automation, FLARE stops setting it until the room next goes dark.
  [See how →]({{ site.baseurl }}/reference/zones/#override-protection)
- **It works with Siri, Alexa and Google.** Each room gets a single light to expose to them,
  so "turn on the kitchen" lights the kitchen the way FLARE would, rather than at whatever the
  bulbs were last set to. If you ask for a brightness or colour, FLARE leaves it alone.
  [See how →]({{ site.baseurl }}/guides/flares/)
- **It's gentle on your Zigbee network.** Rooms update one after another rather than all
  at once, and changes too small to see aren't sent.
  [See how →]({{ site.baseurl }}/reference/zones/#when-zones-tick)

---

## Four phases, not one curve

Most adaptive lighting follows the sun's position. That means evening lighting at 4pm in
winter, and bright light until 9pm in summer, whatever time you actually get up and go to
bed.

FLARE works from your schedule instead, dividing the day into four named phases. With the
default settings:

| Phase | What it's for |
|---|---|
| **Morning** | Bright and cold — enough eyeball caffeine to get you as far as the coffee machine, with [some research](https://pubmed.ncbi.nlm.nih.gov/36058557/) to back it up. |
| **Day** | Bright, easing steadily from Morning's colour toward Evening's across the whole afternoon. |
| **Evening** | Dimming and warming, anchored to your actual sunset. |
| **Night** | Warm and low, flat until morning. |

Each boundary has its own transition: how long beforehand to start easing into the next
phase, so the new values land exactly as it begins. If you set a transition to zero, the
lights step straight to the new values instead.

Morning, Day and Night start at fixed times of day. Only Evening tracks the sun, and it's kept
between an earliest and a latest time, so it moves with the season without drifting into the
small hours.

{: .tip }
> [Play with the curve]({{ site.baseurl }}/playground/) to see how each setting shapes
> the day.

---

## Home Assistant native

Every schedule setting is an ordinary Home Assistant entity, and the room automation is an ordinary
automation, so when a default isn't what you want, you change it with the tools you already
use. For example:

- **A weekend lie-in**, by an automation that moves Morning later on Friday and Saturday
  evenings.
- **A holiday schedule**, switched on and off with a toggle.
- **A room lit by a button on a remote**, not just by occupancy.
- **Blinds that close when Night starts.**

[See the examples →]({{ site.baseurl }}/guides/examples/){: .btn .btn-outline }

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
- **It works with lights on a physical wall switch.** Cut the power to a room and
  restore it, and as soon as each bulb shows up in Home Assistant again, FLARE puts it on
  the current phase instead of leaving it at whatever it powered up as.
- **Each room can be different.** Give a light its own brightness, hand the room to a
  scene in any phase, or use a template when a fixed value isn't enough.
- **It can leave a nightlight on.** When a room empties it can dim to a low level instead
  of going dark.
- **It leaves your changes alone.** Change a light yourself — from an app, a wall switch or
  another automation — and FLARE stops setting it until the room next goes dark.
- **It's gentle on your Zigbee network.** Rooms update one after another rather than all
  at once, and changes too small to see aren't sent.

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
phase, so the new values land exactly as it begins. Set one to zero for a visible step
instead.

Morning, Day and Night are wall-clock times. Only Evening tracks the sun, clamped between
an earliest and a latest time so it moves with the season without drifting into the small
hours.

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

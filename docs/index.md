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

FLARE runs your lighting through the day so you don't have to think about it, and stops
the moment you want something else.

- **It keeps every light where it should be** — not just at the moment a phase changes.
  It re-checks as it goes, and fixes anything that has drifted or never arrived.
- **It works with lights on a physical wall switch.** Cut the power to a room and
  restore it, and FLARE catches each bulb as it reappears, putting it straight onto the
  current phase instead of leaving it at whatever it powered up as.
- **It bends to fit the room.** A brightness of your own per light, a scene per phase,
  and templates for either when a fixed value isn't enough.
- **It can leave a nightlight on.** When a room empties it can dim to a low level instead
  of going dark.
- **It gets out of your way.** Change a bulb yourself — app, wall switch, another
  automation — and FLARE stops driving that one until the room next goes dark.

---

## Four phases, not one curve

Adaptive lighting usually maps brightness and colour onto the sun's position. That tracks
the daylight closely, but the daylight isn't your schedule — and the two drift furthest
apart in the months you spend most of the day indoors.

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

## Made of ordinary Home Assistant parts

Every schedule setting is an ordinary Home Assistant entity, and the room automation is an ordinary
automation, so when a default isn't what you want, you change it with the tools you already
use. For example:

- **A weekend lie-in**, by an automation that moves Morning later on Friday and Saturday
  evenings.
- **A holiday schedule**, switched on and off with a toggle.
- **A room lit by the front door opening**, not just by occupancy.
- **Blinds that close when Night starts.**

[See the examples →]({{ site.baseurl }}/examples/){: .btn .btn-outline }

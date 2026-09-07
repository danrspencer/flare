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
- **It bends to fit the room.** A brightness multiplier per light, a scene per phase,
  and templates for either when a fixed value isn't enough.
- **It gets out of your way.** Change a bulb yourself — app, wall switch, another
  automation — and FLARE stops driving that one until the room next goes dark.

---

## Four phases, not one curve

Adaptive lighting usually maps brightness and colour onto the sun's position. That tracks
the daylight closely, but the daylight isn't your schedule — and the two drift furthest
apart in the months you spend most of the day indoors.

FLARE works from your schedule instead, dividing the day into four named phases, each with
its own targets:

| Phase | What it's for |
|---|---|
| **Morning** | Bright and cold. [Research](https://pubmed.ncbi.nlm.nih.gov/36058557/) found 1.5h of bright morning light for a week improved office workers' sleep efficiency and reduced morning sleepiness. |
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
> [Play with the curve]({{ site.baseurl }}/playground/) — every boundary, value and
> transition is a slider, and the chart is the same code the dashboard card runs.

---

## Two ways in

### Standard setup — plug and play
{: .no_toc }

Install via HACS, add the integration, import the blueprint, point it at a room. Everything
below is handled for you: reachability, colour-temperature tolerances, bulbs that can't take
brightness and colour in one command, occupancy timing, and leaving a light alone once
somebody else has taken it.

[Start here →]({{ site.baseurl }}/installation/){: .btn .btn-outline }

### Power users & builders
{: .no_toc }

The blueprint is a worked example, not the product. Every piece of it is a plain Home
Assistant action you can call yourself from YAML, scripts, Node-RED or AppDaemon — and the
override-protection machinery is available standalone, whether or not you use the rest.

[Go deeper →]({{ site.baseurl }}/advanced/){: .btn .btn-outline }

---

## What "reconciliation" means

FLARE knows what every light it drives should be showing right now, and keeps working to
get it there.

That matters because lighting commands go missing. A Zigbee message drops, a bulb is
busy, the mesh hiccups — and the light quietly stays where it was. FLARE doesn't assume a
command landed just because it was sent:

- It **re-checks on a timer** and re-sends anything that isn't where it should be, so a
  command lost on first try is simply sent again.
- A bulb that was unreachable is **caught up as soon as it comes back**, rather than
  sitting wrong until the next phase.
- A bulb already at the target, within tolerance, is **left alone** — so nothing gets
  spammed, and bulbs that round values off aren't fought with.

It also expects to share a room. A **scene** can own part of one while FLARE keeps the
rest on the curve, and **tracking scopes** — one named device per room — show you at a
glance which lights FLARE is currently driving and which have been taken.

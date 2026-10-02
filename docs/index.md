---
title: Home
nav_order: 1
---

# FLARE
{: .no_toc }

**F**lexible **L**ighting **A**utomation & **R**econciliation **E**ngine. Lighting for Home
Assistant that changes brightness and colour through the day, in four phases.
{: .fs-6 .fw-300 }

[Quickstart (5 mins)]({{ site.baseurl }}/installation/){: .btn .btn-primary .mr-2 }
[Curve playground]({{ site.baseurl }}/playground/){: .btn .mr-2 }
[GitHub](https://github.com/danrspencer/flare){: .btn }

---

## What it does

- Sets each room's lights to the brightness and colour for the time of day, and checks them
  every minute.
- Turns a room's lights on when someone comes in and off once it's empty, or dims them to a
  nightlight instead.
- Leaves a light alone once you change it yourself, from an app, a wall switch or another
  automation, until the room is next dark.
- Sets a bulb to the current phase as soon as it comes back online, so lights on a wall
  switch come on at the right level.
- Hands a room to one of your scenes in any phase, and gives each light its own brightness if
  you want.
- Keeps the load on your Zigbee network down: rooms update one after another rather than all
  at once, and changes too small to see aren't sent.

---

## Four phases

Most adaptive lighting follows the sun's position. In winter that means evening lighting from
4pm; in summer, bright light until 9pm.

FLARE follows your day instead, in four phases. With the default settings:

| Phase | Default |
|---|---|
| **Morning** | Bright and cool, to help you wake up. There's [some research](https://pubmed.ncbi.nlm.nih.gov/36058557/) behind it, and it's enough to get you as far as the coffee machine. |
| **Day** | Bright, warming slowly through the afternoon. |
| **Evening** | Dimmer and warmer, starting at sunset. |
| **Night** | Low and warm until morning. |

Morning, Day and Night start at times you set. Evening starts at sunset, but no earlier and no
later than two times you set. Each phase fades into the next over a time you choose, or
switches straight away if you set it to zero.

{: .tip }
> Try the settings in the [curve playground]({{ site.baseurl }}/playground/).

---

## Home Assistant native

Every schedule setting is a Home Assistant entity, and each room runs an ordinary automation,
so you can change how FLARE behaves with automations of your own. For example:

- A weekend lie-in: move Morning later on Friday and Saturday nights.
- A holiday schedule, switched on with a toggle.
- Lighting a room from a button on a remote.
- Closing the blinds when Night starts.

[See the examples →]({{ site.baseurl }}/guides/examples/){: .btn .btn-outline }

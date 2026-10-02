---
title: Reference
nav_order: 7
has_children: true
permalink: /reference/
redirect_from: /advanced/
---

# Reference
{: .no_toc }

The documentation for FLARE's integration itself: the services it registers, the entities
it creates, and how it decides which lights it's driving. The blueprint calls these same
services, so this is also where to look for exactly why a light did what it did.

- **[Integration]({{ site.baseurl }}/reference/integration/)** — every service and entity,
  zones, schedule sensors, and how override protection decides to leave a light alone.
- **[Scene handoff]({{ site.baseurl }}/reference/scenes/)** — how FLARE shares a room with
  scenes, wall switches and other automations.
- **[Building without the blueprint]({{ site.baseurl }}/reference/custom-automations/)** —
  driving FLARE from your own YAML, scripts, Node-RED or AppDaemon instead.

For the blueprint's inputs, see [Blueprint]({{ site.baseurl }}/blueprint/). For automations
that change how FLARE behaves, see [Examples]({{ site.baseurl }}/examples/).

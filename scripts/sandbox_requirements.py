"""Print the requirements of the components the sandbox loads, followed
through their dependencies. Run with the sandbox's Python, by `mise run
sandbox:install`.

Every entity component is included because Home Assistant imports them all
to describe services, so one with a missing requirement breaks the
frontend's service list.
"""

import json
from pathlib import Path

import homeassistant.components as components

CONFIGURED = ["frontend", "config", "automation", "blueprint", "history", "logbook",
              "person", "recorder", "scene", "script", "sun", "onboarding", "group", "repairs"]

manifests = {
    path.parent.name: json.loads(path.read_text())
    for path in Path(components.__file__).parent.glob("*/manifest.json")
}
todo = [d for d, m in manifests.items() if m.get("integration_type") == "entity"] + CONFIGURED
seen = set()
while todo:
    domain = todo.pop()
    if domain in seen or domain not in manifests:
        continue
    seen.add(domain)
    todo += manifests[domain].get("dependencies", []) + manifests[domain].get("after_dependencies", [])
print("\n".join(sorted({r for d in seen for r in manifests[d].get("requirements", [])})))

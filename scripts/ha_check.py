"""Check that FLARE sets up and runs on a Home Assistant release.

    mise run ha-check                    SANDBOX_HA_VERSION's release, else hacs.json's
    python scripts/ha_check.py latest    the newest release on PyPI, betas included
    python scripts/ha_check.py issue     open, update or close the ha-compat issue

`run` (what `mise run ha-check` calls) starts a brand-new sandbox house in
.ha-check/, goes through FLARE's setup as someone pressing Submit on every
step would, runs every room's automation, and checks that FLARE's entries
load, its services register, every bulb ends up on and controlled, and the
log holds nothing from FLARE above INFO. It prints a Markdown report and
exits 1 if anything failed.

.github/workflows/ha-prerelease.yml runs it daily against the newest release.
See CONTRIBUTING.md ("Checking newer Home Assistant releases").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sandbox  # noqa: E402

ROOT = sandbox.ROOT
CONFIG = ROOT / ".ha-check"
SERVICES_YAML = ROOT / "custom_components" / "flare" / "services.yaml"
LABEL = "ha-compat"
PYPI = "https://pypi.org/pypi/homeassistant/json"
STARTUP_TIMEOUT = 600
SETTLE_TIMEOUT = 90

VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:b(\d+))?$")
TIMESTAMP = r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?(?:[+-]\d\d:\d\d)? "
LOG_LINE = re.compile(TIMESTAMP + r"(?P<level>[A-Z]+) ")
MENTIONS_FLARE = re.compile(r"\bflare\b|custom_components[/.]flare", re.IGNORECASE)
# Logged for every custom integration on every start.
EXPECTED = ("We found a custom integration flare which has not been tested",)
BULB = re.compile(r"^light\.\w+_bulb_\d+$")
FLARE_LIGHT = re.compile(r"^light\.\w+_flare$")


def version_key(version: str) -> tuple[int, int, int, int] | None:
    """Sortable, with a release after its betas; None for anything else
    (dev builds, release candidates under another scheme)."""
    if not (m := VERSION.match(version)):
        return None
    year, month, patch, beta = m.groups()
    return int(year), int(month), int(patch), int(beta) if beta is not None else sys.maxsize


def newest(releases: dict[str, list[dict]]) -> str:
    """The newest release PyPI hasn't yanked, betas included."""
    candidates = [
        v for v, files in releases.items()
        if version_key(v) and files and not all(f.get("yanked") for f in files)
    ]
    return max(candidates, key=version_key)


def submitted(fields: list[dict]) -> dict:
    """What pressing Submit sends for a form: each field's suggested value,
    else its default, sections included."""
    out: dict = {}
    for f in fields:
        if f.get("type") == "expandable":
            out[f["name"]] = submitted(f["schema"])
        elif (suggested := (f.get("description") or {}).get("suggested_value")) is not None:
            out[f["name"]] = suggested
        elif "default" in f:
            out[f["name"]] = f["default"]
    return out


def flare_log_entries(log: str) -> list[str]:
    """Each WARNING or worse that concerns FLARE, with its traceback."""
    entries: list[list[str]] = []
    for line in log.splitlines():
        if LOG_LINE.match(line) or not entries:
            entries.append([line])
        else:
            entries[-1].append(line)
    found = []
    for lines in entries:
        m = LOG_LINE.match(lines[0])
        text = "\n".join(lines)
        if m and m["level"] in ("WARNING", "ERROR", "CRITICAL") and MENTIONS_FLARE.search(text):
            if not any(e in text for e in EXPECTED):
                found.append(text)
    return found


def service_names() -> set[str]:
    return set(re.findall(r"^([a-z_]+):\s*$", SERVICES_YAML.read_text(), re.MULTILINE))


@dataclass
class Report:
    version: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((name, ok, detail))
        return ok

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks) and not self.log

    def fingerprint(self) -> str:
        """The same failures on the same release give the same marker, so a
        daily run doesn't repeat itself on the issue."""
        failed = [name for name, ok, _ in self.checks if not ok] + [first_line(e) for e in self.log]
        digest = hashlib.sha256("\n".join(failed).encode()).hexdigest()[:12]
        return f"<!-- ha-check {self.version} {digest} -->"

    def markdown(self) -> str:
        lines = [self.fingerprint(), f"### FLARE on Home Assistant {self.version}", ""]
        for name, ok, detail in self.checks:
            lines.append(f"- {'✅' if ok else '❌'} {name}" + (f": {detail}" if detail else ""))
        if self.log:
            lines += ["", f"FLARE's log entries above INFO ({len(self.log)}):", "", "```"]
            for entry in self.log[:20]:
                lines.append(entry[:3000])
            lines.append("```")
        return "\n".join(lines) + "\n"


def first_line(entry: str) -> str:
    """A log entry's message, without its timestamp."""
    return re.sub(TIMESTAMP, "", entry.splitlines()[0])


def states(token: str) -> dict[str, dict]:
    return {s["entity_id"]: s for s in sandbox.request("/api/states", token=token)}


def wait_running(hass: subprocess.Popen, token: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline and hass.poll() is None:
        try:
            if sandbox.request("/api/config", token=token).get("state") == "RUNNING":
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(2)
    raise RuntimeError("Home Assistant didn't finish starting")


def wait_for(condition, timeout: float = SETTLE_TIMEOUT):
    """condition() until it returns something truthy, or its last result."""
    deadline = time.monotonic() + timeout
    while True:
        result = condition()
        if result or time.monotonic() > deadline:
            return result
        time.sleep(2)


def set_up(token: str, report: Report) -> dict | None:
    """FLARE's setup flow, every step submitted as offered: the first menu
    option, every form's suggested or default values."""
    step = sandbox.request("/api/config/config_entries/flow", {"handler": "flare"}, token=token)
    path = []
    while step.get("type") in ("form", "menu") and len(path) < 20:
        path.append(step["step_id"])
        if step.get("errors"):
            report.check("Setup", False, f"step {step['step_id']} reported {step['errors']}")
            return None
        if step["type"] == "menu":
            answer = {"next_step_id": next(iter(step["menu_options"]))}
        else:
            answer = submitted(step.get("data_schema") or [])
        step = sandbox.request(f"/api/config/config_entries/flow/{step['flow_id']}", answer, token=token)
    ok = step.get("type") == "abort" and step.get("reason") == "setup_complete"
    detail = " → ".join(path) + f" → {step.get('type')} {step.get('reason') or ''}".rstrip()
    report.check("Setup completes", ok, detail)
    return step.get("description_placeholders") or {} if ok else None


def check(report: Report, token: str) -> None:
    summary = set_up(token, report)

    def entries_settled():
        found = sandbox.request("/api/config/config_entries/entry?domain=flare", token=token)
        return found if found and all(e["state"] in ("loaded", "setup_error", "not_loaded") for e in found) else None

    # Adding the flares reloads their entry.
    entries = wait_for(entries_settled) or sandbox.request("/api/config/config_entries/entry?domain=flare", token=token)
    not_loaded = [f"{e['title']} ({e['state']})" for e in entries if e["state"] != "loaded"]
    report.check("Config entries load", bool(entries) and not not_loaded,
                 ", ".join(not_loaded) or f"{len(entries)} loaded")

    registered = next(
        (set(d["services"]) for d in sandbox.request("/api/services", token=token) if d["domain"] == "flare"), set()
    )
    missing = sorted(service_names() - registered)
    report.check("Services register", not missing, f"missing {', '.join(missing)}" if missing else "")

    if summary is None:
        return
    want_rooms, want_flares = int(summary.get("automations", 0)), int(summary.get("flares", 0))

    def rooms_ready():
        s = states(token)
        rooms = [e for e in s if e.startswith("automation.")]
        flares = [e for e in s if FLARE_LIGHT.match(e) and s[e]["state"] != "unavailable"]
        return (rooms, flares) if len(rooms) >= want_rooms and len(flares) >= want_flares else None

    wait_for(rooms_ready)
    s = states(token)
    rooms = [e for e in s if e.startswith("automation.")]
    off = [e for e in rooms if s[e]["state"] != "on"]
    report.check("Room automations are created and on", len(rooms) >= want_rooms and not off,
                 f"{len(rooms)} of {want_rooms}" + (f", off: {', '.join(off)}" if off else ""))
    flares = [e for e in s if FLARE_LIGHT.match(e)]
    down = [e for e in flares if s[e]["state"] == "unavailable"]
    report.check("Flares are created", len(flares) >= want_flares and not down,
                 f"{len(flares)} of {want_flares}" + (f", unavailable: {', '.join(down)}" if down else ""))

    bulbs = [e for e in s if BULB.match(e)]
    sandbox.request("/api/services/automation/trigger", {"entity_id": rooms}, token=token)

    def lit():
        now = states(token)
        dark = [b for b in bulbs if now[b]["state"] != "on"]
        status = {b: now.get(f"sensor.{b.split('.', 1)[1]}_flare_status", {}).get("state") for b in bulbs}
        uncontrolled = [b for b, st in status.items() if st != "controlled"]
        return (not dark and not uncontrolled), dark, uncontrolled, status

    wait_for(lambda: lit()[0])
    _, dark, uncontrolled, status = lit()
    report.check("Running the rooms turns every bulb on", bool(bulbs) and not dark,
                 f"{len(bulbs) - len(dark)} of {len(bulbs)} on" + (f", off: {', '.join(dark)}" if dark else ""))
    report.check("Every bulb is controlled", bool(bulbs) and not uncontrolled,
                 ", ".join(f"{b}: {status[b]}" for b in uncontrolled))


def run(args: argparse.Namespace) -> int:
    version = (sandbox.VENV / "installed").read_text().strip()
    report = Report(version)
    sandbox.prepare(CONFIG, reset=True, hacs=False)
    hass = subprocess.Popen([sandbox.HASS, "-c", CONFIG], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        token = sandbox.onboard(hass)
        report.check("Home Assistant starts", token is not None)
        if token:
            wait_running(hass, token)
            check(report, token)
            # Anything a run logs as it finishes.
            time.sleep(5)
    except Exception as err:  # noqa: BLE001 - any failure is the report's to show
        report.check("The check ran to the end", False, f"{type(err).__name__}: {err}")
    finally:
        if hass.poll() is None:
            hass.terminate()
            hass.wait(timeout=60)
    log = CONFIG / "home-assistant.log"
    report.log = flare_log_entries(log.read_text(errors="replace")) if log.exists() else []
    report.check("FLARE logs nothing above INFO", not report.log,
                 f"{len(report.log)} entries" if report.log else "")
    text = report.markdown()
    print(text)
    if args.report:
        Path(args.report).write_text(text)
    return 0 if report.passed else 1


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def issue(args: argparse.Namespace) -> int:
    """One open issue labelled ha-compat while the check fails: opened on
    the first failure, commented on when the release or what fails
    changes, closed once it passes."""
    run_url = os.environ.get("RUN_URL", "")
    report = Path(args.report).read_text() if args.report and Path(args.report).exists() else (
        f"<!-- ha-check {args.version} setup -->\n### FLARE on Home Assistant {args.version}\n\n"
        "The check didn't get as far as a report: installing that release probably failed.\n"
    )
    found = json.loads(gh("issue", "list", "--label", LABEL, "--state", "open", "--json", "number,body,comments"))
    current = found[0] if found else None
    marker = report.splitlines()[0]
    link = f"\n[The run]({run_url})\n" if run_url else ""

    if args.outcome == "success":
        if current:
            gh("issue", "comment", str(current["number"]), "--body", f"Passes on Home Assistant {args.version}.{link}")
            gh("issue", "close", str(current["number"]))
        return 0
    if current:
        seen = [current["body"]] + [c["body"] for c in current["comments"]]
        if not any(marker in body for body in seen):
            gh("issue", "comment", str(current["number"]), "--body", report + link)
        return 0
    gh("label", "create", LABEL, "--force", "--color", "D93F0B",
       "--description", "FLARE fails on a newer Home Assistant (ha-prerelease.yml)")
    body = (
        "The daily check (`.github/workflows/ha-prerelease.yml`) found FLARE failing on the newest "
        "Home Assistant release. It comments here when the release or what fails changes, and closes "
        "this once it passes. To reproduce, `SANDBOX_HA_VERSION=" + args.version + " mise run ha-check`.\n\n"
        + report + link
    )
    gh("issue", "create", "--title", f"FLARE fails on Home Assistant {args.version}",
       "--label", LABEL, "--body", body)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")
    run_parser = sub.add_parser("run", help="check the sandbox's installed release (the default)")
    run_parser.add_argument("--report", help="also write the Markdown report here")
    sub.add_parser("latest", help="print the newest release on PyPI, betas included")
    issue_parser = sub.add_parser("issue", help="open, update or close the ha-compat issue")
    issue_parser.add_argument("--version", required=True)
    issue_parser.add_argument("--outcome", required=True, choices=["success", "failure"])
    issue_parser.add_argument("--report")
    args = parser.parse_args(argv or ["run"])

    if args.command == "latest":
        with urllib.request.urlopen(PYPI, timeout=30) as response:
            print(newest(json.load(response)["releases"]))
        return 0
    if args.command == "issue":
        return issue(args)
    if not sandbox.PORT or not sandbox.HASS.exists():
        sys.exit("Run the check through mise: mise run ha-check")
    return run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

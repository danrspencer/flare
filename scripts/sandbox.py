"""Run a throwaway Home Assistant with FLARE and a fake house.

    mise run sandbox         start it, setting it up on first run
    mise run sandbox:reset   start again from a brand-new house
    mise run sandbox:hacs    a separate house with HACS and no FLARE

mise installs Home Assistant into .venv-sandbox/ first and sets
SANDBOX_PORT. This runs it from .sandbox/, with FLARE linked in from this
checkout. On first run onboarding is completed through its own API, so the
browser lands on a house with no FLARE in it, ready for Add Integration.
With --hacs it runs from .sandbox-hacs/ instead, with HACS copied in from
.venv-sandbox/hacs/ and FLARE left for HACS to install.
See CONTRIBUTING.md ("A sandbox Home Assistant").
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("SANDBOX_PORT", "0"))
URL = f"http://127.0.0.1:{PORT}"
CLIENT_ID = f"{URL}/"
OWNER = {"name": "Sandbox", "username": "sandbox", "password": "sandbox", "language": "en-GB"}

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sandbox"
VENV = ROOT / ".venv-sandbox"
HASS = VENV / "bin" / "hass"
HACS = VENV / "hacs" / "hacs"
HOUSE = SOURCE / "custom_components" / "sandbox_house"
FLARE = ROOT / "custom_components" / "flare"
# The HACS house has a config dir of its own, since HACS installs FLARE
# into custom_components/flare, which in the other links to this checkout.
CONFIG = ROOT / ".sandbox"
HACS_CONFIG = ROOT / ".sandbox-hacs"


def prepare(config: Path, reset: bool, hacs: bool) -> None:
    if reset and config.exists():
        shutil.rmtree(config)
    config.mkdir(exist_ok=True)
    shutil.copyfile(SOURCE / "configuration.yaml", config / "configuration.yaml")
    for name, empty in (("automations.yaml", "[]\n"), ("scenes.yaml", ""), ("scripts.yaml", "")):
        if not (config / name).exists():
            (config / name).write_text(empty)
    # The port lives in HA's own store, not YAML: a port set in YAML is a
    # trial that HA asks to confirm, and reverts five minutes later. This is
    # the store a fresh SANDBOX_HA_VERSION writes, with the port changed.
    http = config / ".storage" / "http"
    if not http.exists():
        http.parent.mkdir(exist_ok=True)
        stable = {
            "server_port": PORT,
            "cors_allowed_origins": ["https://cast.home-assistant.io"],
            "login_attempts_threshold": -1,
            "ip_ban_enabled": True,
            "ssl_profile": "modern",
            "use_x_frame_options": True,
            "created_at": "2026-01-01T00:00:00+00:00",
            "error": None,
            "error_message": None,
        }
        http.write_text(json.dumps({
            "version": 2,
            "minor_version": 2,
            "key": "http",
            "data": {"stable": stable, "pending": None, "yaml_migration_done": True},
        }))
    components = config / "custom_components"
    components.mkdir(exist_ok=True)
    links = {"sandbox_house": HOUSE} if hacs else {"flare": FLARE, "sandbox_house": HOUSE}
    for name, target in links.items():
        link = components / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
    # Copied, not linked: HACS updates itself in place.
    if hacs:
        shutil.rmtree(components / "hacs", ignore_errors=True)
        shutil.copytree(HACS, components / "hacs")


def request(path: str, data: dict | None = None, *, token: str | None = None, form: bool = False):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(URL + path, body, headers), timeout=10) as response:
        return json.load(response)


def onboarding_steps(hass: subprocess.Popen) -> dict[str, bool]:
    """Wait for the HTTP server (a first start installs the frontend,
    which takes a few minutes), then report which steps are done."""
    while hass.poll() is None:
        try:
            return {step["step"]: step["done"] for step in request("/api/onboarding")}
        except urllib.error.HTTPError as err:
            # HA removes the onboarding API once onboarding is finished.
            if err.code == 404:
                return {}
            time.sleep(2)
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(2)
    sys.exit("Home Assistant stopped before it was ready")


def onboard(hass: subprocess.Popen) -> None:
    done = onboarding_steps(hass)
    if all(done.values()):
        return
    print("Completing onboarding ...", flush=True)
    code = request("/api/onboarding/users", {**OWNER, "client_id": CLIENT_ID})["auth_code"]
    token = request(
        "/auth/token",
        {"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID},
        form=True,
    )["access_token"]
    request("/api/onboarding/core_config", {}, token=token)
    request("/api/onboarding/analytics", {}, token=token)
    request(
        "/api/onboarding/integration",
        {"client_id": CLIENT_ID, "redirect_uri": f"{URL}/?auth_callback=1"},
        token=token,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="throw away the house's state and start a brand-new one")
    parser.add_argument("--hacs", action="store_true", help="run a separate house with HACS and no FLARE")
    args = parser.parse_args()
    if not PORT or not HASS.exists() or (args.hacs and not HACS.exists()):
        sys.exit("Run the sandbox through mise: mise run sandbox, or mise run sandbox:hacs")

    config = HACS_CONFIG if args.hacs else CONFIG
    prepare(config, args.reset, args.hacs)
    hass = subprocess.Popen([HASS, "-c", config])
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        onboard(hass)
        if hass.poll() is not None:
            sys.exit(hass.returncode)
        print(f"Sandbox ready at {URL}", flush=True)
        # Whatever stops Home Assistant, start it again: only stopping this
        # (Ctrl-C, or the mise task being killed) ends the sandbox.
        while True:
            code = hass.wait()
            print(f"Home Assistant stopped (exit code {code}), starting it again ...", flush=True)
            time.sleep(1)
            hass = subprocess.Popen([HASS, "-c", config])
    except KeyboardInterrupt:
        pass
    finally:
        if hass.poll() is None:
            hass.terminate()
            hass.wait()

if __name__ == "__main__":
    main()

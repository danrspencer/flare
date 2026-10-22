"""Run a throwaway Home Assistant with FLARE and a fake house.

    mise run sandbox         start it, setting it up on first run
    mise run sandbox:reset   start again from a brand-new house

mise installs Home Assistant into .venv-sandbox/ first and sets
SANDBOX_PORT. This runs it from .sandbox/, with FLARE linked in from this
checkout. On first run onboarding is completed through its own API, so the
browser lands on a house with no FLARE in it, ready for Add Integration.
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
# homeassistant.const.RESTART_EXIT_CODE
RESTART_EXIT_CODE = 100
OWNER = {"name": "Sandbox", "username": "sandbox", "password": "sandbox", "language": "en-GB"}

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sandbox"
CONFIG = ROOT / ".sandbox"
VENV = ROOT / ".venv-sandbox"
HASS = VENV / "bin" / "hass"
LINKS = {
    "flare": ROOT / "custom_components" / "flare",
    "sandbox_house": SOURCE / "custom_components" / "sandbox_house",
}


def prepare(reset: bool) -> None:
    if reset and CONFIG.exists():
        shutil.rmtree(CONFIG)
    CONFIG.mkdir(exist_ok=True)
    shutil.copyfile(SOURCE / "configuration.yaml", CONFIG / "configuration.yaml")
    for name, empty in (("automations.yaml", "[]\n"), ("scenes.yaml", ""), ("scripts.yaml", "")):
        if not (CONFIG / name).exists():
            (CONFIG / name).write_text(empty)
    # The port lives in HA's own store, not YAML: a port set in YAML is a
    # trial that HA asks to confirm, and reverts five minutes later. This is
    # the store a fresh SANDBOX_HA_VERSION writes, with the port changed.
    http = CONFIG / ".storage" / "http"
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
    components = CONFIG / "custom_components"
    components.mkdir(exist_ok=True)
    for name, target in LINKS.items():
        link = components / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)


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
    parser.add_argument("--reset", action="store_true", help="throw away .sandbox/ and start a brand-new house")
    args = parser.parse_args()
    if not PORT or not HASS.exists():
        sys.exit("Run the sandbox through mise: mise run sandbox")

    prepare(args.reset)
    hass = subprocess.Popen([HASS, "-c", CONFIG])
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        onboard(hass)
        if hass.poll() is not None:
            sys.exit(hass.returncode)
        print(f"Sandbox ready at {URL}", flush=True)
        # Restarting from HA's UI exits with this, for whatever started it
        # to start it again.
        while hass.wait() == RESTART_EXIT_CODE:
            print("Restarting Home Assistant ...", flush=True)
            hass = subprocess.Popen([HASS, "-c", CONFIG])
    except KeyboardInterrupt:
        pass
    finally:
        if hass.poll() is None:
            hass.terminate()
            hass.wait()

if __name__ == "__main__":
    main()

"""Record walkthrough videos of FLARE in the sandbox.

    mise run sandbox:record                one video after another
    mise run sandbox:record -- setup       just the first
    mise run sandbox:record -- customise   the second needs the first's house

Starts a brand-new sandbox (stop any running one first), clears the
notifications and repairs a new install shows, then plays each scene in
a fresh browser with a visible pointer. Once every scene has recorded,
the videos and their still frames go to docs/assets/video/ and the
README's GIF to docs/assets/img/: commit them. Working files, and a
screenshot of any step that fails, stay in sandbox/recordings/. Run by
mise, with .venv-record's Playwright.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sandbox" / "recordings"
VIDEOS = ROOT / "docs" / "assets" / "video"
# The README shows the setup as a GIF: GitHub and HACS show images, not video.
README_GIF = {"setup": ROOT / "docs" / "assets" / "img" / "setup.gif"}
PORT = int(os.environ.get("SANDBOX_PORT", "0"))
URL = f"http://localhost:{PORT}"
# Tall enough for a schedule's graph and all its sliders at once.
SIZE = {"width": 1280, "height": 1000}

# A pointer that follows the mouse, since a recording shows none. It starts
# where the last page left it.
POINTER = """
window.addEventListener('DOMContentLoaded', () => {
  const [x, y] = (sessionStorage.getItem('pointer') || '640,500').split(',');
  const pointer = document.createElement('div');
  pointer.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 11.5-6.6 1.1 4.1 7.4-3 1.6-4.1-7.5L4 20z" fill="#111" stroke="#fff" stroke-width="1.6"/></svg>';
  Object.assign(pointer.style, {position: 'fixed', left: '0', top: '0', zIndex: 2147483647,
    pointerEvents: 'none', transform: 'translate(-3px, -2px)', transition: 'scale 0.12s'});
  pointer.style.left = x + 'px';
  pointer.style.top = y + 'px';
  document.documentElement.appendChild(pointer);
  addEventListener('mousemove', (e) => {
    pointer.style.left = e.clientX + 'px';
    pointer.style.top = e.clientY + 'px';
    sessionStorage.setItem('pointer', e.clientX + ',' + e.clientY);
  }, true);
  addEventListener('mousedown', () => { pointer.style.scale = '0.85'; }, true);
  addEventListener('mouseup', () => { pointer.style.scale = '1'; }, true);
});
"""


# --- The sandbox ----------------------------------------------------------


def onboarded() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/api/onboarding", timeout=2) as response:
            return all(step["done"] for step in json.load(response))
    except OSError:
        return False


def start_sandbox() -> subprocess.Popen:
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"Something is already on port {PORT}: stop the sandbox first.")
    sandbox = subprocess.Popen(
        [sys.executable, ROOT / "scripts" / "sandbox.py", "--reset"], stdout=subprocess.DEVNULL
    )
    deadline = time.monotonic() + 600
    while not onboarded():
        if sandbox.poll() is not None or time.monotonic() > deadline:
            sys.exit("The sandbox didn't start")
        time.sleep(1)
    return sandbox


# --- Acting like a person -------------------------------------------------


class Director:
    """Moves the pointer to things before using them, at a watchable pace."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.x, self.y = SIZE["width"] / 2, SIZE["height"] / 2

    def pause(self, seconds: float = 0.8) -> None:
        self.page.wait_for_timeout(seconds * 1000)

    def point_at(self, target: Locator, dx: float = 0.5, dy: float = 0.5) -> tuple[float, float]:
        target.wait_for(state="visible", timeout=20000)
        self.wheel_to(target)
        target.scroll_into_view_if_needed()
        box = target.bounding_box()
        x, y = box["x"] + box["width"] * dx, box["y"] + box["height"] * dy
        self.page.mouse.move(x, y, steps=max(8, int(((x - self.x) ** 2 + (y - self.y) ** 2) ** 0.5 / 18)))
        self.x, self.y = x, y
        return x, y

    def wheel_to(self, target: Locator) -> None:
        """Scrolls a target into view with the mouse wheel, as a person
        would, from over the column it's in. Stops if the page doesn't move,
        leaving anything else to scroll_into_view_if_needed."""
        last = None
        for _ in range(80):
            box = target.bounding_box()
            if box is None or 0 <= box["y"] and box["y"] + box["height"] <= SIZE["height"]:
                return
            if box["y"] == last:
                return
            if last is None:
                x = box["x"] + box["width"] / 2
                y = min(max(box["y"], 200), SIZE["height"] - 200)
                self.page.mouse.move(x, y, steps=12)
                self.x, self.y = x, y
            last = box["y"]
            self.page.mouse.wheel(0, 100 if box["y"] > 0 else -100)
            self.page.wait_for_timeout(30)

    def click(self, target: Locator, pause: float = 0.6) -> None:
        self.point_at(target)
        self.pause(0.25)
        self.page.mouse.down()
        self.page.mouse.up()
        self.pause(pause)

    def open(self, target: Locator, shows: Locator, pause: float = 0.8) -> None:
        """Clicks until `shows` appears: early on a page, HA can drop a click
        that lands before it's ready."""
        for _ in range(4):
            self.click(target, pause=0)
            try:
                shows.wait_for(state="visible", timeout=5000)
                break
            except PlaywrightTimeout:
                continue
        else:
            raise PlaywrightTimeout(f"clicking {target} never showed {shows}")
        self.pause(pause)

    def type(self, into: Locator, text: str, pause: float = 0.6) -> None:
        """Into a field, which it focuses first: a key pressed with nothing
        focused is one of HA's shortcuts."""
        self.click(into, pause=0.3)
        into.press_sequentially(text, delay=90)
        # Unfocused, or a later wheel over a number box changes it.
        into.evaluate("e => e.blur()")
        self.pause(pause)

    def scroll(self, over: Locator, pixels: int, step: int = 100) -> None:
        self.point_at(over)
        for _ in range(abs(pixels) // step):
            self.page.mouse.wheel(0, step if pixels > 0 else -step)
            self.page.wait_for_timeout(30)
        self.pause(0.5)

    def drag(self, target: Locator, start: float, end: float) -> None:
        """Along a horizontal slider, from one fraction of its width to another."""
        box = target.bounding_box()
        y = box["y"] + box["height"] / 2
        self.point_at(target, start)
        self.page.mouse.down()
        self.page.mouse.move(box["x"] + box["width"] * end, y, steps=25)
        self.page.mouse.up()
        self.x = box["x"] + box["width"] * end
        self.pause(0.8)


def ha_ready(page: Page) -> None:
    """Connected, with HA's loading screen gone."""
    page.wait_for_function(
        "() => document.querySelector('home-assistant')?.hass?.connected && !document.getElementById('ha-launch-screen')"
    )


def call_ws(page: Page, message: dict) -> object:
    return page.evaluate("(m) => document.querySelector('home-assistant').hass.callWS(m)", message)


def call_api(page: Page, method: str, path: str, data: dict | None = None) -> object:
    return page.evaluate(
        "([m, p, d]) => document.querySelector('home-assistant').hass.callApi(m, p, d)", [method, path, data]
    )


# --- Recording ------------------------------------------------------------


def record(browser, name: str, scene: Callable[[Director], None]) -> Path:
    """Plays a scene in a fresh browser and saves it, trimmed to start once
    the first page has loaded."""
    context = browser.new_context(viewport=SIZE, record_video_dir=OUT / ".raw", record_video_size=SIZE)
    context.add_init_script(POINTER)
    page = context.new_page()
    opened = time.monotonic()  # the video's first frame
    # HA's first load in a browser reloads itself once its service worker
    # is in; get that over with before the part that's kept.
    page.goto(URL)
    ha_ready(page)
    page.wait_for_timeout(3000)
    director = Director(page)
    page.mouse.move(director.x, director.y)
    director.started = None
    try:
        scene(director)
    except Exception:
        page.screenshot(path=OUT / f"{name}-failed.png")
        context.close()
        raise
    director.pause(1.5)
    context.close()
    raw = Path(page.video.path())
    out = OUT / f"{name}.mp4"
    skip = max(0.0, (director.started or opened) - opened)
    ffmpeg("-ss", f"{skip:.2f}", "-i", raw, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
           "-movflags", "+faststart", out)
    raw.unlink()
    return out


def ffmpeg(*args) -> None:
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", *map(str, args)], check=True)


def publish(name: str, video: Path) -> list[Path]:
    """The video and a still from near its end, where it shows what was
    done, for the site; and the README's GIF, if it has one."""
    VIDEOS.mkdir(parents=True, exist_ok=True)
    out = [VIDEOS / f"{name}.mp4", VIDEOS / f"{name}.jpg"]
    out[0].write_bytes(video.read_bytes())
    ffmpeg("-sseof", "-2", "-i", video, "-frames:v", "1", "-q:v", "3", out[1])
    if gif := README_GIF.get(name):
        # 800 wide at 10 frames a second keeps the text readable in a few MB.
        palette = "fps=10,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];" \
            "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
        ffmpeg("-i", video, "-vf", palette, gif)
        out.append(gif)
    return out


def action(director: Director) -> None:
    """Where the video starts: everything before is cut."""
    director.started = time.monotonic()


def tidy(browser) -> None:
    """Clears what a brand-new install shows before anyone records it."""
    context = browser.new_context(viewport=SIZE)
    page = context.new_page()
    page.goto(URL)
    ha_ready(page)
    for issue in call_ws(page, {"type": "repairs/list_issues"})["issues"]:
        if issue["domain"] == "homeassistant":
            call_ws(page, {"type": "repairs/ignore_issue", "domain": issue["domain"], "issue_id": issue["issue_id"], "ignore": True})
    call_ws(page, {"type": "call_service", "domain": "persistent_notification", "service": "dismiss_all"})
    context.close()


# --- The scenes -----------------------------------------------------------


def setup(d: Director) -> None:
    """Adding FLARE, one schedule per floor, then its dashboard."""
    page = d.page
    page.goto(f"{URL}/config/integrations/dashboard")
    ha_ready(page)
    page.get_by_text("Sandbox House").wait_for()
    action(d)
    d.pause(1.2)

    search = page.get_by_placeholder("Search for a brand name")
    d.open(page.locator("ha-button", has_text="Add integration"), search)
    d.type(search, "FLARE")
    d.click(page.get_by_role("listitem").filter(has_text="FLARE").first, pause=1.5)
    d.click(page.get_by_text("One per floor:"), pause=0.8)
    d.click(page.get_by_role("button", name="Submit"), pause=1.5)
    d.click(page.get_by_text("Set up room automations"), pause=1.5)

    d.pause(0.8)
    d.scroll(page.get_by_text("Pick the schedule each area follows"), 1200)
    d.pause(1)
    d.click(page.get_by_role("button", name="Submit"), pause=2.5)

    d.click(page.get_by_role("link", name="Reload this page"), pause=0)
    ha_ready(page)
    page.get_by_role("button", name="Add dashboard").wait_for()
    d.pause(1.2)

    d.click(page.get_by_role("button", name="Add dashboard"), pause=1)
    d.click(page.get_by_text("FLARE Lighting", exact=True), pause=1.5)
    d.click(page.get_by_role("button", name="Create"), pause=1.2)

    # What setup made: an automation per room, labelled FLARE.
    d.click(page.get_by_role("link", name="Settings"), pause=0.8)
    d.click(page.get_by_text("Automations & scenes"), pause=3)

    d.click(page.get_by_role("link", name="FLARE").first, pause=0)
    page.wait_for_url("**/dashboard-flare/**")
    d.pause(3)


MOVIE_TEMPLATE = """{% if is_state('media_player.living_room_tv', 'on')
and states('sensor.downstairs_flare') in ['Evening', 'Night'] %}
scene.living_room_movie_night
{% endif %}"""


def customise(d: Director) -> None:
    """Tuning both schedules with their graphs in view, then a nightlight in
    the bedroom and a movie-night scene template in the living room."""
    page = d.page
    page.goto(f"{URL}/dashboard-flare/downstairs")
    ha_ready(page)

    def tile(name: str) -> Locator:
        """By its name; not the Phase tile, whose dropdown lists the phases."""
        tiles = page.locator("hui-tile-card").filter(has=page.get_by_text(name, exact=True))
        return tiles.filter(has_not_text="Phase").first

    def slider(name: str) -> Locator:
        return tile(name).locator("ha-control-slider")

    def set_hour(name: str, hour: str) -> None:
        hours = page.locator("input[name=hours]")
        d.open(tile(name), hours)
        d.type(hours, hour)
        page.keyboard.press("Escape")
        d.pause(1.2)

    slider("Evening brightness").wait_for()
    action(d)
    d.pause(1.5)
    d.drag(slider("Evening brightness"), 0.8, 0.55)
    d.drag(slider("Night colour temp"), 0.45, 0.2)
    d.pause(1.5)

    d.click(page.get_by_role("tab", name="Upstairs"), pause=1.5)
    set_hour("Evening (latest)", "9")
    set_hour("Night", "11")
    d.drag(slider("Evening colour temp"), 0.5, 0.3)
    d.drag(slider("Night brightness"), 0.4, 0.15)
    d.pause(1.5)

    d.click(page.get_by_role("link", name="Settings"), pause=0.8)
    d.click(page.get_by_text("Automations & scenes"), pause=1.5)

    def field(name: str) -> Locator:
        """A blueprint input, named in its row rather than labelled."""
        return page.locator("ha-settings-row").filter(has=page.get_by_text(name, exact=True)).first

    d.click(page.get_by_text("Bedroom Lighting"), pause=1.5)
    d.click(page.get_by_text("Idle Brightness", exact=True), pause=1)
    night = field("Night Idle Brightness").locator("input")
    night.fill("")
    d.type(night, "20")
    d.click(page.get_by_role("button", name="Save"), pause=1.5)
    page.go_back()
    d.pause(1.2)

    # Off screen: the TV on and the evening here, so the template has
    # something to show.
    call_ws(page, {"type": "call_service", "domain": "media_player", "service": "turn_on",
                   "target": {"entity_id": "media_player.living_room_tv"}})
    call_ws(page, {"type": "call_service", "domain": "select", "service": "select_option",
                   "target": {"entity_id": "select.downstairs_flare_phase"}, "service_data": {"option": "Evening"}})

    d.click(page.get_by_text("Living Room Lighting"), pause=1.5)
    search = page.get_by_placeholder("Search", exact=True)
    d.click(page.get_by_text("Sensors & Triggers", exact=True), pause=0.8)
    d.open(field("Additional Triggers").locator("ha-entity-picker").last, search)
    d.type(search, "TV")
    d.click(page.get_by_text("TV", exact=True).last, pause=1)

    d.click(page.get_by_text("Scene Handoff", exact=True), pause=0.8)
    template = field("Scene Template")
    # Up the screen, leaving room under the editor for its result.
    d.scroll(page.get_by_text("Scene Handoff", exact=True), 500)
    d.click(template.locator(".cm-content"), pause=0.3)
    page.keyboard.type(MOVIE_TEMPLATE, delay=25)
    # The editor closes brackets as they're typed; drop what it added.
    page.keyboard.press("Shift+ControlOrMeta+End")
    page.keyboard.press("Delete")
    d.pause(0.8)
    d.click(template.locator("ha-icon-button").first, pause=2.5)
    d.click(page.get_by_role("button", name="Save"), pause=2)


def movie_scene(browser) -> None:
    """A scene for the living room's evenings, which a new house lacks."""
    context = browser.new_context(viewport=SIZE)
    page = context.new_page()
    page.goto(URL)
    ha_ready(page)
    lights = {f"light.living_room_bulb_{n}": {"state": "on", "brightness": 70, "color_temp_kelvin": 2200} for n in (1, 2)}
    call_api(page, "POST", "config/scene/config/living_room_movie_night", {"name": "Living Room Movie Night", "entities": lights})
    context.close()


SCENES = {"setup": setup, "customise": customise}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenes", nargs="*", default=list(SCENES), help=", ".join(SCENES))
    args = parser.parse_args()
    if unknown := set(args.scenes) - set(SCENES):
        sys.exit(f"No such scene: {', '.join(sorted(unknown))}")
    if not PORT:
        sys.exit("Run it through mise: mise run sandbox:record")
    if args.scenes == ["customise"]:
        sys.exit("customise picks up where setup ends: record both")

    OUT.mkdir(parents=True, exist_ok=True)
    recorded: dict[str, Path] = {}
    sandbox = start_sandbox()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            tidy(browser)
            for name in args.scenes:
                if name == "customise":
                    movie_scene(browser)
                print(f"Recording {name} ...", flush=True)
                recorded[name] = record(browser, name, SCENES[name])
            browser.close()
        # Only once every scene has recorded, so a failure leaves the
        # published ones as they were.
        for name, video in recorded.items():
            for path in publish(name, video):
                print(f"  {path.relative_to(ROOT)}", flush=True)
    finally:
        sandbox.terminate()
        sandbox.wait()


if __name__ == "__main__":
    main()

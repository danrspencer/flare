#!/usr/bin/env python3
"""
Generates brand/icon.svg - the integration's icon - from the actual
curve module rather than being drawn by hand: the icon IS the day's
brightness/colour curve, not an
artist's impression of it. Bar heights come from brightness_for_phase,
bar colours from kelvin_for_phase run through kelvin_to_rgb, and the
schedule is curve.py's own DEFAULT_SCHEDULE_HOURS - change the
defaults and a regenerated icon follows.

This file (and icon.svg, its output) is design/authoring tooling only -
it lives here, not inside the integration package, and is NOT what HA
actually reads. Since HA 2026.3.0, a custom integration ships its own
brand icon directly inside its own folder - see
`custom_components/flare/brand/` (icon.png,
icon@2x.png), served automatically via HA's local brands API with no
manifest.json changes and no external submission needed.
`home-assistant/brands` (the previous mechanism, a central repo custom
integrations used to submit icons to) has since stopped accepting PRs
for custom integrations entirely, so that path is no longer viable even
as a fallback - confirmed live, 2026-08-13: no
`custom_integrations/flare/` entry and no open PR
for one exist there.

This script writes BOTH icon.svg and the two PNGs Home Assistant
actually serves, `custom_components/flare/brand/{icon.png,icon@2x.png}`.

It used to write only the SVG, with a docstring telling you to render
the PNGs by hand via `qlmanage -t -s 256`, "transparency preserved".
That was wrong: `qlmanage` composites onto WHITE, so every icon it
produced had opaque white corners instead of a transparent background -
which is what shipped, and what showed up as a white square behind the
icon on Home Assistant's own integrations page. A separate manual step
that silently produces the wrong file is worse than no step, so the
rendering lives here now, drawn directly rather than shelling out to a
thumbnailer.

Drawn with Pillow at 4x and downsampled, which is what keeps the
rounded corners clean without an SVG rasteriser dependency. The shapes
are simple enough (one rounded tile, seven rounded bars) that drawing
them twice - once as SVG, once as pixels - costs less than depending on
librsvg or cairosvg being installed.

Needs Pillow: `pip install pillow`.

Run from the repo root: python3 brand/generate_icon.py
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "flare"))
from curve import (  # noqa: E402
    DEFAULT_SCHEDULE_HOURS,
    brightness_for_phase,
    kelvin_for_phase,
    kelvin_to_rgb,
    phase_at,
)

SIZE = 256
CORNER_R = 58  # squircle-ish, matches typical brand-icon rounding
BG = "#171a26"  # deep night-blue, so both the warm and cool ends pop

# Chart area inside the tile.
PAD_X = 34
PAD_BOTTOM = 46
PAD_TOP = 56
CHART_W = SIZE - 2 * PAD_X
CHART_H = SIZE - PAD_TOP - PAD_BOTTOM

N_BARS = 7  # same bar language as the dashboard card, icon-sized

# A representative day (hours -> synthetic
# timestamps; the curve functions only care about differences).
MORNING = DEFAULT_SCHEDULE_HOURS["morning"] * 3600
DAY = DEFAULT_SCHEDULE_HOURS["day"] * 3600
EVENING = 18 * 3600  # a mid-window sunset, between earliest and latest
NIGHT = DEFAULT_SCHEDULE_HOURS["night"] * 3600

# Zoom the icon onto the interesting stretch of the day - from just
# before Morning to just after Night - rather than the full 24h, half
# of which is a flat night shelf that wastes icon real estate.
T_START = MORNING - 3 * 3600
T_END = NIGHT + 3 * 3600


BRAND_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "flare" / "brand"

# Drawn this many times larger and scaled back down. Pillow has no
# antialiasing of its own, so a rounded corner drawn at final size comes
# out visibly stepped; downsampling from 4x is what makes the tile's
# corners and the bars' caps smooth.
SUPERSAMPLE = 4


def y_of(brightness):
    return SIZE - PAD_BOTTOM - (brightness / 255) * CHART_H


def render_png(bars, size):
    """The same shapes the SVG describes, as pixels - on a TRANSPARENT
    background.

    That last part is the entire point of this function existing. The
    tile is a rounded rectangle, so the four corners outside it must be
    alpha 0; the thumbnailer this replaced composited them onto white,
    and Home Assistant drew the result as a white square behind the
    icon."""
    scale = size / SIZE * SUPERSAMPLE
    image = Image.new("RGBA", (int(SIZE * scale), int(SIZE * scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (0, 0, SIZE * scale - 1, SIZE * scale - 1),
        radius=CORNER_R * scale,
        fill=BG,
    )
    for x, y, w, h, radius, colour in bars:
        draw.rounded_rectangle(
            (x * scale, y * scale, (x + w) * scale - 1, (y + h) * scale - 1),
            radius=radius * scale,
            fill=colour,
        )

    return image.resize((size, size), Image.LANCZOS)


def main():
    # One bar per sample across the zoomed window - the dashboard card's
    # bar language, at icon scale. Each bar's height is the real
    # brightness and its colour the real Kelvin at that instant; the
    # hard jump at Morning and the evening fade are what make this
    # schedule recognisably itself.
    slot_w = CHART_W / N_BARS
    bar_w = slot_w * 0.68
    baseline = SIZE - PAD_BOTTOM

    # Geometry once, rendered twice - as SVG below and as pixels in
    # render_png. Two hand-maintained copies of the same seven bars is
    # exactly how the icon and its source drift apart.
    bar_specs = []
    for i in range(N_BARS):
        t = T_START + (T_END - T_START) * (i + 0.5) / N_BARS
        phase = phase_at(t, MORNING, DAY, EVENING, NIGHT)
        # Both take (phase, now, morning, day, evening, night). Note
        # targets_for_phase in curve.py takes those four in a
        # DIFFERENT order - don't copy this call over to that one.
        b = brightness_for_phase(phase, t, MORNING, DAY, EVENING, NIGHT)
        colour = kelvin_to_rgb(kelvin_for_phase(phase, t, MORNING, DAY, EVENING, NIGHT))
        x = PAD_X + i * slot_w + (slot_w - bar_w) / 2
        h = baseline - y_of(b)
        bar_specs.append((x, baseline - h, bar_w, h, bar_w / 2, colour))

    bars = [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'rx="{r:.1f}" fill="rgb({c[0]},{c[1]},{c[2]})" />'
        for x, y, w, h, r, c in bar_specs
    ]

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">
  <rect x="0" y="0" width="{SIZE}" height="{SIZE}" rx="{CORNER_R}" fill="{BG}" />
  {chr(10).join('  ' + b for b in bars).strip()}
</svg>
"""

    out_path = Path(__file__).resolve().parent / "icon.svg"
    out_path.write_text(svg)
    print(f"wrote {out_path}")

    for size, name in ((SIZE, "icon.png"), (SIZE * 2, "icon@2x.png")):
        png_path = BRAND_DIR / name
        render_png(bar_specs, size).save(png_path)
        print(f"wrote {png_path}")


if __name__ == "__main__":
    main()

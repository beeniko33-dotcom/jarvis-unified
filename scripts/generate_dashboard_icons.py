#!/usr/bin/env python3
"""Regenerate the dashboard PNG icons from the geometry of apps/dashboard/icon.svg.

iOS ignores SVG touch icons and Android install prompts expect 192/512 px PNGs, so the
dashboard ships raster icons next to the SVG. This is a developer tool: it needs Pillow
(``pip install pillow``) but the runtime has no dependency on it. Output is deterministic.

    python scripts/generate_dashboard_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - developer tool
    sys.exit("Pillow is required to regenerate icons: pip install pillow")

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "apps" / "dashboard" / "icons"

BACKGROUND = (20, 27, 47, 255)  # #141b2f, same as icon.svg
STROKE = (93, 222, 166, 255)  # #5ddea6
SUPERSAMPLE = 4

# Geometry in the SVG's 64x64 viewBox.
LINE = [(14, 43), (26, 31), (34, 38), (50, 20)]
ARROW = [(39, 20), (50, 20), (50, 31)]
STROKE_WIDTH = 5
CORNER_RADIUS = 14
CENTER = (32, 32)


def _stroke(draw: ImageDraw.ImageDraw, points, unit: float, scale: float) -> None:
    mapped = [
        ((CENTER[0] + (x - CENTER[0]) * scale) * unit, (CENTER[1] + (y - CENTER[1]) * scale) * unit)
        for x, y in points
    ]
    width = STROKE_WIDTH * scale * unit
    draw.line(mapped, fill=STROKE, width=round(width), joint="curve")
    radius = width / 2
    for x, y in mapped:  # round caps and joins, as stroke-linecap/linejoin=round
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=STROKE)


def render(size: int, *, rounded: bool, glyph_scale: float) -> Image.Image:
    """Render one icon. ``rounded`` keeps the SVG's rounded corners (transparent outside);
    otherwise the background is full-bleed, as maskable and Apple touch icons require."""
    canvas = size * SUPERSAMPLE
    unit = canvas / 64
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if rounded:
        draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), CORNER_RADIUS * unit, fill=BACKGROUND)
    else:
        draw.rectangle((0, 0, canvas, canvas), fill=BACKGROUND)
    _stroke(draw, LINE, unit, glyph_scale)
    _stroke(draw, ARROW, unit, glyph_scale)
    return image.resize((size, size), Image.LANCZOS)


ICONS = {
    # name: (size, rounded, glyph_scale)
    "icon-192.png": (192, True, 1.0),
    "icon-512.png": (512, True, 1.0),
    # Maskable: full-bleed, glyph shrunk to stay inside the 80% safe zone.
    "icon-maskable-512.png": (512, False, 0.8),
    # iOS fills transparency with black, so the touch icon is opaque and full-bleed.
    "apple-touch-icon.png": (180, False, 0.9),
}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, (size, rounded, scale) in ICONS.items():
        target = OUT_DIR / name
        render(size, rounded=rounded, glyph_scale=scale).save(target, optimize=True)
        print(f"wrote {target.relative_to(ROOT)} ({size}x{size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

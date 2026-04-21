"""One-shot rasterizer for the map-layer school icon.

Renders the Tabler Icons outline ``school`` glyph
(https://tabler.io/icons/icon/school — MIT) to a 64x64 transparent PNG
suitable for MapLibre ``addImage(..., {pixelRatio: 2})``.

Output
------
``consorcio-web/public/capas/escuelas/escuela-icon.png``

Run
---
From the repo root::

    python -m scripts.etl_escuelas.export_icon

The output PNG is committed to the repo; this script is intended to run
ONCE per icon revision, not at build time or runtime.

Implementation strategy
-----------------------
The Tabler ``school`` outline glyph is only two ``<path>`` elements over a
24x24 viewBox:

- Roof:  ``M22 9 l-10 -4 l-10 4 l10 4 l10 -4 v6``
- Bell:  ``M6 10.6 v5.4 a6 3 0 0 0 12 0 v-5.4``

That is simple enough to hand-translate to Pillow ``ImageDraw`` primitives
(``line`` for the polyline, ``arc`` for the elliptical half-arc). No SVG
parser, no external rasterizer — just the Pillow already bundled with the
project venv.

If a more faithful rasterization is ever needed (e.g. the upstream glyph
becomes more complex), the documented fallback is ``cairosvg`` — see
``scripts/etl_escuelas/README.md``. The project venv does NOT ship
``cairosvg`` by default; install with ``pip install cairosvg`` when
needed.

License
-------
Icon © Tabler Icons contributors, MIT License. The rasterized PNG inherits
the MIT license. See https://github.com/tabler/tabler-icons/blob/main/LICENSE.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw

# --- Output location --------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
OUTPUT_PATH: Final[Path] = (
    REPO_ROOT / "consorcio-web" / "public" / "capas" / "escuelas" / "escuela-icon.png"
)

# --- Rasterization parameters ----------------------------------------------

ICON_SIZE: Final[int] = 64
"""Output PNG side length in pixels. MapLibre renders it at pixelRatio 2."""

STROKE_COLOR: Final[tuple[int, int, int, int]] = (0x19, 0x76, 0xD2, 0xFF)
"""``#1976d2`` — matches the KMZ ``ff0055ff`` operator blue (BGR → RGB)."""

# Tabler ``school`` glyph native viewBox is 24x24.
VIEWBOX: Final[int] = 24

# Stroke width in viewBox units is 2. Scaled to 64 px that yields ~5.3 px,
# which looks chunky at z10 / icon-size 0.4. A width of 4 px reads as a clean
# outline at both 0.4 (~26 px rendered) and 0.8 (~51 px rendered) zoom stops.
STROKE_WIDTH: Final[int] = 4

# --- SVG-to-Pillow coordinate mapping --------------------------------------


def _px(value: float) -> float:
    """Map a viewBox unit to a pixel coordinate on the ``ICON_SIZE`` canvas."""
    return value * ICON_SIZE / VIEWBOX


def _render_roof(draw: ImageDraw.ImageDraw) -> None:
    """Render the Tabler ``school`` roof polyline.

    SVG path: ``M22 9 l-10 -4 l-10 4 l10 4 l10 -4 v6``.
    Absolute points: (22,9) (12,5) (2,9) (12,13) (22,9); the trailing ``v6``
    is drawn separately as a right-edge vertical.
    """
    roof_points: list[tuple[float, float]] = [
        (_px(22), _px(9)),
        (_px(12), _px(5)),
        (_px(2), _px(9)),
        (_px(12), _px(13)),
        (_px(22), _px(9)),
    ]
    draw.line(
        roof_points,
        fill=STROKE_COLOR,
        width=STROKE_WIDTH,
        joint="curve",
    )
    # Right-edge vertical from (22,9) down to (22,15) — the ``v6`` leg.
    draw.line(
        [(_px(22), _px(9)), (_px(22), _px(15))],
        fill=STROKE_COLOR,
        width=STROKE_WIDTH,
    )


def _render_bell(draw: ImageDraw.ImageDraw) -> None:
    """Render the bell (lower arc) of the Tabler ``school`` glyph.

    SVG path: ``M6 10.6 v5.4 a6 3 0 0 0 12 0 v-5.4``.
    - Left vertical leg: (6, 10.6) → (6, 16).
    - Elliptical arc (rx=6, ry=3) sweeping from (6, 16) to (18, 16) along
      the lower half of the ellipse centred at (12, 16).
    - Right vertical leg: (18, 16) → (18, 10.6).
    """
    # Left leg
    draw.line(
        [(_px(6), _px(10.6)), (_px(6), _px(16))],
        fill=STROKE_COLOR,
        width=STROKE_WIDTH,
    )
    # Lower half of the ellipse centred at (12, 16), rx=6, ry=3.
    # Pillow ``arc`` draws the bounding box from (cx-rx, cy-ry) to
    # (cx+rx, cy+ry). Angles are measured clockwise from 3 o'clock.
    # The lower half goes from 0° (right endpoint at (18,16)) sweeping
    # through 90° (bottom at (12,19)) to 180° (left endpoint at (6,16)).
    bbox = (
        _px(12 - 6),  # left
        _px(16 - 3),  # top
        _px(12 + 6),  # right
        _px(16 + 3),  # bottom
    )
    draw.arc(bbox, start=0, end=180, fill=STROKE_COLOR, width=STROKE_WIDTH)
    # Right leg
    draw.line(
        [(_px(18), _px(16)), (_px(18), _px(10.6))],
        fill=STROKE_COLOR,
        width=STROKE_WIDTH,
    )


def render_icon() -> Image.Image:
    """Return a ``(ICON_SIZE, ICON_SIZE)`` RGBA image with the school glyph."""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _render_roof(draw)
    _render_bell(draw)
    return img


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img = render_icon()
    img.save(OUTPUT_PATH, format="PNG", optimize=True)
    print(f"wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

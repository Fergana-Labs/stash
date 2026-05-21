"""Canonical slide canvas dimensions, shared across all export targets.

Every exporter (PDF, PPTX, Google Slides) and the renderer's iframe
canvas-enforcing CSS derive from these. If you need to change the slide
size, change it here.

1 inch = 914_400 EMU (English Metric Units) — python-pptx natively
expresses positions in EMUs.
"""

from __future__ import annotations

from pptx.util import Emu

# Pixel dimensions used as the Playwright viewport for both PPTX
# screenshots and PDF rendering, and matched by the iframe canvas CSS
# in the frontend renderer.
SLIDE_WIDTH_PX = 1920
SLIDE_HEIGHT_PX = 1080

# Inches dimensions reported in the PPTX manifest. 13.333" x 7.5" is
# the standard 16:9 widescreen size in PowerPoint / Keynote / Google
# Slides. 1920 px / 144 dpi = 13.333" exactly.
SLIDE_WIDTH_INCHES = 13.333
SLIDE_HEIGHT_INCHES = 7.5

# EMU equivalents (cached so callers don't recompute Emu(int) per slide).
SLIDE_WIDTH_EMU = Emu(12192000)
SLIDE_HEIGHT_EMU = Emu(6858000)

# Device scale factor for raster export screenshots. 2x doubles the
# PNG resolution to 3840x2160 — keeps slides crisp when zoomed in
# PowerPoint or projected on a 4K screen, at ~4x file size.
EXPORT_DEVICE_SCALE_FACTOR = 2

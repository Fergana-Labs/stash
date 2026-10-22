"""Build the off-style contrast set every image eval trains against.

An eval built only from images in a style has nothing telling it what is clearly *not* the
style, so an image unlike anything it saw (a flat peach square) can score 0.94. This script
makes a fixed set of clearly off-style images, embeds them with the same model as examples,
and saves only the embeddings to services/image_eval/contrast.npz; no images ship.

    .venv/bin/python -m backend.scripts.build_image_eval_contrast OUT_DIR

OUT_DIR keeps the PNGs for review. Two kinds of image, all made here, none collected:
- procedural: blank and flat-color pages, single shapes and blobs on white, gradients,
  noise, stripes, plain text pages, wireframes and charts;
- drawings: Claude draws plain subjects as SVG in many distinct, common styles.
Embedding runs on Modal (embedder.embed); nothing heavy runs locally.
"""

import asyncio
import random
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from backend.services.image_eval import build, embedder

SIDE = 1024
OUT = Path(__file__).resolve().parent.parent / "services" / "image_eval" / "contrast.npz"
FONT = build.FONT

STYLES = [
    "flat corporate vector illustration with geometric people and a blue/purple palette",
    "8-bit pixel art on a visible pixel grid",
    "isometric 3D-looking technical illustration with clean gradients",
    "art deco travel poster with bold geometric shapes and gold accents",
    "white-on-blue engineering blueprint with ruled construction lines",
    "a young child's crayon drawing with scribbled fills",
    "pop-art comic panel with halftone dots and thick black outlines",
    "minimal single-weight line icon, no fill",
    "Bauhaus composition of primary-colored circles, squares and triangles",
    "black-and-white woodcut print with heavy carved hatching",
    "soft watercolor landscape wash with blurred edges",
    "neon synthwave scene with a magenta and cyan glow on black",
    "flat Japanese ukiyo-e woodblock style with wave patterns",
    "chalk drawing on a dark green chalkboard",
    "glossy app-store icon with a rounded square and drop shadow",
    "sticker style with a thick white outline and saturated flat colors",
]
SUBJECTS = [
    "a cat",
    "a person working at a laptop",
    "a house with a tree",
    "a robot",
    "a city street",
]
DRAW_SYSTEM = """You are an illustrator. Draw the subject in exactly the named style. Output ONE \
self-contained SVG, viewBox 0 0 1024 1024, with a background rect. Use only SVG shapes, paths \
and text: no <image>, <script>, <foreignObject>, external references or CSS imports.

Reply with the SVG only, in a single ```svg block."""


def png(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def procedural(rng: random.Random) -> list[tuple[str, bytes]]:
    palette = [
        "#e8a87c",
        "#f6dcc4",
        "#1f1b16",
        "#3b6fd8",
        "#d94a4a",
        "#5aa469",
        "#f2c94c",
        "#9b51e0",
        "#ffffff",
        "#888888",
    ]
    made: list[tuple[str, bytes]] = []
    for c in palette:
        made.append((f"solid {c}", png(Image.new("RGB", (SIDE, SIDE), c))))
    for i in range(14):  # one shape or blob on white: the "plain peach square" case and its cousins
        im = Image.new("RGB", (SIDE, SIDE), "white")
        d = ImageDraw.Draw(im)
        c = palette[i % 6]
        x0, y0 = rng.randint(80, 400), rng.randint(80, 400)
        x1, y1 = x0 + rng.randint(250, 550), y0 + rng.randint(250, 550)
        [d.rectangle, d.ellipse, d.rounded_rectangle][i % 3]((x0, y0, x1, y1), fill=c)
        if i % 4 == 3:
            im = im.filter(ImageFilter.GaussianBlur(30))
        made.append((f"shape {i}", png(im)))
    for i in range(4):
        a, b = (
            np.array(Image.new("RGB", (1, 1), palette[i]).getpixel((0, 0))),
            np.array(Image.new("RGB", (1, 1), palette[i + 3]).getpixel((0, 0))),
        )
        t = np.linspace(0, 1, SIDE)[:, None, None]
        made.append(
            (
                f"gradient {i}",
                png(Image.fromarray((a * (1 - t) + b * t).repeat(SIDE, 1).astype("uint8"))),
            )
        )
    for i in range(3):
        noise = np.random.default_rng(i).integers(0, 255, (SIDE // 8, SIDE // 8, 3), dtype=np.uint8)
        made.append((f"noise {i}", png(Image.fromarray(noise).resize((SIDE, SIDE)))))
    for i in range(3):
        im = Image.new("RGB", (SIDE, SIDE), "white")
        d = ImageDraw.Draw(im)
        w = 32 * (i + 1)
        for k in range(0, SIDE, 2 * w):
            d.rectangle((k, 0, k + w, SIDE), fill=palette[i + 2])
        made.append((f"stripes {i}", png(im)))
    for i in range(6):  # pages of plain text
        im = Image.new("RGB", (SIDE, SIDE), "white")
        d = ImageDraw.Draw(im)
        big = ImageFont.truetype(str(FONT), 64) if i % 2 else ImageFont.load_default(size=56)
        small = ImageFont.load_default(size=28)
        d.text(
            (80, 90),
            [
                "Quarterly results",
                "Release notes",
                "Welcome back",
                "Terms of service",
                "Meeting agenda",
                "Read me",
            ][i],
            fill="#111",
            font=big,
        )
        for line in range(18):
            d.text(
                (80, 220 + line * 40),
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit sed do.",
                fill="#444",
                font=small,
            )
        made.append((f"text page {i}", png(im)))
    for i in range(4):  # wireframes and charts
        im = Image.new("RGB", (SIDE, SIDE), "#f7f7f9")
        d = ImageDraw.Draw(im)
        if i < 2:
            d.rectangle((0, 0, SIDE, 90), fill="#2d3a4a")
            for r in range(5):
                d.rounded_rectangle(
                    (60, 140 + r * 160, SIDE - 60, 260 + r * 160),
                    radius=12,
                    outline="#c5cad3",
                    width=3,
                    fill="white",
                )
        else:
            for k in range(8):
                h = rng.randint(120, 700)
                d.rectangle((90 + k * 110, 900 - h, 160 + k * 110, 900), fill=palette[3 + k % 3])
            d.line((80, 900, 980, 900), fill="#222", width=4)
        made.append((f"ui {i}", png(im)))
    return made


async def drawings() -> list[tuple[str, bytes]]:
    gate = asyncio.Semaphore(8)

    async def one(style: str, subject: str):
        async with gate:
            for _ in range(2):
                try:
                    text = await build._ask(
                        DRAW_SYSTEM,
                        [{"type": "text", "text": f"Style: {style}\nSubject: {subject}"}],
                        16000,
                    )
                    svg = build.re.search(
                        r"```svg\s*(.*?)```", text, build.re.S
                    ) or build.re.search(r"(<svg\b.*</svg>)", text, build.re.S)
                    if svg:
                        image = await asyncio.to_thread(
                            build.rasterize, build.sanitize_svg(svg.group(1))
                        )
                        if not build._blank(image):
                            return f"{subject} | {style}", image
                except Exception as exc:  # one lost drawing, not a failed set
                    print("drawing failed:", subject, "|", style, exc, file=sys.stderr)
        return None

    made = await asyncio.gather(*(one(s, subj) for s in STYLES for subj in SUBJECTS))
    return [m for m in made if m]


async def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    items = procedural(random.Random(7)) + await drawings()
    for i, (name, data) in enumerate(items):
        (out_dir / f"{i:03d}.png").write_bytes(data)
    vectors: list[list[float]] = []
    for i in range(0, len(items), 32):
        vectors += await embedder.embed([data for _, data in items[i : i + 32]])
    np.savez_compressed(
        OUT,
        embeddings=np.asarray(vectors, dtype=np.float16),
        names=np.asarray([name for name, _ in items]),
        embed_model=np.asarray(embedder.EMBED_MODEL),
    )
    print(f"{len(items)} off-style images -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))

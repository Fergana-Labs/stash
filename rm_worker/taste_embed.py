"""Frozen image embeddings for taste classifiers (SigLIP2 SO400M).

A tall image (a full-page screenshot) is cut into up to MAX_TILES square tiles from
the top; each tile is embedded and L2-normalized, and the image's embedding is their
mean. The backend never imports torch: it always calls the deployed Modal
function below and never imports this module in-process.

Deploy (once per change):  modal deploy rm_worker/taste_embed.py
"""

from io import BytesIO
from pathlib import Path

import modal

MODEL = "ViT-SO400M-16-SigLIP2-384"
PRETRAINED = "webli"
EMBED_MODEL = "siglip2-so400m-16-384/tiles4"
MAX_TILES = 4
APP_NAME = "stash-taste-embed"

_model = None


def _load():
    global _model
    if _model is None:
        import open_clip
        import torch

        device = (
            "cuda"
            if torch.cuda.is_available()
            else ("mps" if torch.backends.mps.is_available() else "cpu")
        )
        model, _, preprocess = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED)
        _model = (model.eval().to(device), preprocess, device)
    return _model


def _tiles(image):
    w, h = image.size
    if h <= 1.5 * w:
        return [image]
    n = min(MAX_TILES, round(h / w))
    return [image.crop((0, i * w, w, min(h, (i + 1) * w))) for i in range(n)]


def embed_images(images: list[bytes]) -> list[list[float]]:
    import torch
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = 60_000_000
    model, preprocess, device = _load()
    out = []
    with torch.no_grad():
        for data in images:
            with Image.open(BytesIO(data)) as im:
                tiles = _tiles(im.convert("RGB"))
            batch = torch.stack([preprocess(t) for t in tiles]).to(device)
            v = torch.nn.functional.normalize(model.encode_image(batch).float(), dim=-1).mean(0)
            out.append(v.cpu().tolist())
    return out


image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(Path(__file__).parent / "taste_requirements.txt"))
    # Bake the weights into the image so a cold start does not download them.
    .run_function(_load)
)
app = modal.App(APP_NAME, image=image)


@app.function(gpu="T4", timeout=300, scaledown_window=600)
def embed(images: list[bytes]) -> list[list[float]]:
    return embed_images(images)

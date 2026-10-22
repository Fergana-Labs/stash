"""Image embeddings for taste classifiers, without importing torch in the API.

Always calls the deployed Modal function in rm_worker/taste_embed.py. There is
deliberately no in-process mode: loading SigLIP2 locally took a dev laptop to
20 GB and froze it (2026-10-22). Tests replace `embed` with a fake.
"""

EMBED_MODEL = "siglip2-so400m-16-384/tiles4"
MODAL_APP = "stash-taste-embed"


class EmbedderUnavailable(RuntimeError):
    pass


async def embed(images: list[bytes]) -> list[list[float]]:
    try:
        import modal

        fn = modal.Function.from_name(MODAL_APP, "embed")
        return await fn.remote.aio(images)
    except (
        Exception
    ) as exc:  # modal raises its own error types for auth, lookup and remote failures
        raise EmbedderUnavailable(f"Image embedding service unavailable: {exc}") from exc

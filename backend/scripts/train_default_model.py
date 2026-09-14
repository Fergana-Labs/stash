"""Train the shared default model of a kind and ship its profile.

    python -m backend.scripts.train_default_model stylewriter ./corpus-dir

Reads every .md/.txt file in the directory as the corpus, runs the same
readiness check and GPU call a user's training run does, waits for the
adapter, and writes the kind's `default_profile.json` — the file whose
presence is what makes the shared model exist. Commit that file.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from ..trained_models import gpu, registry
from ..trained_models.kinds.stylewriter.corpus import Document


async def main(kind_name: str, corpus_dir: str) -> None:
    kind = registry.get(kind_name)
    files = sorted(p for p in Path(corpus_dir).iterdir() if p.suffix in (".md", ".txt"))
    documents = [Document(p.name, p.read_text(encoding="utf-8")) for p in files]
    report = kind.check_corpus(documents)
    print(json.dumps(report.to_dict(), indent=2))
    if not report.ready:
        raise SystemExit("corpus is not ready; see reasons above")

    job = await kind.start_training("model_default", report)
    print(f"training job {job} started; polling")
    started = time.monotonic()
    while True:
        try:
            result = await kind.training_result(job)
        except gpu.GpuJobFailed as error:
            raise SystemExit(f"training failed: {error}") from error
        if result is not None:
            break
        print(f"  still training ({int(time.monotonic() - started)}s)")
        await asyncio.sleep(30)

    print(f"trained in {result['seconds']}s: {result['pairs']} pairs -> {result['adapter_path']}")
    if result["adapter_path"] != kind.DEFAULT_ADAPTER:
        raise SystemExit(f"adapter landed at {result['adapter_path']}, not {kind.DEFAULT_ADAPTER}")
    shipped = {
        "profile": result["profile"],
        "corpus": {
            "usable_words": report.usable_words,
            "chunks": len(report.chunks),
            "sources": sorted({c.source for c in report.chunks}),
        },
    }
    kind.DEFAULT_PROFILE_PATH.write_text(json.dumps(shipped, indent=1) + "\n")
    print(f"wrote {kind.DEFAULT_PROFILE_PATH}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))

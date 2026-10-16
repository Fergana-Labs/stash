"""Bounded document parser child for the eval builder; no DB or network access."""

import contextlib
import io
import json
import os
import resource
import sys
import zipfile


def main():
    # Optional extraction dependencies import NumPy; keep their thread buffers bounded.
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    try:
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    except (ValueError, OSError):
        pass
    from ..services.file_extraction import extract_text

    data = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        return 1
    if data.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 8 * 1024 * 1024:
                return 1
    with contextlib.redirect_stdout(io.StringIO()):
        text = extract_text(data, sys.argv[1])
    if text and len(text) <= 50000:
        print(json.dumps(text))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

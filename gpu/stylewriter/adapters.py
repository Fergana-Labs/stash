"""Naming adapters for the serving engine."""

from __future__ import annotations

import zlib

# vLLM keys a LoRA by a positive int32; a raw CRC can exceed that.
_INT32_MAX = 0x7FFFFFFF


def lora_id(adapter_path: str) -> int:
    """A stable positive int32 for an adapter path, never zero (zero means
    "no adapter" to the engine)."""
    return (zlib.crc32(adapter_path.encode()) & _INT32_MAX) or 1

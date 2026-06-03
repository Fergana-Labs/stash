"""Provider + exporter registries.

The OAuth router resolves a provider by URL segment (`get_provider`). Export
endpoints resolve a Celery task name by export format. Connected sources are
indexed (not imported) — their indexers live in backend/tasks/sources, keyed by
source_type, so there is no importer registry.

Registration happens at module-import time: each integration's __init__.py calls
`register_provider(...)` and any `register_exporter(...)`. The package
__init__.py imports every provider, so registration runs at backend boot.
"""

from __future__ import annotations

from fastapi import HTTPException

from .base import Integration

_providers: dict[str, Integration] = {}
_exporters: dict[str, str] = {}


def register_provider(integration: Integration) -> None:
    if integration.name in _providers:
        raise RuntimeError(f"provider already registered: {integration.name}")
    _providers[integration.name] = integration


def get_provider(name: str) -> Integration:
    p = _providers.get(name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"unknown provider: {name}")
    return p


def list_providers() -> list[Integration]:
    return list(_providers.values())


def register_exporter(fmt: str, celery_task_name: str) -> None:
    if fmt in _exporters:
        raise RuntimeError(f"exporter already registered: {fmt}")
    _exporters[fmt] = celery_task_name


def resolve_exporter(fmt: str) -> str:
    task_name = _exporters.get(fmt)
    if task_name is None:
        raise HTTPException(status_code=400, detail=f"unknown export format: {fmt}")
    return task_name

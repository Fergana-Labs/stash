"""Provider + importer/exporter registries.

The OAuth router resolves a provider by URL segment (`get_provider`).
Import/export endpoints resolve a Celery task name by (provider,
resource_type) or by export format.

Registration happens at module-import time: each integration's
__init__.py calls `register_provider(...)` and one or more
`register_importer(...)` / `register_exporter(...)`. The package
__init__.py imports every provider, so registration runs at backend
boot.
"""

from __future__ import annotations

from fastapi import HTTPException

from .base import Integration

_providers: dict[str, Integration] = {}
_importers: dict[tuple[str, str], str] = {}
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


def register_importer(provider: str, resource_type: str, celery_task_name: str) -> None:
    key = (provider, resource_type)
    if key in _importers:
        raise RuntimeError(f"importer already registered: {key}")
    _importers[key] = celery_task_name


def resolve_importer(provider: str, resource_type: str) -> str:
    task_name = _importers.get((provider, resource_type))
    if task_name is None:
        raise HTTPException(
            status_code=400,
            detail=f"no importer for ({provider!r}, {resource_type!r})",
        )
    return task_name


def register_exporter(fmt: str, celery_task_name: str) -> None:
    if fmt in _exporters:
        raise RuntimeError(f"exporter already registered: {fmt}")
    _exporters[fmt] = celery_task_name


def resolve_exporter(fmt: str) -> str:
    task_name = _exporters.get(fmt)
    if task_name is None:
        raise HTTPException(status_code=400, detail=f"unknown export format: {fmt}")
    return task_name

"""Notion integration.

Demonstrates the "drop a directory, register it" claim of the
integration framework. Nothing in router.py, storage.py, or
registry.py changes to support Notion — the only addition outside
this directory is the `import` line in backend/integrations/__init__.py.
"""

from ..registry import register_importer, register_provider
from .provider import NotionIntegration

register_provider(NotionIntegration())

register_importer(
    provider="notion",
    resource_type="page",
    celery_task_name="backend.integrations.notion.importers.page.import_notion_page",
)

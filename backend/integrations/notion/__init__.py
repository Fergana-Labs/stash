"""Notion integration.

Demonstrates the "drop a directory, register it" claim of the
integration framework. Nothing in router.py, storage.py, or
registry.py changes to support Notion — the only addition outside
this directory is the `import` line in backend/integrations/__init__.py.

One importer task auto-detects whether the user-supplied id points at
a page or a database. Pages are imported recursively (child pages
become real Stash pages inside a folder named after the parent);
databases become Stash tables.
"""

from ..registry import register_importer, register_provider
from .provider import NotionIntegration

register_provider(NotionIntegration())

# Single resource type — the task fans out by probing pages vs databases.
register_importer(
    provider="notion",
    resource_type="resource",
    celery_task_name="backend.integrations.notion.importers.resource.import_notion_resource",
)

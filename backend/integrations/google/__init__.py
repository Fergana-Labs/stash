"""Google integration: OAuth + Drive imports + Google Slides export."""

from ..registry import register_importer, register_provider
from .provider import GoogleIntegration

register_provider(GoogleIntegration())

# One importer for all Drive MIME types; the task itself reads the MIME
# from the Drive API and dispatches internally. Keeps the API layer
# from having to do a Drive call before dispatching.
register_importer(
    provider="google",
    resource_type="drive_file",
    celery_task_name="backend.integrations.google.importers.drive_file.import_drive_file",
)

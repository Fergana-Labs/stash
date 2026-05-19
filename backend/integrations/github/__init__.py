"""GitHub integration: OAuth + repo zipball import."""

from ..registry import register_importer, register_provider
from .provider import GitHubIntegration

register_provider(GitHubIntegration())

# Resource types this provider knows how to import. The git-import endpoint
# always asks for ('github', 'repo') regardless of the URL's host — the
# repo task itself dispatches by host inside resolve_archive_url.
register_importer(
    provider="github",
    resource_type="repo",
    celery_task_name="backend.integrations.github.importers.repo.import_repo",
)

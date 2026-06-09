"""Integration framework.

Each third-party integration lives in its own submodule under this
package. Importing the submodule registers the provider + any importer
or exporter Celery tasks with the registry.

Adding a new integration:
  1. Create backend/integrations/<name>/{__init__,provider,client}.py
     plus importers/ or exporters/ as needed.
  2. Add an `import backend.integrations.<name>` line below.
  3. Set the provider's OAuth env vars in config.py.

No changes to base.py, registry.py, storage.py, or router.py are needed
for a new provider — only the explicit list of providers grows.
"""

from . import (
    asana,  # noqa: F401
    github,  # noqa: F401 — import for side-effect (provider self-registration)
    gmail,  # noqa: F401
    gong,  # noqa: F401
    google,  # noqa: F401
    granola,  # noqa: F401
    jira,  # noqa: F401
    notion,  # noqa: F401
    slack,  # noqa: F401
    snowflake,  # noqa: F401
)

"""The web service's one logging configuration site.

Uvicorn configures only its own `uvicorn.*` loggers, so without this the application's
records have nowhere to go: INFO and DEBUG are dropped outright, and an ERROR escapes
only through stdlib's `lastResort` handler — message plus traceback, with no timestamp,
level or logger name to attribute it to. That is how the STAS-131 founder-preview
incident — a harness spawn dying with `FileNotFoundError: [Errno 2] No such file or
directory`, which does not even name the binary that was missing — sat unattributable in
the preview container for about a day.

Call it from the lifespan *after* `init_db()`, which runs Alembic in-process: Alembic's
`env.py` reconfigures logging from `alembic.ini` every time it runs, so setting up
before it would leave the outcome dependent on whether migrations happened to apply.
`env.py` also passes `disable_existing_loggers=False` — with the default, it would
disable every application logger here, and a disabled logger never reaches its
handlers at all.
"""

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_app_logging() -> None:
    """Send the root logger to stderr, replacing any handler an earlier boot stage left."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)

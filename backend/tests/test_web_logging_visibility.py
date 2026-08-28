"""Web-service log visibility (STAS-132).

The STAS-131 founder-preview incident: a turn died with `FileNotFoundError: 'claude'`
and the crash trace the code logs was nowhere in the container logs, so a
founder-facing bug stayed unattributed for ~24h.

The cause is a fight over the logging module during web boot, in this order:

1. `uvicorn`'s `Config.load()` applies its own dictConfig, which configures only the
   `uvicorn.*` loggers and leaves the root logger with no handler.
2. The app lifespan calls `init_db()`, which runs `alembic upgrade head` IN-PROCESS.
   Alembic always execs `env.py`, whose module-level `fileConfig(alembic.ini)` then
   disables every logger `alembic.ini` does not name — which is every application
   logger and `uvicorn.access` too. A disabled logger emits nothing at all: not even
   stdlib's bare `lastResort` line.
3. `setup_app_logging()` installs the one root handler the app loggers need.

Step 3 alone cannot recover step 2: `Logger.handle()` returns as soon as it sees
`.disabled`, so a root handler is never consulted. These tests pin all three facts —
the hazard (`test_alembic_fileconfig_*`), the fix's end state (`test_setup_*`), and
the source that must stop causing it (`test_migration_env_py_*`).
"""

import logging
import logging.config
import re
import sys
from pathlib import Path

import pytest
from uvicorn.config import LOGGING_CONFIG

from backend.logging_setup import setup_app_logging

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

# The turn pump whose logger.exception was invisible during the incident, and the
# startup INFO that is the deterministic proof INFO+ records now reach the logs.
TURN_PUMP = "backend.services.sprite_agent_service"
DEMO_STARTUP = "backend.services.demo_service"
APP_LOGGERS = ("stash", TURN_PUMP, DEMO_STARTUP)

MIGRATION_ENV_FILES = (
    REPO_ROOT / "backend" / "migrations" / "env.py",
    REPO_ROOT / "backend" / "managed" / "migrations" / "env.py",
)


def _snapshot_logging() -> tuple:
    """Everything a test below may mutate, so the rest of the suite is untouched."""
    manager = logging.Logger.manager
    per_logger = {
        name: (lg.disabled, lg.level, lg.propagate, list(lg.handlers))
        for name, lg in manager.loggerDict.items()
        if not isinstance(lg, logging.PlaceHolder)
    }
    return logging.root.level, list(logging.root.handlers), per_logger


def _restore_logging(snapshot: tuple) -> None:
    root_level, root_handlers, per_logger = snapshot
    logging.root.setLevel(root_level)
    logging.root.handlers[:] = root_handlers
    for name, (disabled, level, propagate, handlers) in per_logger.items():
        lg = logging.getLogger(name)
        lg.disabled, lg.level, lg.propagate = disabled, level, propagate
        lg.handlers[:] = handlers
    for name, lg in logging.Logger.manager.loggerDict.items():
        if name not in per_logger and not isinstance(lg, logging.PlaceHolder):
            lg.disabled = False


@pytest.fixture(autouse=True)
def _isolated_logging():
    snapshot = _snapshot_logging()
    yield
    _restore_logging(snapshot)


def _boot_web_process(*, disable_existing_loggers: bool) -> None:
    """Replay the order a web worker mutates logging in: uvicorn's dictConfig, then
    the app's module-level `getLogger` calls, then `init_db()`'s alembic side effect.

    `disable_existing_loggers` mirrors what the migration `env.py` passes today, so a
    test can assert the boot either does or does not silence the app loggers.
    """
    logging.config.dictConfig(LOGGING_CONFIG)
    for name in APP_LOGGERS:
        logging.getLogger(name)
    logging.config.fileConfig(str(ALEMBIC_INI), disable_existing_loggers=disable_existing_loggers)


def _emit_incident_records() -> None:
    """The two records the incident proved were missing: the turn pump's crash trace
    and a routine startup INFO."""
    turn_pump = logging.getLogger(TURN_PUMP)
    try:
        raise FileNotFoundError(2, "No such file or directory")
    except FileNotFoundError:
        turn_pump.exception("cloud agent: turn failed for session %s", "agent-probe")
    logging.getLogger(DEMO_STARTUP).info("created demo system user %s", "6f1b-0000")


# --- the mechanism, unchanged by the fix (green before and after) ------------------


def test_alembic_fileconfig_default_silences_every_app_logger(capfd):
    """`alembic.ini` names only root/sqlalchemy/alembic, so `fileConfig`'s default
    `disable_existing_loggers=True` silences every logger this card cares about —
    completely, which is why the incident trace was invisible rather than merely
    unformatted. Guards the `env.py` flag from silently reverting to the default."""
    logging.config.dictConfig(LOGGING_CONFIG)
    for name in APP_LOGGERS:
        logging.getLogger(name)
    logging.config.fileConfig(str(ALEMBIC_INI))

    for name in (*APP_LOGGERS, "uvicorn.access"):
        assert logging.getLogger(name).disabled is True, name

    _emit_incident_records()
    assert capfd.readouterr().err == ""


def test_uvicorn_config_alone_leaves_records_bare_and_drops_info(capfd):
    """Without the app's own setup, uvicorn's dictConfig configures only `uvicorn.*` and
    installs no root handler, so an ERROR escapes via stdlib's `lastResort` — bare, no
    timestamp or logger name — while INFO is dropped outright."""
    handlers_before = list(logging.root.handlers)
    logging.config.dictConfig(LOGGING_CONFIG)

    assert "root" not in LOGGING_CONFIG
    assert list(logging.root.handlers) == handlers_before

    # A uvicorn worker starts with no such handlers of its own on root; pytest has added
    # its own here, and `lastResort` only speaks when there are none.
    logging.root.handlers = []
    _emit_incident_records()
    captured = capfd.readouterr().err

    assert captured.startswith("cloud agent: turn failed for session agent-probe")
    assert "ERROR" not in captured.splitlines()[0]
    assert "Traceback (most recent call last):" in captured
    assert "created demo system user" not in captured


# --- the invariant: app records reach process stderr, attributed ------------------


def test_boot_then_setup_emits_attributed_error_and_info(capfd):
    """After a web boot that leaves loggers usable, `setup_app_logging()` puts a
    timestamped, levelled, logger-named ERROR + traceback and an INFO on stderr — the
    shape the incident needed to attribute the crash in minutes."""
    _boot_web_process(disable_existing_loggers=False)
    setup_app_logging()

    _emit_incident_records()
    captured = capfd.readouterr().err

    assert re.search(
        rf"^\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}},\d{{3}} ERROR \[{re.escape(TURN_PUMP)}\]"
        r" cloud agent: turn failed for session agent-",
        captured,
        re.MULTILINE,
    ), captured
    assert "Traceback (most recent call last):" in captured
    assert "FileNotFoundError: [Errno 2] No such file or directory" in captured
    assert re.search(
        rf"^\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}},\d{{3}} INFO \[{re.escape(DEMO_STARTUP)}\]"
        r" created demo system user",
        captured,
        re.MULTILINE,
    ), captured


def test_setup_app_logging_installs_one_root_handler_and_is_idempotent():
    """One handler on stderr at INFO, and calling setup twice still leaves exactly
    one — so a boot where alembic already attached a handler cannot double-log."""
    setup_app_logging()
    setup_app_logging()

    assert len(logging.root.handlers) == 1
    handler = logging.root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
    assert logging.root.level == logging.INFO


def test_setup_app_logging_leaves_the_uvicorn_access_path_untouched():
    """The card is about app-logger visibility only: uvicorn keeps its own handler and
    keeps not propagating, so access lines stay in uvicorn's own format."""
    _boot_web_process(disable_existing_loggers=False)
    setup_app_logging()

    access = logging.getLogger("uvicorn.access")
    assert access.propagate is False
    assert access.disabled is False
    assert len(access.handlers) == 1


# --- the source of the hijack must stay fixed -------------------------------------


@pytest.mark.parametrize("env_file", MIGRATION_ENV_FILES, ids=lambda p: p.parent.parent.name)
def test_migration_env_py_does_not_disable_existing_loggers(env_file: Path):
    """`init_db()` runs `alembic upgrade head` in-process on every web boot, and alembic
    execs `env.py` unconditionally — so a default `fileConfig()` here silences the whole
    application's logging for the rest of the process's life. A test that boots the real
    app cannot catch the regression, because it is invisible to unit tests."""
    calls = [
        line.strip()
        for line in env_file.read_text().splitlines()
        if "fileConfig(" in line and not line.strip().startswith("#")
    ]

    assert calls, f"{env_file} no longer configures logging — update this test knowingly"
    for call in calls:
        assert "disable_existing_loggers=False" in call, f"{env_file}: {call}"

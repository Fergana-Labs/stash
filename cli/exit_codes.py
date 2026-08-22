"""Canonical exit-code contract for the stash CLI.

The stash CLI is consumed by both humans and AI agents, so every invocation
must exit with a code an agent can classify deterministically:

* ``EXIT_SUCCESS`` (0) — the command did what the user asked.
* ``EXIT_USER_ERROR`` (1) — the request was wrong: bad args, an invalid
  enum choice, a missing required file/session/config, a validation
  failure, or a 4xx backend rejection. The user (or the agent) can fix the
  input and retry exactly as-is.
* ``EXIT_INTERNAL_ERROR`` (2) — something went wrong that is not the
  caller's fault: a 5xx backend failure, a corrupt/local parse failure, a
  backend-delivery failure (e.g. a wrapped ``httpx.TransportError``), or any
  unexpected runtime error.
* ``EXIT_AGENT_SIGNAL`` (20) — reserved for agent-facing signals (the
  ``20+`` band). No command uses it yet; it is reserved so future agent
  signalling (e.g. "retry later", "credentials needed") has a stable home
  that never collides with the 0/1/2 user/internal contract.

This contract supersedes the literal wording of AXI §6 ("1=error,
2=usage error"); it is the approved convention for this codebase. It is
enforced centrally via :func:`classify_status_code` (HTTP status -> exit
code) and :func:`classify_error`, and via the per-command exit helpers in
``cli.main`` that give every inline failure path an explicit typed code (so
no failure path rides Typer/Click's default exit-1).

A raw ``httpx.TransportError`` (connection refused, DNS failure, connect/read
timeout, network down) is a backend-delivery failure, never the caller's
fault. ``cli.client`` wraps it into a :class:`~cli.client.StashError` carrying
the synthetic ``TRANSPORT_ERROR_STATUS`` (0), which sits outside 4xx so it
classifies to ``EXIT_INTERNAL_ERROR``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli.client import StashError

EXIT_SUCCESS = 0
"""Success — the command completed what the caller asked."""

EXIT_USER_ERROR = 1
"""User error — bad arguments / input / 4xx backend rejection."""

EXIT_INTERNAL_ERROR = 2
"""Internal error — 5xx backend failure or unexpected runtime fault."""

EXIT_AGENT_SIGNAL = 20
"""Agent-facing signal — reserved (unused in this task) for the 20+ band."""

# Synthetic StashError status for a backend-delivery failure (a wrapped
# httpx.TransportError): there is no HTTP response, so no real status exists.
# 0 is not a valid HTTP status and thus never collides with a 4xx/5xx
# classification, so it routes to EXIT_INTERNAL_ERROR.
TRANSPORT_ERROR_STATUS = 0


def classify_status_code(status_code: int) -> int:
    """Map an HTTP status code to a stash CLI exit code.

    * 200-399 -> ``EXIT_SUCCESS``
    * 400-499 -> ``EXIT_USER_ERROR``
    * anything else (500-599, a network/timeout surfaced with the synthetic
      ``TRANSPORT_ERROR_STATUS``, or an otherwise-unknown status) ->
      ``EXIT_INTERNAL_ERROR``

    The final branch is a deliberate, documented mapping: a status that is
    neither a successful 2xx/3xx nor a caller-fixable 4xx belongs to the
    "not the caller's fault" band. There is exactly one classification path
    and it is deterministic, so agent consumers always get a stable code.
    """
    if 200 <= status_code <= 399:
        return EXIT_SUCCESS
    if 400 <= status_code <= 499:
        return EXIT_USER_ERROR
    return EXIT_INTERNAL_ERROR


def classify_error(error: StashError) -> int:
    """Classify a :class:`~cli.client.StashError` by its HTTP status.

    Convenience wrapper around :func:`classify_status_code` for the central
    handler in ``cli.main``; keeps the status->code rule in one place.
    """
    return classify_status_code(error.status_code)


# The synthetic-transport name used by ``cli.client`` and the entry boundary.
classify_exit_code = classify_status_code

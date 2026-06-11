import uuid

import pytest

from backend.tasks import viz


@pytest.mark.asyncio
async def test_viz_precompute_failure_logs_only_exception_type(monkeypatch):
    """The viz precompute task walks customer content/embeddings; a failure
    must log only the user id and exception class, never the exception
    message, which can quote document fragments or DB parameter values."""
    user_id = uuid.uuid4()
    captured_logs: list[tuple[str, tuple]] = []

    class FakePool:
        async def fetch(self, query, *args):
            return [{"id": user_id}]

    async def fail_recompute(received_user_id):
        raise RuntimeError("token=secret-token and customer transcript")

    def capture_error(message, *args, **kwargs):
        captured_logs.append((message, args))

    monkeypatch.setattr(viz, "get_pool", lambda: FakePool())
    monkeypatch.setattr(viz, "_recompute_one", fail_recompute)
    monkeypatch.setattr(viz.logger, "error", capture_error)

    done = await viz._precompute()

    assert done == 0
    assert captured_logs == [
        (
            "viz precompute failed user=%s exception_type=%s",
            (user_id, "RuntimeError"),
        )
    ]
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)

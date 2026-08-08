"""The heartbeat queue exists so cadence-sensitive beat tasks cannot sit
behind heavy tasks that legally run 30 minutes each. X token keep-fresh is
the sharpest case: the X provider's 45-min refresh_margin only rotates
tokens pre-expiry if the keep-fresh tick actually runs ~every 30 minutes,
so a starved queue silently reverts X to post-expiry reactive refresh."""

from backend.celery_app import celery
from backend.integrations.x_saves.tasks import keep_tokens_fresh
from backend.tasks.linear_tickets import reconcile, reconcile_github_prs

HEARTBEAT_TASKS = {
    keep_tokens_fresh.name,
    reconcile.name,
    reconcile_github_prs.name,
}


def test_heartbeat_tasks_route_off_the_default_queue():
    # Route keys are matched by name at dispatch time, so importing the real
    # task objects above also pins the names against typos and renames.
    routes = celery.conf.task_routes
    assert set(routes) == HEARTBEAT_TASKS
    for task_name in HEARTBEAT_TASKS:
        assert routes[task_name] == {"queue": "heartbeat"}


def test_bare_worker_consumes_both_queues():
    # A worker started without -Q consumes exactly the queues declared in
    # task_queues. If "heartbeat" is missing here, a worker whose command
    # predates the split strands every routed task the moment routing ships.
    assert {q.name for q in celery.conf.task_queues} == {"default", "heartbeat"}

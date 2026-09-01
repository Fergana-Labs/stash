"""Two queues split by task weight: anything that can hold a worker slot for
minutes routes to "heavy", so the beat sweeps and cheap tasks on "default"
never queue behind it. The X token keep-fresh cadence is the sharpest thing
this protects: its 45-min refresh_margin only rotates tokens pre-expiry if
the keep-fresh tick actually runs ~every 30 minutes, and a starved queue
silently reverts X to post-expiry reactive refresh."""

from backend.celery_app import celery
from backend.exports.pdf import export_pdf
from backend.exports.pptx import export_pptx
from backend.integrations.google.exporters.slides import export_to_google_slides
from backend.tasks.agent_schedules import run_curator_now, run_scheduled_agent
from backend.tasks.clips import process_url_imports
from backend.tasks.drive_extraction import extract_drive_document
from backend.tasks.extraction import extract_file_text
from backend.tasks.sources import sync_source
from backend.tasks.viz import precompute

HEAVY_TASKS = {
    extract_file_text.name,
    extract_drive_document.name,
    process_url_imports.name,
    sync_source.name,
    export_pdf.name,
    export_pptx.name,
    export_to_google_slides.name,
    run_scheduled_agent.name,
    run_curator_now.name,
    precompute.name,
}


def test_heavy_tasks_route_off_the_default_queue():
    # Route keys are matched by name at dispatch time, so importing the real
    # task objects above also pins the names against typos and renames.
    routes = celery.conf.task_routes
    assert set(routes) == HEAVY_TASKS
    for task_name in HEAVY_TASKS:
        assert routes[task_name] == {"queue": "heavy"}


def test_only_expensive_viz_beat_task_is_heavy():
    # Beat dispatchers stay on default so their cadence cannot be starved.
    # Viz is the one exception because the task itself fits UMAP inline.
    beat_tasks = {entry["task"] for entry in celery.conf.beat_schedule.values()}
    assert beat_tasks & HEAVY_TASKS == {precompute.name}


def test_bare_worker_consumes_both_queues():
    # A worker started without -Q consumes exactly the queues declared in
    # task_queues. If "heavy" is missing here, a worker whose command
    # predates the split strands every routed task the moment routing ships.
    assert {q.name for q in celery.conf.task_queues} == {"default", "heavy"}

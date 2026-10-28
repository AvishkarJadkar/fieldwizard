"""In-process job runner.

Analysis is CPU-bound and single-machine, so one worker processes matches
serially. Uploads return immediately and the UI polls /api/matches/{id}.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import traceback

from . import db

_jobs: "queue.Queue[tuple[str, str, str, str, dict]]" = queue.Queue()
_started = False
_start_lock = threading.Lock()


def _summary(result: dict) -> dict:
    teams = result.get("teams", [])
    return {
        "teams": [
            {
                "id": t["id"],
                "name": t["name"],
                "colour": t["colour"],
                "possession": t["possession"],
                "passes": t["passes"],
                "pass_accuracy": t["pass_accuracy"],
            }
            for t in teams
        ],
        "possession": result.get("possession"),
        "players": len(result.get("players", [])),
        "coverage": result.get("coverage"),
        "events": len(result.get("events", [])),
        "report_engine": result.get("report", {}).get("engine"),
        "headline": result.get("report", {}).get("headline"),
        "thumb": (result.get("video") or {}).get("thumb"),
    }


def _execute(match_id: str, source: str, outdir: str, title: str, window: dict) -> None:
    db.update(match_id, status="processing", progress=1, message="Starting")

    # The worker is serial, so per-match settings can safely live in the
    # environment the pipeline reads at start-up.
    os.environ["FW_START_SECONDS"] = f"{float(window.get('start', 0.0)):.2f}"
    os.environ["FW_MAX_SECONDS"] = f"{float(window.get('max', 20.0)):.2f}"
    os.environ["FW_ANALYSIS_FPS"] = str(int(window.get("fps", 15)))

    def progress(pct: int, msg: str) -> None:
        db.update(match_id, progress=max(0, min(99, int(pct))), message=msg)

    try:
        # Imported here so the web server starts in ~1 s instead of loading
        # torch and the detector on every launch. The cost is paid once, on the
        # first job.
        from services.pipeline import run as pipeline

        result = pipeline.run(match_id, source, outdir, title, progress)
        db.update(
            match_id,
            status="done",
            progress=100,
            message="Done",
            duration=(result.get("video") or {}).get("duration"),
            summary=json.dumps(_summary(result)),
            error=None,
        )
    except Exception:
        db.update(
            match_id,
            status="error",
            message="Analysis failed",
            error=traceback.format_exc()[-2000:],
        )


def _worker() -> None:
    while True:
        match_id, source, outdir, title, window = _jobs.get()
        try:
            _execute(match_id, source, outdir, title, window)
        except Exception:
            pass
        finally:
            _jobs.task_done()


def _ensure_worker() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        threading.Thread(target=_worker, name="fw-pipeline", daemon=True).start()
        _started = True


def enqueue(match_id: str, source: str, outdir: str, title: str, window: dict) -> None:
    _ensure_worker()
    _jobs.put((match_id, source, outdir, title, window))


def pending() -> int:
    return _jobs.qsize()

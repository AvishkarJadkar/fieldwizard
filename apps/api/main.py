"""FieldWizard HTTP API + dashboard host."""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from services.pipeline import jersey, llm

from . import db, jobs

ROOT = Path(__file__).resolve().parents[2]
MATCHES = ROOT / "data" / "matches"
UPLOADS = ROOT / "data" / "uploads"
WEB_DIST = ROOT / "apps" / "web" / "dist"
MAX_UPLOAD_MB = int(os.environ.get("FW_MAX_UPLOAD_MB", "4096"))
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

app = FastAPI(title="FieldWizard", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:40] or "match").strip("-")


def _match_dir(match_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", match_id):
        raise HTTPException(400, "bad match id")
    return MATCHES / match_id


def _safe_child(base: Path, name: str) -> Path:
    p = (base / name).resolve()
    if base.resolve() not in p.parents and p != base.resolve():
        raise HTTPException(400, "bad path")
    return p


def _bootstrap() -> None:
    """Register matches analysed on disk, and refresh stale summaries.

    A CLI re-run rewrites result.json without touching SQLite, so the list view
    would otherwise keep showing the old possession/player counts.
    """
    if not MATCHES.exists():
        return
    for folder in sorted(MATCHES.iterdir()):
        if not folder.is_dir():
            continue
        result_path = folder / "result.json"
        if not result_path.exists():
            continue
        row = db.get(folder.name)
        if row and row["status"] != "done":
            continue  # an upload is in flight; leave its progress alone
        if row and row.get("updated_at", 0) >= result_path.stat().st_mtime:
            continue  # summary already reflects this file
        try:
            with open(result_path, encoding="utf-8") as f:
                result = json.load(f)
        except Exception:
            continue
        if not row:
            db.create(folder.name, result.get("title") or folder.name,
                      str(folder), str(folder), status="done")
        db.update(folder.name, status="done", progress=100, message="Done",
                  duration=(result.get("video") or {}).get("duration"),
                  summary=json.dumps(jobs._summary(result)))


@app.on_event("startup")
def _startup() -> None:
    db.init()
    UPLOADS.mkdir(parents=True, exist_ok=True)
    MATCHES.mkdir(parents=True, exist_ok=True)
    _bootstrap()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm": llm.available(), "jersey": jersey.enabled(),
            "queued": jobs.pending()}


@app.get("/api/matches")
def list_matches() -> list[dict]:
    # Pick up matches produced by the CLI since the last refresh.
    _bootstrap()
    return [db.public(r) for r in db.list_all()]


@app.post("/api/matches")
async def create_match(
    file: UploadFile = File(...),
    title: str = Form(""),
    start_seconds: float = Form(0.0),
    max_seconds: float = Form(20.0),
    fps: int = Form(15),
) -> dict:
    name = file.filename or "match.mp4"
    ext = Path(name).suffix.lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(400, f"unsupported video type {ext or '(none)'}")

    clean_title = (title or Path(name).stem).strip()[:80]
    match_id = f"{_slug(clean_title)}-{secrets.token_hex(3)}"
    outdir = MATCHES / match_id
    outdir.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / f"{match_id}{ext}"

    size = 0
    limit = MAX_UPLOAD_MB * 1024 * 1024
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"file exceeds {MAX_UPLOAD_MB} MB")
            out.write(chunk)
    await file.close()
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "empty upload")

    # Per-match analysis window, so the UI can request a clip without env vars.
    window = {
        "start": max(0.0, start_seconds),
        "max": max(1.0, min(max_seconds, 600.0)),
        "fps": max(5, min(fps, 30)),
    }

    db.create(match_id, clean_title, str(dest), str(outdir))
    jobs.enqueue(match_id, str(dest), str(outdir), clean_title, window)
    return db.public(db.get(match_id) or {})


@app.get("/api/matches/{match_id}")
def get_match(match_id: str) -> dict:
    row = db.get(match_id)
    if not row:
        raise HTTPException(404, "match not found")
    path = _match_dir(match_id) / "result.json"
    if row["status"] != "done" or not path.exists():
        return {"meta": db.public(row), "result": None}
    with open(path, encoding="utf-8") as f:
        result = json.load(f)
    return {"meta": db.public(row), "result": result}


@app.get("/api/matches/{match_id}/status")
def get_status(match_id: str) -> dict:
    row = db.get(match_id)
    if not row:
        raise HTTPException(404, "match not found")
    return db.public(row)


@app.get("/api/matches/{match_id}/tracks")
def get_tracks(match_id: str) -> FileResponse:
    path = _match_dir(match_id) / "tracks.json"
    if not path.exists():
        raise HTTPException(404, "no tracking data")
    return FileResponse(path, media_type="application/json")


def _stream_range(path: Path, request: Request) -> Response:
    """Byte-range streaming so the video element can seek."""
    size = path.stat().st_size
    media = "video/mp4" if path.suffix == ".mp4" else "application/octet-stream"
    header = request.headers.get("range") or request.headers.get("Range")
    if not header:
        return FileResponse(path, media_type=media,
                            headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"})

    m = re.match(r"bytes=(\d*)-(\d*)", header)
    if not m:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    start_s, end_s = m.group(1), m.group(2)
    if start_s:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
    else:  # suffix range: last N bytes
        length = int(end_s or 0)
        start = max(0, size - length)
        end = size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    chunk = 512 * 1024

    def reader():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(
        reader(), status_code=206, media_type=media,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Cache-Control": "no-cache",
        },
    )


@app.get("/api/matches/{match_id}/video")
def get_video(match_id: str, request: Request) -> Response:
    base = _match_dir(match_id)
    path = base / "proxy.mp4"
    if not path.exists():
        path = base / "analysis.mp4"
    if not path.exists():
        raise HTTPException(404, "no video")
    return _stream_range(path, request)


@app.get("/api/matches/{match_id}/thumb")
def get_thumb(match_id: str) -> FileResponse:
    path = _match_dir(match_id) / "thumb.jpg"
    if not path.exists():
        raise HTTPException(404, "no thumbnail")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/matches/{match_id}/crops/{name}")
def get_crop(match_id: str, name: str) -> FileResponse:
    base = _match_dir(match_id) / "crops"
    path = _safe_child(base, name)
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "no crop")
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.delete("/api/matches/{match_id}")
def delete_match(match_id: str) -> dict:
    base = _match_dir(match_id)
    db.delete(match_id)
    if base.exists():
        for p in sorted(base.rglob("*"), reverse=True):
            try:
                p.unlink() if p.is_file() else p.rmdir()
            except OSError:
                pass
        try:
            base.rmdir()
        except OSError:
            pass
    return {"deleted": match_id}


# ---- static dashboard -------------------------------------------------------
if WEB_DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> Response:
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "not found"}, status_code=404)
        candidate = WEB_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")

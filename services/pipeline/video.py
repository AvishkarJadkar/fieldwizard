"""Video ingest: probe, analysis copy, web proxy, thumbnails."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

import cv2
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _run(cmd: list[str]) -> None:
    """Run ffmpeg with output redirected to a temp file.

    Piping ffmpeg's output back into Python deadlocks on Windows: a lingering
    child can keep the pipe handle open after ffmpeg exits, so ``communicate()``
    never sees EOF and the pipeline hangs forever. A file has no such problem.
    """
    cmd = [cmd[0], "-hide_banner", "-nostdin", "-loglevel", "error", *cmd[1:]]
    fd, log = tempfile.mkstemp(suffix=".log", prefix="fw-ffmpeg-")
    try:
        with os.fdopen(fd, "wb") as sink:
            p = subprocess.run(cmd, stdout=sink, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL)
        if p.returncode != 0:
            with open(log, "rb") as f:
                tail = f.read()[-1500:].decode("utf-8", "ignore")
            raise RuntimeError(f"ffmpeg failed ({p.returncode}): {tail}")
    finally:
        try:
            os.unlink(log)
        except OSError:
            pass


def probe(path: str) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    duration = frames / fps if fps else 0.0
    return {
        "fps": round(float(fps), 3),
        "frames": frames,
        "width": w,
        "height": h,
        "duration": round(duration, 2),
    }


def make_analysis_copy(src: str, dst: str, fps: int = 10, max_width: int = 1280,
                       max_seconds: float | None = None, start_seconds: float = 0.0,
                       crf: int = 23) -> dict:
    info = probe(src)
    width = min(max_width, info["width"]) if info["width"] else max_width
    vf = f"fps={fps},scale={width}:-2"
    cmd = [FFMPEG, "-y"]
    if start_seconds:
        cmd += ["-ss", f"{start_seconds:.2f}"]
    cmd += ["-i", src]
    if max_seconds:
        cmd += ["-t", f"{max_seconds:.2f}"]
    cmd += [
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-an", dst,
    ]
    _run(cmd)
    return probe(dst)


def make_proxy(src: str, dst: str, width: int = 1280, fps: int = 25,
               max_seconds: float | None = None, start_seconds: float = 0.0) -> None:
    vf = f"fps={fps},scale={width}:-2"
    cmd = [FFMPEG, "-y"]
    if start_seconds:
        cmd += ["-ss", f"{start_seconds:.2f}"]
    cmd += ["-i", src]
    if max_seconds:
        cmd += ["-t", f"{max_seconds:.2f}"]
    cmd += [
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", dst,
    ]
    _run(cmd)


def make_thumb(src: str, dst: str, t: float = 1.0) -> None:
    _run([
        FFMPEG, "-y", "-ss", f"{max(t, 0):.2f}", "-i", src,
        "-frames:v", "1", "-q:v", "3", "-vf", "scale=960:-2", dst,
    ])


def read_frame_at(path: str, t: float):
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, max(t, 0) * 1000)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None

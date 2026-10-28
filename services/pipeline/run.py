"""End-to-end clip pipeline: ingest -> track -> identify -> analytics -> report."""
from __future__ import annotations

import json
import os

import cv2
import numpy as np
from ultralytics import YOLO

from . import analytics, ball as ballmod, calibrate, jersey, report, stabilize, teams, video

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRACKER = os.path.join(ROOT, "config", "botsort_fw.yaml")
_DEFAULT_MODEL = os.path.join(ROOT, "models", "football_v8.pt")
MODEL = os.environ.get("FW_MODEL") or (_DEFAULT_MODEL if os.path.exists(_DEFAULT_MODEL) else "yolo11n.pt")
DEFAULT_ANALYSIS_FPS = int(os.environ.get("FW_ANALYSIS_FPS", "15"))


def run(match_id: str, source: str, outdir: str, title: str, on_progress) -> dict:
    os.makedirs(outdir, exist_ok=True)
    crops_dir = os.path.join(outdir, "crops")
    os.makedirs(crops_dir, exist_ok=True)

    on_progress(2, "Probing source")
    info = video.probe(source)
    max_seconds = float(os.environ.get("FW_MAX_SECONDS", "30"))
    start_seconds = float(os.environ.get("FW_START_SECONDS", "0"))
    analysis_fps = int(os.environ.get("FW_ANALYSIS_FPS", DEFAULT_ANALYSIS_FPS))

    on_progress(5, "Building analysis copy")
    analysis = os.path.join(outdir, "analysis.mp4")
    proxy = os.path.join(outdir, "proxy.mp4")
    meta_path = os.path.join(outdir, "encode.meta.json")
    # Re-encoding is the slowest non-ML step (seeking into this WebM decodes
    # from the start), so reuse the copies when the encode request is unchanged.
    want = {
        "fps": analysis_fps,
        "width": min(1920, info["width"] or 1920),
        "start": round(start_seconds, 2),
        "max": round(max_seconds, 2),
        "src_size": os.path.getsize(source),
        "src_mtime": int(os.path.getmtime(source)),
    }
    ainfo = None
    cached = False
    if os.path.exists(meta_path) and os.path.getsize(analysis) > 0 and os.path.getsize(proxy) > 0:
        try:
            with open(meta_path, encoding="utf-8") as f:
                cached = json.load(f) == want
        except Exception:
            cached = False
    if cached:
        on_progress(8, "Reusing analysis copy")
        ainfo = video.probe(analysis)
    else:
        ainfo = video.make_analysis_copy(source, analysis, fps=analysis_fps, max_width=1920,
                                         max_seconds=max_seconds, start_seconds=start_seconds)
        on_progress(8, "Building web proxy")
        video.make_proxy(source, proxy, width=1280, fps=25, max_seconds=max_seconds,
                         start_seconds=start_seconds)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(want, f)
    thumb = os.path.join(outdir, "thumb.jpg")
    if not (cached and os.path.exists(thumb)):
        try:
            video.make_thumb(source, thumb, start_seconds + 1.0)
        except Exception:
            thumb = None

    on_progress(10, "Loading detector")
    model = YOLO(MODEL)
    names = {int(k): str(v).lower() for k, v in model.names.items()}
    ball_ids = [k for k, v in names.items() if "ball" in v]
    person_ids = [k for k, v in names.items() if v in ("player", "goalkeeper", "referee")]
    if not person_ids:
        person_ids = [0]
    if not ball_ids:
        ball_ids = [32]
    person_set, ball_set = set(person_ids), set(ball_ids)
    imgsz = int(os.environ.get("FW_IMGSZ", "1280"))
    cap = cv2.VideoCapture(analysis)
    W, H = ainfo["width"], ainfo["height"]
    total = ainfo["frames"]
    frames: list[dict] = []
    tracks: dict[int, dict] = {}
    ball_yolo: list[list[tuple[float, float, float]]] = []
    ball_blob: list[list[tuple[float, float, float]]] = []
    stabilizer = stabilize.CameraStabilizer(W, H)
    cal_at = {int(round(v)) for v in np.linspace(0, max(0, total - 2), 6)}
    cal_samples: list[tuple[tuple[float, float], np.ndarray]] = []
    i = 0
    last_pct = 10

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        shift = stabilizer.update(frame)
        if i in cal_at:
            cal_samples.append((shift, frame.copy()))
        try:
            res = model.track(
                frame, persist=True, classes=sorted(person_set), conf=0.12,
                iou=0.5, imgsz=imgsz, max_det=90, tracker=TRACKER, verbose=False,
            )[0]
        except Exception:
            res = None
        # Ball detection is a separate predict pass. Verified on the Wolfsburg
        # clip: model.track() stops returning ball-class boxes once its tracker
        # has state, even though the same frame scores the ball at conf 0.8 in
        # a plain predict. A 6-12 px ball cannot depend on BoT-SORT keeping a
        # track for it.
        try:
            bres = model.predict(frame, classes=sorted(ball_set), conf=0.05,
                                 iou=0.5, imgsz=imgsz, max_det=20, verbose=False)[0]
        except Exception:
            bres = None
        players = []
        ball_boxes: list[tuple] = []
        bboxes = getattr(bres, "boxes", None)
        if bboxes is not None and len(bboxes):
            for b, cf in zip(bboxes.xyxy.cpu().numpy(), bboxes.conf.cpu().numpy()):
                ball_boxes.append((b, float(cf)))
        boxes = getattr(res, "boxes", None)
        if boxes is not None and len(boxes):
            xyxy = boxes.xyxy.cpu().numpy()
            cls = boxes.cls.cpu().numpy().astype(int)
            conf = boxes.conf.cpu().numpy()
            ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else np.full(len(xyxy), -1)
            for b, c, cf, tid in zip(xyxy, cls, conf, ids):
                if c in ball_set:
                    ball_boxes.append((b, float(cf)))
                    continue
                if tid < 0:
                    continue
                bw, bh = b[2] - b[0], b[3] - b[1]
                if c in person_set:
                    if cf < 0.25 or bh < 0.018 * H or bh / max(bw, 1) < 1.05:
                        continue
                    players.append({"id": int(tid), "box": [float(v) for v in b],
                                    "conf": float(cf), "role": names.get(int(c), "player")})
                    tr = tracks.setdefault(int(tid), {"crops": [], "team": -1,
                                                      "colour": "#94a3b8", "jersey": None,
                                                      "jersey_conf": 0.0,
                                                      "role": names.get(int(c), "player")})
                    if len(tr["crops"]) < 10:
                        crop = teams.torso_crop(frame, b)
                        if crop is not None and crop.shape[0] >= 10:
                            tr["crops"].append(crop.copy())
        ball_yolo.append(ballmod.reject_in_players(
            ballmod.yolo_candidates(ball_boxes), [p["box"] for p in players]))
        ball_blob.append(ballmod.candidates(frame))
        frames.append({"i": i, "t": round(i / analysis_fps, 3), "shift": shift,
                       "players": players, "ball": None})
        i += 1
        pct = 10 + int(58 * i / max(1, total))
        if pct > last_pct:
            on_progress(min(pct, 68), f"Tracking players · {i}/{total}")
            last_pct = pct

    cap.release()
    if not frames:
        raise RuntimeError("no decodable frames in source video")

    on_progress(69, "Linking ball track")
    ball_path = ballmod.track_candidates(ball_yolo, ball_blob, analysis_fps)
    for fi, (bx, by, bc) in ball_path.items():
        frames[fi]["ball"] = [float(bx), float(by), float(bc)]
        frames[fi]["ball_conf"] = float(bc)

    on_progress(70, "Calibrating pitch")
    cal = (calibrate.calibrate(cal_samples) if cal_samples
           else {"H": None, "quality": "none", "coverage": 0, "clipped": True})

    on_progress(74, "Clustering kits")
    team_samples = {tid: tr["crops"] for tid, tr in tracks.items()
                    if tr.get("role") != "referee" and tr["crops"]}
    team_map = teams.assign_teams(team_samples)
    for tid, meta in team_map.items():
        tracks[tid].update(meta)
    for tid, tr in tracks.items():
        if tr.get("role") == "referee":
            tr["team"] = -1

    # Kit clustering can fail on very small players. Never let that delete the
    # squad from the dashboard: fall back to an arbitrary split and say so.
    team_fallback = not any(tr.get("team") in (0, 1) for tr in tracks.values())
    if team_fallback:
        for n, tid in enumerate(sorted(tracks)):
            tracks[tid]["team"] = n % 2

    on_progress(78, "Reading jersey numbers")
    try:
        numbers = jersey.read_numbers({tid: tr["crops"] for tid, tr in tracks.items()})
        for tid, n in numbers.items():
            tracks[tid]["jersey"] = n["number"]
            tracks[tid]["jersey_conf"] = n["confidence"]
    except Exception:
        pass

    on_progress(82, "Saving player crops")
    for tid, tr in tracks.items():
        crops = tr.get("crops") or []
        if not crops:
            continue
        # Prefer the crop with the most kit pixels: the largest crop is often
        # a blurred box that is mostly grass.
        best = max(crops, key=lambda c: (len(teams._kit_pixels(c)), c.shape[0]))
        img = cv2.resize(best, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        name = f"{tid}.jpg"
        cv2.imwrite(os.path.join(crops_dir, name), img, [cv2.IMWRITE_JPEG_QUALITY, 86])
        tr["crop_name"] = name

    on_progress(86, "Computing analytics")
    data = analytics.build(frames, tracks, cal["H"], analysis_fps, W, H)
    valid_ids = set(data.get("valid_ids", []))

    names = [t["name"] for t in data["teams"]]
    if names[0] == names[1] or not names[0] or not names[1]:
        data["teams"][0]["name"] = "Team A"
        data["teams"][1]["name"] = "Team B"

    limitations = []
    if ainfo["duration"] >= max_seconds - 0.5:
        limitations.append(
            f"Clip mode: analysed {max_seconds:.0f}s from {start_seconds:.0f}s of the source, not a full match."
        )
    if cal["quality"] in ("fallback", "low", "none", "approximate"):
        limitations.append("Pitch registration was approximate; pitch-space distances and heatmaps carry extra error.")
    if not jersey.enabled():
        limitations.append("Jersey OCR is off (FW_JERSEY=1 to enable). Wide shots rarely have legible numbers.")
    if team_fallback:
        limitations.append("Kit colours could not be separated reliably; the two teams are an arbitrary split.")
    if data["coverage"].get("ball_detected_rate", data["coverage"]["ball_rate"]) < 40:
        limitations.append("Ball detection was intermittent; possession and pass counts are conservative.")
    limitations.append("Single-camera tracking cannot see through occlusions; treat ID-linked metrics as estimates.")
    if data["coverage"].get("tracks_total", 0) > 1.8 * max(1, data["coverage"].get("tracks_used", 1)):
        limitations.append("Track fragments were merged out; players who leave frame keep a new identity on re-entry.")
    if len(data["players"]) < 6:
        limitations.append("Very few players tracked — check camera framing or increase resolution.")

    overlay = {
        "fps": analysis_fps,
        "width": W,
        "height": H,
        "frames": [
            {
                "t": f["t"],
                "p": [
                    [p["id"], int(tracks.get(p["id"], {}).get("team", -1)),
                     round(p["box"][0] / W, 4), round(p["box"][1] / H, 4),
                     round(p["box"][2] / W, 4), round(p["box"][3] / H, 4), round(p["conf"], 2)]
                    for p in f["players"] if p["id"] in valid_ids
                ],
                "b": [round(f["ball"][0] / W, 4), round(f["ball"][1] / H, 4)] if f["ball"] else None,
            }
            for f in frames
        ],
    }

    result = {
        "id": match_id,
        "title": title,
        "status": "done",
        "video": {
            "duration": ainfo["duration"],
            "fps": analysis_fps,
            "width": W,
            "height": H,
            "source_duration": info["duration"],
            "proxy": "proxy.mp4",
            "thumb": "thumb.jpg" if thumb else None,
        },
        "calibration": {"quality": cal["quality"], "coverage": cal["coverage"],
                        "clipped": bool(cal.get("clipped", False)),
                        "polygon": [[round(float(x), 1), round(float(y), 1)]
                                    for x, y in cal.get("polygon", [])]},
        "teams": data["teams"],
        "players": data["players"],
        "events": data["events"],
        "momentum": data["momentum"],
        "possession": data["possession"],
        "coverage": data["coverage"],
        "totals": data["totals"],
        "limitations": limitations,
        "jersey_enabled": jersey.enabled(),
    }

    on_progress(92, "Writing coaching report")
    result["report"] = report.generate(result)

    def _write_json(name: str, payload) -> None:
        path = os.path.join(outdir, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)  # atomic: readers never see a partial file

    _write_json("tracks.json", overlay)
    _write_json("result.json", result)

    on_progress(100, "Done")
    return result

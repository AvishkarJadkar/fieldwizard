"""Replay cached detections through several tracker configs to pick the most stable one."""
import sys

sys.path.insert(0, "D:/fieldwizard")

import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.trackers.bot_sort import BOTSORT
from ultralytics.utils import YAML, IterableSimpleNamespace

VIDEO = "D:/fieldwizard/data/matches/sidemen/analysis.mp4"
FRAMES = 90

print("caching detections...", flush=True)
m = YOLO("D:/fieldwizard/models/football_v8.pt")
cap = cv2.VideoCapture(VIDEO)
cached = []
while len(cached) < FRAMES:
    ok, fr = cap.read()
    if not ok:
        break
    r = m.predict(fr, classes=[0, 1, 2, 3], conf=0.2, iou=0.5,
                  imgsz=1280, max_det=90, verbose=False)[0]
    cached.append((fr.copy(), r.boxes))
cap.release()
print("frames", len(cached), flush=True)

BASE = {
    "tracker_type": "bytetrack",
    "track_high_thresh": 0.25,
    "track_low_thresh": 0.1,
    "new_track_thresh": 0.4,
    "track_buffer": 45,
    "match_thresh": 0.8,
    "fuse_score": True,
}

CONFIGS = {
    "A_current": {},
    "B_nofuse_loose": {"fuse_score": False, "match_thresh": 0.9, "track_buffer": 60},
    "C_low_new": {"fuse_score": False, "match_thresh": 0.9, "new_track_thresh": 0.3,
                  "track_high_thresh": 0.2, "track_buffer": 60},
    "D_botsort": {"tracker_type": "botsort", "fuse_score": False, "match_thresh": 0.9,
                  "track_buffer": 60, "gmc_method": "sparseOptFlow",
                  "proximity_thresh": 0.5, "appearance_thresh": 0.8,
                  "with_reid": False},
}


def run(name, overrides):
    cfg = dict(BASE)
    cfg.update(overrides)
    ns = IterableSimpleNamespace(**cfg)
    cls = BOTSORT if cfg.get("tracker_type") == "botsort" else BYTETracker
    tr = cls(args=ns, frame_rate=10)
    seen, per_frame = [], []
    for fr, boxes in cached:
        out = tr.update(boxes, fr, None)
        ids = out[:, 4].astype(int).tolist() if len(out) else []
        seen.extend(ids)
        per_frame.append(len(ids))
    uniq = len(set(seen))
    print(f"{name:16s} unique={uniq:3d} mean_out={np.mean(per_frame):5.1f} "
          f"min_out={min(per_frame):2d} churn={uniq / max(1, np.mean(per_frame)):.2f}",
          flush=True)


for name, ov in CONFIGS.items():
    try:
        run(name, ov)
    except Exception as e:
        print(name, "ERR", repr(e)[:200], flush=True)

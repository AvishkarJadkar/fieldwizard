"""Replay cached detections through BoT-SORT variants; report track longevity."""
import sys

sys.path.insert(0, "D:/fieldwizard")

import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.trackers.bot_sort import BOTSORT
from ultralytics.utils import IterableSimpleNamespace

VIDEO = "D:/fieldwizard/data/matches/sidemen/analysis.mp4"
FRAMES = 150

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
    "tracker_type": "botsort",
    "track_high_thresh": 0.25,
    "track_low_thresh": 0.1,
    "new_track_thresh": 0.25,
    "track_buffer": 60,
    "match_thresh": 0.9,
    "fuse_score": False,
    "gmc_method": "sparseOptFlow",
    "proximity_thresh": 0.5,
    "appearance_thresh": 0.8,
    "with_reid": False,
}

CONFIGS = {
    "D_base": {},
    "E_loose": {"match_thresh": 0.95, "track_buffer": 90},
    "F_strict_new": {"new_track_thresh": 0.35},
    "G_fuse": {"fuse_score": True},
    "H_ecc": {"gmc_method": "ecc"},
}


def run(name, overrides):
    cfg = dict(BASE)
    cfg.update(overrides)
    tr = BOTSORT(args=IterableSimpleNamespace(**cfg), frame_rate=10)
    lengths = {}
    per_frame = []
    for fr, boxes in cached:
        out = tr.update(boxes, fr, None)
        ids = out[:, 4].astype(int).tolist() if len(out) else []
        per_frame.append(len(ids))
        for i in ids:
            lengths[i] = lengths.get(i, 0) + 1
    n = len(cached)
    long_tracks = sum(1 for v in lengths.values() if v >= n * 0.5)
    med = np.median(list(lengths.values())) if lengths else 0
    print(f"{name:14s} uniq={len(lengths):3d} long(>=50%)={long_tracks:2d} "
          f"median_len={med:5.1f} mean_out={np.mean(per_frame):5.1f} "
          f"min_out={min(per_frame):2d}", flush=True)


for name, ov in CONFIGS.items():
    try:
        run(name, ov)
    except Exception as e:
        print(name, "ERR", repr(e)[:200], flush=True)

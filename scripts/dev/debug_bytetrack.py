import sys

sys.path.insert(0, "D:/fieldwizard")

import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import YAML, IterableSimpleNamespace

CFG = "D:/fieldwizard/config/bytetrack_fw.yaml"
cfg = IterableSimpleNamespace(**YAML.load(CFG))
print("cfg", vars(cfg))

m = YOLO("D:/fieldwizard/models/football_v8.pt")
cap = cv2.VideoCapture("D:/fieldwizard/data/matches/sidemen/analysis.mp4")
tr = BYTETracker(args=cfg, frame_rate=10)

i = 0
while True:
    ok, fr = cap.read()
    if not ok:
        break
    if 20 <= i <= 40:
        r = m.predict(fr, classes=[0, 1, 2, 3], conf=0.25, iou=0.5,
                      imgsz=1280, max_det=90, verbose=False)[0]
        dets = r.boxes
        tracks = tr.update(dets, fr, None)
        states = {}
        for t in tr.tracked_stracks:
            states[t.state] = states.get(t.state, 0) + 1
        print(i, "dets", len(dets), "out", len(tracks),
              "tracked", len(tr.tracked_stracks), "lost", len(tr.lost_stracks),
              "removed", len(tr.removed_stracks), "states", states,
              "max_frames_lost", tr.max_frames_lost)
    else:
        r = m.predict(fr, classes=[0, 1, 2, 3], conf=0.25, iou=0.5,
                      imgsz=1280, max_det=90, verbose=False)[0]
        tr.update(r.boxes, fr, None)
    i += 1
cap.release()

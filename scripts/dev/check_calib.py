"""Visualise the auto-detected pitch polygon and the reprojected pitch model."""
import sys

sys.path.insert(0, "D:/fieldwizard")

import cv2
import numpy as np

from services.pipeline import calibrate

cap = cv2.VideoCapture("D:/fieldwizard/data/matches/sidemen/analysis.mp4")
frames = []
for i in range(6):
    ok, fr = cap.read()
    if not ok:
        break
    frames.append(fr)
cap.release()

cal = calibrate.calibrate(frames)
print("quality", cal["quality"], "coverage", cal["coverage"])
print("polygon", np.array(cal["polygon"]).round(1).tolist())

H = cal["H"]
frame = frames[0].copy()
poly = np.array(cal["polygon"], dtype=np.int32).reshape(-1, 1, 2)
cv2.polylines(frame, [poly], True, (0, 0, 255), 3)

Hinv = np.linalg.inv(H)


def proj(pts):
    p = np.array(pts, dtype=np.float32).reshape(-1, 1, 2)
    out = cv2.perspectiveTransform(p, Hinv).reshape(-1, 2)
    return out.astype(np.int32)


L, W = 105.0, 68.0
shapes = {
    "boundary": [(0, 0), (L, 0), (L, W), (0, W)],
    "halfway": [(L / 2, 0), (L / 2, W)],
    "left_box": [(0, 13.84), (16.5, 13.84), (16.5, 54.16), (0, 54.16)],
    "right_box": [(L, 13.84), (L - 16.5, 13.84), (L - 16.5, 54.16), (L, 54.16)],
}
for name, pts in shapes.items():
    p = proj(pts)
    if name in ("halfway",):
        cv2.line(frame, tuple(p[0]), tuple(p[1]), (255, 0, 0), 2)
    else:
        cv2.polylines(frame, [p.reshape(-1, 1, 2)], True, (255, 0, 0), 2)
    cv2.putText(frame, name, tuple(p[0]), 0, 0.6, (0, 255, 255), 2)

cv2.imwrite("D:/fieldwizard/data/raw/calib_check.jpg", frame)
print("wrote calib_check.jpg")

"""Measure accumulated global camera motion across the analysis clip."""
import cv2
import numpy as np

cap = cv2.VideoCapture("D:/fieldwizard/data/matches/sidemen/analysis.mp4")
prev = None
acc = np.zeros(2)
totals = []
i = 0
while True:
    ok, fr = cap.read()
    if not ok:
        break
    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (480, 270))
    g = g[60:250, :]  # crop out crowd / overlays
    if prev is not None:
        (dx, dy), resp = cv2.phaseCorrelate(np.float32(prev), np.float32(g))
        acc += (dx, dy)
        totals.append((i, round(dx, 2), round(dy, 2), round(resp, 3),
                       round(acc[0], 1), round(acc[1], 1)))
    prev = g
    i += 1
cap.release()

print("frames", i)
print("total accumulated shift (480x270 scale):", acc)
for row in totals[:12]:
    print("  ", row)
print("  ...")
for row in totals[-8:]:
    print("  ", row)
steps = np.array([[t[1], t[2]] for t in totals])
print("per-frame |shift| mean", np.linalg.norm(steps, axis=1).mean().round(2),
      "max", np.linalg.norm(steps, axis=1).max().round(2))
print("total path length", np.linalg.norm(steps, axis=1).sum().round(1))

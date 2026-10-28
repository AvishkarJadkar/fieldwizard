import sys
sys.path.insert(0, "D:/fieldwizard")
import cv2
from services.pipeline import ball

cap = cv2.VideoCapture("D:/fieldwizard/data/matches/acbb/analysis.mp4")
frames = []
for i in range(40):
    ok, fr = cap.read()
    if not ok:
        break
    frames.append(fr)
    if i in (0, 10, 20, 30):
        cs = ball.candidates(fr)
        print(i, len(cs), cs[:5])
        for cx, cy, s in cs:
            cv2.circle(fr, (int(cx), int(cy)), 10, (0, 0, 255), 2)
        cv2.imwrite(f"D:/fieldwizard/data/matches/acbb/cand_{i}.jpg", fr)
cap.release()

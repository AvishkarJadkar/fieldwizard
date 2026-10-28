import sys
sys.path.insert(0, "D:/fieldwizard")
import cv2
from ultralytics import YOLO

m = YOLO("D:/fieldwizard/models/football_v8.pt")
cap = cv2.VideoCapture("D:/fieldwizard/data/matches/sidemen/analysis.mp4")
seen = []
for i in range(40):
    ok, fr = cap.read()
    if not ok:
        break
    r = m.track(fr, persist=True, classes=[0, 1, 2, 3], conf=0.25, iou=0.5,
                imgsz=1280, max_det=90, tracker="D:/fieldwizard/config/bytetrack_fw.yaml",
                verbose=False)[0]
    b = r.boxes
    ids = b.id.cpu().numpy().astype(int).tolist() if b.id is not None else []
    seen.extend(ids)
    print(i, "det", len(b), "ids", len(ids), "unique_so_far", len(set(seen)), ids[:12])
cap.release()
print("total unique", len(set(seen)))

"""Ball detection fusion for wide footage.

Two independent sources are merged:

* the YOLO detector's ``ball`` class (the only source that reliably tells the
  ball apart from white paint), and
* a classic blob detector: small, bright, round, grass-surrounded blobs, used
  only to bridge the frames YOLO misses.

Blob candidates that sit in the same place for most of the clip are paint
(centre spot, line intersections, advertising boards) and are discarded before
linking. The remaining detections are linked into one constant-velocity path;
gaps are bridged only when the implied speed is physically possible.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

MAX_AREA = 320
MIN_AREA = 5
MAX_SIDE = 30
GATE = 80.0            # px, base association gate
MAX_MISS = 8           # frames a chain may coast before it is broken
MAX_FILL = 14          # frames a gap may be interpolated over
MAX_STEP_PX = 150.0    # px between consecutive frames before we call it a jump
MIN_CHAIN = 8          # detections needed for a chain to count
MIN_SCORE = 0.2        # mean score needed for a chain to count
HELPER_SCALE = 0.35    # blobs may assist a YOLO path, never lead it
STATIC_SHARE = 0.45    # blob present in this share of frames = paint
STATIC_CELL = 24       # px cell used to detect that


def _ring_green(hsv: np.ndarray, cx: int, cy: int, r: int = 9) -> float:
    h, w = hsv.shape[:2]
    hits = 0
    total = 0
    for a in range(16):
        ang = a * math.pi / 8
        x = int(cx + r * math.cos(ang))
        y = int(cy + r * math.sin(ang))
        if 0 <= x < w and 0 <= y < h:
            total += 1
            hh, ss, vv = hsv[y, x]
            if 30 <= hh <= 95 and ss > 35 and vv > 35:
                hits += 1
    return hits / max(1, total)


def candidates(frame: np.ndarray) -> list[tuple[float, float, float]]:
    """Bright, compact, grass-surrounded blobs. Score is 0..1."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    white = ((hsv[:, :, 2] > 160) & (hsv[:, :, 1] < 85)).astype(np.uint8) * 255
    n, _labels, stats, cents = cv2.connectedComponentsWithStats(white, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (MIN_AREA <= area <= MAX_AREA):
            continue
        if w > MAX_SIDE or h > MAX_SIDE or w < 2 or h < 2:
            continue
        ar = w / h
        if ar < 0.45 or ar > 2.2:
            continue
        cx, cy = float(cents[i][0]), float(cents[i][1])
        green = _ring_green(hsv, int(cx), int(cy))
        if green < 0.35:
            continue
        fill = area / float(w * h)
        if fill < 0.5:
            continue
        score = min(1.0, (green * 2.0 + fill + (1.0 - abs(area - 45) / 220.0)) / 3.0)
        out.append((cx, cy, float(score)))
    return out


def yolo_candidates(boxes) -> list[tuple[float, float, float]]:
    """Normalise raw YOLO ball boxes (xyxy, conf) into scored centres."""
    out = []
    if boxes is None:
        return out
    for box, conf in boxes:
        x1, y1, x2, y2 = [float(v) for v in box]
        w, h = x2 - x1, y2 - y1
        if not (4.0 <= w <= 40.0 and 4.0 <= h <= 40.0):
            continue
        # A football is round; white socks and shorts are not.
        if not (0.6 <= w / max(h, 1e-6) <= 1.6):
            continue
        out.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0, min(1.0, 0.5 + 0.5 * float(conf))))
    return out


def reject_in_players(cands: list[tuple[float, float, float]],
                      boxes: list[list[float]],
                      shrink: float = 0.06) -> list[tuple[float, float, float]]:
    """Drop ball detections that sit inside a player box.

    The detector's most common ball false positive is a white sock or short,
    which always falls inside the person box. The real ball is beside the feet,
    outside the shrunk box.
    """
    if not boxes:
        return cands
    out = []
    for c in cands:
        inside = False
        for x1, y1, x2, y2 in boxes:
            dx, dy = (x2 - x1) * shrink, (y2 - y1) * shrink
            if x1 + dx <= c[0] <= x2 - dx and y1 + dy <= c[1] <= y2 - dy:
                inside = True
                break
        if not inside:
            out.append(c)
    return out


def merge(cands: list[tuple[float, float, float]],
          radius: float = 6.0) -> list[tuple[float, float, float]]:
    """Deduplicate candidates that describe the same blob, best score first."""
    out: list[tuple[float, float, float]] = []
    for c in sorted(cands, key=lambda v: -v[2]):
        if all(math.hypot(c[0] - o[0], c[1] - o[1]) > radius for o in out):
            out.append(c)
    return out


def drop_static(per_frame: list[list[tuple[float, float, float]]]) -> list[list[tuple[float, float, float]]]:
    """Remove blob detections that never move: paint, not a ball."""
    n = max(1, len(per_frame))
    counts: dict[tuple[int, int], int] = {}
    for cs in per_frame:
        seen = {(int(c[0] // STATIC_CELL), int(c[1] // STATIC_CELL)) for c in cs}
        for cell in seen:
            counts[cell] = counts.get(cell, 0) + 1
    limit = STATIC_SHARE * n
    return [[c for c in cs
             if counts.get((int(c[0] // STATIC_CELL), int(c[1] // STATIC_CELL)), 0) <= limit]
            for cs in per_frame]


def _link(per_frame, start_i, start_c, used, step):
    seg = {start_i: start_c}
    pos = (start_c[0], start_c[1])
    vel = (0.0, 0.0)
    miss = 0
    i = start_i + step
    while 0 <= i < len(per_frame):
        pred = (pos[0] + vel[0], pos[1] + vel[1])
        gate = GATE + 14.0 * miss
        best = None
        for c in per_frame[i]:
            d = math.hypot(c[0] - pred[0], c[1] - pred[1])
            if d > gate:
                continue
            cost = d - 45.0 * c[2]
            if best is None or cost < best[0]:
                best = (cost, c)
        if best is None or i in used:
            miss += 1
            if miss > MAX_MISS:
                break
            i += step
            continue
        c = best[1]
        vx, vy = c[0] - pos[0], c[1] - pos[1]
        if math.hypot(vx, vy) > MAX_STEP_PX:
            break
        vel = (0.6 * vel[0] + 0.4 * vx, 0.6 * vel[1] + 0.4 * vy)
        pos = (c[0], c[1])
        miss = 0
        seg[i] = c
        i += step
    return seg


def _chain(primary, helper, fps):
    """Link candidates into a path, seeding only from primary detections."""
    n = len(primary)
    merged = [merge(primary[i] + [(c[0], c[1], c[2] * HELPER_SCALE) for c in helper[i]])
              for i in range(n)]
    seeds = sorted(((c[2], i, c) for i, cs in enumerate(primary) for c in cs), reverse=True)
    used: dict[int, tuple[float, float, float]] = {}
    path: dict[int, tuple[float, float, float]] = {}

    for _score, i, c in seeds:
        if i in used:
            continue
        seg = _link(merged, i, c, used, +1)
        seg.update({k: v for k, v in _link(merged, i, c, used, -1).items() if k != i})
        if len(seg) < MIN_CHAIN:
            continue
        scores = [v[2] for v in seg.values()]
        if float(np.mean(scores)) < MIN_SCORE and max(scores) < 0.35:
            continue
        for k, v in seg.items():
            used[k] = v
            path[k] = v
    return path


def _fill_gaps(path, fps):
    idx = sorted(path)
    for a, b in zip(idx, idx[1:]):
        gap = b - a - 1
        if gap <= 0 or gap > MAX_FILL:
            continue
        (x1, y1, c1), (x2, y2, c2) = path[a], path[b]
        if c1 <= 0 or c2 <= 0:
            continue
        if math.hypot(x2 - x1, y2 - y1) > MAX_STEP_PX * (b - a):
            continue
        for k in range(a + 1, b):
            f = (k - a) / float(b - a)
            path[k] = (x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, 0.0)
    return path


def track_candidates(yolo_per_frame: list[list[tuple[float, float, float]]],
                     blob_per_frame: list[list[tuple[float, float, float]]],
                     fps: float) -> dict[int, tuple[float, float, float]]:
    """Fuse YOLO and blob detections into one ball path.

    YOLO leads: it is the only source that does not confuse the ball with white
    paint. Blobs only assist inside a YOLO-led chain; if YOLO finds nothing at
    all, a static-filtered blob chain is used as a fallback.
    Returns ``{frame: (x, y, conf)}``; ``conf == 0`` marks an interpolated point.
    """
    blobs = drop_static(blob_per_frame)
    path = _chain(yolo_per_frame, blobs, fps)
    if len(path) < MIN_CHAIN:
        path = _chain(blobs, [], fps)
    return _fill_gaps(path, fps)

"""Automatic pitch registration for wide / panoramic footage.

Detects the green playing surface, extracts the four extreme corners of the
largest field contour and computes a homography to a 105 x 68 m pitch.
Falls back to a padded frame mapping when the field cannot be isolated.
"""
from __future__ import annotations

import cv2
import numpy as np

PITCH_L = 105.0
PITCH_W = 68.0


def _order_points(pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmax(d)]
    bl = pts[np.argmin(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


def _field_polygon(frame: np.ndarray):
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([30, 35, 35]), np.array([95, 255, 255]))
    k = max(9, int(w * 0.012)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < 0.12 * w * h:
        return None
    hull = cv2.convexHull(c)
    peri = cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, 0.02 * peri, True)
    if len(approx) < 4:
        return None
    return _order_points(approx.reshape(-1, 2))


def calibrate(samples: list) -> dict:
    """Try several frames; keep the most confident registration.

    ``samples`` may be a list of frames, or a list of ``(shift, frame)`` pairs
    where ``shift`` is the accumulated camera translation in source pixels.
    Polygon corners are moved into the stabilised (frame-0) coordinate frame
    before the homography is fitted.
    """
    best = None
    height, width = samples[0][1].shape[:2] if isinstance(samples[0], tuple) else samples[0].shape[:2]
    for item in samples[:20]:
        if isinstance(item, tuple):
            shift, frame = item
        else:
            shift, frame = (0.0, 0.0), item
        poly = _field_polygon(frame)
        if poly is None:
            continue
        poly = poly - np.array(shift, dtype=np.float32)
        area = cv2.contourArea(poly)
        if area <= 0:
            continue
        if best is None or area > best["area"]:
            best = {"poly": poly, "area": float(area)}

    if best is None:
        src = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
        dst = np.array(
            [[-4, -3], [PITCH_L + 4, -3], [PITCH_L + 4, PITCH_W + 3], [-4, PITCH_W + 3]],
            dtype=np.float32,
        )
        return {
            "H": cv2.getPerspectiveTransform(src, dst),
            "quality": "fallback",
            "coverage": 0.0,
            "clipped": True,
            "polygon": src.tolist(),
        }

    poly = best["poly"]
    dst = np.array([[0, 0], [PITCH_L, 0], [PITCH_L, PITCH_W], [0, PITCH_W]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(poly.astype(np.float32), dst)

    coverage = best["area"] / float(width * height)
    # If the detected field runs into the image border the pitch is only
    # partially visible, so the mapping is a normalised stretch, not a true
    # registration. Report that honestly instead of pretending it is exact.
    margin_x, margin_y = width * 0.02, height * 0.02
    clipped = bool(
        (poly[:, 0] < margin_x).any() and (poly[:, 0] > width - margin_x).any()
        or (poly[:, 1] < margin_y).any() and (poly[:, 1] > height - margin_y).any()
    )
    if clipped:
        quality = "approximate"
    else:
        quality = "auto" if coverage > 0.25 else "low"
    return {
        "H": H,
        "quality": quality,
        "coverage": round(float(coverage), 3),
        "clipped": clipped,
        "polygon": poly.tolist(),
    }


def to_pitch(H: np.ndarray, x: float, y: float) -> tuple[float, float]:
    pt = np.array([[[x, y]]], dtype=np.float32)
    out = cv2.perspectiveTransform(pt, H)[0, 0]
    return float(out[0]), float(out[1])


def inside(x: float, y: float, margin: float = 8.0) -> bool:
    return -margin <= x <= PITCH_L + margin and -margin <= y <= PITCH_W + margin

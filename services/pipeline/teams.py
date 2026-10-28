"""Team clustering from torso colour.

Wide-angle players are only ~30-80 px tall, so a naive torso crop is mostly
grass. We crop tight to the shirt, discard green (pitch) and very dark/very
bright background pixels, then cluster the remaining kit colours in Lab space.
"""
from __future__ import annotations

import colorsys

import cv2
import numpy as np
from sklearn.cluster import KMeans

MIN_CROPS_FOR_FIT = 2
MAX_SAMPLES = 8
DEFAULT_COLOUR = "#94a3b8"
MIN_KIT_VALUE = 55.0   # median L below this is shadow / a bad box, not a shirt
LUMA_W = 0.45          # luminance carries lighting, not identity -> low weight
CHROMA_W = 1.70        # a/b carry the kit colour -> high weight


def torso_crop(frame: np.ndarray, box: tuple[float, float, float, float]):
    """Tight shirt crop: upper torso only, avoiding head, arms and grass."""
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w = y2 - y1, x2 - x1
    if h < 8 or w < 4:
        return None
    cy1 = max(0, y1 + int(0.22 * h))
    cy2 = max(0, y1 + int(0.48 * h))
    cx1 = max(0, x1 + int(0.32 * w))
    cx2 = max(0, x1 + int(0.68 * w))
    crop = frame[cy1:cy2, cx1:cx2]
    if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 3:
        return None
    return crop


def _kit_pixels(crop: np.ndarray) -> np.ndarray:
    """Return BGR pixels that plausibly belong to a shirt, not the pitch."""
    flat = crop.reshape(-1, 3)
    if flat.size == 0:
        return flat
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    hue, sat, val = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    # Pitch grass is mid-brightness green. A neon-green *kit* sits in the same
    # hue band but is far brighter, so brightness is what separates them.
    grass = (hue > 30) & (hue < 100) & (sat > 45) & (val < 190)
    # Never fall back to the raw crop: a crop full of grass pulls the cluster
    # towards green, and a near-black crop (a bad box over shadow) pulls it
    # towards "dark", which is how a 21-vs-1 team split happens.
    return flat[~grass & (val > 45)]


def feature(crop: np.ndarray) -> np.ndarray | None:
    """Chroma-weighted kit descriptor for one torso crop."""
    pixels = _kit_pixels(crop)
    if len(pixels) < 6:
        return None
    lab = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3)
    lab = lab.astype(np.float32)
    median = np.median(lab, axis=0)
    if median[0] < MIN_KIT_VALUE:
        return None  # black / shadowed box: no usable kit information
    spread = np.percentile(lab, 75, axis=0) - median
    weights = np.array([LUMA_W, CHROMA_W, CHROMA_W], dtype=np.float32)
    return np.concatenate([median * weights / 255.0,
                           spread * np.array([0.25, 0.5, 0.5], dtype=np.float32) / 255.0])


def track_feature(crops: list[np.ndarray]) -> np.ndarray | None:
    """Median of the per-crop descriptors: one bad frame cannot move a kit."""
    feats = [f for f in (feature(c) for c in crops[:MAX_SAMPLES]) if f is not None]
    if not feats:
        return None
    return np.median(np.stack(feats), axis=0)


def _median_bgr(crops: list[np.ndarray]) -> np.ndarray:
    pixels = [p for c in crops[:MAX_SAMPLES] for p in [_kit_pixels(c)] if len(p)]
    if not pixels:
        return np.array([148, 163, 184], dtype=np.float32)
    stacked = np.concatenate([p.reshape(-1, 3) for p in pixels], axis=0)
    return np.median(stacked, axis=0).astype(np.float32)


def _hex(bgr: np.ndarray) -> str:
    b, g, r = [int(max(0, min(255, v))) for v in bgr]
    return f"#{r:02x}{g:02x}{b:02x}"


def colour_name(hex_colour: str) -> str:
    r = int(hex_colour[1:3], 16) / 255
    g = int(hex_colour[3:5], 16) / 255
    b = int(hex_colour[5:7], 16) / 255
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.18:
        return "Black"
    if s < 0.16:
        return "White" if v > 0.62 else "Grey"
    deg = h * 360
    if deg < 15 or deg >= 345:
        return "Red"
    if deg < 45:
        return "Orange"
    if deg < 70:
        return "Yellow"
    if deg < 165:
        return "Green"
    if deg < 200:
        return "Cyan"
    if deg < 260:
        return "Blue"
    if deg < 320:
        return "Purple"
    return "Pink"


def _cluster(feats: np.ndarray):
    """Two-way k-means with a balance guard.

    A degenerate split (one cluster holding almost everything) means brightness
    is dominating kit colour, so retry on chroma alone and keep the most
    balanced result. Returns ``(kmeans, columns)``.
    """
    n = len(feats)
    best = None
    for cols in (None, [1, 2, 4, 5]):
        x = feats if cols is None else feats[:, cols]
        try:
            km = KMeans(n_clusters=2, n_init=15, random_state=7).fit(x)
        except Exception:
            continue
        counts = np.bincount(km.labels_, minlength=2)
        if counts.min() == 0:
            continue
        balanced = counts.min() >= max(2, 0.15 * n)
        if best is None or (balanced, counts.min()) > best[0]:
            best = ((balanced, counts.min()), km, cols)
        if balanced:
            break
    if best is None:
        return None, None
    return best[1], best[2]


def assign_teams(samples: dict[int, list[np.ndarray]]) -> dict:
    """samples: track_id -> torso crops. Returns track_id -> {team, colour}."""
    unknown = {tid: {"team": -1, "colour": DEFAULT_COLOUR} for tid in samples}

    def candidates(min_crops: int) -> list[tuple[int, np.ndarray]]:
        out = []
        for tid, crops in samples.items():
            if len(crops) < min_crops:
                continue
            feat = track_feature(crops)
            if feat is None:
                continue
            out.append((tid, feat))
        return out

    # Prefer tracks with several crops (stable colour), but degrade to
    # single-crop tracks rather than losing team separation entirely.
    fitted = candidates(MIN_CROPS_FOR_FIT)
    if len(fitted) < 4:
        fitted = candidates(1)
    if len(fitted) < 2:
        return unknown

    ids = [tid for tid, _ in fitted]
    feats = np.stack([f for _, f in fitted])
    km, cols = _cluster(feats)
    if km is None:
        return unknown

    counts = np.bincount(km.labels_, minlength=2)

    # Order teams so team 0 is the larger kit group (stable across runs).
    order = list(np.argsort(-counts))
    mapping = {int(order[0]): 0, int(order[1]): 1}

    out = dict(unknown)
    for tid, label in zip(ids, km.labels_):
        out[tid] = {"team": mapping[int(label)], "colour": DEFAULT_COLOUR}

    team_colour: dict[int, str] = {}
    for cluster, team in mapping.items():
        members = [tid for tid, label in zip(ids, km.labels_) if int(label) == cluster]
        team_colour[team] = _hex(_median_bgr([c for tid in members for c in samples[tid]]))
        for tid in members:
            out[tid]["colour"] = team_colour[team]

    # Tracks with too few crops inherit the nearest kit cluster instead of
    # being discarded, otherwise short-lived players vanish from the dashboard.
    for tid, crops in samples.items():
        if out[tid]["team"] >= 0 or not crops:
            continue
        vec = track_feature(crops)
        if vec is None:
            continue
        probe = vec if cols is None else vec[cols]
        dists = [float(np.linalg.norm(probe - km.cluster_centers_[c])) for c in (0, 1)]
        best = mapping[int(np.argmin(dists))]
        out[tid] = {"team": best, "colour": team_colour.get(best, DEFAULT_COLOUR)}

    return out

"""Jersey number reading (experimental).

Frame-level OCR is unreliable; we collect torso crops per track, upscale them,
run digit OCR and vote across the track. A roster constraint (numbers 1-99)
turns this into a closed-set problem. Disabled unless FW_JERSEY=1 because it is
the slowest stage and wide broadcast shots rarely have legible digits.
"""
from __future__ import annotations

import os
import re

import cv2
import numpy as np

_reader = None


def enabled() -> bool:
    return os.environ.get("FW_JERSEY", "0") == "1"


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr

        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


def read_numbers(crops: dict[int, list[np.ndarray]], max_tracks: int = 18) -> dict[int, dict]:
    if not enabled():
        return {}
    reader = _get_reader()
    out: dict[int, dict] = {}

    ranked = sorted(crops.items(), key=lambda kv: -sum(c.shape[0] for c in kv[1]))[:max_tracks]
    for tid, track_crops in ranked:
        votes: dict[int, float] = {}
        for crop in track_crops[:6]:
            if crop.shape[0] < 26 or crop.shape[1] < 12:
                continue
            up = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 5, 40, 40)
            try:
                results = reader.readtext(gray, allowlist="0123456789", detail=1, mag_ratio=1.0)
            except Exception:
                continue
            for _box, text, conf in results:
                text = re.sub(r"\D", "", text)
                if not text or len(text) > 2:
                    continue
                n = int(text)
                if not 1 <= n <= 99:
                    continue
                votes[n] = votes.get(n, 0.0) + float(conf)

        if not votes:
            out[tid] = {"number": None, "confidence": 0.0}
            continue
        total = sum(votes.values())
        best = max(votes, key=votes.get)
        out[tid] = {
            "number": int(best),
            "confidence": round(min(0.99, votes[best] / total), 2),
        }
    return out

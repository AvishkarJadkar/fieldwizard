"""Global camera-motion estimation.

Broadcast cameras pan and zoom constantly. A single static homography turns that
camera motion into fake player movement (we measured ~290 px of pan in 20 s,
which showed up as 37 km/h for every player). We estimate the frame-to-frame
translation with phase correlation and accumulate it, so detections can be
mapped back into the coordinate frame the pitch homography was built for.
"""
from __future__ import annotations

import cv2
import numpy as np


class CameraStabilizer:
    """Accumulates global translation; returns per-frame shift in source pixels."""

    def __init__(self, width: int, height: int, work_width: int = 640,
                 crop_top: float = 0.24, min_response: float = 0.08):
        self.scale = work_width / float(max(1, width))
        self.work = (work_width, max(1, int(round(height * self.scale))))
        self.crop_top = int(self.work[1] * crop_top)
        self.min_response = min_response
        self.prev: np.ndarray | None = None
        self.total = np.zeros(2, dtype=np.float64)
        self.last_step = 0.0

    def _prep(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, self.work, interpolation=cv2.INTER_AREA)
        # Drop the crowd / scoreboard band: it dominates the correlation and is
        # often static, which would mask real camera motion.
        gray = gray[self.crop_top:, :]
        return np.float32(gray)

    def update(self, frame: np.ndarray) -> tuple[float, float]:
        cur = self._prep(frame)
        if self.prev is not None and self.prev.shape == cur.shape:
            (dx, dy), response = cv2.phaseCorrelate(self.prev, cur)
            plausible = (response >= self.min_response
                         and abs(dx) < 0.25 * self.work[0]
                         and abs(dy) < 0.25 * self.work[1])
            if plausible:
                self.total += (dx, dy)
                self.last_step = float(np.hypot(dx, dy))
        self.prev = cur
        return (self.total[0] / self.scale, self.total[1] / self.scale)

    def reset(self) -> None:
        self.prev = None
        self.total[:] = 0.0

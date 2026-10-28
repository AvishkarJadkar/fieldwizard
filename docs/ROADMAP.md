# FieldWizard roadmap

The one-day build is a working vertical slice on clips. Everything below is
scoped so that each item is independently shippable — no phase requires another
one first. Items in **Next up** are the highest value-per-hour given the current
state of the code.

## Current state (what exists today)

- End-to-end pipeline: ingest → YOLO detection + BoT-SORT tracking → camera
  stabilisation → kit clustering → pitch registration → analytics → report.
- Ball tracking is a fused path (YOLO ball detections + bright-blob detector,
  constant-velocity linking, paint suppression) that covers ~98% of frames.
- FastAPI service with SQLite job store, serial worker, byte-range video
  streaming, SPA hosting.
- React dashboard: match overview, squad, players, coaching report with
  clickable video evidence.
- Deterministic rules-based report; Gemini 2.5 Flash path written but untested
  end-to-end (no API key was available during the build).
- Result sanity suite (`scripts/validate_result.py`) that fails on degenerate
  team splits, low ball coverage, impossible speeds and broken overlays.

## Next up (in order)

1. **LLM report end-to-end test.** Add a `GEMINI_API_KEY`, run
   `scripts/regenerate_report.py`, and compare the LLM findings against the
   rules engine. ~1 hour. Nothing to build — only to verify and tune the prompt.
2. **Pass / touch reconstruction.** Touch events are sparse, so pass counts are
   0–3 per 20 s instead of the true count. Use the now-continuous ball path:
   detect touch = ball decelerating-to-stationary near a player, pass =
   sustained directional ball movement between two touches of different players.
   Estimated 1 day.
3. **Player re-identification across chunks** (prerequisite for full matches).
   Link track IDs at window boundaries using kit colour + position continuity.
   Estimated 2–3 days.
4. **Long-clip mode.** Sliding windows with overlap, per-window analytics,
   stitch events and possession; backfill from `FW_START_SECONDS`/`FW_MAX_SECONDS`
   which already exist. GPU strongly recommended by this point (~0.8 s/frame on
   CPU today).
5. **Ball accuracy pass.** Verify against manual labels on 3–4 diverse clips;
   tune `GATE`, `MAX_MISS`, `MAX_FILL` in `ball.py`; consider a second detector
   pass on a zoomed ROI around the predicted ball position for the frames the
   fusion misses.

## Later (planned, not started)

- **Pitch keypoint registration.** Replace the single homography with landmark
  detection (penalty spots, box corners, centre circle) for accurate pitch-space
  distances and non-degenerate maps when the pitch is clipped by the frame.
- **Jersey-number OCR for player identity.** `FW_JERSEY=1` exists; needs a
  dedicated crop-and-super-resolution pass on chest regions and only pays off on
  close or 4K footage.
- **Multi-camera input.** Several feeds of the same match, stitched by
  calibration.
- **Event enrichment.** Offside lines, xG estimates, set-piece detection
  (currently corner kicks surface as "shots").
- **Player metadata.** Map track IDs to real names once jersey OCR is reliable.
- **Cloud profile.** Celery/Redis workers, S3-compatible storage, Postgres;
  the API already isolates storage behind small helpers, so this is a port not a
  rewrite.
- **GPU profiles.** CUDA wheels are a drop-in (one order of magnitude faster
  detection); expose a `--device` flag through the API.
- **Auth + multi-tenancy**, Dockerfile + docker-compose, CI (lint, unit tests
  on `ball.py` linking with synthetic sequences, pipeline smoke test).

## Known hard limits (by design, documented for users)

- Single camera: occlusions and out-of-frame players are lost until they are
  visible again; re-entry keeps a new identity.
- Analytics are estimates from a single camera, not official statistics.
- Clip mode is the default; full-match performance is bounded by CPU tracking
  speed (~0.8 s per analysed frame).
- Jersey OCR off by default (wide shots rarely have legible numbers).
- LLM report needs a key; everything else runs fully offline.

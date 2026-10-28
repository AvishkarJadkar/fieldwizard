# FieldWizard

**Football video analytics from a single camera.** Upload a clip, and FieldWizard
returns player tracking, team separation, possession, heatmaps, movement
metrics, an event timeline and a coaching report — in a dark, FIFA-style
dashboard with the ball overlaid on the actual footage.

Built as a one-day vertical slice that is honest about accuracy and structured
to scale to full 90-minute matches.

---

## What it does

| Capability | Status | How |
| --- | --- | --- |
| Player + ball tracking | ✅ working | YOLOv8 football detector + BoT-SORT with global motion compensation |
| Ball detection fusion | ✅ working | Independent ball `predict` pass + bright-blob detector, constant-velocity linking, paint suppression |
| Team separation (kit colours) | ✅ working | Chroma-weighted, median-of-crops clustering in Lab space |
| Possession / touches | ✅ working | Ball-to-player distance in raw image space (camera-pan invariant) |
| Distance / speed / sprints | ✅ working | Stabilised image coordinates scaled by player pixel height (1.8 m reference) |
| Events | ✅ basic | Passes, turnovers, shots with timestamps (pass detection is the weakest analytic) |
| Heatmaps + formation metrics | ✅ approximate | Pitch homography; flagged `approximate` when the pitch is clipped by the frame |
| Momentum chart | ✅ working | Adaptive rolling window over possession changes |
| Coaching report | ✅ rules engine / ⚠️ LLM untested | Deterministic findings with timestamped evidence; Gemini 2.5 Flash path written but not yet verified end-to-end |
| Jersey numbers | 🔌 off by default | `FW_JERSEY=1`; wide tactical shots rarely have legible numbers |
| Full 90-minute matches | 🧱 scaffolding present | Windowed jobs exist; cross-chunk re-identification is the missing piece |

Legend: ✅ working · ⚠️ written, unverified · 🔌 gated behind a flag · 🧱 partial

---

## Quick start

Requirements: **Python 3.11+**, **Node 18+**, model weights (see
[`models/README.md`](models/README.md)).

```powershell
git clone <repo-url> fieldwizard
cd fieldwizard

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# model weights: place a YOLO model with ball/goalkeeper/player/referee classes
# at models/football_v8.pt (see models/README.md)

Copy-Item .env.example .env      # optional: add GEMINI_API_KEY
```

`.env` is read automatically by both the API and the CLI; real environment
variables take precedence.

### Run the dashboard

```powershell
# build the web app once
cd apps\web
npm install
npm run build
cd ..\..

# serve API + dashboard on http://127.0.0.1:8000
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Or `powershell -File scripts\serve.ps1`.

Frontend development with hot reload:

```powershell
cd apps\web
npm run dev        # http://localhost:5173, proxies /api to :8000
```

### Analyse a clip from the CLI

```powershell
$env:FW_START_SECONDS="14"; $env:FW_MAX_SECONDS="20"; $env:FW_ANALYSIS_FPS="15"
python scripts\run_pipeline.py data\raw\your_clip.mp4 `
  --id my_match --out data\matches\my_match --title "My Match"
```

Outputs land in `data/matches/<id>/`: `result.json` (all analytics + report),
`tracks.json` (per-frame overlay), `analysis.mp4` (analysis copy),
`proxy.mp4` (streaming video), `thumb.jpg`, `crops/` (player thumbnails).
The API picks up any such folder on startup, so CLI-produced matches appear in
the dashboard automatically.

### Upload through the UI instead

Drag a video onto the dashboard, set the start offset and clip length, and the
serial job queue processes it while the UI polls progress.

### Rebuild a report without re-analysing

Adding a `GEMINI_API_KEY` later does not require another tracking run:

```powershell
python scripts\regenerate_report.py data\matches\my_match
```

### Check a result

```powershell
python scripts\validate_result.py data\matches\my_match
```

Asserts the failure modes that actually bite: no players, **degenerate team
splits (e.g. 21 vs 1)**, low ball coverage, impossible speeds, possession not
summing to 100, overlay frames disagreeing with the video, and evidence
timestamps outside the clip.

---

## How the pipeline works

```
upload ─▶ probe ─▶ analysis copy (15 fps, 1080p) ─┬─▶ player detect + BoT-SORT
                                                  └─▶ ball detect (separate predict pass)
                                                        │
                          ┌─────────────────────────────┘
                          ▼
              camera stabilisation (phase correlation)
                          ▼
              ball path linking  ─▶  kit clustering ─▶ jersey OCR (optional)
                          ▼
              pitch registration (homography)
                          ▼
              analytics ─▶ coaching report ─▶ result.json + tracks.json
```

### Design decisions that matter for accuracy

1. **BoT-SORT, not ByteTrack.** Broadcast cameras pan. ByteTrack's IoU
   association fails when every box shifts together, re-spawning the whole squad
   with new IDs. BoT-SORT's global motion compensation warps tracks with the
   camera first.
2. **Ball detection never depends on the tracker.** Verified on real footage:
   once BoT-SORT has internal state, `model.track()` stops returning ball-class
   boxes entirely, even when the same frame scores the ball at conf 0.8. The
   ball is therefore detected in a separate `predict` pass and fused with a
   bright-blob detector (small, round, grass-surrounded candidates), then linked
   into a constant-velocity path. Blob candidates that sit still for most of the
   clip are pitch paint and are discarded; gaps are interpolated only when the
   implied speed is physically possible.
3. **Stabilised motion.** Frame-to-frame camera translation is accumulated with
   phase correlation and removed before measuring player movement. Without it,
   ~290 px of pan in 20 s read as ~37 km/h for every player.
4. **Metric scale from player height.** A footballer is ~1.8 m, so a player's
   bounding-box height gives a per-player metres-per-pixel scale — more reliable
   than trusting a homography fitted to a partially visible pitch.
5. **Possession in image space.** Ball-to-player distance is measured in raw
   pixels; the camera moves ball and players together, so the distance is
   pan-invariant and needs no calibration at all.
6. **Kit clustering is chroma-weighted and median-of-crops.** Luminance carries
   lighting, not identity; weighting it heavily splits "dark vs light"
   (referees, shadows) instead of "green vs white" — that is how a 21-vs-1 team
   split happens. Each track's descriptor is the median of its crops (one bad
   frame cannot move a kit), near-black crops are rejected, pitch green is
   filtered by hue *and* brightness (so neon-green kits survive), and a
   degenerate split triggers a chroma-only retry.
7. **Turnovers are sustained.** A possession change only counts if the new team
   holds the ball ≥1.5 s, so a single contested flick is not an event.
8. **Track filtering.** Tracks shorter than 10% of the clip are fragments and
   are dropped before analytics, so they do not invent extra players.
9. **Atomic writes + encode cache.** JSON artefacts are written through a temp
   file + rename (readers never see partial files), and re-encoded video copies
   are cached on their encode parameters, turning 230 s re-runs into ~1 s.

---

## Dashboard

Four tabs:

- **Match** — hero KPIs (passes, turnovers, distance, ball detection), possession
  bar, formation, momentum chart, and the video stage with the live tracking
  overlay: ball dot, players coloured by team, synced to the analysed frames.
- **Squad** — team cards, pass network, formation shapes, possession.
- **Players** — sortable table (distance, top speed, touches, sprints, rating),
  per-player profile with crop thumbnail and heatmap.
- **Report** — headline, findings with **clickable evidence buttons that seek
  the video to that timestamp**, training drills, and a data-quality panel
  generated from the actual run.

---

## Performance

Measured on CPU only (no CUDA in the dev environment):

| Stage | 20 s clip @ 15 fps, 1080p |
| --- | --- |
| Encode (cached after first run) | ~1 s |
| Detection + tracking (players + ball) | ~0.8 s / frame → ~4 min |
| Analytics + report | ~2 s |
| Full pipeline, cold | ~4–6 min |

GPU (CUDA wheels) is a drop-in change and roughly an order of magnitude faster;
the pipeline code is device-agnostic.

---

## Accuracy: what is real and what is approximate

The dashboard's *Report → Data quality & limitations* panel is generated per
match from the actual run; read that first. Reference runs:

**Wolfsburg broadcast clip** (20 s, 15 fps): 19 players, teams **10 vs 9**,
possession **50.9 / 49.1**, ball detected in **97.7%** of frames (path 100%),
115/115 validation checks.

**Sidemen Charity Match corner-kick scene** (20 s): 25 players, teams 14 vs 11,
ball detected 98.7%, 145/145 checks. This window is one team camping on the ball
at a corner, so the lopsided possession in it is genuine.

What to trust:

- **Tracking and the ball path** are the strong parts: roughly one long-lived
  track per player on wide, elevated footage; ball positions verified frame by
  frame on test footage.
- **Possession** is sound (nearest player within 4.5 m of the ball).
- **Distance and speed** are estimates: pan-corrected and height-scaled, but
  occlusion, ID switches and box jitter add error. Use them to rank players,
  not as official statistics.
- **Pitch-space visuals** (heatmaps, formation width/depth) depend on the
  homography and are labelled `approximate` when the pitch is clipped.
- **Pass counting is the weakest analytic** (0–3 per 20 s instead of the true
  count) — touch events are sparse; this is the top item in
  [`docs/ROADMAP.md`](docs/ROADMAP.md).
- **Jersey numbers** are off by default (`FW_JERSEY=1`), so players are
  identified by track ID.
- **Clip mode** is the default (20 s unless you raise it): this is a demo slice,
  not a match analysis.

---

## Scaling to a full match

The architecture already separates the expensive stage from the rest:

- **Windowing.** `FW_START_SECONDS` / `FW_MAX_SECONDS` are per-job parameters.
- **Chunked processing** is designed for: analytics are computed per window;
  the missing piece is re-identification across chunk boundaries (see roadmap).
- **Serial job queue.** One CPU-bound job at a time; on upload the summary is
  refreshed from disk on startup, so CLI runs appear automatically.
- Swap the in-process queue for Celery/RQ and SQLite for Postgres to scale out;
  storage touches are already isolated behind small helpers.

---

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | LLM/jersey availability, queue depth |
| `GET` | `/api/matches` | List matches with status and summary |
| `POST` | `/api/matches` | Upload a video (multipart: `file`, `title`, `start_seconds`, `max_seconds`, `fps`) |
| `GET` | `/api/matches/{id}` | Job metadata + full `result.json` |
| `GET` | `/api/matches/{id}/status` | Lightweight progress polling |
| `GET` | `/api/matches/{id}/tracks` | Per-frame overlay data |
| `GET` | `/api/matches/{id}/video` | Proxy video with byte-range support |
| `GET` | `/api/matches/{id}/thumb` | Poster frame |
| `GET` | `/api/matches/{id}/crops/{name}` | Player crop image |
| `DELETE` | `/api/matches/{id}` | Remove match and files |

---

## Repository layout

```
apps/
  api/            FastAPI app: endpoints, SQLite job store, serial worker, SPA host
  web/            React + TypeScript + Vite dashboard (Recharts, custom SVG pitch)
services/pipeline/
  video.py        probe, analysis copy, proxy, thumbnail, encode cache
  ball.py         ball detection fusion + constant-velocity linking
  stabilize.py    camera motion estimation (phase correlation)
  teams.py        kit clustering (chroma-weighted, median-of-crops)
  jersey.py       optional jersey-number OCR (FW_JERSEY=1)
  calibrate.py    pitch homography + quality labelling
  analytics.py    possession, motion, events, heatmaps, ratings, momentum
  llm.py          Gemini structured report (free tier)
  report.py       fact sheet + deterministic rules fallback
  run.py          orchestration
scripts/
  run_pipeline.py       CLI entry point
  validate_result.py    result sanity suite
  regenerate_report.py  rebuild reports without re-tracking
  serve.ps1             start the API
  dev/                  tracker benchmarks and debug probes used during the build
config/           BoT-SORT tracker configuration
docs/             product plan + roadmap
models/           weights (not committed) — see models/README.md
data/             runtime artefacts (ignored by git)
```

---

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `FW_START_SECONDS` | `0` | Clip start offset |
| `FW_MAX_SECONDS` | `30` | Clip length to analyse |
| `FW_ANALYSIS_FPS` | `15` | Analysis frame rate |
| `FW_IMGSZ` | `1280` | Detector inference size |
| `FW_MODEL` | `models/football_v8.pt` | Detector weights |
| `FW_JERSEY` | `0` | Enable jersey OCR |
| `FW_MAX_UPLOAD_MB` | `4096` | Upload limit (API) |
| `GEMINI_API_KEY` | — | Enables the LLM report; otherwise the rules engine runs |
| `FW_LLM_MODEL` | `gemini-2.5-flash` | LLM model id |

---

## Roadmap

Implemented, planned and the explicitly-ordered next steps live in
[`docs/ROADMAP.md`](docs/ROADMAP.md); the long-form product plan is
[`docs/PRODUCT_PLAN.md`](docs/PRODUCT_PLAN.md).

## Demo footage

`sidemen.webm` — Wikimedia Commons, **CC BY 4.0** (analysis window 14–34 s).
Rough footage and model weights are not distributed with the repository.

Tracking and analytics are estimates from a single camera and are not official
match statistics.

"""Pitch analytics.

Design notes (these matter for accuracy on wide-angle footage):

* Ball-to-player distances are measured in raw image pixels. Camera pan moves
  the ball and the players together, so this distance is pan-invariant and does
  not depend on pitch calibration at all. That is what possession, touches and
  passes are built on.
* Player motion is measured in *stabilised* image coordinates (camera shift
  removed) and converted to metres with a per-player scale derived from the
  player's pixel height (a footballer is ~1.8 m). This gives usable distances
  and speeds even when the homography is only approximate.
* Pitch coordinates (for heatmaps, formation shape and the pitch canvas) come
  from the homography and are labelled approximate when calibration is partial.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

PITCH_L, PITCH_W = 105.0, 68.0
GRID_X, GRID_Y = 24, 16
SPRINT_MS = 7.0
PLAYER_HEIGHT_M = 1.8
TOUCH_M = 2.2
POSSESS_M = 4.5
MAX_SPEED_MS = 10.5


def _xy(H, px, py):
    if H is None:
        return None
    pt = np.array([[[px, py]]], dtype=np.float32)
    out = cv2.perspectiveTransform(pt, H)[0, 0]
    return float(out[0]), float(out[1])


def _smooth(a: np.ndarray, k: int = 3) -> np.ndarray:
    if len(a) < k:
        return a
    ker = np.ones(k) / k
    return np.convolve(a, ker, mode="same")


def _heat(points: list[tuple[float, float]]) -> list[list[float]]:
    g = np.zeros((GRID_Y, GRID_X), dtype=np.float32)
    for x, y in points:
        ix = int(np.clip(x / PITCH_L * GRID_X, 0, GRID_X - 1))
        iy = int(np.clip(y / PITCH_W * GRID_Y, 0, GRID_Y - 1))
        g[iy, ix] += 1
    g = gaussian_filter(g, sigma=1.3)
    m = g.max()
    if m > 0:
        g = g / m
    return [[round(float(v), 3) for v in row] for row in g]


def _zscore(v: np.ndarray) -> np.ndarray:
    sd = v.std()
    if sd < 1e-9:
        return np.zeros_like(v)
    return (v - v.mean()) / sd


def _interp_ball(ball: dict[int, tuple[float, float]], n: int, fps: float,
                 max_gap: float = 0.2, px_per_m: float = 25.0) -> dict[int, tuple[float, float]]:
    """Linearly fill short detection gaps so possession is not fragmented.

    Only very short gaps are filled: a long gap plus a big jump is more likely a
    detector ID switch onto a different white object than a real ball path.
    """
    if not ball:
        return ball
    max_missing = max(1, int(round(max_gap * fps)))
    idx = sorted(ball)
    out = dict(ball)
    for a, b in zip(idx, idx[1:]):
        gap = b - a - 1
        if gap <= 0 or gap > max_missing:
            continue
        (x0, y0), (x1, y1) = ball[a], ball[b]
        # Compare against a physical speed cap, converted into pixels.
        if math.hypot(x1 - x0, y1 - y0) / ((b - a) / fps) > 40.0 * px_per_m:
            continue  # teleport: do not invent a path
        for k in range(1, gap + 1):
            f = k / (gap + 1)
            out[a + k] = (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
    return out


def build(frames: list[dict], tracks: dict, H, fps: float, width: int, height: int) -> dict:
    n = len(frames)

    # ---- per-frame geometry ----
    # raw_px   : camera-relative point (pan-invariant when paired with the ball)
    # stab_px  : camera shift removed, used for motion and pitch projection
    raw_px: dict[int, dict[int, tuple[float, float]]] = {tid: {} for tid in tracks}
    stab_px: dict[int, dict[int, tuple[float, float]]] = {tid: {} for tid in tracks}
    mpp: dict[int, dict[int, float]] = {tid: {} for tid in tracks}
    ball_raw: dict[int, tuple[float, float]] = {}
    ball_rate = 0
    ball_det = 0
    frame_scale: dict[int, float] = {}

    for i, f in enumerate(frames):
        sx, sy = f.get("shift", (0.0, 0.0))
        scales = []
        for p in f["players"]:
            tid = p["id"]
            if tid not in tracks:
                continue
            x1, y1, x2, y2 = p["box"]
            cx, fy = (x1 + x2) / 2.0, y2
            h = max(1.0, y2 - y1)
            scale = PLAYER_HEIGHT_M / h
            raw_px[tid][i] = (cx, fy)
            stab_px[tid][i] = (cx - sx, fy - sy)
            mpp[tid][i] = scale
            scales.append(scale)
        if scales:
            frame_scale[i] = float(np.median(scales))
        if f.get("ball"):
            ball_raw[i] = (float(f["ball"][0]), float(f["ball"][1]))
            ball_rate += 1
            if float(f.get("ball_conf", 1.0)) > 0:
                ball_det += 1

    global_scale = float(np.median([s for v in frame_scale.values() for s in [v]])) if frame_scale else 0.02

    ball = _interp_ball(ball_raw, n, fps, max_gap=0.2,
                        px_per_m=1.0 / max(global_scale, 1e-6))

    # Pitch projection (stabilised coordinates) for spatial visuals only.
    pitch_pos: dict[int, dict[int, tuple[float, float]]] = {tid: {} for tid in tracks}
    for tid, pts in stab_px.items():
        for i, (x, y) in pts.items():
            pt = _xy(H, x, y)
            if pt and -12 <= pt[0] <= PITCH_L + 12 and -10 <= pt[1] <= PITCH_W + 10:
                pitch_pos[tid][i] = pt
    ball_pitch: dict[int, tuple[float, float]] = {}
    for i, (x, y) in ball.items():
        sx, sy = frames[i].get("shift", (0.0, 0.0))
        pt = _xy(H, x - sx, y - sy)
        if pt:
            ball_pitch[i] = pt

    # Drop fragments: short tracks would invent extra players.
    min_frames = max(6, int(0.10 * n))
    valid = {tid for tid, pts in raw_px.items() if len(pts) >= min_frames}

    # ---- per-track motion (stabilised pixels -> metres) ----
    for tid, track in tracks.items():
        if tid not in valid:
            track.update({"_positions": {}, "_speeds": np.array([0.0]), "distance_m": 0.0,
                          "top_speed_kmh": 0.0, "sprints": 0})
            continue
        pts = stab_px[tid]
        idx = sorted(pts)
        xs = np.array([pts[i][0] for i in idx], dtype=np.float32)
        ys = np.array([pts[i][1] for i in idx], dtype=np.float32)
        if len(idx) >= 3:
            xs, ys = _smooth(xs), _smooth(ys)
        sm = {i: (float(x), float(y)) for i, x, y in zip(idx, xs, ys)}

        dist = 0.0
        speeds = []
        for a, b in zip(idx, idx[1:]):
            if b - a > max(2, int(round(fps * 0.2))):
                continue
            px = math.hypot(sm[b][0] - sm[a][0], sm[b][1] - sm[a][1])
            scale = 0.5 * (mpp[tid].get(a, global_scale) + mpp[tid].get(b, global_scale))
            d = px * scale
            dt = (b - a) / fps
            s = d / dt if dt > 0 else 0.0
            if s <= MAX_SPEED_MS:
                dist += d
                speeds.append(s)
        speeds_arr = np.array(speeds) if speeds else np.array([0.0])
        track["distance_m"] = round(float(dist), 1)
        track["top_speed_kmh"] = round(float(min(37.0, speeds_arr.max() * 3.6)), 1)
        track["sprints"] = int(_count_runs(speeds_arr, SPRINT_MS))
        track["_positions"] = pitch_pos.get(tid, {})
        track["_speeds"] = speeds_arr

    # ---- possession / touches (raw image space, pan-invariant) ----
    frame_team: list[int] = []
    touch_events: list[dict] = []
    last_touch = None
    last_touch_t = -99.0

    for i, f in enumerate(frames):
        t = i / fps
        if i not in ball:
            frame_team.append(-1)
            continue
        bx, by = ball[i]
        best = None
        for p in f["players"]:
            tid = p["id"]
            if tid not in valid or i not in raw_px[tid]:
                continue
            if tracks[tid]["team"] < 0:
                continue
            px, py = raw_px[tid][i]
            d = math.hypot(px - bx, py - by) * mpp[tid][i]
            if best is None or d < best[0]:
                best = (d, tid, px, py)
        if best is None or best[0] > POSSESS_M:
            frame_team.append(-1)
            if t - last_touch_t > 2.0:
                last_touch = None
            continue
        d, tid, px, py = best
        frame_team.append(int(tracks[tid]["team"]))
        if d <= TOUCH_M:
            if last_touch is None or tid != last_touch["tid"] or t - last_touch_t > 2.0:
                ev = {"t": round(t, 2), "tid": tid, "team": int(tracks[tid]["team"]),
                      "x": round(px, 1), "y": round(py, 1), "s": mpp[tid][i]}
                touch_events.append(ev)
                last_touch = ev
            last_touch_t = t
        elif t - last_touch_t > 1.5:
            last_touch = None

    frame_team = _majority(frame_team, 5)
    possessed = [v for v in frame_team if v >= 0]
    poss = {0: 0, 1: 0}
    for v in possessed:
        poss[v] = poss.get(v, 0) + 1
    total_poss = max(1, len(possessed))

    # ---- passes ----
    passes = []
    for a, b in zip(touch_events, touch_events[1:]):
        if b["t"] - a["t"] > 7.0 or a["tid"] == b["tid"]:
            continue
        # Touch points are raw pixels, so convert through the per-player scale
        # before applying the metre threshold for a pass.
        scale = 0.5 * (a.get("s", global_scale) + b.get("s", global_scale))
        d = math.hypot(b["x"] - a["x"], b["y"] - a["y"]) * scale
        if a["team"] == b["team"] and d > 3.5:
            passes.append({"t": a["t"], "from": a["tid"], "to": b["tid"], "team": a["team"],
                           "x": a["x"], "y": a["y"], "length": round(d, 1)})

    # ---- turnovers ----
    # A turnover is a *sustained* change of possession, not a single touch. In a
    # contested ball two opponents alternate touches several times a second;
    # counting each flip produced 21 "turnovers" in 20 seconds.
    min_hold = max(2, int(round(1.5 * fps)))
    segments = []
    start = 0
    for i in range(1, n + 1):
        if i == n or frame_team[i] != frame_team[start]:
            segments.append((start, i, frame_team[start]))
            start = i

    turnovers = []
    held: int | None = None
    for s, e, team in segments:
        if team not in (0, 1) or e - s < min_hold:
            continue
        if held is not None and held != team:
            # Attribute the loss to the team that had the ball, and name the
            # player closest to it on the last frame before the change.
            tid = None
            probe = max(0, s - 1)
            if probe in ball:
                bx, by = ball[probe]
                for p in frames[probe]["players"]:
                    pid = p["id"]
                    if (pid in valid and tracks[pid]["team"] == held
                            and probe in raw_px[pid]):
                        d = math.hypot(raw_px[pid][probe][0] - bx,
                                       raw_px[pid][probe][1] - by)
                        if tid is None or d < tid[0]:
                            tid = (d, pid)
            turnovers.append({
                "t": round(s / fps, 2),
                "tid": tid[1] if tid else None,
                "team": held,
                "x": round(ball.get(s, (0, 0))[0], 1),
                "y": round(ball.get(s, (0, 0))[1], 1),
            })
        held = team

    # ---- shots / goals ----
    # A shot must be a fast, sustained ball movement *towards* a goal from the
    # attacking third. Speed alone produces false positives whenever the
    # detector jumps between white objects (crowd, advertising boards, posts).
    shots, goals = [], []
    last_shot = -99.0
    prev_i = None
    for i in sorted(ball):
        t = i / fps
        if prev_i is not None and i - prev_i <= 2:
            dt = (i - prev_i) / fps
            px, py = ball[prev_i]
            x, y = ball[i]
            sp = math.hypot(x - px, y - py) * frame_scale.get(i, global_scale) / dt
            pp = ball_pitch.get(i)
            if pp and 18.0 < sp <= 35.0 and t - last_shot >= 5.0:
                gx, gy = pp
                toward_goal = (gx > PITCH_L / 2 and x > px) or (gx < PITCH_L / 2 and x < px)
                in_third = gx > PITCH_L * 0.74 or gx < PITCH_L * 0.26
                if toward_goal and in_third and abs(gy - PITCH_W / 2) < 18:
                    shots.append({"t": round(t, 2),
                                  "team": _team_near(frames[i], raw_px, i, tracks, x, y),
                                  "x": round(gx, 1), "y": round(gy, 1),
                                  "speed": round(sp, 1)})
                    last_shot = t
        prev_i = i

    for i, (gx, gy) in ball_pitch.items():
        if (gx <= 1.0 or gx >= PITCH_L - 1.0) and 30.0 <= gy <= 38.0:
            if shots and 0 <= i / fps - shots[-1]["t"] <= 6.0:
                if not goals or i / fps - goals[-1]["t"] > 4.0:
                    goals.append({"t": round(i / fps, 2),
                                  "team": _team_near(frames[i], raw_px, i, tracks,
                                                     *ball.get(i, (0, 0))),
                                  "x": round(gx, 1), "y": round(gy, 1)})

    # ---- team aggregates ----
    team_players = {0: [], 1: []}
    for tid, tr in tracks.items():
        if tid in valid and tr["team"] in (0, 1):
            team_players[tr["team"]].append(tid)

    team_meta = []
    for team in (0, 1):
        ids = team_players[team]
        all_pts = []
        per_frame: dict[int, list] = {}
        for tid in ids:
            for i, p in tracks[tid]["_positions"].items():
                all_pts.append(p)
                per_frame.setdefault(i, []).append(p)
        widths, depths, comps, cx = [], [], [], []
        for i, ps in per_frame.items():
            arr = np.array(ps)
            if len(arr) < 4:
                continue
            c = arr.mean(axis=0)
            cx.append(float(c[0]))
            widths.append(float(arr[:, 1].std() * 2))
            depths.append(float(arr[:, 0].std() * 2))
            comps.append(float(np.linalg.norm(arr - c, axis=1).mean()))

        tp = [p for p in passes if p["team"] == team]
        to = [p for p in turnovers if p["team"] == team]
        att = len(tp) + len(to)
        team_meta.append({
            "id": team,
            "name": None,
            "colour": _team_colour(tracks, team),
            "possession": round(poss.get(team, 0) / total_poss * 100, 1),
            "players": len(ids),
            "passes": len(tp),
            "turnovers": len(to),
            "pass_accuracy": round(len(tp) / att * 100, 1) if att else 0.0,
            "width": round(float(np.mean(widths)), 1) if widths else 0.0,
            "depth": round(float(np.mean(depths)), 1) if depths else 0.0,
            "compactness": round(float(np.mean(comps)), 1) if comps else 0.0,
            "avg_x": round(float(np.mean(cx)), 1) if cx else 0.0,
            "heatmap": _heat(all_pts),
            "avg_positions": [
                {"track_id": tid,
                 "x": round(float(np.mean([p[0] for p in tracks[tid]["_positions"].values()])), 1),
                 "y": round(float(np.mean([p[1] for p in tracks[tid]["_positions"].values()])), 1)}
                for tid in ids if tracks[tid]["_positions"]
            ],
            "network": _network(tp, tracks, ids),
        })

    # ---- player rows ----
    rows = []
    for tid, tr in tracks.items():
        if tid not in valid or tr["team"] not in (0, 1):
            continue
        pts = tr.get("_positions", {})
        mins = max(len(raw_px[tid]) / fps / 60, 0.01)
        passes_by = [p for p in passes if p["from"] == tid]
        lost = [p for p in turnovers if p["tid"] == tid]
        touches = [e for e in touch_events if e["tid"] == tid]
        rows.append({
            "track_id": tid,
            "team": tr["team"],
            "jersey": tr.get("jersey"),
            "jersey_conf": tr.get("jersey_conf", 0),
            "name": f"#{tr['jersey']}" if tr.get("jersey") else f"Player {tid}",
            "minutes": round(mins, 2),
            "distance_m": tr.get("distance_m", 0),
            "distance_per_min": round(tr.get("distance_m", 0) / mins, 1),
            "top_speed": tr.get("top_speed_kmh", 0),
            "sprints": tr.get("sprints", 0),
            "touches": len(touches),
            "passes": len(passes_by),
            "turnovers": len(lost),
            "avg_x": round(float(np.mean([p[0] for p in pts.values()])), 1) if pts else 0.0,
            "avg_y": round(float(np.mean([p[1] for p in pts.values()])), 1) if pts else 0.0,
            "heatmap": _heat(list(pts.values())),
            "colour": tr.get("colour", "#94a3b8"),
            "crop": tr.get("crop_name"),
            "_pmin": len(passes_by) / mins,
            "_tmin": len(touches) / mins,
            "_lmin": len(lost) / mins,
            "_dmin": tr.get("distance_m", 0) / mins,
        })

    if rows:
        z = {
            "d": _zscore(np.array([r["_dmin"] for r in rows])),
            "t": _zscore(np.array([r["_tmin"] for r in rows])),
            "p": _zscore(np.array([r["_pmin"] for r in rows])),
            "s": _zscore(np.array([r["top_speed"] for r in rows])),
            "l": _zscore(np.array([r["_lmin"] for r in rows])),
        }
        for j, r in enumerate(rows):
            rating = (6.2 + 0.34 * z["d"][j] + 0.30 * z["t"][j] + 0.20 * z["p"][j]
                      + 0.14 * z["s"][j] - 0.22 * z["l"][j])
            r["rating"] = round(float(np.clip(rating, 3.5, 9.9)), 1)
            for k in ("_pmin", "_tmin", "_lmin", "_dmin"):
                r.pop(k, None)

    rows.sort(key=lambda r: (-r["rating"], r["track_id"]))
    for t in team_meta:
        t["name"] = f"Team {teams_label(t['colour'])}"

    events = []
    for p in passes:
        events.append({"t": p["t"], "type": "pass", "team": p["team"],
                       "player": p["from"], "detail": f"{p['length']} m", "x": p["x"], "y": p["y"]})
    for t in turnovers:
        events.append({"t": t["t"], "type": "turnover", "team": t["team"],
                       "player": t["tid"], "detail": "possession lost", "x": t["x"], "y": t["y"]})
    for s in shots:
        events.append({"t": s["t"], "type": "shot", "team": s["team"], "player": None,
                       "detail": f"{s['speed']} m/s", "x": s["x"], "y": s["y"]})
    for g in goals:
        events.append({"t": g["t"], "type": "goal", "team": g["team"], "player": None,
                       "detail": "goal", "x": g["x"], "y": g["y"]})
    events.sort(key=lambda e: e["t"])

    return {
        "teams": team_meta,
        "players": rows,
        "valid_ids": sorted(int(t) for t in valid),
        "events": events[:80],
        "momentum": _momentum(frames, ball_pitch, frame_team, fps),
        "possession": {"a": round(poss.get(0, 0) / total_poss * 100, 1),
                       "b": round(poss.get(1, 0) / total_poss * 100, 1),
                       "neutral": round(100 - (poss.get(0, 0) + poss.get(1, 0)) / total_poss * 100, 1)},
        "coverage": {
            "ball_rate": round(ball_rate / max(1, n) * 100, 1),
            "ball_detected_rate": round(ball_det / max(1, n) * 100, 1),
            "avg_players": round(sum(len([p for p in f["players"] if p["id"] in valid])
                                     for f in frames) / max(1, n), 1),
            "pitch_points": round(sum(len(pitch_pos[t]) for t in valid) / max(1, n), 1),
            "tracks_total": len(tracks),
            "tracks_used": len(valid),
        },
        "totals": {
            "passes": len(passes),
            "turnovers": len(turnovers),
            "shots": len(shots),
            "goals": len(goals),
            "distance_m": round(sum(r["distance_m"] for r in rows), 0),
        },
    }


def _count_runs(speeds: np.ndarray, threshold: float) -> int:
    runs, cur = 0, 0
    for s in speeds:
        if s >= threshold:
            cur += 1
        else:
            if cur >= 2:
                runs += 1
            cur = 0
    if cur >= 2:
        runs += 1
    return runs


def _majority(seq: list[int], k: int) -> list[int]:
    out = []
    half = k // 2
    for i in range(len(seq)):
        window = [v for v in seq[max(0, i - half):i + half + 1] if v >= 0]
        if not window:
            out.append(-1)
        else:
            out.append(max(set(window), key=window.count))
    return out


def _team_near(frame: dict, raw_px: dict, i: int, tracks: dict, bx: float, by: float):
    best = None
    for p in frame["players"]:
        tid = p["id"]
        if i in raw_px.get(tid, {}) and tracks.get(tid, {}).get("team", -1) >= 0:
            px, py = raw_px[tid][i]
            d = math.hypot(px - bx, py - by)
            if best is None or d < best[0]:
                best = (d, int(tracks[tid]["team"]))
    return best[1] if best else -1


def _team_colour(tracks: dict, team: int) -> str:
    cols = [t.get("colour", "#94a3b8") for t in tracks.values() if t.get("team") == team]
    return cols[0] if cols else "#94a3b8"


def teams_label(colour: str) -> str:
    from .teams import colour_name

    return colour_name(colour)


def _network(passes: list[dict], tracks: dict, ids: list[int]) -> dict:
    nodes = {}
    for tid in ids:
        pts = tracks[tid].get("_positions", {})
        if pts:
            nodes[tid] = {
                "x": round(float(np.mean([p[0] for p in pts.values()])), 1),
                "y": round(float(np.mean([p[1] for p in pts.values()])), 1),
            }
    edges = {}
    for p in passes:
        if p["from"] in nodes and p["to"] in nodes:
            key = (p["from"], p["to"])
            edges[key] = edges.get(key, 0) + 1
    return {
        "nodes": [{"id": k, **v} for k, v in nodes.items()],
        "edges": [{"from": a, "to": b, "count": c} for (a, b), c in
                  sorted(edges.items(), key=lambda kv: -kv[1])[:20]],
    }


def _momentum(frames: list[dict], ball_pitch: dict, frame_team: list[int], fps: float) -> list[dict]:
    if not frames:
        return []
    # Aim for a readable number of buckets: a 20 s clip should not collapse to
    # two points, and a 90 minute match should not produce 540.
    duration = len(frames) / fps
    win = max(1, int(round(float(np.clip(duration / 14.0, 4.0, 30.0)) * fps)))
    out = []
    for start in range(0, len(frames), win):
        end = min(len(frames), start + win)
        teams = [frame_team[i] for i in range(start, end) if frame_team[i] >= 0]
        if not teams:
            continue
        share = (teams.count(0) - teams.count(1)) / len(teams)
        xs = [ball_pitch[i][0] for i in range(start, end) if i in ball_pitch]
        territory = ((np.mean(xs) / PITCH_L) - 0.5) * 2 if xs else 0.0
        out.append({"t": round(start / fps, 1),
                    "v": round(float(0.7 * share + 0.3 * territory), 3)})
    return out

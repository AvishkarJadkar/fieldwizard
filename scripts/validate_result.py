"""Sanity-check a finished match folder.

Catches the failure modes that actually happened during development: an empty
player list, lopsided team assignment, impossible speeds, possession that does
not sum to 100, and overlay frames that disagree with the video.

Usage:
    python scripts/validate_result.py data/matches/sidemen
"""
from __future__ import annotations

import json
import os
import sys

CHECKS = 0
FAILURES: list[str] = []


def check(ok: bool, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(message)


def main(folder: str) -> int:
    result_path = os.path.join(folder, "result.json")
    tracks_path = os.path.join(folder, "tracks.json")
    for p in (result_path, tracks_path):
        if not os.path.exists(p):
            print(f"MISSING {p}")
            return 2

    with open(result_path, encoding="utf-8") as f:
        r = json.load(f)
    with open(tracks_path, encoding="utf-8") as f:
        t = json.load(f)

    players = r.get("players", [])
    teams = r.get("teams", [])

    check(len(teams) == 2, f"expected 2 teams, got {len(teams)}")
    check(len(players) >= 6, f"too few players tracked: {len(players)}")

    for p in players:
        tag = p.get("name", p.get("track_id"))
        check(p.get("team") in (0, 1), f"{tag}: team not assigned ({p.get('team')})")
        check(0 <= p.get("top_speed", 0) <= 40, f"{tag}: implausible top speed {p.get('top_speed')} km/h")
        check(0 <= p.get("rating", 0) <= 10, f"{tag}: rating out of range {p.get('rating')}")
        check(p.get("distance_m", 0) >= 0, f"{tag}: negative distance")
        check(len(p.get("heatmap", [])) == 16, f"{tag}: heatmap is not 16 rows")

    poss = r.get("possession", {})
    total = poss.get("a", 0) + poss.get("b", 0) + poss.get("neutral", 0)
    check(abs(total - 100) < 1.0, f"possession sums to {total}, expected 100")

    for team in teams:
        check(team.get("players", 0) > 0, f"{team.get('name')}: no players assigned")
        check(len(team.get("heatmap", [])) == 16, f"{team.get('name')}: bad heatmap shape")

    events = r.get("events", [])
    times = [e["t"] for e in events]
    check(times == sorted(times), "events are not sorted by time")

    frames = t.get("frames", [])
    duration = r.get("video", {}).get("duration", 0)
    fps = t.get("fps", 1)
    check(abs(len(frames) - duration * fps) <= 2, f"overlay has {len(frames)} frames, expected ~{duration * fps:.0f}")

    report = r.get("report", {})
    check(bool(report.get("headline")), "report has no headline")
    check(len(report.get("findings", [])) > 0, "report has no findings")
    for f in report.get("findings", []):
        for ev in f.get("evidence", []):
            check(0 <= ev.get("ts", -1) <= duration + 0.5, f"evidence timestamp {ev.get('ts')} outside clip")

    cov = r.get("coverage", {})
    check(cov.get("ball_rate", 0) > 60, f"ball path covers only {cov.get('ball_rate')}% of frames")
    check(cov.get("ball_detected_rate", 100) > 20,
          f"ball actually detected in only {cov.get('ball_detected_rate')}% of frames")
    check(
        cov.get("tracks_used", 0) <= cov.get("tracks_total", 0),
        "tracks_used exceeds tracks_total",
    )

    # A 21-vs-1 split means the kit clustering collapsed onto one team.
    counts = [len([p for p in players if p.get("team") == t]) for t in (0, 1)]
    check(min(counts) >= 0.25 * max(1, sum(counts)),
          f"team split is degenerate: {counts[0]} vs {counts[1]}")

    print(f"{os.path.basename(folder)}: {len(players)} players, {len(events)} events, "
          f"ball {cov.get('ball_rate')}%, possession {poss.get('a')}/{poss.get('b')}")
    print(f"{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    for f in FAILURES:
        print(f"  FAIL {f}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/matches/sidemen"))

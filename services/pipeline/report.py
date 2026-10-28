"""Deterministic report builder + LLM enrichment."""
from __future__ import annotations

from . import llm


def _fmt(t: float) -> str:
    m, s = divmod(int(max(0, t)), 60)
    return f"{m}:{s:02d}"


def build_fact_sheet(result: dict) -> dict:
    teams = result["teams"]
    players = result["players"]
    return {
        "sample_seconds": result["video"]["duration"],
        "coverage": result["coverage"],
        "possession": result["possession"],
        "teams": [
            {k: t[k] for k in ("name", "possession", "passes", "pass_accuracy", "turnovers",
                               "width", "depth", "compactness", "avg_x", "players")}
            for t in teams
        ],
        "players": [
            {k: p[k] for k in ("name", "team", "minutes", "distance_m", "distance_per_min",
                               "top_speed", "sprints", "touches", "passes", "turnovers", "rating",
                               "avg_x", "avg_y")}
            for p in players[:14]
        ],
        "totals": result["totals"],
        "calibration": result["calibration"],
        "limitations": result["limitations"],
    }


def generate(result: dict) -> dict:
    facts = build_fact_sheet(result)
    events = result["events"]
    report = llm.generate(facts, events)
    if report:
        report.setdefault("limitations", result["limitations"])
        return report
    return _fallback(result)


def _fallback(result: dict) -> dict:
    teams = result["teams"]
    players = result["players"]
    events = result["events"]
    poss = result["possession"]
    total_seconds = result["video"]["duration"]
    a, b = teams[0], teams[1]

    findings = []
    if abs(poss["a"] - poss["b"]) >= 8:
        lead = a if poss["a"] > poss["b"] else b
        findings.append({
            "title": f"{lead['name']} controlled possession",
            "detail": f"{lead['name']} held {lead['possession']}% of possession versus "
                      f"{100 - lead['possession']:.1f}%. Sustained possession usually means better rest defence, "
                      f"but check whether it translated into entries into the final third.",
            "confidence": "high",
            "evidence": _spread_events(events, ["pass", "turnover"], 2),
            "recommendation": "Review the first 10 seconds after each regain: is the team progressing or recycling sideways?",
        })

    if players:
        # players[] is sorted by rating, so pick the distance leader explicitly.
        top = max(players, key=lambda p: p["distance_m"])
        findings.append({
            "title": f"{top['name']} covered the most ground",
            "detail": f"{top['name']} covered {top['distance_m']:.0f} m ({top['distance_per_min']:.1f} m/min) "
                      f"with a top speed of {top['top_speed']:.1f} km/h and {top['sprints']} sprints.",
            "confidence": "medium",
            "evidence": _spread_events(events, ["pass", "turnover"], 1),
            "recommendation": "Use this player's movement as the reference for the team's pressing triggers.",
        })

    busiest = max(players, key=lambda p: p["touches"]) if players else None
    if busiest and busiest["touches"] > 0:
        findings.append({
            "title": f"{busiest['name']} was the main link",
            "detail": f"{busiest['touches']} touches and {busiest['passes']} completed passes. "
                      f"Highest involvement on the pitch in this sample.",
            "confidence": "medium",
            "evidence": _spread_events(events, ["pass", "turnover"], 1),
            "recommendation": "Build progression patterns around this player, but add a second outlet to avoid predictability.",
        })

    losing = max(teams, key=lambda t: t["turnovers"])
    if losing["turnovers"] > 0:
        findings.append({
            "title": f"{losing['name']} lost possession most often",
            "detail": f"{losing['turnovers']} turnovers in {total_seconds:.0f}s. "
                      f"Pass accuracy was {losing['pass_accuracy']:.0f}%.",
            "confidence": "medium",
            "evidence": _spread_events(events, ["turnover"], 2),
            "recommendation": "Add a safe backwards option when the forward pass is blocked; train scanning before receiving.",
        })

    tighter = min(teams, key=lambda t: t["compactness"])
    if tighter["compactness"] > 0:
        findings.append({
            "title": f"{tighter['name']} held the tighter shape",
            "detail": f"Average compactness {tighter['compactness']:.1f} m from the team centroid, "
                      f"width {tighter['width']:.1f} m and depth {tighter['depth']:.1f} m.",
            "confidence": "medium",
            "evidence": _spread_events(events, ["turnover", "pass"], 1),
            "recommendation": "Keep the distances between units under 12 m when defending; test it in a 6v6 possession rondo.",
        })

    return {
        "headline": f"{a['name']} {poss['a']:.0f}% – {poss['b']:.0f}% {b['name']}",
        "summary": (
            f"Sample length {_fmt(total_seconds)}. {len(players)} players tracked across "
            f"{result['coverage']['avg_players']:.1f} detections per frame, with the ball found in "
            f"{result['coverage'].get('ball_detected_rate', result['coverage']['ball_rate']):.0f}% of frames. "
            f"{result['totals']['passes']} passes and {result['totals']['turnovers']} turnovers were detected. "
            "Metrics are estimates from single-camera tracking and should be read as directional, not official."
        ),
        "findings": findings,
        "training": [
            {"focus": "Possession under pressure",
             "drill": "4v4+3 rondo with a 2-touch limit",
             "why": "Improves scanning and first-touch direction after regains."},
            {"focus": "Defensive compactness",
             "drill": "11v11 shadow play, 20 m depth limit",
             "why": "Directly targets the measured width/depth imbalance."},
            {"focus": "Transition reaction",
             "drill": "5-second counter-press game",
             "why": "Turns turnovers into immediate regain opportunities."},
        ],
        "limitations": result["limitations"],
        "engine": "rules",
    }


def _spread_events(events: list[dict], types: list[str], n: int) -> list[dict]:
    """Pick evidence spread across the clip instead of always the first events.

    Two findings that both cite 0:03 look like a copy-paste bug to a coach, so
    sample evenly over the event list. If the preferred event types are too
    rare (a 20 s clip may contain a single pass), widen to all events rather
    than repeating one timestamp.
    """
    pool = [e for e in events if e["type"] in types]
    if len(pool) < n:
        pool = list(events)
    if not pool:
        return []
    if len(pool) <= n:
        picks = pool
    else:
        step = (len(pool) - 1) / max(1, n - 1) if n > 1 else 0
        picks = [pool[int(round(k * step))] for k in range(n)]
    seen, out = set(), []
    for e in picks:
        key = round(e["t"], 1)
        if key in seen:
            continue
        seen.add(key)
        out.append({"ts": e["t"], "label": f"{e['type']} at {_fmt(e['t'])}"})
    return out

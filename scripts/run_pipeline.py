"""Run the pipeline on a local file without the API (debugging)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.pipeline import run as pipeline  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--id", default="dev")
    ap.add_argument("--out", default="data/matches/dev")
    ap.add_argument("--title", default="Dev match")
    args = ap.parse_args()

    started = time.time()
    last = {"pct": -1}

    def progress(pct: int, msg: str) -> None:
        if pct != last["pct"]:
            print(f"[{pct:3d}%] {msg}  ({time.time() - started:.0f}s)", flush=True)
            last["pct"] = pct

    result = pipeline.run(args.id, args.video, args.out, args.title, progress)
    print(json.dumps({
        "players": len(result["players"]),
        "teams": [(t["name"], t["possession"]) for t in result["teams"]],
        "coverage": result["coverage"],
        "calibration": result["calibration"],
        "totals": result["totals"],
        "events": len(result["events"]),
        "report_engine": result["report"].get("engine"),
    }, indent=2))


if __name__ == "__main__":
    main()

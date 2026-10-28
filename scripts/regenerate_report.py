"""Rebuild the coaching report for an already-analysed match.

Tracking and analytics are the expensive stages; the report is cheap. Use this
after adding a GEMINI_API_KEY, or after changing report.py, instead of
re-running the whole pipeline.

Usage:
    python scripts/regenerate_report.py data/matches/sidemen
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.pipeline import llm, report  # noqa: E402


def main(folder: str) -> int:
    path = os.path.join(folder, "result.json")
    if not os.path.exists(path):
        print(f"no result.json in {folder}")
        return 2

    with open(path, encoding="utf-8") as f:
        result = json.load(f)

    new = report.generate(result)
    result["report"] = new

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)

    engine = "Gemini" if llm.available() else "rules"
    print(f"report rebuilt with {engine} engine: {new.get('headline')}")
    print(f"  {len(new.get('findings', []))} findings, "
          f"{len(new.get('training', []))} drills")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/matches/sidemen"))

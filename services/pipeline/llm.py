"""Gemini (free tier) structured report generation with graceful fallback."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "headline": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "findings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "detail": {"type": "STRING"},
                    "confidence": {"type": "STRING"},
                    "evidence": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "ts": {"type": "NUMBER"},
                                "label": {"type": "STRING"},
                            },
                            "required": ["ts", "label"],
                        },
                    },
                    "recommendation": {"type": "STRING"},
                },
                "required": ["title", "detail", "confidence", "recommendation"],
            },
        },
        "training": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "focus": {"type": "STRING"},
                    "drill": {"type": "STRING"},
                    "why": {"type": "STRING"},
                },
                "required": ["focus", "drill", "why"],
            },
        },
        "limitations": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["headline", "summary", "findings", "training"],
}


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    if val:
        return val
    path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def available() -> bool:
    return bool(_env("GEMINI_API_KEY") or _env("FW_LLM_KEY"))


def generate(fact_sheet: dict, events: list[dict]) -> dict | None:
    key = _env("GEMINI_API_KEY") or _env("FW_LLM_KEY")
    if not key:
        return None
    model = _env("FW_LLM_MODEL") or "gemini-2.5-flash"
    prompt = (
        "You are an elite football performance analyst. Analyse ONLY the structured data below. "
        "Never invent numbers, players, events or timestamps. If the sample is short, say so. "
        "Every finding must reference at least one timestamp from the events list. "
        "Write for a coach: specific, tactical, actionable, no clichés. "
        "Return JSON matching the schema.\n\n"
        f"EVENTS (ts = seconds):\n{json.dumps(events[:40], ensure_ascii=False)}\n\n"
        f"MATCH DATA:\n{json.dumps(fact_sheet, ensure_ascii=False)}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.25,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            payload = json.loads(r.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)
        return _verify(data, events)
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError):
        return None


def _verify(report: dict, events: list[dict]) -> dict:
    stamps = [e["t"] for e in events]
    for f in report.get("findings", []):
        kept = []
        for ev in f.get("evidence", []) or []:
            ts = float(ev.get("ts", -99))
            if any(abs(ts - s) <= 2.0 for s in stamps):
                kept.append(ev)
        f["evidence"] = kept
        f["grounded"] = bool(kept)
    report["engine"] = "gemini"
    return report

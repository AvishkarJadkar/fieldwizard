"""FieldWizard analysis pipeline.

Importing this package loads ``.env`` from the repository root once, so the API,
the CLI runner and the standalone scripts all see the same configuration.
Real environment variables always win over the file.
"""
from __future__ import annotations

import os


def load_env(path: str | None = None) -> None:
    """Minimal .env reader (KEY=VALUE, # comments, optional quotes).

    Deliberately dependency-free and non-destructive: it never overwrites a
    variable that is already set in the process environment.
    """
    if path is None:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = f.readlines()
    except OSError:
        return

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


load_env()

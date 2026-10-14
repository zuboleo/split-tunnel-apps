from __future__ import annotations

import json
from pathlib import Path


def load_seed(path: Path) -> dict[str, dict]:
    """Load the small trusted bootstrap set keyed by Android package ID."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    seed: dict[str, dict] = {}
    for app in raw.get("apps", []):
        package_id = (app.get("package_id") or "").strip()
        if not package_id:
            continue
        seed[package_id] = {
            "names": list(app.get("names") or []),
            "first_seen": app.get("first_seen"),
            "last_seen": app.get("last_seen"),
            "source_domains": list(app.get("source_domains") or []),
            "evidence_count": int(app.get("evidence_count") or 1),
        }
    return seed

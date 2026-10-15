from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from .evidence_engine import analyze_review, analyze_text
from .models import Evidence


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)


def _normalized_snippet(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _observation_fingerprint(row: dict) -> str:
    payload = "\n".join(
        [
            str(row.get("package_id") or ""),
            str(row.get("source_type") or ""),
            str(row.get("source_id") or ""),
            str(row.get("url") or ""),
            _normalized_snippet(row.get("snippet")),
        ]
    )
    return sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def _merge_observation(previous: dict, current: dict) -> dict:
    merged = dict(previous)
    for key, value in current.items():
        if value not in (None, "", [], {}):
            merged[key] = value

    old_name = previous.get("app_name")
    new_name = current.get("app_name")
    if old_name and (not new_name or new_name == current.get("package_id")):
        merged["app_name"] = old_name

    dates = [x for x in (previous.get("discovered_at"), current.get("discovered_at")) if x]
    if dates:
        merged["discovered_at"] = min(dates)
    return merged


def _reanalyze_row(row: dict) -> dict:
    """Persisted text is re-run through the current shared route engine."""
    updated = dict(row)
    snippet = str(updated.get("snippet") or "").strip()
    if not snippet:
        return updated

    app_name = updated.get("app_name") or updated.get("title")
    source_type = str(updated.get("source_type") or "")
    query = str(updated.get("query") or "")

    marker = "\nDeveloper reply: "
    if marker in snippet:
        review_text, developer_reply = snippet.split(marker, 1)
        classification = analyze_review(review_text, developer_reply, app_name=app_name)
    elif source_type == "article":
        classification = analyze_text(snippet, role="article", app_name=app_name)
    elif "indexed" in query:
        classification = analyze_text(snippet, role="search_snippet", app_name=app_name)
    else:
        classification = analyze_text(snippet, role="user_review", app_name=app_name)

    updated["score"] = classification.score
    updated["strong_matches"] = classification.strong_matches
    updated["weak_matches"] = classification.weak_matches
    updated["negative_matches"] = classification.negative_matches
    updated["verdict"] = classification.verdict
    updated["confidence"] = classification.confidence
    updated["route"] = classification.route
    updated["condition"] = classification.condition
    updated["effect"] = classification.effect
    updated["fingerprint"] = _observation_fingerprint(updated)
    return updated


def merge_evidence(path: Path, new_items: list[Evidence]) -> list[dict]:
    existing = load_json(path, [])
    by_observation: dict[str, dict] = {}

    for row in [*existing, *(item.to_dict() for item in new_items)]:
        key = _observation_fingerprint(row)
        current = dict(row)
        current["fingerprint"] = key
        if key in by_observation:
            by_observation[key] = _merge_observation(by_observation[key], current)
        else:
            by_observation[key] = current

    rows = [_reanalyze_row(row) for row in by_observation.values()]
    rows.sort(key=lambda x: (x.get("discovered_at", ""), x.get("package_id") or "", x.get("url") or ""))
    save_json(path, rows)
    return rows


def load_id_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    raw = path.read_text(encoding="utf-8")
    return {
        item.strip()
        for item in raw.replace("\n", ",").split(",")
        if item.strip() and not item.strip().startswith("#")
    }


def _row_route(row: dict) -> str:
    route = str(row.get("route") or "").lower()
    if route in {"direct", "proxy", "neutral", "uncertain"}:
        return route

    verdict = str(row.get("verdict") or "").lower()
    if verdict == "positive":
        return "direct"
    if verdict == "negative":
        return "proxy"
    return verdict if verdict in {"neutral", "uncertain"} else "uncertain"


def _row_confidence(row: dict) -> float:
    try:
        return max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _source_weight(row: dict) -> float:
    if row.get("source_type") == "store":
        return 0.94 if "indexed" in str(row.get("query") or "") else 1.0
    if row.get("source_type") == "article":
        return 0.90
    return 0.82


def _content_key(row: dict) -> str:
    text = _normalized_snippet(row.get("snippet"))
    if not text:
        return ""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^0-9a-zа-яё]+", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _aggregate(rows: list[dict]) -> float:
    if not rows:
        return 0.0

    counts: defaultdict[str, int] = defaultdict(int)
    seen_content: set[str] = set()
    combined = 0.0

    for row in sorted(rows, key=_row_confidence, reverse=True):
        content_key = _content_key(row)
        if content_key and content_key in seen_content:
            continue
        if content_key:
            seen_content.add(content_key)

        domain = str(row.get("source_domain") or row.get("source_id") or "unknown")
        occurrence = counts[domain]
        counts[domain] += 1
        repeat_weight = (1.0, 0.72, 0.50, 0.35)[min(occurrence, 3)]
        confidence = _row_confidence(row) * _source_weight(row) * repeat_weight
        combined = 1.0 - (1.0 - combined) * (1.0 - confidence)

    return round(max(0.0, min(1.0, combined)), 3)


def _empty_app(package_id: str, now: str) -> dict:
    return {
        "package_id": package_id,
        "names": [],
        "first_seen": now,
        "last_seen": now,
        "source_domains": [],
        "stores": [],
        "evidence_count": 0,
        "direct_evidence_count": 0,
        "proxy_evidence_count": 0,
        "direct_confidence": 0.0,
        "proxy_confidence": 0.0,
        "positive_evidence_count": 0,
        "negative_evidence_count": 0,
        "positive_confidence": 0.0,
        "negative_confidence": 0.0,
        "route": "uncertain",
        "status": "candidate",
        "reason": "insufficient_evidence",
        "_direct_rows": [],
        "_proxy_rows": [],
    }


def build_apps(
    evidence_rows: list[dict],
    seed: dict[str, dict],
    allowlist: set[str],
    denylist: set[str],
    proxy_allowlist: set[str] | None = None,
) -> dict:
    now = utcnow_iso()
    proxy_allowlist = proxy_allowlist or set()
    apps: dict[str, dict] = {}

    # The historical seed contains applications known to dislike/detect VPN, so
    # its semantic route is DIRECT.
    for package_id, seed_item in seed.items():
        if package_id in denylist:
            continue
        apps[package_id] = {
            **_empty_app(package_id, now),
            "names": sorted(set(seed_item.get("names", []))),
            "first_seen": seed_item.get("first_seen") or now,
            "last_seen": seed_item.get("last_seen") or now,
            "source_domains": sorted(set(seed_item.get("source_domains", []))),
            "evidence_count": int(seed_item.get("evidence_count", 1)),
            "direct_confidence": 1.0,
            "positive_confidence": 1.0,
            "route": "direct",
            "status": "confirmed",
            "reason": "seed",
        }

    # Explicit PROXY overrides also work without scraped evidence. This is useful
    # for a small verified baseline and for correcting a noisy source quickly.
    for package_id in proxy_allowlist:
        if package_id in denylist or package_id in apps:
            continue
        apps[package_id] = _empty_app(package_id, now)

    for row in evidence_rows:
        package_id = row.get("package_id")
        if not package_id or package_id in denylist:
            continue

        item = apps.setdefault(package_id, _empty_app(package_id, row.get("discovered_at") or now))

        if row.get("app_name"):
            item["names"] = sorted(set(item["names"]) | {row["app_name"]})
        if row.get("source_domain"):
            item["source_domains"] = sorted(set(item["source_domains"]) | {row["source_domain"]})
        if row.get("store"):
            item["stores"] = sorted(set(item["stores"]) | {row["store"]})

        item["evidence_count"] += 1
        item["last_seen"] = max(item.get("last_seen") or "", row.get("discovered_at") or "")

        route = _row_route(row)
        if route == "direct":
            item["_direct_rows"].append(row)
            item["direct_evidence_count"] += 1
        elif route == "proxy":
            item["_proxy_rows"].append(row)
            item["proxy_evidence_count"] += 1

    for package_id, item in apps.items():
        if item.get("reason") == "seed":
            item.pop("_direct_rows", None)
            item.pop("_proxy_rows", None)
            continue

        direct = _aggregate(item.pop("_direct_rows", []))
        proxy = _aggregate(item.pop("_proxy_rows", []))

        item["direct_confidence"] = direct
        item["proxy_confidence"] = proxy
        item["positive_evidence_count"] = item["direct_evidence_count"]
        item["negative_evidence_count"] = item["proxy_evidence_count"]
        item["positive_confidence"] = direct
        item["negative_confidence"] = proxy

        # Manual route files are explicit overrides. denylist remains the highest
        # priority because such packages never reach this point.
        if package_id in proxy_allowlist:
            item["route"] = "proxy"
            item["status"] = "confirmed"
            item["reason"] = "proxy_allowlist"
            continue
        if package_id in allowlist:
            item["route"] = "direct"
            item["status"] = "confirmed"
            item["reason"] = "allowlist"
            continue

        strongest = max(direct, proxy)
        delta = abs(direct - proxy)

        if strongest >= 0.80 and delta >= 0.15:
            item["route"] = "direct" if direct > proxy else "proxy"
            item["status"] = "confirmed"
            item["reason"] = "route_confidence"
        elif strongest >= 0.50:
            item["route"] = "uncertain" if delta < 0.15 else ("direct" if direct > proxy else "proxy")
            item["status"] = "candidate"
            item["reason"] = "route_conflict" if delta < 0.15 else "needs_more_confidence"
        else:
            item["route"] = "uncertain"
            item["status"] = "candidate"
            item["reason"] = "insufficient_evidence"

    ordered = sorted(
        apps.values(),
        key=lambda item: (
            item["status"] != "confirmed",
            item.get("route") or "uncertain",
            item["package_id"],
        ),
    )
    return {"updated_at": now, "apps": ordered}


def _write_id_file(path: Path, package_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(package_ids) + ("\n" if package_ids else ""), encoding="utf-8")


def write_outputs(dataset: dict, data_file: Path, public_file: Path, status_file: Path) -> None:
    apps = dataset.get("apps", [])
    direct = sorted(
        app["package_id"]
        for app in apps
        if app.get("status") == "confirmed" and app.get("route") == "direct"
    )
    proxy = sorted(
        app["package_id"]
        for app in apps
        if app.get("status") == "confirmed" and app.get("route") == "proxy"
    )

    # Legacy app_ids.txt remains the DIRECT list so existing consumers do not
    # silently invert their routing. New installations should use proxy_apps.txt
    # with DIRECT as the default route.
    _write_id_file(data_file, direct)
    _write_id_file(public_file, direct)
    _write_id_file(data_file.with_name("direct_apps.txt"), direct)
    _write_id_file(public_file.with_name("direct_apps.txt"), direct)
    _write_id_file(data_file.with_name("proxy_apps.txt"), proxy)
    _write_id_file(public_file.with_name("proxy_apps.txt"), proxy)

    save_json(
        status_file,
        {
            "updated_at": dataset.get("updated_at"),
            "confirmed_count": len(direct) + len(proxy),
            "direct_count": len(direct),
            "proxy_count": len(proxy),
            "candidate_count": sum(1 for app in apps if app.get("status") == "candidate"),
            "rejected_count": 0,
            "legacy_file": "app_ids.txt",
            "direct_file": "direct_apps.txt",
            "proxy_file": "proxy_apps.txt",
        },
    )

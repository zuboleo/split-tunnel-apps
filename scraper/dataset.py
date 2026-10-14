from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from .evidence_engine import analyze_review, analyze_text
from .models import Evidence


_EXPLICIT_MATCHES = {
    "false_vpn_detection_ru",
    "requires_disable_vpn_ru",
    "vpn_detected_ru",
    "vpn_allergy_ru",
    "blocked_with_vpn_ru",
    "vpn_blocks_access_ru",
    "false_vpn_detection_en",
    "requires_disable_vpn_en",
    "vpn_detected_en",
    "blocked_with_vpn_en",
    "vpn_blocks_access_en",
    "detected_vpn_ru",
    "access_blocked_vpn_ru",
}


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
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    return text


def _observation_fingerprint(row: dict) -> str:
    """Stable identity for one observation, independent of parser metadata.

    Direct scan and deep recheck can see the exact same store review with a
    different app title/name. Those are one observation and must not increase
    confidence twice.
    """
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

    # Keep useful human metadata when a later deep recheck only knows package ID.
    old_name = previous.get("app_name")
    new_name = current.get("app_name")
    if old_name and (not new_name or new_name == current.get("package_id")):
        merged["app_name"] = old_name

    dates = [x for x in (previous.get("discovered_at"), current.get("discovered_at")) if x]
    if dates:
        merged["discovered_at"] = min(dates)
    return merged


def _reanalyze_row(row: dict) -> dict:
    """Run persisted evidence through today's shared semantic engine.

    Evidence is data, not a frozen classifier decision. A core fix therefore
    cleans yesterday's false positives without waiting for the same review to
    be rediscovered.
    """
    updated = dict(row)
    snippet = str(updated.get("snippet") or "").strip()
    if not snippet:
        return updated

    app_name = updated.get("app_name") or updated.get("title")
    source_type = str(updated.get("source_type") or "")
    query = str(updated.get("query") or "")
    was_legacy = "verdict" not in updated or "confidence" not in updated

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

    confidence = classification.confidence
    # Legacy rows sometimes joined a user review and generic support advice
    # without preserving roles. Weak legacy positives should not decide an app.
    if was_legacy and confidence < 0.90:
        confidence = min(confidence, 0.55)

    updated["score"] = int(round(confidence * 10))
    updated["strong_matches"] = classification.strong_matches
    updated["weak_matches"] = classification.weak_matches
    updated["negative_matches"] = classification.negative_matches
    updated["verdict"] = classification.verdict
    updated["confidence"] = round(confidence, 3)
    updated["fingerprint"] = _observation_fingerprint(updated)
    return updated


def merge_evidence(path: Path, new_items: list[Evidence]) -> list[dict]:
    existing = load_json(path, [])
    by_observation: dict[str, dict] = {}

    # Existing rows go first; current scan can refresh their metadata. Identity
    # deliberately ignores app_name/title/query so the same review from direct
    # scan and deep recheck is counted once.
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
    return {x.strip() for x in raw.replace("\n", ",").split(",") if x.strip() and not x.strip().startswith("#")}


def _row_verdict(row: dict) -> str:
    verdict = str(row.get("verdict") or "").lower()
    if verdict in {"positive", "negative", "uncertain", "neutral"}:
        return verdict
    if row.get("strong_matches") or int(row.get("score") or 0) >= 3:
        return "positive"
    return "uncertain"


def _row_confidence(row: dict) -> float:
    raw = row.get("confidence")
    if raw is not None:
        try:
            value = float(raw)
            if value > 0:
                return max(0.0, min(1.0, value))
        except (TypeError, ValueError):
            pass

    strong = set(row.get("strong_matches") or [])
    if strong & _EXPLICIT_MATCHES:
        return 0.92
    if len(strong) >= 2:
        return 0.86
    if strong:
        return 0.66
    score = int(row.get("score") or 0)
    return min(0.72, 0.38 + score * 0.06) if score else 0.0


def _source_weight(row: dict) -> float:
    if row.get("source_type") == "store":
        if "indexed" in str(row.get("query") or ""):
            return 0.94
        return 1.0
    if row.get("source_type") == "article":
        return 0.90
    return 0.82


def _content_key(row: dict) -> str:
    """Collapse exact syndicated copies even when they live on other domains."""
    text = _normalized_snippet(row.get("snippet"))
    if not text:
        return ""
    # Remove obvious site/app decoration but retain semantic wording.
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
        # Multiple distinct reviews from one store matter, but less than a new
        # independent source. Repeated copies on one domain rapidly diminish.
        repeat_weight = (1.0, 0.72, 0.50, 0.35)[min(occurrence, 3)]
        confidence = _row_confidence(row) * _source_weight(row) * repeat_weight
        combined = 1.0 - (1.0 - combined) * (1.0 - confidence)
    return round(max(0.0, min(1.0, combined)), 3)


def build_apps(
    evidence_rows: list[dict],
    seed: dict[str, dict],
    allowlist: set[str],
    denylist: set[str],
) -> dict:
    now = utcnow_iso()
    apps: dict[str, dict] = {}

    for package_id, seed_item in seed.items():
        if package_id in denylist:
            continue
        apps[package_id] = {
            "package_id": package_id,
            "names": sorted(set(seed_item.get("names", []))),
            "first_seen": seed_item.get("first_seen") or now,
            "last_seen": seed_item.get("last_seen") or now,
            "source_domains": sorted(set(seed_item.get("source_domains", []))),
            "stores": [],
            "evidence_count": int(seed_item.get("evidence_count", 1)),
            "positive_evidence_count": 0,
            "negative_evidence_count": 0,
            "positive_confidence": 1.0,
            "negative_confidence": 0.0,
            "direct_store_evidence": False,
            "direct_store_evidence_count": 0,
            "status": "confirmed",
            "reason": "seed",
            "_positive_rows": [],
            "_negative_rows": [],
            "_store_fingerprints": set(),
        }

    for row in evidence_rows:
        package_id = row.get("package_id")
        if not package_id or package_id in denylist:
            continue
        item = apps.setdefault(
            package_id,
            {
                "package_id": package_id,
                "names": [],
                "first_seen": row.get("discovered_at") or now,
                "last_seen": row.get("discovered_at") or now,
                "source_domains": [],
                "stores": [],
                "evidence_count": 0,
                "positive_evidence_count": 0,
                "negative_evidence_count": 0,
                "positive_confidence": 0.0,
                "negative_confidence": 0.0,
                "direct_store_evidence": False,
                "direct_store_evidence_count": 0,
                "status": "candidate",
                "reason": "insufficient_evidence",
                "_positive_rows": [],
                "_negative_rows": [],
                "_store_fingerprints": set(),
            },
        )
        if row.get("app_name"):
            item["names"] = sorted(set(item["names"]) | {row["app_name"]})
        if row.get("source_domain"):
            item["source_domains"] = sorted(set(item["source_domains"]) | {row["source_domain"]})
        if row.get("store"):
            item["stores"] = sorted(set(item["stores"]) | {row["store"]})
        item["evidence_count"] += 1
        item["last_seen"] = max(item.get("last_seen") or "", row.get("discovered_at") or "")

        verdict = _row_verdict(row)
        if verdict == "positive":
            item["_positive_rows"].append(row)
            item["positive_evidence_count"] += 1
        elif verdict == "negative":
            item["_negative_rows"].append(row)
            item["negative_evidence_count"] += 1

        if row.get("source_type") == "store" and verdict in {"positive", "negative"}:
            item["direct_store_evidence"] = True
            fp = row.get("fingerprint") or "|".join(
                str(row.get(key) or "") for key in ("source_id", "url", "snippet", "discovered_at", "verdict")
            )
            item["_store_fingerprints"].add(fp)

    for package_id, item in apps.items():
        if item.get("reason") == "seed":
            item.pop("_positive_rows", None)
            item.pop("_negative_rows", None)
            item.pop("_store_fingerprints", None)
            continue

        positive_rows = item.pop("_positive_rows", [])
        negative_rows = item.pop("_negative_rows", [])
        item["direct_store_evidence_count"] = len(item.pop("_store_fingerprints", set()))
        positive = _aggregate(positive_rows)
        negative = _aggregate(negative_rows)
        item["positive_confidence"] = positive
        item["negative_confidence"] = negative

        if package_id in allowlist:
            item["status"] = "confirmed"
            item["reason"] = "allowlist"
        elif negative >= 0.80 and negative >= positive + 0.12:
            item["status"] = "rejected"
            item["reason"] = "counterevidence"
        elif positive >= 0.80 and positive >= negative + 0.15:
            item["status"] = "confirmed"
            item["reason"] = "evidence_confidence"
        elif positive >= 0.50:
            item["status"] = "candidate"
            item["reason"] = "needs_more_confidence"
        elif negative >= 0.55:
            item["status"] = "rejected"
            item["reason"] = "leans_against_blocking"
        else:
            item["status"] = "candidate"
            item["reason"] = "insufficient_evidence"

    ordered = sorted(
        apps.values(),
        key=lambda x: (
            x["status"] != "confirmed",
            x["status"] == "rejected",
            x["package_id"],
        ),
    )
    return {"updated_at": now, "apps": ordered}


def write_outputs(dataset: dict, data_file: Path, public_file: Path, status_file: Path) -> None:
    apps = dataset.get("apps", [])
    confirmed = sorted(a["package_id"] for a in apps if a.get("status") == "confirmed")
    content = ",".join(confirmed) + ("\n" if confirmed else "")
    data_file.parent.mkdir(parents=True, exist_ok=True)
    public_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text(content, encoding="utf-8")
    public_file.write_text(content, encoding="utf-8")
    save_json(
        status_file,
        {
            "updated_at": dataset.get("updated_at"),
            "confirmed_count": len(confirmed),
            "candidate_count": sum(1 for a in apps if a.get("status") == "candidate"),
            "rejected_count": sum(1 for a in apps if a.get("status") == "rejected"),
            "file": "app_ids.txt",
        },
    )

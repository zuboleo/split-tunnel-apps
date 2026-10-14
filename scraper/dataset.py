from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Evidence


_EXPLICIT_MATCHES = {
    "false_vpn_detection_ru",
    "requires_disable_vpn_ru",
    "vpn_detected_ru",
    "blocked_with_vpn_ru",
    "vpn_blocks_access_ru",
    "false_vpn_detection_en",
    "requires_disable_vpn_en",
    "vpn_detected_en",
    "blocked_with_vpn_en",
    # Backward compatibility with evidence produced before the shared engine.
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


def merge_evidence(path: Path, new_items: list[Evidence]) -> list[dict]:
    existing = load_json(path, [])
    by_fp = {row.get("fingerprint"): row for row in existing if row.get("fingerprint")}
    for item in new_items:
        row = item.to_dict()
        # New schema-aware observations replace an older row with the same
        # stable fingerprint, upgrading it with verdict/confidence fields.
        by_fp[row["fingerprint"]] = row
    rows = list(by_fp.values())
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
    # Old rows had only score/strong_matches and represented positive evidence.
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

    # Migrate old evidence conservatively. Explicit block/detection stays strong;
    # a generic "disable VPN" mention becomes moderate rather than definitive.
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


def _aggregate(rows: list[dict]) -> float:
    """Combine observations without pretending repeated copies are independent."""
    if not rows:
        return 0.0
    counts: defaultdict[str, int] = defaultdict(int)
    combined = 0.0
    for row in sorted(rows, key=_row_confidence, reverse=True):
        domain = str(row.get("source_domain") or row.get("source_id") or "unknown")
        occurrence = counts[domain]
        counts[domain] += 1
        # Multiple distinct reviews from one store matter, but less than a new
        # independent domain. This also stops syndicated duplicates exploding.
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

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Evidence


# A single store review is enough only when it explicitly says that VPN was
# detected/blocked. Generic troubleshooting advice such as "disable VPN" stays
# a candidate until it is corroborated by another independent observation.
EXPLICIT_BLOCK_MATCHES = {
    "vpn_detected_ru",
    "detected_vpn_ru",
    "vpn_blocks_access_ru",
    "access_blocked_vpn_ru",
    "vpn_detected_en",
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
        fp = row["fingerprint"]
        if fp not in by_fp:
            by_fp[fp] = row
    rows = list(by_fp.values())
    rows.sort(key=lambda x: (x.get("discovered_at", ""), x.get("package_id") or "", x.get("url") or ""))
    save_json(path, rows)
    return rows


def load_id_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    raw = path.read_text(encoding="utf-8")
    return {x.strip() for x in raw.replace("\n", ",").split(",") if x.strip() and not x.strip().startswith("#")}


def _is_explicit_store_evidence(row: dict) -> bool:
    if row.get("source_type") != "store" or int(row.get("score") or 0) < 3:
        return False
    strong = set(row.get("strong_matches") or [])
    return bool(strong & EXPLICIT_BLOCK_MATCHES) or len(strong) >= 2


def build_apps(
    evidence_rows: list[dict],
    seed: dict[str, dict],
    allowlist: set[str],
    denylist: set[str],
) -> dict:
    now = utcnow_iso()
    apps: dict[str, dict] = {}

    # Seed contains the small trusted bootstrap set.
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
            "direct_store_evidence": False,
            "direct_store_evidence_count": 0,
            "explicit_store_evidence": False,
            "status": "confirmed",
            "reason": "seed",
            "_store_evidence_fingerprints": set(),
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
                "direct_store_evidence": False,
                "direct_store_evidence_count": 0,
                "explicit_store_evidence": False,
                "status": "candidate",
                "reason": "single_source",
                "_store_evidence_fingerprints": set(),
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

        if row.get("source_type") == "store" and int(row.get("score") or 0) >= 3:
            item["direct_store_evidence"] = True
            fingerprint = row.get("fingerprint") or "|".join(
                str(row.get(key) or "") for key in ("source_id", "url", "snippet", "discovered_at")
            )
            item["_store_evidence_fingerprints"].add(fingerprint)
            if _is_explicit_store_evidence(row):
                item["explicit_store_evidence"] = True

    for package_id, item in apps.items():
        item["direct_store_evidence_count"] = len(item.pop("_store_evidence_fingerprints", set()))

        if package_id in allowlist:
            item["status"] = "confirmed"
            item["reason"] = "allowlist"
        elif item.get("status") == "confirmed":
            pass
        elif item.get("explicit_store_evidence"):
            item["status"] = "confirmed"
            item["reason"] = "explicit_store_evidence"
        elif item.get("direct_store_evidence_count", 0) >= 2:
            item["status"] = "confirmed"
            item["reason"] = "multiple_store_evidence"
        elif len(set(item.get("source_domains", []))) >= 2:
            item["status"] = "confirmed"
            item["reason"] = "two_independent_domains"
        else:
            item["status"] = "candidate"
            item["reason"] = "needs_corroboration"

    ordered = sorted(apps.values(), key=lambda x: (x["status"] != "confirmed", x["package_id"]))
    return {"updated_at": now, "apps": ordered}


def write_outputs(dataset: dict, data_file: Path, public_file: Path, status_file: Path) -> None:
    confirmed = sorted(a["package_id"] for a in dataset.get("apps", []) if a.get("status") == "confirmed")
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
            "candidate_count": sum(1 for a in dataset.get("apps", []) if a.get("status") == "candidate"),
            "file": "app_ids.txt",
        },
    )

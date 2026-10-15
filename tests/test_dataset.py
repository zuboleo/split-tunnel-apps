from pathlib import Path

from scraper.dataset import build_apps, merge_evidence, write_outputs
from scraper.models import Evidence


def row(
    *,
    confidence: float,
    route: str = "direct",
    fingerprint: str = "one",
    domain: str = "play.google.com",
    source_type: str = "store",
    discovered_at: str = "2026-10-14T00:00:00+00:00",
    snippet: str | None = None,
) -> dict:
    verdict = "positive" if route == "direct" else "negative" if route == "proxy" else route
    return {
        "package_id": "ru.dns.shop.android",
        "app_name": "DNS SHOP",
        "source_type": source_type,
        "source_id": "test",
        "source_domain": domain,
        "url": f"https://{domain}/item",
        "store": "google_play" if source_type == "store" else None,
        "snippet": snippet or f"evidence {fingerprint}",
        "score": round(confidence * 10),
        "strong_matches": ["fails_with_vpn"] if route == "direct" and confidence >= 0.8 else [],
        "negative_matches": ["fails_without_vpn"] if route == "proxy" and confidence >= 0.8 else [],
        "verdict": verdict,
        "route": route,
        "confidence": confidence,
        "fingerprint": fingerprint,
        "discovered_at": discovered_at,
    }


def test_single_moderate_observation_stays_candidate() -> None:
    ds = build_apps([row(confidence=0.54)], {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "candidate"
    assert app["route"] == "direct"


def test_single_clear_direct_observation_can_confirm() -> None:
    ds = build_apps([row(confidence=0.96, route="direct")], {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "confirmed"
    assert app["route"] == "direct"
    assert app["direct_confidence"] >= 0.9


def test_single_clear_proxy_observation_can_confirm() -> None:
    ds = build_apps([row(confidence=0.97, route="proxy")], {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "confirmed"
    assert app["route"] == "proxy"
    assert app["proxy_confidence"] >= 0.9


def test_proxy_allowlist_can_force_known_app_without_evidence() -> None:
    ds = build_apps([], {}, set(), set(), proxy_allowlist={"com.google.android.youtube"})
    app = ds["apps"][0]
    assert app["package_id"] == "com.google.android.youtube"
    assert app["status"] == "confirmed"
    assert app["route"] == "proxy"
    assert app["reason"] == "proxy_allowlist"


def test_proxy_allowlist_overrides_conflicting_scraped_route() -> None:
    evidence = [row(confidence=0.96, route="direct")]
    evidence[0]["package_id"] = "com.google.android.youtube"
    ds = build_apps(
        evidence,
        {},
        set(),
        set(),
        proxy_allowlist={"com.google.android.youtube"},
    )
    app = ds["apps"][0]
    assert app["route"] == "proxy"
    assert app["status"] == "confirmed"


def test_two_moderate_reviews_from_same_store_can_confirm() -> None:
    rows = [
        row(confidence=0.66, fingerprint="one", snippet="review one"),
        row(
            confidence=0.66,
            fingerprint="two",
            snippet="review two",
            discovered_at="2026-10-14T01:00:00+00:00",
        ),
    ]
    ds = build_apps(rows, {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "confirmed"
    assert app["direct_evidence_count"] == 2


def test_conflicting_routes_stay_candidate() -> None:
    rows = [
        row(confidence=0.92, route="direct", fingerprint="direct", snippet="direct evidence"),
        row(confidence=0.90, route="proxy", fingerprint="proxy", snippet="proxy evidence"),
    ]
    ds = build_apps(rows, {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "candidate"
    assert app["route"] == "uncertain"
    assert app["reason"] == "route_conflict"


def test_syndicated_exact_copy_does_not_count_twice() -> None:
    rows = [
        row(
            confidence=0.62,
            source_type="article",
            domain="one.example",
            fingerprint="one",
            snippet="same syndicated text about vpn",
        ),
        row(
            confidence=0.62,
            source_type="article",
            domain="two.example",
            fingerprint="two",
            snippet="same syndicated text about vpn",
        ),
    ]
    ds = build_apps(rows, {}, set(), set())
    assert ds["apps"][0]["status"] == "candidate"


def test_seed_is_direct() -> None:
    seed = {
        "ru.dns.shop.android": {
            "names": ["DNS SHOP"],
            "first_seen": "2026-05-18",
            "source_domains": ["example.com"],
        }
    }
    ds = build_apps([], seed, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "confirmed"
    assert app["route"] == "direct"


def test_merge_evidence_reanalyzes_same_review_and_deduplicates(tmp_path) -> None:
    path = tmp_path / "evidence.json"
    first = Evidence(
        package_id="ru.dns.shop.android",
        app_name="DNS SHOP",
        source_type="store",
        source_id="google_play_reviews",
        source_domain="play.google.com",
        url="https://play.google.com/store/apps/details?id=ru.dns.shop.android",
        title="DNS SHOP",
        snippet="Приложение требует отключить VPN, но он выключен",
        score=10,
        strong_matches=[],
        discovered_at="2026-10-14T00:00:00+00:00",
        store="google_play",
        query="direct_store_scan",
    )
    second = Evidence(
        package_id="ru.dns.shop.android",
        app_name=None,
        source_type="store",
        source_id="google_play_reviews",
        source_domain="play.google.com",
        url="https://play.google.com/store/apps/details?id=ru.dns.shop.android",
        title="ru.dns.shop.android",
        snippet="Приложение требует отключить VPN, но он выключен",
        score=10,
        strong_matches=[],
        discovered_at="2026-10-14T01:00:00+00:00",
        store="google_play",
        query="deep_review_recheck",
    )

    rows = merge_evidence(path, [first, second])
    assert len(rows) == 1
    assert rows[0]["app_name"] == "DNS SHOP"
    assert rows[0]["route"] == "direct"
    assert rows[0]["confidence"] >= 0.95


def test_outputs_keep_legacy_direct_and_add_proxy_file(tmp_path) -> None:
    dataset = {
        "updated_at": "2026-10-15T00:00:00+00:00",
        "apps": [
            {"package_id": "ru.direct", "status": "confirmed", "route": "direct"},
            {"package_id": "com.google.android.youtube", "status": "confirmed", "route": "proxy"},
        ],
    }
    data_file = tmp_path / "data" / "app_ids.txt"
    public_file = tmp_path / "public" / "app_ids.txt"
    status_file = tmp_path / "public" / "status.json"

    write_outputs(dataset, data_file, public_file, status_file)

    assert public_file.read_text(encoding="utf-8").strip() == "ru.direct"
    assert (tmp_path / "public" / "direct_apps.txt").read_text(encoding="utf-8").strip() == "ru.direct"
    assert (
        tmp_path / "public" / "proxy_apps.txt"
    ).read_text(encoding="utf-8").strip() == "com.google.android.youtube"

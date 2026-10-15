from scraper.dataset import build_apps, merge_evidence
from scraper.models import Evidence


def row(
    *,
    confidence: float,
    verdict: str = "positive",
    fingerprint: str = "one",
    domain: str = "play.google.com",
    source_type: str = "store",
    discovered_at: str = "2026-10-14T00:00:00+00:00",
    snippet: str | None = None,
) -> dict:
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
        "strong_matches": ["vpn_blocks_access_ru"] if confidence >= 0.8 else [],
        "negative_matches": ["requires_vpn_ru"] if verdict == "negative" else [],
        "verdict": verdict,
        "confidence": confidence,
        "fingerprint": fingerprint,
        "discovered_at": discovered_at,
    }


def test_single_moderate_store_observation_stays_candidate() -> None:
    ds = build_apps([row(confidence=0.54)], {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "candidate"
    assert app["reason"] == "needs_more_confidence"


def test_single_clear_observation_can_confirm() -> None:
    ds = build_apps([row(confidence=0.96)], {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "confirmed"
    assert app["reason"] == "evidence_confidence"
    assert app["positive_confidence"] >= 0.9


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
    assert app["positive_evidence_count"] == 2
    assert app["direct_store_evidence_count"] == 2


def test_one_article_is_only_candidate() -> None:
    ds = build_apps(
        [row(confidence=0.66, source_type="article", domain="example.com")],
        {},
        set(),
        set(),
    )
    assert ds["apps"][0]["status"] == "candidate"


def test_two_independent_articles_can_confirm() -> None:
    rows = [
        row(
            confidence=0.62,
            source_type="article",
            domain="one.example",
            fingerprint="one",
            snippet="first independent report",
        ),
        row(
            confidence=0.62,
            source_type="article",
            domain="two.example",
            fingerprint="two",
            snippet="second independent report",
            discovered_at="2026-10-14T01:00:00+00:00",
        ),
    ]
    ds = build_apps(rows, {}, set(), set())
    assert ds["apps"][0]["status"] == "confirmed"


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


def test_counterevidence_can_reject_weak_positive() -> None:
    rows = [
        row(confidence=0.60, verdict="positive", fingerprint="positive"),
        row(confidence=0.92, verdict="negative", fingerprint="negative"),
    ]
    ds = build_apps(rows, {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "rejected"
    assert app["reason"] == "counterevidence"
    assert app["negative_confidence"] > app["positive_confidence"]


def test_two_negative_observations_are_not_ignored() -> None:
    rows = [
        row(confidence=0.75, verdict="negative", fingerprint="n1", snippet="negative one"),
        row(
            confidence=0.75,
            verdict="negative",
            fingerprint="n2",
            snippet="negative two",
            discovered_at="2026-10-14T01:00:00+00:00",
        ),
    ]
    ds = build_apps(rows, {}, set(), set())
    app = ds["apps"][0]
    assert app["status"] == "rejected"
    assert app["negative_evidence_count"] == 2


def test_merge_evidence_deduplicates_same_review_from_two_scan_paths(tmp_path) -> None:
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
        strong_matches=["false_vpn_detection_ru"],
        discovered_at="2026-10-14T00:00:00+00:00",
        store="google_play",
        query="direct_store_scan",
        verdict="positive",
        confidence=0.99,
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
        strong_matches=["false_vpn_detection_ru"],
        discovered_at="2026-10-14T01:00:00+00:00",
        store="google_play",
        query="deep_review_recheck",
        verdict="positive",
        confidence=0.99,
    )

    rows = merge_evidence(path, [first, second])
    assert len(rows) == 1
    assert rows[0]["app_name"] == "DNS SHOP"
    assert rows[0]["verdict"] == "positive"

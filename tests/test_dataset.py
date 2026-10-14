from scraper.dataset import build_apps


def store_row(*, strong_matches: list[str], fingerprint: str, discovered_at: str = "2026-10-14T00:00:00+00:00") -> dict:
    return {
        "package_id": "ru.dns.shop.android",
        "app_name": "DNS SHOP",
        "source_type": "store",
        "source_id": "google_play_reviews",
        "source_domain": "play.google.com",
        "store": "google_play",
        "score": max(3, len(strong_matches) * 3),
        "strong_matches": strong_matches,
        "fingerprint": fingerprint,
        "discovered_at": discovered_at,
    }


def test_single_generic_store_evidence_stays_candidate() -> None:
    ds = build_apps(
        [store_row(strong_matches=["disable_vpn_ru"], fingerprint="one")],
        {},
        set(),
        set(),
    )
    assert ds["apps"][0]["status"] == "candidate"
    assert ds["apps"][0]["reason"] == "needs_corroboration"


def test_explicit_store_block_confirms() -> None:
    ds = build_apps(
        [store_row(strong_matches=["vpn_blocks_access_ru"], fingerprint="one")],
        {},
        set(),
        set(),
    )
    assert ds["apps"][0]["status"] == "confirmed"
    assert ds["apps"][0]["reason"] == "explicit_store_evidence"


def test_two_store_observations_confirm() -> None:
    rows = [
        store_row(strong_matches=["disable_vpn_ru"], fingerprint="one"),
        store_row(
            strong_matches=["disable_vpn_ru"],
            fingerprint="two",
            discovered_at="2026-10-14T01:00:00+00:00",
        ),
    ]
    ds = build_apps(rows, {}, set(), set())
    assert ds["apps"][0]["status"] == "confirmed"
    assert ds["apps"][0]["reason"] == "multiple_store_evidence"
    assert ds["apps"][0]["direct_store_evidence_count"] == 2


def test_one_article_is_only_candidate() -> None:
    rows = [{
        "package_id": "com.example.app",
        "app_name": "Example",
        "source_type": "article",
        "source_domain": "example.com",
        "store": None,
        "score": 3,
        "strong_matches": ["disable_vpn_ru"],
        "discovered_at": "2026-10-14T00:00:00+00:00",
    }]
    ds = build_apps(rows, {}, set(), set())
    assert ds["apps"][0]["status"] == "candidate"


def test_two_independent_article_domains_confirm() -> None:
    rows = [
        {
            "package_id": "com.example.app",
            "source_type": "article",
            "source_domain": "one.example",
            "score": 3,
            "strong_matches": ["disable_vpn_ru"],
            "discovered_at": "2026-10-14T00:00:00+00:00",
        },
        {
            "package_id": "com.example.app",
            "source_type": "article",
            "source_domain": "two.example",
            "score": 3,
            "strong_matches": ["disable_vpn_ru"],
            "discovered_at": "2026-10-14T01:00:00+00:00",
        },
    ]
    ds = build_apps(rows, {}, set(), set())
    assert ds["apps"][0]["status"] == "confirmed"
    assert ds["apps"][0]["reason"] == "two_independent_domains"

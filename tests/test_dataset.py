from scraper.dataset import build_apps


def test_direct_store_evidence_confirms() -> None:
    rows = [{
        "package_id": "ru.dns.shop.android",
        "app_name": "DNS SHOP",
        "source_type": "store",
        "source_domain": "play.google.com",
        "store": "google_play",
        "score": 3,
        "discovered_at": "2026-10-14T00:00:00+00:00",
    }]
    ds = build_apps(rows, {}, set(), set())
    assert ds["apps"][0]["status"] == "confirmed"


def test_one_article_is_only_candidate() -> None:
    rows = [{
        "package_id": "com.example.app",
        "app_name": "Example",
        "source_type": "article",
        "source_domain": "example.com",
        "store": None,
        "score": 3,
        "discovered_at": "2026-10-14T00:00:00+00:00",
    }]
    ds = build_apps(rows, {}, set(), set())
    assert ds["apps"][0]["status"] == "candidate"

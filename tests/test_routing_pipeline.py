import pytest

from scraper.main import (
    VERIFIED_DIRECT,
    VERIFIED_PROXY,
    ReviewReport,
    classify_reports,
    route_from_labels,
    select_reports,
)


class FakeClassifier:
    def __init__(self, labels: dict[str, dict[str, str] | Exception]):
        self.labels = labels

    def classify_reports(self, package_id: str, app_name: str | None, reports: list[dict[str, object]]) -> dict[str, str]:
        result = self.labels[package_id]
        if isinstance(result, Exception):
            raise result
        return result


def test_select_reports_balances_stores_and_limits_developer_only_reports() -> None:
    reports = [ReviewReport("google_play", (f"Google VPN context {i}",), ()) for i in range(10)]
    reports += [ReviewReport("rustore", (f"RuStore VPN context {i}",), ()) for i in range(4)]
    reports += [ReviewReport("google_play", (), (f"Developer VPN reply {i}",)) for i in range(5)]

    selected = select_reports(reports)

    assert len(selected) <= 10
    assert any(report.source == "google_play" for report in selected)
    assert any(report.source == "rustore" for report in selected)
    assert sum(not report.has_user_context for report in selected) <= 1


def test_multiple_sentences_in_one_review_stay_one_report() -> None:
    report = ReviewReport(
        "rustore",
        ("Без VPN не работает.", "С VPN работает."),
        ("Спасибо за отзыв.",),
    )
    payload = report.as_payload("r1")
    assert payload["report_id"] == "r1"
    assert payload["review"] == ["Без VPN не работает.", "С VPN работает."]


def test_one_strong_report_is_enough() -> None:
    assert route_from_labels({"r1": "DIRECT_STRONG"}) == "DIRECT"
    assert route_from_labels({"r1": "PROXY_STRONG"}) == "PROXY"


def test_two_independent_regular_reports_are_enough() -> None:
    assert route_from_labels({"r1": "DIRECT", "r2": "DIRECT"}) == "DIRECT"
    assert route_from_labels({"r1": "PROXY", "r2": "PROXY"}) == "PROXY"


def test_one_regular_report_is_not_enough() -> None:
    assert route_from_labels({"r1": "DIRECT"}) == "SKIP"
    assert route_from_labels({"r1": "PROXY"}) == "SKIP"


def test_conflicting_evidence_is_skipped() -> None:
    assert route_from_labels({"r1": "DIRECT_STRONG", "r2": "PROXY"}) == "SKIP"
    assert route_from_labels({"r1": "DIRECT", "r2": "PROXY"}) == "SKIP"


def test_noise_does_not_count() -> None:
    assert route_from_labels({"r1": "PROXY", "r2": "NOISE", "r3": "PROXY"}) == "PROXY"


def test_skip_never_enters_public_routes() -> None:
    reports = {
        "app.direct": [ReviewReport("rustore", ("Приложение требует отключить VPN",), ())],
        "app.proxy": [
            ReviewReport("rustore", ("Без VPN не работает, с VPN работает",), ()),
            ReviewReport("google_play", ("Только через VPN открывается",), ()),
        ],
        "app.noise": [ReviewReport("rustore", ("VPN не помог",), ())],
    }
    classifier = FakeClassifier(
        {
            "app.direct": {"r1": "DIRECT_STRONG"},
            "app.proxy": {"r1": "PROXY", "r2": "PROXY"},
            "app.noise": {"r1": "NOISE"},
        }
    )

    direct, proxy, skipped = classify_reports(classifier, {}, reports)

    assert "app.direct" in direct
    assert "app.proxy" in proxy
    assert "app.noise" not in direct | proxy
    assert skipped == 1


def test_verified_routes_are_always_published_without_model_call() -> None:
    verified_direct = next(iter(VERIFIED_DIRECT))
    verified_proxy = next(iter(VERIFIED_PROXY))
    reports = {
        verified_direct: [ReviewReport("rustore", ("VPN не влияет",), ())],
        verified_proxy: [ReviewReport("google_play", ("VPN не влияет",), ())],
    }
    classifier = FakeClassifier({})

    direct, proxy, skipped = classify_reports(classifier, {}, reports)

    assert verified_direct in direct
    assert verified_proxy in proxy
    assert skipped == 0


def test_classification_failure_aborts_instead_of_publishing_partial_result() -> None:
    reports = {
        "app.ok": [ReviewReport("rustore", ("В России доступ только через VPN",), ())],
        "app.fail": [ReviewReport("google_play", ("Приложение запрещает VPN",), ())],
    }
    classifier = FakeClassifier(
        {
            "app.fail": RuntimeError("API error"),
            "app.ok": {"r1": "PROXY_STRONG"},
        }
    )

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        classify_reports(classifier, {}, reports)

import pytest

from scraper.main import (
    ReviewReport,
    classify_reports,
    merge_unobserved_previous,
    select_reports,
)


class FakeClassifier:
    def __init__(self, routes: dict[str, str | Exception]):
        self.routes = routes

    def classify(self, package_id: str, app_name: str | None, reports: list[dict[str, object]]) -> str:
        result = self.routes[package_id]
        if isinstance(result, Exception):
            raise result
        return result


def test_select_reports_balances_stores_and_limits_developer_only_reports() -> None:
    reports = [
        ReviewReport("google_play", (f"Google VPN context {i}",), ())
        for i in range(10)
    ]
    reports += [
        ReviewReport("rustore", (f"RuStore VPN context {i}",), ())
        for i in range(4)
    ]
    reports += [
        ReviewReport("google_play", (), (f"Developer VPN reply {i}",))
        for i in range(5)
    ]

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
    assert payload["developer_reply"] == ["Спасибо за отзыв."]


def test_skip_never_enters_public_routes() -> None:
    reports = {
        "app.direct": [ReviewReport("rustore", ("Приложение требует отключить VPN",), ())],
        "app.proxy": [ReviewReport("rustore", ("Без VPN не работает, включил VPN — заработало",), ())],
        "app.noise": [ReviewReport("rustore", ("VPN не помог",), ())],
    }
    classifier = FakeClassifier(
        {
            "app.direct": "DIRECT",
            "app.proxy": "PROXY",
            "app.noise": "SKIP",
        }
    )

    direct, proxy, skipped = classify_reports(classifier, {}, reports)

    assert direct == {"app.direct"}
    assert proxy == {"app.proxy"}
    assert skipped == 1


def test_unobserved_previous_route_is_retained() -> None:
    reports = {
        "app.observed": [ReviewReport("rustore", ("VPN не влияет",), ())],
    }

    direct, proxy, retained = merge_unobserved_previous(
        set(),
        set(),
        reports,
        previous_direct={"app.known.direct", "app.observed"},
        previous_proxy={"app.known.proxy"},
    )

    assert direct == {"app.known.direct"}
    assert proxy == {"app.known.proxy"}
    assert retained == 2


def test_observed_skip_is_not_carried_forward() -> None:
    reports = {
        "app.old": [ReviewReport("rustore", ("VPN не помог",), ())],
    }

    direct, proxy, retained = merge_unobserved_previous(
        set(),
        set(),
        reports,
        previous_direct={"app.old"},
        previous_proxy=set(),
    )

    assert direct == set()
    assert proxy == set()
    assert retained == 0


def test_classification_failure_aborts_instead_of_publishing_partial_result() -> None:
    reports = {
        "app.ok": [ReviewReport("rustore", ("Без VPN не работает",), ())],
        "app.fail": [ReviewReport("google_play", ("С VPN не работает",), ())],
    }
    classifier = FakeClassifier(
        {
            "app.fail": RuntimeError("API error"),
            "app.ok": "PROXY",
        }
    )

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        classify_reports(classifier, {}, reports)

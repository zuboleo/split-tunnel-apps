import pytest

from scraper.main import ContextItem, classify_contexts, select_contexts


class FakeClassifier:
    def __init__(self, routes: dict[str, str | Exception]):
        self.routes = routes

    def classify(self, package_id: str, app_name: str | None, contexts: list[dict[str, str]]) -> str:
        result = self.routes[package_id]
        if isinstance(result, Exception):
            raise result
        return result


def test_select_contexts_balances_stores_and_limits_developer_replies() -> None:
    items = [
        ContextItem("google_play", "review", f"Google VPN context {i}")
        for i in range(10)
    ]
    items += [
        ContextItem("rustore", "review", f"RuStore VPN context {i}")
        for i in range(4)
    ]
    items += [
        ContextItem("google_play", "developer_reply", f"Developer VPN reply {i}")
        for i in range(5)
    ]

    selected = select_contexts(items)

    assert len(selected) <= 12
    assert any(item.source == "google_play" for item in selected)
    assert any(item.source == "rustore" for item in selected)
    assert sum(item.role == "developer_reply" for item in selected) <= 2


def test_skip_never_enters_public_routes() -> None:
    contexts = {
        "app.direct": [ContextItem("rustore", "review", "С VPN не работает")],
        "app.proxy": [ContextItem("rustore", "review", "Без VPN не работает")],
        "app.noise": [ContextItem("rustore", "review", "VPN не помог")],
    }
    classifier = FakeClassifier(
        {
            "app.direct": "DIRECT",
            "app.proxy": "PROXY",
            "app.noise": "SKIP",
        }
    )

    direct, proxy, skipped = classify_contexts(classifier, {}, contexts)

    assert direct == {"app.direct"}
    assert proxy == {"app.proxy"}
    assert skipped == 1


def test_classification_failure_aborts_instead_of_publishing_partial_result() -> None:
    contexts = {
        "app.ok": [ContextItem("rustore", "review", "Без VPN не работает")],
        "app.fail": [ContextItem("google_play", "review", "С VPN не работает")],
    }
    classifier = FakeClassifier(
        {
            "app.fail": RuntimeError("API error"),
            "app.ok": "PROXY",
        }
    )

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        classify_contexts(classifier, {}, contexts)

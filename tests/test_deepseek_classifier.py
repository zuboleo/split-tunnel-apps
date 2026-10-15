import pytest

from scraper.deepseek_classifier import DeepSeekClassifier


def test_parse_route() -> None:
    assert DeepSeekClassifier.parse_route("DIRECT") == "DIRECT"
    assert DeepSeekClassifier.parse_route("proxy") == "PROXY"


def test_parse_route_rejects_unknown_answer() -> None:
    with pytest.raises(ValueError):
        DeepSeekClassifier.parse_route("UNCERTAIN")

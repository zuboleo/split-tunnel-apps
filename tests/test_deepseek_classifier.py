import pytest

from scraper.deepseek_classifier import DeepSeekClassifier


def test_parse_labels() -> None:
    assert DeepSeekClassifier.parse_labels(
        '{"r1":"PROXY","r2":"NOISE","r3":"DIRECT_STRONG"}',
        ["r1", "r2", "r3"],
    ) == {
        "r1": "PROXY",
        "r2": "NOISE",
        "r3": "DIRECT_STRONG",
    }


def test_parse_labels_accepts_json_fence() -> None:
    assert DeepSeekClassifier.parse_labels(
        '```json\n{"r1":"PROXY_STRONG"}\n```',
        ["r1"],
    ) == {"r1": "PROXY_STRONG"}


def test_parse_labels_requires_exact_report_ids() -> None:
    with pytest.raises(ValueError):
        DeepSeekClassifier.parse_labels('{"r1":"PROXY"}', ["r1", "r2"])


def test_parse_labels_rejects_unknown_label() -> None:
    with pytest.raises(ValueError):
        DeepSeekClassifier.parse_labels('{"r1":"UNCERTAIN"}', ["r1"])

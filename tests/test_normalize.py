"""Tests for the normalizer."""

from pathlib import Path

import pytest

from scraper.normalize import Normalizer

ALIASES_PATH = Path(__file__).resolve().parent.parent / "scraper" / "aliases.yaml"


@pytest.fixture(scope="module")
def normalizer() -> Normalizer:
    return Normalizer(ALIASES_PATH)


def test_loads_apps(normalizer: Normalizer) -> None:
    assert len(normalizer.apps) > 0


def test_exact_match(normalizer: Normalizer) -> None:
    match = normalizer.match("Ozon")
    assert match is not None
    assert match.canonical == "Ozon"
    assert match.category == "marketplace"


def test_case_insensitive(normalizer: Normalizer) -> None:
    assert normalizer.match("OZON") is not None
    assert normalizer.match("ozon") is not None


def test_cyrillic_match(normalizer: Normalizer) -> None:
    match = normalizer.match("Озон")
    assert match is not None
    assert match.canonical == "Ozon"


def test_yo_e_equivalence(normalizer: Normalizer) -> None:
    """ё and е should be treated as the same letter."""
    assert normalizer.match("Пятёрочка") is not None
    assert normalizer.match("Пятерочка") is not None


def test_longest_match_wins(normalizer: Normalizer) -> None:
    """'Яндекс Пэй' should match Yandex Pay, not generic 'Яндекс'."""
    match = normalizer.match("Скачать Яндекс Пэй для платежей")
    assert match is not None
    assert match.canonical == "Яндекс Пэй"


def test_substring_in_sentence(normalizer: Normalizer) -> None:
    match = normalizer.match("Также не работает Wildberries при VPN")
    assert match is not None
    assert match.canonical == "Wildberries"


def test_unknown_returns_none(normalizer: Normalizer) -> None:
    assert normalizer.match("Какой-то неизвестный сервис XYZ") is None


def test_dedup_in_list(normalizer: Normalizer) -> None:
    """Multiple raw mentions of the same app should produce one record."""
    raw = ["Ozon", "ozon.ru", "Озон", "Wildberries"]
    result = normalizer.normalize_list(raw)
    assert len(result) == 2
    names = {app.canonical for app in result}
    assert names == {"Ozon", "Wildberries"}

from scraper.context_extractor import contains_vpn, extract_vpn_contexts


def test_extracts_only_sentence_with_vpn() -> None:
    text = "После обновления всё тормозит. Без VPN приложение не открывается. Переустановка не помогла."
    assert extract_vpn_contexts(text) == ["Без VPN приложение не открывается."]


def test_supports_russian_aliases() -> None:
    assert contains_vpn("С ВПН не работает")
    assert contains_vpn("Без КВН не открывается")


def test_does_not_support_mixed_script_garbage() -> None:
    assert not contains_vpn("С VРN не работает")


def test_long_unpunctuated_text_is_trimmed_to_local_window() -> None:
    before = " ".join(f"b{i}" for i in range(30))
    after = " ".join(f"a{i}" for i in range(30))
    contexts = extract_vpn_contexts(f"{before} vpn {after}")
    assert len(contexts) == 1
    words = contexts[0].split()
    assert len(words) == 21
    assert words[10].lower() == "vpn"


def test_multiple_sentences_with_mentions_are_kept_separately() -> None:
    text = "Без VPN не работает. С VPN работает нормально. Остальной текст."
    assert extract_vpn_contexts(text) == ["Без VPN не работает.", "С VPN работает нормально."]

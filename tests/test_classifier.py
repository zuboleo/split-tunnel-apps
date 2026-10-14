from scraper.evidence_classifier import classify
from scraper.evidence_engine import analyze_review, analyze_text


def test_strong_russian_detection() -> None:
    c = classify("Приложение сообщает: отключить VPN, чтобы продолжить")
    assert c.relevant
    assert c.verdict == "positive"
    assert c.confidence >= 0.9


def test_generic_vpn_mention_is_not_enough() -> None:
    c = classify("VPN помогает защищать ваш интернет")
    assert not c.relevant
    assert c.verdict == "neutral"


def test_vpn_as_blocking_bypass_is_not_app_blocking() -> None:
    c = analyze_text("VPN — это средство обхода блокировок и защиты соединения")
    assert c.verdict == "neutral"
    assert not c.relevant


def test_without_vpn_is_counterevidence() -> None:
    c = analyze_text("Приложение не работает без VPN, а с VPN открывается нормально")
    assert not c.relevant
    assert c.verdict == "negative"
    assert c.confidence >= 0.9


def test_without_vpn_prefix_is_counterevidence() -> None:
    c = analyze_text("Без впн не зайдёшь, пишет ошибка подключения")
    assert c.verdict == "negative"
    assert "requires_vpn_ru" in c.negative_matches


def test_make_it_work_without_vpn_is_counterevidence() -> None:
    c = analyze_text("Сделайте приложение чтобы работало без VPN, а то без него не работает")
    assert c.verdict == "negative"
    assert not c.relevant


def test_same_failure_with_and_without_vpn_is_counterevidence() -> None:
    c = analyze_text("Приложение не открывается: что с ВПН, что без него")
    assert c.verdict == "negative"


def test_shazam_style_same_with_or_without_vpn_is_negative() -> None:
    c = analyze_text('Не работает от слова "вообще", с впн или без не имеет значения.')
    assert c.verdict == "negative"
    assert "same_with_without_vpn_ru" in c.negative_matches
    assert not c.relevant


def test_youtube_style_vpn_helps_is_negative() -> None:
    c = analyze_text(
        "ютуб ограничили, но впн поможет, разработчики стараются сделать чтобы ютуб без впн работал"
    )
    assert c.verdict == "negative"
    assert "vpn_helps_ru" in c.negative_matches
    assert not c.relevant


def test_preposition_must_be_a_word_not_a_letter_inside_word() -> None:
    c = analyze_text("ограниченной части но впн поможет")
    assert "blocked_with_vpn_ru" not in c.strong_matches
    assert c.verdict == "negative"


def test_vpn_does_not_fix_failure_is_negative() -> None:
    c = analyze_text("Без вайфая не открывается вообще, да и с впн тоже через раз")
    assert c.verdict == "negative"
    assert "vpn_does_not_fix_ru" in c.negative_matches


def test_with_vpn_failure_is_positive() -> None:
    c = analyze_text("Приложение не работает с VPN")
    assert c.relevant
    assert c.verdict == "positive"
    assert "blocked_with_vpn_ru" in c.strong_matches


def test_colloquial_vpn_allergy_is_positive() -> None:
    c = analyze_text('У вашего приложения "аллергия" на VPN? Тогда больше 1 звезды не получите.')
    assert c.verdict == "positive"
    assert c.confidence >= 0.9
    assert "vpn_allergy_ru" in c.strong_matches


def test_false_vpn_detection_is_very_strong() -> None:
    c = analyze_text("Приложение требует отключить VPN, но он у меня не включен")
    assert c.verdict == "positive"
    assert c.confidence >= 0.95
    assert "false_vpn_detection_ru" in c.strong_matches


def test_rustore_style_false_detection_text() -> None:
    c = analyze_text("Не работает!!! Требует отключить VPN, но он у меня не включен!!!!")
    assert c.verdict == "positive"
    assert c.confidence >= 0.95


def test_explicit_app_message_disable_vpn_is_strong() -> None:
    c = analyze_text("Приложение не работает за границей. Пишет выключите впн. Бред просто.")
    assert c.verdict == "positive"
    assert c.confidence >= 0.9
    assert "requires_disable_vpn_ru" in c.strong_matches


def test_developer_disable_vpn_boilerplate_is_only_moderate() -> None:
    c = analyze_review(
        "Не открывается приложение",
        "Пожалуйста, отключите VPN, очистите кэш и перезагрузите телефон",
        app_name="Example",
    )
    assert c.verdict == "positive"
    assert 0.5 <= c.confidence < 0.7


def test_vpn_app_review_is_not_mistaken_for_blocking() -> None:
    c = analyze_text("VPN не работает после обновления", app_name="VPN ЕНОТ")
    assert c.verdict in {"neutral", "uncertain"}
    assert not c.relevant

from scraper.evidence_classifier import classify
from scraper.evidence_engine import analyze_review, analyze_text


def test_explicit_disable_vpn_routes_direct() -> None:
    c = classify("Приложение сообщает: отключить VPN, чтобы продолжить")
    assert c.relevant
    assert c.route == "direct"
    assert c.verdict == "positive"
    assert c.confidence >= 0.9


def test_generic_vpn_mention_is_neutral() -> None:
    c = classify("VPN помогает защищать ваш интернет")
    assert not c.relevant
    assert c.route == "neutral"


def test_without_vpn_failure_routes_proxy() -> None:
    c = analyze_text("Приложение не работает без VPN, а с VPN открывается нормально")
    assert c.relevant
    assert c.route == "proxy"
    assert c.verdict == "negative"
    assert c.confidence >= 0.9


def test_inflected_without_vpn_failure_routes_proxy() -> None:
    c = analyze_text("Приложения не запускались без ВПН после обновления")
    assert c.route == "proxy"
    assert c.condition == "WITHOUT_VPN"
    assert c.effect == "NOT_WORKING"


def test_rustore_without_vpn_cannot_enter_routes_proxy() -> None:
    c = analyze_text("Без впн не зайдёшь, пишет ошибка подключения")
    assert c.route == "proxy"
    assert c.condition == "WITHOUT_VPN"
    assert c.confidence >= 0.9


def test_goal_to_work_without_vpn_means_proxy_is_currently_needed() -> None:
    c = analyze_text("Сделайте приложение чтобы работало без VPN, а то без него не работает")
    assert c.route == "proxy"
    assert c.confidence >= 0.9


def test_same_failure_with_and_without_vpn_is_neutral() -> None:
    c = analyze_text('Не работает от слова "вообще", с впн или без не имеет значения.')
    assert c.route == "neutral"
    assert not c.relevant


def test_vpn_also_fails_does_not_imply_direct() -> None:
    c = analyze_text("Без вайфая не открывается вообще, да и с впн тоже через раз")
    assert c.route == "neutral"
    assert not c.relevant


def test_youtube_style_vpn_help_routes_proxy() -> None:
    c = analyze_text(
        "ютуб ограничили, но впн поможет, разработчики стараются сделать чтобы ютуб без впн работал",
        app_name="YouTube",
    )
    assert c.route == "proxy"
    assert c.relevant
    assert c.confidence >= 0.9


def test_with_vpn_failure_routes_direct() -> None:
    c = analyze_text("Приложение не работает с VPN")
    assert c.route == "direct"
    assert c.relevant
    assert c.condition == "WITH_VPN"
    assert c.effect == "NOT_WORKING"


def test_enabled_vpn_state_failure_routes_direct() -> None:
    c = analyze_text("При включенном ВПН приложение не работает")
    assert c.route == "direct"
    assert c.condition == "WITH_VPN"
    assert c.effect == "NOT_WORKING"


def test_enabling_vpn_then_working_routes_proxy() -> None:
    c = analyze_text("Включил VPN — приложение заработало")
    assert c.route == "proxy"
    assert c.condition == "ENABLE_VPN"
    assert c.effect == "WORKING"


def test_disabling_vpn_then_working_routes_direct() -> None:
    c = analyze_text("Выключил VPN — приложение заработало")
    assert c.route == "direct"
    assert c.condition == "DISABLE_VPN"
    assert c.effect == "WORKING"


def test_false_vpn_detection_is_very_strong_direct() -> None:
    c = analyze_text("Приложение требует отключить VPN, но он у меня не включен")
    assert c.route == "direct"
    assert c.confidence >= 0.95


def test_colloquial_vpn_allergy_is_direct() -> None:
    c = analyze_text('У вашего приложения "аллергия" на VPN? Тогда больше 1 звезды не получите.')
    assert c.route == "direct"
    assert c.confidence >= 0.9


def test_developer_disable_vpn_boilerplate_is_only_moderate_direct() -> None:
    c = analyze_review(
        "Не открывается приложение",
        "Пожалуйста, отключите VPN, очистите кэш и перезагрузите телефон",
        app_name="Example",
    )
    assert c.route == "direct"
    assert 0.5 <= c.confidence < 0.7


def test_russian_kvn_alias_is_supported() -> None:
    c = analyze_text("Без КВН приложение не открывается")
    assert c.route == "proxy"
    assert c.condition == "WITHOUT_VPN"


def test_mixed_script_vpn_is_not_supported() -> None:
    # Latin V/N plus Cyrillic Р: intentionally not normalized as VPN.
    c = analyze_text("Приложение не работает с VРN")
    assert c.route == "neutral"
    assert not c.relevant


def test_vpn_app_review_is_not_mistaken_for_direct_blocking() -> None:
    c = analyze_text("VPN не работает после обновления", app_name="VPN ЕНОТ")
    assert c.route in {"neutral", "uncertain"}
    assert not c.relevant

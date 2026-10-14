from scraper.evidence_classifier import classify


def test_strong_russian_detection() -> None:
    c = classify("Приложение сообщает: отключите VPN, чтобы продолжить")
    assert c.relevant
    assert c.score >= 3


def test_generic_vpn_mention_is_not_enough() -> None:
    c = classify("VPN помогает защищать ваш интернет")
    assert not c.relevant


def test_without_vpn_is_not_block_evidence() -> None:
    c = classify("Приложение не работает без VPN, а с VPN открывается нормально")
    assert not c.relevant


def test_same_failure_with_and_without_vpn_is_not_block_evidence() -> None:
    c = classify("Приложение не открывается: что с ВПН, что без него")
    assert not c.relevant


def test_with_vpn_failure_is_still_relevant() -> None:
    c = classify("Приложение не работает с VPN")
    assert c.relevant
    assert "not_work_with_vpn_ru" in c.strong_matches

from scraper.evidence_classifier import classify


def test_strong_russian_detection() -> None:
    c = classify("Приложение сообщает: отключите VPN, чтобы продолжить")
    assert c.relevant
    assert c.score >= 3


def test_generic_vpn_mention_is_not_enough() -> None:
    c = classify("VPN помогает защищать ваш интернет")
    assert not c.relevant

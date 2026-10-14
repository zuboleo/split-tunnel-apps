from scraper.discovery.bing_rss import BingRssSearch


def test_parse_bing_rss() -> None:
    xml = """<?xml version='1.0'?><rss><channel><item>
    <title>DNS SHOP asks to disable VPN</title>
    <link>https://play.google.com/store/apps/details?id=ru.dns.shop.android</link>
    <description>Приложение требует отключить VPN</description>
    <pubDate>Wed, 14 Oct 2026 09:00:00 GMT</pubDate>
    </item></channel></rss>"""
    hits = BingRssSearch.parse_rss(xml, '"отключите VPN"')
    assert len(hits) == 1
    assert hits[0].url.endswith("id=ru.dns.shop.android")
    assert hits[0].published_at is not None

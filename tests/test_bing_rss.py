from scraper.discovery.bing_rss import BingRssSearch
from scraper.link_finder import LinkFinder


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


class DummySearch:
    def search(self, *args, **kwargs):
        return []


def test_link_finder_routes_only_configured_article_domains(tmp_path) -> None:
    config = tmp_path / "discovery.yaml"
    config.write_text(
        """
source_domains:
  - {domain: example.com, enabled: true}
stores:
  - {domains: [play.google.com], enabled: true}
""".strip(),
        encoding="utf-8",
    )
    finder = LinkFinder(config, DummySearch())

    assert finder.is_article_source("https://news.example.com/story")
    assert not finder.is_article_source("https://gorki-apartamenti.ru/random")
    assert finder.is_store_source("https://play.google.com/store/apps/details?id=x.y")
    assert not finder.is_store_source("https://example.com/story")

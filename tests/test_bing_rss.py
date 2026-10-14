import base64
from urllib.parse import quote

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


def test_parse_bing_web_tracking_url() -> None:
    target = "https://www.rustore.ru/catalog/app/ru.dns.shop.android/reviews"
    encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    wrapped = f"https://www.bing.com/ck/a?!&&p=x&u=a1{encoded}&ntb=1"
    xml = f"""<?xml version='1.0'?><rss><channel><item>
    <title>DNS SHOP</title>
    <link>{wrapped.replace('&', '&amp;')}</link>
    <description>Требует отключить VPN</description>
    </item></channel></rss>"""
    hits = BingRssSearch.parse_rss(xml, "dns")
    assert hits[0].url == target


def test_parse_bing_news_tracking_url() -> None:
    target = "https://example.com/news/vpn-story?x=1"
    wrapped = (
        "https://www.bing.com/news/apiclick.aspx?ref=FexRss&url="
        + quote(target, safe="")
        + "&c=tracking"
    )
    xml = f"""<?xml version='1.0'?><rss><channel><item>
    <title>News</title>
    <link>{wrapped.replace('&', '&amp;')}</link>
    <description>VPN story</description>
    </item></channel></rss>"""
    hits = BingRssSearch.parse_rss(xml, "vpn", limit=1)
    assert hits[0].url == target


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

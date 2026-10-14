from __future__ import annotations

from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from ..http import PoliteDelay
from ..models import SearchHit


class BingRssSearch:
    """Keyless web/news search via Bing's public RSS result format."""

    provider_id = "bing_rss"

    def __init__(self, session: requests.Session, delay_seconds: float = 0.7):
        self.session = session
        self.delay = PoliteDelay(delay_seconds)

    def search(self, query: str, limit: int = 10, news: bool = False) -> list[SearchHit]:
        self.delay.wait()
        endpoint = "https://www.bing.com/news/search" if news else "https://www.bing.com/search"
        response = self.session.get(
            endpoint,
            params={"q": query, "format": "rss", "mkt": "ru-RU", "setlang": "ru-RU"},
            timeout=20,
        )
        response.raise_for_status()
        return self.parse_rss(response.text, query=query, limit=limit)

    @classmethod
    def parse_rss(cls, xml_text: str, query: str, limit: int = 10) -> list[SearchHit]:
        root = ElementTree.fromstring(xml_text)
        hits: list[SearchHit] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            snippet = (item.findtext("description") or "").strip()
            pub_raw = (item.findtext("pubDate") or "").strip()
            published_at = None
            if pub_raw:
                try:
                    published_at = parsedate_to_datetime(pub_raw).isoformat()
                except (TypeError, ValueError):
                    published_at = pub_raw
            if not url:
                continue
            hits.append(
                SearchHit(
                    provider=cls.provider_id,
                    query=query,
                    title=title,
                    url=url,
                    snippet=snippet,
                    published_at=published_at,
                )
            )
            if len(hits) >= limit:
                break
        return hits

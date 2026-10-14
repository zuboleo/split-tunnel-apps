from __future__ import annotations

from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
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

    def _request_rss(self, endpoint: str, params: dict[str, str]) -> requests.Response:
        # requests used to follow Bing geo redirects automatically. Some of
        # Bing's generated hosts (www.ru.bing.com, www.fi.bing.com, etc.) have
        # recently presented certificates for a different hostname, which made
        # otherwise valid searches disappear from the daily run. Follow Bing
        # redirects manually and pin them back to canonical www.bing.com.
        response = self.session.get(endpoint, params=params, timeout=20, allow_redirects=False)
        for _ in range(2):
            if response.status_code not in {301, 302, 303, 307, 308}:
                break
            location = response.headers.get("Location")
            if not location:
                break
            target = urljoin(response.url, location)
            parsed = urlparse(target)
            host = (parsed.hostname or "").lower()
            if host.endswith(".bing.com") and host != "www.bing.com":
                parsed = parsed._replace(netloc="www.bing.com")
                target = parsed.geturl()
            response = self.session.get(target, timeout=20, allow_redirects=False)

        if response.status_code in {301, 302, 303, 307, 308}:
            # Last-resort canonical request with an explicit country instead of
            # following another geo host.
            fallback = dict(params)
            fallback["cc"] = "ru"
            fallback["mkt"] = "en-US"
            response = self.session.get(endpoint, params=fallback, timeout=20, allow_redirects=False)

        response.raise_for_status()
        if response.status_code in {301, 302, 303, 307, 308}:
            raise RuntimeError(f"Bing RSS redirect loop: {response.status_code} {response.headers.get('Location')}")
        return response

    def search(self, query: str, limit: int = 10, news: bool = False) -> list[SearchHit]:
        self.delay.wait()
        endpoint = "https://www.bing.com/news/search" if news else "https://www.bing.com/search"
        response = self._request_rss(
            endpoint,
            {"q": query, "format": "rss", "mkt": "ru-RU", "setlang": "ru-RU"},
        )
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

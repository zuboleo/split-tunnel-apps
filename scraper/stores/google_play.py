from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from ..models import SearchHit
from .base import StoreMatch, StoreParser


class GooglePlayParser(StoreParser):
    store_id = "google_play"

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("play.google.com") and "/store/apps/details" in url

    def parse_hit(self, hit: SearchHit, html: str | None = None) -> StoreMatch:
        query = parse_qs(urlparse(hit.url).query)
        package_id = (query.get("id") or [None])[0]
        app_name = hit.title.strip() or None
        if html:
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1")
            if h1:
                app_name = h1.get_text(" ", strip=True) or app_name
            if not package_id:
                match = re.search(r"[?&]id=([A-Za-z0-9._]+)", html)
                package_id = match.group(1) if match else None
        return StoreMatch(self.store_id, package_id, app_name)

    def fetch_recent_reviews(self, package_id: str, count: int = 100) -> list[str]:
        """Optional deep scan. Failure is deliberately non-fatal.

        google-play-scraper uses Google Play's public app surface without an API key.
        The main pipeline does not depend on it: Bing snippets still work when this
        endpoint changes.
        """
        try:
            from google_play_scraper import Sort, reviews

            rows, _ = reviews(package_id, lang="ru", country="ru", sort=Sort.NEWEST, count=count)
            texts: list[str] = []
            for row in rows:
                content = (row.get("content") or "").strip()
                reply = (row.get("replyContent") or "").strip()
                joined = " ".join(x for x in (content, reply) if x)
                if joined:
                    texts.append(joined)
            return texts
        except Exception:
            return []

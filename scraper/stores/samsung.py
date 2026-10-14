from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..models import SearchHit
from .base import StoreMatch, StoreParser


class SamsungStoreParser(StoreParser):
    store_id = "samsung_galaxy_store"
    _path_re = re.compile(r"/detail/([^/?#]+)")

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("galaxystore.samsung.com") and "/detail/" in url

    def parse_hit(self, hit: SearchHit, html: str | None = None) -> StoreMatch:
        match = self._path_re.search(urlparse(hit.url).path)
        package_id = match.group(1) if match else None
        app_name = hit.title.strip() or None
        if html:
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1")
            if h1:
                app_name = h1.get_text(" ", strip=True) or app_name
        return StoreMatch(self.store_id, package_id, app_name)

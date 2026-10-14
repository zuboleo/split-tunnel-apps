from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import SearchHit
from .base import StoreMatch, StoreParser


_PACKAGE_RE = re.compile(r"(?:packageName|pkgName|bundleName)[\"'\s:=]+([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)", re.I)


class HuaweiAppGalleryParser(StoreParser):
    store_id = "huawei_appgallery"

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("appgallery.huawei.com") or host.endswith("appgallery.cloud.huawei.com")

    def parse_hit(self, hit: SearchHit, html: str | None = None) -> StoreMatch:
        parsed = urlparse(hit.url)
        query = parse_qs(parsed.query)
        package_id = (query.get("pkgName") or query.get("packageName") or [None])[0]
        app_name = hit.title.strip() or None

        haystacks = [unquote(hit.url), hit.snippet]
        if html:
            haystacks.append(html)
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1")
            if h1:
                app_name = h1.get_text(" ", strip=True) or app_name

        if not package_id:
            for haystack in haystacks:
                match = _PACKAGE_RE.search(haystack or "")
                if match:
                    package_id = match.group(1)
                    break
        return StoreMatch(self.store_id, package_id, app_name)

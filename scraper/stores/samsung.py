from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import SearchHit
from .base import StoreMatch, StoreParser


_PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_EMBEDDED_PACKAGE_RE = re.compile(
    r"(?:packageName|package_name|appId|productId)[\"'\s:=]+[\"']?([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)",
    re.I,
)


class SamsungStoreParser(StoreParser):
    store_id = "samsung_galaxy_store"
    _detail_path_re = re.compile(r"/detail/([^/?#]+)", re.I)

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host.endswith("galaxystore.samsung.com"):
            return "/detail/" in parsed.path.lower()
        if host.endswith("apps.samsung.com"):
            return "appdetail" in parsed.path.lower()
        return False

    @staticmethod
    def detail_url(package_id: str) -> str:
        return f"https://galaxystore.samsung.com/detail/{package_id}"

    @staticmethod
    def _valid_package(value: str | None) -> str | None:
        if not value:
            return None
        value = unquote(value).strip()
        return value if _PACKAGE_ID_RE.fullmatch(value) else None

    def parse_hit(self, hit: SearchHit, html: str | None = None) -> StoreMatch:
        parsed = urlparse(hit.url)
        query = parse_qs(parsed.query)
        package_id: str | None = None

        match = self._detail_path_re.search(parsed.path)
        if match:
            package_id = self._valid_package(match.group(1))

        if not package_id:
            for key in ("appId", "packageName", "pkgName", "productId"):
                package_id = self._valid_package((query.get(key) or [None])[0])
                if package_id:
                    break

        app_name = hit.title.strip() or None
        haystacks = [unquote(hit.url), hit.snippet]
        if html:
            haystacks.append(html)
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1")
            if h1:
                app_name = h1.get_text(" ", strip=True) or app_name
            elif soup.find("meta", attrs={"property": "og:title"}):
                app_name = soup.find("meta", attrs={"property": "og:title"}).get("content") or app_name

        if not package_id:
            for haystack in haystacks:
                embedded = _EMBEDDED_PACKAGE_RE.search(haystack or "")
                if embedded:
                    package_id = self._valid_package(embedded.group(1))
                    if package_id:
                        break

        return StoreMatch(self.store_id, package_id, app_name)

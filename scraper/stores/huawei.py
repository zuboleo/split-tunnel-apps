from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import SearchHit
from .base import StoreMatch, StoreParser


_PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_PACKAGE_RE = re.compile(
    r"(?:packageName|pkgName|bundleName|package)[\"'\s:=]+[\"']?([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)",
    re.I,
)
_APP_PATH_RE = re.compile(r"/(?:#?/)?app(?:dl)?/([^/?#]+)", re.I)


class HuaweiAppGalleryParser(StoreParser):
    store_id = "huawei_appgallery"

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(
            host.endswith(suffix)
            for suffix in (
                "appgallery.huawei.com",
                "appgallery.cloud.huawei.com",
                "appgallery.huawei.ru",
            )
        )

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

        for key in ("pkgName", "packageName", "bundleName", "id"):
            package_id = self._valid_package((query.get(key) or [None])[0])
            if package_id:
                break

        # Some AppGallery links contain the real package name in /app/<value>,
        # while the common C123456789 form is an AppGallery ID, not a package.
        if not package_id:
            route = unquote(parsed.path)
            if parsed.fragment:
                route += "/" + unquote(parsed.fragment).lstrip("/")
            path_match = _APP_PATH_RE.search(route)
            if path_match:
                package_id = self._valid_package(path_match.group(1))

        app_name = hit.title.strip() or None
        haystacks = [unquote(hit.url), hit.snippet]
        if html:
            haystacks.append(html)
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1")
            if h1:
                app_name = h1.get_text(" ", strip=True) or app_name
            else:
                meta = soup.find("meta", attrs={"property": "og:title"})
                if meta and meta.get("content"):
                    app_name = meta.get("content") or app_name

        if not package_id:
            for haystack in haystacks:
                match = _PACKAGE_RE.search(haystack or "")
                if match:
                    package_id = self._valid_package(match.group(1))
                    if package_id:
                        break

        return StoreMatch(self.store_id, package_id, app_name)

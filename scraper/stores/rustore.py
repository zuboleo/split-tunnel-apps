from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..evidence_classifier import classify
from ..models import Evidence, SearchHit
from .base import StoreMatch, StoreParser

log = logging.getLogger(__name__)


class RuStoreParser(StoreParser):
    store_id = "rustore"
    _path_re = re.compile(r"/catalog/app/([^/?#]+)")

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("rustore.ru") and "/catalog/app/" in url

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

    @staticmethod
    def reviews_url(package_id: str) -> str:
        return f"https://www.rustore.ru/catalog/app/{package_id}/reviews"

    def discover_catalog(self, session: requests.Session, *, max_apps: int = 160) -> dict[str, str]:
        """Collect package IDs directly from RuStore's public catalogue pages."""
        urls = [
            "https://www.rustore.ru/catalog/all",
            "https://www.rustore.ru/catalog/category/finansy",
            "https://www.rustore.ru/catalog/category/pokupki",
            "https://www.rustore.ru/catalog/category/transport-i-navigatsiya",
            "https://www.rustore.ru/catalog/category/gosudarstvennye",
            "https://www.rustore.ru/catalog/category/eda-i-napitki",
            "https://www.rustore.ru/catalog/category/zdorove",
        ]
        found: dict[str, str] = {}
        for url in urls:
            if len(found) >= max_apps:
                break
            try:
                r = session.get(url, timeout=20)
                r.raise_for_status()
            except Exception as exc:
                log.warning("RuStore catalogue failed %s: %s", url, exc)
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])
                m = self._path_re.search(urlparse(href).path)
                if not m:
                    continue
                package_id = m.group(1)
                title = a.get_text(" ", strip=True) or package_id
                found.setdefault(package_id, title)
                if len(found) >= max_apps:
                    break
        log.info("RuStore catalogue discovery: %d apps", len(found))
        return found

    def fetch_reviews_text(self, session: requests.Session, package_id: str) -> tuple[str, str]:
        url = self.reviews_url(package_id)
        try:
            r = session.get(url, timeout=20)
            r.raise_for_status()
        except Exception as exc:
            log.warning("RuStore reviews failed for %s: %s", package_id, exc)
            return "", url
        soup = BeautifulSoup(r.text, "lxml")
        return soup.get_text(" ", strip=True), url

    def scan_reviews(self, session: requests.Session, *, max_apps: int = 160) -> list[Evidence]:
        packages = self.discover_catalog(session, max_apps=max_apps)
        evidence: list[Evidence] = []
        for package_id, app_name in packages.items():
            text, url = self.fetch_reviews_text(session, package_id)
            c = classify(text)
            if not c.relevant:
                continue
            evidence.append(
                Evidence(
                    package_id=package_id,
                    app_name=app_name,
                    source_type="store",
                    source_id="rustore_reviews",
                    source_domain="rustore.ru",
                    url=url,
                    title=app_name,
                    snippet=text[:1200],
                    score=c.score,
                    strong_matches=c.strong_matches,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    store=self.store_id,
                    query="direct_store_scan",
                )
            )
        log.info("RuStore direct scan: %d apps checked, %d matches", len(packages), len(evidence))
        return evidence

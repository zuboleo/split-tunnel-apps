from __future__ import annotations

import logging
import re
from collections import deque
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
    def app_url(package_id: str) -> str:
        return f"https://www.rustore.ru/catalog/app/{package_id}"

    @classmethod
    def reviews_url(cls, package_id: str) -> str:
        return f"{cls.app_url(package_id)}/reviews"

    def _collect_app_links(self, page_url: str, html: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        found: list[tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = urljoin(page_url, a["href"])
            match = self._path_re.search(urlparse(href).path)
            if not match:
                continue
            package_id = match.group(1)
            title = a.get_text(" ", strip=True) or package_id
            found.append((package_id, title))
        return found

    def discover_catalog(
        self,
        session: requests.Session,
        *,
        max_apps: int = 160,
        expansion_pages: int = 24,
    ) -> dict[str, str]:
        """Collect package IDs from live RuStore pages without hard-coded category slugs.

        RuStore changes category URLs periodically. The stable public entry points are
        /catalog and /catalog/all, while application URLs are documented as
        /catalog/app/{packageName}. We crawl those entry points and then a small,
        bounded number of discovered app pages to pick up related-app links.
        """
        queue: deque[str] = deque(
            [
                "https://www.rustore.ru/catalog",
                "https://www.rustore.ru/catalog/all",
            ]
        )
        visited: set[str] = set()
        found: dict[str, str] = {}
        expanded_apps = 0

        while queue and len(found) < max_apps:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            try:
                response = session.get(url, timeout=20)
                response.raise_for_status()
            except Exception as exc:
                log.warning("RuStore catalogue failed %s: %s", url, exc)
                continue

            for package_id, title in self._collect_app_links(url, response.text):
                is_new = package_id not in found
                found.setdefault(package_id, title)
                if (
                    is_new
                    and expanded_apps < expansion_pages
                    and len(found) < max_apps
                ):
                    queue.append(self.app_url(package_id))
                    expanded_apps += 1
                if len(found) >= max_apps:
                    break

        log.info(
            "RuStore catalogue discovery: %d apps from %d pages",
            len(found),
            len(visited),
        )
        return found

    def fetch_reviews_text(self, session: requests.Session, package_id: str) -> tuple[str, str]:
        url = self.reviews_url(package_id)
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            log.warning("RuStore reviews failed for %s: %s", package_id, exc)
            return "", url
        soup = BeautifulSoup(response.text, "lxml")
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

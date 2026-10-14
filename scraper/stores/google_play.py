from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from ..evidence_classifier import classify
from ..models import Evidence, SearchHit
from .base import StoreMatch, StoreParser

log = logging.getLogger(__name__)


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
        except Exception as exc:
            log.warning("Google Play reviews failed for %s: %s", package_id, exc)
            return []

    def discover_packages(self, queries: list[str], per_query: int = 12) -> dict[str, str]:
        """Discover apps directly through Google Play search, not web-search snippets."""
        try:
            from google_play_scraper import search
        except Exception as exc:
            log.warning("Google Play search unavailable: %s", exc)
            return {}

        found: dict[str, str] = {}
        for query in queries:
            try:
                rows = search(query, lang="ru", country="ru", n_hits=per_query)
            except Exception as exc:
                log.warning("Google Play search failed for %r: %s", query, exc)
                continue
            for row in rows:
                package_id = row.get("appId")
                if package_id:
                    found.setdefault(package_id, row.get("title") or package_id)
        return found

    def scan_reviews(
        self,
        queries: list[str],
        *,
        per_query: int = 12,
        review_count: int = 60,
        max_apps: int = 120,
        max_evidence_per_app: int = 2,
    ) -> list[Evidence]:
        from datetime import datetime, timezone

        packages = self.discover_packages(queries, per_query=per_query)
        evidence: list[Evidence] = []
        matched_apps = 0
        for package_id, app_name in list(packages.items())[:max_apps]:
            app_matches = 0
            for text in self.fetch_recent_reviews(package_id, count=review_count):
                c = classify(text)
                if not c.relevant:
                    continue
                evidence.append(
                    Evidence(
                        package_id=package_id,
                        app_name=app_name,
                        source_type="store",
                        source_id="google_play_reviews",
                        source_domain="play.google.com",
                        url=f"https://play.google.com/store/apps/details?id={package_id}",
                        title=app_name,
                        snippet=text[:1200],
                        score=c.score,
                        strong_matches=c.strong_matches,
                        discovered_at=datetime.now(timezone.utc).isoformat(),
                        store=self.store_id,
                        query="direct_store_scan",
                    )
                )
                app_matches += 1
                if app_matches >= max_evidence_per_app:
                    break
            if app_matches:
                matched_apps += 1
        log.info(
            "Google Play direct scan: %d apps checked, %d apps matched, %d evidence rows",
            min(len(packages), max_apps),
            matched_apps,
            len(evidence),
        )
        return evidence

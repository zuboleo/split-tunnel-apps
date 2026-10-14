from __future__ import annotations

import html as html_lib
import logging
import re
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..evidence_engine import analyze_text
from ..models import Evidence, SearchHit
from .base import StoreMatch, StoreParser

log = logging.getLogger(__name__)

_VPN_TOKEN = re.compile(r"\b(?:vpn|впн|proxy|прокси)\b", re.I)


class RuStoreParser(StoreParser):
    store_id = "rustore"
    _path_re = re.compile(r"/catalog/app/([^/?#]+)")

    # These are not application names. They are search phrases aimed directly
    # at indexed RuStore review pages, which is much more efficient than hoping
    # a random top-120 catalogue sample contains a VPN-sensitive application.
    REVIEW_SEARCH_PHRASES = (
        '"требует отключить VPN"',
        '"требует выключить VPN"',
        '"просит отключить VPN"',
        '"отключите VPN"',
        '"выключите VPN"',
        '"обнаружен VPN"',
        '"ругается на VPN"',
        '"не работает с VPN"',
        '"VPN detected"',
        '"disable VPN"',
    )

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("rustore.ru") and "/catalog/app/" in url

    def parse_hit(self, hit: SearchHit, html: str | None = None) -> StoreMatch:
        match = self._path_re.search(urlparse(hit.url).path)
        package_id = match.group(1) if match else None
        app_name = self._clean_title(hit.title) or None
        if html:
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1")
            if h1:
                app_name = h1.get_text(" ", strip=True) or app_name
        return StoreMatch(self.store_id, package_id, app_name)

    @staticmethod
    def _clean_title(title: str) -> str:
        title = (title or "").strip()
        match = re.search(r"отзыв(?:а|ов)?\s+о\s+приложении\s+(.+?)\s+в\s+RuStore", title, re.I)
        return (match.group(1) if match else title).strip()

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
                if is_new and expanded_apps < expansion_pages and len(found) < max_apps:
                    queue.append(self.app_url(package_id))
                    expanded_apps += 1
                if len(found) >= max_apps:
                    break

        log.info("RuStore catalogue discovery: %d apps from %d pages", len(found), len(visited))
        return found

    def discover_search_api(
        self,
        session: requests.Session,
        queries: list[str],
        *,
        per_query: int = 20,
        max_apps: int = 160,
    ) -> dict[str, str]:
        """Diversify direct scanning with RuStore's public showcase search backend."""
        found: dict[str, str] = {}
        endpoint = "https://backapi.rustore.ru/applicationData/apps"
        for query in queries:
            if len(found) >= max_apps:
                break
            try:
                response = session.get(
                    endpoint,
                    params={"pageSize": per_query, "pageNumber": 0, "query": query},
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                log.debug("RuStore search API failed for %r: %s", query, exc)
                continue
            rows = ((payload or {}).get("body") or {}).get("content") or []
            for row in rows:
                package_id = row.get("packageName")
                if package_id:
                    found.setdefault(package_id, row.get("appName") or package_id)
                if len(found) >= max_apps:
                    break
        return found

    @staticmethod
    def _vpn_fragments(text: str, *, radius: int = 260, limit: int = 12) -> list[str]:
        if not text:
            return []
        fragments: list[str] = []
        seen: set[str] = set()
        for match in _VPN_TOKEN.finditer(text):
            start = max(0, match.start() - radius)
            end = min(len(text), match.end() + radius)
            fragment = re.sub(r"\s+", " ", text[start:end]).strip()
            if fragment and fragment not in seen:
                seen.add(fragment)
                fragments.append(fragment)
            if len(fragments) >= limit:
                break
        return fragments

    def fetch_review_fragments(self, session: requests.Session, package_id: str) -> tuple[list[str], str]:
        """Extract VPN-centred text from visible HTML and embedded page JSON.

        RuStore changes rendering frequently. Reading both visible text and raw
        HTML catches server-rendered reviews as well as review payloads embedded
        into script state. If the page is only a JS shell, indexed-review search
        below remains the fallback.
        """
        url = self.reviews_url(package_id)
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            log.warning("RuStore reviews failed for %s: %s", package_id, exc)
            return [], url

        soup = BeautifulSoup(response.text, "lxml")
        visible = soup.get_text(" ", strip=True)
        raw = html_lib.unescape(response.text)
        fragments = self._vpn_fragments(visible)
        if len(fragments) < 12:
            for fragment in self._vpn_fragments(raw, limit=12 - len(fragments)):
                clean = BeautifulSoup(fragment, "lxml").get_text(" ", strip=True)
                clean = re.sub(r"\\[nrt]", " ", clean)
                clean = clean.replace('\\"', '"')
                clean = re.sub(r"\s+", " ", clean).strip()
                if clean and clean not in fragments:
                    fragments.append(clean)
        return fragments, url

    def scan_indexed_reviews(self, search, *, limit_per_phrase: int = 10) -> list[Evidence]:
        """Find RuStore review pages whose indexed snippets already mention VPN."""
        evidence: list[Evidence] = []
        seen: set[tuple[str, str, str]] = set()

        for phrase in self.REVIEW_SEARCH_PHRASES:
            query = f"site:rustore.ru/catalog/app {phrase}"
            try:
                hits = search.search(query, limit=limit_per_phrase)
            except Exception as exc:
                log.warning("RuStore indexed review search failed for %r: %s", phrase, exc)
                continue

            for hit in hits:
                if "/catalog/app/" not in hit.url or "/reviews" not in hit.url:
                    continue
                match = self.parse_hit(hit)
                if not match.package_id:
                    continue
                classification = analyze_text(
                    " ".join(x for x in (hit.title, hit.snippet) if x),
                    role="search_snippet",
                    app_name=match.app_name,
                )
                if classification.verdict not in {"positive", "negative"}:
                    continue
                key = (match.package_id, classification.verdict, hit.snippet.strip())
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    Evidence(
                        package_id=match.package_id,
                        app_name=match.app_name,
                        source_type="store",
                        source_id="rustore_indexed_reviews",
                        source_domain="rustore.ru",
                        url=hit.url,
                        title=hit.title,
                        snippet=hit.snippet[:1200],
                        score=classification.score,
                        strong_matches=classification.strong_matches,
                        discovered_at=datetime.now(timezone.utc).isoformat(),
                        published_at=hit.published_at,
                        store=self.store_id,
                        query="indexed_review_scan",
                        verdict=classification.verdict,
                        confidence=classification.confidence,
                        negative_matches=classification.negative_matches,
                    )
                )

        log.info("RuStore indexed review scan: %d evidence rows", len(evidence))
        return evidence

    def scan_reviews(
        self,
        session: requests.Session,
        *,
        search=None,
        discovery_queries: list[str] | None = None,
        max_apps: int = 160,
        max_evidence_per_app: int = 3,
    ) -> list[Evidence]:
        packages = self.discover_catalog(session, max_apps=max_apps)
        if discovery_queries:
            for package_id, app_name in self.discover_search_api(
                session,
                discovery_queries,
                per_query=15,
                max_apps=max_apps,
            ).items():
                if len(packages) >= max_apps:
                    break
                packages.setdefault(package_id, app_name)

        evidence: list[Evidence] = []
        matched_apps = 0
        for package_id, app_name in list(packages.items())[:max_apps]:
            fragments, url = self.fetch_review_fragments(session, package_id)
            app_matches = 0
            for fragment in fragments:
                classification = analyze_text(fragment, role="user_review", app_name=app_name)
                if classification.verdict not in {"positive", "negative"}:
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
                        snippet=fragment[:1200],
                        score=classification.score,
                        strong_matches=classification.strong_matches,
                        discovered_at=datetime.now(timezone.utc).isoformat(),
                        store=self.store_id,
                        query="direct_store_scan",
                        verdict=classification.verdict,
                        confidence=classification.confidence,
                        negative_matches=classification.negative_matches,
                    )
                )
                app_matches += 1
                if app_matches >= max_evidence_per_app:
                    break
            if app_matches:
                matched_apps += 1

        log.info(
            "RuStore direct scan: %d apps checked, %d apps with VPN evidence, %d evidence rows",
            min(len(packages), max_apps),
            matched_apps,
            len(evidence),
        )
        if search is not None:
            evidence.extend(self.scan_indexed_reviews(search))
        return evidence

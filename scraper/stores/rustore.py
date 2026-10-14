from __future__ import annotations

import logging
import re
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..evidence_engine import analyze_review, analyze_text
from ..models import Evidence, SearchHit
from .base import StoreMatch, StoreParser

log = logging.getLogger(__name__)

_VPN_TOKEN = re.compile(r"\b(?:vpn|впн|proxy|прокси)\b", re.I)


class RuStoreParser(StoreParser):
    store_id = "rustore"
    _path_re = re.compile(r"/catalog/app/([^/?#]+)")
    feedback_endpoint = "https://web-api.rustore.ru/v1/showcase/web/feedbacks/comments/{package_id}"

    # Search-engine discovery is kept as an additional source, but direct
    # feedback API scanning is the primary path now.
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

    @classmethod
    def feedback_url(cls, package_id: str) -> str:
        return cls.feedback_endpoint.format(package_id=package_id)

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
        max_apps: int = 80,
        expansion_pages: int = 16,
    ) -> dict[str, str]:
        """Take a bounded sample from current public catalogue pages."""
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
        per_query: int = 12,
        max_apps: int = 140,
    ) -> dict[str, str]:
        """Build a broad candidate pool through RuStore's public app search."""
        found: dict[str, str] = {}
        endpoint = "https://backapi.rustore.ru/applicationData/apps"
        for query in queries:
            if len(found) >= max_apps:
                break
            try:
                response = session.get(
                    endpoint,
                    params={"pageSize": per_query, "pageNumber": 0, "query": query},
                    headers={"ruStoreVerCode": "110802"},
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
        log.info("RuStore search discovery: %d apps", len(found))
        return found

    @staticmethod
    def _reply_text(reply: object) -> str:
        if not isinstance(reply, dict):
            return ""
        for key in ("comment", "text", "reply", "message"):
            value = reply.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @classmethod
    def reviews_from_payload(cls, payload: object) -> list[tuple[str, str, str | None]]:
        """Normalize RuStore feedback payload into (review, reply, date)."""
        if not isinstance(payload, dict):
            return []
        result: list[tuple[str, str, str | None]] = []
        for row in payload.get("elements") or []:
            if not isinstance(row, dict):
                continue
            comment = row.get("comment")
            if not isinstance(comment, str) or not comment.strip():
                continue
            replies = [cls._reply_text(item) for item in (row.get("replies") or [])]
            reply = " ".join(text for text in replies if text)
            result.append((comment.strip(), reply, row.get("commentDate")))
        return result

    def fetch_reviews_api(
        self,
        session: requests.Session,
        package_id: str,
        *,
        limit: int = 60,
        max_pages: int = 2,
    ) -> list[tuple[str, str, str | None]]:
        """Fetch actual RuStore reviews from the public web feedback endpoint."""
        url = self.feedback_url(package_id)
        reviews: list[tuple[str, str, str | None]] = []
        continuation: str | None = None
        seen_cursors: set[str] = set()

        for _ in range(max_pages):
            params: dict[str, object] = {"limit": limit, "sortBy": "NEW_FIRST"}
            if continuation and continuation not in {"0", "null", "None"}:
                params["continuation"] = continuation
            try:
                response = session.get(
                    url,
                    params=params,
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "Referer": self.reviews_url(package_id),
                        "Origin": "https://www.rustore.ru",
                    },
                    timeout=20,
                )
                if response.status_code == 404:
                    return reviews
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                log.debug("RuStore feedback API failed for %s: %s", package_id, exc)
                return reviews

            reviews.extend(self.reviews_from_payload(payload))
            next_cursor = str(payload.get("continuation") or "") if isinstance(payload, dict) else ""
            if not next_cursor or next_cursor in {"0", "null", "None"} or next_cursor in seen_cursors:
                break
            seen_cursors.add(next_cursor)
            continuation = next_cursor

        return reviews

    @staticmethod
    def _vpn_fragments(text: str, *, radius: int = 260, limit: int = 12) -> list[str]:
        """Fallback for HTML-only delivery if the feedback API changes."""
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

    def fetch_review_fragments(self, session: requests.Session, package_id: str) -> list[str]:
        url = self.reviews_url(package_id)
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            log.debug("RuStore review HTML failed for %s: %s", package_id, exc)
            return []
        return self._vpn_fragments(BeautifulSoup(response.text, "lxml").get_text(" ", strip=True))

    def scan_indexed_reviews(self, search, *, limit_per_phrase: int = 8) -> list[Evidence]:
        """Keep indexed review search as a supplementary discovery channel."""
        evidence: list[Evidence] = []
        seen: set[tuple[str, str, str]] = set()

        for phrase in self.REVIEW_SEARCH_PHRASES:
            query = f"site:rustore.ru/catalog/app {phrase}"
            try:
                hits = search.search(query, limit=limit_per_phrase)
            except Exception as exc:
                log.debug("RuStore indexed review search failed for %r: %s", phrase, exc)
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

    def discover_candidates(
        self,
        session: requests.Session,
        *,
        discovery_queries: list[str],
        priority_package_ids: list[str] | None,
        max_apps: int,
    ) -> dict[str, str]:
        """Mix known/watchlisted, search and catalogue candidates.

        The previous implementation filled max_apps from the first catalogue
        page before search results were appended, so search discovery was never
        scanned. Priority IDs are candidates only; they still need live review
        evidence before the shared evidence engine can confirm them.
        """
        result: dict[str, str] = {}
        for package_id in priority_package_ids or []:
            result.setdefault(package_id, package_id)
            if len(result) >= max_apps:
                return result

        search_budget = max(0, int(max_apps * 0.70) - len(result))
        if search_budget:
            searched = self.discover_search_api(
                session,
                discovery_queries,
                per_query=12,
                max_apps=search_budget,
            )
            for package_id, app_name in searched.items():
                result.setdefault(package_id, app_name)
                if len(result) >= max_apps:
                    return result

        catalog_budget = max_apps - len(result)
        if catalog_budget:
            catalog = self.discover_catalog(session, max_apps=catalog_budget)
            for package_id, app_name in catalog.items():
                result.setdefault(package_id, app_name)
                if len(result) >= max_apps:
                    break

        log.info("RuStore candidate pool: %d apps", len(result))
        return result

    def scan_reviews(
        self,
        session: requests.Session,
        *,
        search=None,
        discovery_queries: list[str] | None = None,
        priority_package_ids: list[str] | None = None,
        max_apps: int = 180,
        max_evidence_per_app: int = 3,
    ) -> list[Evidence]:
        packages = self.discover_candidates(
            session,
            discovery_queries=discovery_queries or [],
            priority_package_ids=priority_package_ids,
            max_apps=max_apps,
        )

        evidence: list[Evidence] = []
        matched_apps = 0
        api_reviews = 0
        for package_id, app_name in packages.items():
            reviews = self.fetch_reviews_api(session, package_id, limit=60, max_pages=2)
            api_reviews += len(reviews)
            app_matches = 0

            for review_text, developer_reply, published_at in reviews:
                classification = analyze_review(
                    review_text,
                    developer_reply,
                    app_name=None if app_name == package_id else app_name,
                )
                if classification.verdict not in {"positive", "negative"}:
                    continue
                snippet = review_text
                if developer_reply:
                    snippet = f"{snippet}\nDeveloper reply: {developer_reply}"
                evidence.append(
                    Evidence(
                        package_id=package_id,
                        app_name=None if app_name == package_id else app_name,
                        source_type="store",
                        source_id="rustore_reviews_api",
                        source_domain="rustore.ru",
                        url=self.reviews_url(package_id),
                        title=app_name,
                        snippet=snippet[:1200],
                        score=classification.score,
                        strong_matches=classification.strong_matches,
                        discovered_at=datetime.now(timezone.utc).isoformat(),
                        published_at=published_at,
                        store=self.store_id,
                        query="direct_store_api_scan",
                        verdict=classification.verdict,
                        confidence=classification.confidence,
                        negative_matches=classification.negative_matches,
                    )
                )
                app_matches += 1
                if app_matches >= max_evidence_per_app:
                    break

            # HTML fallback only when API gave us nothing at all for this app.
            if not reviews:
                for fragment in self.fetch_review_fragments(session, package_id):
                    classification = analyze_text(fragment, role="user_review", app_name=app_name)
                    if classification.verdict not in {"positive", "negative"}:
                        continue
                    evidence.append(
                        Evidence(
                            package_id=package_id,
                            app_name=None if app_name == package_id else app_name,
                            source_type="store",
                            source_id="rustore_reviews_html",
                            source_domain="rustore.ru",
                            url=self.reviews_url(package_id),
                            title=app_name,
                            snippet=fragment[:1200],
                            score=classification.score,
                            strong_matches=classification.strong_matches,
                            discovered_at=datetime.now(timezone.utc).isoformat(),
                            store=self.store_id,
                            query="direct_store_html_fallback",
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
            "RuStore direct scan: %d apps checked, %d reviews fetched, %d apps with VPN evidence, %d evidence rows",
            len(packages),
            api_reviews,
            matched_apps,
            len(evidence),
        )
        if search is not None:
            evidence.extend(self.scan_indexed_reviews(search))
        return evidence

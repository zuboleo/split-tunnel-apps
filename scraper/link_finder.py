from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .discovery import BingRssSearch
from .models import SearchHit

log = logging.getLogger(__name__)


class LinkFinder:
    """Parser #1: continuously discovers URLs that mention VPN restrictions."""

    def __init__(self, config_path: Path, search: BingRssSearch):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f) or {}
        self.search = search

    @property
    def combined_query(self) -> str:
        phrases = self.config.get("phrases", [])
        if not phrases:
            return '"отключите VPN" OR "не работает с VPN"'
        return "(" + " OR ".join(phrases) + ")"

    @staticmethod
    def _host_matches(host: str, domain: str) -> bool:
        host = (host or "").lower().rstrip(".")
        domain = (domain or "").lower().rstrip(".")
        return bool(domain) and (host == domain or host.endswith("." + domain))

    @property
    def article_domains(self) -> tuple[str, ...]:
        return tuple(
            str(source.get("domain") or "").lower()
            for source in self.config.get("source_domains", [])
            if source.get("enabled", True) and source.get("domain")
        )

    @property
    def store_domains(self) -> tuple[str, ...]:
        domains: list[str] = []
        for store in self.config.get("stores", []):
            if not store.get("enabled", True):
                continue
            domains.extend(str(domain).lower() for domain in store.get("domains", []) if domain)
        return tuple(domains)

    def is_article_source(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(self._host_matches(host, domain) for domain in self.article_domains)

    def is_store_source(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(self._host_matches(host, domain) for domain in self.store_domains)

    def _query(self, q: str, *, news: bool = False) -> list[SearchHit]:
        settings = self.config.get("search", {})
        limit = int(settings.get("max_results_per_query", 10))
        try:
            return self.search.search(q, limit=limit, news=news)
        except Exception as exc:  # one failed source must not abort the daily run
            log.warning("Search failed for %r: %s", q, exc)
            return []

    def discover(self, max_queries: int | None = None) -> list[SearchHit]:
        hits: list[SearchHit] = []
        queries_used = 0

        def add_query(q: str, *, news: bool = False) -> None:
            nonlocal queries_used
            if max_queries is not None and queries_used >= max_queries:
                return
            queries_used += 1
            hits.extend(self._query(q, news=news))

        base = self.combined_query

        # 10+ media/community sources, each searched dynamically rather than
        # repeatedly parsing a single hard-coded article.
        for source in self.config.get("source_domains", []):
            if not source.get("enabled", True):
                continue
            domain = source["domain"]
            add_query(f"site:{domain} {base}")

        # Store review/detail pages are the strongest source because their URL
        # often contains the Android package id directly.
        for store in self.config.get("stores", []):
            if not store.get("enabled", True):
                continue
            for domain in store.get("domains", []):
                add_query(f"site:{domain} {base}")

        # Generic sweeps are useful for surfacing candidates, but callers must
        # not fetch arbitrary third-party pages as articles. Only configured
        # article domains are eligible for article parsing; store URLs are
        # handled by their adapters.
        add_query(base)
        add_query(base, news=True)

        # Stable de-duplication. Same URL can occur for several phrases/sources.
        unique: dict[tuple[str, str], SearchHit] = {}
        for hit in hits:
            key = (hit.url, hit.snippet.strip())
            unique.setdefault(key, hit)
        log.info("Discovery: %d queries, %d unique hits", queries_used, len(unique))
        return list(unique.values())

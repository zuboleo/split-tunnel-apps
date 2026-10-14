from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from .article_parser import ArticleParser
from .dataset import build_apps, load_id_set, merge_evidence, save_json, write_outputs
from .discovery import BingRssSearch
from .evidence_engine import analyze_review, analyze_text
from .http import build_session, domain_of
from .link_finder import LinkFinder
from .models import Evidence, SearchHit
from .normalize import Normalizer
from .package_resolver import PackageResolver
from .seed import load_seed
from .stores import GooglePlayParser, RuStoreParser, parser_for_url

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, repo_root: Path):
        self.root = repo_root
        self.data = self.root / "data"
        self.public = self.root / "public"
        self.session = build_session()
        self.search = BingRssSearch(self.session)
        self.normalizer = Normalizer(self.root / "scraper" / "aliases.yaml")
        self.finder = LinkFinder(self.root / "scraper" / "discovery.yaml", self.search)
        self.article_parser = ArticleParser(self.session, self.normalizer)
        self.resolver = PackageResolver(
            self.root / "scraper" / "packages.yaml",
            self.data / "package_map.json",
            self.search,
        )
        self._dynamic_resolves_left = 0

    def _parse_store_hit(self, hit: SearchHit):
        parser = parser_for_url(hit.url)
        if not parser:
            return None, None

        match = parser.parse_hit(hit)
        if match.package_id:
            return parser, match

        try:
            response = self.session.get(hit.url, timeout=15)
            response.raise_for_status()
            match = parser.parse_hit(hit, response.text)
        except Exception as exc:
            log.debug("Store page metadata fetch failed for %s: %s", hit.url, exc)
        return parser, match

    def _evidence_from_store_hit(self, hit: SearchHit) -> Evidence | None:
        parser, match = self._parse_store_hit(hit)
        if not parser or not match or not match.package_id:
            return None

        classification = analyze_text(
            " ".join(x for x in (hit.title, hit.snippet) if x),
            role="search_snippet",
            app_name=match.app_name,
        )
        if classification.verdict not in {"positive", "negative"}:
            return None

        return Evidence(
            package_id=match.package_id,
            app_name=match.app_name,
            source_type="store",
            source_id=parser.store_id,
            source_domain=domain_of(hit.url),
            url=hit.url,
            title=hit.title,
            snippet=hit.snippet[:1200],
            score=classification.score,
            strong_matches=classification.strong_matches,
            discovered_at=datetime.now(timezone.utc).isoformat(),
            published_at=hit.published_at,
            store=parser.store_id,
            query=hit.query,
            verdict=classification.verdict,
            confidence=classification.confidence,
            negative_matches=classification.negative_matches,
        )

    def _evidence_from_article_hit(self, hit: SearchHit, allow_resolver_search: bool) -> list[Evidence]:
        doc = self.article_parser.parse(hit)
        if doc.classification.verdict not in {"positive", "negative"}:
            return []

        names = list(doc.known_apps)
        for candidate in doc.candidate_names:
            if candidate not in names:
                names.append(candidate)

        evidence: list[Evidence] = []
        known_names = [name for name in names if self.resolver.known(name)]
        unknown_names = [name for name in names if not self.resolver.known(name)][:3]
        selected_unknown: list[str] = []
        if allow_resolver_search and self._dynamic_resolves_left > 0:
            selected_unknown = unknown_names[: self._dynamic_resolves_left]
            self._dynamic_resolves_left -= len(selected_unknown)

        for name in known_names + selected_unknown:
            package_id = self.resolver.resolve(name, allow_search=allow_resolver_search)
            if not package_id:
                continue
            evidence.append(
                Evidence(
                    package_id=package_id,
                    app_name=name,
                    source_type="article",
                    source_id=domain_of(doc.url) or hit.provider,
                    source_domain=domain_of(doc.url) or domain_of(hit.url),
                    url=doc.url,
                    title=doc.title,
                    snippet=(doc.text or hit.snippet)[:1200],
                    score=doc.classification.score,
                    strong_matches=doc.classification.strong_matches,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    published_at=hit.published_at,
                    store=None,
                    query=hit.query,
                    verdict=doc.classification.verdict,
                    confidence=doc.classification.confidence,
                    negative_matches=doc.classification.negative_matches,
                )
            )
        return evidence

    def _deep_google_play_recheck(
        self,
        package_ids: list[str],
        limit_apps: int = 40,
        max_evidence_per_app: int = 3,
    ) -> list[Evidence]:
        parser = GooglePlayParser()
        evidence: list[Evidence] = []
        for package_id in package_ids[:limit_apps]:
            app_matches = 0
            for review_text, developer_reply in parser.fetch_recent_reviews(package_id, count=50):
                classification = analyze_review(review_text, developer_reply, app_name=package_id)
                if classification.verdict not in {"positive", "negative"}:
                    continue
                snippet = review_text.strip()
                if developer_reply:
                    snippet = f"{snippet}\nDeveloper reply: {developer_reply}".strip()
                evidence.append(
                    Evidence(
                        package_id=package_id,
                        app_name=None,
                        source_type="store",
                        source_id="google_play_reviews",
                        source_domain="play.google.com",
                        url=f"https://play.google.com/store/apps/details?id={package_id}",
                        title=package_id,
                        snippet=snippet[:1200],
                        score=classification.score,
                        strong_matches=classification.strong_matches,
                        discovered_at=datetime.now(timezone.utc).isoformat(),
                        store="google_play",
                        query="deep_review_recheck",
                        verdict=classification.verdict,
                        confidence=classification.confidence,
                        negative_matches=classification.negative_matches,
                    )
                )
                app_matches += 1
                if app_matches >= max_evidence_per_app:
                    break
        return evidence

    def run(self, *, offline: bool = False, max_queries: int | None = None, deep_store: bool = True) -> dict:
        seed = load_seed(self.data / "seed.json")
        evidence_path = self.data / "evidence.json"
        new_evidence: list[Evidence] = []

        if not offline:
            self._dynamic_resolves_left = 8
            hits = self.finder.discover(max_queries=max_queries)
            article_budget = 25
            article_count = 0
            for hit in hits:
                store_ev = self._evidence_from_store_hit(hit)
                if store_ev:
                    new_evidence.append(store_ev)
                    continue
                if article_count >= article_budget:
                    continue
                article_count += 1
                new_evidence.extend(self._evidence_from_article_hit(hit, allow_resolver_search=True))

            if deep_store:
                store_queries = [
                    "магазин", "банк", "доставка", "аптека", "транспорт",
                    "госуслуги", "маркет", "такси", "погода", "кино",
                    "работа", "жкх", "билеты", "еда", "здоровье",
                ]
                new_evidence.extend(
                    GooglePlayParser().scan_reviews(
                        store_queries,
                        per_query=10,
                        review_count=60,
                        max_apps=120,
                        max_evidence_per_app=3,
                    )
                )
                new_evidence.extend(
                    RuStoreParser().scan_reviews(
                        self.session,
                        search=self.search,
                        discovery_queries=store_queries,
                        max_apps=120,
                        max_evidence_per_app=3,
                    )
                )

                known_ids = sorted(set(seed) | {e.package_id for e in new_evidence if e.package_id})
                new_evidence.extend(
                    self._deep_google_play_recheck(
                        known_ids,
                        limit_apps=120,
                        max_evidence_per_app=3,
                    )
                )

        evidence_rows = merge_evidence(evidence_path, new_evidence)
        self.resolver.save()

        allowlist = load_id_set(self.data / "allowlist.txt")
        denylist = load_id_set(self.data / "denylist.txt")
        dataset = build_apps(evidence_rows, seed, allowlist, denylist)
        save_json(self.data / "apps.json", dataset)
        write_outputs(
            dataset,
            self.data / "app_ids.txt",
            self.public / "app_ids.txt",
            self.public / "status.json",
        )
        return dataset

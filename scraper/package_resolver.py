from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .discovery import BingRssSearch
from .models import SearchHit
from .stores import default_store_parsers

log = logging.getLogger(__name__)


def _norm_name(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _title_similarity(expected: str, actual: str) -> float:
    a = set(_norm_name(expected).split())
    b = set(_norm_name(actual).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


class PackageResolver:
    """Resolve an app name to Android package id and cache the result in a file."""

    def __init__(self, seed_path: Path, cache_path: Path, search: BingRssSearch):
        self.seed_path = seed_path
        self.cache_path = cache_path
        self.search = search
        with open(seed_path, "r", encoding="utf-8") as f:
            seed = yaml.safe_load(f) or {}
        self.seed: dict[str, str] = seed.get("packages", {})
        self.cache: dict[str, dict] = self._load_cache()
        self.parsers = default_store_parsers()

    def _load_cache(self) -> dict[str, dict]:
        if not self.cache_path.exists():
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2, sort_keys=True)

    def known(self, app_name: str) -> str | None:
        if app_name in self.seed:
            return self.seed[app_name]
        cached = self.cache.get(app_name)
        if cached:
            return cached.get("package_id")
        return None

    def resolve(self, app_name: str, allow_search: bool = True) -> str | None:
        known = self.known(app_name)
        if known or not allow_search:
            return known

        search_targets = [
            ("google_play", "play.google.com"),
            ("rustore", "rustore.ru"),
            ("samsung_galaxy_store", "galaxystore.samsung.com"),
            ("huawei_appgallery", "appgallery.cloud.huawei.com"),
        ]
        best: tuple[float, str, str, str] | None = None
        for store_id, site in search_targets:
            query = f'site:{site} "{app_name}"'
            try:
                hits = self.search.search(query, limit=5)
            except Exception as exc:
                log.debug("Resolver search failed for %s/%s: %s", app_name, store_id, exc)
                continue
            for hit in hits:
                for parser in self.parsers:
                    if not parser.matches(hit.url):
                        continue
                    match = parser.parse_hit(hit)
                    if not match.package_id:
                        continue
                    similarity = _title_similarity(app_name, match.app_name or hit.title)
                    if similarity < 0.5:
                        continue
                    candidate = (similarity, match.package_id, parser.store_id, hit.url)
                    if best is None or candidate[0] > best[0]:
                        best = candidate

        if best:
            _, package_id, store_id, url = best
            self.cache[app_name] = {"package_id": package_id, "store": store_id, "url": url}
            return package_id
        return None

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class GooglePlayParser:
    def discover_packages(self, queries: list[str], *, per_query: int = 10, max_apps: int = 140) -> dict[str, str]:
        try:
            from google_play_scraper import search
        except Exception as exc:
            log.warning("Google Play search unavailable: %s", exc)
            return {}

        found: dict[str, str] = {}
        # RU search is primary, but a second EN/US pass is important because
        # globally popular apps can be absent or poorly ranked in RU search.
        locales = (("ru", "ru"), ("en", "us"))
        for query in queries:
            if len(found) >= max_apps:
                break
            for lang, country in locales:
                if len(found) >= max_apps:
                    break
                try:
                    rows = search(query, lang=lang, country=country, n_hits=per_query)
                except Exception as exc:
                    log.warning("Google Play search failed for %r (%s/%s): %s", query, lang, country, exc)
                    continue
                for row in rows:
                    package_id = row.get("appId")
                    if package_id:
                        found.setdefault(package_id, row.get("title") or package_id)
                    if len(found) >= max_apps:
                        break
        return found

    def fetch_recent_reviews(self, package_id: str, *, count: int = 80) -> list[tuple[str, str]]:
        try:
            from google_play_scraper import Sort, reviews

            rows, _ = reviews(package_id, lang="ru", country="ru", sort=Sort.NEWEST, count=count)
        except Exception as exc:
            log.debug("Google Play reviews failed for %s: %s", package_id, exc)
            return []

        result: list[tuple[str, str]] = []
        for row in rows:
            review = (row.get("content") or "").strip()
            reply = (row.get("replyContent") or "").strip()
            if review or reply:
                result.append((review, reply))
        return result

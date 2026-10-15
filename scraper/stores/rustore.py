from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


class RuStoreParser:
    feedback_endpoint = "https://web-api.rustore.ru/v1/showcase/web/feedbacks/comments/{package_id}"

    def discover_search_api(
        self,
        session: requests.Session,
        queries: list[str],
        *,
        per_query: int = 12,
        max_apps: int = 160,
    ) -> dict[str, str]:
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
                rows = ((response.json() or {}).get("body") or {}).get("content") or []
            except Exception as exc:
                log.debug("RuStore search failed for %r: %s", query, exc)
                continue

            for row in rows:
                package_id = row.get("packageName")
                if package_id:
                    found.setdefault(package_id, row.get("appName") or package_id)
                if len(found) >= max_apps:
                    break
        return found

    def discover_catalog(self, session: requests.Session, *, max_apps: int = 80) -> dict[str, str]:
        try:
            response = session.get("https://www.rustore.ru/catalog", timeout=20)
            response.raise_for_status()
        except Exception as exc:
            log.debug("RuStore catalog failed: %s", exc)
            return {}

        found: dict[str, str] = {}
        soup = BeautifulSoup(response.text, "lxml")
        for link in soup.find_all("a", href=True):
            path = urlparse(link["href"]).path
            marker = "/catalog/app/"
            if marker not in path:
                continue
            package_id = path.split(marker, 1)[1].split("/", 1)[0]
            if package_id:
                found.setdefault(package_id, link.get_text(" ", strip=True) or package_id)
            if len(found) >= max_apps:
                break
        return found

    def discover_packages(
        self,
        session: requests.Session,
        queries: list[str],
        *,
        priority: set[str] | None = None,
        max_apps: int = 200,
    ) -> dict[str, str]:
        found = {package_id: package_id for package_id in sorted(priority or set())}
        searched = self.discover_search_api(session, queries, max_apps=max_apps)
        for package_id, name in searched.items():
            found.setdefault(package_id, name)
            if len(found) >= max_apps:
                return found
        for package_id, name in self.discover_catalog(session, max_apps=max_apps - len(found)).items():
            found.setdefault(package_id, name)
            if len(found) >= max_apps:
                break
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

    def fetch_recent_reviews(
        self,
        session: requests.Session,
        package_id: str,
        *,
        limit: int = 60,
        max_pages: int = 2,
    ) -> list[tuple[str, str]]:
        url = self.feedback_endpoint.format(package_id=package_id)
        result: list[tuple[str, str]] = []
        continuation: str | None = None
        seen: set[str] = set()

        for _ in range(max_pages):
            params: dict[str, object] = {"limit": limit, "sortBy": "NEW_FIRST"}
            if continuation:
                params["continuation"] = continuation
            try:
                response = session.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json, text/plain, */*", "Origin": "https://www.rustore.ru"},
                    timeout=20,
                )
                if response.status_code == 404:
                    break
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                log.debug("RuStore reviews failed for %s: %s", package_id, exc)
                break

            for row in payload.get("elements") or []:
                if not isinstance(row, dict):
                    continue
                review = str(row.get("comment") or "").strip()
                replies = [self._reply_text(item) for item in (row.get("replies") or [])]
                reply = " ".join(value for value in replies if value)
                if review or reply:
                    result.append((review, reply))

            next_cursor = str(payload.get("continuation") or "")
            if not next_cursor or next_cursor in {"0", "null", "None"} or next_cursor in seen:
                break
            seen.add(next_cursor)
            continuation = next_cursor

        return result

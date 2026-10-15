from __future__ import annotations

import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import requests

from .context_extractor import extract_vpn_contexts
from .deepseek_classifier import DeepSeekClassifier
from .stores.google_play import GooglePlayParser
from .stores.rustore import RuStoreParser

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
DIRECT_FILE = PUBLIC / "direct_apps.txt"
PROXY_FILE = PUBLIC / "proxy_apps.txt"

APP_QUERIES = [
    "банк",
    "магазин",
    "маркетплейс",
    "доставка",
    "еда",
    "такси",
    "транспорт",
    "билеты",
    "путешествия",
    "кино",
    "видео",
    "музыка",
    "соцсеть",
    "мессенджер",
    "госуслуги",
    "жкх",
    "здоровье",
    "аптека",
    "погода",
    "работа",
]

MAX_CONTEXTS_PER_SOURCE_ROLE = 10
MAX_CONTEXTS_PER_APP = 12
MAX_DEVELOPER_CONTEXTS_PER_APP = 2

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ContextItem:
    source: str
    role: str
    text: str

    def as_payload(self) -> dict[str, str]:
        return {"source": self.source, "role": self.role, "text": self.text}


def _read_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        value.strip()
        for value in path.read_text(encoding="utf-8").replace("\n", ",").split(",")
        if value.strip()
    }


def _write_ids(path: Path, values: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(",".join(sorted(values)) + "\n", encoding="utf-8")


def _add_text(
    contexts: dict[str, list[ContextItem]],
    package_id: str,
    text: str,
    *,
    source: str,
    role: str,
) -> None:
    bucket = contexts[package_id]
    same_bucket = sum(1 for item in bucket if item.source == source and item.role == role)
    if same_bucket >= MAX_CONTEXTS_PER_SOURCE_ROLE:
        return

    existing = {item.text.casefold() for item in bucket}
    for fragment in extract_vpn_contexts(text):
        key = fragment.casefold()
        if key in existing:
            continue
        bucket.append(ContextItem(source=source, role=role, text=fragment))
        existing.add(key)
        same_bucket += 1
        if same_bucket >= MAX_CONTEXTS_PER_SOURCE_ROLE:
            break


def _round_robin(items: list[ContextItem], *, limit: int, seen: set[str]) -> list[ContextItem]:
    by_source: dict[str, list[ContextItem]] = defaultdict(list)
    for item in items:
        by_source[item.source].append(item)

    result: list[ContextItem] = []
    sources = sorted(by_source)
    index = 0
    while len(result) < limit:
        added = False
        for source in sources:
            source_items = by_source[source]
            if index >= len(source_items):
                continue
            item = source_items[index]
            key = item.text.casefold()
            if key not in seen:
                seen.add(key)
                result.append(item)
                added = True
                if len(result) >= limit:
                    break
        if not added and all(index >= len(by_source[source]) - 1 for source in sources):
            break
        index += 1
    return result


def select_contexts(items: list[ContextItem]) -> list[ContextItem]:
    """Keep a small source-balanced evidence packet for one app.

    User reviews are primary evidence. Developer replies are included only as a
    small supplement so boilerplate support answers cannot dominate the model.
    """
    seen: set[str] = set()
    reviews = [item for item in items if item.role == "review"]
    replies = [item for item in items if item.role == "developer_reply"]

    selected = _round_robin(
        reviews,
        limit=MAX_CONTEXTS_PER_APP - MAX_DEVELOPER_CONTEXTS_PER_APP,
        seen=seen,
    )
    remaining = MAX_CONTEXTS_PER_APP - len(selected)
    if remaining:
        selected.extend(
            _round_robin(
                replies,
                limit=min(MAX_DEVELOPER_CONTEXTS_PER_APP, remaining),
                seen=seen,
            )
        )
    return selected


def collect_contexts(priority: set[str] | None = None) -> tuple[dict[str, str], dict[str, list[ContextItem]]]:
    priority = set(priority or set())
    names: dict[str, str] = {package_id: package_id for package_id in priority}
    raw_contexts: dict[str, list[ContextItem]] = defaultdict(list)

    session = requests.Session()
    session.headers.update({"User-Agent": "split-tunnel-apps/1.0"})

    google = GooglePlayParser()
    google_packages = google.discover_packages(APP_QUERIES, per_query=10, max_apps=140)
    for package_id in priority:
        google_packages.setdefault(package_id, package_id)
    names.update(google_packages)

    for package_id, app_name in google_packages.items():
        names[package_id] = app_name or package_id
        for review, reply in google.fetch_recent_reviews(package_id, count=80):
            _add_text(raw_contexts, package_id, review, source="google_play", role="review")
            _add_text(raw_contexts, package_id, reply, source="google_play", role="developer_reply")

    rustore = RuStoreParser()
    rustore_packages = rustore.discover_packages(
        session,
        APP_QUERIES,
        priority=priority,
        max_apps=200,
    )
    for package_id, app_name in rustore_packages.items():
        if app_name and app_name != package_id:
            names[package_id] = app_name
        for review, reply in rustore.fetch_recent_reviews(session, package_id, limit=60, max_pages=2):
            _add_text(raw_contexts, package_id, review, source="rustore", role="review")
            _add_text(raw_contexts, package_id, reply, source="rustore", role="developer_reply")

    contexts = {
        package_id: selected
        for package_id, items in raw_contexts.items()
        if (selected := select_contexts(items))
    }
    log.info("Collected VPN contexts for %d apps", len(contexts))
    return names, contexts


def classify_contexts(
    classifier: DeepSeekClassifier,
    names: dict[str, str],
    contexts: dict[str, list[ContextItem]],
) -> tuple[set[str], set[str], int]:
    direct: set[str] = set()
    proxy: set[str] = set()
    skipped = 0

    for package_id, items in sorted(contexts.items()):
        payload = [item.as_payload() for item in items]
        try:
            route = classifier.classify(package_id, names.get(package_id), payload)
        except Exception as exc:
            raise RuntimeError(
                f"Classification failed for {package_id}; refusing to overwrite public lists"
            ) from exc

        if route == "DIRECT":
            direct.add(package_id)
        elif route == "PROXY":
            proxy.add(package_id)
        else:
            skipped += 1

    return direct, proxy, skipped


def run() -> tuple[set[str], set[str]]:
    # Previous public lists are used only to make sure known packages are scanned
    # again. Their classifications are never carried into the new result.
    priority = _read_ids(DIRECT_FILE) | _read_ids(PROXY_FILE)
    names, contexts = collect_contexts(priority=priority)
    if not contexts:
        raise RuntimeError("No VPN contexts collected; refusing to overwrite public lists")

    classifier = DeepSeekClassifier.from_env()
    direct, proxy, skipped = classify_contexts(classifier, names, contexts)
    if not direct and not proxy:
        raise RuntimeError("DeepSeek classified every app as SKIP; refusing to overwrite public lists")

    # Write only after the complete classification succeeds. A partial API/store
    # failure must not publish half-built lists.
    _write_ids(DIRECT_FILE, direct)
    _write_ids(PROXY_FILE, proxy)
    log.info(
        "Done: %d apps checked, %d skipped, %d DIRECT, %d PROXY",
        len(contexts),
        skipped,
        len(direct),
        len(proxy),
    )
    return direct, proxy


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

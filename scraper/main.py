from __future__ import annotations

import logging
import sys
from collections import defaultdict
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

MAX_CONTEXTS_PER_APP = 12

log = logging.getLogger(__name__)


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


def _add_text(contexts: dict[str, list[str]], package_id: str, text: str, role: str) -> None:
    if len(contexts[package_id]) >= MAX_CONTEXTS_PER_APP:
        return
    for fragment in extract_vpn_contexts(text):
        item = f"{role}: {fragment}"
        if item not in contexts[package_id]:
            contexts[package_id].append(item)
        if len(contexts[package_id]) >= MAX_CONTEXTS_PER_APP:
            break


def collect_contexts() -> tuple[dict[str, str], dict[str, list[str]]]:
    direct = _read_ids(DIRECT_FILE)
    proxy = _read_ids(PROXY_FILE)
    known = direct | proxy

    names: dict[str, str] = {package_id: package_id for package_id in known}
    contexts: dict[str, list[str]] = defaultdict(list)

    session = requests.Session()
    session.headers.update({"User-Agent": "split-tunnel-apps/1.0"})

    google = GooglePlayParser()
    google_packages = google.discover_packages(APP_QUERIES, per_query=10, max_apps=140)
    for package_id in known:
        google_packages.setdefault(package_id, package_id)
    names.update(google_packages)

    for package_id, app_name in google_packages.items():
        names[package_id] = app_name or package_id
        for review, reply in google.fetch_recent_reviews(package_id, count=80):
            _add_text(contexts, package_id, review, "review")
            _add_text(contexts, package_id, reply, "developer_reply")
            if len(contexts[package_id]) >= MAX_CONTEXTS_PER_APP:
                break

    rustore = RuStoreParser()
    rustore_packages = rustore.discover_packages(
        session,
        APP_QUERIES,
        priority=known,
        max_apps=200,
    )
    for package_id, app_name in rustore_packages.items():
        if app_name and app_name != package_id:
            names[package_id] = app_name
        for review, reply in rustore.fetch_recent_reviews(session, package_id, limit=60, max_pages=2):
            _add_text(contexts, package_id, review, "review")
            _add_text(contexts, package_id, reply, "developer_reply")
            if len(contexts[package_id]) >= MAX_CONTEXTS_PER_APP:
                break

    return names, dict(contexts)


def run() -> tuple[set[str], set[str]]:
    classifier = DeepSeekClassifier.from_env()
    direct = _read_ids(DIRECT_FILE)
    proxy = _read_ids(PROXY_FILE)
    names, contexts = collect_contexts()

    classified = 0
    failed = 0
    for package_id, fragments in sorted(contexts.items()):
        if not fragments:
            continue
        try:
            route = classifier.classify(package_id, names.get(package_id), fragments)
        except Exception as exc:
            failed += 1
            log.warning("DeepSeek classification failed for %s: %s", package_id, exc)
            continue

        classified += 1
        if route == "DIRECT":
            direct.add(package_id)
            proxy.discard(package_id)
        else:
            proxy.add(package_id)
            direct.discard(package_id)

    _write_ids(DIRECT_FILE, direct)
    _write_ids(PROXY_FILE, proxy)
    log.info(
        "Done: %d classified, %d failed, %d DIRECT, %d PROXY",
        classified,
        failed,
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

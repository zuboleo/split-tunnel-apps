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

# Tiny manual safety net for routes that were verified independently of noisy
# store reviews. This is code/config, not persisted evidence. Everything else
# must be rediscovered and justified by the current run.
VERIFIED_DIRECT = {"ru.dns.shop.android"}
VERIFIED_PROXY = {"com.google.android.youtube"}

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

MAX_REPORTS_PER_SOURCE = 16
MAX_REPORTS_PER_APP = 10
MAX_DEVELOPER_ONLY_REPORTS = 1
MAX_FRAGMENTS_PER_TEXT = 2
GOOGLE_REVIEW_COUNT = 160
GOOGLE_PRIORITY_REVIEW_COUNT = 600
RUSTORE_REVIEW_PAGES = 3
RUSTORE_PRIORITY_REVIEW_PAGES = 8

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReviewReport:
    """One independent store review and its developer reply.

    Only extracted VPN sentences are kept. The full review never leaves the
    current process and is never persisted.
    """

    source: str
    review: tuple[str, ...]
    developer_reply: tuple[str, ...]

    @property
    def has_user_context(self) -> bool:
        return bool(self.review)

    def dedupe_key(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            tuple(value.casefold() for value in self.review),
            tuple(value.casefold() for value in self.developer_reply),
        )

    def as_payload(self, report_id: str) -> dict[str, object]:
        return {
            "report_id": report_id,
            "source": self.source,
            "review": list(self.review),
            "developer_reply": list(self.developer_reply),
        }


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


def _extract(text: str) -> tuple[str, ...]:
    return tuple(extract_vpn_contexts(text)[:MAX_FRAGMENTS_PER_TEXT])


def _add_report(
    reports: dict[str, list[ReviewReport]],
    package_id: str,
    review: str,
    developer_reply: str,
    *,
    source: str,
) -> None:
    review_context = _extract(review)
    reply_context = _extract(developer_reply)
    if not review_context and not reply_context:
        return

    bucket = reports[package_id]
    if sum(item.source == source for item in bucket) >= MAX_REPORTS_PER_SOURCE:
        return

    report = ReviewReport(source=source, review=review_context, developer_reply=reply_context)
    key = report.dedupe_key()
    if any(item.dedupe_key() == key for item in bucket):
        return
    bucket.append(report)


def _round_robin_reports(
    reports: list[ReviewReport],
    *,
    limit: int,
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]],
) -> list[ReviewReport]:
    by_source: dict[str, list[ReviewReport]] = defaultdict(list)
    for report in reports:
        by_source[report.source].append(report)

    selected: list[ReviewReport] = []
    sources = sorted(by_source)
    index = 0
    while len(selected) < limit:
        any_remaining = False
        for source in sources:
            source_reports = by_source[source]
            if index >= len(source_reports):
                continue
            any_remaining = True
            report = source_reports[index]
            key = report.dedupe_key()
            if key in seen:
                continue
            seen.add(key)
            selected.append(report)
            if len(selected) >= limit:
                break
        if not any_remaining:
            break
        index += 1
    return selected


def select_reports(reports: list[ReviewReport]) -> list[ReviewReport]:
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    user_reports = [report for report in reports if report.has_user_context]
    developer_only = [report for report in reports if not report.has_user_context]

    selected = _round_robin_reports(
        user_reports,
        limit=MAX_REPORTS_PER_APP - MAX_DEVELOPER_ONLY_REPORTS,
        seen=seen,
    )
    remaining = MAX_REPORTS_PER_APP - len(selected)
    if remaining:
        selected.extend(
            _round_robin_reports(
                developer_only,
                limit=min(MAX_DEVELOPER_ONLY_REPORTS, remaining),
                seen=seen,
            )
        )
    return selected


def collect_reports(priority: set[str] | None = None) -> tuple[dict[str, str], dict[str, list[ReviewReport]]]:
    priority = set(priority or set())
    names: dict[str, str] = {package_id: package_id for package_id in priority}
    raw_reports: dict[str, list[ReviewReport]] = defaultdict(list)

    session = requests.Session()
    session.headers.update({"User-Agent": "split-tunnel-apps/1.0"})

    google = GooglePlayParser()
    google_packages = google.discover_packages(APP_QUERIES, per_query=10, max_apps=160)
    for package_id in priority:
        google_packages.setdefault(package_id, package_id)
    names.update(google_packages)

    for package_id, app_name in google_packages.items():
        names[package_id] = app_name or package_id
        count = GOOGLE_PRIORITY_REVIEW_COUNT if package_id in priority else GOOGLE_REVIEW_COUNT
        for review, reply in google.fetch_recent_reviews(package_id, count=count):
            _add_report(raw_reports, package_id, review, reply, source="google_play")

    rustore = RuStoreParser()
    rustore_packages = rustore.discover_packages(
        session,
        APP_QUERIES,
        priority=priority,
        max_apps=220,
    )
    for package_id, app_name in rustore_packages.items():
        if app_name and app_name != package_id:
            names[package_id] = app_name
        pages = RUSTORE_PRIORITY_REVIEW_PAGES if package_id in priority else RUSTORE_REVIEW_PAGES
        for review, reply in rustore.fetch_recent_reviews(
            session,
            package_id,
            limit=60,
            max_pages=pages,
        ):
            _add_report(raw_reports, package_id, review, reply, source="rustore")

    reports = {
        package_id: selected
        for package_id, items in raw_reports.items()
        if (selected := select_reports(items))
    }
    log.info("Collected VPN reports for %d apps", len(reports))
    return names, reports


def classify_reports(
    classifier: DeepSeekClassifier,
    names: dict[str, str],
    reports: dict[str, list[ReviewReport]],
) -> tuple[set[str], set[str], int]:
    direct: set[str] = set()
    proxy: set[str] = set()
    skipped = 0

    for package_id, app_reports in sorted(reports.items()):
        # Manually verified routes do not need to spend a model request and
        # cannot be knocked out by a random fresh review.
        if package_id in VERIFIED_DIRECT or package_id in VERIFIED_PROXY:
            continue

        payload = [report.as_payload(f"r{index}") for index, report in enumerate(app_reports, start=1)]
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

    direct |= VERIFIED_DIRECT
    proxy |= VERIFIED_PROXY
    direct -= proxy
    return direct, proxy, skipped


def run() -> tuple[set[str], set[str]]:
    previous = _read_ids(DIRECT_FILE) | _read_ids(PROXY_FILE)
    priority = previous | VERIFIED_DIRECT | VERIFIED_PROXY

    names, reports = collect_reports(priority=priority)
    if not reports:
        raise RuntimeError("No VPN reports collected; refusing to overwrite public lists")

    classifier = DeepSeekClassifier.from_env()
    direct, proxy, skipped = classify_reports(classifier, names, reports)
    if not direct and not proxy:
        raise RuntimeError("No publishable routes found; refusing to overwrite public lists")

    # Public lists are rebuilt from the current model result plus the tiny
    # independently verified safety net. Old model decisions are not durable.
    _write_ids(DIRECT_FILE, direct)
    _write_ids(PROXY_FILE, proxy)
    log.info(
        "Done: %d apps checked, %d skipped, %d DIRECT, %d PROXY",
        len(reports),
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

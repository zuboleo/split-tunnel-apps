from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .orchestrator import Orchestrator

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Track Android apps that detect/block VPN connections")
    p.add_argument("--offline", action="store_true", help="Do not use network; rebuild outputs from saved data/seeds")
    p.add_argument("--max-queries", type=int, default=None, help="Limit discovery queries (useful for manual tests)")
    p.add_argument("--no-deep-store", action="store_true", help="Skip Google Play recent-review recheck")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    dataset = Orchestrator(REPO_ROOT).run(
        offline=args.offline,
        max_queries=args.max_queries,
        deep_store=not args.no_deep_store,
    )
    confirmed = sum(1 for app in dataset.get("apps", []) if app.get("status") == "confirmed")
    candidates = sum(1 for app in dataset.get("apps", []) if app.get("status") == "candidate")
    logging.info("Done: %d confirmed, %d candidates", confirmed, candidates)
    return 0


if __name__ == "__main__":
    sys.exit(main())

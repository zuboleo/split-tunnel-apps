from __future__ import annotations

from dataclasses import dataclass

from ..models import SearchHit


@dataclass(slots=True)
class StoreMatch:
    store: str
    package_id: str | None
    app_name: str | None


class StoreParser:
    store_id = "base"

    def matches(self, url: str) -> bool:
        raise NotImplementedError

    def parse_hit(self, hit: SearchHit, html: str | None = None) -> StoreMatch:
        raise NotImplementedError

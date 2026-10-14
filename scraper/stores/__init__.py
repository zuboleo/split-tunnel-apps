from __future__ import annotations

from .base import StoreMatch, StoreParser
from .google_play import GooglePlayParser
from .huawei import HuaweiAppGalleryParser
from .rustore import RuStoreParser
from .samsung import SamsungStoreParser


def default_store_parsers() -> list[StoreParser]:
    return [
        GooglePlayParser(),
        RuStoreParser(),
        SamsungStoreParser(),
        HuaweiAppGalleryParser(),
    ]


def parser_for_url(url: str) -> StoreParser | None:
    for parser in default_store_parsers():
        if parser.matches(url):
            return parser
    return None


__all__ = [
    "StoreMatch",
    "StoreParser",
    "GooglePlayParser",
    "RuStoreParser",
    "SamsungStoreParser",
    "HuaweiAppGalleryParser",
    "default_store_parsers",
    "parser_for_url",
]

"""Normalize raw app names extracted from articles to canonical names.

Uses scraper/aliases.yaml to map variations like "яндекс.пэй" -> "Яндекс Пэй".
Anything that contains a known alias as a substring is considered a match.
Unknown items are dropped (configurable) to keep noise out of the final list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AppDefinition:
    canonical: str
    category: str
    aliases: list[str]


class Normalizer:
    def __init__(self, aliases_path: Path):
        with open(aliases_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.default_category = data.get("default_category", "other")
        self.apps: list[AppDefinition] = []
        for canonical, info in data.get("apps", {}).items():
            self.apps.append(
                AppDefinition(
                    canonical=canonical,
                    category=info.get("category", self.default_category),
                    aliases=[a.lower().strip() for a in info.get("aliases", [])],
                )
            )

    @staticmethod
    def _normalize_text(s: str) -> str:
        """Lowercase, collapse whitespace, normalize dashes."""
        s = s.lower().strip()
        s = re.sub(r"\s+", " ", s)
        s = s.replace("ё", "е")  # treat ё/е as equivalent
        return s

    def match(self, raw_text: str) -> AppDefinition | None:
        """Return the AppDefinition matching the raw text, or None.

        Matching strategy: tokenize the raw text and check if any alias
        appears as a substring. The longest matching alias wins to avoid
        false positives (e.g. "Яндекс" matching "Яндекс Пэй").
        """
        normalized = self._normalize_text(raw_text)

        best_match: AppDefinition | None = None
        best_len = 0
        for app in self.apps:
            for alias in app.aliases:
                alias_norm = self._normalize_text(alias)
                if alias_norm in normalized and len(alias_norm) > best_len:
                    best_match = app
                    best_len = len(alias_norm)
        return best_match

    def match_all(self, raw_text: str) -> list[AppDefinition]:
        """Return every known app mentioned in the text, de-duplicated."""
        normalized = self._normalize_text(raw_text)
        found: list[AppDefinition] = []
        seen: set[str] = set()
        for app in self.apps:
            if app.canonical in seen:
                continue
            for alias in app.aliases:
                alias_norm = self._normalize_text(alias)
                if alias_norm and alias_norm in normalized:
                    seen.add(app.canonical)
                    found.append(app)
                    break
        return found

    def normalize_list(self, raw_items: list[str]) -> list[AppDefinition]:
        """Map a list of raw strings to a deduplicated list of AppDefinitions."""
        seen: set[str] = set()
        result: list[AppDefinition] = []
        for raw in raw_items:
            match = self.match(raw)
            if match and match.canonical not in seen:
                seen.add(match.canonical)
                result.append(match)
        return result

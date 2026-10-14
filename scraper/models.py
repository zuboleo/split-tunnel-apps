from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256


@dataclass(slots=True)
class SearchHit:
    provider: str
    query: str
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None


@dataclass(slots=True)
class Classification:
    relevant: bool
    score: int
    strong_matches: list[str] = field(default_factory=list)
    weak_matches: list[str] = field(default_factory=list)
    verdict: str = "neutral"
    confidence: float = 0.0
    negative_matches: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedDocument:
    url: str
    title: str
    text: str
    classification: Classification
    known_apps: list[str] = field(default_factory=list)
    candidate_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Evidence:
    package_id: str | None
    app_name: str | None
    source_type: str
    source_id: str
    source_domain: str
    url: str
    title: str
    snippet: str
    score: int
    strong_matches: list[str]
    discovered_at: str
    published_at: str | None = None
    store: str | None = None
    query: str | None = None
    verdict: str = "positive"
    confidence: float = 0.0
    negative_matches: list[str] = field(default_factory=list)

    @property
    def fingerprint(self) -> str:
        payload = "\n".join(
            [
                self.package_id or "",
                self.app_name or "",
                self.source_type,
                self.source_id,
                self.url,
                self.title,
                self.snippet,
                self.verdict,
            ]
        )
        return sha256(payload.encode("utf-8", errors="ignore")).hexdigest()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["fingerprint"] = self.fingerprint
        return data

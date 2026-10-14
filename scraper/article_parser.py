from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from .evidence_engine import analyze_text
from .models import ParsedDocument, SearchHit
from .normalize import Normalizer


_CANDIDATE_PATTERNS = [
    re.compile(r"[«\"]([^»\"]{2,60})[»\"]"),
    re.compile(r"(?:приложени(?:е|я)|сервис(?:а|е)?|сайт(?:а|е)?)\s+([A-ZА-ЯЁ0-9][\wА-Яа-яЁё0-9 .&+\-]{1,45})", re.I),
]
_STOP = {
    "vpn", "впн", "прокси", "proxy", "приложение", "сервис", "сайт", "пользователь",
    "россия", "россии", "android", "google play", "rustore", "ru store",
}


def _clean_candidate(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .,:;!?—–-\"'«»")
    value = re.split(r"\s+(?:требует|просит|не\s+работает|блокирует|обнаруживает)\b", value, maxsplit=1, flags=re.I)[0]
    return value[:60].strip()


def _extract_candidate_names(text: str, title: str) -> list[str]:
    candidates: list[str] = []
    title_part = re.split(r"[|—–:]", title, maxsplit=1)[0].strip()
    if 2 <= len(title_part) <= 60:
        candidates.append(title_part)

    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if not re.search(r"\b(?:vpn|впн|proxy|прокси)\b", sentence, re.I):
            continue
        for pattern in _CANDIDATE_PATTERNS:
            for match in pattern.findall(sentence):
                candidates.append(_clean_candidate(match))

    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        item = _clean_candidate(item)
        key = item.lower().replace("ё", "е")
        if not item or key in _STOP or len(item) < 2 or len(item.split()) > 8:
            continue
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result[:20]


class ArticleParser:
    """Fetch discovered pages and route their text through the shared engine."""

    def __init__(self, session: requests.Session, normalizer: Normalizer):
        self.session = session
        self.normalizer = normalizer

    def parse(self, hit: SearchHit) -> ParsedDocument:
        title = hit.title
        page_text = ""
        final_url = hit.url
        try:
            response = self.session.get(hit.url, timeout=20, allow_redirects=True)
            response.raise_for_status()
            final_url = response.url
            soup = BeautifulSoup(response.text, "lxml")
            if soup.title and soup.title.get_text(strip=True):
                title = soup.title.get_text(" ", strip=True)
            for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
                tag.decompose()
            main = soup.find("article") or soup.find("main") or soup.body or soup
            page_text = main.get_text(" ", strip=True)
        except Exception:
            page_text = ""

        combined = " ".join(part for part in (title, hit.snippet, page_text) if part)
        classification = analyze_text(combined, role="article", app_name=title)
        known_apps = [app.canonical for app in self.normalizer.match_all(combined)]
        candidates = _extract_candidate_names(combined, title)

        return ParsedDocument(
            url=final_url,
            title=title,
            text=combined,
            classification=classification,
            known_apps=known_apps,
            candidate_names=candidates,
        )

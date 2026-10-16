from __future__ import annotations

import re

VPN_RE = re.compile(r"(?<![\w])(?:vpn|впн)(?![\w])", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"\S+")


def contains_vpn(text: str) -> bool:
    return bool(text and VPN_RE.search(text))


def _window(sentence: str, match: re.Match[str], radius: int) -> str:
    words = list(_WORD_RE.finditer(sentence))
    if not words:
        return sentence.strip()

    anchor = 0
    for index, word in enumerate(words):
        if word.start() <= match.start() < word.end() or word.start() < match.end() <= word.end():
            anchor = index
            break

    start = max(0, anchor - radius)
    end = min(len(words), anchor + radius + 1)
    return " ".join(word.group(0) for word in words[start:end]).strip()


def extract_vpn_contexts(
    text: str,
    *,
    max_sentence_words: int = 40,
    fallback_radius: int = 10,
) -> list[str]:
    """Return only short local contexts that contain VPN/ВПН.

    Prefer a complete sentence. If punctuation is missing or the sentence is too
    long, keep only up to `fallback_radius` words on each side of the VPN token.
    """
    if not text or not contains_vpn(text):
        return []

    normalized = re.sub(r"\s+", " ", text).strip()
    sentences = _SENTENCE_SPLIT_RE.split(normalized)
    result: list[str] = []
    seen: set[str] = set()

    for sentence in sentences:
        matches = list(VPN_RE.finditer(sentence))
        if not matches:
            continue

        word_count = len(_WORD_RE.findall(sentence))
        candidates = [sentence.strip()] if word_count <= max_sentence_words else [
            _window(sentence, match, fallback_radius) for match in matches
        ]

        for candidate in candidates:
            candidate = candidate.strip()
            key = candidate.casefold()
            if candidate and key not in seen:
                seen.add(key)
                result.append(candidate)

    return result

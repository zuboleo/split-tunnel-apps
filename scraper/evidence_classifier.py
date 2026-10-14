from __future__ import annotations

import re

from .models import Classification


# Strong phrases mean that VPN/proxy is explicitly detected, rejected or must be disabled.
STRONG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("disable_vpn_ru", re.compile(r"(?:отключ(?:ите|ить)|выключ(?:ите|ить))[^.!?]{0,45}\b(?:vpn|впн)\b", re.I)),
    ("vpn_detected_ru", re.compile(r"\b(?:vpn|впн)\b[^.!?]{0,45}(?:обнаружен|обнаружено|активен|включен|включён)", re.I)),
    ("detected_vpn_ru", re.compile(r"(?:обнаружен|обнаружено|определяет|распозна[её]т)[^.!?]{0,45}\b(?:vpn|впн)\b", re.I)),
    ("not_work_with_vpn_ru", re.compile(r"(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится)|отказывается\s+работать)[^.!?]{0,80}\b(?:vpn|впн)\b", re.I)),
    ("vpn_blocks_access_ru", re.compile(r"\b(?:vpn|впн)\b[^.!?]{0,80}(?:блокир|огранич|не\s+да[её]т|мешает\s+вход)", re.I)),
    ("access_blocked_vpn_ru", re.compile(r"(?:доступ|вход|авторизац\w*)[^.!?]{0,80}(?:блокир|огранич)[^.!?]{0,80}\b(?:vpn|впн)\b", re.I)),
    ("vpn_or_proxy_ru", re.compile(r"\b(?:vpn|впн)\b\s*(?:или|/)\s*(?:proxy|прокси)\b", re.I)),
    ("disable_vpn_en", re.compile(r"(?:disable|turn\s+off)[^.!?]{0,40}\bvpn\b", re.I)),
    ("vpn_detected_en", re.compile(r"\bvpn\b[^.!?]{0,45}(?:detected|active|enabled|not\s+allowed|blocked)", re.I)),
    ("not_work_with_vpn_en", re.compile(r"(?:does(?:n't| not)|won't|will not)\s+(?:work|open|login|load)[^.!?]{0,80}\bvpn\b", re.I)),
]

WEAK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("vpn_problem_ru", re.compile(r"\b(?:vpn|впн)\b[^.!?]{0,80}(?:ошибк|проблем|некоррект|стабильн)", re.I)),
    ("vpn_recommendation_ru", re.compile(r"(?:рекомендуем|попробуйте|советуем)[^.!?]{0,60}(?:отключить|выключить)[^.!?]{0,40}\b(?:vpn|впн)\b", re.I)),
    ("vpn_problem_en", re.compile(r"\bvpn\b[^.!?]{0,80}(?:problem|issue|incorrect|unstable)", re.I)),
]

_INVERTED_RU = re.compile(
    r"(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится)[^.!?]{0,80}\bбез\s+(?:vpn|впн)\b|"
    r"(?:что\s+)?с\s+(?:vpn|впн)[^.!?]{0,40}(?:что\s+)?без(?:\s+(?:него|vpn|впн))?)",
    re.I,
)
_INVERTED_EN = re.compile(
    r"(?:does(?:n't| not)|won't|will not)\s+(?:work|open|login|load)[^.!?]{0,80}\bwithout\s+vpn\b",
    re.I,
)


def _is_inverted_match(name: str, text: str, start: int, end: int) -> bool:
    # The generic "does not work ... VPN" pattern must not turn statements
    # such as "does not work without VPN" into evidence that VPN is blocked.
    left = max(0, start - 20)
    right = min(len(text), end + 45)
    context = text[left:right]
    if name == "not_work_with_vpn_ru":
        return bool(_INVERTED_RU.search(context))
    if name == "not_work_with_vpn_en":
        return bool(_INVERTED_EN.search(context))
    return False


def classify(text: str) -> Classification:
    if not text:
        return Classification(False, 0)

    normalized = text.replace("\xa0", " ")
    strong: list[str] = []
    weak: list[str] = []

    for name, pattern in STRONG_PATTERNS:
        for match in pattern.finditer(normalized):
            if _is_inverted_match(name, normalized, match.start(), match.end()):
                continue
            strong.append(name)
            break
    for name, pattern in WEAK_PATTERNS:
        if pattern.search(normalized):
            weak.append(name)

    # One strong signal is enough to become a relevant candidate. Confirmation
    # is intentionally stricter and happens later in dataset.build_apps().
    score = len(strong) * 3 + len(weak)
    return Classification(bool(strong), score, strong, weak)

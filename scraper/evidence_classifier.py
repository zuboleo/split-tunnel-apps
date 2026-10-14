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


def classify(text: str) -> Classification:
    if not text:
        return Classification(False, 0)

    normalized = text.replace("\xa0", " ")
    strong: list[str] = []
    weak: list[str] = []

    for name, pattern in STRONG_PATTERNS:
        if pattern.search(normalized):
            strong.append(name)
    for name, pattern in WEAK_PATTERNS:
        if pattern.search(normalized):
            weak.append(name)

    # One strong signal is enough to become a relevant candidate. Weak-only
    # findings are retained by the pipeline only when corroborated elsewhere.
    score = len(strong) * 3 + len(weak)
    return Classification(bool(strong), score, strong, weak)

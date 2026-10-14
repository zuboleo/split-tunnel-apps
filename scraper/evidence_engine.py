from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Classification


_VPN_TOKEN = re.compile(r"\b(?:vpn|впн|proxy|прокси)\b", re.I)
_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")


@dataclass(frozen=True, slots=True)
class _Rule:
    name: str
    confidence: float
    pattern: re.Pattern[str]


# Rules describe the relationship between an app and VPN, not merely the fact
# that the word VPN occurs. Confidence is intentionally semantic: one explicit
# block can be stronger than several generic troubleshooting replies.
_POSITIVE_RULES = [
    _Rule(
        "false_vpn_detection_ru",
        0.99,
        re.compile(
            r"(?:(?:требует|просит|пишет|сообщает|показывает|ругается|находит|наш[её]л|видит)[^.!?]{0,90}"
            r"(?:vpn|впн)[^.!?]{0,90}(?:нет|не\s+установлен|не\s+включ[её]н|выключен|отключен)|"
            r"(?:vpn|впн)[^.!?]{0,50}(?:нет|не\s+установлен|не\s+включ[её]н|выключен|отключен)[^.!?]{0,90}"
            r"(?:требует|просит|пишет|сообщает|показывает|ругается))",
            re.I,
        ),
    ),
    _Rule(
        "requires_disable_vpn_ru",
        0.96,
        re.compile(
            r"(?:(?:требует|просит|нужно|необходимо|надо|предлагает|пишет|сообщает|показывает)[^.!?]{0,80}"
            r"(?:отключить|выключить)[^.!?]{0,35}(?:vpn|впн)|"
            r"(?:отключите|выключите)[^.!?]{0,35}(?:vpn|впн)[^.!?]{0,80}(?:чтобы|для|иначе|продолж))",
            re.I,
        ),
    ),
    _Rule(
        "vpn_detected_ru",
        0.96,
        re.compile(
            r"(?:(?:vpn|впн)[^.!?]{0,55}(?:обнаружен|обнаружено|активен|включ[её]н|запрещ[её]н|не\s+разреш[её]н)|"
            r"(?:обнаружен|обнаружено|детектит|определяет|распозна[её]т|видит|находит|наш[её]л|ругается\s+на)[^.!?]{0,55}(?:vpn|впн))",
            re.I,
        ),
    ),
    _Rule(
        "blocked_with_vpn_ru",
        0.92,
        re.compile(
            r"(?:(?:с|при|через)[^.!?]{0,20}(?:vpn|впн)[^.!?]{0,100}"
            r"(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится|пускает)|блокир|огранич|ошибк)|"
            r"(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится|пускает)|блокир|огранич)[^.!?]{0,100}"
            r"(?:с|при|через)[^.!?]{0,20}(?:vpn|впн))",
            re.I,
        ),
    ),
    _Rule(
        "vpn_blocks_access_ru",
        0.93,
        re.compile(
            r"(?:vpn|впн)[^.!?]{0,100}(?:блокир|огранич|не\s+да[её]т\s+(?:войти|зайти|открыть)|не\s+пускает|мешает\s+вход)",
            re.I,
        ),
    ),
    _Rule(
        "disable_vpn_ru",
        0.66,
        re.compile(r"(?:отключите|выключите|отключить|выключить)[^.!?]{0,45}(?:vpn|впн)", re.I),
    ),
    _Rule(
        "false_vpn_detection_en",
        0.99,
        re.compile(
            r"(?:asks?|requires?|says?|reports?|shows?)[^.!?]{0,80}(?:disable|turn\s+off)[^.!?]{0,35}vpn"
            r"[^.!?]{0,80}(?:not\s+installed|not\s+enabled|already\s+off|disabled)",
            re.I,
        ),
    ),
    _Rule(
        "requires_disable_vpn_en",
        0.96,
        re.compile(
            r"(?:(?:asks?|requires?|must|need\s+to|says?|reports?|shows?)[^.!?]{0,80}(?:disable|turn\s+off)[^.!?]{0,35}vpn|"
            r"(?:disable|turn\s+off)[^.!?]{0,35}vpn[^.!?]{0,80}(?:to\s+continue|otherwise))",
            re.I,
        ),
    ),
    _Rule(
        "vpn_detected_en",
        0.96,
        re.compile(r"(?:vpn[^.!?]{0,50}(?:detected|active|enabled|not\s+allowed|blocked)|(?:detects?|detected)[^.!?]{0,50}vpn)", re.I),
    ),
    _Rule(
        "blocked_with_vpn_en",
        0.92,
        re.compile(
            r"(?:(?:with|when\s+using)[^.!?]{0,25}vpn[^.!?]{0,90}(?:does(?:n't| not)|won't|will\s+not)\s+(?:work|open|login|load)|"
            r"(?:does(?:n't| not)|won't|will\s+not)\s+(?:work|open|login|load)[^.!?]{0,90}(?:with|when\s+using)[^.!?]{0,25}vpn)",
            re.I,
        ),
    ),
    _Rule("disable_vpn_en", 0.66, re.compile(r"(?:disable|turn\s+off)[^.!?]{0,40}vpn", re.I)),
]

_NEGATIVE_RULES = [
    _Rule(
        "requires_vpn_ru",
        0.97,
        re.compile(
            r"(?:(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится))[^.!?]{0,80}без\s+(?:vpn|впн)|"
            r"(?:работает|открывается|заходит|входит)[^.!?]{0,50}только\s+(?:с|через)\s*(?:vpn|впн))",
            re.I,
        ),
    ),
    _Rule(
        "same_with_without_vpn_ru",
        0.91,
        re.compile(
            r"(?:(?:что|и)\s+с\s+(?:vpn|впн)[^.!?]{0,45}(?:что|и)\s+без(?:\s+(?:него|vpn|впн))?|"
            r"(?:с\s+(?:vpn|впн)[^.!?]{0,35}без\s+(?:vpn|впн)|без\s+(?:vpn|впн)[^.!?]{0,35}с\s+(?:vpn|впн)))",
            re.I,
        ),
    ),
    _Rule(
        "works_with_vpn_ru",
        0.86,
        re.compile(r"(?:с|через|при\s+включ[её]нном)[^.!?]{0,25}(?:vpn|впн)[^.!?]{0,55}(?:работает|открывается|заходит|входит|вс[её]\s+норм)", re.I),
    ),
    _Rule(
        "requires_vpn_en",
        0.97,
        re.compile(r"(?:does(?:n't| not)|won't|will\s+not)\s+(?:work|open|login|load)[^.!?]{0,80}without\s+vpn", re.I),
    ),
    _Rule(
        "same_with_without_vpn_en",
        0.91,
        re.compile(r"(?:same|fails?|broken)[^.!?]{0,60}(?:with\s+vpn[^.!?]{0,30}without\s+vpn|without\s+vpn[^.!?]{0,30}with\s+vpn)", re.I),
    ),
    _Rule(
        "works_with_vpn_en",
        0.86,
        re.compile(r"(?:with|through)\s+vpn[^.!?]{0,60}(?:works?|opens?|logs?\s+in|loads?)", re.I),
    ),
]

_WEAK_RULES = [
    _Rule("vpn_problem_ru", 0.48, re.compile(r"(?:vpn|впн)[^.!?]{0,80}(?:ошибк|проблем|некоррект|мешает|конфликт)", re.I)),
    _Rule("vpn_problem_en", 0.48, re.compile(r"vpn[^.!?]{0,80}(?:problem|issue|conflict|error)", re.I)),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _units(text: str) -> list[str]:
    """Return VPN-centred clauses while keeping enough context for negation."""
    raw_parts = [part.strip() for part in _SPLIT_RE.split(text) if part.strip()]
    result: list[str] = []
    for part in raw_parts:
        if not _VPN_TOKEN.search(part):
            continue
        if len(part) <= 360:
            result.append(part)
            continue
        for match in _VPN_TOKEN.finditer(part):
            start = max(0, match.start() - 170)
            end = min(len(part), match.end() + 190)
            result.append(part[start:end])
    return result or ([text] if _VPN_TOKEN.search(text) else [])


def _adjust(confidence: float, role: str, rule_name: str) -> float:
    if role == "developer_reply":
        # "Try disabling VPN" is common support boilerplate. It is useful, but
        # by itself it is not proof that the application actively blocks VPN.
        if rule_name in {"disable_vpn_ru", "disable_vpn_en"}:
            return min(confidence, 0.54)
        return confidence * 0.94
    if role == "search_snippet":
        return confidence * 0.95
    if role == "article":
        return confidence * 0.96
    return confidence


def analyze_text(
    text: str,
    *,
    role: str = "generic",
    app_name: str | None = None,
) -> Classification:
    normalized = _normalize(text)
    if not normalized or not _VPN_TOKEN.search(normalized):
        return Classification(False, 0, verdict="neutral", confidence=0.0)

    positive: list[tuple[str, float]] = []
    negative: list[tuple[str, float]] = []
    weak: list[tuple[str, float]] = []

    for unit in _units(normalized):
        for rule in _POSITIVE_RULES:
            if rule.pattern.search(unit):
                positive.append((rule.name, _adjust(rule.confidence, role, rule.name)))
        for rule in _NEGATIVE_RULES:
            if rule.pattern.search(unit):
                negative.append((rule.name, _adjust(rule.confidence, role, rule.name)))
        for rule in _WEAK_RULES:
            if rule.pattern.search(unit):
                weak.append((rule.name, _adjust(rule.confidence, role, rule.name)))

    pos_conf = max((value for _, value in positive), default=0.0)
    neg_conf = max((value for _, value in negative), default=0.0)
    weak_conf = max((value for _, value in weak), default=0.0)

    # Do not confuse reviews of VPN applications themselves with evidence that
    # another application rejects VPN. Explicit detection/disable rules can
    # still override this guard.
    app_is_vpn = bool(app_name and _VPN_TOKEN.search(app_name))
    explicit_positive = any(
        name
        in {
            "false_vpn_detection_ru",
            "requires_disable_vpn_ru",
            "vpn_detected_ru",
            "blocked_with_vpn_ru",
            "vpn_blocks_access_ru",
            "false_vpn_detection_en",
            "requires_disable_vpn_en",
            "vpn_detected_en",
            "blocked_with_vpn_en",
        }
        for name, _ in positive
    )
    if app_is_vpn and not explicit_positive:
        pos_conf = 0.0

    # Counter-evidence wins when it is materially stronger. This catches
    # "does not work without VPN" and "same with and without VPN" instead of
    # turning them into false positives merely because both words occur.
    if neg_conf >= 0.72 and neg_conf >= pos_conf + 0.08:
        verdict = "negative"
        confidence = neg_conf
    elif pos_conf >= 0.52 and pos_conf >= neg_conf + 0.04:
        verdict = "positive"
        confidence = pos_conf
    elif max(pos_conf, neg_conf, weak_conf) >= 0.45:
        verdict = "uncertain"
        confidence = max(pos_conf, neg_conf, weak_conf)
    else:
        verdict = "neutral"
        confidence = 0.0

    strong_names = sorted({name for name, value in positive if value >= 0.80})
    weak_names = sorted({name for name, value in positive + weak if value < 0.80})
    negative_names = sorted({name for name, _ in negative})
    score = int(round(confidence * 10))

    return Classification(
        relevant=verdict == "positive",
        score=score,
        strong_matches=strong_names,
        weak_matches=weak_names,
        verdict=verdict,
        confidence=round(confidence, 3),
        negative_matches=negative_names,
    )


def combine_classifications(*items: Classification) -> Classification:
    """Combine parts of one observation, e.g. review text + developer reply."""
    positive = [item for item in items if item.verdict == "positive"]
    negative = [item for item in items if item.verdict == "negative"]
    uncertain = [item for item in items if item.verdict == "uncertain"]

    pos_conf = max((item.confidence for item in positive), default=0.0)
    neg_conf = max((item.confidence for item in negative), default=0.0)

    if neg_conf >= 0.72 and neg_conf >= pos_conf + 0.08:
        verdict = "negative"
        confidence = neg_conf
    elif pos_conf >= 0.52 and pos_conf >= neg_conf + 0.04:
        verdict = "positive"
        confidence = pos_conf
    elif uncertain:
        verdict = "uncertain"
        confidence = max(item.confidence for item in uncertain)
    else:
        verdict = "neutral"
        confidence = 0.0

    return Classification(
        relevant=verdict == "positive",
        score=int(round(confidence * 10)),
        strong_matches=sorted({name for item in items for name in item.strong_matches}),
        weak_matches=sorted({name for item in items for name in item.weak_matches}),
        verdict=verdict,
        confidence=round(confidence, 3),
        negative_matches=sorted({name for item in items for name in item.negative_matches}),
    )


def analyze_review(
    review_text: str,
    developer_reply: str = "",
    *,
    app_name: str | None = None,
) -> Classification:
    review = analyze_text(review_text, role="user_review", app_name=app_name)
    if not developer_reply:
        return review
    reply = analyze_text(developer_reply, role="developer_reply", app_name=app_name)
    return combine_classifications(review, reply)

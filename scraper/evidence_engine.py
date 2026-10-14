from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Classification


_VPN = r"(?:vpn|впн)"
_VPN_TOKEN = re.compile(rf"\b{_VPN}\b", re.I)
_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")


@dataclass(frozen=True, slots=True)
class _Rule:
    name: str
    confidence: float
    pattern: re.Pattern[str]


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I)


_POSITIVE_RULES = [
    _Rule("false_vpn_detection_ru", 0.99, _rx(
        rf"(?:(?:требует|просит|пишет|сообщает|показывает|ругается|находит|наш[её]л|видит)"
        rf"[^.!?]{{0,90}}\b{_VPN}\b[^.!?]{{0,90}}(?:нет|не\s+установлен|не\s+включ[её]н|выключен|отключен)|"
        rf"\b{_VPN}\b[^.!?]{{0,50}}(?:нет|не\s+установлен|не\s+включ[её]н|выключен|отключен)"
        rf"[^.!?]{{0,90}}(?:требует|просит|пишет|сообщает|показывает|ругается))"
    )),
    _Rule("requires_disable_vpn_ru", 0.96, _rx(
        rf"(?:(?:требует|просит|нужно|необходимо|надо|предлагает|пишет|сообщает|показывает)"
        rf"[^.!?]{{0,80}}(?:отключить|выключить|отключите|выключите)[^.!?]{{0,35}}\b{_VPN}\b|"
        rf"(?:для\s+(?:входа|доступа|работы|продолжения)|чтобы\s+(?:войти|зайти|продолжить|работало?))"
        rf"[^.!?]{{0,80}}(?:требуется|нужно|необходимо|надо)[^.!?]{{0,35}}(?:отключить|выключить)"
        rf"[^.!?]{{0,35}}\b{_VPN}\b|"
        rf"(?:отключите|выключите)[^.!?]{{0,35}}\b{_VPN}\b[^.!?]{{0,80}}(?:чтобы|для|иначе|продолж))"
    )),
    _Rule("vpn_detected_ru", 0.96, _rx(
        rf"(?:\b{_VPN}\b[^.!?]{{0,55}}(?:обнаружен|обнаружено|активен|включ[её]н|запрещ[её]н|не\s+разреш[её]н)|"
        rf"(?:обнаружен|обнаружено|детектит|определяет|распозна[её]т|видит|находит|наш[её]л|ругается\s+на)"
        rf"[^.!?]{{0,55}}\b{_VPN}\b)"
    )),
    _Rule("vpn_allergy_ru", 0.91, _rx(
        rf"(?:(?:приложени[еяю]|сервис|прога|приложуха)[^.!?]{{0,60}}(?:аллерги|не\s+любит|не\s+дружит)"
        rf"[^.!?]{{0,35}}\b{_VPN}\b|(?:аллерги|не\s+любит|не\s+дружит)[^.!?]{{0,35}}\b{_VPN}\b)"
    )),
    _Rule("blocked_with_vpn_ru", 0.92, _rx(
        rf"(?:\b(?:с|при|через)\b[^.!?]{{0,20}}\b{_VPN}\b[^.!?]{{0,100}}"
        rf"(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится|пускает)|"
        rf"(?:выда[её]т|пишет|показывает)\s+ошибк|доступ\s+(?:закрыт|ограничен)|блокируется)|"
        rf"(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится|пускает)|"
        rf"доступ\s+(?:закрыт|ограничен)|блокируется)[^.!?]{{0,100}}"
        rf"\b(?:с|при|через)\b[^.!?]{{0,20}}\b{_VPN}\b)"
    )),
    _Rule("vpn_blocks_access_ru", 0.93, _rx(
        rf"\b{_VPN}\b[^.!?]{{0,75}}(?:не\s+да[её]т\s+(?:войти|зайти|открыть|работать)|"
        rf"не\s+пускает|мешает\s+(?:входу|работе)|блокирует\s+(?:доступ|вход|работу)|"
        rf"ограничивает\s+(?:доступ|вход|работу))"
    )),
    _Rule("disable_vpn_ru", 0.66, _rx(
        rf"(?:отключите|выключите|отключить|выключить)[^.!?]{{0,45}}\b{_VPN}\b"
    )),
    _Rule("false_vpn_detection_en", 0.99, _rx(
        r"(?:asks?|requires?|says?|reports?|shows?)[^.!?]{0,80}(?:disable|turn\s+off)[^.!?]{0,35}\bvpn\b"
        r"[^.!?]{0,80}(?:not\s+installed|not\s+enabled|already\s+off|disabled)"
    )),
    _Rule("requires_disable_vpn_en", 0.96, _rx(
        r"(?:(?:asks?|requires?|must|need\s+to|says?|reports?|shows?)[^.!?]{0,80}"
        r"(?:disable|turn\s+off)[^.!?]{0,35}\bvpn\b|"
        r"(?:disable|turn\s+off)[^.!?]{0,35}\bvpn\b[^.!?]{0,80}(?:to\s+continue|otherwise))"
    )),
    _Rule("vpn_detected_en", 0.96, _rx(
        r"(?:\bvpn\b[^.!?]{0,50}(?:detected|active|enabled|not\s+allowed|blocked)|(?:detects?|detected)[^.!?]{0,50}\bvpn\b)"
    )),
    _Rule("blocked_with_vpn_en", 0.92, _rx(
        r"(?:(?:\bwith\b|\bwhen\s+using\b)[^.!?]{0,25}\bvpn\b[^.!?]{0,90}"
        r"(?:does(?:n't| not)|won't|will\s+not)\s+(?:work|open|login|load)|"
        r"(?:does(?:n't| not)|won't|will\s+not)\s+(?:work|open|login|load)[^.!?]{0,90}"
        r"(?:\bwith\b|\bwhen\s+using\b)[^.!?]{0,25}\bvpn\b)"
    )),
    _Rule("vpn_blocks_access_en", 0.93, _rx(
        r"\bvpn\b[^.!?]{0,75}(?:blocks?\s+(?:access|login)|prevents?\s+(?:login|access)|breaks?\s+the\s+app)"
    )),
    _Rule("disable_vpn_en", 0.66, _rx(r"(?:disable|turn\s+off)[^.!?]{0,40}\bvpn\b")),
]


_NEGATIVE_RULES = [
    _Rule("requires_vpn_ru", 0.97, _rx(
        rf"(?:(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится|пускает))"
        rf"[^.!?]{{0,80}}\bбез\b[^.!?]{{0,20}}\b{_VPN}\b|"
        rf"\bбез\b[^.!?]{{0,20}}\b{_VPN}\b[^.!?]{{0,45}}"
        rf"(?:не\s+(?:работает|открывается|запускается|заходит|входит|грузится|пускает|зайд[её]шь|войд[её]шь)|"
        rf"(?:не\s+)?зайд[её]шь|(?:не\s+)?войд[её]шь)|"
        rf"\b{_VPN}\b[^.!?]{{0,90}}\bбез\s+него\b[^.!?]{{0,45}}не\s+(?:работает|открывается|заходит|входит|грузится)|"
        rf"(?:работает|открывается|заходит|входит)[^.!?]{{0,50}}\bтолько\b[^.!?]{{0,20}}"
        rf"\b(?:с|через)\b[^.!?]{{0,15}}\b{_VPN}\b)"
    )),
    _Rule("same_with_without_vpn_ru", 0.96, _rx(
        rf"(?:\bс\b\s*\b{_VPN}\b\s*(?:или|и|/)\s*\bбез\b(?:\s+(?:него|\b{_VPN}\b))?"
        rf"[^.!?]{{0,55}}(?:не\s+имеет\s+значения|одинаков|вс[её]\s+равно|так\s+же)|"
        rf"(?:что|и)\s+\bс\b\s*\b{_VPN}\b[^.!?]{{0,55}}(?:что|и)\s+\bбез\b(?:\s+(?:него|\b{_VPN}\b))?|"
        rf"\bбез\b\s*\b{_VPN}\b[^.!?]{{0,45}}\bс\b\s*\b{_VPN}\b)"
    )),
    _Rule("vpn_helps_ru", 0.97, _rx(
        rf"(?:(?:не\s+(?:работает|открывается|заходит|входит|грузится)|блокир\w*|огранич\w*)"
        rf"[^.!?]{{0,90}}\b{_VPN}\b[^.!?]{{0,25}}(?:поможет|помогает|спасает|выручает)|"
        rf"\b{_VPN}\b[^.!?]{{0,25}}(?:поможет|помогает|спасает|выручает)"
        rf"[^.!?]{{0,65}}(?:зайти|войти|открыть|загрузить|работать|получить\s+доступ|разблокировать|обойти\s+огранич)|"
        rf"(?:нужен|нужна|необходим)[^.!?]{{0,25}}\b{_VPN}\b[^.!?]{{0,55}}(?:для|чтобы)"
        rf"[^.!?]{{0,35}}(?:вход|доступ|работ|открыт|загруз))"
    )),
    _Rule("works_with_vpn_ru", 0.90, _rx(
        rf"\b(?:с|через|при\s+включ[её]нном)\b[^.!?]{{0,25}}\b{_VPN}\b"
        rf"[^.!?]{{0,55}}(?:работает|открывается|заходит|входит|вс[её]\s+норм)"
    )),
    _Rule("vpn_does_not_fix_ru", 0.90, _rx(
        rf"(?:\bс\b\s*\b{_VPN}\b[^.!?]{{0,30}}(?:тоже|так\s+же)[^.!?]{{0,25}}"
        rf"(?:не\s+работает|не\s+открывается|глючит|ошибк|через\s+раз)|"
        rf"\b{_VPN}\b[^.!?]{{0,20}}(?:не\s+помогает|не\s+помог|не\s+спасает))"
    )),
    _Rule("without_vpn_is_goal_ru", 0.92, _rx(
        rf"(?:(?:чтобы|хочу|хотел(?:ось)?|сделайте)[^.!?]{{0,80}}"
        rf"(?:работал[оа]?|открывал(?:ось|ся)?|заходил[оа]?|грузил(?:ось|ся)?)"
        rf"[^.!?]{{0,45}}\bбез\b[^.!?]{{0,15}}\b{_VPN}\b|"
        rf"(?:чтобы|хочу|хотел(?:ось)?|сделайте)[^.!?]{{0,80}}\bбез\b[^.!?]{{0,15}}\b{_VPN}\b"
        rf"[^.!?]{{0,45}}(?:работал|работало|открывал|заходил|грузил))"
    )),
    _Rule("requires_vpn_en", 0.97, _rx(
        r"(?:(?:does(?:n't| not)|won't|will\s+not)\s+(?:work|open|login|load)[^.!?]{0,80}\bwithout\s+vpn\b|"
        r"\bwithout\s+vpn\b[^.!?]{0,55}(?:does(?:n't| not)|won't|will\s+not)\s+(?:work|open|login|load)|"
        r"(?:works?|opens?|logs?\s+in|loads?)[^.!?]{0,45}\bonly\b[^.!?]{0,20}\bwith\s+vpn\b)"
    )),
    _Rule("same_with_without_vpn_en", 0.96, _rx(
        r"(?:(?:with\s+vpn\s+(?:or|and)\s+without\s+(?:it|vpn)|without\s+vpn\s+(?:or|and)\s+with\s+vpn)"
        r"[^.!?]{0,55}(?:same|no\s+difference|doesn't\s+matter|does\s+not\s+matter)|"
        r"(?:same|fails?|broken)[^.!?]{0,60}(?:with\s+vpn[^.!?]{0,30}without\s+vpn|without\s+vpn[^.!?]{0,30}with\s+vpn))"
    )),
    _Rule("vpn_helps_en", 0.97, _rx(
        r"(?:(?:doesn't\s+work|does\s+not\s+work|won't\s+open|blocked|restricted)[^.!?]{0,90}\bvpn\b[^.!?]{0,25}(?:helps?|fixes?)|"
        r"\bvpn\b[^.!?]{0,25}(?:helps?|fixes?)[^.!?]{0,65}(?:work|open|login|load|access|unblock)|"
        r"(?:needed|required)[^.!?]{0,25}\bvpn\b[^.!?]{0,55}(?:to|for)[^.!?]{0,30}(?:work|open|login|access))"
    )),
    _Rule("works_with_vpn_en", 0.90, _rx(
        r"(?:\bwith\b|\bthrough\b)[^.!?]{0,20}\bvpn\b[^.!?]{0,60}(?:works?|opens?|logs?\s+in|loads?)"
    )),
    _Rule("vpn_does_not_fix_en", 0.90, _rx(
        r"(?:with\s+vpn[^.!?]{0,30}(?:also|still)[^.!?]{0,30}(?:fails?|doesn't\s+work|broken)|"
        r"vpn[^.!?]{0,25}(?:doesn't\s+help|does\s+not\s+help))"
    )),
]

_WEAK_RULES = [
    _Rule("vpn_problem_ru", 0.48, _rx(rf"\b{_VPN}\b[^.!?]{{0,80}}(?:ошибк|проблем|некоррект|мешает|конфликт)")),
    _Rule("vpn_problem_en", 0.48, _rx(r"\bvpn\b[^.!?]{0,80}(?:problem|issue|conflict|error)")),
]

_AMBIGUOUS_POSITIVE = {"blocked_with_vpn_ru", "blocked_with_vpn_en", "vpn_blocks_access_ru", "vpn_blocks_access_en"}
_CONTEXTUAL_NEGATIVE = {rule.name for rule in _NEGATIVE_RULES}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _units(text: str) -> list[str]:
    raw_parts = [part.strip() for part in _SPLIT_RE.split(text) if part.strip()]
    result: list[str] = []
    for part in raw_parts:
        if not _VPN_TOKEN.search(part):
            continue
        if len(part) <= 360:
            result.append(part)
            continue
        for match in _VPN_TOKEN.finditer(part):
            result.append(part[max(0, match.start() - 170):min(len(part), match.end() + 190)])
    return result or ([text] if _VPN_TOKEN.search(text) else [])


def _adjust(confidence: float, role: str, rule_name: str) -> float:
    if role == "developer_reply":
        if rule_name in {"disable_vpn_ru", "disable_vpn_en"}:
            return min(confidence, 0.54)
        return confidence * 0.94
    if role == "search_snippet":
        return confidence * 0.95
    if role == "article":
        return confidence * 0.96
    return confidence


def analyze_text(text: str, *, role: str = "generic", app_name: str | None = None) -> Classification:
    normalized = _normalize(text)
    if not normalized or not _VPN_TOKEN.search(normalized):
        return Classification(False, 0, verdict="neutral", confidence=0.0)

    positive: list[tuple[str, float]] = []
    negative: list[tuple[str, float]] = []
    weak: list[tuple[str, float]] = []

    for unit in _units(normalized):
        unit_positive = [(r.name, _adjust(r.confidence, role, r.name)) for r in _POSITIVE_RULES if r.pattern.search(unit)]
        unit_negative = [(r.name, _adjust(r.confidence, role, r.name)) for r in _NEGATIVE_RULES if r.pattern.search(unit)]
        unit_weak = [(r.name, _adjust(r.confidence, role, r.name)) for r in _WEAK_RULES if r.pattern.search(unit)]
        if {name for name, _ in unit_negative} & _CONTEXTUAL_NEGATIVE:
            unit_positive = [item for item in unit_positive if item[0] not in _AMBIGUOUS_POSITIVE]
        positive.extend(unit_positive)
        negative.extend(unit_negative)
        weak.extend(unit_weak)

    pos_conf = max((value for _, value in positive), default=0.0)
    neg_conf = max((value for _, value in negative), default=0.0)
    weak_conf = max((value for _, value in weak), default=0.0)

    explicit_positive_names = {
        "false_vpn_detection_ru", "requires_disable_vpn_ru", "vpn_detected_ru", "vpn_allergy_ru",
        "blocked_with_vpn_ru", "vpn_blocks_access_ru", "false_vpn_detection_en",
        "requires_disable_vpn_en", "vpn_detected_en", "blocked_with_vpn_en", "vpn_blocks_access_en",
    }
    if app_name and _VPN_TOKEN.search(app_name) and not any(name in explicit_positive_names for name, _ in positive):
        pos_conf = 0.0

    if neg_conf >= 0.72 and neg_conf >= pos_conf + 0.08:
        verdict, confidence = "negative", neg_conf
    elif pos_conf >= 0.52 and pos_conf >= neg_conf + 0.04:
        verdict, confidence = "positive", pos_conf
    elif max(pos_conf, neg_conf, weak_conf) >= 0.45:
        verdict, confidence = "uncertain", max(pos_conf, neg_conf, weak_conf)
    else:
        verdict, confidence = "neutral", 0.0

    return Classification(
        relevant=verdict == "positive",
        score=int(round(confidence * 10)),
        strong_matches=sorted({name for name, value in positive if value >= 0.80}),
        weak_matches=sorted({name for name, value in positive + weak if value < 0.80}),
        verdict=verdict,
        confidence=round(confidence, 3),
        negative_matches=sorted({name for name, _ in negative}),
    )


def combine_classifications(*items: Classification) -> Classification:
    positive = [item for item in items if item.verdict == "positive"]
    negative = [item for item in items if item.verdict == "negative"]
    uncertain = [item for item in items if item.verdict == "uncertain"]
    pos_conf = max((item.confidence for item in positive), default=0.0)
    neg_conf = max((item.confidence for item in negative), default=0.0)

    if neg_conf >= 0.72 and neg_conf >= pos_conf + 0.08:
        verdict, confidence = "negative", neg_conf
    elif pos_conf >= 0.52 and pos_conf >= neg_conf + 0.04:
        verdict, confidence = "positive", pos_conf
    elif uncertain:
        verdict, confidence = "uncertain", max(item.confidence for item in uncertain)
    elif positive or negative:
        verdict, confidence = "uncertain", max(pos_conf, neg_conf)
    else:
        verdict, confidence = "neutral", 0.0

    return Classification(
        relevant=verdict == "positive",
        score=int(round(confidence * 10)),
        strong_matches=sorted({name for item in items for name in item.strong_matches}),
        weak_matches=sorted({name for item in items for name in item.weak_matches}),
        verdict=verdict,
        confidence=round(confidence, 3),
        negative_matches=sorted({name for item in items for name in item.negative_matches}),
    )


def analyze_review(review_text: str, developer_reply: str = "", *, app_name: str | None = None) -> Classification:
    review = analyze_text(review_text, role="user_review", app_name=app_name)
    if not developer_reply:
        return review
    reply = analyze_text(developer_reply, role="developer_reply", app_name=app_name)
    return combine_classifications(review, reply)

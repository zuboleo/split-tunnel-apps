from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from pymorphy3 import MorphAnalyzer
from razdel import sentenize, tokenize

from .models import Classification


# Deliberately support only normal spellings/aliases. Mixed Cyrillic/Latin
# lookalikes are not normalized: they add complexity and false positives.
_VPN_ALIASES = {"vpn", "впн", "квн"}
_VPN_RE = re.compile(r"(?<![\w])(?:vpn|впн|квн)(?![\w])", re.I)
_MORPH = MorphAnalyzer()

_CLAUSE_BREAK_WORDS = {"а", "но", "зато", "однако"}
_HARD_PUNCT = {".", "!", "?", ";"}

_WORK_LEMMAS = {
    "работать",
    "открываться",
    "открывать",
    "запускаться",
    "запускать",
    "заходить",
    "входить",
    "грузиться",
    "загружаться",
    "пускать",
}
_DISABLE_LEMMAS = {"отключать", "отключить", "выключать", "выключить"}
_ENABLE_LEMMAS = {"включать", "включить", "подключать", "подключить"}
_REQUIRE_LEMMAS = {"требовать", "требоваться", "нужно", "необходимо", "надо", "приходиться"}
_DETECT_LEMMAS = {
    "обнаруживать",
    "обнаружить",
    "определять",
    "определить",
    "распознавать",
    "распознать",
    "детектить",
    "видеть",
    "ругаться",
}
_BLOCK_LEMMAS = {
    "блокировать",
    "заблокировать",
    "ограничивать",
    "ограничить",
    "запрещать",
    "запретить",
}
_HELP_LEMMAS = {"помогать", "помочь", "спасать", "спасти", "выручать", "выручить"}
_ACCESS_LEMMAS = {
    "вход",
    "доступ",
    "авторизация",
    "регистрация",
    "приложение",
    "сервис",
    "сайт",
    "блокировка",
    "ограничение",
    "обход",
}
_GOAL_WORDS = {"чтобы", "хотеть", "сделать", "просить"}
_OFF_WORDS = {"выключенный", "отключенный", "неактивный"}


@dataclass(frozen=True, slots=True)
class _Token:
    text: str
    lower: str
    lemma: str


@dataclass(frozen=True, slots=True)
class _Relation:
    route: str
    confidence: float
    condition: str
    effect: str
    reason: str


@lru_cache(maxsize=8192)
def _lemma(word: str) -> str:
    if not re.fullmatch(r"[а-яё]+", word, re.I):
        return word.lower()
    try:
        return _MORPH.parse(word.lower())[0].normal_form
    except Exception:
        return word.lower()


def _tokens(text: str) -> list[_Token]:
    result: list[_Token] = []
    for item in tokenize(text):
        lower = item.text.lower()
        result.append(_Token(item.text, lower, _lemma(lower)))
    return result


def _is_anchor(token: _Token) -> bool:
    return token.lower in _VPN_ALIASES


def _clause_bounds(tokens: list[_Token], anchor: int, radius: int = 14) -> tuple[int, int]:
    left = max(0, anchor - radius)
    right = min(len(tokens), anchor + radius + 1)

    for i in range(anchor - 1, left - 1, -1):
        if tokens[i].text in _HARD_PUNCT or tokens[i].lower in _CLAUSE_BREAK_WORDS:
            left = i + 1
            break
    for i in range(anchor + 1, right):
        if tokens[i].text in _HARD_PUNCT or tokens[i].lower in _CLAUSE_BREAK_WORDS:
            right = i
            break
    return left, right


def _window(tokens: list[_Token], anchor: int) -> tuple[list[_Token], int]:
    left, right = _clause_bounds(tokens, anchor)
    return tokens[left:right], anchor - left


def _near(values: set[str], tokens: list[_Token], anchor: int, distance: int) -> list[int]:
    return [
        i
        for i, token in enumerate(tokens)
        if token.lemma in values and abs(i - anchor) <= distance
    ]


def _is_negated(tokens: list[_Token], index: int) -> bool:
    start = max(0, index - 3)
    for token in tokens[start:index]:
        if token.lower == "не":
            return True
        if token.text in {",", ";", ".", "!", "?"}:
            return False
    return False


def _condition(tokens: list[_Token], anchor: int) -> str:
    before = tokens[max(0, anchor - 4):anchor]
    before_lemmas = [t.lemma for t in before]

    # Verb operators are more specific than a nearby preposition.
    for i in _near(_DISABLE_LEMMAS, tokens, anchor, 5):
        if not _is_negated(tokens, i):
            return "DISABLE_VPN"
    for i in _near(_ENABLE_LEMMAS, tokens, anchor, 5):
        if not _is_negated(tokens, i):
            return "ENABLE_VPN"

    if "без" in before_lemmas[-3:]:
        return "WITHOUT_VPN"
    if any(value in before_lemmas[-3:] for value in {"с", "через", "при"}):
        return "WITH_VPN"
    return "VPN"


def _work_effect(tokens: list[_Token], anchor: int) -> tuple[str | None, int | None]:
    candidates: list[tuple[int, int, str]] = []
    for i, token in enumerate(tokens):
        if token.lemma not in _WORK_LEMMAS:
            continue
        distance = abs(i - anchor)
        if distance > 8:
            continue
        effect = "NOT_WORKING" if _is_negated(tokens, i) else "WORKING"
        candidates.append((distance, i, effect))
    if not candidates:
        return None, None
    _, index, effect = min(candidates)
    return effect, index


def _contains(tokens: list[_Token], lemmas: set[str]) -> bool:
    return any(token.lemma in lemmas for token in tokens)


def _contains_goal(tokens: list[_Token]) -> bool:
    return any(token.lower == "чтобы" or token.lemma in _GOAL_WORDS for token in tokens)


def _contains_only(tokens: list[_Token]) -> bool:
    return any(token.lower == "только" for token in tokens)


def _same_with_without_vpn(text: str) -> bool:
    alias = r"(?:vpn|впн|квн)"
    patterns = (
        rf"(?:что\s+)?с\s+{alias}[^.!?]{{0,45}}(?:что\s+)?без(?:\s+(?:него|{alias}))?[^.!?]{{0,40}}(?:не\s+имеет\s+значения|одинаков|вс[её]\s+равно|так\s+же)",
        rf"с\s+{alias}\s+(?:или|и|/)\s+без(?:\s+(?:него|{alias}))?[^.!?]{{0,40}}(?:не\s+имеет\s+значения|одинаков|вс[её]\s+равно|так\s+же)",
        rf"(?:не\s+работает|не\s+открывается|глючит)[^.!?]{{0,45}}с\s+{alias}[^.!?]{{0,35}}(?:и|или|что)\s+без",
    )
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _vpn_does_not_help(text: str) -> bool:
    return bool(
        re.search(
            r"(?<![\w])(?:vpn|впн|квн)(?![\w])[^.!?]{0,25}не\s+(?:помогает|помог|спасает|спас)",
            text,
            re.I,
        )
    )


def _false_detection(tokens: list[_Token], anchor: int) -> bool:
    # "Требует отключить VPN, но он выключен" / "VPN у меня не включен".
    has_disable = bool(_near(_DISABLE_LEMMAS, tokens, anchor, 6))
    if not has_disable:
        return False
    lemmas = [token.lemma for token in tokens]
    raw = " ".join(token.lower for token in tokens)
    return (
        any(value in lemmas for value in _OFF_WORDS)
        or bool(re.search(r"(?:не\s+включ[её]н|не\s+использую|vpn\s+нет|впн\s+нет|квн\s+нет)", raw, re.I))
    )


def _problem_context(tokens: list[_Token], app_name: str | None) -> bool:
    if _contains(tokens, _WORK_LEMMAS | _BLOCK_LEMMAS | _ACCESS_LEMMAS):
        return True
    if any(token.lemma in {"ошибка", "проблема", "недоступный"} for token in tokens):
        return True
    if app_name:
        app_words = {part.lower() for part in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", app_name) if len(part) >= 3}
        token_words = {token.lower for token in tokens}
        return bool(app_words & token_words)
    return False


def _adjust(confidence: float, role: str, reason: str) -> float:
    if role == "developer_reply":
        # Generic support advice like "try disabling VPN" is evidence, but not
        # proof that the application actively rejects VPN.
        if reason == "disable_vpn":
            return min(confidence, 0.54)
        return confidence * 0.97
    if role == "search_snippet":
        return confidence * 0.95
    if role == "article":
        return confidence * 0.96
    return confidence


def _relation_for_anchor(
    tokens: list[_Token],
    anchor: int,
    *,
    role: str,
    app_name: str | None,
) -> list[_Relation]:
    clause, local_anchor = _window(tokens, anchor)
    if not clause:
        return []

    raw = " ".join(token.text for token in clause)
    condition = _condition(clause, local_anchor)
    effect, effect_index = _work_effect(clause, local_anchor)
    relations: list[_Relation] = []

    def add(route: str, confidence: float, cond: str, eff: str, reason: str) -> None:
        relations.append(_Relation(route, _adjust(confidence, role, reason), cond, eff, reason))

    if _same_with_without_vpn(raw) or _vpn_does_not_help(raw):
        add("neutral", 0.97, condition, "NO_VPN_EFFECT", "vpn_no_effect")

    if _false_detection(clause, local_anchor):
        add("direct", 0.99, "DISABLE_VPN", "FALSE_DETECTION", "false_vpn_detection")

    disable_indexes = _near(_DISABLE_LEMMAS, clause, local_anchor, 5)
    if disable_indexes and any(not _is_negated(clause, i) for i in disable_indexes):
        explicit = _contains(clause, _REQUIRE_LEMMAS) or _contains(clause, _ACCESS_LEMMAS)
        add(
            "direct",
            0.97 if explicit else 0.66,
            "DISABLE_VPN",
            "REQUIRED" if explicit else "ADVICE",
            "requires_disable_vpn" if explicit else "disable_vpn",
        )

    if _near(_DETECT_LEMMAS, clause, local_anchor, 6):
        add("direct", 0.96, "VPN", "DETECTED", "vpn_detected")

    # Colloquial but quite specific: "у приложения аллергия на VPN", "не любит VPN".
    lower_raw = raw.lower()
    if re.search(r"(?:аллерги\w*|не\s+любит|не\s+дружит)[^.!?]{0,35}(?:vpn|впн|квн)", lower_raw, re.I):
        add("direct", 0.91, "WITH_VPN", "NOT_WORKING", "vpn_allergy")

    if effect == "NOT_WORKING":
        if condition == "WITH_VPN":
            add("direct", 0.94, condition, effect, "fails_with_vpn")
        elif condition == "WITHOUT_VPN":
            add("proxy", 0.97, condition, effect, "fails_without_vpn")
    elif effect == "WORKING":
        if condition == "WITH_VPN":
            confidence = 0.97 if _contains_only(clause) else 0.66
            add("proxy", confidence, condition, effect, "works_only_with_vpn" if confidence > 0.9 else "works_with_vpn")
        elif condition == "WITHOUT_VPN" and _contains_goal(clause):
            # "сделайте, чтобы работало без VPN" describes the desired state,
            # so it is evidence that VPN is currently required.
            add("proxy", 0.94, condition, "CURRENTLY_REQUIRES_VPN", "goal_work_without_vpn")

    if condition == "ENABLE_VPN":
        if effect in {"WORKING", None} or _contains(clause, _REQUIRE_LEMMAS | _ACCESS_LEMMAS):
            add("proxy", 0.94, condition, effect or "REQUIRED", "enable_vpn")

    if _near(_BLOCK_LEMMAS, clause, local_anchor, 7):
        # A block verb tied to WITH_VPN/VPN means VPN causes the problem. Under
        # WITHOUT_VPN it usually describes a restriction that VPN is bypassing.
        if condition in {"WITH_VPN", "VPN"}:
            add("direct", 0.94, condition, "BLOCKED", "vpn_blocks_access")
        elif condition == "WITHOUT_VPN":
            add("proxy", 0.93, condition, "BLOCKED", "blocked_without_vpn")

    if _near(_HELP_LEMMAS, clause, local_anchor, 6) and _problem_context(clause, app_name):
        # "VPN помогает защищать интернет" is deliberately excluded because it
        # has no app/access/problem context.
        add("proxy", 0.92, "VPN", "HELPS", "vpn_helps_access")

    # "VPN нужен для входа/доступа".
    if _contains(clause, _REQUIRE_LEMMAS) and _contains(clause, _ACCESS_LEMMAS):
        disable_near = any(not _is_negated(clause, i) for i in disable_indexes)
        if not disable_near:
            add("proxy", 0.95, "VPN", "REQUIRED", "vpn_required")

    # "VPN для обхода блокировок YouTube". This needs application/problem
    # context so generic descriptions of VPN technology stay neutral.
    if {"обход", "блокировка"}.issubset({token.lemma for token in clause}) and _problem_context(clause, app_name):
        add("proxy", 0.91, "VPN", "BYPASS_RESTRICTION", "vpn_bypasses_restriction")

    # If a normal work verb was found very far from the anchor, ignore it rather
    # than inventing a relation across unrelated parts of a long sentence.
    if effect_index is not None and abs(effect_index - local_anchor) > 8:
        relations = [rel for rel in relations if rel.effect not in {"WORKING", "NOT_WORKING"}]

    return relations


def _english_relations(sentence: str, *, role: str) -> list[_Relation]:
    text = sentence.lower()
    if "vpn" not in text:
        return []
    result: list[_Relation] = []

    def add(route: str, confidence: float, condition: str, effect: str, reason: str) -> None:
        result.append(_Relation(route, _adjust(confidence, role, reason), condition, effect, reason))

    if re.search(r"(?:does(?:n't| not)|won't|will not)\s+(?:work|open|load|login)[^.!?]{0,50}without\s+vpn", text) or re.search(
        r"without\s+vpn[^.!?]{0,50}(?:does(?:n't| not)|won't|will not)\s+(?:work|open|load|login)", text
    ):
        add("proxy", 0.97, "WITHOUT_VPN", "NOT_WORKING", "fails_without_vpn")
    if re.search(r"with\s+vpn[^.!?]{0,50}(?:does(?:n't| not)|won't|will not)\s+(?:work|open|load|login)", text):
        add("direct", 0.94, "WITH_VPN", "NOT_WORKING", "fails_with_vpn")
    if re.search(r"(?:disable|turn\s+off)[^.!?]{0,30}vpn", text):
        explicit = bool(re.search(r"(?:required|must|need|to\s+continue|to\s+login|for\s+access)", text))
        add("direct", 0.97 if explicit else 0.66, "DISABLE_VPN", "REQUIRED" if explicit else "ADVICE", "requires_disable_vpn" if explicit else "disable_vpn")
    if re.search(r"vpn[^.!?]{0,35}(?:detected|not\s+allowed|forbidden)", text):
        add("direct", 0.96, "VPN", "DETECTED", "vpn_detected")
    if re.search(r"(?:only\s+works?|works?\s+only)[^.!?]{0,35}with\s+vpn", text):
        add("proxy", 0.97, "WITH_VPN", "WORKING", "works_only_with_vpn")
    if re.search(r"vpn[^.!?]{0,30}(?:helps?|fixes?)[^.!?]{0,45}(?:work|open|load|login|access|block)", text):
        add("proxy", 0.92, "VPN", "HELPS", "vpn_helps_access")
    return result


def _resolve(relations: list[_Relation]) -> Classification:
    if not relations:
        return Classification(False, 0, verdict="neutral", confidence=0.0, route="neutral")

    best_direct = max((rel for rel in relations if rel.route == "direct"), key=lambda r: r.confidence, default=None)
    best_proxy = max((rel for rel in relations if rel.route == "proxy"), key=lambda r: r.confidence, default=None)
    best_neutral = max((rel for rel in relations if rel.route == "neutral"), key=lambda r: r.confidence, default=None)

    direct_conf = best_direct.confidence if best_direct else 0.0
    proxy_conf = best_proxy.confidence if best_proxy else 0.0
    neutral_conf = best_neutral.confidence if best_neutral else 0.0

    strongest_route = max(direct_conf, proxy_conf)
    if neutral_conf >= 0.90 and neutral_conf >= strongest_route - 0.02:
        route = "neutral"
        confidence = neutral_conf
        chosen = best_neutral
    elif direct_conf >= 0.52 or proxy_conf >= 0.52:
        if direct_conf and proxy_conf and abs(direct_conf - proxy_conf) < 0.10:
            route = "uncertain"
            confidence = max(direct_conf, proxy_conf)
            chosen = best_direct if direct_conf >= proxy_conf else best_proxy
        elif direct_conf > proxy_conf:
            route = "direct"
            confidence = direct_conf
            chosen = best_direct
        else:
            route = "proxy"
            confidence = proxy_conf
            chosen = best_proxy
    elif neutral_conf:
        route = "neutral"
        confidence = neutral_conf
        chosen = best_neutral
    else:
        route = "uncertain"
        confidence = max(direct_conf, proxy_conf)
        chosen = best_direct or best_proxy

    verdict = {
        "direct": "positive",
        "proxy": "negative",
        "neutral": "neutral",
        "uncertain": "uncertain",
    }[route]

    direct_reasons = sorted({rel.reason for rel in relations if rel.route == "direct" and rel.confidence >= 0.80})
    proxy_reasons = sorted({rel.reason for rel in relations if rel.route == "proxy" and rel.confidence >= 0.80})
    weak_reasons = sorted({rel.reason for rel in relations if rel.confidence < 0.80})

    return Classification(
        relevant=route in {"direct", "proxy"},
        score=int(round(confidence * 10)),
        strong_matches=direct_reasons,
        weak_matches=weak_reasons,
        verdict=verdict,
        confidence=round(confidence, 3),
        negative_matches=proxy_reasons,
        route=route,
        condition=chosen.condition if chosen else None,
        effect=chosen.effect if chosen else None,
    )


def analyze_text(
    text: str,
    *,
    role: str = "generic",
    app_name: str | None = None,
) -> Classification:
    normalized = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
    if not normalized or not _VPN_RE.search(normalized):
        return Classification(False, 0, verdict="neutral", confidence=0.0, route="neutral")

    relations: list[_Relation] = []
    sentences = list(sentenize(normalized))
    if not sentences:
        sentences = [type("Sentence", (), {"text": normalized})()]

    for sentence in sentences:
        sentence_text = sentence.text
        sentence_tokens = _tokens(sentence_text)
        for index, token in enumerate(sentence_tokens):
            if _is_anchor(token):
                relations.extend(
                    _relation_for_anchor(
                        sentence_tokens,
                        index,
                        role=role,
                        app_name=app_name,
                    )
                )
        relations.extend(_english_relations(sentence_text, role=role))

    return _resolve(relations)


def combine_classifications(*items: Classification) -> Classification:
    relations: list[_Relation] = []
    for item in items:
        if item.route not in {"direct", "proxy", "neutral"} or item.confidence <= 0:
            continue
        reason = (
            (item.strong_matches or item.negative_matches or item.weak_matches or [item.route])[0]
        )
        relations.append(
            _Relation(
                route=item.route,
                confidence=item.confidence,
                condition=item.condition or "VPN",
                effect=item.effect or "UNKNOWN",
                reason=reason,
            )
        )
    return _resolve(relations)


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

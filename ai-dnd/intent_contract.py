"""Intent contract (W09): one message, one intent kind; a line stays with its speaker; no choices for the player.

Pure text -> data. Nothing here touches world state, rolls dice or changes attack/save/death rules: it only separates a real
attack declaration from speech, a quoted report, a threat, a condition, a negation or an out-of-character remark, in Turkish and
English, and shapes the narrator's request. The existing session-bound Turkish owner (`game._has_explicit_attack_verb`,
`combat_lifecycle.is_attack_decision`) stays the combat gate; this contract is the shared, language-agnostic front door.
"""
from __future__ import annotations

import re
from typing import Any

_QUOTE = re.compile(r"[\"“”«»](.+?)[\"“”«»]")
_OOC = re.compile(r"^\s*(?:\(\s*ooc\b|\[\s*ooc\b|//|ooc\s*:|\(\(|\(\s*oyun\s+d[iı]ş[iı])", re.IGNORECASE)

_TR_ATTACK = re.compile(
    r"\b(?!kesin|keşif|kestirme|vurgu|dövme)(?:sald[ıi]r|vur|d[öo]v|kes|sapla|b[ıi]çakl|yumrukla)\w*", re.IGNORECASE)
_EN_ATTACK = re.compile(r"\b(?:attack|stab|slash|strike|punch|shoot|hit|smite|swing|slay)\w*", re.IGNORECASE)
_TR_NEGATION = re.compile(
    r"(?:\w(?:m[ıiuü]yorum|m[ıiuü]yoruz|mayaca[ğg]\w*|meyece[ğg]\w*|mad[ıi]m|medim)"
    r"|(?:mak|mek)\s+(?:istem\w*|dü[sş]ünm\w*)|(?:mak|mek)\s+niyetim\s+yok)\b", re.IGNORECASE)
_EN_NEGATION = re.compile(
    r"\b(?:don'?t|do not|won'?t|will not|never|refuse to|not going to|no intention of|not\s+attack|am not)\b", re.IGNORECASE)
_TR_CONDITION = re.compile(r"\b(?:e[ğg]er|[şs]ayet)\b|\w(?:rsa|rse|rlarsa|rlerse|[ıi]rsam|[ıi]rsem)\b", re.IGNORECASE)
_EN_CONDITION = re.compile(r"\b(?:if|unless|in case|should (?:he|she|they|it|you)|when(?:ever)? (?:he|she|they|it|you))\b",
                           re.IGNORECASE)
_TR_THREAT = re.compile(r"\b(?:pi[sş]man\s+ed\w*|uyar[ıi]yorum|tehdit|seni\s+(?:[öo]ld[üu]r|gebert|param\s+par[çc]a))", re.IGNORECASE)
_EN_THREAT = re.compile(r"\b(?:i'?m warning you|i warn you|you'?ll regret|make you regret|or else|"
                        r"i'?ll (?:kill|hurt|destroy|end|crush) you|i will (?:kill|hurt|destroy|end|crush) you)\b", re.IGNORECASE)
_EN_WORDS = re.compile(r"\b(?:the|i|you|my|with|and|if|he|she|they|him|her|it|is|am|will|don'?t)\b", re.IGNORECASE)
_JOKE = re.compile(r"\b(?:[şs]aka\s+yap\w*|bir\s+[şs]aka|tell (?:him|her|them|a)?\s*(?:a\s+)?joke|crack a joke)\b", re.IGNORECASE)


def _language(text: str) -> str:
    if re.search(r"[çğıöşüÇĞİÖŞÜ]", text):
        return "tr"
    return "en" if len(_EN_WORDS.findall(text)) >= 2 else "tr"


def _outside_quotes(text: str) -> str:
    return _QUOTE.sub(" ", text)


def _find_npc(text: str, context: dict[str, Any]) -> str | None:
    folded = text.casefold()
    best: tuple[int, int, Any] | None = None  # (match position, -name length, id): earliest, then longest
    for npc in context.get("npcs", []) or []:
        name = str(npc.get("name", "")).casefold()
        found = re.search(rf"(?<![\wçğıöşü]){re.escape(name)}(?:['’][a-zçğıöşü]+|(?![\wçğıöşü]))", folded) if name else None
        if found and (best is None or (found.start(), -len(name)) < best[:2]):
            best = (found.start(), -len(name), npc.get("id"))
    return best[2] if best else None


def resolve_intent(text: str, mode: str, context: dict[str, Any]) -> dict[str, Any]:
    """Classify one message: ooc | quote | negation | condition | threat | attack | speech | other."""
    text = str(text or "").strip()
    language = _language(text)
    result = {"kind": "other", "language": language, "speaker": "player", "addressee": _find_npc(text, context),
              "line": None, "quoted": [m.group(1) for m in _QUOTE.finditer(text)], "joke_request": bool(_JOKE.search(text))}
    if result["quoted"]:
        result["line"] = result["quoted"][0]
    if _OOC.match(text) or mode == "ooc":
        result["kind"] = "ooc"
        return result
    spoken = _outside_quotes(text)
    attack = _TR_ATTACK if language == "tr" else _EN_ATTACK
    negation = _TR_NEGATION if language == "tr" else _EN_NEGATION
    condition = _TR_CONDITION if language == "tr" else _EN_CONDITION
    threat = _TR_THREAT if language == "tr" else _EN_THREAT
    outside_attack = bool(attack.search(spoken))
    inside_attack = any(attack.search(item) for item in result["quoted"])
    if mode == "say":
        result["kind"] = "threat" if threat.search(text) else "speech"
        return result
    if inside_attack and not outside_attack:
        result["kind"] = "quote"  # an attack verb that survives only inside quotation is a report
        return result
    if outside_attack and negation.search(spoken):
        result["kind"] = "negation"
    elif outside_attack and condition.search(spoken):
        result["kind"] = "condition"
    elif threat.search(spoken) and not outside_attack:
        result["kind"] = "threat"
    elif outside_attack and not spoken.rstrip().endswith("?"):
        result["kind"] = "attack"
    elif result["line"] is not None:
        result["kind"] = "speech"
    return result


_DECISION_PATTERNS = (
    re.compile(r"\bsen\b[^.!?]{0,40}\b(?:hissed\w*|korku\w*|kızg\w*|karar\s+ver\w*|istiyor\w*|anl[ıi]yor\w*|seçiyor\w*)", re.IGNORECASE),
    re.compile(r"\b(?:ç[ıi]kmak|girmek|kaçmak|gitmek|a[cç]mak|saldırmak)\s+istiyorsun\b", re.IGNORECASE),
    re.compile(r"\b(?:iç[ıi]eri|içeri)\s+girmek\s+istiyorsun\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:feel|decide|want|choose|realize|resolve|wish|can'?t help but)\b", re.IGNORECASE),
    re.compile(r"\b(?:istiyorsun|karar veriyorsun|hissediyorsun|korkuyorsun|öfkeleniyorsun)\b", re.IGNORECASE),
)


def unauthorized_player_decisions(narration: str, intent: dict[str, Any]) -> int:
    """Count sentences that choose a feeling, goal or action for the player (spoken NPC quotes are not counted)."""
    count = 0
    for sentence in re.split(r"(?<=[.!?])\s+", _outside_quotes(str(narration))):
        if any(pattern.search(sentence) for pattern in _DECISION_PATTERNS):
            count += 1
    return count


def build_narration_request(intent: dict[str, Any], delta: dict[str, Any], knowledge: dict[str, Any]) -> dict[str, Any]:
    """The narrator's task: concrete, scene-toned, one intent; never a bare forbidden-word list."""
    task: dict[str, Any] = {"describe": "outcome of the single declared intent", "single_intent": intent.get("kind")}
    if intent.get("joke_request"):
        task["concrete_content_required"] = "joke_text"
        task["instruction"] = "Write the actual joke as a short quoted line; do not merely say that a joke is told."
    return {
        "intent_kind": intent.get("kind"), "speaker": intent.get("speaker", "player"), "addressee": intent.get("addressee"),
        "line": intent.get("line"), "task": task, "delta": delta or {}, "knowledge": knowledge or {},
        "forbidden": ["player_feelings", "player_goals", "player_actions"], "invent_mechanical_result": False,
    }


def narration_satisfies(request: dict[str, Any], narration: str) -> bool:
    """A joke request needs an actual quoted joke line, not a statement that a joke happened."""
    if request.get("task", {}).get("concrete_content_required") == "joke_text":
        quoted = [m.group(1) for m in _QUOTE.finditer(str(narration))]
        return any(len(item.split()) >= 5 for item in quoted)
    return bool(str(narration).strip())


def risk_gate(intent: dict[str, Any], knowledge: dict[str, Any], perceived_risks: list[dict[str, Any]]) -> dict[str, Any]:
    """Stop for confirmation only for a NEW, significant risk the player can perceive; never re-ask a known one."""
    known = set(knowledge.get("known_risk_ids") or [])
    new = [risk["id"] for risk in perceived_risks
           if risk.get("id") and risk.get("significant") and risk.get("perceivable") is True and risk["id"] not in known]
    return {"needs_confirmation": bool(new), "risk_ids": new}

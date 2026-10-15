"""Closed-family checks for player-visible narration.

Unrecognized sentences are texture, not new facts. A passing check is not a
canonical event. This module does not call a model and does not write world
state. Quests, rewards, and new people stay with the later narration safety
chain; this checker does not decide them.
"""

from __future__ import annotations

import re
from typing import Any


def fold(text: str) -> str:
    """Accent-fold for matching. The original wording stays with the caller."""
    value = str(text).replace("İ", "i").replace("I", "ı").casefold()
    value = value.translate(str.maketrans({
        "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u",
    }))
    value = re.sub(r"[’'`]+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def death_fold(text: str) -> str:
    """Fold like ``fold`` but keep ö and ü, so olur/ölür stay different."""
    value = str(text).replace("İ", "i").replace("I", "ı").casefold()
    value = value.translate(str.maketrans({
        "ı": "i", "ş": "s", "ç": "c", "ğ": "g",
    }))
    value = re.sub(r"[’'`]+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _enemy_actor_name(enemy: dict) -> str:
    """A display name can support a named claim. An id cannot."""
    for key in ("actor_name", "name"):
        value = enemy.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _side_outcome(result: dict, enemies: list, outcomes: tuple[str, ...]) -> bool:
    if result.get("action") == "attack" and result.get("outcome") in outcomes:
        return True
    return any(
        isinstance(enemy, dict) and enemy.get("outcome") in outcomes
        for enemy in enemies
    )


def packet_from_result(
    action_result: dict | None,
    *,
    door: dict | None = None,
    player_hidden: bool | None = None,
) -> dict[str, Any]:
    """Copy only facts Python already resolved. Missing keys are not events."""
    result = action_result if isinstance(action_result, dict) else {}
    enemies = result.get("enemy_actions")
    if enemies is None:
        single = result.get("enemy_action")
        enemies = [single] if isinstance(single, dict) else []
    dodge = any(
        isinstance(enemy, dict) and enemy.get("outcome") == "dodge"
        for enemy in enemies
    )
    damages: list[int] = []
    if result.get("action") == "attack" and isinstance(result.get("damage"), int):
        damages.append(result["damage"])
    for enemy in enemies:
        if isinstance(enemy, dict) and isinstance(enemy.get("damage"), int):
            damages.append(enemy["damage"])
    player_critical = (
        result.get("action") == "attack" and result.get("outcome") == "critical_hit"
    )
    exchanges: list[dict[str, Any]] = []
    if result.get("action") == "attack":
        exchanges.append({
            "actor": "player",
            "target": result.get("target_name") or result.get("target") or "",
            "outcome": result.get("outcome"),
            "damage": result.get("damage") if isinstance(result.get("damage"), int) else None,
            "critical": player_critical,
            "dead": result.get("target_status") == "dead",
        })
    for enemy in enemies:
        if not isinstance(enemy, dict):
            continue
        exchanges.append({
            "actor": _enemy_actor_name(enemy),
            "target": "player",
            "outcome": enemy.get("outcome"),
            "damage": enemy.get("damage") if isinstance(enemy.get("damage"), int) else None,
            "critical": enemy.get("outcome") == "critical_hit" or enemy.get("critical") is True,
            "dead": False,
        })
    packet: dict[str, Any] = {
        "action": result.get("action"),
        "outcome": result.get("outcome"),
        "skill": result.get("skill"),
        "target": result.get("target_name") or result.get("target"),
        "damage": damages[0] if damages else None,
        "damage_values": damages,
        "dc": result.get("dc") if isinstance(result.get("dc"), int) else None,
        "critical": player_critical,
        "dead": result.get("target_status") == "dead",
        "perception": None,
        "dodge": dodge,
        "any_hit": _side_outcome(result, enemies, ("hit", "critical_hit")),
        "any_miss": _side_outcome(result, enemies, ("miss",)),
        "door_name": None,
        "door_open": None,
        "door_locked": None,
        "player_hidden": None,
        "required": [],
    }
    if isinstance(door, dict):
        packet["door_name"] = door.get("name") or "Kapı"
        packet["door_open"] = bool(door.get("open"))
        packet["door_locked"] = bool(door.get("locked"))
    if (
        result.get("action") == "skill_check"
        and result.get("target_type") == "door"
        and packet["door_open"] is not None
    ):
        packet["required"].append("door_open" if packet["door_open"] else "door_closed")
    if result.get("action") == "skill_check" and result.get("skill") == "Stealth":
        if player_hidden is None:
            hidden = result.get("outcome") in ("success", "critical_success")
        else:
            hidden = bool(player_hidden)
        packet["player_hidden"] = hidden
        packet["required"].append("hidden" if hidden else "not_hidden")
    if result.get("action") == "attack":
        outcome = result.get("outcome")
        if outcome in ("hit", "critical_hit"):
            packet["required"].append("hit")
        elif outcome == "miss":
            packet["required"].append("miss")
        if player_critical:
            packet["required"].append("critical")
        if packet["dead"]:
            packet["required"].append("death")
        if dodge:
            packet["required"].append("dodge")
    if exchanges:
        packet["exchanges"] = exchanges
    return packet


_OPEN = re.compile(
    r"\b(?:kapi|kapisi|giris)\b.{0,40}\b(?:acildi|acilir|acik|aralandi|aralanir)\b|"
    r"\bkilit cozul"
)
_CLOSED = re.compile(
    r"\b(?:kapi|kapisi|giris|kilit)\b.{0,40}\b(?:kilitli kal\w*|kapali kal\w*|acilmaz\w*|acilmadi\w*)\b|"
    r"\bkilitli\b"
)
_HIT = re.compile(r"\b(?:darbe|isabet eder\w*|isabet etti\w*)\b")
_POSITIVE_HIT = re.compile(
    r"\bdarbe\s+alir\w*\b|\bdarbe\s+aldi\w*\b|\bisabet eder\w*\b|\bisabet etti\w*\b"
)
_NEGATED_HIT = re.compile(r"\bdarbe\s+almaz\w*\b|\bdarbe\s+almadi\w*\b")
_MISS = re.compile(r"\b(?:iskala\w*|isabet etmez)\b")
_CRITICAL = re.compile(r"\bkritik\b")
_DEATH = re.compile(r"\b(?:ölür|öldü|öldür\w*|yere düşer)\b")
_NAMED_BLOW = re.compile(
    r"\b([a-z0-9]+)\s+(?:(kritik)\s+)?(?:agir\s+)?(?:bir\s+)?darbe\s+"
    r"al(maz\w*|madi\w*|ir\w*|di\w*)?"
)
_NAMED_MISS = re.compile(r"\b([a-z0-9]+)(?:\s+i)?\s+iskala\w*")
_RECIPIENT_HURT = re.compile(
    r"(\d+)\s*(?:puan\s+)?hasar\s+alirsin\w*\b|"
    r"\bhasar\s*(?:puan\s*)?(\d+)\s+alirsin\w*\b"
)
_STOP = frozenset({
    "bir", "kritik", "agir", "bu", "su", "o", "ve", "sonra", "hedef",
    "hedefi", "saldirin", "saldiri", "rakip", "rakibin", "karsi", "kisa",
    "son", "ilk", "her", "sey", "ama", "ile",
})
_TRAILING = frozenset({"bir", "kritik", "agir", "ve", "ama", "ile"})
_BRIDGE = frozenset({"sendeleyerek"})
_GENERIC_BEFORE_SANA = _STOP | frozenset({
    "saldiri", "saldirisi", "saldiriyla", "saldirisiyla", "vurus", "vurusu",
    "vurusla", "hamle", "hamlesi",
})
_DEATH_NOISE = _STOP | _BRIDGE | frozenset({
    "darbe", "alir", "aldi", "aliyor", "almaz", "almadi", "yere", "hasar",
    "puan", "verir", "alirsin", "izler",
})
_NEGATION = re.compile(r"\bdegil\b")
_DODGE = re.compile(r"\bsavunmaya gec")
_HIDDEN = re.compile(r"\bgizlen\w*.{0,48}\b(?:basarili|tutar|gizli sayilir)\b")
_NOT_HIDDEN = re.compile(
    r"\bgizlen\w*.{0,48}\b(?:basarisiz|tutmaz|gizli sayilmaz)\b"
)
_PERCEPTION = re.compile(
    r"\bsesi duyup\b|\bseni duy\w*\b|\bseni gor\w*\b|\bseni gorm\w*\b|"
    r"\bfark edildi\w*\b|\bfark edilmedi\w*\b|"
    r"\b(?:isit\w*|duyup|duyunca|duyar\w*|duydu\w*)\b.{0,48}"
    r"\b(?:yonel\w*|bakar\w*|bakt\w*)\b|"
    r"\bayak ses\w*.{0,40}\b(?:isit\w*|yonel\w*)\b"
)
_MECHANICAL_NUMBER = re.compile(
    r"(\d+)\s*(?:puan\s+)?(hasar|can|hp|dc|zar|altin|gp)\b|"
    r"\b(hasar|can|hp|dc|zar|altin|gp)\s*(?:puan\s*)?(\d+)"
)
_OTHER_TARGET = re.compile(r"\bbaska bir dusman\w*\b")
_UNRESOLVED_PLAYER_ATTACK = re.compile(
    r"\bsana\s+(?:karsi\s+)?saldir\w*\b"
)


def _door_polarity(folded: str) -> tuple[str | None, str]:
    """Return open, closed, or both after a short negation window."""
    open_match = _OPEN.search(folded)
    closed_match = _CLOSED.search(folded)
    open_flag = open_match is not None
    closed_flag = closed_match is not None
    open_span = open_match.group(0) if open_match else ""
    closed_span = closed_match.group(0) if closed_match else ""
    if open_match and _NEGATION.search(folded[open_match.end():open_match.end() + 24]):
        open_flag = False
        closed_flag = True
        closed_span = closed_span or open_span
    elif closed_match and _NEGATION.search(folded[closed_match.end():closed_match.end() + 24]):
        closed_flag = False
        open_flag = True
        open_span = open_span or closed_span
    if open_flag and closed_flag:
        return "both", open_span or closed_span
    if open_flag:
        return "open", open_span
    if closed_flag:
        return "closed", closed_span
    return None, ""


def _hit_present(folded: str) -> bool:
    if _POSITIVE_HIT.search(folded):
        return True
    return _HIT.search(folded) is not None and _NEGATED_HIT.search(folded) is None


def _miss_present(folded: str) -> bool:
    return _MISS.search(folded) is not None or _NEGATED_HIT.search(folded) is not None


def _family_present(family: str, folded: str, death_folded: str | None = None) -> bool:
    polarity, _span = _door_polarity(folded)
    if family == "door_open":
        return polarity == "open"
    if family == "door_closed":
        return polarity == "closed"
    if family == "hit":
        return _hit_present(folded)
    if family == "miss":
        return _miss_present(folded)
    if family == "critical":
        return _CRITICAL.search(folded) is not None
    if family == "death":
        return _DEATH.search(death_folded if death_folded is not None else folded) is not None
    if family == "dodge":
        return _DODGE.search(folded) is not None
    if family == "hidden":
        return _HIDDEN.search(folded) is not None and _NOT_HIDDEN.search(folded) is None
    if family == "not_hidden":
        return _NOT_HIDDEN.search(folded) is not None
    return False


def _reject(reason: str, span: str) -> dict[str, Any]:
    return {"reject": True, "reason": reason, "span": span[:160]}


def _clauses(narration: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?]+", str(narration)) if part.strip()]


def _landed(exchange: dict) -> bool:
    return exchange.get("outcome") in ("hit", "critical_hit")


def _targets_named(exchanges: list, name: str) -> list:
    key = fold(name)
    return [
        exchange for exchange in exchanges
        if fold(str(exchange.get("target") or "")) == key
    ]


def _player_received(exchanges: list) -> list:
    return [exchange for exchange in exchanges if exchange.get("target") == "player"]


def _player_dealt(exchanges: list) -> list:
    return [exchange for exchange in exchanges if exchange.get("actor") == "player"]


def _catalog(exchanges: list, field: str, name_fold) -> list[tuple[str, dict]]:
    catalog = []
    for exchange in exchanges:
        name = name_fold(str(exchange.get(field) or ""))
        if not name or name in _STOP or name == "player":
            continue
        catalog.append((name, exchange))
    return catalog


def _matching_tail(tokens: list[str], catalog: list[tuple[str, dict]]) -> list[dict]:
    if not tokens:
        return []
    tail = " ".join(tokens)
    best_len = -1
    found: list[dict] = []
    for name, exchange in catalog:
        if tail == name or tail.endswith(" " + name):
            if len(name) > best_len:
                best_len = len(name)
                found = [exchange]
            elif len(name) == best_len:
                found.append(exchange)
    return found


def _subject_exchanges(tokens: list[str], catalog: list[tuple[str, dict]]):
    tokens = list(tokens)
    while tokens and tokens[-1] in _TRAILING:
        tokens.pop()
    found = _matching_tail(tokens, catalog)
    if found:
        return "known", found
    if tokens and tokens[-1] in _BRIDGE:
        tokens.pop()
        while tokens and tokens[-1] in _TRAILING:
            tokens.pop()
        found = _matching_tail(tokens, catalog)
        if found:
            return "known", found
    if not tokens:
        return "unnamed", []
    return "unknown", tokens[-1]


def _hasar_numbers(text: str) -> list[int]:
    numbers = []
    for match in _MECHANICAL_NUMBER.finditer(text):
        kind = match.group(2) or match.group(3)
        if kind != "hasar":
            continue
        numbers.append(int(match.group(1) or match.group(4)))
    return numbers


def _target_hasar_numbers(region: str) -> list[int]:
    numbers = []
    for match in _MECHANICAL_NUMBER.finditer(region):
        kind = match.group(2) or match.group(3)
        if kind != "hasar":
            continue
        before = region[max(0, match.start() - 24):match.start()]
        after = region[match.end():match.end() + 12]
        if re.search(r"\bsana\b", before) or re.search(r"^\s+alirsin\b", after):
            continue
        numbers.append(int(match.group(1) or match.group(4)))
    return numbers


def _damage_fits(exchanges: list[dict], numbers: list[int]) -> list[dict]:
    if not numbers:
        return exchanges
    return [
        exchange for exchange in exchanges
        if all(number == exchange.get("damage") for number in numbers)
    ]


def _bind_clause(clause: str, exchanges: list) -> dict | None:
    """Bind every claim in the clause to its own subject. A nearby true name does not transfer."""
    targets = _catalog(exchanges, "target", fold)
    actors = _catalog(exchanges, "actor", fold)
    blows = list(_NAMED_BLOW.finditer(clause))
    critical_checked = False
    for index, blow in enumerate(blows):
        previous = blows[index - 1].end() if index else 0
        darbe_at = clause.find("darbe", blow.start())
        window = clause[previous:darbe_at if darbe_at >= 0 else blow.end()]
        kind, subject = _subject_exchanges(window.split(), targets)
        suffix = blow.group(3) or ""
        negated = suffix.startswith("maz") or suffix.startswith("madi")
        crit_word = bool(blow.group(2))
        next_start = blows[index + 1].start() if index + 1 < len(blows) else len(clause)
        numbers = _target_hasar_numbers(clause[blow.end():next_start])
        if kind == "unknown":
            return _reject("COMBAT_RESULT_CONTRADICTION", str(subject))
        if kind == "unnamed":
            if negated and any(_landed(item) for item in _player_dealt(exchanges)):
                return _reject("COMBAT_RESULT_CONTRADICTION", "darbe almaz")
            if not negated and not any(_landed(item) for item in exchanges):
                return _reject("COMBAT_RESULT_CONTRADICTION", "isabet")
            if crit_word:
                critical_checked = True
                if not any(item.get("critical") for item in _player_dealt(exchanges)):
                    return _reject("COMBAT_RESULT_CONTRADICTION", "kritik")
            continue
        if negated:
            if any(_landed(item) for item in subject):
                return _reject("COMBAT_RESULT_CONTRADICTION", "darbe almaz")
            continue
        landed = [item for item in subject if _landed(item)]
        if not landed:
            return _reject("COMBAT_RESULT_CONTRADICTION", "isabet")
        if crit_word:
            critical_checked = True
            if not any(item.get("critical") for item in landed):
                return _reject("COMBAT_RESULT_CONTRADICTION", "kritik")
        if numbers and not _damage_fits(landed, numbers):
            return _reject("MECHANICAL_NUMBER", f"{numbers[0]} hasar")

    for match in re.finditer(r"\bsana\b", clause):
        span = clause[max(0, match.start() - 48):match.end() + 64]
        numbers = _hasar_numbers(clause[match.end():match.end() + 64])
        if not (numbers or _CRITICAL.search(span) or _hit_present(span) or _MISS.search(span)):
            continue
        kind, subject = _actor_before_sana(clause[:match.start()].split(), actors)
        if kind == "unknown":
            return _reject("COMBAT_RESULT_CONTRADICTION", str(subject))
        pool = subject if kind == "known" else _player_received(exchanges)
        landed = [item for item in pool if _landed(item)]
        if _hit_present(span) and not landed:
            return _reject("COMBAT_RESULT_CONTRADICTION", "isabet")
        fitting = _damage_fits(landed, numbers)
        if numbers and not fitting:
            return _reject("MECHANICAL_NUMBER", f"{numbers[0]} hasar")
        krit_scope = span if kind == "known" else clause
        if _CRITICAL.search(krit_scope):
            critical_checked = True
            if not any(item.get("critical") for item in (fitting or landed)):
                return _reject("COMBAT_RESULT_CONTRADICTION", "kritik")

    received = [item for item in _player_received(exchanges) if _landed(item)]
    for match in _RECIPIENT_HURT.finditer(clause):
        number = int(match.group(1) or match.group(2))
        if not any(item.get("damage") == number for item in received):
            return _reject("MECHANICAL_NUMBER", match.group(0))

    miss = _NAMED_MISS.search(clause)
    if miss:
        name = miss.group(1)
        if name == "seni" or (name in _STOP and re.search(r"\bseni\b", clause)):
            matched = _player_received(exchanges)
        elif name not in _STOP:
            matched = _targets_named(exchanges, name)
        else:
            matched = _player_dealt(exchanges)
        if not any(item.get("outcome") == "miss" for item in matched):
            return _reject("COMBAT_RESULT_CONTRADICTION", "iskalama")
    elif _MISS.search(clause):
        matched = _player_received(exchanges) if re.search(r"\bseni\b", clause) else _player_dealt(exchanges)
        if not any(item.get("outcome") == "miss" for item in matched):
            return _reject("COMBAT_RESULT_CONTRADICTION", "iskalama")

    if _hit_present(clause) and not any(_landed(item) for item in exchanges):
        return _reject("COMBAT_RESULT_CONTRADICTION", "isabet")

    if _CRITICAL.search(clause) and not critical_checked:
        return _reject("COMBAT_RESULT_CONTRADICTION", "kritik")
    return None


def _actor_before_sana(tokens: list[str], actors: list[tuple[str, dict]]):
    tokens = list(tokens)
    while tokens and tokens[-1] in _TRAILING:
        tokens.pop()
    found = _matching_tail(tokens, actors)
    if found:
        return "known", found
    if not tokens or tokens[-1] in _GENERIC_BEFORE_SANA:
        return "unnamed", []
    return "unknown", tokens[-1]


def _bind_death(narration: str, exchanges: list, facts: dict) -> dict | None:
    catalog = _catalog(exchanges, "target", death_fold)
    for clause in _clauses(narration):
        folded = death_fold(clause)
        previous = 0
        for death in _DEATH.finditer(folded):
            tokens = [
                token for token in folded[previous:death.start()].split()
                if not token.isdigit()
            ]
            while tokens and tokens[-1] in _DEATH_NOISE:
                tokens.pop()
            found = _matching_tail(tokens, catalog)
            if not found and tokens and tokens[-1] in _BRIDGE:
                tokens.pop()
                while tokens and tokens[-1] in _DEATH_NOISE:
                    tokens.pop()
                found = _matching_tail(tokens, catalog)
            if found:
                if not any(item.get("dead") for item in found):
                    return _reject("COMBAT_RESULT_CONTRADICTION", "olum")
            elif tokens:
                return _reject("COMBAT_RESULT_CONTRADICTION", "olum")
            elif not facts.get("dead") and not any(item.get("dead") for item in exchanges):
                return _reject("COMBAT_RESULT_CONTRADICTION", "olum")
            previous = death.end()
    return None


def assess(narration: str, packet: dict | None) -> dict[str, Any]:
    """Reject a clear contradiction. Leave unrecognized wording alone."""
    facts = packet if isinstance(packet, dict) else {}
    folded = fold(narration)
    death_text = death_fold(narration)
    if not folded:
        return {"reject": False, "reason": None, "span": None}

    if _PERCEPTION.search(folded) and not facts.get("perception"):
        span = _PERCEPTION.search(folded).group(0)
        return _reject("PERCEPTION_NOT_RESOLVED", span)

    if _OTHER_TARGET.search(folded) and facts.get("target"):
        return _reject("COMBAT_RESULT_CONTRADICTION", "baska bir dusman")

    if _DODGE.search(folded) and not facts.get("dodge"):
        return _reject("COMBAT_RESULT_CONTRADICTION", "savunmaya gec")
    exchanges = [item for item in facts.get("exchanges") or [] if isinstance(item, dict)]
    if _UNRESOLVED_PLAYER_ATTACK.search(folded):
        incoming_attack = any(
            fold(item.get("actor", "")) not in {"", "player", "sen"}
            and fold(item.get("target", "")) in {"player", "sen"}
            and item.get("outcome") in {"hit", "miss", "critical_hit"}
            for item in exchanges
        )
        if not incoming_attack:
            return _reject(
                "COMBAT_RESULT_CONTRADICTION",
                _UNRESOLVED_PLAYER_ATTACK.search(folded).group(0),
            )
    if exchanges:
        for clause in _clauses(narration):
            bound = _bind_clause(fold(clause), exchanges)
            if bound:
                return bound
    else:
        if (
            facts.get("action") == "attack"
            and _CRITICAL.search(folded)
            and not facts.get("critical")
        ):
            return _reject("COMBAT_RESULT_CONTRADICTION", "kritik")
        if facts.get("action") == "attack" and _hit_present(folded) and not facts.get("any_hit"):
            return _reject("COMBAT_RESULT_CONTRADICTION", "isabet")
        if facts.get("action") == "attack" and _miss_present(folded) and not facts.get("any_miss"):
            return _reject("COMBAT_RESULT_CONTRADICTION", "iskalama")

    polarity, door_span = _door_polarity(folded)
    door_open = facts.get("door_open")
    if polarity == "both":
        return _reject("DOOR_RESULT_CONTRADICTION", door_span)
    if polarity == "open" and door_open is not True:
        return _reject("DOOR_RESULT_CONTRADICTION", door_span)
    if polarity == "closed" and door_open is not False:
        return _reject("DOOR_RESULT_CONTRADICTION", door_span)

    if _HIDDEN.search(folded) and facts.get("player_hidden") is not True:
        return _reject("SKILL_RESULT_CONTRADICTION", "gizlenme")
    if _NOT_HIDDEN.search(folded) and facts.get("player_hidden") is not False:
        return _reject("SKILL_RESULT_CONTRADICTION", "gizlenme")

    allowed_damage = [
        number for number in facts.get("damage_values") or []
        if isinstance(number, int)
    ]
    if isinstance(facts.get("damage"), int) and facts["damage"] not in allowed_damage:
        allowed_damage.append(facts["damage"])
    allowed_rolls = [
        number for number in facts.get("rolls") or []
        if isinstance(number, int)
    ]
    for match in _MECHANICAL_NUMBER.finditer(folded):
        raw = match.group(1) or match.group(4)
        kind = match.group(2) or match.group(3)
        number = int(raw)
        if kind == "hasar" and number not in allowed_damage:
            return _reject("MECHANICAL_NUMBER", match.group(0))
        if kind in {"can", "hp"} and facts.get("hp") != number:
            return _reject("MECHANICAL_NUMBER", match.group(0))
        if kind == "dc" and facts.get("dc") != number:
            return _reject("MECHANICAL_NUMBER", match.group(0))
        if kind == "zar" and number not in allowed_rolls:
            return _reject("MECHANICAL_NUMBER", match.group(0))
        if kind in {"altin", "gp"} and facts.get("gold") != number:
            return _reject("MECHANICAL_NUMBER", match.group(0))

    if exchanges:
        death_bound = _bind_death(narration, exchanges, facts)
        if death_bound:
            return death_bound
    elif _DEATH.search(death_text) and not facts.get("dead"):
        return _reject("COMBAT_RESULT_CONTRADICTION", "olum")

    for family in facts.get("required") or []:
        if not _family_present(family, folded, death_text):
            return _reject("MISSING_REQUIRED_OUTCOME", family)
    return {"reject": False, "reason": None, "span": None}


def fallback_sentence(packet: dict | None) -> str | None:
    """One safe sentence for the required facts. Texture is left to Qwen."""
    facts = packet if isinstance(packet, dict) else {}
    required = list(facts.get("required") or [])
    name = facts.get("door_name") or "Kapı"
    parts: list[str] = []
    if "door_open" in required:
        parts.append(f"{name} açılır.")
    elif "door_closed" in required:
        parts.append(f"{name} kilitli kalır.")
    if "hidden" in required:
        parts.append("Gizlenme girişimin tutar.")
    elif "not_hidden" in required:
        parts.append("Gizlenme girişimin tutmaz; gizli sayılmazsın.")
    exchanges = [item for item in facts.get("exchanges") or [] if isinstance(item, dict)]
    player_exchange = next((item for item in exchanges if item.get("actor") == "player"), None)
    player_critical = player_exchange.get("critical") if player_exchange else facts.get("critical")
    if "miss" in required:
        parts.append("Saldırın hedefi ıskalar.")
    elif "hit" in required:
        target = facts.get("target") or "Hedef"
        kind = "kritik bir darbe" if player_critical else "bir darbe"
        damage = facts.get("damage")
        sentence = f"{target}, {kind} alır"
        if isinstance(damage, int):
            sentence += f": {damage} hasar"
        sentence += "."
        parts.append(sentence)
    if "death" in required:
        parts.append(f"{facts.get('target') or 'Hedef'} ölür.")
    if "dodge" in required:
        parts.append("Rakibin savunmaya geçer.")
    if not parts:
        return None
    return " ".join(parts)

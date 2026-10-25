"""Separate server-attributed NPC words from authoritative scene narration.

This module neither creates entities nor grants permission for mechanical or
identity claims. It scopes name detection to narration and distinguishes
nonbinding suggestions and explicit denials from affirmative events.
All other safety checks still inspect the complete response.
"""

import re

from narration_claims import fold


def normalize_bound_speech_label(raw, npc, *, visible=False):
    """Remove one redundant public-speaker wrapper, never narrative content."""
    import living_world
    if (
        not isinstance(raw, str) or not isinstance(npc, dict) or not visible
        or npc.get("hidden") or npc.get("discovered") is False
        or not living_world.npc_name_known_to_player(npc)
    ):
        return raw
    name = npc.get("name")
    if not isinstance(name, str) or not name.strip():
        return raw
    prefix = name.strip() + ": "
    if not raw.startswith(prefix):
        return raw
    quoted = raw[len(prefix):]
    for opening, closing in (("“", "”"), ('"', '"')):
        if quoted.startswith(opening) and quoted.endswith(closing):
            inner = quoted[1:-1]
            if inner.strip() and not any(mark in inner for mark in ('“', '”', '"')):
                return inner
    return raw


def bound_fields(payload, npc, action_result):
    if not all(isinstance(value, dict) for value in (payload, npc, action_result)):
        return None
    npc_id = npc.get("id")
    if (
        not isinstance(npc_id, str) or not npc_id
        or payload.get("source") != "experimental_attributed_speech"
        or payload.get("speaker_id") != npc_id
        or action_result.get("npc_id") != npc_id
        or action_result.get("status") != "experimental_attributed_speech"
        or action_result.get("action") not in {"dialogue", "query"}
    ):
        return None
    spoken, stage = payload.get("spoken_text"), payload.get("stage_direction")
    if (
        not isinstance(spoken, str) or not spoken.strip() or len(spoken) > 600
        or not isinstance(stage, str) or len(stage) > 600
    ):
        return None
    return spoken.strip(), stage.strip()


def narrated_entity_text(narration, payload, npc, action_result):
    """Keep the full check unless both attribution and exact text match.

Mentioning someone in an NPC's words is not an entity creation proposal. In
particular, capitalized sentence starters must not become invented NPCs.
Stage directions are still narration, even when attached to accepted speech.
"""
    fields = fields_for_narration(narration, payload, npc, action_result)
    if fields is None:
        return narration
    spoken, stage = fields
    return stage


def fields_for_narration(narration, payload, npc, action_result):
    fields = bound_fields(payload, npc, action_result)
    if fields is None:
        return None
    spoken, stage = fields
    return fields if narration == " ".join(part for part in (stage, spoken) if part) else None


def is_nonassertive_collective(verb, tail):
    """A proposal, possibility, condition or explicit denial is not a move.

    Only use this distinction inside exactly bound NPC speech. Present/past
    affirmative events and unilateral future commitments remain claims. A
    negative finite verb followed by a reversal is not a clear denial.
    """
    word = fold(verb)
    if re.fullmatch(r"\w+(?:alim|elim|sak|sek)", word):
        return True
    if re.fullmatch(r"\w+(?:abilir|ebilir)(?:iz|dik)?", word):
        return True
    if not re.fullmatch(
        r"\w+(?:mayiz|meyiz|m[iu]yoruz|madik|medik|mayacagiz|meyecegiz)", word
    ):
        return False
    clause_tail = re.split(r"[.!?;\n]", tail, maxsplit=1)[0]
    return not re.search(
        r"^(?:degil\w*|diyem(?:em|eyiz)|soyleyem(?:em|eyiz)|"
        r"denemez|soylenemez|demem|inkar edemem)\b", fold(clause_tail)
    )


def explicit_history_denial(text, match):
    """Recognize a local denial, never a denial elsewhere in the response.

An uncertainty predicate must govern a nominalized history clause. An
affirmative finite sentence followed by uncertainty is not a clear denial.
Double negatives and a later affirmative claim remain subject to validation.
"""
    claim = fold(match.group(0))
    tail = re.split(
        r"[.!?;\n]|\b(?:ama|ancak|fakat|oysa)\b",
        text[match.end():match.end() + 100], maxsplit=1, flags=re.IGNORECASE,
    )[0]
    tail = fold(tail)
    reversal = r"^(?:degil\w*|diyemem|soyleyemem|demem|inkar edemem)\b"
    if re.search(r"\w+(?:madim|medim|madik|medik|mamistim|memistim)\b$", claim):
        return not re.search(reversal, tail)
    uncertainty = re.search(r"\b(?:hatirlamiyorum|hatirlamadim|bilmiyorum|emin degilim)\b", tail)
    if uncertainty is None or re.search(reversal, tail[uncertainty.end():].strip()):
        return False
    return re.search(r"\b\w+(?:dig|tig|dug|tug)[iu][mn]\w*\b", claim + " " + tail[:uncertainty.start()]) is not None


def matches_speaker_identity(claim, allowed_names):
    """Match the bound name, including an apostrophized first-person copula.

    Do not strip arbitrary suffixes or accept name prefixes: Selim is not Sel.
    The apostrophe distinguishes a proper-name inflection from a different name.
    This recognizes identity wording only; disclosure and other guards still run.
    """
    def identity_fold(value):
        return fold(value).translate(str.maketrans({"â": "a", "î": "i", "û": "u"}))

    if identity_fold(claim) in allowed_names:
        return True
    inflected = re.fullmatch(r"(.+)['’](?:y?[ıiuü]m)", claim, re.IGNORECASE)
    return inflected is not None and identity_fold(inflected.group(1)) in allowed_names


def mask_spoken_questions(text, spoken_start):
    """Questions in exactly bound NPC speech do not commit player agency.

    Keep stage directions and preceding declarative sentences intact. Only the
    agency/mental-state view uses this mask; identity, history, rewards and all
    other validators still receive the complete original response.
    """
    if spoken_start is None or not 0 <= spoken_start <= len(text):
        return text
    speech = text[spoken_start:]
    speech = re.sub(r"[^.!?;\n]+\?", lambda match: " " * len(match.group(0)), speech)
    return text[:spoken_start] + speech


def is_spoken_player_address(text, match, spoken_start):
    """A disclosed-name address or confirmation question is not narrator agency.

    The caller proves disclosure to this exact NPC. Stage directions and
    declarative third-person action subjects do not receive this exception.
    """
    if spoken_start is None or match.start() < spoken_start:
        return False
    if re.match(r"\s*(?:[,;.!?]|$)", text[match.end():]) is not None:
        return True
    return any(
        question.start() + spoken_start <= match.start()
        and match.end() <= question.end() + spoken_start
        for question in re.finditer(r"[^.!?;\n]+\?", text[spoken_start:])
    )


def hidden_identity_scan_text(text, identity, world):
    """A public place label is not disclosure of a namesake NPC's identity.

    Mask only complete, registered, player-known, non-hidden multiword place
    labels in the identity-check view. Every other validator sees full text.
    Bare NPC names, unknown places and a label equal to the whole hidden
    identity stay checked. This function never changes player knowledge.
    """
    import exploration
    import npc_statements
    if not isinstance(world, dict) or not isinstance(world.get('locations'), dict):
        return text
    known = exploration.known_locations(world)
    def normalized(value):
        return fold(value).translate(str.maketrans({'â':'a','î':'i','û':'u'}))
    hidden = normalized(identity)
    labels = {
        normalized(record['name']) for key, record in world['locations'].items()
        if key in known and isinstance(record, dict) and not record.get('hidden')
        and isinstance(record.get('name'), str)
    }
    result = normalized(text)
    for label in sorted(labels, key=len, reverse=True):
        if len(label.split()) < 2 or label == hidden:
            continue
        pattern = r'(?<![a-z0-9])' + re.escape(label) + r'(?P<tail>[a-z0-9]*)\b'
        result = re.sub(
            pattern,
            lambda match: ' ' * len(match.group(0))
            if npc_statements._CASE_TAIL.fullmatch(match.group('tail'))
            else match.group(0),
            result,
        )
    return result


def mask_bound_self_name(text, identity, world, payload, npc, action_result):
    """Mask only an exact public speaker's first-person name claim for disclosure.

    This is an identity-scan view, never a rewritten reply. Stage directions,
    other mentions and all role/private-fact checks keep their original text.
    """
    import living_world
    fields = fields_for_narration(text, payload, npc, action_result)
    if fields is None or not isinstance(world, dict):
        return text
    canonical = next((record for record in world.get('npcs', [])
                      if isinstance(record, dict) and record.get('id') == npc.get('id')), None)
    if (canonical is None or canonical.get('hidden')
            or canonical.get('location') != world.get('location')
            or not living_world.npc_name_known_to_player(canonical)
            or fold(str(canonical.get('name', ''))) != fold(str(npc.get('name', '')))
            or fold(str(identity)) != fold(str(canonical.get('name', '')))):
        return text
    spoken, stage = fields
    name = re.escape(str(canonical['name']))
    claim = re.compile(
        r'(^|[.!?;]\s*)(?:benim\s+adım|adım|ismim|ben)\s+'
        r'(?P<name>' + name + r"(?:['’]y?[ıiuü]m)?)(?=\s*[,!.?;]|$)",
        re.IGNORECASE,
    )
    def mask(match):
        start, end = match.span('name')
        relative = start - match.start()
        return match.group(0)[:relative] + ' ' * (end - start) + match.group(0)[relative + end - start:]
    return ' '.join(part for part in (stage, claim.sub(mask, spoken)) if part)


def mask_visible_entity_labels(text, world):
    """Exclude whole known place/visible feature labels from person detection only."""
    import exploration
    import living_world
    if not isinstance(world, dict):
        return text
    labels = {record['name'] for record in living_world.visible_features(world)}
    known = exploration.known_locations(world)
    labels.update(record['name'] for key, record in world.get('locations', {}).items()
                  if key in known and isinstance(record, dict) and not record.get('hidden')
                  and isinstance(record.get('name'), str) and record['name'].strip())
    npc_names = {fold(str(record.get('name', ''))) for record in world.get('npcs', [])
                 if isinstance(record, dict)}
    for label in sorted(labels, key=len, reverse=True):
        if fold(label) in npc_names:
            continue
        def mask_label(match):
            # A known suffix must not conceal an unknown compound person name.
            preceding = re.search(r'([^\W\d_]+)\s+$', text[:match.start()])
            if preceding and preceding.group(1)[0].isupper():
                return match.group(0)
            return ' ' * len(match.group(0))
        text = re.sub(r'(?<!\w)' + re.escape(label) + r'(?!\w)',
                      mask_label, text, flags=re.IGNORECASE)
    return text


_MONTH_NAMES = frozenset({
    "ocak", "subat", "mart", "nisan", "mayis", "haziran",
    "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik",
})
_MONTH_PATTERN = re.compile(
    r"(?<!\w)(?P<name>\w+)\s+ay(?:ı|i|ında|inda|ının|inin|ına|ina|ından|indan|larında|larinda)\b",
    re.IGNORECASE,
)


def mask_calendar_month_name(text, identity):
    """Hide a month-name mention from the identity scan, nothing else.

    A hidden NPC named after a real Turkish month ("Kasım") must not make
    "Kasım ayında kar yağar" a disclosure. A bare name, "Ben Kasım" and
    "Kasım gülümsüyor" stay visible, and a name that is not a month is never
    masked. This returns a scan view; the narration itself is unchanged.
    """
    if not isinstance(text, str) or not isinstance(identity, str):
        return text
    if fold(identity) not in _MONTH_NAMES:
        return text

    def mask(match):
        if fold(match.group("name")) != fold(identity):
            return match.group(0)
        start, end = match.span("name")
        relative = start - match.start()
        blank = " " * (end - start)
        return match.group(0)[:relative] + blank + match.group(0)[relative + end - start:]

    return _MONTH_PATTERN.sub(mask, text)


_PLAYER_QUOTE = re.compile(
    r'[“"«]([^“”"«»\n]{1,300})[”"»]'
    r"|(?<![\wçğıöşüÇĞİÖŞÜ])['‘]([^'’\n]{1,300})['’](?![\wçğıöşüÇĞİÖŞÜ])",
    re.IGNORECASE,
)


def player_supplied_quote(player_input):
    """The words the player put in quotes, or None. An apostrophe is not a quote."""
    if not isinstance(player_input, str):
        return None
    match = _PLAYER_QUOTE.search(player_input)
    if match is None:
        return None
    text = (match.group(1) or match.group(2) or "").strip()
    return text or None


_PLAYER_ACT = re.compile(
    r"(?<![\wçğıöşüÇĞİÖŞÜ])(?P<stem>[\wçğıöşüÇĞİÖŞÜ]{6,}?)(?:yip|yıp|yup|yüp|ip|ıp|up|üp|erek|arak|miş|mış|muş|müş)\b",
    re.IGNORECASE,
)


def strip_player_echo(text, player_input):
    """Drop NPC sentences that replay the player's own gesture or quoted words."""
    text = strip_player_quote(text, player_input)
    if not isinstance(text, str) or not text.strip():
        return text
    stems = []
    for match in _PLAYER_ACT.finditer(player_input or ""):
        stem = fold(match.group("stem"))
        if len(stem) >= 6:
            stems.append(stem)
            stems.append(stem[:4])
    quote = player_supplied_quote(player_input)
    if quote:
        stems.extend(fold(word) for word in re.findall(r"\w{5,}", quote))
    if not stems:
        return text
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        folded = fold(sentence)
        if any(stem and stem in folded for stem in stems):
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


_UNGROUNDED_NOUN = re.compile(r"(?<![\wçğıöşüÇĞİÖŞÜ])([\wçğıöşüÇĞİÖŞÜ]{5,})")


def drop_ungrounded_prop_sentences(text, facts):
    """Drop a spoken sentence that names a prop the scene cannot support.

    A registered prop must bring one content word from its own description.
    A sentence that names no registered prop still drops when it contains a
    concrete noun absent from every fact. Ordinary short words stay.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    records = []
    packet = []
    for fact in facts or []:
        if not isinstance(fact, dict):
            continue
        labels = [fact.get("name") or "", *(fact.get("aliases") or [])]
        stems = [fold(label) for label in labels if isinstance(label, str) and label.strip()]
        description = fold(fact.get("description") or "")
        content = [
            word for word in description.split()
            if len(word) >= 5 and word not in stems
        ]
        records.append((stems, content))
        packet.extend(stems)
        packet.extend(description.split())
    packet_text = " ".join(packet)
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        folded = fold(sentence)
        grounded = False
        names_prop = False
        for stems, content in records:
            if not any(stem and stem in folded for stem in stems):
                continue
            names_prop = True
            if any(word and word in folded for word in content):
                grounded = True
                break
        if names_prop and not grounded:
            continue
        foreign = False
        for match in _UNGROUNDED_NOUN.finditer(sentence):
            stem = fold(match.group(1))
            if len(stem) < 5 or stem in packet_text:
                continue
            if stem.endswith(("iyor", "uyor", "acak", "ecek")):
                continue
            foreign = True
            break
        if foreign and not names_prop:
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


def strip_player_quote(text, player_input):
    """Drop the player's own quoted words from NPC speech. Other words stay."""
    quote = player_supplied_quote(player_input)
    if not quote or not isinstance(text, str) or fold(quote) not in fold(text):
        return text
    cleaned = re.sub(re.escape(quote), "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[“”\"«»‘’']\s*[“”\"«»‘’']", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip(" \t\"“”«»‘’'")

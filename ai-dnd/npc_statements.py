"""What NPCs actually said, kept apart from what is true in the world.

LR00 fix (owner P6 rejection, 18 Oct 2026). An NPC line the player saw is a
statement by that NPC: never a world fact, quest, reward or obligation. Two
things in those statements still matter to play and must not be forgotten:

* places the NPC named or vouched for ("Kızılhan", "açık bir han var"): kept as
  attributed references. The player can follow one; when they do, the place is
  created once and saved, with the NPC's words kept as claims, not as its state;
* commitments the NPC really made ("Hemen gidelim" after "beni hana götür"): a
  later "götüreceğini söylemiştin" is supported only by such a record, and an
  invented promise ("bana kılıç vereceğini söylemiştin") is not.

Everything lives in world_state[KEY], so it is saved, undone and replayed with
the turn like any other state. Matching is generic Turkish morphology, never a
list of names from one campaign.
"""

from __future__ import annotations

import re
from typing import Any

import living_world

KEY = "npc_statements"
SCHEMA_VERSION = 1
KEEP_PER_NPC = 40
MAX_REFERENCES = 60

# folded noun stem -> place kind (tavern is the existing venue kind; others are
# local_places kinds; "generic" places have no catalogue content).
PLACE_NOUNS: tuple[tuple[str, str], ...] = (
    ("meyhane", "tavern"), ("birahane", "tavern"), ("taverna", "tavern"),
    ("lokanta", "tavern"), ("han", "tavern"),
    ("camhane", "generic"), ("rasathane", "generic"),
    ("arsiv", "archive"), ("demirhane", "smithy"), ("demirci", "smithy"),
    ("tapinak", "temple"), ("tapinag", "temple"), ("mabet", "temple"), ("mabed", "temple"),
    ("liman", "harbor"), ("iskele", "harbor"), ("rihtim", "harbor"),
    ("pazar", "market"), ("carsi", "market"), ("kutuphane", "library"),
    ("firin", "bakery"), ("atolye", "workshop"), ("marangoz", "workshop"),
    ("kisla", "barracks"), ("karakol", "barracks"), ("mezarlik", "graveyard"),
    ("ahir", "stable"), ("dukkan", "generic"), ("meydan", "generic"),
    ("konak", "generic"), ("kule", "generic"), ("depo", "generic"), ("ambar", "generic"),
)
# A bare noun with only case endings after it is not a name ("Hanın yolu").
_CASE_TAIL = re.compile(
    r"^(?:i|in|ina|ini|inda|indan|a|e|da|de|dan|den|ta|te|tan|ten|ya|ye|yi|nin|nun|"
    r"lar|ler|lari|leri|larin|lerin|si|su|sina|sini|sinda|sindan|na|ne|nda|nde|ndan|nden|"
    r"i|u|ina|una|u|in|un|a|e)?$"
)
_EXISTENCE = re.compile(
    r"\b(?:var|vardir|bulunur|bulunuyor|bilirim|biliyorum|gidebilirsin|bulabilirsin|"
    r"ugrayabilirsin|onerim|oneririm|tavsiye)\b"
)
_ADJECTIVES = ("acik", "kapali", "ucuz", "pahali", "guvenli", "kalabalik", "sakin",
               "yakin", "uzak", "eski", "yeni", "temiz", "kirli", "iyi", "kotu")
_PLACE_RELATION = re.compile(
    r"\b(?:yamac\w*|bulun\w*|konumlan\w*|yer(?:idir|dir|i)\b|"
    r"(?:git|gid)\w*|"
    r"(?:kap\w*|sokak\w*|yol\w*|meydan\w*).{0,40}"
    r"\b(?:yan\w*|yakin\w*|karsi\w*))"
)
_PERSON_TITLES = frozenset({
    "amir", "baron", "barones", "bey", "beyefendi", "kont", "kontes",
    "kraliçe", "kralice", "kral", "lady", "lord", "paşa", "pasa",
    "prens", "prenses", "sör", "sor", "şövalye", "sovalye",
})
_DENIED_PLACE = re.compile(
    r"^\s*(?:diye\s+bir\s+yer\s+yok(?:tur)?|"
    r"(?:bir\s+yer\s+)?yok(?:tur)?|değil(?:dir)?|degil(?:dir)?|bulunmuyor)\b"
)
_DENIED_PLACE_PREDICATE = re.compile(r"\b(?:yok(?:tur)?|değil(?:dir)?|degil(?:dir)?|bulunmuyor)\b")

_REFUSAL = re.compile(
    r"\b(?:hayir|olmaz|yapamam|gidemem|goturemem|veremem|gosteremem|istemem|"
    r"\w+(?:emem|amam|meyecegim|mayacagim))\b"
)
_AGREE = re.compile(r"\b(?:tamam|olur|peki|elbette|tabii|tabi|hemen|haydi|hadi|gidelim|anlastik|kabul)\b")
_COMMIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("escort", re.compile(
        r"\b(?:gotur(?:urum|eyim|ecegim|uruz|elim)|gidelim|gidebiliriz|birlikte\s+gid\w*|"
        r"eslik\s+ed(?:erim|eyim|ecegim)|yol\s+gosteri\w*|yolu\s+gosteri\w*)\b")),
    ("show", re.compile(r"\bgoster(?:irim|eyim|ecegim)\b")),
    ("give", re.compile(r"\b(?:ver(?:irim|eyim|ecegim)|getir(?:irim|eyim|ecegim))\b")),
    ("meet", re.compile(
        r"\b(?:bulus(?:alim|uruz|abiliriz)|birlikte\s+ol(?:abiliriz|alim|uruz)|"
        r"orada\s+ol(?:acagim|urum|uruz|abiliriz)|bekle(?:rim|yecegim))\b")),
    ("help", re.compile(r"\byardim\s+ed(?:erim|eyim|ecegim)\b")),
)
_REQUEST_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("escort", re.compile(r"\b(?:gotur\w*|eslik\s+et\w*|yol\s+goster\w*|yolu\s+goster\w*)\b")),
    ("show", re.compile(r"\bgoster\w*\b")),
    ("give", re.compile(r"\b(?:ver\b|verir\s+misin|verebilir\w*|getir\w*)")),
    ("help", re.compile(r"\byardim\s+et\w*\b")),
)
# Claims the player makes about a past promise.
_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("escort", re.compile(r"\b(?:gotur\w*|eslik\s+ed\w*|eslik\s+et\w*|birlikte\s+gid\w*)\b")),
    ("show", re.compile(r"\bgoster(?:ecegini|ecektin|ecegin|ecegim|ecektin|mistin|din)\w*\b")),
    ("give", re.compile(r"\b(?:ver(?:ecegini|ecektin|ecegin|mistin|din|eceksin)|getir(?:ecegini|ecektin|mistin))\w*\b")),
    ("meet", re.compile(r"\b(?:bulus\w*|bekle(?:yecegini|yecektin)\w*)\b")),
    ("help", re.compile(r"\byardim\s+ed(?:ecegini|ecektin)\w*\b")),
)
_SAID_CLAIM = re.compile(
    r"\b(?:soyle\w*|demistin|dedin|demis\w*|bahset\w*|anlat\w*|soz\s+ver\w*|vadet\w*)\b"
)
_STOP = frozenset({
    "ben", "beni", "bana", "benim", "sen", "seni", "sana", "senin", "o", "onu", "ona",
    "bu", "bunu", "buna", "su", "sunu", "suna", "hani", "dun", "daha", "once", "az",
    "bir", "ve", "ile", "da", "de", "mi", "mu", "ki", "icin", "gibi", "cok", "en",
    "yakindaki", "yakin", "tamam", "hadi", "haydi", "lutfen", "sozun", "soz",
    "soylemistin", "demistin", "dedin", "bahsetmistin", "anlatmistin", "unuttun",
    "hatirliyor", "musun", "misin", "hatirla", "sadece", "simdi", "hemen",
})


def fold(text: Any) -> str:
    return living_world.normalize_text(text)


def _state(world: dict[str, Any]) -> dict[str, Any]:
    state = world.get(KEY)
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        state = {
            "schema_version": SCHEMA_VERSION,
            "next_reference": 1,
            "next_commitment": 1,
            "statements": {},
            "references": [],
            "commitments": [],
            "backfilled": False,
        }
        world[KEY] = state
    return state


def ensure(world: dict[str, Any]) -> dict[str, Any]:
    """Return the ledger; an older save is backfilled once from its speech log."""
    state = _state(world)
    if not state.get("backfilled"):
        state["backfilled"] = True
        log = world.get("npc_speech_log")
        if isinstance(log, dict):
            for npc_id, entries in log.items():
                npc = _npc(world, npc_id)
                if npc is None or not isinstance(entries, list):
                    continue
                for entry in entries:
                    if isinstance(entry, dict):
                        record(world, npc, entry.get("player", ""), entry.get("npc", ""), turn=None)
    return state


def view(world: dict[str, Any]) -> dict[str, Any]:
    """Read the ledger without writing anything into the world.

    An older save is backfilled on a scratch copy, so merely reading (a turn
    that turns out to belong to another owner) never changes saved state.
    The ids come out the same as a later real backfill (same order).
    """
    state = world.get(KEY)
    if isinstance(state, dict) and state.get("schema_version") == SCHEMA_VERSION:
        return state
    scratch = {
        "npcs": world.get("npcs", []),
        "npc_speech_log": world.get("npc_speech_log"),
        "locations": world.get("locations", {}),
        "location": world.get("location"),
        "flags": dict(world.get("flags", {}) or {}),
    }
    return ensure(scratch)


def _npc(world: dict[str, Any], npc_id: Any) -> dict[str, Any] | None:
    return next(
        (n for n in world.get("npcs", []) if isinstance(n, dict) and n.get("id") == npc_id),
        None,
    )


def _spoken_words(npc: dict[str, Any], shown: str) -> str:
    """The NPC's own words from a shown line ('Quarion, “...” diye yanıt verir')."""
    quoted = re.findall(r"[“\"]([^”\"]+)[”\"]", shown or "")
    if quoted:
        return " ".join(part.strip() for part in quoted if part.strip())
    return str(shown or "").strip()


def _settlement(world: dict[str, Any]) -> str | None:
    current = world.get("location")
    locations = world.get("locations", {})
    seen = set()
    while isinstance(current, str) and current not in seen:
        seen.add(current)
        record_ = locations.get(current) if isinstance(locations, dict) else None
        if not isinstance(record_, dict):
            return current
        if record_.get("type") == "city" or living_world.scene_kind(world, current) == "city":
            return current
        parent = record_.get("parent_location_id")
        if not isinstance(parent, str):
            return current
        current = parent
    return current


def place_kind_of(word: str) -> tuple[str, str] | None:
    """('han', 'tavern') when a folded word is or ends with a place noun."""
    for noun, kind in PLACE_NOUNS:
        if word.startswith(noun) and _CASE_TAIL.match(word[len(noun):] or ""):
            return noun, kind
    return None


def _named_places(text: str) -> list[tuple[str, str, str]]:
    """Proper place names in an NPC line -> [(display name, noun, kind)]."""
    found = []
    tokens = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû']+", text)

    def denied(name: str) -> bool:
        folded_text = fold(text)
        position = folded_text.find(fold(name))
        if position < 0:
            return False
        tail = folded_text[position + len(fold(name)):]
        return bool(_DENIED_PLACE.search(tail) or _DENIED_PLACE_PREDICATE.search(tail))

    for index, token in enumerate(tokens):
        bare = token.split("'")[0]
        if not bare or not bare[0].isupper():
            continue
        if index > 0 and tokens[index - 1][:1].isupper():
            continue  # a place head belongs to the full proper-name span
        folded = fold(bare)
        # Single word: "Kızılhan", "Kızılhanda" -> name before the case ending.
        for noun, kind in PLACE_NOUNS:
            position = folded.find(noun, 3)
            if position < 3 or len(noun) < 3:
                continue
            tail = folded[position + len(noun):]
            if _CASE_TAIL.match(tail):
                # Map the folded cut back onto the original spelling.
                display = bare[: position + len(noun)]
                if not denied(display):
                    found.append((display, noun, kind))
                break
        else:
            # Multi-word: capitalised words followed by a place noun word.
            if index + 1 < len(tokens):
                follow = fold(tokens[index + 1].split("'")[0])
                hit = place_kind_of(follow)
                if hit and tokens[index + 1][:1].isupper():
                    noun, kind = hit
                    words = [bare]
                    back = index - 1
                    while back >= 0 and tokens[back][:1].isupper() and back > 0:
                        words.insert(0, tokens[back].split("'")[0])
                        back -= 1
                    head = tokens[index + 1].split("'")[0]
                    display = " ".join([*words, head])
                    if not denied(display):
                        found.append((display, noun, kind))
    # NPC speech is evidence for an attributed named-place reference even when
    # its head noun is not in PLACE_NOUNS. Keep the complete, spoken proper-name
    # span and treat its type as generic; do not promote the quote to world fact.
    for index, token in enumerate(tokens):
        bare = token.split("'")[0]
        if not bare or not bare[0].isupper():
            continue
        if index > 0 and tokens[index - 1][:1].isupper():
            continue  # keep the maximal proper-name span, not its suffixes
        words = [bare]
        following = index + 1
        while (
            following < len(tokens)
            and tokens[following]
            and tokens[following][0].isupper()
        ):
            words.append(tokens[following].split("'")[0])
            following += 1
        if len(words) < 2:
            continue
        if fold(words[0]) in _PERSON_TITLES:
            continue
        display = " ".join(words)
        tail = fold(" ".join(tokens[following:]))
        if not _PLACE_RELATION.search(tail) or denied(display):
            continue
        found.append((display, fold(words[-1]), "generic"))
    # Sentence-initial ordinary words ("Bu", "Hanın") never survive the 3-char rule.
    unique = []
    for item in found:
        if fold(item[0]) not in {fold(x[0]) for x in unique}:
            unique.append(item)
    return unique


def _unnamed_place(folded: str) -> tuple[str, str, list[str]] | None:
    """'Çevrede açık bir han var' -> ('han', 'tavern', ['acik'])."""
    if not _EXISTENCE.search(folded):
        return None
    words = folded.split()
    for index, word in enumerate(words):
        hit = place_kind_of(word)
        if hit is None:
            continue
        window = words[max(0, index - 3): index]
        claims = [adj for adj in _ADJECTIVES if adj in window]
        return hit[0], hit[1], claims
    return None


def place_references(world: dict[str, Any], *, settlement_id: str | None = None) -> list[dict[str, Any]]:
    refs = view(world)["references"]
    return [
        ref for ref in refs
        if isinstance(ref, dict) and (settlement_id is None or ref.get("settlement_id") == settlement_id)
    ]


def _existing_location_named(world: dict[str, Any], name: str) -> str | None:
    target = fold(name)
    for location_id, location in world.get("locations", {}).items():
        if isinstance(location, dict) and fold(location.get("name", "")) == target:
            return location_id
    return None


def _add_reference(world, state, *, npc_id, name, noun, kind, claims, quote, turn, settlement):
    refs = state["references"]
    if name:
        key = fold(name)
        same = next((r for r in refs if r.get("name") and fold(r["name"]) == key), None)
        if same is not None:
            for claim in claims:
                if claim not in same["claims"]:
                    same["claims"].append(claim)
            return same
        # The same speaker naming the place they just vouched for.
        recent = next(
            (
                r for r in reversed(refs)
                if r.get("name") is None and r.get("said_by") == npc_id and r.get("place_kind") == kind
            ),
            None,
        )
        if recent is not None:
            recent["name"] = name
            recent["noun"] = noun
            recent["quotes"].append(quote[:240])
            for claim in claims:
                if claim not in recent["claims"]:
                    recent["claims"].append(claim)
            known = _existing_location_named(world, name)
            if known:
                recent.update(location_id=known, status="resolved")
            return recent
    elif any(r.get("said_by") == npc_id and r.get("place_kind") == kind and r.get("name") is None for r in refs):
        return None
    if len(refs) >= MAX_REFERENCES:
        return None
    number = state["next_reference"]
    state["next_reference"] = number + 1
    known = _existing_location_named(world, name) if name else None
    ref = {
        "id": f"ref_{number:04d}",
        "kind": "place",
        "place_kind": kind,
        "noun": noun,
        "name": name,
        "said_by": npc_id,
        "settlement_id": settlement,
        "turn": turn,
        "quotes": [quote[:240]],
        "claims": list(claims),
        "status": "resolved" if known else "rumor",
        "location_id": known,
    }
    refs.append(ref)
    return ref


def _destination(world, folded_texts, npc_id, turn, settlement):
    """Where a commitment points: a named reference, else a place noun."""
    state = ensure(world)
    for text in folded_texts:
        for ref in reversed(state["references"]):
            if ref.get("name") and fold(ref["name"]) in text:
                return {"ref_id": ref["id"], "place_kind": ref["place_kind"], "noun": ref.get("noun")}
        for word in text.split():
            hit = place_kind_of(word)
            if hit:
                noun, kind = hit
                known = [
                    lid for lid, loc in world.get("locations", {}).items()
                    if isinstance(loc, dict) and loc.get("parent_location_id") == settlement
                    and (loc.get("scene_kind") == kind or loc.get("place_kind") == kind)
                ]
                return {
                    "place_kind": kind, "noun": noun,
                    "location_id": known[0] if len(known) == 1 else None,
                }
    return None


def _objects(folded: str, *, drop: tuple[re.Pattern[str], ...] = ()) -> list[str]:
    words = []
    for word in folded.split():
        if word in _STOP or len(word) < 3:
            continue
        if any(p.fullmatch(word) or p.search(word) for p in drop):
            continue
        words.append(word)
    return words


def record(world: dict[str, Any], npc: dict[str, Any], player_text: str, shown_text: str,
           *, turn: int | None) -> dict[str, Any] | None:
    """Keep one NPC statement the player saw, with what it names and commits to."""
    if not isinstance(npc, dict) or not isinstance(npc.get("id"), str):
        return None
    words = _spoken_words(npc, shown_text)
    if not words:
        return None
    state = ensure(world)
    npc_id = npc["id"]
    turn = turn if type(turn) is int else int(world.get("flags", {}).get("turn_index", 0) or 0)
    statements = state["statements"].setdefault(npc_id, [])
    if statements and statements[-1].get("text") == words and statements[-1].get("player") == player_text:
        return statements[-1]
    folded = fold(words)
    folded_player = fold(player_text)
    settlement = _settlement(world)
    entry = {"turn": turn, "player": str(player_text or "")[:240], "text": words[:400],
             "reference_ids": [], "commitment_ids": []}
    # A stock refusal or confusion line names nothing and promises nothing.
    stock = bool(re.search(r"\b(?:anlayamadim|anlamadim|animsamiyorum|karistirmis|soylemedim)\b", folded))
    if not stock:
        asked_name = bool(re.search(r"\b(?:ismi|adi|ismini|adini)\b", folded_player))
        for display, noun, kind in _named_places(words):
            claims = [adj for adj in _ADJECTIVES if re.search(rf"\b{adj}\b", folded)]
            ref = _add_reference(world, state, npc_id=npc_id, name=display, noun=noun, kind=kind,
                                 claims=claims, quote=words, turn=turn, settlement=settlement)
            if ref:
                entry["reference_ids"].append(ref["id"])
        if not entry["reference_ids"] and not asked_name:
            unnamed = _unnamed_place(folded)
            if unnamed:
                noun, kind, claims = unnamed
                ref = _add_reference(world, state, npc_id=npc_id, name=None, noun=noun, kind=kind,
                                     claims=claims, quote=words, turn=turn, settlement=settlement)
                if ref:
                    entry["reference_ids"].append(ref["id"])
        for kind, commitment_text in _commitments(folded, folded_player):
            number = state["next_commitment"]
            state["next_commitment"] = number + 1
            commitment = {
                "id": f"commit_{number:04d}",
                "npc_id": npc_id,
                "kind": kind,
                "objects": _objects(folded_player if commitment_text == "request" else folded,
                                    drop=(*[p for _, p in _REQUEST_PATTERNS], *[p for _, p in _COMMIT_PATTERNS])),
                "destination": _destination(world, [folded, folded_player], npc_id, turn, settlement)
                if kind in {"escort", "show", "meet"} else None,
                "quote": words[:240],
                "player": str(player_text or "")[:240],
                "turn": turn,
                "status": "open",
            }
            state["commitments"].append(commitment)
            entry["commitment_ids"].append(commitment["id"])
    statements.append(entry)
    del statements[:-KEEP_PER_NPC]
    return entry


def _commitments(folded: str, folded_player: str) -> list[tuple[str, str]]:
    if _REFUSAL.search(folded):
        return []
    found = []
    for kind, pattern in _COMMIT_PATTERNS:
        if pattern.search(folded):
            found.append((kind, "own"))
    if not found and _AGREE.search(folded):
        for kind, pattern in _REQUEST_PATTERNS:
            if pattern.search(folded_player):
                found.append((kind, "request"))
                break
    # One line commits to one thing of a kind.
    seen, unique = set(), []
    for kind, origin in found:
        if kind not in seen:
            seen.add(kind)
            unique.append((kind, origin))
    return unique


def open_commitments(world: dict[str, Any], *, npc_id: str | None = None,
                     kind: str | None = None) -> list[dict[str, Any]]:
    return [
        c for c in view(world)["commitments"]
        if c.get("status") == "open"
        and (npc_id is None or c.get("npc_id") == npc_id)
        and (kind is None or c.get("kind") == kind)
    ]


def _stem_match(a: str, b: str) -> bool:
    if len(a) < 3 or len(b) < 3:
        return a == b
    short, long_ = sorted((a, b), key=len)
    return long_.startswith(short[: max(3, min(len(short), 5))])


def claim_support(world: dict[str, Any], npc: dict[str, Any] | None, claim: str) -> dict[str, Any]:
    """Is a 'you told me / you promised' claim backed by this NPC's own words?

    status: supported (with the NPC's real quote), unsupported, or absent (no
    statement of this NPC was ever recorded: an older save; callers then keep
    their own stricter check).
    """
    if not isinstance(npc, dict):
        return {"status": "absent"}
    state = view(world)
    statements = state["statements"].get(npc.get("id"), [])
    commitments = [c for c in state["commitments"] if c.get("npc_id") == npc.get("id")]
    if not statements and not commitments:
        return {"status": "absent"}
    folded = fold(claim)
    if re.search(r"\b(?:soylemistim|demistim|anlattim|anlatmistim|bahsetmistim|soyledim|dedim|bahsettim)\b", folded):
        return {"status": "absent"}  # a claim about the player's own words: memory owns it
    claim_kind = next((kind for kind, pattern in _CLAIM_PATTERNS if pattern.search(folded)), None)
    drop = tuple(p for _, p in _CLAIM_PATTERNS) + (_SAID_CLAIM,)
    objects = [
        word for word in _objects(folded, drop=drop)
        if not re.search(r"(?:ecegini|acagini|ecektin|acaktin|mistin|mistin|din)$", word)
    ]
    names = {fold(npc.get("name", ""))} | {fold(living_world.public_npc_name(npc))}
    objects = [w for w in objects if not any(w.startswith(n) for n in names if n)]
    if claim_kind is not None:
        for commitment in reversed(commitments):
            if commitment.get("kind") != claim_kind:
                continue
            haystack = list(commitment.get("objects") or [])
            destination = commitment.get("destination") or {}
            for key in ("noun", "place_kind"):
                if destination.get(key):
                    haystack.append(fold(destination[key]))
            if destination.get("ref_id"):
                ref = next((r for r in state["references"] if r["id"] == destination["ref_id"]), None)
                if ref and ref.get("name"):
                    haystack.append(fold(ref["name"]))
            nouns = [w for w in objects if place_kind_of(w) or not re.search(r"(?:mek|mak)$", w)]
            if not nouns or all(any(_stem_match(w, h) for h in haystack) for w in nouns):
                return {"status": "supported", "quote": commitment["quote"], "commitment": commitment}
        return {"status": "unsupported", "claim_kind": claim_kind, "objects": objects}
    if _SAID_CLAIM.search(folded) and objects:
        for statement in reversed(statements):
            text_words = fold(statement.get("text", "")).split()
            if all(any(_stem_match(w, t) for t in text_words) for w in objects):
                return {"status": "supported", "quote": statement["text"], "statement": statement}
        return {"status": "unsupported", "claim_kind": "said", "objects": objects}
    return {"status": "unsupported", "claim_kind": None, "objects": objects}


def resolve_reference(world: dict[str, Any], ref_id: str, location_id: str) -> None:
    for ref in ensure(world)["references"]:
        if ref.get("id") == ref_id:
            ref["location_id"] = location_id
            ref["status"] = "resolved"


def fulfil(world: dict[str, Any], commitment_id: str, how: str) -> None:
    for commitment in ensure(world)["commitments"]:
        if commitment.get("id") == commitment_id:
            commitment["status"] = "fulfilled"
            commitment["fulfilled_by"] = how


def legacy_entry_supports(entry_text: str, claim: str) -> bool:
    """Older saves (no ledger): a memory line supports a claim only if it shares its subject.

    The P6 run answered "Evet, bunu söylemiştim: <a greeting>" because one
    common word overlapped. The claimed object (what was promised or said)
    must appear in the NPC's own line.
    """
    folded = fold(claim)
    drop = tuple(p for _, p in _CLAIM_PATTERNS) + (_SAID_CLAIM,)
    objects = [w for w in _objects(folded, drop=drop)
               if not re.search(r"(?:ecegini|acagini|ecektin|acaktin|mistin|din)$", w)]
    if not objects:
        return False
    words = fold(entry_text).split()
    return any(any(_stem_match(o, w) for w in words) for o in objects)

"""Understand a local action once, bind it to a real target, let its owner resolve it.

LR00 fix after the owner's P6 rejection (18 Oct 2026). Before this module every
layer re-read the raw sentence with its own word list: "Garrick Hanına
yaklaşıyorum" became a person search ("Kime yaklaşmak istedin?"), "Garrick Hanı"
answered "Bulunduğun yer: Garrick Hanı" while the save still said Neverwinter,
and "kilidi açmaya çalışıyorum" fell between two door checks into an empty
"resolved".

Here a turn is read ONCE into ordered steps (verb, target, negation, condition,
dependency). Targets are bound against what really exists around the player:
people, doors, places, features, and places an NPC only talked about (those are
attributed references, see npc_statements). The bound step goes to the owner
that can actually do it: movement, door, skill check, a new local detail. Each
step reports what happened (completed / blocked with a reason / not attempted
because an earlier step failed / condition not met). Nothing is reported as
done unless it was done, and the narration is built from those receipts.

Nothing here is specific to one campaign: words are generic Turkish verbs and
nouns, targets come from the saved world. When the words alone do not bind a
target, one bounded model call may choose among the listed candidate IDs; it
can never invent an ID or a state change.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from typing import Any

import living_world
import npc_statements

KEY = "grounded_actions"
SCHEMA_VERSION = 1


def fold(text: Any) -> str:
    return living_world.normalize_text(text)


# ---------------------------------------------------------------------------
# Words. Each verb stem must be followed by a real verb ending, so nouns that
# share a stem (açık, giriş, kırmızı, araba) are not read as verbs.
# ---------------------------------------------------------------------------
_VERB_TAIL = re.compile(
    r"(?:"
    r"(?:abil|ebil|ama|eme)?(?:i|u|a|e|y)?yor\w*"
    r"|(?:y)?(?:acak|ecek|acag|eceg)\w*"
    r"|(?:i|u|a|e)?r(?:im|um|sin|sun|iz|uz|siniz|sunuz|lar|ler|ken|sa|se)?"
    r"|(?:d|t)(?:i|u)\w*"
    r"|m(?:i|u)s\w*"
    r"|m(?:a|e)\w*"
    r"|(?:i|u)?p"
    r"|(?:y)?(?:arak|erek)"
    r"|(?:y)?(?:ince|inca|unca|ince)"
    r"|(?:y)?(?:elim|alim|eyim|ayim)"
    r"|(?:i|u)?n(?:iz|uz)?"
    r"|(?:a|e)?bil\w*"
    r"|meli\w*|mali\w*"
    r"|s(?:a|e)\w*"
    r")"
)
_NEGATIVE_TAIL = re.compile(
    r"^(?:abil|ebil|ama|eme)?(?:m[aeiu](?:z|m$|yacag|yeceg|yacak|yecek|di|dan|den|mis|sin|yin|yalim|yelim|sa|se|yiz)"
    r"|m[iu]yor)"
)
_INFINITIVE_TAIL = re.compile(r"^(?:mak|mek|maya|meye|mayi|meyi|masi|mesi)$")
_ATTEMPT_WORD = re.compile(r"^(?:calis|dene|deni|ugras|kalk|ist|niyet|karar|ugra)\w*")
_NEGATED_HELPER = re.compile(r"^(?:istemiyor\w*|istemem|calismiyor\w*|kalkmiyor\w*|denemiyor\w*|niyetim\s*yok|degil\w*|yok|falan|filan)$")

# (canonical verb, stem regex). Order matters only for ties.
VERBS: tuple[tuple[str, str], ...] = (
    ("approach", r"(?:yaklas|sokul|yanas)"),
    ("enter", r"(?:gir|dal|suzul)"),
    ("leave", r"(?:cik(?!ar)|ayril|terket|terk)"),
    ("search", r"(?:ara(?!b|c|l|s)|ari(?=yor|yac|ya)|bul(?=mak|maya|mayi|urum|ur$|abil|acag|ayim|mam|up|dum)|kolacan|arastir|tara(?=yor|ma|rim))"),
    ("wander", r"(?:dolas|dolan|gez(?!dir))"),
    ("go", r"(?:git|gid|yonel|ugra|ilerl|yuru|var(?=i|a|d|m|ip)|don(?=u|e|d|m)|gec(?=iyor|ip|ecek|eceg)|sap(?=iyor|ip|acag))"),
    ("listen", r"(?:dinle)"),
    ("inspect", r"(?:incel|bak|kontrol|muayene|gozle|goz\s*gezdir|goz\s*at|dikkat)"),
    ("knock", r"(?:vur(?!ul)|cal(?!is|g)|tiklat|tikirdat|yumrukla)"),
    ("call_out", r"(?:seslen|bagir|cagir|haykir)"),
    ("unlock", r"(?:maymuncukla|kurcala)"),
    ("climb", r"(?:tirman)"),
    # Pushing a door ("itip açmaya çalışıyorum") is trying to open it, not forcing it.
    ("open", r"(?:ac(?!ik|il)|kaldir|cevir|bastir|it(?=iyor|ip|erek|mek|meye|eyim|er))"),
    ("force", r"(?:zorla|kir(?!m?iz|li|ik)|omuzla|tekmele|parcala|yik(?=iyor|ip|mak|maya))"),
    ("close", r"(?:kapat|kapa(?=yor|r|di|mak|maya))"),
    ("read", r"(?:oku(?!l))"),
    ("touch", r"(?:dokun|yokla|elle|cek(?=iyor|ip|mek|meye|erek))"),
    ("wait", r"(?:bekle)"),
    ("talk", r"(?:konus|sor(?!un)|selam|soyle|anlat|tesekkur|rica|sohbet)"),
    ("hide", r"(?:saklan|gizlen|siper)"),
    ("follow", r"(?:takip|izle)"),
    ("take", r"(?:al(?=iyor|ip|mak|maya|irim|acag|dim))"),
    ("sit", r"(?:otur)"),
    ("attack", r"(?:saldir|bicakla|vurus)"),
)
_VERB_RES = tuple((verb, re.compile(r"^" + stem)) for verb, stem in VERBS)
# Two-word verbs: "göz atıyorum", "kulak veriyorum", "dikkat ediyorum".
_LIGHT = {"goz": "inspect", "kulak": "listen", "dikkat": "inspect", "kontrol": "inspect",
          "eslik": "follow", "yardim": "talk", "selam": "talk", "tekme": "force", "omuz": "force"}
_LIGHT_VERB = re.compile(r"^(?:at|ver|ed|et|gezdir)\w*")

DEFER_VERBS = frozenset({"talk", "hide", "follow", "take", "sit", "attack", "wait"})
TARGET_VERBS = frozenset({"approach", "go", "enter", "knock", "open", "unlock", "force", "close", "read", "touch"})

_DOOR_NOUNS = ("kapi", "giris", "esik")
_LOCK_PARTS = {"kilit": "lock", "kilid": "lock", "mandal": "latch", "tokmak": "knocker", "tokmag": "knocker",
               "kol": "handle", "kulp": "handle", "sap": "handle", "mentese": "hinge",
               "anahtar delig": "lock", "surgu": "bolt"}
_PRONOUNS = ("onu", "ona", "orada", "oraya", "orayi", "suna", "sunu", "buna", "bunu", "oradaki", "icine")
_RELATIONAL = {"altina", "altinda", "onune", "onunde", "yanina", "yaninda", "arkasina", "arkasinda",
               "ustune", "ustunde", "dibine", "dibinde", "basina", "basinda"}
_SAID_BY = re.compile(r"\b(?:soyledig|bahsettig|dedig|onerdig|anlattig|gosterdig|tarif ettig)\w*")
_QUESTION_WORDS = frozenset({"ne", "neler", "nerede", "nereye", "nereden", "nasil", "neden", "niye", "nicin",
                             "kim", "kimi", "kime", "hangi", "hangisi", "kac"})
_QUESTION_PARTICLE = re.compile(r"^(?:mi|mu|misin|musun|miyim|muyum|miyiz|muyuz|midir|mudur|mi\w{0,3})$")
_REPORTED = re.compile(r"\b(?:dedi|soyledi|istedi|onerdi|emretti|diyor|soyluyor|istiyor\s+benden)\b")
_CONDITION_WORD = re.compile(
    r"^(?:eger|sayet|\w+(?:rsa|rse|ysa|yse|osa|ose|mazsa|mezse|degilse|dise|disa)|aciksa|kapaliysa|kilitliyse|varsa|yoksa)$"
)
_IMPLICIT_GO = re.compile(r"^(?:gidelim|gidiyoruz|yuruyelim|haydi|hadi)$")


def _verb_of(token: str, following: str = "") -> tuple[str, bool, bool] | None:
    """(verb, negated, infinitive) when a folded token is a verb form."""
    if token in _LIGHT and _LIGHT_VERB.match(following or ""):
        tail = following[2:] if following.startswith(("at", "ed", "et")) else following
        return _LIGHT[token], bool(_NEGATIVE_TAIL.match(tail)), False
    for verb, pattern in _VERB_RES:
        match = pattern.match(token)
        if not match:
            continue
        tail = token[match.end():]
        if tail and not _VERB_TAIL.fullmatch(tail):
            continue
        if not tail and len(token) < 4:
            continue
        return verb, bool(_NEGATIVE_TAIL.match(tail)), bool(_INFINITIVE_TAIL.match(tail))
    return None


# ---------------------------------------------------------------------------
# Clauses
# ---------------------------------------------------------------------------
_QUOTE_RE = re.compile(r"[“\"«]([^”\"»]{1,400})[”\"»]")


def split_clauses(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Ordered clauses of one turn and any quoted speech, both from the raw text."""
    speech = [m.group(1) for m in _QUOTE_RE.finditer(text)]
    plain = _QUOTE_RE.sub(" ", text)
    clauses = []
    for sentence_match in re.finditer(r"[^.!?;]+[.!?;]*", plain):
        sentence = sentence_match.group(0)
        asked = sentence.strip().endswith("?")
        parts = re.split(r",|\b(?:ve\s+sonra|daha\s+sonra|ondan\s+sonra|sonra\s+da|sonra|ardından|ve|ama|fakat)\b",
                         sentence, flags=re.IGNORECASE)
        for part in parts:
            if not part or not part.strip(" .!?;"):
                continue
            tokens = fold(part).split()
            # A converb (-ip, -ince) closes its own clause: "gidip | kapıyı çalıyorum".
            current: list[str] = []
            for index, token in enumerate(tokens):
                current.append(token)
                verb = _verb_of(token, tokens[index + 1] if index + 1 < len(tokens) else "")
                if verb and re.search(r"(?:ip|up|ince|inca|unca|yip|yup)$", token) and index + 1 < len(tokens):
                    clauses.append({"tokens": current, "asked": False})
                    current = []
            if current:
                clauses.append({"tokens": current, "asked": asked})
    # A part with no verb belongs to its neighbour ("fıçılar ve sandıklar" + "arkasına bakıyorum").
    merged: list[dict[str, Any]] = []
    carry: list[str] = []
    for clause in clauses:
        tokens = carry + clause["tokens"]
        if not any(_verb_of(t, tokens[i + 1] if i + 1 < len(tokens) else "") for i, t in enumerate(tokens)):
            if merged and any(_CONDITION_WORD.match(t) for t in tokens):
                # "..., açan olursa (soracağım)": a condition for something not
                # yet done stays its own clause; merged into the previous one it
                # would make the knock itself conditional.
                carry = []
                merged.append({"tokens": tokens, "asked": clause["asked"]})
                continue
            carry = tokens
            continue
        carry = []
        merged.append({"tokens": tokens, "asked": clause["asked"]})
    if carry:
        if merged:
            merged[-1]["tokens"].extend(carry)
        else:
            merged.append({"tokens": carry, "asked": any(c["asked"] for c in clauses)})
    return merged, speech


def _read_clause(clause: dict[str, Any]) -> dict[str, Any]:
    tokens = clause["tokens"]
    found = []
    for index, token in enumerate(tokens):
        verb = _verb_of(token, tokens[index + 1] if index + 1 < len(tokens) else "")
        if verb:
            found.append((index, *verb))
    info: dict[str, Any] = {
        "tokens": tokens, "verb": None, "negated": False, "attempt": False, "question": False,
        "conditional": False, "condition_tokens": None, "reported": False, "purpose": None,
        "verb_index": None, "manner_negated": [],
    }
    text = " ".join(tokens)
    embedded = "diye" in tokens
    info["question"] = bool(clause.get("asked")) and not embedded or (
        not embedded and any(_QUESTION_PARTICLE.match(t) for t in tokens)
        or (not embedded and tokens and tokens[0] in _QUESTION_WORDS)
    )
    info["reported"] = bool(_REPORTED.search(text))
    # Condition: "kilit açılırsa | içeri bakarım", "eğer açıksa | girerim".
    for index, token in enumerate(tokens):
        if _CONDITION_WORD.match(token) and index + 1 < len(tokens):
            if token in {"eger", "sayet"}:
                end = next((j for j in range(index + 1, len(tokens)) if _CONDITION_WORD.match(tokens[j])), None)
                if end is None:
                    continue
            else:
                end = index
            info["conditional"] = True
            info["condition_tokens"] = tokens[: end + 1]
            found = [f for f in found if f[0] > end]
            break
    if not found:
        return info
    # Purpose: "Kızılhanı bulmak için tabelalara bakıyorum" -> goal search(Kızılhan).
    if "icin" in tokens:
        for position, verb, negated, infinitive in found:
            if infinitive and position + 1 < len(tokens) and tokens[position + 1] == "icin":
                info["purpose"] = {"verb": verb, "tokens": tokens[:position]}
                found = [f for f in found if f[0] > position + 1] or found
                break
    # Manner converbs before the main verb: "zorlamadan", "iterek".
    for position, verb, negated, infinitive in found[:-1]:
        if re.search(r"(?:madan|meden)$", tokens[position]):
            info["manner_negated"].append(verb)
    # "dolanırken" (while), "zorlamadan" (without), "iterek" (by) qualify the act; they are not it.
    actions = [f for f in found if not re.search(r"(?:madan|meden|arak|erek|ken)$", tokens[f[0]])]
    if not actions:
        return info
    position, verb, negated, infinitive = actions[-1]
    # "açmaya çalışıyorum", "açmayı denemiyorum", "girmek istiyorum": the
    # infinitive names the act, the helper verb only says try / want / not.
    helper = tokens[position + 1] if position + 1 < len(tokens) else ""
    if infinitive and helper:
        info["attempt"] = bool(_ATTEMPT_WORD.match(helper))
        negated = negated or bool(_NEGATED_HELPER.match(helper)) or bool(
            _ATTEMPT_WORD.match(helper) and re.search(r"m[iu]yor|mem$|mam$|me(?:y|z)|ma(?:y|z)", helper[3:]))
    elif helper and _NEGATED_HELPER.match(helper):
        negated = True
    # "kapıyı açmaya kalkmıyorum": the helper is the finite verb and was read as one.
    finite_index = position
    if len(actions) >= 2 and actions[-2][3] and actions[-2][0] == position - 1:
        p2, v2, n2, _ = actions[-2]
        info["attempt"] = True
        negated = n2 or negated
        position, verb = p2, v2
    # Not a present act: "kırmayı denedim" (past), "hedefim ... araştırmak"
    # (a bare infinitive), "... araştırıyorum demiyorum" (words about words).
    last_word = tokens[-1] if tokens else ""
    finite_word = last_word if finite_index < len(tokens) - 1 and infinitive else tokens[finite_index]
    stem = next((m.end() for _, p in _VERB_RES if (m := p.match(finite_word))), 0)
    finite_tail = finite_word[stem:] if stem else finite_word[-6:]
    info["not_now"] = bool(
        re.search(r"(?:(?:d|t)(?:i|u)(?:m|n|k|niz|nuz|ler|lar)?|m(?:i|u)st(?:i|u)(?:m|n|k)?)$", finite_tail)
        and not re.search(r"(?:yor|acak|ecek|acag|eceg)", finite_tail)
        or (infinitive and position == len(tokens) - 1)
        or bool(re.match(r"^(?:demiyor|demedim|diyorum|dedim|demem|dememis)", last_word))
    )
    info.update(verb=verb, negated=negated, verb_index=position)
    return info


# ---------------------------------------------------------------------------
# Candidates: everything the player could mean, from the saved world.
# ---------------------------------------------------------------------------
_PERSON_NOUNS = ("kisi", "adam", "kadin", "yabanci", "genc", "yasli", "cocuk")
_OUTSIDE_NOUNS = ("disari", "sokak", "cadde", "meydan")


def _soften(token: str) -> str:
    return token[:-1] + {"t": "d", "p": "b", "k": "g", "c": "c"}.get(token[-1], token[-1]) if token else token


def _levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def token_matches(name_token: str, text_token: str) -> bool:
    """A saved name word inside a typed word, with case endings and small typos."""
    if not name_token or not text_token:
        return False
    variants = {name_token, _soften(name_token)}
    if len(name_token) >= 5 and name_token[-1] in "iu":
        variants.add(name_token[:-1])  # "Garrick Hanı" typed "garrick han" (not "kapı" -> "kapağı")
    if name_token.endswith(("si", "su")) and len(name_token) > 4:
        variants.add(name_token[:-2])  # "Hanı Kapısı" typed "kapı"
    for variant in variants:
        if len(variant) < 3:
            continue
        if text_token.startswith(variant) and len(text_token) - len(variant) <= 7:
            return True
    if len(name_token) >= 5:
        for size in (len(name_token) - 1, len(name_token), len(name_token) + 1):
            if size <= len(text_token) and _levenshtein(name_token, text_token[:size]) <= 1:
                return True
    return False


def _phrase_at(name_words: list[str], tokens: list[str]) -> int | None:
    if not name_words or len(tokens) < len(name_words):
        return None
    for start in range(len(tokens) - len(name_words) + 1):
        if all(token_matches(w, tokens[start + i]) for i, w in enumerate(name_words)):
            return start
    return None


def _settlement(world: dict[str, Any]) -> str | None:
    return npc_statements._settlement(world)


def candidates(session) -> list[dict[str, Any]]:
    import game
    import exploration

    world = session.world_state
    here = world.get("location")
    settlement = _settlement(world)
    locations = world.get("locations", {}) if isinstance(world.get("locations"), dict) else {}
    found: list[dict[str, Any]] = []
    for npc in game.active_npcs(here):
        if not isinstance(npc, dict) or not isinstance(npc.get("id"), str):
            continue
        names = []
        if living_world.npc_name_known_to_player(npc) and npc.get("name"):
            names.append(fold(npc["name"]))
        nouns = list(_PERSON_NOUNS)
        if living_world.npc_role_known_to_player(npc) and npc.get("role"):
            nouns.extend(fold(npc["role"]).split()[:2])
        nouns.extend(w for w in fold(living_world.public_npc_descriptor(npc)).split() if len(w) > 3)
        found.append({"id": npc["id"], "kind": "npc", "names": names, "nouns": nouns,
                      "label": living_world.public_npc_name(npc), "record": npc})
    for door in exploration.visible_doors(world):
        if not isinstance(door, dict) or door.get("location") != here or door.get("hidden"):
            continue
        place_id = door["id"].split(":", 1)[1] if str(door.get("id", "")).startswith("venue-door:") else None
        found.append({"id": door["id"], "kind": "door", "names": [fold(door.get("name", ""))],
                      "nouns": list(_DOOR_NOUNS), "label": door.get("name", "Kapı"),
                      "record": door, "place_id": place_id})
    for location_id, location in locations.items():
        if not isinstance(location, dict) or location_id == here:
            continue
        parent = location.get("parent_location_id")
        if parent not in {here, settlement} or location.get("hidden"):
            continue
        names = [fold(location.get("name", ""))]
        nouns = []
        for alias in location.get("aliases", []) or []:
            folded = fold(alias)
            if not folded or folded == names[0]:
                continue
            (nouns if " " not in folded else names).append(folded)
        kind = location.get("place_kind") or location.get("scene_kind")
        for noun, noun_kind in npc_statements.PLACE_NOUNS:
            if noun_kind == kind and noun not in nouns:
                nouns.append(noun)
        found.append({"id": location_id, "kind": "place", "names": names, "nouns": nouns,
                      "label": location.get("name", location_id), "record": location,
                      "place_kind": kind, "door_id": f"venue-door:{location_id}"
                      if any(d.get("id") == f"venue-door:{location_id}" for d in world.get("doors", [])
                             if isinstance(d, dict)) else None})
    if isinstance(here, str) and isinstance(locations.get(here), dict) and here != settlement:
        record = locations[here]
        here_nouns = [fold(a) for a in record.get("aliases", []) or [] if fold(a) and " " not in fold(a)]
        found.append({"id": here, "kind": "here", "names": [fold(record.get("name", ""))],
                      "nouns": here_nouns, "label": record.get("name", here), "record": record})
    if isinstance(here, str) and isinstance(locations.get(here), dict):
        record = locations[here]
        parent = record.get("parent_location_id") or record.get("exit_location_id")
        if parent in locations and here != settlement:
            found.append({"id": parent, "kind": "outside", "names": [fold(locations[parent].get("name", ""))],
                          "nouns": list(_OUTSIDE_NOUNS), "label": locations[parent].get("name", parent),
                          "record": locations[parent]})
    for feature in world.get("features", []):
        if not isinstance(feature, dict) or feature.get("location") != here or feature.get("hidden"):
            continue
        names = [fold(feature.get("name", ""))]
        nouns = [fold(a) for a in feature.get("aliases", []) or [] if fold(a)]
        found.append({"id": feature["id"], "kind": "feature", "names": names, "nouns": nouns,
                      "label": feature.get("name", "ayrıntı"), "record": feature})
    for ref in npc_statements.place_references(world, settlement_id=settlement):
        if ref.get("location_id"):
            continue  # a followed reference is now its place
        found.append({"id": ref["id"], "kind": "reference", "names": [fold(ref["name"])] if ref.get("name") else [],
                      "nouns": [ref.get("noun")] if ref.get("noun") else [],
                      "label": ref.get("name") or f"{ref.get('noun', 'yer')} (söylenen)",
                      "record": ref, "place_kind": ref.get("place_kind")})
    return found


def _noun_hit(noun: str, tokens: list[str]) -> bool:
    if not noun:
        return False
    words = noun.split()
    if len(words) > 1:
        return _phrase_at(words, tokens) is not None
    hit = npc_statements.place_kind_of
    for token in tokens:
        if token == noun:
            return True
        if token.startswith(noun):
            tail = token[len(noun):]
            if npc_statements._CASE_TAIL.match(tail) or re.fullmatch(r"(?:n|s|y)?(?:i|u|a|e)(?:n|na|ni|nda|ndan|nin)?|lar\w*|ler\w*", tail):
                return True
        if len(noun) >= 4 and token_matches(noun, token) and hit(token) is None and len(token) <= len(noun) + 5:
            return True
    return False


def bind(clause_tokens: list[str], cands: list[dict[str, Any]], *, world: dict[str, Any],
         verb: str | None) -> dict[str, Any]:
    """Pick the entity a clause is about. Returns {'target', 'part', 'score', 'ambiguous'}."""
    flags = world.get("flags", {}) if isinstance(world.get("flags"), dict) else {}
    memory = world.get(KEY) if isinstance(world.get(KEY), dict) else {}
    near = memory.get("near_target_id")
    last = memory.get("last_target_id")
    scored: list[tuple[int, dict[str, Any]]] = []
    text = " ".join(clause_tokens)
    other = "baska" in clause_tokens or "diger" in clause_tokens or "farkli" in clause_tokens
    said_by_npc = None
    if _SAID_BY.search(text):
        for cand in cands:
            if cand["kind"] == "npc" and (
                any(_phrase_at(n.split(), clause_tokens) is not None for n in cand["names"] if n)
                or any(_noun_hit(n, clause_tokens) for n in cand["nouns"][len(_PERSON_NOUNS):])
            ):
                said_by_npc = cand["id"]
    part = None
    for token in clause_tokens:
        for word, name in _LOCK_PARTS.items():
            if token.startswith(word):
                part = name
    for cand in cands:
        score = 0
        for name in cand["names"]:
            words = name.split()
            if words and _phrase_at(words, clause_tokens) is not None:
                score = max(score, 100 + 10 * len(words))
        if score == 0 and any(_noun_hit(noun, clause_tokens) for noun in cand["nouns"] if noun):
            score = 40
        if score == 0 and cand["kind"] == "door" and part is not None:
            score = 38
        if score == 0:
            continue
        if cand["id"] == near:
            score += 12
        if cand["id"] == last:
            score += 6
        if said_by_npc and cand["kind"] == "reference" and cand["record"].get("said_by") == said_by_npc:
            score += 80
        if said_by_npc and cand["kind"] == "npc" and cand["id"] == said_by_npc:
            score -= 60  # the speaker is the source, not the target
        if other and cand["kind"] == "place" and score < 100:
            score -= 70
        if other and cand["kind"] == "reference":
            score += 20
        # Hands-on verbs mean something in reach, not a place someone only mentioned.
        if cand["kind"] == "reference" and score < 100 and verb in {
                "enter", "knock", "open", "unlock", "force", "close", "approach", "inspect", "read", "touch", "listen"}:
            score -= 15
        scored.append((score, cand))
    if not scored and any(t in _PRONOUNS for t in clause_tokens):
        for cand in cands:
            if cand["id"] in (last, near):
                scored.append((30, cand))
    if not scored:
        return {"target": None, "part": part, "score": 0, "ambiguous": []}
    scored.sort(key=lambda item: -item[0])
    best_score, best = scored[0]
    if best_score <= 0:
        return {"target": None, "part": part, "score": 0, "ambiguous": [], "excluded": [c for _, c in scored]}
    # A door and the place it belongs to are one target seen from two sides.
    tied = [c for s, c in scored if s >= best_score - 4 and c is not best]
    tied = [c for c in tied if not _same_site(c, best)]
    if tied and best_score < 100:
        return {"target": None, "part": part, "score": best_score, "ambiguous": [best, *tied]}
    best = _prefer_side(best, scored, verb, part, cands)
    return {"target": best, "part": part, "score": best_score, "ambiguous": []}


def _same_site(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ids = {a.get("id"), a.get("place_id"), a.get("door_id")}
    return bool(ids & {b.get("id"), b.get("place_id"), b.get("door_id")} - {None})


def _prefer_side(best, scored, verb, part, cands):
    """Door verbs act on the place's door; movement verbs on the place."""
    door_verbs = {"knock", "open", "unlock", "force", "close"}
    if best["kind"] == "place" and (verb in door_verbs or part) and best.get("door_id"):
        door = next((c for c in cands if c["id"] == best["door_id"]), None)
        if door:
            return door
    if best["kind"] == "door" and verb in {"go", "enter", "approach"} and best.get("place_id") and not part:
        place = next((c for c in cands if c["id"] == best["place_id"]), None)
        if place and verb in {"go", "enter"}:
            return place
    return best


# ---------------------------------------------------------------------------
# Small local details a player can look for. Generic Turkish nouns; whether a
# detail exists at a given building is decided once by Python and saved.
# "access" details can change what the player can do, so their existence is
# seeded and, when searched for, gated by a check; "flavor" details cannot.
# ---------------------------------------------------------------------------
DETAILS: dict[str, dict[str, Any]] = {
    "pencere": {"class": "access", "name": "Pencere", "chance": 90, "states": ("kepenkli", "parmaklıklı", "aralık")},
    "arka kapi": {"class": "access", "name": "Arka kapı", "chance": 55, "states": ("kilitli", "sürgülü", "aralık")},
    "arka giris": {"class": "access", "name": "Arka kapı", "chance": 55, "states": ("kilitli", "sürgülü", "aralık")},
    "avlu": {"class": "access", "name": "Avlu kapısı", "chance": 45, "states": ("kilitli", "kapalı", "aralık")},
    "bodrum": {"class": "access", "name": "Bodrum kapağı", "chance": 35, "states": ("kilitli", "kapalı", "aralık")},
    "merdiven": {"class": "access", "name": "Dış merdiven", "chance": 30, "states": ("çürük", "sağlam", "sağlam")},
    "cati": {"class": "access", "name": "Çatı", "chance": 60, "states": ("yüksek", "kaygan", "ulaşılabilir")},
    "tabela": {"class": "flavor", "name": "Tabela", "descriptions": (
        "Rüzgârda hafifçe gıcırdayan, boyası solmuş bir tabela.",
        "Zincirle asılmış, harfleri oyulmuş ahşap bir tabela.")},
    "fener": {"class": "flavor", "name": "Fener", "descriptions": (
        "İsli camlı, demir bir fener; fitili kısılmış.", "Duvara çakılı paslı bir fener askısı.")},
    "fici": {"class": "flavor", "name": "Fıçılar", "descriptions": (
        "Duvar dibine dizilmiş birkaç boş fıçı; birinin kapağı yerinden oynamış.",
        "Üst üste konmuş, çemberleri paslı fıçılar.")},
    "sandik": {"class": "flavor", "name": "Sandıklar", "descriptions": (
        "Ağzı çivilenmiş, üstüne tebeşirle işaret konmuş iki sandık.",
        "Islanıp kabarmış tahtadan eski bir sandık.")},
    "kuyu": {"class": "flavor", "name": "Kuyu", "descriptions": (
        "Taş bilezikli bir kuyu; makarasındaki ip yıpranmış.",
        "Ağzı tahta kapakla örtülü eski bir kuyu.")},
    "cesme": {"class": "flavor", "name": "Çeşme", "descriptions": (
        "Lülesinden ince bir su akan taş bir çeşme; yalağı yosun tutmuş.",
        "Kitabesi silinmiş, mermeri çatlak bir çeşme.")},
    "duvar": {"class": "flavor", "name": "Duvar", "descriptions": (
        "Sıvası yer yer dökülmüş, rutubet lekeli bir duvar.",)},
    "baca": {"class": "flavor", "name": "Baca", "descriptions": ("Ağzından ince bir duman sızan tuğla baca.",)},
    "ara sokak": {"class": "flavor", "name": "Ara sokak", "descriptions": (
        "İki bina arasına sıkışmış, çamurlu ve dar bir ara sokak.",)},
    "arka sokak": {"class": "flavor", "name": "Arka sokak", "descriptions": (
        "Binaların arkasından dolanan, çöp ve kırık kasalarla dolu dar bir sokak.",)},
    "ilan": {"class": "flavor", "name": "İlan panosu", "descriptions": (
        "Üstüne üst üste çivilenmiş, yarısı yırtılmış ilanlarla dolu bir pano.",)},
    "afis": {"class": "flavor", "name": "İlan panosu", "descriptions": (
        "Üstüne üst üste çivilenmiş, yarısı yırtılmış ilanlarla dolu bir pano.",)},
    "heykel": {"class": "flavor", "name": "Heykel", "descriptions": (
        "Yüzü aşınmış, kaidesi yosunlu taş bir heykel.",)},
    "agac": {"class": "flavor", "name": "Ağaç", "descriptions": ("Gövdesi budaklı, yaşlı bir ağaç.",)},
    "bank": {"class": "flavor", "name": "Bank", "descriptions": ("Ayakları paslı, tahtası çatlamış bir bank.",)},
}
# Containers can be opened; what is inside is decided once, saved, and never loot
# (no item is created by opening a crate in the street).
_CONTAINERS = {
    "sandik": ("Kapağını kaldırıyorsun: içinde talaşa sarılmış birkaç boş şişe var.",
               "Kapağını kaldırıyorsun: içi boş, dibinde biraz kuru saman kalmış.",
               "Kapağını kaldırıyorsun: içinde yırtık çuvallar ve paslı çiviler var."),
    "fici": ("Kapağını oynatıp içine bakıyorsun: dibinde ekşimiş bir şarap tortusu kalmış.",
             "Kapağını oynatıp içine bakıyorsun: ağzına kadar yağmur suyuyla dolu.",
             "Kapağını oynatıp içine bakıyorsun: boş, içi küf kokuyor."),
}
_ACCESS_GOAL = re.compile(r"\b(?:baska|diger|alternatif|ikinci|gizli)\s+(?:bir\s+)?(?:giris|yol|kapi)\w*|\barka\s+(?:kapi|giris)\w*")
_ITEM_GOAL = re.compile(r"\b(?:anahtar|para|altin|silah|hazine|esya|ipucu|iz)\w*")


def _detail_in(tokens: list[str]) -> str | None:
    text = " ".join(tokens)
    for key in sorted(DETAILS, key=len, reverse=True):
        words = key.split()
        if len(words) > 1:
            if _phrase_at(words, tokens) is not None:
                return key
        else:
            for t in tokens:
                for stem in {key, _soften(key)}:  # "sandık" -> "sandığa", "sandığın"
                    if len(stem) >= 3 and t.startswith(stem) and (
                            npc_statements._CASE_TAIL.match(t[len(stem):])
                            or re.fullmatch(r"(?:ler|lar)\w*|(?:y|s|n)?(?:i|u|a|e)\w{0,4}", t[len(stem):])):
                        return key
    return None


def _place_noun_in(tokens: list[str]) -> tuple[str, str] | None:
    for token in tokens:
        hit = npc_statements.place_kind_of(token)
        if hit:
            return hit
    return None


def _seed(world: dict[str, Any], *parts: Any) -> int:
    material = "\x00".join([living_world._campaign_seed(world), *[str(p) for p in parts]])
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:4], "big")


def _pick(world, options, *parts):
    return options[_seed(world, *parts) % len(options)]


def note_near(world: dict[str, Any], target_id: str | None) -> None:
    """Record where the player now stands (a door, a detail) for later 'it'/'the door'."""
    state = _memory(world)
    state["near_target_id"] = target_id
    if target_id:
        state["last_target_id"] = target_id


def clear_near(world: dict[str, Any]) -> None:
    """The player changed location: no longer standing at anything (touches only existing state)."""
    state = world.get(KEY)
    if isinstance(state, dict) and state.get("near_target_id") is not None:
        state["near_target_id"] = None


def near_door_id(world: dict[str, Any]) -> str | None:
    state = world.get(KEY) if isinstance(world.get(KEY), dict) else {}
    near = state.get("near_target_id")
    if not isinstance(near, str):
        return None
    return near if near.startswith("venue-door:") or any(
        isinstance(d, dict) and d.get("id") == near for d in world.get("doors", [])) else None


def _memory(world: dict[str, Any]) -> dict[str, Any]:
    state = world.get(KEY)
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        state = {"schema_version": SCHEMA_VERSION, "near_target_id": None, "last_target_id": None,
                 "observations": {}, "details": {}, "searches": {}, "answers": {}}
        world[KEY] = state
    return state


# ---------------------------------------------------------------------------
# Planning: clauses -> steps
# ---------------------------------------------------------------------------
_FIRST_PERSON_ACT = re.compile(r"\b\w+(?:iyorum|uyorum|yorum|acagim|ecegim|irim|urum|arim|erim)\b")


def plan(session, player_input: str) -> dict[str, Any]:
    world = session.world_state
    clauses, speech = split_clauses(player_input)
    cands = candidates(session)
    steps: list[dict[str, Any]] = []
    pending_condition = None
    for clause in clauses:
        info = _read_clause(clause)
        if info["conditional"]:
            pending_condition = info["condition_tokens"]
            if not info["verb"]:
                continue
        if not info["verb"]:
            continue
        verb = info["verb"]
        tokens = info["tokens"]
        object_tokens = [t for i, t in enumerate(tokens) if i != info["verb_index"]]
        if info["condition_tokens"]:
            object_tokens = [t for t in object_tokens if t not in info["condition_tokens"]]
        if verb == "wander" and (info["purpose"] or "diye" in tokens or _place_noun_in(tokens)
                                  or _ACCESS_GOAL.search(" ".join(tokens))):
            verb = "search"
        if verb in {"go"} and any(t in {"iceri", "icine", "iceriye"} for t in tokens):
            verb = "enter"
        if verb in {"leave"} and not any(t in {"disari", "disariya"} or t.endswith(("dan", "den", "tan", "ten")) for t in tokens):
            verb = "leave"
        purpose = info["purpose"]
        goal_tokens = purpose["tokens"] if purpose else object_tokens
        if purpose and purpose["verb"] in {"search", "go", "approach"}:
            verb_for_bind = "search"
        else:
            verb_for_bind = verb
        binding = bind(goal_tokens, cands, world=world, verb=verb_for_bind)
        step = {
            "verb": "search" if purpose and purpose["verb"] in {"search"} else verb,
            "method": verb if purpose else None,
            "negated": info["negated"],
            "attempt": info["attempt"],
            "question": info["question"],
            "reported": info["reported"],
            "condition": pending_condition,
            "manner_negated": info["manner_negated"],
            "tokens": tokens,
            "goal_tokens": goal_tokens,
            "target": binding["target"],
            "named": binding["score"] >= 100,  # bound by its own name, not a generic noun
            "via_pronoun": binding["score"] == 30,  # "oraya", "onu": the last thing in play
            "part": binding["part"],
            "ambiguous": binding["ambiguous"],
            "other": any(t in {"baska", "diger", "farkli"} for t in tokens),
            "detail": _detail_in(goal_tokens),
            "place_noun": _place_noun_in(goal_tokens),
            "not_now": info.get("not_now", False),
        }
        if step["place_noun"]:
            place_kinds = set(step["place_noun"])
            matching_places = [
                candidate for candidate in cands
                if candidate.get("kind") == "place" and candidate.get("place_kind") in place_kinds
            ]
            if len(matching_places) == 1:
                step["target"] = matching_places[0]
        target = step.get("target")
        implicit_followup_door = (target is None and not step["place_noun"]) or (
            isinstance(target, dict)
            and target.get("kind") in {"door", "reference"}
            and not step["named"]
            and not step["place_noun"]
        )
        if steps and verb in {"knock", "open", "unlock", "force", "close"} and implicit_followup_door:
            previous = steps[-1]
            previous_target = previous.get("target")
            if (
                previous.get("verb") in {"go", "approach", "enter"}
                and isinstance(previous_target, dict)
                and previous_target.get("kind") == "place"
                and previous_target.get("door_id")
            ):
                # Bind an implicit follow-up door action at execution time, after
                # the movement step has actually placed the player at its target.
                step["target"] = None
                step["ambiguous"] = []
                step["door_by_default"] = True
        pending_condition = None
        # "Şu kapalı dükkânın kapısına": the kind of place named wins over a door
        # that only matched the word "kapı" (a different building's door).
        if step["place_noun"] and step["target"] is not None and step["target"]["kind"] in {"door", "place"} \
                and not step["named"]:
            place_id = step["target"].get("place_id") if step["target"]["kind"] == "door" else step["target"]["id"]
            record = (world.get("locations") or {}).get(place_id) or {}
            kinds = {record.get("scene_kind"), record.get("place_kind"), record.get("generic_noun")}
            if step["place_noun"][1] not in kinds and step["place_noun"][0] not in kinds:
                step["target"] = None
        # "İçeri giriyorum" with no name: the door the player stands at, or the only one here.
        if step["verb"] == "enter" and step["target"] is None and not step["place_noun"]:
            near = (world.get(KEY) or {}).get("near_target_id")
            doors = [c for c in cands if c["kind"] == "door"]
            chosen = next((c for c in doors if c["id"] == near), None) or (doors[0] if len(doors) == 1 else None)
            if chosen:
                step["target"] = chosen
        step["outside"] = any(t.startswith(_OUTSIDE_NOUNS) for t in goal_tokens) and step["target"] is None
        step["foreign_object"] = _foreign_object(tokens, info["verb_index"], step, cands) \
            if verb in {"inspect", "open", "knock", "read", "touch", "unlock", "force", "close", "search"} \
            and not purpose else None
        # "lock" alone means the door the lock belongs to.
        if step["target"] is None and step["part"] == "lock":
            doors = [c for c in cands if c["kind"] == "door"]
            near = (world.get(KEY) or {}).get("near_target_id")
            near_door = next((c for c in doors if c["id"] == near or c.get("place_id") == near), None)
            if near_door or len(doors) == 1:
                step["target"] = near_door or doors[0]
                step["door_by_default"] = True
        # "...pencereye tırmanmayacağım, altına gidip": "under it", "in front of it",
        # "next to it" point at what the previous clause was about.
        if steps and step["target"] is None and not step["detail"] and not step["place_noun"] \
                and any(t in _RELATIONAL for t in goal_tokens):
            previous = steps[-1]
            step["target"], step["detail"] = previous["target"], previous["detail"]
            step["place_noun"] = previous["place_noun"]
        steps.append(step)
    # "Binanın etrafında dolaşıp başka bir giriş arıyorum": the walk is how the
    # search is done, not a separate stroll that ends somewhere else.
    steps = [s for i, s in enumerate(steps)
             if not (s["verb"] == "wander" and i + 1 < len(steps) and steps[i + 1]["verb"] == "search")]
    conditional_seen = any(_read_clause(c)["conditional"] for c in clauses)
    bare = None
    if not steps and clauses:
        tokens = [t for c in clauses for t in c["tokens"]]
        if 1 <= len(tokens) <= 5 and not any(c.get("asked") for c in clauses):
            binding = bind(tokens, cands, world=world, verb=None)
            target = binding["target"]
            # Only the name itself (plus at most one word): "Garrick Hanı",
            # "Kızılhan?" - not a sentence that happens to contain a name.
            if target is not None and binding["score"] >= 100:
                name_words = max((len(n.split()) for n in target["names"] if n), default=0)
                if len(tokens) <= name_words + 1:
                    bare = target
            elif target is not None and len(tokens) == 1 and not binding["ambiguous"] \
                    and target["kind"] in {"door", "place", "feature"}:
                bare = target  # "kapı": the one door here, by its noun
    return {"steps": steps, "speech": speech, "candidates": cands, "bare_reference": bare,
            "first_person_act": bool(_FIRST_PERSON_ACT.search(fold(player_input))),
            "conditional_seen": conditional_seen}


_ADVERBS = re.compile(
    r"^(?:iki|uc|bir|birkac|kez|defa|sefer|hafif\w*|sert\w*|yavas\w*|dikkat\w*|sessiz\w*|hizli\w*|iyice|"
    r"sadece|biraz|tekrar|yine|once|simdi|hemen|iceri\w*|disari\w*|yakindan|uzaktan|\w+(?:ce|ca|cesine|casina)|"
    r"sehir\w*|kasaba\w*|koy\w*|etraf\w*|cevre\w*|civar\w*|burada|orada|yakin\w*|baska|diger|farkli|acik|kapali|olan|"
    r"\w+(?:madan|meden|arak|erek|ken)|ses)$"
)


def _foreign_object(tokens, verb_index, step, cands) -> str | None:
    """The word the verb acts on, when nothing this module owns matches it.

    "Zili çalıyorum" (a bell), "kitabı açıyorum" (a carried item), "izleri
    inceliyorum" (tracks) belong to other owners; pinning them on the nearest
    door would be a wrong act, so the turn is left to those owners.
    """
    if verb_index is None:
        return None
    index = verb_index - 1
    while index >= 0 and (_ADVERBS.match(tokens[index]) or _CONDITION_WORD.match(tokens[index])):
        index -= 1
    if index < 0:
        return None
    word = tokens[index]
    if len(word) < 2 or word in _PRONOUNS or word.startswith(_DOOR_NOUNS) or word.startswith(_OUTSIDE_NOUNS):
        return None
    if word in {"diye", "icin", "var", "varmi", "yok", "mi", "mu"} or _ACCESS_GOAL.search(" ".join(tokens)):
        return None  # "... var mı diye", "başka bir giriş": a search goal, not an object
    if any(word.startswith(part) for part in _LOCK_PARTS) or _detail_in([word]) or npc_statements.place_kind_of(word):
        return None
    for cand in cands:
        names = [n for n in cand["names"] if n] + [n for n in cand["nouns"] if n]
        if any(token_matches(w, word) for n in names for w in n.split()):
            return None
    return word


def _implicit_escort_target(session, step) -> dict[str, Any] | None:
    """'tamam gidelim' right after an NPC agreed to take the player somewhere."""
    world = session.world_state
    flags = world.get("flags", {})
    npc_id = flags.get("active_npc_id") or flags.get("last_npc_id")
    for commitment in reversed(npc_statements.open_commitments(world, npc_id=npc_id)):
        if commitment.get("kind") in {"escort", "show"} and commitment.get("destination"):
            return commitment
    return None


# ---------------------------------------------------------------------------
# Execution. Each handler does the act through the real owner and returns a
# receipt; text is written from that receipt only.
# ---------------------------------------------------------------------------
class _Run:
    def __init__(self, session, player_input):
        import game

        self.game = game
        self.session = session
        self.world = session.world_state
        self.text = player_input
        self.before = copy.deepcopy(session.world_state)
        self.checks: list[dict[str, Any]] = []
        self.inspections: list[dict[str, Any]] = []
        self.local_place: dict[str, Any] | None = None
        self.model_calls = 0
        self.model_ms: list[int] = []
        self.escorts: list[str] = []

    @property
    def here(self):
        return self.world.get("location")

    @property
    def memory(self):
        return _memory(self.world)

    def location(self, location_id):
        record = self.world.get("locations", {}).get(location_id)
        return record if isinstance(record, dict) else None

    def door_for(self, place_id):
        return next((d for d in self.world.get("doors", []) if isinstance(d, dict)
                     and d.get("id") == f"venue-door:{place_id}"), None)

    def door(self, door_id):
        return next((d for d in self.world.get("doors", []) if isinstance(d, dict) and d.get("id") == door_id), None)

    def spend(self, seconds):
        if seconds <= 0 or "campaign_time" not in self.world:
            return {}
        try:
            return self.session.advance_campaign_time(seconds, "exploration") or {}
        except Exception:
            return {}

    def near(self, target_id):
        self.memory["near_target_id"] = target_id
        self.memory["last_target_id"] = target_id


def _door_state_text(door: dict[str, Any]) -> str:
    name = door.get("name", "Kapı")
    if door.get("broken"):
        return f"{name} kırık, açık duruyor."
    if door.get("open"):
        return f"{name} açık."
    if door.get("locked"):
        return f"{name} kapalı ve kilitli."
    return f"{name} kapalı ama kilitli görünmüyor."


def _receipt(verb, status, target=None, **extra):
    data = {"verb": verb, "status": status}
    if isinstance(target, dict):
        data["target_id"] = target.get("id")
        data["target_name"] = target.get("label") or target.get("name")
    data.update({k: v for k, v in extra.items() if v is not None})
    return data


def _place_target(run: _Run, target: dict[str, Any] | None) -> dict[str, Any] | None:
    """A place candidate for a place, its door, or a followed reference."""
    if target is None:
        return None
    if target["kind"] == "place":
        return target
    if target["kind"] == "door" and target.get("place_id"):
        record = run.location(target["place_id"])
        if record:
            return {"id": target["place_id"], "kind": "place", "label": record.get("name"),
                    "record": record, "door_id": target["id"], "place_kind": record.get("scene_kind")}
    if target["kind"] == "reference":
        record = _materialize_reference(run, target["record"])
        if record:
            return {"id": record["id"], "kind": "place", "label": record.get("name"), "record": record,
                    "door_id": f"venue-door:{record['id']}" if run.door_for(record["id"]) else None,
                    "place_kind": record.get("place_kind") or record.get("scene_kind")}
    return None


_GENERIC_BUILDINGS: dict[str, dict[str, Any]] = {
    "dukkan": {"suffix": "Dükkânı", "noun": "dükkân", "door": "shop", "descriptions": (
        "Vitrin camı buğulu, tabelası rüzgârda sallanan küçük bir dükkân.",
        "Önüne birkaç sandık dizilmiş, dar cepheli bir dükkân.")},
    "depo": {"suffix": "Deposu", "noun": "depo", "door": "locked", "descriptions": (
        "Tahta kepenkleri çürümeye yüz tutmuş, geniş kapılı eski bir depo.",
        "Taş temelli, penceresiz, basık bir depo binası.")},
    "ambar": {"suffix": "Ambarı", "noun": "ambar", "door": "locked", "descriptions": (
        "Kalın kirişli, saman kokan eski bir ambar.",)},
    "konak": {"suffix": "Konağı", "noun": "konak", "door": "locked", "descriptions": (
        "Bahçe duvarı yüksek, pencereleri perdeli iki katlı bir konak.",)},
    "kule": {"suffix": "Kulesi", "noun": "kule", "door": "locked", "descriptions": (
        "Taşları yosun tutmuş, dar pencereli eski bir kule.",)},
    "meydan": {"suffix": "Meydanı", "noun": "meydan", "door": None, "descriptions": (
        "Ortasında kurumuş bir havuz olan, kaldırım taşlı küçük bir meydan.",)},
}


def _campaign_hour(world) -> int | None:
    try:
        import campaign_time
        public = campaign_time.public_time(world)
        return public.get("hour") if isinstance(public, dict) else None
    except Exception:
        return None


def _create_venue(run: _Run, settlement: str, *, name: str | None, kind: str,
                  provenance: dict[str, Any], noun: str | None = None) -> dict[str, Any] | None:
    import local_places

    world = run.world
    locations = world.setdefault("locations", {})
    if len(locations) >= 80:
        return None
    if kind in local_places.PLACE_KINDS:
        record = local_places.create_local_place(world, settlement, kind)
        if record is None:
            return None
        if name and fold(record.get("name")) != fold(name):
            record["name"] = name
            record["aliases"] = list(dict.fromkeys([*record.get("aliases", []), name]))
        record["provenance"] = provenance
        return record
    taverns = [r for r in locations.values() if isinstance(r, dict)
               and r.get("parent_location_id") == settlement and r.get("scene_kind") == "tavern"]
    if kind == "tavern" and len(taverns) >= 4:
        return None
    number = max(1, int(world.get("next_location_number", 1)))
    while f"location_{number:03d}" in locations:
        number += 1
    location_id = f"location_{number:03d}"
    world["next_location_number"] = number + 1
    if kind != "tavern":
        # A shop, store, house or tower: a plain local building with a real,
        # saved name and (for buildings people lock) a door whose state Python
        # decides. A square has no door.
        spec = _GENERIC_BUILDINGS.get(noun or "", _GENERIC_BUILDINGS["dukkan"])
        if not name:
            name = living_world.stable_local_name(world, settlement, f"local {noun or 'yer'}") + " " + spec["suffix"]
        record = {
            "id": location_id, "name": name, "type": "building",
            "aliases": [alias for alias in dict.fromkeys([name, noun or "", spec["noun"]]) if alias],
            "description": _pick(world, spec["descriptions"], location_id, "description"),
            "reality_layer": "PROCEDURAL_LOCAL_FICTION", "parent_location_id": settlement,
            "exit_location_id": settlement, "scene_kind": "building", "place_kind": None,
            "generic_noun": noun, "tags": ["campaign_local"], "provenance": provenance,
        }
        locations[location_id] = record
        if spec["door"]:
            hour = _campaign_hour(world)
            open_hours = spec["door"] == "shop" and isinstance(hour, int) and 8 <= hour < 19
            world.setdefault("doors", []).append({
                "id": f"venue-door:{location_id}", "name": f"{name} Kapısı", "location": settlement,
                "description": f"{name} sokağa açılan kapısı.", "open": False,
                "locked": not open_hours or _seed(world, location_id, "door") % 4 == 0, "broken": False,
            })
        return record
    if not name:
        name = living_world.stable_local_name(world, settlement, f"local tavern {len(taverns) + 1}") + " Hanı"
    record = {
        "id": location_id,
        "name": name,
        "type": "building",
        "aliases": ["taverna", "tavern", "inn", "han", "meyhane", name],
        "description": _pick(world, (
            "İki katlı, cumbalı bir han; kapısının üstünde is lekeli bir fener asılı.",
            "Taş temelli, ahşap üst katlı bir han; pencerelerinden mutfak kokusu sızıyor.",
            "Avlusuna fıçılar yığılmış, basık çatılı bir han.",
        ), location_id, "description"),
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "parent_location_id": settlement,
        "exit_location_id": settlement,
        "scene_kind": "tavern",
        "tags": ["campaign_local", "public_house"],
        "provenance": provenance,
    }
    locations[location_id] = record
    # The door's state is Python's, not what anyone said about the place.
    hour = None
    try:
        import campaign_time
        public = campaign_time.public_time(world)
        hour = public.get("hour") if isinstance(public, dict) else None
    except Exception:
        hour = None
    business = isinstance(hour, int) and 10 <= hour < 23
    locked = not business or _seed(world, location_id, "door") % 5 == 0
    world.setdefault("doors", []).append({
        "id": f"venue-door:{location_id}",
        "name": f"{name} Kapısı",
        "location": settlement,
        "description": f"{name} sokağa açılan kapısı.",
        "open": False,
        "locked": locked,
        "broken": False,
    })
    return record


def _materialize_reference(run: _Run, ref: dict[str, Any]) -> dict[str, Any] | None:
    if ref.get("location_id") and run.location(ref["location_id"]):
        return run.location(ref["location_id"])
    settlement = ref.get("settlement_id") or _settlement(run.world)
    if not settlement or not run.location(settlement):
        return None
    if ref.get("name"):
        existing = npc_statements._existing_location_named(run.world, ref["name"])
        if existing:
            npc_statements.resolve_reference(run.world, ref["id"], existing)
            return run.location(existing)
    record = _create_venue(run, settlement, name=ref.get("name"), kind=ref.get("place_kind") or "generic",
                           noun=ref.get("noun"), provenance={"source": "npc_statement", "said_by": ref.get("said_by"),
                                       "reference_id": ref.get("id"), "claims": list(ref.get("claims", [])),
                                       "quotes": list(ref.get("quotes", []))[:2]})
    if record:
        npc_statements.resolve_reference(run.world, ref["id"], record["id"])
    return record


def _escort_with(run: _Run, place: dict[str, Any] | None, commitment: dict[str, Any] | None) -> str:
    """An NPC who really agreed to take the player along walks with them."""
    world = run.world
    pool = [commitment] if commitment else [
        c for c in npc_statements.open_commitments(world) if c.get("kind") in {"escort", "show"}
    ]
    for item in pool:
        if not item:
            continue
        npc = npc_statements._npc(world, item.get("npc_id"))
        if not npc or npc.get("location") != run.here or npc.get("status", "active") != "active":
            continue
        destination = item.get("destination") or {}
        matches = commitment is not None or not destination
        if place is not None and not matches:
            ref_id = destination.get("ref_id")
            ref = next((r for r in npc_statements.place_references(world) if r["id"] == ref_id), None) if ref_id else None
            matches = (destination.get("location_id") == place["id"]
                       or (ref is not None and ref.get("location_id") == place["id"])
                       or destination.get("place_kind") in {place.get("place_kind"), place["record"].get("scene_kind")})
        if matches:
            run.escorts.append(npc["id"])
            npc_statements.fulfil(world, item["id"], "walked_with_player")
            return living_world.public_npc_name(npc)
    return ""


def _arrive_front(run: _Run, place: dict[str, Any], *, verb: str, commitment=None, prefix: str = "") -> dict[str, Any]:
    """Stand in front of a place in the current street (no teleport inside)."""
    import local_places

    record = place["record"]
    companion = _escort_with(run, place, commitment)
    with_text = f" {companion} yanında yürüyor." if companion else ""
    door = run.door_for(place["id"])
    if run.here != record.get("parent_location_id"):
        parent = record.get("parent_location_id")
        if parent and run.location(parent) and run.here != parent:
            if not run.game.commit_location_change(parent):
                return _receipt(verb, "blocked", place, reason="cannot_leave", text="Bulunduğun yerden çıkamıyorsun.")
            prefix += f"Dışarı, {run.location(parent).get('name')} sokaklarına çıkıyorsun. "
    if door is not None:
        run.near(door["id"])
        text = f"{prefix}{record.get('name')} önüne geliyorsun.{with_text} {_door_state_text(door)}"
        if verb == "go" and (door.get("open") or door.get("broken")):
            return _enter(run, place, prefix=text + " ")
        return _receipt(verb, "completed", place, text=text.strip(), door_state=_door_public(door),
                        position="at_door")
    if verb == "go" and record.get("place_kind") in local_places.PLACE_KINDS:
        return _enter(run, place, prefix=prefix + with_text.strip() + (" " if with_text else ""))
    run.near(place["id"])
    description = record.get("description") or ""
    return _receipt(verb, "completed", place, text=f"{prefix}{record.get('name')} önüne geliyorsun.{with_text} {description}".strip(),
                    position="outside")


def _door_public(door):
    return {"open": bool(door.get("open")), "locked": bool(door.get("locked")), "broken": bool(door.get("broken"))}


def _enter(run: _Run, place: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:
    import local_places

    record = place["record"]
    if run.here == place["id"]:
        return _receipt("enter", "completed", place, text=f"{prefix}Zaten {record.get('name')} içindesin.".strip())
    door = run.door_for(place["id"])
    opened = ""
    if door is not None and not door.get("open") and not door.get("broken"):
        if door.get("locked"):
            run.near(door["id"])
            return _receipt("enter", "blocked", place, reason="door_locked",
                            text=f"{prefix}{_door_state_text(door)} İçeri giremiyorsun.".strip(),
                            door_state=_door_public(door))
        door["open"] = True
        opened = f"{door.get('name', 'Kapı')} kolunu çevirip açıyorsun. "
    companions = [npc_statements._npc(run.world, npc_id) for npc_id in run.escorts]
    scenes = (run.world.get("scene_state") or {}).get("scenes") or {}
    seen_before = isinstance(scenes.get(place["id"]), dict) and scenes[place["id"]].get("last_visit_turn") is not None
    if not run.game.commit_location_change(place["id"]):
        return _receipt("enter", "blocked", place, reason="entry_refused",
                        text=f"{prefix}İçeri geçemiyorsun.".strip())
    for npc in companions:
        if npc:
            npc["location"] = place["id"]
    run.near(None)
    run.memory["last_target_id"] = place["id"]
    if record.get("place_kind") in local_places.PLACE_KINDS:
        npc, feature = local_places.furnish(run.world, record, create_npc=run.game.create_npc_from_ai,
                                            create_feature=run.game.create_local_feature)
        first = not seen_before
        run.local_place = {"kind": record["place_kind"], "created": first,
                           "npc_id": npc.get("id") if isinstance(npc, dict) else None}
        arrival = local_places.arrival_text(run.world, record, npc, feature, first_visit=first)
        return _receipt("enter", "completed", place, text=f"{prefix}{opened}{arrival}".strip())
    people = [living_world.public_npc_name(n) for n in run.game.active_npcs(place["id"])][:3]
    inside = f" İçeride {', '.join(people)} var." if people else " İçerisi sessiz."
    description = record.get("description") or ""
    return _receipt("enter", "completed", place,
                    text=f"{prefix}{opened}{record.get('name')} içine giriyorsun. {description}{inside}".strip())


def _current_door_target(run: _Run, step) -> dict[str, Any] | None:
    """The door a door verb means: the bound one, the one we stand at, or the only one."""
    target = step.get("target")
    if target and target["kind"] == "door":
        return target
    if target and target["kind"] in {"place", "reference"}:
        place = _place_target(run, target)
        if place and place.get("door_id"):
            door = run.door(place["door_id"])
            if door and door.get("location") == run.here:
                return {"id": door["id"], "kind": "door", "label": door.get("name"), "record": door,
                        "place_id": place["id"]}
        return None
    doors = [d for d in run.world.get("doors", []) if isinstance(d, dict)
             and d.get("location") == run.here and not d.get("hidden")]
    near = run.memory.get("near_target_id")
    chosen = next((d for d in doors if d["id"] == near or d["id"] == f"venue-door:{near}"), None)
    if chosen is None and len(doors) == 1:
        chosen = doors[0]
    if chosen is None:
        return None
    place_id = chosen["id"].split(":", 1)[1] if chosen["id"].startswith("venue-door:") else None
    return {"id": chosen["id"], "kind": "door", "label": chosen.get("name"), "record": chosen, "place_id": place_id}


def _lock_policy(door):
    policy = door.get("lock_policy") if isinstance(door.get("lock_policy"), dict) else {}
    quality = policy.get("quality", "good")
    complexity = policy.get("complexity", "simple")
    return {
        "unlock_dc": {"inferior": 10, "good": 15, "superior": 20}.get(quality, 15),
        "break_dc": 15,
        "seconds": 6 if complexity == "simple" else 60,
        "words": {"inferior": "basit, ucuz işçilik", "good": "sağlam, düzgün işçilik",
                  "superior": "usta işi, karmaşık"}.get(quality, "sağlam"),
    }


def _check(run: _Run, skill: str, dc: int, *, tool=None, disadvantage=False) -> dict[str, Any]:
    import exploration

    check = exploration._check(run.session, skill, dc, tool=tool, disadvantage=disadvantage)
    run.checks.append(check)
    return check


def _guard_reaction(run: _Run) -> str:
    for npc in run.game.active_npcs(run.here):
        role = fold(npc.get("role", ""))
        if any(word in role for word in ("muhafiz", "guard", "nobet", "bekci")):
            return f" {living_world.public_npc_name(npc)} gürültüye başını çevirip sana bakıyor."
    return ""


def _do_knock(run: _Run, step) -> dict[str, Any]:
    door_target = _current_door_target(run, step)
    if door_target is None:
        return _doorless_entrance(run, step, "knock") or _receipt(
            "knock", "blocked", step.get("target"), reason="no_door", text="Vurabileceğin bir kapı yakınında değil.")
    door = door_target["record"]
    run.near(door["id"])
    name = door.get("name", "Kapı")
    if door.get("open") or door.get("broken"):
        return _receipt("knock", "completed", door_target, text=f"{name} zaten açık; vurmana gerek kalmadan içerisi görünüyor.")
    try:
        import campaign_time
        public = campaign_time.public_time(run.world) or {}
    except Exception:
        public = {}
    bucket = f"{public.get('day_index', 0)}:{(public.get('hour') or 0) // 3}"
    key = f"{door['id']}|{bucket}"
    answers = run.memory["answers"]
    if key not in answers:
        roll = _seed(run.world, key, "answer") % 100
        if door.get("locked"):
            answers[key] = _pick(run.world, (
                "İçeriden boğuk bir ses geliyor: “Kapalıyız! Akşamüstü gel.” Sonra ayak sesleri uzaklaşıyor.",
                "Bir süre bekliyorsun. İçeriden ne bir ses ne bir ayak sesi geliyor.",
                "Üst kattaki bir kepenk aralanıyor, biri aşağı bakıp başını sallıyor ve kepengi geri kapatıyor.",
            ), key) if roll < 70 else "Bir süre bekliyorsun; içeriden yanıt gelmiyor."
        else:
            answers[key] = "İçeriden bir ses sesleniyor: “Açık, buyur gir!”"
    knock_words = "Tokmağı birkaç kez vuruyorsun" if step.get("part") == "knocker" else f"{name} üzerine birkaç kez vuruyorsun"
    declined = " Kapıyı zorlamıyorsun." if "force" in (step.get("manner_negated") or []) else ""
    state = " Kapı kilitli kalıyor." if door.get("locked") else ""
    return _receipt("knock", "completed", door_target,
                    text=f"{knock_words}.{declined} {answers[key]}{state}".strip(), answer=answers[key])


def _do_call_out(run: _Run, step) -> dict[str, Any]:
    door_target = _current_door_target(run, step)
    if door_target is not None:
        result = _do_knock(run, step)
        result["verb"] = "call_out"
        result["text"] = result["text"].replace("Tokmağı birkaç kez vuruyorsun", "Sesleniyorsun").replace(
            f"{door_target['record'].get('name', 'Kapı')} üzerine birkaç kez vuruyorsun", "Kapıya doğru sesleniyorsun")
        return result
    people = run.game.active_npcs(run.here)
    if people:
        who = living_world.public_npc_name(people[0])
        return _receipt("call_out", "completed", None, text=f"Sesleniyorsun. {who} başını çevirip sana bakıyor.")
    return _receipt("call_out", "completed", None, text="Sesleniyorsun; sesin sokakta yankılanıp kayboluyor.")


def _doorless_entrance(run: _Run, step, verb: str) -> dict[str, Any] | None:
    """A public place without a registered door (temple, market, archive): its way in stands open."""
    host = _host_place(run, step)
    if host is None or run.door_for(host["id"]):
        return None
    texts = {
        "knock": f"{host['label']} girişinde kapalı bir kapı yok; içeriden sesler geliyor, çalmana gerek kalmıyor.",
        "open": f"{host['label']} girişi zaten açık.",
        "inspect": f"{host['label']} girişi ardına kadar açık; içeriyi buradan seçebiliyorsun.",
    }
    return _receipt(verb, "completed", host, text=texts.get(verb, texts["inspect"]), door_state={"open": True})


def _do_climb(run: _Run, step) -> dict[str, Any]:
    key = step.get("detail")
    host = _host_place(run, step)
    if key is None or DETAILS[key]["class"] != "access":
        return _receipt("climb", "blocked", None, reason="nothing_to_climb", text="Tırmanabileceğin belirgin bir yer görmüyorsun.")
    feature, decision = _detail_feature(run, key, host)
    if not decision.get("exists") or feature is None:
        return _receipt("climb", "blocked", host, reason="not_here",
                        text=f"Görünürde tırmanabileceğin bir {DETAILS[key]['name'].lower()} yok.")
    check = _check(run, "Athletics", 12)
    run.near(feature["id"])
    if check["success"]:
        return _receipt("climb", "completed", {"id": feature["id"], "label": feature.get("name")}, check=_check_public(check),
                        text=f"Tutunacak yerleri bulup {feature.get('name')} hizasına kadar tırmanıyorsun; içeri girmiyorsun.")
    return _receipt("climb", "failed", {"id": feature["id"], "label": feature.get("name")}, check=_check_public(check),
                    text="Tutunduğun yer kayıyor; birkaç adım tırmanıp yere iniyorsun.")


def _open_container(run: _Run, step, key: str) -> dict[str, Any]:
    host = _host_place(run, step)
    feature, decision = _detail_feature(run, key, host)
    if feature is None:
        return _receipt("open", "blocked", None, reason="not_here", text=f"Yakında bir {DETAILS[key]['name'].lower()} görmüyorsun.")
    if "locked" not in decision:
        decision["locked"] = _seed(run.world, feature.get("id"), "lock") % 10 < 3
        decision["contents"] = _pick(run.world, _CONTAINERS[key], feature.get("id"), "contents")
    run.near(feature["id"])
    target = {"id": feature["id"], "label": feature.get("name")}
    if decision["locked"]:
        return _receipt("open", "blocked", target, reason="container_locked",
                        text=f"{feature.get('name')} kapağı kilitli; asma kilit yerinden oynamıyor.")
    return _receipt("open", "completed", target, text=decision["contents"])


def _do_open(run: _Run, step) -> dict[str, Any]:
    if step.get("part") == "lock":
        return _do_unlock(run, step)
    target = step.get("target")
    if step.get("detail") in _CONTAINERS and (target is None or target["kind"] == "feature"):
        return _open_container(run, step, step["detail"])
    if target and target["kind"] == "feature":
        return _open_feature(run, target)
    door_target = _current_door_target(run, step)
    if door_target is None:
        return _doorless_entrance(run, step, "open") or _receipt(
            "open", "blocked", target, reason="no_door", text="Burada açabileceğin bir kapı görmüyorsun.")
    door = door_target["record"]
    run.near(door["id"])
    if door.get("open") or door.get("broken"):
        return _receipt("open", "completed", door_target, text=f"{door.get('name')} zaten açık.")
    if door.get("locked"):
        part = {"latch": "Mandalı kaldırıyorsun", "handle": "Kolu çeviriyorsun"}.get(step.get("part"), "Kapıyı itiyorsun")
        return _receipt("open", "blocked", door_target, reason="door_locked", door_state=_door_public(door),
                        text=f"{part} ama {door.get('name')} kilitli; yerinden oynamıyor. "
                             "Kilidi açmayı, kapıyı çalmayı ya da başka bir giriş aramayı deneyebilirsin.")
    door["open"] = True
    return _receipt("open", "completed", door_target, text=f"{door.get('name')} gıcırdayarak açılıyor.",
                    door_state=_door_public(door))


def _do_close(run: _Run, step) -> dict[str, Any]:
    door_target = _current_door_target(run, step)
    if door_target is None:
        return _receipt("close", "blocked", None, reason="no_door", text="Kapatabileceğin bir kapı görmüyorsun.")
    door = door_target["record"]
    if door.get("broken"):
        return _receipt("close", "blocked", door_target, reason="door_broken", text="Kırık kapı kapanmıyor.")
    if not door.get("open"):
        return _receipt("close", "completed", door_target, text=f"{door.get('name')} zaten kapalı.")
    door["open"] = False
    return _receipt("close", "completed", door_target, text=f"{door.get('name')} kapatıyorsun.")


_IMPROVISED = re.compile(r"hancer|bicak|tel|firkete|igne|civi|dagger|knife")


def _do_unlock(run: _Run, step) -> dict[str, Any]:
    import equipment_economy

    door_target = _current_door_target(run, step)
    if door_target is None:
        return _receipt("unlock", "blocked", step.get("target"), reason="no_door",
                        text="Üzerinde uğraşabileceğin bir kilit yakınında değil.")
    door = door_target["record"]
    run.near(door["id"])
    if not door.get("locked"):
        return _receipt("unlock", "completed", door_target, text=f"{door.get('name')} zaten kilitli değil.")
    labels = [equipment_economy.label(item) for item in run.world.get("inventory", [])]
    tools = any(label == "Thieves' Tools" or "hirsiz alet" in fold(label) for label in labels)
    improvised = next((label for label in labels if _IMPROVISED.search(fold(label))), None)
    policy = _lock_policy(door)
    if not tools and not improvised:
        return _receipt("unlock", "blocked", door_target, reason="tools_required", door_state=_door_public(door),
                        text=f"Kilide eğilip bakıyorsun: {policy['words']} bir kilit. Elinde maymuncuk ya da "
                             "ince bir alet yok; dilini çıplak parmakla oynatamıyorsun. Kapıyı çalabilir, "
                             "zorlayabilir ya da başka bir giriş arayabilirsin.")
    time_result = run.spend(policy["seconds"])
    if time_result.get("interrupted"):
        return _receipt("unlock", "blocked", door_target, reason="interrupted", text="Kilitle uğraşırken bir şey seni durduruyor.")
    check = _check(run, "Sleight of Hand", policy["unlock_dc"],
                   tool="Thieves' Tools" if tools else None, disadvantage=not tools)
    tool_text = "Maymuncuklarını" if tools else f"{improvised} ucunu"
    if check["success"]:
        door["locked"] = False
        return _receipt("unlock", "completed", door_target, check=_check_public(check), door_state=_door_public(door),
                        text=f"{tool_text} kilide sokup sabırla oynatıyorsun. Bir tık sesi geliyor: kilit açıldı.")
    return _receipt("unlock", "failed", door_target, check=_check_public(check), door_state=_door_public(door),
                    text=f"{tool_text} kilide sokup oynatıyorsun ama dilleri bir türlü yerine oturmuyor. Kapı kilitli kalıyor.")


def _do_force(run: _Run, step) -> dict[str, Any]:
    door_target = _current_door_target(run, step)
    if door_target is None:
        return _receipt("force", "blocked", step.get("target"), reason="no_door", text="Zorlayabileceğin bir kapı yakınında değil.")
    door = door_target["record"]
    run.near(door["id"])
    if door.get("open") or door.get("broken"):
        return _receipt("force", "completed", door_target, text=f"{door.get('name')} zaten açık.")
    policy = _lock_policy(door)
    time_result = run.spend(6)
    if time_result.get("interrupted"):
        return _receipt("force", "blocked", door_target, reason="interrupted", text="Kapıya yüklenecekken bir şey seni durduruyor.")
    check = _check(run, "Athletics", policy["break_dc"])
    if check["success"]:
        door.update(locked=False, open=True, broken=True)
        return _receipt("force", "completed", door_target, check=_check_public(check), door_state=_door_public(door),
                        text=f"Omzunla {door.get('name')} kapısına yükleniyorsun; kilit dili kasadan kopuyor, kapı açılıyor.{_guard_reaction(run)}")
    return _receipt("force", "failed", door_target, check=_check_public(check), door_state=_door_public(door),
                    text=f"{door.get('name')} kapısına yükleniyorsun; tahta inliyor ama dayanıyor.{_guard_reaction(run)}")


def _check_public(check):
    keys = ("skill", "ability", "dice", "dice_rolls", "modifier", "proficiency_bonus", "total", "dc",
            "outcome", "success", "advantage", "disadvantage", "tool")
    return {k: check.get(k) for k in keys if k in check}


# --- looking ---------------------------------------------------------------
def _host_place(run: _Run, step) -> dict[str, Any] | None:
    """The building a detail belongs to: the bound place, or the one we stand at."""
    target = step.get("target")
    place = _place_target(run, target) if target and target["kind"] in {"place", "door", "reference"} else None
    if place:
        return place
    near = run.memory.get("near_target_id")
    if isinstance(near, str):
        place_id = near.split(":", 1)[1] if near.startswith("venue-door:") else near
        record = run.location(place_id)
        if record and record.get("parent_location_id") == run.here:
            return {"id": place_id, "kind": "place", "label": record.get("name"), "record": record,
                    "door_id": f"venue-door:{place_id}" if run.door_for(place_id) else None}
    return None


def _detail_feature(run: _Run, key: str, host: dict[str, Any] | None, *, decide=True,
                    materialize=True) -> tuple[dict | None, dict]:
    """Find or decide (once) a local detail. Returns (feature or None, decision)."""
    spec = DETAILS[key]
    owner = host["id"] if host else run.here
    decision_key = f"{owner}|{spec['name']}"
    decisions = run.memory["details"]
    decision = decisions.get(decision_key)
    if decision is None:
        if not decide:
            return None, {}
        if spec["class"] == "access":
            exists = host is not None and _seed(run.world, decision_key, "exists") % 100 < spec["chance"]
            state = _pick(run.world, spec["states"], decision_key, "state") if exists else None
            decision = {"exists": exists, "state": state, "class": "access"}
        else:
            decision = {"exists": True, "state": None, "class": "flavor",
                        "description": _pick(run.world, spec["descriptions"], decision_key, "desc")}
        decisions[decision_key] = decision
    feature = None
    if decision.get("exists") and materialize:
        feature_id = decision.get("feature_id")
        feature = next((f for f in run.world.get("features", []) if f.get("id") == feature_id), None) if feature_id else None
        if feature is None:
            name = f"{host['label']} {spec['name'].lower()}" if host and spec["class"] == "access" else spec["name"]
            description = decision.get("description") or (
                f"{host['label'] if host else 'Bina'} cephesinde {spec['name'].lower()}; {decision['state']}.")
            feature = run.game.create_local_feature({
                "location": run.here, "name": name[:60], "description": description[:200],
                "kind": "detail", "aliases": [key, spec["name"].lower()],
            })
            if isinstance(feature, dict):
                feature["grounded_detail"] = {"key": key, "host_id": host["id"] if host else None,
                                              "class": spec["class"], "state": decision.get("state")}
                decision["feature_id"] = feature.get("id")
    return feature, decision


def _observe_detail(run: _Run, step, key: str) -> dict[str, Any]:
    host = _host_place(run, step)
    spec = DETAILS[key]
    if spec["class"] == "access" and host is None:
        return _receipt(step["verb"], "blocked", None, reason="no_building",
                        text=f"Hangi binanın {spec['name'].lower()}ine bakmak istediğin belli değil; önce bir binanın önüne git.")
    feature, decision = _detail_feature(run, key, host)
    if not decision.get("exists"):
        return _receipt(step["verb"], "completed", host, found=False, detail=key,
                        text=f"{host['label']} çevresine bakıyorsun; görünürde bir {spec['name'].lower()} yok.")
    run.memory["last_target_id"] = feature.get("id") if feature else None
    run.inspections.append({"target_name": feature.get("name") if feature else spec["name"],
                            "target_kind": "feature", "found": True})
    text = feature.get("description") if feature else spec["name"]
    if spec["class"] == "access" and decision.get("state") == "aralık":
        text += " Biraz zorlasan içeri bakabilecek kadar aralık."
    if key == "tabela" and host:
        text += f" Üzerinde “{host['label']}” yazıyor."
    return _receipt(step["verb"], "completed", {"id": feature.get("id") if feature else None, "label": spec["name"]},
                    found=True, detail=key, text=text)


def _do_inspect(run: _Run, step) -> dict[str, Any]:
    target = step.get("target")
    if target is None and step.get("detail"):
        return _observe_detail(run, step, step["detail"])
    if target is None and step.get("part"):
        target = _current_door_target(run, step)
    if target is None and step.get("place_noun"):
        return _do_search(run, step)
    if target is None and any(t.startswith("kapi") for t in step.get("tokens", [])) \
            and _current_door_target(run, step) is None:
        doorless = _doorless_entrance(run, step, "inspect")
        if doorless:
            return doorless
    if target is None:
        near = run.memory.get("near_target_id")
        target = next((c for c in candidates(run.session) if c["id"] == near), None)
    if target is None:
        return _receipt("inspect", "blocked", None, reason="no_target",
                        text="Neye bakmak istediğini seçemedim. " + clarification_text(run.session))
    if target["kind"] == "door" or step.get("part"):
        return _inspect_door(run, step, target if target["kind"] == "door" else _current_door_target(run, step))
    if target["kind"] in {"place", "reference"}:
        place = _place_target(run, target)
        record = place["record"]
        door = run.door_for(place["id"])
        run.near(door["id"] if door and door.get("location") == run.here else place["id"])
        parts = [f"{record.get('name')}: {record.get('description') or 'sıradan bir bina'}"]
        if door:
            parts.append(_door_state_text(door))
        run.inspections.append({"target_name": record.get("name"), "target_kind": "place", "found": True})
        return _receipt("inspect", "completed", place, text=" ".join(parts))
    if target["kind"] == "npc":
        npc = target["record"]
        looks = npc.get("appearance") or "Sıradan giyimli biri."
        run.memory["last_target_id"] = npc["id"]
        return _receipt("inspect", "completed", target, text=f"{target['label']}: {looks}")
    if target["kind"] == "feature":
        feature = target["record"]
        run.near(feature["id"])
        run.inspections.append({"target_name": feature.get("name"), "target_kind": "feature", "found": True})
        return _receipt("inspect", "completed", target, text=feature.get("description") or feature.get("name", ""))
    if target["kind"] == "outside":
        return _receipt("inspect", "completed", target, text=f"Dışarıda {target['label']} sokakları uzanıyor.")
    if target["kind"] == "here":
        record = target["record"]
        return _receipt("inspect", "completed", target,
                        text=f"{record.get('name')}: {record.get('description') or 'etrafında belirgin bir değişiklik yok'}.")
    return _receipt("inspect", "blocked", target, reason="no_target", text="Bunu inceleyemiyorsun.")


def _inspect_door(run: _Run, step, door_target) -> dict[str, Any]:
    if door_target is None:
        return _receipt("inspect", "blocked", None, reason="no_door", text="Yakınında incelenecek bir kapı yok.")
    door = door_target["record"]
    run.near(door["id"])
    part = step.get("part") or "door"
    signature = json.dumps(_door_public(door), sort_keys=True)
    key = f"{door['id']}|{part}|{signature}"
    observations = run.memory["observations"]
    careful = any(t.startswith(("incel", "dikkat", "kontrol", "muayene")) for t in step.get("tokens", []))
    known = observations.get(key)
    policy = _lock_policy(door)
    if known and (not careful or known.get("careful")):
        # The saved fact is the outcome; the words are rebuilt from the current record.
        text = _door_part_text(door, part, policy) + (_lock_finding(policy, known["found"]) if known.get("careful") else "")
        run.inspections.append({"target_name": door.get("name"), "target_kind": "door", "found": known.get("found")})
        return _receipt("inspect", "completed", door_target, repeated_observation=True,
                        text=text + " Daha önce gördüğünden fazlasını seçemiyorsun.")
    base = _door_part_text(door, part, policy)
    found = None
    text = base
    if careful and part in {"lock", "door"} and door.get("locked"):
        check = _check(run, "Investigation", 12)
        found = check["success"]
        text = base + _lock_finding(policy, found)
        observations[key] = {"found": found, "careful": True, "check": _check_public(check)}
        run.inspections.append({"target_name": door.get("name"), "target_kind": "door", "found": found})
        return _receipt("inspect", "completed", door_target, check=_check_public(check), text=text, found=found)
    observations[key] = {"found": True, "careful": careful}
    run.inspections.append({"target_name": door.get("name"), "target_kind": "door", "found": True})
    return _receipt("inspect", "completed", door_target, text=text, found=True)


def _lock_finding(policy, found) -> str:
    if found:
        return (" Yakından bakınca mekanizmayı seçiyorsun: maymuncukla açılabilir, "
                f"{'kısa sürede' if policy['seconds'] <= 6 else 'epey uğraştırarak'}.")
    return " Mekanizmanın içini bu bakışla seçemiyorsun."


def _door_part_text(door, part, policy) -> str:
    base = _door_state_text(door)
    if part == "lock":
        base = f"{door.get('name')} kilitli; {policy['words']} bir kilit." if door.get("locked") else \
            f"{door.get('name')} kilidi açık; dili geri çekilmiş."
        base += " Zorlandığına dair bir iz yok." if not door.get("broken") else " Kasası parçalanmış."
    elif part == "knocker":
        base = f"{door.get('name')} üzerinde dökme demir bir tokmak var; kullanılmaktan parlamış."
    elif part in {"latch", "handle"}:
        base = f"{door.get('name')} kolu sağlam. " + ("Kapı kilitli olduğu için kol boşa dönüyor." if door.get("locked") else "Kapı kilitli değil.")
    return base


def _open_feature(run: _Run, target) -> dict[str, Any]:
    feature = target["record"]
    info = feature.get("grounded_detail") or {}
    state = info.get("state")
    if info.get("class") != "access":
        return _receipt("open", "blocked", target, reason="not_openable", text=f"{feature.get('name')} açılacak bir şey değil.")
    if state == "aralık":
        return _receipt("open", "completed", target, text=f"{feature.get('name')} biraz daha aralanıyor.")
    return _receipt("open", "blocked", target, reason="feature_closed", text=f"{feature.get('name')} {state}; açılmıyor.")


def _do_read(run: _Run, step) -> dict[str, Any]:
    target = step.get("target")
    if target is None and step.get("detail") in {"tabela", "ilan", "afis"}:
        return _observe_detail(run, step, step["detail"])
    if target and target["kind"] in {"place", "door", "reference"}:
        place = _place_target(run, target)
        if place:
            return _receipt("read", "completed", place, text=f"Kapının üstündeki tabelada “{place['label']}” yazıyor.")
    if target and target["kind"] == "feature":
        feature = target["record"]
        return _receipt("read", "completed", target, text=feature.get("text") or feature.get("description")
                        or f"{feature.get('name')} üzerinde okunacak bir yazı yok.")
    return None


def _do_listen(run: _Run, step) -> dict[str, Any]:
    host = _host_place(run, step)
    if host:
        door = run.door_for(host["id"])
        sound = _pick(run.world, ("İçeriden tabak çanak tıngırtısı ve alçak sesler geliyor.",
                                  "İçerisi sessiz; yalnızca bir yerde damlayan su sesi var.",
                                  "Üst kattan ağır ayak sesleri duyuluyor, sonra kesiliyor."),
                      host["id"], (run.world.get("campaign_time") or {}).get("elapsed_seconds", 0) // 3600)
        if door and door.get("locked"):
            sound = sound if "tabak" not in sound else "İçerisi sessiz; kapalı bir yerin ağır sessizliği."
        return _receipt("listen", "completed", host, text=f"{host['label']} kapısına kulak veriyorsun. {sound}",
                        answer=sound)
    people = run.game.active_npcs(run.here)
    who = f" {living_world.public_npc_name(people[0])} kendi işine dalmış." if people else ""
    return _receipt("listen", "completed", None, text=f"Kulak veriyorsun: uzaktan araba tekerlekleri, satıcı sesleri.{who}")


def _do_touch(run: _Run, step) -> dict[str, Any] | None:
    target = step.get("target")
    if target is None and step.get("detail"):
        return _observe_detail(run, step, step["detail"])
    if target and target["kind"] == "door":
        door = target["record"]
        return _receipt("touch", "completed", target, text=f"{door.get('name')} tahtası serin ve pürüzlü; "
                                                          + ("kımıldamıyor." if door.get("locked") else "hafifçe esniyor."))
    if target and target["kind"] == "feature":
        return _receipt("touch", "completed", target, text=target["record"].get("description") or target["label"])
    return None


# --- moving -----------------------------------------------------------------
def _commitment_place(run: _Run, commitment) -> dict[str, Any] | None:
    destination = commitment.get("destination") or {}
    if destination.get("location_id") and run.location(destination["location_id"]):
        record = run.location(destination["location_id"])
        return {"id": destination["location_id"], "kind": "place", "label": record.get("name"), "record": record,
                "door_id": f"venue-door:{destination['location_id']}" if run.door_for(destination["location_id"]) else None,
                "place_kind": record.get("scene_kind")}
    if destination.get("ref_id"):
        ref = next((r for r in npc_statements.place_references(run.world) if r["id"] == destination["ref_id"]), None)
        if ref:
            return _place_target(run, {"id": ref["id"], "kind": "reference", "record": ref, "label": ref.get("name")})
    return None


def _do_move(run: _Run, step, verb: str) -> dict[str, Any]:
    target = step.get("target")
    commitment = step.get("commitment")
    if target is None and commitment is not None:
        place = _commitment_place(run, commitment)
        if place:
            return _arrive_front(run, place, verb="go" if verb == "go" else "approach", commitment=commitment)
    if target is None and step.get("outside"):
        if run.location(run.here) and run.location(run.here).get("parent_location_id"):
            return _do_leave(run, step)
        return _receipt(verb, "completed", None, text="Zaten sokaktasın.")
    if target is None and step.get("place_noun"):
        return _do_search(run, step, move=True)
    if target is None and step.get("detail"):
        host = _host_place(run, step)
        feature, decision = _detail_feature(run, step["detail"], host)
        if feature:
            run.near(feature["id"])
            return _receipt(verb, "completed", {"id": feature["id"], "label": feature.get("name")},
                            text=f"{feature.get('name')} yanına geliyorsun. {feature.get('description', '')}".strip())
        return _receipt(verb, "blocked", None, reason="not_here",
                        text=f"Yakında bir {DETAILS[step['detail']]['name'].lower()} görmüyorsun.")
    if target is None:
        return _receipt(verb, "blocked", None, reason="no_target", text=clarification_text(run.session))
    kind = target["kind"]
    if kind == "here":
        return _receipt(verb, "completed", target, text=f"Zaten {target['label']} içindesin.", position="inside")
    if kind == "npc":
        npc = target["record"]
        flags = run.world.setdefault("flags", {})
        run.game._set_scene_active_npc(npc, int(flags.get("turn_index", 0)) + 1)
        npc["distance_ft"] = 5
        run.near(npc["id"])
        return _receipt(verb, "completed", target, text=f"{target['label']} yanına gidiyorsun; seni fark edip sana dönüyor.")
    if kind == "outside":
        return _do_leave(run, step)
    if kind == "feature":
        feature = target["record"]
        run.near(feature["id"])
        return _receipt(verb, "completed", target, text=f"{feature.get('name')} yanına geliyorsun. {feature.get('description', '')}".strip())
    if kind == "door":
        door = target["record"]
        run.near(door["id"])
        if verb == "enter":
            place = _place_target(run, target)
            if place:
                return _enter(run, place)
        return _receipt(verb, "completed", target, text=f"{door.get('name')} önüne geliyorsun. {_door_state_text(door)}",
                        door_state=_door_public(door), position="at_door")
    place = _place_target(run, target)
    if place is None:
        return _receipt(verb, "blocked", target, reason="no_target", text="Oraya nasıl gideceğini çıkaramadım.")
    run.game._clear_active_interlocutor()
    if verb == "enter":
        if run.here != place["record"].get("parent_location_id") and run.here != place["id"]:
            front = _arrive_front(run, place, verb="approach")
            if front["status"] != "completed":
                return front
            return _enter(run, place, prefix=front["text"] + " ")
        return _enter(run, place)
    return _arrive_front(run, place, verb=verb)


def _do_leave(run: _Run, step) -> dict[str, Any]:
    record = run.location(run.here)
    parent = record.get("parent_location_id") if record else None
    if not parent or not run.location(parent):
        return _receipt("leave", "completed", None, text="Zaten dışarıdasın.")
    left = record.get("name")
    companions = [npc_statements._npc(run.world, i) for i in run.escorts]
    if not run.game.commit_location_change(parent):
        return _receipt("leave", "blocked", None, reason="exit_refused", text="Dışarı çıkamıyorsun.")
    for npc in companions:
        if npc:
            npc["location"] = parent
    door = run.door_for(record["id"]) if record.get("id") else None
    run.near(door["id"] if door else None)
    return _receipt("leave", "completed", {"id": parent, "label": run.location(parent).get("name")},
                    text=f"{left} içinden çıkıp {run.location(parent).get('name')} sokaklarına dönüyorsun.")


# --- searching ----------------------------------------------------------------
def _places_of_kind(run: _Run, settlement: str, kind: str) -> list[str]:
    return [
        lid for lid, rec in run.world.get("locations", {}).items()
        if isinstance(rec, dict) and rec.get("parent_location_id") == settlement
        and (rec.get("scene_kind") == kind or rec.get("place_kind") == kind)
    ]


def _found_place(run: _Run, record, *, how: str, move: bool, step) -> dict[str, Any]:
    place = {"id": record["id"], "kind": "place", "label": record.get("name"), "record": record,
             "door_id": f"venue-door:{record['id']}" if run.door_for(record["id"]) else None,
             "place_kind": record.get("place_kind") or record.get("scene_kind")}
    result = _arrive_front(run, place, verb="go" if move and step.get("verb") == "go" else "approach", prefix=how)
    result["verb"] = step.get("verb") or "search"
    return result


def _do_search(run: _Run, step, *, move: bool = False) -> dict[str, Any]:
    settlement = _settlement(run.world)
    target = step.get("target")
    tokens = step.get("goal_tokens") or step.get("tokens") or []
    text = " ".join(tokens)
    method = step.get("method")
    how = "Tabelaları takip ederek " if method == "inspect" or any(t.startswith("tabela") for t in step.get("tokens", [])) else ""
    if target and target["kind"] in {"reference", "place"} and not (step.get("other") and target["kind"] == "place"):
        record = _place_target(run, target)
        if record:
            spent = run.spend(600 if run.here == settlement else 0)
            if spent.get("interrupted"):
                return _receipt("search", "blocked", target, reason="interrupted", text="Ararken bir şey yolunu kesiyor.")
            said = ""
            if target["kind"] == "reference" and target["record"].get("said_by"):
                speaker = npc_statements._npc(run.world, target["record"]["said_by"])
                said = f"{_whose(run, speaker)} tarif ettiği yeri arıyorsun. " if speaker else ""
            walk = f"{how}birkaç sokak dolaşıyorsun ve buluyorsun. " if how else "Birkaç sokak dolaşıp buluyorsun. "
            prefix = said + walk[:1].upper() + walk[1:]
            text = _claim_contrast(run, target["record"] if target["kind"] == "reference" else None, record["record"])
            result = _found_place(run, record["record"], how=prefix, move=move, step=step)
            if text:
                result["text"] = f"{result['text']} {text}"
            return result
    if target and target["kind"] == "here" and not step.get("other"):
        return _receipt("search", "completed", target, found=True, text=f"Zaten {target['label']} içindesin.")
    if _ACCESS_GOAL.search(text) or (step.get("detail") and DETAILS[step["detail"]]["class"] == "access"):
        return _search_access(run, step)  # "başka bir giriş": around the building, not to its front door
    if target and target["kind"] in {"npc", "feature", "door"} and not step.get("place_noun"):
        return _do_move(run, step, "approach")
    if step.get("detail"):
        return _observe_detail(run, step, step["detail"])
    noun_kind = step.get("place_noun")
    if noun_kind and settlement:
        noun, kind = noun_kind
        return _search_place_kind(run, step, settlement, noun, kind, move=move, how=how)
    if _ITEM_GOAL.search(text):
        key = f"{run.here}|item|{fold(text)[:40]}"
        searches = run.memory["searches"]
        if key not in searches:
            searches[key] = {"found": False}
        return _receipt("search", "completed", None, found=False,
                        text="Etrafı karıştırıyorsun ama sokakta işine yarayacak bir şey göze çarpmıyor.")
    return _do_wander(run, step, how=how)


def _whose(run: _Run, npc) -> str:
    """'Sera'nın', 'muhafızın': who said it, in the genitive."""
    if living_world.npc_name_known_to_player(npc) and npc.get("name"):
        return run.game._turkish_genitive_form(npc["name"])
    role = (living_world.public_npc_role(npc) or "kişi").strip()
    word = role[:1].lower() + role[1:]
    genitive = run.game._turkish_genitive_form(word).replace("'", "")
    return genitive[:1].upper() + genitive[1:]


def _claim_contrast(run: _Run, ref, record) -> str:
    """The speaker's claim next to what the player actually sees; neither replaces the other."""
    if not ref:
        return ""
    door = run.door_for(record["id"])
    claims = ref.get("claims") or []
    speaker = npc_statements._npc(run.world, ref.get("said_by"))
    if not speaker or not door:
        return ""
    if "acik" in claims and door.get("locked"):
        return f"{_whose(run, speaker)} “açık” dediği yerin kapısı şimdi kilitli."
    return ""


def _search_place_kind(run, step, settlement, noun, kind, *, move, how):
    other = step.get("other")
    refs = [r for r in npc_statements.place_references(run.world, settlement_id=settlement)
            if r.get("place_kind") == kind and not r.get("location_id")]
    spent = run.spend(600)
    if spent.get("interrupted"):
        return _receipt("search", "blocked", None, reason="interrupted", text="Ararken bir şey yolunu kesiyor.")
    if refs:
        ref = refs[-1]
        record = _materialize_reference(run, ref)
        if record:
            speaker = npc_statements._npc(run.world, ref.get("said_by"))
            said = f"{_whose(run, speaker)} bahsettiği yer aklına geliyor. " if speaker else ""
            result = _found_place(run, record, how=f"{said}{how}Birkaç sokak dolaşıyorsun. ", move=move, step=step)
            contrast = _claim_contrast(run, ref, record)
            if contrast:
                result["text"] = f"{result['text']} {contrast}"
            return result
    known = [lid for lid in _places_of_kind(run, settlement, kind) if lid != run.here]
    visited_or_known = set(known) | {run.here}
    if known and not other:
        return _found_place(run, run.location(known[0]), how=how, move=move, step=step)
    here_words = {"su", "bu", "karsidaki", "yandaki", "kosedeki", "ilerideki", "sondaki", "sonundaki", "sagdaki", "soldaki"}
    in_view = bool(here_words & set(step.get("tokens", [])))
    record = _create_venue(run, settlement, name=None, kind=kind, noun=noun,
                           provenance={"source": "player_search" if not in_view else "player_pointed",
                                       "searched_for": noun})
    if record is not None and record["id"] not in visited_or_known and in_view:
        # "Şu kapalı dükkân", "sokağın sonundaki depo": the player points at it; it is right here.
        return _found_place(run, record, how="", move=move, step=step)
    if record is None or record["id"] in visited_or_known:
        return _receipt("search", "completed", None, found=False,
                        text=f"{how}Epey dolaşıyorsun ama bildiklerinden başka bir {noun} bulamıyorsun.".strip())
    return _found_place(run, record, how=f"{how}Birkaç sokak ötede daha önce görmediğin bir yer çıkıyor karşına. ",
                        move=move, step=step)


def _search_access(run: _Run, step) -> dict[str, Any]:
    host = _host_place(run, step)
    if host is None:
        return _receipt("search", "blocked", None, reason="no_building",
                        text="Hangi binanın çevresinde giriş aradığın belli değil; önce o binanın önüne git.")
    key = f"{host['id']}|access"
    searches = run.memory["searches"]
    if key in searches:
        result = searches[key]
        return _receipt("search", "completed", host, repeated_observation=True, found=result["found"],
                        text=result["text"] + " Aynı yerleri yeniden kolaçan etsen de fazlasını bulamıyorsun.")
    spent = run.spend(600)
    if spent.get("interrupted"):
        return _receipt("search", "blocked", host, reason="interrupted", text="Ararken bir şey seni durduruyor.")
    check = _check(run, "Investigation", 12)
    # Whether each entrance exists is decided (and saved) now; only a
    # successful search makes one visible to the player.
    existing = []
    for key_name in ("arka kapi", "avlu", "bodrum", "merdiven"):
        _, decision = _detail_feature(run, key_name, host, materialize=False)
        if decision.get("exists"):
            existing.append(key_name)
    if check["success"] and existing:
        feature, decision = _detail_feature(run, existing[0], host)
        text = f"{host['label']} çevresini dolaşıyorsun ve {feature.get('name')} buluyorsun; {decision.get('state')}."
        found = True
    elif check["success"]:
        text = f"{host['label']} çevresini dikkatle dolaşıyorsun: ön kapıdan başka bir giriş yok."
        found = False
    else:
        text = f"{host['label']} çevresini dolaşıyorsun ama gözüne başka bir giriş çarpmıyor."
        found = False
    searches[key] = {"found": found, "text": text}
    return _receipt("search", "completed", host, found=found, check=_check_public(check), text=text)


_DISCOVERY_KINDS = ("tavern", "market", "temple", "smithy", "bakery", "library", "workshop", "barracks", "stable", "graveyard")


def _do_wander(run: _Run, step, *, how: str = "") -> dict[str, Any]:
    import local_places

    settlement = _settlement(run.world)
    if not settlement or run.here != settlement:
        return _receipt("wander", "completed", None, text="Bulunduğun yerde biraz dolaşıyorsun; yeni bir şey çıkmıyor.")
    spent = run.spend(1200)
    if spent.get("interrupted"):
        return _receipt("wander", "blocked", None, reason="interrupted", text="Dolaşırken bir şey yolunu kesiyor.")
    signs = any(t.startswith("tabela") for t in step.get("tokens", [])) or how
    lead = "Tabelalara göz atarak sokak sokak dolaşıyorsun. " if signs else "Sokak sokak dolaşıyorsun. "
    refs = [r for r in npc_statements.place_references(run.world, settlement_id=settlement) if not r.get("location_id")]
    if refs:
        ref = refs[-1]
        record = _materialize_reference(run, ref)
        speaker = npc_statements._npc(run.world, ref.get("said_by"))
        if record:
            said = f" — {living_world.public_npc_name(speaker)} söz etmişti" if speaker else ""
            result = _found_place(run, record, how=f"{lead}Bir köşede {record.get('name')} tabelasını görüyorsun{said}. ",
                                  move=False, step=step)
            result["verb"] = "wander"
            return result
    order = sorted(_DISCOVERY_KINDS, key=lambda k: _seed(run.world, settlement, "discover", k))
    for kind in order:
        if _places_of_kind(run, settlement, kind):
            continue
        record = _create_venue(run, settlement, name=None, kind=kind,
                               provenance={"source": "player_wander"})
        if record:
            result = _found_place(run, record, how=f"{lead}Yolun seni {record.get('name')} önüne çıkarıyor. ",
                                  move=False, step=step)
            result["verb"] = "wander"
            if kind in local_places.PLACE_KINDS:
                run.local_place = {"kind": kind, "created": True}
            return result
    return _receipt("wander", "completed", None, text=f"{lead}Bildiğin yerlerin dışında dikkatini çeken bir şey yok.")


# --- conditions ------------------------------------------------------------------
def _condition_holds(run: _Run, tokens: list[str] | None, previous: list[dict[str, Any]]) -> bool | None:
    if not tokens:
        return True
    text = " ".join(tokens)
    if any(t in {"degilse", "yoksa"} for t in tokens) and len(tokens) <= 2:
        prior = run.memory.get("_last_condition")
        return None if prior is None else not prior
    door_target = _current_door_target(run, {"target": None})
    door = door_target["record"] if door_target else None
    value = None
    answer = next((r.get("answer") for r in reversed(previous) if r.get("answer")), None)
    answered = None if answer is None else not any(
        marker in answer for marker in ("yanıt gelmiyor", "ne bir ses", "sessiz"))
    if re.search(r"\b(?:acik\w*|acil\w*|acarsa)\b", text) and door and not re.search(r"\bacan\b", text):
        value = bool(door.get("open") or door.get("broken"))
    elif re.search(r"\bkapali\w*\b", text) and door:
        value = not (door.get("open") or door.get("broken"))
    elif re.search(r"\bkilitli\w*\b", text) and door:
        value = bool(door.get("locked"))
    elif re.search(r"\b(?:cevap|yanit|ses)\b.*\b(?:gelmezse|yoksa|vermezse)\b", text):
        value = None if answered is None else not answered
    elif re.search(r"\b(?:acan|cevap|yanit|biri)\b.*\b(?:olursa|verirse|gelirse|acarsa)\b", text):
        value = answered
    elif re.search(r"\bkimse\b.*\b(?:gor\w*sa|bak\w*sa|yoksa)\b", text):
        people = run.game.active_npcs(run.here)
        value = not people
        if people:
            names = ", ".join(living_world.public_npc_name(n) for n in people[:3])
            run.memory["_condition_why"] = f"Etrafta seni görebilecek kişiler var ({names})."
    run.memory["_last_condition"] = value
    return value


# ---------------------------------------------------------------------------
# One bounded model call: choose verbs and candidate IDs, nothing else.
# ---------------------------------------------------------------------------
MODEL_VERBS = ("approach", "go", "enter", "leave", "inspect", "search", "wander", "knock", "call_out", "open",
               "unlock", "force", "close", "read", "touch", "listen", "talk", "hide", "wait", "other")


def model_ground(run: _Run, player_input: str, cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    game = run.game
    options = [{"id": c["id"], "kind": c["kind"], "name": c["label"]} for c in cands][:24]
    ids = [o["id"] for o in options] + ["none"]
    schema = {
        "type": "object",
        "properties": {"steps": {"type": "array", "maxItems": 3, "items": {
            "type": "object",
            "properties": {
                "verb": {"type": "string", "enum": list(MODEL_VERBS)},
                "target_id": {"type": "string", "enum": ids},
                "negated": {"type": "boolean"},
                "conditional": {"type": "boolean"},
                "new_thing": {"type": "string", "maxLength": 40},
            },
            "required": ["verb", "target_id", "negated", "conditional", "new_thing"],
        }}},
        "required": ["steps"],
    }
    prompt = (
        "Bir D&D oyuncusunun Türkçe cümlesini sırayla yaptığı eylemlere ayır. Hikâye yazma, sonuç belirleme. "
        "Her eylem için verb listeden seçilir. target_id yalnız aşağıdaki listeden bir id olabilir; cümle listede "
        "olmayan bir şeyden söz ediyorsa target_id='none' ve new_thing alanına o şeyin kısa Türkçe adını yaz "
        "(ör. 'pencere', 'arka sokak'); yoksa new_thing boş kalsın. Oyuncu bir eylemi yapmayacağını söylüyorsa "
        "negated=true; 'eğer/…sa/…se' ile bir koşula bağlıysa conditional=true. 'han', 'kapı', 'o', 'oraya' gibi "
        "sözleri bağlamdaki en uygun id ile eşleştir. Konuşma/soru ise verb=talk.\n"
        f"Liste: {json.dumps(options, ensure_ascii=False)}\n"
        f"Oyuncunun cümlesi: {player_input}"
    )
    started = time.monotonic()
    try:
        response = game.ollama.chat(
            model="qwen3:8b",
            messages=[{"role": "system", "content": "Return JSON only. You map words to listed IDs; Python owns every fact."},
                      {"role": "user", "content": prompt}],
            format=schema, think=False, options={"temperature": 0.0, "num_predict": 220},
        )
        data = game._extract_json_object(game.ollama_response_content(response))
    except Exception:
        data = None
    run.model_calls += 1
    run.model_ms.append(int((time.monotonic() - started) * 1000))
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list):
        return []
    by_id = {c["id"]: c for c in cands}
    clean = []
    for item in steps[:3]:
        if not isinstance(item, dict) or item.get("verb") not in MODEL_VERBS:
            continue
        target = by_id.get(item.get("target_id"))
        new_thing = fold(item.get("new_thing") or "")
        clean.append({
            "verb": item["verb"], "target": target, "negated": item.get("negated") is True,
            "conditional": item.get("conditional") is True, "new_thing": new_thing,
            "detail": _detail_in(new_thing.split()) if new_thing else None,
            "place_noun": _place_noun_in(new_thing.split()) if new_thing else None,
        })
    return clean


# ---------------------------------------------------------------------------
# Public helpers used by older pipeline exits.
# ---------------------------------------------------------------------------
def clarification_text(session) -> str:
    cands = candidates(session)
    people = [c["label"] for c in cands if c["kind"] == "npc"][:4]
    places = [c["label"] for c in cands if c["kind"] in {"place", "door", "feature", "reference"}][:5]
    parts = []
    if people:
        parts.append("yakınındakiler: " + ", ".join(people))
    if places:
        parts.append("çevrede: " + ", ".join(places))
    hint = ("; ".join(parts)) if parts else "çevrede belirgin bir hedef yok"
    return f"Kime ya da neye yöneldiğini seçemedim ({hint}). Hangisini kastediyorsun?"


def place_hint(session, location_id: str) -> str | None:
    """'Garrick Hanı' typed alone while standing in the street: what and where it is."""
    world = session.world_state
    record = world.get("locations", {}).get(location_id)
    here = world.get("location")
    if not isinstance(record, dict) or location_id == here:
        return None
    if record.get("parent_location_id") not in {here, _settlement(world)}:
        return None
    door = next((d for d in world.get("doors", []) if isinstance(d, dict)
                 and d.get("id") == f"venue-door:{location_id}"), None)
    current = world.get("locations", {}).get(here, {}).get("name", here)
    where = "bu sokakta" if record.get("parent_location_id") == here else "yakınlarda"
    state = f" {_door_state_text(door)}" if door else ""
    return (f"Şu an {current} sokaklarındasın; {record.get('name')} {where}.{state} "
            "Yanına gitmek, kapısını çalmak ya da çevresine bakmak istersen söyle.")


# ---------------------------------------------------------------------------
# The turn
# ---------------------------------------------------------------------------
HANDLERS = {
    "approach": lambda run, s: _do_move(run, s, "approach"),
    "go": lambda run, s: _do_move(run, s, "go"),
    "enter": lambda run, s: _do_move(run, s, "enter"),
    "leave": lambda run, s: _do_leave(run, s),
    "inspect": _do_inspect,
    "search": _do_search,
    "wander": _do_wander,
    "knock": _do_knock,
    "call_out": _do_call_out,
    "open": _do_open,
    "unlock": _do_unlock,
    "force": _do_force,
    "close": _do_close,
    "read": _do_read,
    "listen": _do_listen,
    "touch": _do_touch,
    "wait": lambda run, s: _receipt("wait", "completed", None, text="Olduğun yerde bekliyorsun."),
    "climb": _do_climb,
}

_LOOK_AROUND = re.compile(r"\b(?:etraf\w*|cevre\w*|sahne\w*|sag\w*\s+sol\w*)\b")


def _owned_single_step(step, conditional_seen: bool = False) -> bool:
    """Single acts this module owns: the ones the P6 run showed older owners get wrong."""
    kind = (step.get("target") or {}).get("kind")
    verb = step["verb"]
    if kind == "reference" or step.get("commitment") or step.get("other"):
        return True  # a place someone only mentioned, a promised escort, "another X"
    if verb == "approach" and kind in {"place", "door", "feature", "here"}:
        return True  # walking up to a building / door / detail (not a person)
    if verb == "wander":
        return True  # walking the streets: something real and saved turns up
    if verb == "search":
        # Searching for a rumoured place, "another" one, a back way in: ours.
        # A plain search of the surroundings stays an Investigation check, and
        # a search for a known place keeps the existing local_search receipt.
        text = " ".join(step.get("goal_tokens") or [])
        access = bool(_ACCESS_GOAL.search(text)) or (
            step.get("detail") is not None and DETAILS[step["detail"]]["class"] == "access")
        named_place = kind == "place" and step.get("named")  # "Kızılhan'ı arıyorum" once it exists
        return access or named_place or (step.get("place_noun") is not None and kind is None)
    if verb in {"inspect", "read", "touch"} and (kind == "door" or step.get("part")):
        return True  # the lock or a part of the door, observed once, consistently
    if verb == "unlock" or (verb == "open" and step.get("part") == "lock"):
        return True  # "kilidi açmaya çalışıyorum": tools, a roll, or a concrete obstacle
    if verb in {"go", "approach"} and step.get("outside"):
        return True
    if verb in {"go", "approach"} and kind is None and (step.get("place_noun") or (None, ""))[1] == "generic":
        return True  # "şu eski depoya doğru yürüyorum": a building nobody registered yet
    if verb == "open" and (step.get("part") in {"latch", "handle", "knocker"} or step.get("detail") in _CONTAINERS):
        return True  # the latch, the handle, a crate's lid
    if verb == "climb":
        return True
    if step.get("via_pronoun") and kind in {"place", "door", "feature"}:
        return True  # "oraya gidiyorum": the place in play, not a fresh search
    if verb in {"inspect", "read", "touch"} and step.get("detail") and kind is None and (
            step["detail"] != "pencere" or conditional_seen or step.get("condition")):
        # An unregistered crate, sign or well; a registered feature and the
        # window keep their existing owners (sit mechanics, window findings).
        return True
    if verb == "knock" and conditional_seen:
        return True  # "kapıyı çalıyorum, açan olursa ...": older knock owner drops conditional turns
    return False


def _looks_like_speech(session, player_input: str) -> bool:
    try:
        return bool(session.is_npc_dialogue_input(player_input))
    except Exception:
        return False


def resolve_turn(session, player_input: Any, *, interaction_mode=None, target_id=None,
                 allow_model: bool = True, phase: str = "front", dry_run: bool = False):
    """Resolve a local, physical turn, or return None to leave it to the older owners.

    Deciding never changes saved state: if the turn is left to another owner
    (or this is a dry run) the world is restored exactly as it was.
    dry_run=True returns True when this module would take the turn.
    """
    world = session.world_state
    if not isinstance(world, dict):
        return None
    snapshot = copy.deepcopy(world)
    try:
        decision, payload = _decide(session, player_input, interaction_mode=interaction_mode,
                                    allow_model=allow_model and not dry_run, phase=phase)
    except Exception:
        decision, payload = "defer", None
    if decision == "defer" or dry_run:
        if world != snapshot:
            world.clear()
            world.update(snapshot)
        return None if decision == "defer" else True
    messages_before = len(session.messages)
    try:
        if decision == "info":
            return _finish_info(*payload)
        if decision == "clarify":
            return _finish_clarification(*payload)
        return _execute(*payload)
    except Exception:
        # A bug here must not cost the player the turn or leave half an act
        # in the save: restore everything and let the older owners answer.
        import logging
        logging.getLogger(__name__).exception("grounded_action failed; turn handed back to older owners")
        world.clear()
        world.update(snapshot)
        del session.messages[messages_before:]
        return None


def _decide(session, player_input: Any, *, interaction_mode, allow_model: bool, phase: str):
    defer = ("defer", None)
    if not isinstance(player_input, str) or not player_input.strip() or player_input.strip().startswith("/"):
        return defer
    if interaction_mode in {"say", "ask_dm"}:
        return defer
    world = session.world_state
    if world.get("combat", {}).get("active"):
        return defer
    if session.character.get("current_hp", 0) <= 0 or world.get("player_combat_status") not in (None, "active"):
        return defer
    p = plan(session, player_input)
    if p["steps"] and p["steps"][0].get("not_now"):
        return defer  # "dün kırmayı denedim", "hedefim araştırmak": told, not done now
    steps = [s for s in p["steps"] if not s["reported"] and not s.get("not_now")]
    run = _Run(session, player_input)
    fallback = phase == "fallback"
    # "Marek, ..." - an NPC addressed by name first is speech for the conversation owner.
    head = re.match(r"\s*([^,!?:;]{2,40})[,!:]", player_input)
    if head:
        head_tokens = fold(head.group(1)).split()
        if any(c["kind"] == "npc" and any(n and _phrase_at(n.split(), head_tokens) == 0 for n in c["names"])
               for c in p["candidates"]) and len(head_tokens) <= 3:
            return defer
    if not steps and p["bare_reference"] is not None and not fallback:
        return "info", (run, p["bare_reference"])
    # A sentence with no verb this module knows stays with the older pipeline,
    # whose own intent call reads it; a second call here would exceed the
    # API's two-calls-per-turn budget.
    if not steps:
        return defer
    if p["speech"] or any(s["question"] for s in steps):
        return defer
    first = steps[0]
    for step in steps:
        if step["verb"] in {"go", "approach"} and step["target"] is None and not step["place_noun"] \
                and not step["detail"] and not step.get("outside"):
            step["commitment"] = _implicit_escort_target(session, step)
    if first["verb"] in DEFER_VERBS:
        return defer
    if all(s["negated"] for s in steps):
        return defer
    if any(s.get("foreign_object") for s in steps):
        return defer  # "zili çalıyorum", "kitabı açıyorum", "bir dalı kırıyorum", "iş arıyorum": not ours
    try:
        import exploration
        if exploration._natural_venue_door_action(session, player_input) is not None:
            return defer  # a named venue door already has its owner and contract
    except Exception:
        pass
    if first["target"] is None and first["place_noun"] and not first["other"] \
            and first["verb"] in {"search", "go", "enter", "wander"}:
        kind = first["place_noun"][1]
        settlement = _settlement(world)
        rumoured = any(r.get("place_kind") == kind and not r.get("location_id")
                       for r in npc_statements.place_references(world, settlement_id=settlement))
        if not rumoured and len(steps) == 1 and kind != "generic":
            return defer  # first discovery of an inn / catalogue place keeps its owner (local_search / P3)
    if first["target"] is not None and first["target"]["kind"] == "npc" and first["verb"] in {"go", "approach"}:
        return defer  # walking up to a person: the conversation owner keeps it
    if first["verb"] in {"go", "approach"} and first["target"] is None and not first.get("commitment") \
            and not first["place_noun"] and not first["detail"] and not first.get("outside") \
            and any(t in _PRONOUNS for t in first["tokens"]):
        # "oraya gidiyorum" with nothing said or seen before: ask, naming what is here.
        options = [c for c in p["candidates"] if c["kind"] in {"place", "door", "feature", "reference", "npc"}]
        return "clarify", (run, options[:4])
    if len(steps) == 1 and not _owned_single_step(first, p.get("conditional_seen", False)):
        # One plain act that an existing owner already resolves with its own
        # contract (enter/exit with door checks, knocking, forcing, building
        # inspection with scene-detail proposals): keep it there.
        return defer
    if first["verb"] == "inspect" and first["target"] is None and not (first["detail"] or first["part"]
                                                                    or first["place_noun"]) \
            and (_LOOK_AROUND.search(" ".join(first["tokens"])) or len(first["tokens"]) <= 2):
        return defer  # "etrafa bakıyorum": the scene owner describes the scene
    if first["verb"] in {"go", "enter"} and first["target"] is None and first["place_noun"] \
            and len(steps) == 1 and not first["other"]:
        import local_places
        kind = first["place_noun"][1]
        settlement = _settlement(world)
        if kind in local_places.PLACE_KINDS and settlement and not _places_of_kind(run, settlement, kind) \
                and not any(r.get("place_kind") == kind and not r.get("location_id")
                            for r in npc_statements.place_references(world, settlement_id=settlement)):
            return defer  # first visit to a catalogue place: the local-place owner creates it inside
    unbound = [s for s in steps if s["target"] is None and s["verb"] in TARGET_VERBS
               and not (s["place_noun"] or s["detail"] or s.get("commitment") or s["ambiguous"] or s.get("outside"))
               and not (s["verb"] in {"knock", "open", "unlock", "force", "close"} and _current_door_target(run, s))]
    if unbound and not fallback:
        return defer  # the older owners get their turn first; the fallback pass may ask the model
    if unbound and allow_model:
        suggested = model_ground(run, player_input, p["candidates"])
        actionable = [m for m in suggested if m["verb"] not in {"talk", "other"}]
        if len(actionable) == len(steps):
            for step, hint in zip(steps, actionable):
                if step["target"] is None:
                    step["target"] = hint["target"]
                    step["detail"] = step["detail"] or hint["detail"]
                    step["place_noun"] = step["place_noun"] or hint["place_noun"]
        elif unbound and len(steps) == 1 and actionable:
            hint = actionable[0]
            steps[0].update(target=hint["target"], detail=hint["detail"], place_noun=hint["place_noun"])
    still = [s for s in steps if s["target"] is None and s["verb"] in {"approach", "go", "enter"}
             and not (s["place_noun"] or s["detail"] or s.get("commitment") or s.get("outside"))]
    if still and not steps[0]["ambiguous"]:
        if run.model_calls:
            # The model was asked and could not bind it either: ask the player,
            # naming what is really here, instead of a second pipeline run.
            options = [c for c in p["candidates"] if c["kind"] in {"npc", "place", "door", "feature", "reference"}]
            return "clarify", (run, options[:4])
        return defer  # nothing to bind: older owners (people, travel) keep it
    if steps[0]["ambiguous"]:
        return "clarify", (run, steps[0]["ambiguous"])
    return "execute", (run, steps, p)


def _execute(run: _Run, steps, p) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    stopped = None
    for index, step in enumerate(steps):
        if stopped is not None:
            results.append(_receipt(step["verb"], "not_attempted", step.get("target"), reason="earlier_step_" + stopped))
            continue
        if step["negated"]:
            results.append(_receipt(step["verb"], "declined", step.get("target"), text=""))
            continue
        if step.get("condition"):
            run.memory.pop("_condition_why", None)
            holds = _condition_holds(run, step["condition"], results)
            if holds is not True:
                why = run.memory.pop("_condition_why", "")
                results.append(_receipt(step["verb"], "condition_unmet" if holds is False else "condition_unknown",
                                        step.get("target"),
                                        text=(f"{why} " if why else "") + (
                                            "Koşulun gerçekleşmiyor; bunu yapmıyorsun." if holds is False
                                            else "Koşulun şu an belli değil; bunu yapmıyorsun.")))
                continue
        if index > 0 and step.get("door_by_default"):
            # "...yaklaşıp kulak veriyorum, ses yoksa kilide bakıyorum": "the lock"
            # is the lock of the door the earlier step brought the player to.
            step = {**step, "target": None}
        if step["verb"] == "go" and len(steps) > 1:
            # "Tapınağa varınca kapısına bakıyorum": in a chain, going somewhere
            # means arriving in front of it; entering needs its own "girmek".
            step = {**step, "verb": "approach"}
        handler = HANDLERS.get(step["verb"])
        if step["verb"] == "talk" and index > 0:
            results.append(_receipt("talk", "not_attempted", step.get("target"), reason="speak_next_turn",
                                    text="Ne söyleyeceğini bir sonraki hamlende yazabilirsin."))
            continue
        result = handler(run, step) if handler else None
        if result is not None and steps[index]["verb"] == "go" and step["verb"] == "approach":
            result["verb"] = "go"  # the player's verb; it was carried out as arriving in front
        if result is None:
            result = _receipt(step["verb"], "unsupported", step.get("target"), reason="no_owner",
                              text="Bunu nasıl yapmak istediğini tam çıkaramadım; biraz daha açık anlatır mısın?")
        results.append(result)
        if result["status"] in {"blocked", "failed", "unsupported"}:
            stopped = result["status"]
    return _finish(run, results, p)


def _overall(results) -> str:
    done = [r for r in results if r["status"] == "completed"]
    if results and all(r["status"] in {"completed", "declined"} for r in results) and done:
        return "completed"
    if results and results[0]["status"] in {"blocked", "failed", "unsupported", "condition_unmet", "condition_unknown"} and not done:
        return results[0]["status"]
    if done:
        return "partial"
    return results[0]["status"] if results else "unsupported"


def _bookkeeping(run: _Run, narration: str, action_result: dict[str, Any]) -> dict[str, Any]:
    session = run.session
    flags = run.world.setdefault("flags", {})
    flags["turn_index"] = int(flags.get("turn_index", 0)) + 1
    changed = [key for key in sorted(set(run.before) | set(run.world))
               if key not in {"flags", KEY, npc_statements.KEY} and run.before.get(key) != run.world.get(key)]
    action_result.setdefault("state_changes", changed)
    action_result["direct_response"] = narration
    if run.before.get("location") != run.world.get("location"):
        try:
            session.evaluate_quest_events(run.before, action_result)
        except Exception:
            pass
    session.messages.extend([
        {"role": "user", "content": run.text},
        {"role": "assistant", "content": narration},
    ])
    return {"messages": session.messages, "narration": narration, "model_calls": run.model_calls,
            "action_result": action_result}


def _dedupe_sentences(text: str) -> str:
    """Two steps describing the same thing must not repeat the same sentence."""
    seen, kept = set(), []
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        key = sentence.strip()
        if key and key not in seen:
            seen.add(key)
            kept.append(key)
    return " ".join(kept)


def _finish(run: _Run, results, p) -> dict[str, Any]:
    texts = [r.get("text") for r in results if r.get("text")]
    narration = _dedupe_sentences(" ".join(t.strip() for t in texts if t and t.strip())) or "Bir an duraksıyorsun."
    status = _overall(results)
    primary = next((r for r in results if r["status"] in {"completed", "blocked", "failed"}), results[0])
    action_result: dict[str, Any] = {
        "action": "grounded_action",
        "status": status,
        "success": status in {"completed", "partial"},
        "steps": [{k: v for k, v in r.items() if k != "text"} for r in results],
        "target_id": primary.get("target_id"),
        "target_name": primary.get("target_name"),
        "reason": primary.get("reason"),
        "grounding": {
            "source": "model" if run.model_calls else "deterministic",
            "model_calls": run.model_calls,
            "model_ms": run.model_ms,
            "clauses": [{"verb": s["verb"], "target_id": (s.get("target") or {}).get("id"),
                         "negated": s["negated"], "condition": bool(s.get("condition"))} for s in p["steps"]],
        },
    }
    if len(run.checks) == 1:
        check = run.checks[0]
        action_result.update(_check_public(check))
        action_result["resolution"] = check.get("resolution")
        action_result["action_id"] = (check.get("resolution") or {}).get("action_id")
        action_result["resolution_id"] = (check.get("resolution") or {}).get("resolution_id")
        action_result["success"] = bool(check.get("success")) if status != "blocked" else False
    elif run.checks:
        action_result["checks"] = [_check_public(c) for c in run.checks]
    if run.inspections:
        action_result["inspection"] = run.inspections[-1]
    if run.local_place:
        action_result["local_place"] = run.local_place
    if any(r.get("repeated_observation") for r in results):
        action_result["repeated_observation"] = True
    if run.escorts:
        action_result["companions"] = list(run.escorts)
    return _bookkeeping(run, narration, action_result)


def _finish_info(run: _Run, target: dict[str, Any]) -> dict[str, Any]:
    if target["kind"] in {"place", "door"}:
        place_id = target["id"] if target["kind"] == "place" else target.get("place_id")
        text = place_hint(run.session, place_id) if place_id else None
        if text is None and target["kind"] == "door":
            text = _door_state_text(target["record"]) + " Ne yapmak istersin?"
    elif target["kind"] == "npc":
        text = f"{target['label']} burada. Yanına gidebilir, onunla konuşabilir ya da onu izleyebilirsin."
    elif target["kind"] == "reference":
        ref = target["record"]
        speaker = npc_statements._npc(run.world, ref.get("said_by"))
        who = living_world.public_npc_name(speaker) if speaker else "Biri"
        text = f"{target['label']}: {who} böyle bir yerden söz etmişti; nerede olduğunu henüz görmedin. Aramak istersen söyle."
    else:
        text = f"{target['label']} burada. Ne yapmak istersin?"
    return _bookkeeping(run, text or "Ne yapmak istersin?", {
        "action": "grounded_action", "status": "info", "success": True, "steps": [],
        "target_id": target["id"], "target_name": target["label"], "state_changes": [],
        "grounding": {"source": "deterministic", "model_calls": 0, "bare_reference": True},
    })


def _finish_clarification(run: _Run, options) -> dict[str, Any]:
    labels = [o["label"] for o in options][:4]
    if not labels:
        text = "Neyi kastettiğini seçemedim; çevrende belirgin bir hedef yok. Biraz daha açık anlatır mısın?"
    elif len(labels) == 1:
        text = f"Bunu {labels[0]} için söylediğini mi anlamalıyım?"
    else:
        text = "Hangisini kastediyorsun: " + ", ".join(labels[:-1]) + " ya da " + labels[-1] + "?"
    return _bookkeeping(run, text, {
        "action": "grounded_action", "status": "clarification", "success": False, "steps": [],
        "candidates": [o["id"] for o in options], "state_changes": [],
        "grounding": {"source": "deterministic", "model_calls": run.model_calls},
    })

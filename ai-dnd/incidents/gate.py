"""Reality Gate. One class per proposal. No model retry in any class."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from incidents import categories, proposal as proposal_schema
from incidents.models import REWARD_CLASSES

ACCEPT = "ACCEPT"
NORMALIZE = "NORMALIZE"
HARD_REJECT = "HARD_REJECT"

FACTION_RANKS = ("associate", "member", "agent", "officer", "leader")
# A requested rank at or above this index is a different person, not a downgrade.
_RANK_PREMISE_INDEX = FACTION_RANKS.index("officer")

FORBIDDEN_ROLES = frozenset({
    "deity", "god", "goddess", "ruler", "king", "queen", "lord", "lady",
    "duke", "archmage", "high_priest", "dragon", "demon", "devil", "lich",
    "vampire", "beholder", "giant", "monster", "creature",
})
# Categories whose premise is the reward itself. Removing the reward changes it.
REWARD_PREMISE_CATEGORIES = frozenset({"treasure_find"})

_DEITY = re.compile(r"\b(tanr[ıi]\w*|ilah\w*|deit\w*|gods?|goddess\w*|pantheon)\b", re.IGNORECASE)
_GEOGRAPHY = re.compile(
    r"\b(district|city|town|kingdom|nation|temple|cathedral|castle|citadel|"
    r"mahalle\w*|şehir\w*|kasaba\w*|krall[ıi]\w*|tap[ıi]na[kğ]\w*|kale\w*|saray\w*)\b",
    re.IGNORECASE,
)
_COIN_AMOUNT = re.compile(r"\d[\d.,]*\s*(alt[ıi]n|gold|gp|gümüş|silver|sp|bakır|copper|cp|xp|tp)\b", re.IGNORECASE)
_MAGIC = re.compile(r"(\+\s?\d\b|\bvorpal\b|\bbüyülü\b|\bmagic\w*\b|\benchant\w*\b|\bsihirli\b|\befsun\w*\b)", re.IGNORECASE)
_PUBLISHED_OUTCOME = re.compile(
    r"\b(dragon delves|published adventure|modül (zaten |tamamland)|the (module|adventure) (already|concluded))\b",
    re.IGNORECASE,
)
_HISTORICAL_OVERRIDE = re.compile(
    r"\b(netheril|shadovar).{0,48}(şimdi|current|today|1501|şu an|now (rule|rules|governs))\b",
    re.IGNORECASE,
)
_PROTECTED_DEATH = re.compile(
    r"\b(öldü|öldürüldü|ölmüş|has died|is dead|was (slain|killed|murdered)|murdered)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GateResult:
    outcome: str
    reason: str | None = None
    normalized: dict | None = None
    notes: tuple = field(default_factory=tuple)


def _reject(reason):
    return GateResult(HARD_REJECT, reason=reason)


def _texts(data):
    yield data["premise"]
    yield data["narrative_seed"]
    yield from data["surface_facts"]
    yield from data["hidden_facts"]
    for person in data["people"]:
        yield person["label"]
        if person["name"]:
            yield person["name"]
        if person["backstory"]:
            yield person["backstory"]
    for prop in data["props"]:
        yield prop["label"]
        yield prop["appearance"]
    if data["subscene"]:
        yield data["subscene"]["label"]
        yield data["subscene"]["description"]


def _player_texts(data):
    yield data["premise"]
    yield data["narrative_seed"]
    yield from data["surface_facts"]


def evaluate(envelope, raw_or_data):
    """Classify one proposal against its envelope.

    ``raw_or_data`` is model text or an already decoded dict. Nothing here calls
    a model. A reject is final for the trigger.
    """
    try:
        if isinstance(raw_or_data, str):
            data = proposal_schema.parse(raw_or_data, envelope)
        else:
            data = proposal_schema.validate(
                proposal_schema.complete(copy.deepcopy(raw_or_data), envelope)
            )
    except proposal_schema.ProposalError as error:
        return _reject(error.reason)

    if data["category"] not in envelope["allowed_categories"]:
        return _reject("category")
    drawn = envelope["decisions"].get("category")
    if drawn is not None and data["category"] != drawn:
        return _reject("category")
    allowed_entities = set(envelope["allowed_entity_ids"])
    if any(ref not in allowed_entities for ref in data["existing_refs"]):
        return _reject("entity_ref")
    texts = list(_texts(data))
    folded = [text.casefold() for text in texts]
    for name in envelope["protected_names"]:
        if any(name.casefold() in text for text in folded):
            return _reject("protected_identity")
    if any(_DEITY.search(text) for text in texts):
        return _reject("new_deity")
    for person in data["people"]:
        if person["role"] in FORBIDDEN_ROLES:
            return _reject("forbidden_role")
        if person["role"] not in envelope["allowed_roles"]:
            return _reject("forbidden_role")
    subscene = data["subscene"]
    if subscene is not None:
        if subscene["kind"] not in envelope["allowed_subscene_kinds"]:
            return _reject("geography")
        if _GEOGRAPHY.search(subscene["label"]) or _GEOGRAPHY.search(subscene["description"]):
            return _reject("geography")
    if any(_COIN_AMOUNT.search(text) for text in texts):
        return _reject("mechanical_ownership")
    if any(_MAGIC.search(text) for text in texts):
        return _reject("magic_item")
    if any(_PUBLISHED_OUTCOME.search(text) for text in texts):
        return _reject("adventure_canon")
    if any(_HISTORICAL_OVERRIDE.search(text) for text in texts):
        return _reject("historical_override")
    joined = " ".join(texts)
    if _PROTECTED_DEATH.search(joined):
        for name in envelope["protected_names"]:
            if name.casefold() in joined.casefold():
                return _reject("protected_identity")
    if data["category"] == categories.COMBAT and not envelope.get("allowed_creature_ids"):
        return _reject("combat_bind")
    if data["category"] == categories.GAMBLING and data["reward_class"] != "none":
        return _reject("premise_change")
    if any(token not in categories.CHECK_OWNERS for token in data["check_categories"]):
        return _reject("mechanical_ownership")
    for hidden in envelope["hidden_context"].values():
        needle = hidden.casefold().strip()
        if len(needle) >= 12 and any(needle in text.casefold() for text in _player_texts(data)):
            return _reject("hidden_information")
    if data["persistence_tier"] >= 5:
        return _reject("tier5")

    notes = []
    normalized = copy.deepcopy(data)
    ceiling = envelope["tier_ceiling"]
    if normalized["persistence_tier"] > ceiling:
        normalized["persistence_tier"] = ceiling
        notes.append("persistence_tier")

    wanted = REWARD_CLASSES.index(normalized["reward_class"])
    allowed = REWARD_CLASSES.index(envelope["reward_ceiling"])
    if wanted > allowed:
        if data["category"] in REWARD_PREMISE_CATEGORIES and allowed == 0:
            return _reject("premise_change")
        normalized["reward_class"] = envelope["reward_ceiling"]
        notes.append("reward_class")

    affiliation = normalized["affiliation"]
    if affiliation is not None:
        if affiliation["faction_id"] not in envelope["allowed_faction_ids"]:
            return _reject("faction")
        if affiliation["rank"] not in FACTION_RANKS:
            return _reject("faction")
        requested = FACTION_RANKS.index(affiliation["rank"])
        rank_ceiling = FACTION_RANKS.index(envelope["faction_rank_ceiling"])
        if requested > rank_ceiling:
            if requested >= _RANK_PREMISE_INDEX:
                return _reject("premise_change")
            affiliation["rank"] = envelope["faction_rank_ceiling"]
            notes.append("faction_rank")

    if normalized["significance"] != envelope["decisions"].get("significance", "minor"):
        normalized["significance"] = envelope["decisions"].get("significance", "minor")
        notes.append("significance")

    low, high = envelope["expiry_seconds"]
    if normalized["expiry_hours"] is None:
        expiry = low
    else:
        requested_seconds = normalized["expiry_hours"] * 3600
        expiry = min(max(requested_seconds, low), high)
        if expiry != requested_seconds:
            notes.append("expiry")
    normalized["expiry_seconds"] = expiry
    del normalized["expiry_hours"]

    outcome = NORMALIZE if notes else ACCEPT
    return GateResult(outcome, normalized=normalized, notes=tuple(notes))

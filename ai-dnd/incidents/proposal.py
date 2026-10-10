"""Proposal schema. A proposal is not reality."""

from __future__ import annotations

import json

from incidents.models import REWARD_CLASSES, is_id, is_token

MAX_PROPOSAL_BYTES = 16_384

PROPOSAL_FIELDS = frozenset({
    "category", "significance", "premise", "surface_facts", "hidden_facts",
    "people", "existing_refs", "props", "subscene", "hooks",
    "check_categories", "consequence_classes", "reward_class",
    "persistence_tier", "affiliation", "expiry_hours", "narrative_seed",
})
_PERSON_FIELDS = frozenset({"label", "role", "name", "traits", "backstory"})
_PROP_FIELDS = frozenset({"label", "appearance"})
_SUBSCENE_FIELDS = frozenset({"label", "kind", "description"})
_AFFILIATION_FIELDS = frozenset({"faction_id", "rank"})

MECHANICAL_KEYS = frozenset({
    "hp", "current_hp", "max_hp", "ac", "armor_class", "xp", "experience",
    "gold", "gp", "sp", "cp", "coins", "dc", "cr", "challenge_rating",
    "damage", "attack_bonus", "inventory", "items", "item_stats", "stats",
    "level", "standing", "quest", "quest_id", "objectives", "complete",
    "completed", "reward_amount", "price", "rarity", "bonus", "spell_slots",
    "relationship_score", "companion", "party", "weight", "lifecycle",
    "incident_id", "tier", "trigger_id", "canon_stamp",
})


class ProposalError(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _mechanical_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.casefold() in MECHANICAL_KEYS:
                return True
            if _mechanical_keys(child):
                return True
    elif isinstance(value, list):
        return any(_mechanical_keys(child) for child in value)
    return False


_STRUCTURAL = {
    "existing_refs": [],
    "hooks": [],
    "check_categories": [],
    "consequence_classes": [],
    "people": [],
    "props": [],
    "hidden_facts": [],
    "surface_facts": [],
    "subscene": None,
    "affiliation": None,
    "expiry_hours": None,
    "persistence_tier": 1,
}


def complete(data, envelope=None):
    """Fill omitted structural keys. Does not invent premise text or shorten model text.

    A supplied value is left for the Reality Gate, including values that conflict
    with the envelope. Extra keys, over-long lists, and mechanical keys stay in
    place so validate can hard-reject them. People, props, and subscenes the
    model actually sent are preserved.
    """
    if not isinstance(data, dict):
        return data
    filled = dict(data)
    decisions = envelope.get("decisions") if isinstance(envelope, dict) else None
    if not isinstance(decisions, dict):
        decisions = {}
    if "category" not in filled and isinstance(decisions.get("category"), str):
        filled["category"] = decisions["category"]
    if "significance" not in filled:
        filled["significance"] = decisions.get("significance") or "minor"
    if "reward_class" not in filled:
        filled["reward_class"] = decisions.get("reward_class") or "none"
    for key, default in _STRUCTURAL.items():
        if key not in filled:
            filled[key] = json.loads(json.dumps(default))
    people = filled.get("people")
    if isinstance(people, list):
        filled["people"] = [
            dict(person, **{
                "name": person.get("name", None),
                "traits": person["traits"] if "traits" in person else [],
                "backstory": person.get("backstory", None),
            }) if isinstance(person, dict) else person
            for person in people
        ]
    premise = filled.get("premise")
    if "narrative_seed" not in data and isinstance(premise, str) and premise.strip() and len(premise) <= 300:
        filled["narrative_seed"] = premise
    return filled


def parse(raw, envelope=None):
    """Parse model text once. Returns a validated dict or raises ProposalError."""
    if not isinstance(raw, str):
        raise ProposalError("malformed")
    if len(raw.encode("utf-8")) > MAX_PROPOSAL_BYTES:
        raise ProposalError("oversize")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise ProposalError("malformed") from None
    if _mechanical_keys(data):
        raise ProposalError("mechanical_ownership")
    return validate(complete(data, envelope))


def validate(data):
    if not isinstance(data, dict):
        raise ProposalError("malformed")
    if _mechanical_keys(data):
        raise ProposalError("mechanical_ownership")
    if set(data) != PROPOSAL_FIELDS:
        raise ProposalError("schema")
    if not is_token(data["category"]) or data["significance"] not in ("minor", "notable"):
        raise ProposalError("schema")
    _text(data["premise"], 400)
    _texts(data["surface_facts"], 4, 200)
    _texts(data["hidden_facts"], 3, 200)
    _text(data["narrative_seed"], 300)
    if not isinstance(data["people"], list) or len(data["people"]) > 3:
        raise ProposalError("schema")
    for person in data["people"]:
        if not isinstance(person, dict) or set(person) != _PERSON_FIELDS:
            raise ProposalError("schema")
        _text(person["label"], 80)
        if not is_token(person["role"]):
            raise ProposalError("schema")
        _optional_text(person["name"], 80)
        _optional_text(person["backstory"], 300)
        _tokens(person["traits"], 4)
    if not isinstance(data["existing_refs"], list) or len(data["existing_refs"]) > 6 or any(
        not is_id(item) for item in data["existing_refs"]
    ):
        raise ProposalError("schema")
    if not isinstance(data["props"], list) or len(data["props"]) > 3:
        raise ProposalError("schema")
    for prop in data["props"]:
        if not isinstance(prop, dict) or set(prop) != _PROP_FIELDS:
            raise ProposalError("schema")
        _text(prop["label"], 80)
        _text(prop["appearance"], 300)
    subscene = data["subscene"]
    if subscene is not None:
        if not isinstance(subscene, dict) or set(subscene) != _SUBSCENE_FIELDS:
            raise ProposalError("schema")
        _text(subscene["label"], 80)
        if not is_token(subscene["kind"]):
            raise ProposalError("schema")
        _text(subscene["description"], 300)
    for field, limit in (("hooks", 6), ("check_categories", 4), ("consequence_classes", 4)):
        _tokens(data[field], limit)
    if data["reward_class"] not in REWARD_CLASSES:
        raise ProposalError("schema")
    tier = data["persistence_tier"]
    if type(tier) is not int or not 1 <= tier <= 5:
        raise ProposalError("schema")
    affiliation = data["affiliation"]
    if affiliation is not None and (
        not isinstance(affiliation, dict) or set(affiliation) != _AFFILIATION_FIELDS
        or not is_id(affiliation["faction_id"]) or not is_token(affiliation["rank"])
    ):
        raise ProposalError("schema")
    hours = data["expiry_hours"]
    if hours is not None and (type(hours) is not int or not 0 <= hours <= 720):
        raise ProposalError("schema")
    return data


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ProposalError("schema")


def _optional_text(value, limit):
    if value is not None:
        _text(value, limit)


def _texts(value, count, limit):
    if not isinstance(value, list) or len(value) > count:
        raise ProposalError("schema")
    for item in value:
        _text(item, limit)


def _tokens(value, count):
    if not isinstance(value, list) or len(value) > count or len(set(value)) != len(value) or any(
        not is_token(item) for item in value
    ):
        raise ProposalError("schema")

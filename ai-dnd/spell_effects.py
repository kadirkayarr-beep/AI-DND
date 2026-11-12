"""Dilim 4C.5: the narrative spell layer (design §3 layer 2) and the "not yet" line (layer 3).

Layer 2, first cut: Mage Hand, Minor Illusion, Light, Prestidigitation, cast outside a fight. Python decides and commits:
the spell is one of the caster's cantrips, its components can be given (V: can speak; S: a free hand), no fight is on.
It spends no slot, no action budget and no time, moves no money and no item, and writes one fact
(`world_state["spell_effects_v1"]`: which spell, where, from when until when). The turn narrator tells the fact; it never
rolls, spends or moves anything. Range, components, duration and page come from the PHB 2024 spell index
(`content/rules/phb2024/spells.json`, read by `class_progression.prepared_caster`), never from a model.

A line that would carry money or an item with the spell (K2) is not a narrative cast: it goes on to today's paths (the
economic/bold-act reading, the item and theft owners), where any transfer needs a card or a roll.

Layer 3: a spell the PHB index names, with a casting word, that has neither a resolver (`spell_scope.CATALOG`) nor a
narrative owner, gets a plain Turkish line: it is not in the engine yet; nothing is spent. A narrative spell typed in a
fight gets the same kind of line (the fight's action economy has no owner for it yet).
"""
from __future__ import annotations

import copy
import re
from typing import Any

KEY = "spell_effects_v1"
# Turkish creation names (dnd_2024_rules SPELLS_CATALOG name_tr) and what the fact tells; mechanics stay out of it.
NARRATIVE = {
    "Mage Hand": ("Büyücü Eli", "hayalet bir el belirir ve dediğin işe uzanır"),
    "Minor Illusion": ("Küçük Yanılsama", "bir ses ya da küçük bir hayal belirir"),
    "Light": ("Işık", "dokunduğun nesne ışık saçmaya başlar"),
    "Prestidigitation": ("Hokkabazlık", "küçük, zararsız bir büyü numarası olur"),
}
_ALIASES = (("mage hand", "Mage Hand"), ("buyucu eli", "Mage Hand"), ("minor illusion", "Minor Illusion"),
            ("kucuk yanilsama", "Minor Illusion"), ("prestidigitation", "Prestidigitation"),
            ("hokkabazlik", "Prestidigitation"))
# "Light" and "Işık" are everyday words: only with a casting word next to them are they the spell.
_LIGHT = re.compile(r"\b(?:isik|light)\s+(?:buyu\w*|spell|cantrip)\b|\bcast(?:ing)?\s+(?:the\s+)?light\b")
_CAST_WORD = re.compile(r"\bcast(?:s|ing)?\b|\bbuyu(?:su\w*|yu|yle|nu)?\b")  # "büyücü" (a wizard) is no casting word
_QUESTION = re.compile(r"\?|\b(?:nedir|nasil|what|how|describe|anlat)\b")
# Negated, wished, asked or weighed forms are no cast: "yapmak istemiyorum", "yapsam mı", "kullanmalı mıyım", "keşke".
_NEGATED = re.compile(
    r"\b(?:not|don't|dont|never|degil|should|would|could|shall|if|maybe|acaba|keske|eger|belki)\b"
    r"|\bm[iu](?:s\w*|y\w*)?\b|istem(?:iyor|em|ez|edi|eyece)|\w+(?:sam|sem|saydim|seydim)\b|\w+m[ae]li\b"
    r"|\b(?:kullan|yap|at|dene)m(?:a\b|iyor|am\b|ayacag|adi)")
# K2: money, an item, a container, a hand/bag/pocket to put something in, or a taking verb is no narrative cast:
# when it is not plainly a pure effect, the line goes on to today's paths (economic, theft, item owners).
_TRANSFER = re.compile(
    r"\b(?:para\w*|kese\w*|altin\w*|gumus\w*|bakir\w*|sikke\w*|cuzdan\w*|cep\w*|ceb\w*|bozuk\w*|coin\w*|purse\w*"
    r"|gold|silver|copper|wallet\w*|pocket\w*|pouch\w*|bag|bags)\b"
    r"|\b(?:mucevher\w*|yuzu\w*|hancer\w*|esya\w*|anahtar\w*|sandik\w*|hazine\w*|ganimet\w*|cant\w*|avuc\w*"
    r"|ring|rings|jewel\w*|gem|gems|item\w*|key|keys|dagger\w*|loot\w*|treasure\w*|chest\w*)\b"
    r"|\b(?:kendime|bana|elime|ustume)\b|\b(?:to|toward|towards)\s+me\b|\binto\s+my\b|\bmy\s+hand\b"
    r"|\b(?:cal(?:ar|iyor|ip|mak|acag|dim)\w*|asir\w*|yuru(?:t|d)\w*|al(?:iyor|ip|ir|mak|acag|dim)\w*|getir\w*"
    r"|ver(?:iyor|ir|mek)\w*|kap(?:iyor|ar|ip|mak|tim|acag)\w*|cek(?:iyor|ip|er|mek|tim)\w*"
    r"|koy(?:uyor|ar|up|mak|dum)\w*|topla\w*|steal\w*|stole|pickpocket\w*|pilfer\w*|snatch\w*|grab\w*"
    r"|take|takes|taking|took|fetch\w*|bring\w*|give|giving|carry\w*|carries)\b|\bpick(?:s|ing|ed)?\s+up\b")
_DURATION = {"1 minute": 60, "1 hour": 3600, "Up to 1 hour": 3600}
_DURATION_TR = {"1 minute": "bir dakika sürer", "1 hour": "bir saat sürer", "Up to 1 hour": "en çok bir saat sürer"}
_FIELDS = {"id", "spell_id", "kind", "location_id", "cast_second", "until_second"}


def _fold(text: Any) -> str:
    import spells
    return spells.fold_text(str(text))


def _source(spell_id: str) -> dict[str, Any]:
    from class_progression.prepared_caster import _source_spells
    return _source_spells()[spell_id]


def _range_tr(value: str) -> str:
    if value == "Touch":
        return ""  # the fact's own words say "dokunduğun"
    feet = re.fullmatch(r"(\d+) feet", value)
    return f"{feet.group(1)} fit içinde" if feet else value


def named(message: Any) -> tuple[str, str] | None:
    """Read only, words alone: ("narrative", spell) or ("not_yet", spell) for a casting line, else None.

    A question, a negated line or a line that would move money or an item is no cast (None); a line naming a spell with a
    resolver is the resolver's (None)."""
    import spell_scope
    import spells
    folded = _fold(message)
    if _QUESTION.search(folded) or _NEGATED.search(folded):
        return None
    if any(re.search(rf"(?<![a-z0-9]){re.escape(_fold(alias))}(?![a-z0-9])", folded)
           for alias in [*spell_scope.CATALOG, *spell_scope.ALIASES]):
        return None
    hits = {spell for alias, spell in _ALIASES if re.search(rf"(?<![a-z0-9]){alias}(?![a-z0-9])", folded)}
    if _LIGHT.search(folded):
        hits.add("Light")
    if hits:
        if len(hits) != 1 or _TRANSFER.search(folded):
            return None
        return "narrative", hits.pop()
    if not _CAST_WORD.search(folded):
        return None
    for alias, spell in spells._UNSUPPORTED_ALIASES:
        if spell not in NARRATIVE and re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", folded):
            return "not_yet", spell
    for spell in sorted(_manifest_names(), key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(_fold(spell))}(?![a-z0-9])", folded):
            return "not_yet", spell
    return None


# What a narrative cast never does (the engine wrote only the fact): coin, an item in the player's hand/bag/pocket,
# finding or winning something, healing, damage. A narrator line that says so is replaced by the Python line.
_STATE_CLAIM = re.compile(
    r"\b(?:altin\w*|gumus\w*|bakir\w*|sikke\w*|para\w*|kese\w*|coin\w*|gold|silver|copper|purse\w*)\b"
    r"|\b(?:cebin\w*|cebe|cantan\w*|avucun\w*|kesene|senin\w*dir|senin\s+olur\w*|yours|pocket\w*)\b"
    r"|\belinde\s+kal\w*|\beline\s+(?:gec|al|dus)\w*|\bele\s+gecir\w*|\byour\s+(?:palm|hand|hands|bag|pack|pouch)\b"
    r"|\b(?:bul(?:ur|up|dun|ursun|uyorsun)|kazan\w*|alirsin|edinirsin)\b|\b(?:find|found|gain\w*|receive\w*|earn\w*)\b"
    r"|\byara\w*\s+(?:kapan|iyiles|gec)\w*|\biyiles\w*|\bcan\w*\s+(?:dol|art|yenilen)\w*|\bcan\s+puan\w*"
    r"|\b(?:heal\w*|wound\w*|hit\s+points?)\b|\bhasar\w*|\bdamage\w*")


def claims_state_change(text: Any) -> bool:
    """True when a narrator line for a narrative cast claims coin, an item taken, healing or damage (none happened)."""
    return isinstance(text, str) and bool(_STATE_CLAIM.search(_fold(text)))


def _manifest_names() -> frozenset[str]:
    import spell_registry
    return frozenset(name for name in spell_registry._manifest_spells()
                     if name not in NARRATIVE and spell_registry.spell_state(name) == "catalog_only")


def current(world: dict[str, Any]) -> list[dict[str, Any]]:
    facts = world.get(KEY)
    return facts if isinstance(facts, list) else []


def active(world: dict[str, Any]) -> list[dict[str, Any]]:
    """The facts still running at the campaign second (read only)."""
    import spell_scope
    now = spell_scope.clock_second(world)
    return [fact for fact in current(world) if fact["until_second"] > now]


def validate_saved(world: dict[str, Any]) -> None:
    if KEY not in world:
        return
    facts = world[KEY]
    if not isinstance(facts, list) or len(facts) > len(NARRATIVE):
        raise ValueError("Invalid saved spell effects.")
    seen = set()
    for fact in facts:
        if (not isinstance(fact, dict) or set(fact) != _FIELDS or fact["spell_id"] not in NARRATIVE
                or fact["spell_id"] in seen or fact["kind"] != "narrative"
                or not isinstance(fact["id"], str) or not fact["id"]
                or not isinstance(fact["location_id"], str) or not fact["location_id"]
                or type(fact["cast_second"]) is not int or fact["cast_second"] < 0
                or type(fact["until_second"]) is not int or fact["until_second"] <= fact["cast_second"]):
            raise ValueError("Invalid saved spell effects.")
        seen.add(fact["spell_id"])


def _not_cast(line: str, spell_id: str, reason: str) -> dict[str, Any]:
    return {"action_result": {"action": "narrative_spell", "status": "unsupported", "success": False,
                              "spell": spell_id, "slot_spent": False, "reason": reason, "state_changes": [],
                              "direct_response": line},
            "narration": line}


def resolve(session: Any, reading: tuple[str, str]) -> dict[str, Any]:
    """The engine's answer to a `named` reading: a committed fact, or a truthful line that nothing was cast."""
    import spell_preparation
    import spell_scope
    import weapon_attack as attacks
    kind, spell_id = reading
    world = session.world_state
    if kind == "not_yet":
        return _not_cast(f"{spell_id} büyüsü henüz motorda yok; büyü yapılmadı, yuvan ve eylemin harcanmadı.",
                         spell_id, "spell_not_in_engine")
    tr = NARRATIVE[spell_id][0]
    if world.get("combat", {}).get("active"):
        return _not_cast(f"{tr} ({spell_id}) savaşta henüz motorda yok; büyü yapılmadı, eylemin harcanmadı.",
                         spell_id, "narrative_spell_in_combat")
    state = world.get("spellcasting_v1")
    spell_scope.validate(state, session.character)
    if state is None or spell_id not in state["cantrips"]:
        return _not_cast(f"{tr} ({spell_id}) bildiğin büyüler arasında değil; büyü yapılmadı.",
                         spell_id, "spell_not_available")
    import combat_lifecycle
    if combat_lifecycle.player_incapacitated(session.character, world):
        return _not_cast(f"Şu an {tr} ({spell_id}) yapamazsın; büyü yapılmadı.", spell_id, "player_incapacitated")
    source = _source(spell_id)
    parts = source["components"]
    conditions = attacks.conditions(session, "player", session.character)
    if parts["v"] and conditions & {"silenced", "silence", "cannot_speak", "petrified"}:
        return _not_cast(f"{tr} ({spell_id}) için konuşabilmen gerekir; büyü yapılmadı.", spell_id,
                         "spell_components_unavailable")
    if parts["s"] and not any(value is None for value in attacks.equipment(session, "player", session.character).values()):
        return _not_cast(f"{tr} ({spell_id}) için bir elinin boş olması gerekir; büyü yapılmadı.", spell_id,
                         "spell_components_unavailable")
    now = spell_scope.clock_second(world)
    fact = {"id": f"{spell_id.casefold().replace(' ', '_')}-{now}", "spell_id": spell_id, "kind": "narrative",
            "location_id": str(world.get("location") or "unknown"), "cast_second": now,
            "until_second": now + _DURATION[source["duration"]]}
    # A new cast of the same spell replaces the earlier one; finished facts are dropped.
    world[KEY] = [entry for entry in active(world) if entry["spell_id"] != spell_id] + [fact]
    validate_saved(world)
    # D-038: casting ends a Long Rest preparation window (combat start does the same); creation/migration/level-up
    # windows wait for their list, as before.
    spell_preparation.close_window(session)
    where = _range_tr(source["range"])
    line = (f"{tr} ({spell_id}): {where + ' ' if where else ''}{NARRATIVE[spell_id][1]}; büyü "
            f"{_DURATION_TR[source['duration']]}. Yuva harcanmaz.")
    return {"action_result": {"action": "narrative_spell", "status": "resolved", "success": True, "spell": spell_id,
                              "slot_spent": False, "spell_effect": copy.deepcopy(fact),
                              "range": source["range"], "duration": source["duration"],
                              "state_changes": [f"world.{KEY}"], "direct_response": line},
            "narration": line}

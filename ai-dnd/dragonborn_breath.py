"""Dragonborn Draconic Ancestry and Breath Weapon (PHB 2024 p.187; D-233).

`character["draconic_ancestry"]` (the dragon chosen once) and `character["breath_weapon_spent"]` (uses spent since the
last Long Rest) are additive, like `fighter_uses`: a save without them chose nothing and spent nothing. A spent counter,
not a remaining value, lets a higher Proficiency Bonus add a use without refilling the others.

Breath Weapon (PHB 2024): when you take the Attack action on your turn, you can replace one of its attacks with a 15-foot
Cone or a 30-foot Line 5 feet wide. Each creature in the area makes a Dexterity saving throw (DC 8 + Constitution
modifier + Proficiency Bonus): the ancestry's damage type, 1d10 on a failure and half on a success; 2d10 at level 5,
3d10 at 11, 4d10 at 17. The damage is rolled once for the area (dice guide 5.2, 9.E). Uses equal the Proficiency
Bonus; all return on a Long Rest. Draconic Ancestry also gives Resistance to that damage type.

The engine knows distances but not facing, so the area holds the creature the breath is aimed at, inside the shape's
reach; whether anyone else stands in it is unknown and is never guessed (K01, effect_targeting).
"""
from __future__ import annotations

from typing import Any

import action_economy
import effect_targeting
import weapon_attack
from combat_lifecycle import CombatRequestError

ANCESTRY_KEY = "draconic_ancestry"
SPENT_KEY = "breath_weapon_spent"
SPECIES = "Dragonborn"
# PHB 2024 Draconic Ancestors table.
ANCESTRIES = {"black": "acid", "blue": "lightning", "brass": "fire", "bronze": "lightning", "copper": "acid",
              "gold": "fire", "green": "poison", "red": "fire", "silver": "cold", "white": "cold"}
SHAPES = {"cone": 15, "line": 30}
_SHAPE_TR = {"cone": "15 fit koni", "line": "30 fit hat"}
_TYPE_TR = {"acid": "asit", "lightning": "yıldırım", "fire": "ateş", "poison": "zehir", "cold": "soğuk"}
_SOURCE = "PHB 2024 p.187 Dragonborn: Breath Weapon"


def is_dragonborn(character: dict[str, Any]) -> bool:
    return character.get("species", character.get("race")) == SPECIES


def maximum(character: dict[str, Any]) -> int:
    value = character.get("proficiency_bonus", 2)
    return value if type(value) is int and value > 0 else 0


def uses_left(character: dict[str, Any]) -> int:
    return max(0, maximum(character) - character.get(SPENT_KEY, 0))


def dice(level: int) -> int:
    return 1 + sum(level >= threshold for threshold in (5, 11, 17))


def resistance(character: dict[str, Any]) -> str | None:
    """The damage type a Dragonborn resists, or None before an ancestry is chosen."""
    return ANCESTRIES.get(character.get(ANCESTRY_KEY)) if is_dragonborn(character) else None


def validate_saved(player: dict[str, Any]) -> None:
    ancestry = player.get(ANCESTRY_KEY)
    if ancestry is not None and (not is_dragonborn(player) or ancestry not in ANCESTRIES):
        raise ValueError("Kayıt ejderha soyu seçimi geçersiz.")
    if SPENT_KEY in player:
        spent = player[SPENT_KEY]
        if not is_dragonborn(player) or type(spent) is not int or not 0 <= spent <= maximum(player):
            raise ValueError("Kayıt Nefes Silahı kullanımı geçersiz.")


def long_rest(character: dict[str, Any]) -> None:
    character.pop(SPENT_KEY, None)


def choose_ancestry(session: Any, ancestry: Any) -> tuple[str, dict[str, Any]]:
    character = session.character
    if not is_dragonborn(character):
        raise ValueError("Bu tür yeteneği karakterin için kullanılamaz.")
    if session.world_state.get("combat", {}).get("active"):
        raise ValueError("Ejderha Soyu çatışma sırasında seçilemez.")
    if ancestry not in ANCESTRIES:
        raise ValueError("Geçerli bir Ejderha Soyu seç.")
    if character.get(ANCESTRY_KEY) is not None:
        raise ValueError("Ejderha Soyu zaten seçilmiş; kampanya içinde değiştirilemez.")
    character[ANCESTRY_KEY] = ancestry
    return "Ejderha Soyu seçimi kaydedildi.", {"draconic_ancestry": ancestry, "damage_type": ANCESTRIES[ancestry]}


def _attack_left(session: Any) -> bool:
    """An attack of the Attack action is still open: the next of one already taken, or a fresh Action for it."""
    ongoing = action_economy.ensure(session)["player"].get("attack_action")
    if ongoing and ongoing.get("remaining_attacks", 0) > 0:
        return True
    try:
        action_economy.action_slot(session, "player", "attack")
    except CombatRequestError:
        return False
    return True


def _spend_one_attack(session: Any) -> None:
    """One attack of the Attack action: the next of an Attack action already taken, else a new one (as attack_step)."""
    resources = action_economy.ensure(session)["player"]
    ongoing = resources.get("attack_action")
    if ongoing and ongoing.get("remaining_attacks", 0) > 0:
        ongoing["remaining_attacks"] -= 1
        return
    slot = action_economy.action_slot(session, "player", "attack")
    limit = slot["restrictions"].get("max_attacks", 1) if slot else action_economy.attacks_per_action(session, "player")
    if type(limit) is not int or limit < 1:
        action_economy.fail("invalid_attack_allowance", "Invalid server-defined attacks-per-Action.")
    action_economy.consume_action(session, "player", "attack")
    resources["attack_action"] = {"remaining_attacks": limit - 1, "total_attacks": limit, "action_resource_cost": 1}


def breathe(session: Any, shape: Any, target_id: Any) -> tuple[str, dict[str, Any]]:
    """Validate everything, then spend the attack and the use, roll once, and apply each target's save."""
    import spell_scope
    character = session.character
    if not is_dragonborn(character):
        raise ValueError("Bu tür yeteneği karakterin için kullanılamaz.")
    damage_type = ANCESTRIES.get(character.get(ANCESTRY_KEY))
    if damage_type is None:
        raise ValueError("Önce Ejderha Soyunu seç; nefesin hasar türü ondan gelir.")
    if not session.world_state.get("combat", {}).get("active"):
        raise ValueError("Nefes Silahı savaşta, Saldırı eyleminin bir saldırısı yerine kullanılır.")
    action_economy.validate_actor(session)
    if uses_left(character) <= 0:
        raise ValueError("Nefes Silahı uzun dinlenmeye kadar kullanıldı.")
    if shape is not None and shape not in SHAPES:
        raise ValueError("Nefes için koni ya da hat seç.")
    reach = {name: effect_targeting.eligible_effect_targets(
        session, "player", effect_targeting.EffectSpec(f"breath_weapon_{name}", feet, _SOURCE)) for name, feet in SHAPES.items()}
    if target_id is None:
        aimed = set(reach["line"])
        if len(aimed) != 1:
            raise ValueError("Nefesi kime yönelttiğini seç.")
        target_id = aimed.pop()
    if shape is None:  # not said: the shorter shape that reaches the target (the Cone), else the Line
        shape = "cone" if target_id in reach["cone"] else "line"
    if target_id not in reach[shape]:
        raise ValueError(f"Nefesin ({_SHAPE_TR[shape]}) o hedefe ulaşmıyor.")
    target = next(npc for npc in session.world_state["npcs"] if isinstance(npc, dict) and npc.get("id") == target_id)
    try:
        spell_scope._save_bonus_known(target, "dexterity")  # the save owner's zero fallback is never taken without evidence
    except CombatRequestError:
        raise ValueError("Hedefin Çeviklik kurtulma zarı bilinmiyor; nefes ona yöneltilemez.") from None
    if not _attack_left(session):
        raise ValueError("Bu turda Saldırı eylemine yer kalmadı; Nefes Silahı bir saldırının yerine kullanılır.")
    _spend_one_attack(session)
    character[SPENT_KEY] = character.get(SPENT_KEY, 0) + 1
    count = dice(character.get("level", 1))
    rolled = session.roll_damage(10, count, 0)
    dc = 8 + character.get("constitution_mod", 0) + character.get("proficiency_bonus", 2)
    resolution = weapon_attack.save(session, target_id, ["dexterity"], dc,
                                    effect_context={"source": "breath_weapon", "severity": "harmful"})
    saved = resolution["outcome"] != "FAILURE"
    mitigation = weapon_attack.mitigate(session, target_id, damage_type, rolled // 2 if saved else rolled)
    session.apply_npc_damage(target, mitigation["final_damage"])
    session._combat_end_if_decided()
    effects = {"trait": "breath_weapon", "shape": shape, "area_ft": SHAPES[shape], "damage_type": damage_type,
               "save_dc": dc, "damage_dice": f"{count}d10", "raw_damage": rolled, "uses_remaining": uses_left(character),
               "targets": [{"target_id": target_id, "saved": saved, "resolution": resolution,
                            "damage": mitigation["final_damage"], "mitigation": mitigation,
                            "target_hp_after": target.get("current_hp")}]}
    import living_world
    name = living_world.public_npc_name(target)
    message = (f"Nefes Silahı ({_SHAPE_TR[shape]}): {name} {'kurtulma zarını geçti' if saved else 'kurtulma zarında kaldı'};"
               f" {mitigation['final_damage']} {_TYPE_TR[damage_type]} hasarı.")
    return message, effects


def named(session: Any, text: str) -> bool:
    """A Dragonborn's own words for the breath in a fight; the engine owns them, not the model's reading."""
    import re
    if not is_dragonborn(session.character) or not session.world_state.get("combat", {}).get("active"):
        return False
    folded = session._normalize_turkish_typos(text)
    # "sal" only as salmak's own forms (folded: salıyor, salıver, salar, salma, saldı, salacak, bare "sal"); never the head
    # of another word: "nefes nefese saldırıyorum / sallıyorum / salonda / salata / salgın" is not the breath.
    return bool(re.search(r"nefes\s*silah|breath\s*weapon|ejderha\s*nefes|"
                          r"nefes\w*\s+(?:puskurt|ufle|sal(?:iyor|iver|ar|ma|di(?!r)|ac|\b))", folded))


def shape_in(text: str) -> str | None:
    import re
    if re.search(r"\b(?:hat|hatt\w*|cizgi\w*|line)\b", text):
        return "line"
    if re.search(r"\b(?:koni\w*|cone)\b", text):
        return "cone"
    return None

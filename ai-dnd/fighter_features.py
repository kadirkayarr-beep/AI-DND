"""Fighter 1-5 feature effects on the existing owners; it holds rules and two spent counters, not a budget or a resource system.

Values only (PHB 2024 PDF 90/91 Second Wind, Action Surge, Tactical Shift; PDF 95 Champion; PDF 208/209 Fighting Style feats).
`character["fighter_uses"]` = {"second_wind_spent", "action_surge_spent"} is additive, like `hit_dice`: a save without it spent
nothing, and a counter (not a remaining value) makes table growth add a use without refilling the others.
Second Wind's maximum and healing follow the APPLIED Fighter level; a level granted by XP alone changes nothing here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import character_progression as core
from combat_lifecycle import CombatRequestError

KEY = "fighter_uses"
TACTICAL_MIND = "tactical_mind"
TACTICAL_MIND_LEVEL = 2
TACTICAL_MIND_DIE = 10
STYLE = "fighting_style"
_FIELDS = {"second_wind_spent", "action_surge_spent"}
SUBCLASS = "champion"
ACTION_SURGE_LEVEL = 2
ACTION_SURGE_USES = 1
TACTICAL_SHIFT_LEVEL = 5
CHAMPION_LEVEL = 3
SECOND_WIND_DIE = 10
IMPROVED_CRITICAL = 19
ARCHERY_ATTACK_BONUS = 2
DUELING_DAMAGE_BONUS = 2
GREAT_WEAPON_MINIMUM = 3

# Every Fighting Style feat of the book: a stored one is a valid record. Only the applied ones are offered at creation.
KNOWN_STYLES = frozenset({"Archery", "Blind Fighting", "Defense", "Dueling", "Great Weapon Fighting", "Interception", "Protection",
                          "Thrown Weapon Fighting", "Two-Weapon Fighting", "Unarmed Fighting"})
APPLIED_STYLES = frozenset({"Archery", "Defense", "Dueling", "Great Weapon Fighting", "Two-Weapon Fighting"})


def fighter_level(character: Any) -> int | None:
    """The applied Fighter level, or None when this is not a verified Fighter 1-5 (at 3+ the Champion choice must be retained)."""
    if not isinstance(character, dict) or character.get("class") != "Fighter":
        return None
    applied, raw = character.get("progression_level", 1), character.get("level")
    if type(applied) is not int or type(raw) is not int or not 1 <= applied <= 5 or not applied <= raw <= 20:
        return None
    if applied >= CHAMPION_LEVEL and character.get("subclass_id") != SUBCLASS:
        return None
    return applied


def second_wind_maximum(level: int) -> int:
    value = core.table("Fighter")["levels"][str(level)]["second_wind"]
    if type(value) is not int or value < 1:
        raise ValueError("Invalid Second Wind table value.")
    return value


def action_surge_maximum(level: int) -> int:
    return ACTION_SURGE_USES if level >= ACTION_SURGE_LEVEL else 0


def validate_saved(player: dict[str, Any]) -> None:
    """Runs for every class on every save: these fields exist only on a verified Fighter, with counts its applied level allows."""
    style = player.get(STYLE)
    if style is not None and (player.get("class") != "Fighter" or type(style) is not str or style not in KNOWN_STYLES):
        raise ValueError("Kayıt Fighting Style alanı geçersiz.")
    if KEY not in player:
        return
    level, uses = fighter_level(player), player[KEY]
    if (level is None or type(uses) is not dict or set(uses) != _FIELDS
            or any(type(value) is not int or value < 0 for value in uses.values())
            or uses["second_wind_spent"] > second_wind_maximum(level)
            or uses["action_surge_spent"] > action_surge_maximum(level)):
        raise ValueError("Kayıt Fighter kullanım alanı geçersiz.")


def _uses(character: dict[str, Any]) -> dict[str, int]:
    return dict(character.get(KEY) or {"second_wind_spent": 0, "action_surge_spent": 0})


def _spend(character: dict[str, Any], field: str) -> None:
    uses = _uses(character)
    uses[field] += 1
    character[KEY] = uses


def rest_recovery(session: Any, kind: str) -> None:
    """Short Rest: one Second Wind and Action Surge back. Long Rest: all. Nothing is written for a character that spent nothing."""
    character = session.character
    if KEY not in character:
        return
    uses = _uses(character)
    uses["second_wind_spent"] = max(0, uses["second_wind_spent"] - 1) if kind == "short_rest" else 0
    uses["action_surge_spent"] = 0
    character[KEY] = uses


def _incapacitated(session: Any) -> bool:
    import barbarian_rage
    return barbarian_rage._incapacitated(session.character, session.world_state)


def _turn_reason(session: Any, prefix: str) -> str | None:
    combat = session.world_state.get("combat", {})
    if not combat.get("active") or combat.get("current_actor_id") != "player":
        return f"{prefix}_current_combat_turn_required"
    if _incapacitated(session):
        return f"{prefix}_incapacitated"
    if combat.get("turn_resources", {}).get("player", {}).get("opportunity"):
        return "reaction_pending"  # pure projection, no ensure() mutation
    return None


def _second_wind_reason(session: Any) -> str | None:
    level = fighter_level(session.character)
    if level is None:
        return "second_wind_not_available"
    reason = _turn_reason(session, "second_wind")
    if reason:
        return reason
    if session.world_state["combat"].get("turn_resources", {}).get("player", {}).get("bonus_action_spent"):
        return "bonus_action_spent"
    if _uses(session.character)["second_wind_spent"] >= second_wind_maximum(level):
        return "second_wind_uses_exhausted"
    return None


def _action_surge_reason(session: Any) -> str | None:
    level = fighter_level(session.character)
    if level is None or level < ACTION_SURGE_LEVEL:
        return "action_surge_not_available"
    reason = _turn_reason(session, "action_surge")
    if reason:
        return reason
    if _uses(session.character)["action_surge_spent"] >= action_surge_maximum(level):
        return "action_surge_uses_exhausted"
    return None


def tactical_mind_reason(session: Any) -> str | None:
    """The bounded route: an immediate out-of-combat check, with a Second Wind use left (the two features share that pool)."""
    level = fighter_level(session.character)
    if level is None or level < TACTICAL_MIND_LEVEL:
        return "tactical_mind_not_available"
    if session.world_state.get("combat", {}).get("active"):
        return "tactical_mind_immediate_check_only"
    if _uses(session.character)["second_wind_spent"] >= second_wind_maximum(level):
        return "tactical_mind_uses_exhausted"
    return None


def require_tactical_mind(session: Any) -> None:
    reason = tactical_mind_reason(session)
    if reason:
        raise CombatRequestError(reason, "Tactical Mind is unavailable: " + reason, 400)


def tactical_mind_roll(session: Any) -> int:
    return session.rng.randint(1, TACTICAL_MIND_DIE)


def spend_tactical_mind(session: Any) -> None:
    """Only a check the d10 turned into a success expends the use; healing never happens on this route."""
    _spend(session.character, "second_wind_spent")


@dataclass(frozen=True)
class TacticalMindEvidence:
    """At-roll in-process provenance, never a request, save or model field."""
    action_id: str | None
    resolution_id: str | None
    skill: str
    roll: int | None
    resolution_json: str


def _canonical(resolution: Any) -> str:
    return json.dumps(resolution, sort_keys=True, separators=(",", ":"))


def record_tactical_mind(result: dict[str, Any]) -> TacticalMindEvidence:
    resolution = result["resolution"]
    return TacticalMindEvidence(resolution["action_id"], resolution["resolution_id"], result["skill"],
                                result["tactical_mind_roll"], _canonical(resolution))


def tactical_mind_annotation(evidence: Any, action_result: Any) -> dict[str, Any]:
    """Verify a completed live roll; a feature label alone never authorizes the extra d10 in a public result."""
    if type(evidence) is not TacticalMindEvidence or type(action_result) is not dict:
        raise ValueError("Missing trusted Tactical Mind roll evidence.")
    resolution = action_result.get("resolution")
    if (not evidence.action_id or not evidence.resolution_id or action_result.get("action") != "skill_check"
            or action_result.get("skill") != evidence.skill or action_result.get("action_id") != evidence.action_id
            or action_result.get("resolution_id") != evidence.resolution_id
            or action_result.get("tactical_mind_roll") != evidence.roll or _canonical(resolution) != evidence.resolution_json):
        raise ValueError("Tactical Mind evidence does not match the completed roll.")
    return {"check_feature": TACTICAL_MIND, **({"tactical_mind_roll": evidence.roll} if evidence.roll is not None else {})}


def _heal(session: Any, amount: int) -> int:
    return session.heal_player(amount)


def _regain(session: Any, level: int) -> dict[str, Any]:
    roll = session.rng.randint(1, SECOND_WIND_DIE)
    healing = _heal(session, roll + level)
    _spend(session.character, "second_wind_spent")
    return {"roll": roll, "healing": healing, "current_hp": session.character["current_hp"],
            "uses_remaining": second_wind_maximum(level) - _uses(session.character)["second_wind_spent"]}


def _tactical_shift(session: Any, level: int, distance: Any) -> None:
    """The half-Speed move happens now, inside the activation, on the existing movement ledger; no allowance outlives the step."""
    import action_economy as economy
    import spatial_rules
    if level < TACTICAL_SHIFT_LEVEL:
        raise CombatRequestError("tactical_shift_not_available", "Tactical Shift starts at Fighter level 5.")
    data = session.character
    cost = spatial_rules.movement_cost(distance, crawling=bool(data.get("prone") or "prone" in economy.conditions(session, "player")))
    if cost > economy.speed(session, "player") // 2:
        raise CombatRequestError("tactical_shift_out_of_range", "Tactical Shift moves up to half your Speed.")
    economy.ensure(session)["player"]["ready_movement_grant"] += cost
    economy.move(session, "player", distance)


def activate_second_wind(session: Any, distance: Any = None) -> dict[str, Any]:
    from initiative import atomic
    import action_economy as economy
    with atomic(session):
        reason = _second_wind_reason(session)
        if reason:
            raise CombatRequestError(reason, "Second Wind is unavailable: " + reason)
        economy.consume_feature_bonus(session)
        level = fighter_level(session.character)
        result = _regain(session, level)
        if distance is not None:
            _tactical_shift(session, level, distance)
        return {**result, "moved_ft": distance or 0}


def second_wind_outside_combat(session: Any) -> dict[str, Any]:
    """Outside combat a Bonus Action has no turn budget to spend; the use pool is the same one."""
    level = fighter_level(session.character)
    if level is None:
        raise ValueError("Bu karakterin Second Wind özelliği yok.")
    if session.world_state.get("combat", {}).get("active"):
        raise ValueError("Çatışmada Second Wind, kendi turunda Bonus Action ile kullanılır.")
    if _uses(session.character)["second_wind_spent"] >= second_wind_maximum(level):
        raise ValueError("Second Wind kullanımın kalmadı.")
    return _regain(session, level)


def activate_action_surge(session: Any) -> dict[str, Any]:
    from initiative import atomic
    import action_economy as economy
    with atomic(session):
        reason = _action_surge_reason(session)
        if reason:
            raise CombatRequestError(reason, "Action Surge is unavailable: " + reason)
        _spend(session.character, "action_surge_spent")
        # A limited grant on the existing resource: never Magic, and an Attack action taken with it has the normal attack count.
        economy.grant(session, "player", "action_surge", sorted(economy.ACTION_TYPES - {"magic"}),
                      restrictions={"requires_base_action_spent": True, "max_attacks": economy.attacks_per_action(session, "player")})
        level = fighter_level(session.character)
        return {"uses_remaining": action_surge_maximum(level) - _uses(session.character)["action_surge_spent"]}


def native_command(command: Any) -> bool:
    if type(command) is not dict or set(command) != {"steps"} or type(command["steps"]) is not list or len(command["steps"]) != 1:
        return False
    step = command["steps"][0]
    if type(step) is not dict:
        return False
    if step.get("kind") == "action_surge":  # a parsed public step carries the default action resource
        return set(step) - {"resource"} == {"kind"} and step.get("resource", "action") == "action"
    return (step.get("kind") == "second_wind" and step.get("resource") == "bonus"
            and set(step) - {"distance_ft"} == {"kind", "resource"}
            and ("distance_ft" not in step or (type(step["distance_ft"]) is int and step["distance_ft"] > 0)))


def projection(session: Any) -> dict[str, Any] | None:
    character = session.character
    try:
        level = fighter_level(character)
        if level is None:
            return None
        validate_saved(character)
        uses = _uses(character)
        wind_reason, surge_reason = _second_wind_reason(session), _action_surge_reason(session)
        mind_reason = tactical_mind_reason(session)
        maximum = second_wind_maximum(level)
        return {
            "fighting_style": character.get(STYLE),
            "tactical_mind": None if level < TACTICAL_MIND_LEVEL else {"available": mind_reason is None, "reason": mind_reason},
            "second_wind": {"uses_remaining": maximum - uses["second_wind_spent"], "max_uses": maximum, "die": SECOND_WIND_DIE,
                            "level_bonus": level, "activate": {"available": wind_reason is None, "reason": wind_reason},
                            "tactical_shift": level >= TACTICAL_SHIFT_LEVEL},
            "action_surge": None if level < ACTION_SURGE_LEVEL else {
                "uses_remaining": action_surge_maximum(level) - uses["action_surge_spent"], "max_uses": action_surge_maximum(level),
                "activate": {"available": surge_reason is None, "reason": surge_reason}},
        }
    except (ValueError, KeyError, TypeError):
        return None


def style(character: Any) -> str | None:
    return character.get(STYLE) if fighter_level(character) is not None else None


def attack_rules(character: Any, weapon: dict[str, Any]) -> dict[str, Any]:
    """Sourced modifiers for the existing attack-rule owner. Only an applied style reaches it."""
    held = style(character)
    if held == "Archery" and weapon["kind"] == "ranged":
        return {"attack_modifiers": [{"source": "fighting_style_archery", "value": ARCHERY_ATTACK_BONUS}]}
    if (held == "Dueling" and weapon["kind"] == "melee" and weapon.get("grip") == 1
            and sum(value is not None for value in weapon.get("equipment_after", {}).values()) == 1):
        # The hands record names no shield, so a filled off hand is never read as free: under-grant, disclosed.
        return {"damage_modifiers": [{"source": "fighting_style_dueling", "value": DUELING_DAMAGE_BONUS}]}
    return {}


def great_weapon_rolls(character: Any, weapon: dict[str, Any], mode: str, rolls: list[int]) -> list[int] | None:
    """Damage dice with 1 and 2 counted as 3, or None when Great Weapon Fighting does not apply to this attack."""
    if (style(character) != "Great Weapon Fighting" or mode != "melee" or weapon.get("grip") != 2
            or not {"two-handed", "versatile"} & set(weapon["properties"])):
        return None
    return [max(GREAT_WEAPON_MINIMUM, roll) for roll in rolls]


def light_attack_keeps_modifier(character: Any, origin: str) -> bool:
    return origin == "light" and style(character) == "Two-Weapon Fighting"


def champion(character: Any) -> bool:
    level = fighter_level(character)
    return level is not None and level >= CHAMPION_LEVEL


def critical_threshold(character: Any) -> int:
    return IMPROVED_CRITICAL if champion(character) else 20


def initiative_rules(character: Any) -> dict[str, Any]:
    return {"advantage_sources": ["remarkable_athlete"]} if champion(character) else {}


def remarkable_athlete_check(character: Any, skill: str, ability: str) -> bool:
    return champion(character) and skill == "Athletics" and ability == "strength"

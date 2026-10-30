"""C06 progression state: selected Sorcerer 1–5 and earned Barbarian 1→5 (creation at starting level 1–5 for both), with pending class effects.

Facts come from `content/rules/phb2024/classes/<class>.json` (read from the book's page scans). `progression_level` is the level
whose choices were applied; a level granted by XP above it is a PENDING level-up: the character keeps its previous resources
(`capacity` follows `progression_level`, never `level`) until `apply_level_choices` applies the choices exactly once.
Applied progression supports selected non-DEX ordinary ASI Sorcerer4 followed by selected5 / selected Berserker3→4→5 (level 5 has no choices); other paths are BLOCKED.
Subclass choice storage is not implementation of subclass features or full playability. Every delta lists effects that are not implemented under `effects_pending`.
Class-specific rules live in `class_progression/<class>.py` behind a registry; this module keeps the shared flow and re-exports
the class names other modules and tests read from here.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from api.dnd_2024_rules import proficiency_bonus_for_level
from class_progression import for_class, registered
from class_progression.barbarian import (  # noqa: F401
    _barbarian_asi_options,
    _validate_primal_knowledge,
    barbarian_level_five_applied,
    BARBARIAN_SKILLS,
    barbarian_starting_creation_options,
    berserker_eligible,
    EXTRA_ATTACK_ATTACKS,
    FAST_MOVEMENT_FT,
)
from class_progression.sorcerer import sorcerer_starting_creation_options  # noqa: F401

_CLASS_DIR = Path(__file__).resolve().parents[1] / "content" / "rules" / "phb2024" / "classes"
_cache: dict[str, dict[str, Any] | None] = {}
MAX_SUPPORTED_LEVEL = 5  # progression state only; pending class/spell effects are not playability acceptance


def _supported_level(class_name: Any) -> int:
    return min(MAX_SUPPORTED_LEVEL, for_class(class_name).supported_level)


def _project_selected_asi_hp(character: Any, target_level: Any, choice: Any) -> dict[str, Any]:
    """Selected ordinary ASI/paid-HP bridge; grants no level, feat, HP or permission.

    Atomic progression recomputes from pre-mutation state after validating choices. Base HP and retroactive maximum are separate
    components: the latter belongs to set_player_max_hp, never heal_player.
    Character-only input cannot authorize death/world state. The selected level4
    caller consumes this projection, not a client preview token or saved grant.
    """
    def refuse(reason: str, status: str = "rejected") -> dict[str, Any]:
        return {"status": status, "reason": reason}

    if not isinstance(character, dict) or type(target_level) is not int:
        return refuse("invalid_projection_input")
    raw, applied = character.get("level"), character.get("progression_level")
    if type(raw) is not int or type(applied) is not int:
        return refuse("invalid_projection_levels")
    if not for_class(character.get("class")).selected_asi or target_level != 4 or applied != 3 or raw not in (3, 4, 5):
        return refuse("projection_scope_not_supported", "unsupported")
    if (type(choice) is not dict or set(choice) != {"increase"}
            or not _supported_asi_increase(choice["increase"])):
        return refuse("selected_asi_not_supported", "unsupported")
    constitution, maximum = character.get("constitution"), character.get("max_hp")
    if type(constitution) is not int or not 1 <= constitution <= 30 or type(maximum) is not int or maximum < 1:
        return refuse("invalid_projection_values")
    import feat_rules
    import xp
    detached = copy.deepcopy(character)
    detached["level"] = target_level
    delta = feat_rules.apply_feat_choice(detached, "Ability Score Improvement",
                                         {**copy.deepcopy(choice), "source": "class_asi"})
    if delta["status"] != "applied":
        return refuse(delta["reason"])
    con_change = next((change for change in delta["changes"] if change["ability"] == "constitution"), None)
    modifier_gain = ((con_change["to"] - 10) // 2 - (con_change["from"] - 10) // 2) if con_change else 0
    base_gain = xp.hit_point_gain(character) if raw < target_level else 0
    retroactive_gain = modifier_gain * max(raw, target_level)
    return {"status": "projected", "reason": None, "unpaid_base_gain": base_gain,
            "retroactive_max_gain": retroactive_gain,
            "resulting_maximum": maximum + base_gain + retroactive_gain,
            "feat_delta": delta}


def table(class_name: Any) -> dict[str, Any] | None:
    if not isinstance(class_name, str) or not class_name.isalpha():
        return None
    if class_name not in _cache:
        path = _CLASS_DIR / f"{class_name.lower()}.json"
        _cache[class_name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return _cache[class_name]


def applied_level(character: dict[str, Any]) -> int:
    value = character.get("progression_level", 1)
    level = character.get("level", 1)
    if type(value) is not int or value < 1:
        value = 1
    return min(value, level) if type(level) is int and level >= 1 else value


def has_table(character: dict[str, Any]) -> bool:
    return table(character.get("class")) is not None


def row(character: dict[str, Any], level: int) -> dict[str, Any]:
    return table(character["class"])["levels"][str(level)]


def capacity(character: dict[str, Any]) -> dict[str, Any] | None:
    """Spell resources at the APPLIED level for a class with a table; None when the class has no table (old level-1 rule)."""
    if not has_table(character):
        return None
    return for_class(character.get("class")).capacity(character)


def slot_capacity(character: dict[str, Any]) -> dict[str, int] | None:
    cap = capacity(character)
    return cap["slots"] if cap else None


def _preview(status: str, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **extra}


def progression_disclosure(class_name: str, level: int, **adopted: Any) -> dict[str, list[str]]:
    """Pure supported/pending view. Capability facts never adopt resources."""
    return for_class(class_name).disclosure(level, **adopted)


def progression_effects_pending(class_name: str, level: int, **adopted: Any) -> list[str]:
    return progression_disclosure(class_name, level, **adopted)["pending"]


HIGHER_START_EQUIPMENT_PENDING = ("Higher-start equipment: normal starting gear only; optional extra wealth and magic items remain pending")


def preview_level_up(session: Any, target_level: Any) -> dict[str, Any]:
    """What reaching `target_level` needs and gives. Pure: nothing is changed."""
    character = session.character
    if type(target_level) is not int or not 1 <= target_level <= 20:
        return _preview("blocked", "invalid_target_level")
    if not has_table(character):
        return _preview("blocked", "class_table_not_available")
    current = applied_level(character)
    if type(character.get("level")) is not int or not 1 <= character["level"] <= 20:
        return _preview("blocked", "invalid_character_level")
    if target_level <= current:
        return _preview("blocked", "target_not_above_applied_level", from_level=current, to_level=target_level)
    if target_level > _supported_level(character["class"]):
        return _preview("blocked", "progression_level_not_supported", from_level=current, to_level=target_level)
    if target_level == 5:
        if (type(character.get("progression_level")) is not int or character["progression_level"] != 4
                or character["level"] != 5):
            return _preview("blocked", "previous_level_four_choices_and_numeric_five_required")
        try:
            validate_saved(character, session.world_state)
            _validate_con_caches(character)
        except (ValueError, KeyError, TypeError):
            return _preview("blocked", "previous_level_four_state_invalid")
    handler = for_class(character["class"])
    problem = handler.level_prerequisite(session, target_level)
    if problem:
        return _preview("blocked", problem, from_level=current, to_level=target_level)
    rows = [row(character, level) for level in range(current + 1, target_level + 1)]
    features = [feature for data in rows for feature in data["features"]]
    prior, goal = row(character, current), rows[-1]
    import xp
    required = handler.choices_required(character, current, target_level, prior, goal)
    disclosure = progression_disclosure(character["class"], target_level, **handler.adoption(session.world_state))
    pending = disclosure["pending"]
    return _preview(
        "ready", None, class_name=character["class"], from_level=current, to_level=target_level, features=features,
        choices_required=required,
        capacity=handler.preview_capacity(goal),
        hit_points={"gain": xp.hit_point_gain(character) * max(0, target_level - character["level"]), "already_applied": character["level"] >= target_level},
        effects_pending=pending, effects_supported=disclosure["supported"],
        **handler.preview_options(session, target_level),
    )


_NONDEX_ASI_ABILITIES = ("strength", "constitution", "intelligence", "wisdom", "charisma")


def _supported_asi_increase(increase: Any) -> bool:
    return (type(increase) is dict and not set(increase) - set(_NONDEX_ASI_ABILITIES)
            and all(type(amount) is int for amount in increase.values())
            and sorted(increase.values()) in ([2], [1, 1]))


def supported_asi_choices(character: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Static engine family, or cap-eligible choices for the current character.

    C03 remains the score/eligibility owner; DEX requires worn-armor provenance.
    """
    import feat_rules
    increases = [{a: 2} for a in _NONDEX_ASI_ABILITIES]
    increases += [{a: 1, b: 1} for i, a in enumerate(_NONDEX_ASI_ABILITIES)
                  for b in _NONDEX_ASI_ABILITIES[i + 1:]]
    options = [{"feat": "Ability Score Improvement", "increase": inc} for inc in increases]
    if character is None:
        return options
    detached = {**copy.deepcopy(character), "level": 4}
    return [option for option in options if feat_rules.apply_feat_choice(
        detached, option["feat"], {"source": "class_asi", "increase": option["increase"]})["status"] == "applied"]


def _selected_asi_record(increase: dict[str, int] | None = None) -> list[dict[str, Any]]:
    return [{"class_level": 4, "feat": "Ability Score Improvement",
             "increase": copy.deepcopy(increase if increase is not None else {"constitution": 2})}]


def _score_context(player: dict[str, Any], *, saved: bool) -> dict[str, Any]:
    import feat_rules
    origin = player.get("origin_choices", {}) if saved else player
    if type(origin) is not dict:
        raise ValueError("Invalid ASI origin provenance.")
    return dict(scores={a: player.get(a) for a in feat_rules.ABILITIES},
                base_scores=origin.get("base_ability_scores"),
                background_bonuses=origin.get("background_ability_bonuses"),
                ability_score_method=origin.get("ability_score_method"), background=origin.get("background"),
                class_name=player.get("class"), level=player.get("level"),
                applied_level=player.get("progression_level"), asi_choices=player.get("asi_choices"))


def _validate_con_caches(player: dict[str, Any], *, saved: bool = False) -> None:
    import feat_rules
    scores = {a: player.get(a) for a in feat_rules.ABILITIES}
    if any(type(v) is not int for v in scores.values()):
        raise ValueError("Invalid ASI ability scores.")
    modifiers = {a: (v - 10) // 2 for a, v in scores.items()}
    if type(player.get("proficiency_bonus")) is not int or player["proficiency_bonus"] != proficiency_bonus_for_level(player["level"]):
        raise ValueError("Invalid selected ASI proficiency bonus.")
    saves = player.get("saving_throw_mods")
    if (type(saves) is not dict or set(saves) != set(scores)
            or any(type(v) is not int for v in saves.values())):
        # These are authoritative totals, not a reconstructed proficiency cache.
        # The generalized ASI family preserves legitimate nonability offsets.
        raise ValueError("Invalid ASI saving throw totals.")
    if not saved:
        if (type(player.get("modifiers")) is not dict or player["modifiers"] != modifiers
                or any(type(v) is not int for v in player["modifiers"].values())
                or any(type(player.get(a + "_mod")) is not int or player[a + "_mod"] != m
                       for a, m in modifiers.items())
                or ("final_ability_scores" in player and (type(player["final_ability_scores"]) is not dict
                    or player["final_ability_scores"] != scores
                    or any(type(v) is not int for v in player["final_ability_scores"].values())))):
            raise ValueError("Inconsistent ASI ability caches.")


def _validate_asi_choice_storage(player: dict[str, Any], *, saved: bool = False) -> None:
    """Admit one selected non-DEX ordinary ASI with source-reconstructable scores."""
    choices = player.get("asi_choices", [])
    applied = player.get("progression_level")
    if type(choices) is not list:
        raise ValueError("Invalid ASI choices.")
    if not choices and applied not in (4, 5):
        return
    if (len(choices) != 1 or type(choices[0]) is not dict
            or set(choices[0]) != {"class_level", "feat", "increase"}
            or type(choices[0]["class_level"]) is not int or choices[0]["class_level"] != 4
            or choices[0]["feat"] != "Ability Score Improvement"
            or not _supported_asi_increase(choices[0]["increase"])):
        raise ValueError("Selected earned ASI record required.")
    result = _check_detached_asi_consistency(**_score_context(player, saved=saved))
    if not result["consistent"]:
        raise ValueError("Invalid earned ASI provenance: " + result["reason"])
    _validate_con_caches(player, saved=saved)
    for_class(player.get("class")).validate_asi_storage(player, saved=saved)


def attacks_per_attack_action(character: Any) -> int:
    """Attacks one Attack action allows from class features (the existing attacks-per-Action allowance owner reads this)."""
    return _handler_of(character).attacks_per_attack_action(character)


def fast_movement_bonus_ft(character: Any, world: Any) -> int:
    """Speed bonus from class features (the existing Speed owner reads this)."""
    return _handler_of(character).speed_bonus_ft(character, world)


def _handler_of(character: Any) -> Any:
    return for_class(character.get("class") if isinstance(character, dict) else None)


def _check_detached_asi_consistency(*, scores: Any, base_scores: Any,
                                    background_bonuses: Any, ability_score_method: Any,
                                    background: Any, class_name: Any, level: Any,
                                    applied_level: Any, asi_choices: Any) -> dict[str, Any]:
    """Private hypothetical selected ordinary ASI consistency check, NOT admission.

    Inputs are explicit normalized values, not live/saved character dictionaries.
    No mutation, ready token, HP calculation or entitlement follows from success.
    A consistent unsigned claim is not proof against rewriting its entire baseline.
    Rolled provenance is unsupported: stored scores are not a verified dice pool.
    """
    import feat_rules
    from api.dnd_2024_rules import validate_ability_scores, validate_background_bonuses

    def reject(reason):
        return {"consistent": False, "reason": reason}

    if (not for_class(class_name).selected_asi or type(level) is not int or level not in (4, 5)
            or type(applied_level) is not int or applied_level not in (4, 5) or applied_level > level):
        return reject("unsupported_hypothetical_context")
    abilities = set(feat_rules.ABILITIES)
    for values in (scores, base_scores):
        if (type(values) is not dict or set(values) != abilities
                or any(type(v) is not int for v in values.values())):
            return reject("invalid_scores")
    if (type(background_bonuses) is not dict or set(background_bonuses) - abilities
            or any(type(v) is not int or not 0 <= v <= 2 for v in background_bonuses.values())
            or type(background) is not str or type(ability_score_method) is not str
            or ability_score_method not in ("standard_array", "point_buy", "manual")):
        return reject("invalid_origin_provenance")
    try:
        validate_ability_scores(ability_score_method, base_scores)
        validate_background_bonuses(background, background_bonuses, base_scores)
    except ValueError:
        return reject("invalid_origin_provenance")
    if type(asi_choices) is not list or len(asi_choices) != 1:
        return reject("invalid_asi_record")
    record = asi_choices[0]
    if (type(record) is not dict or set(record) != {"class_level", "feat", "increase"}
            or type(record["class_level"]) is not int or record["class_level"] != 4
            or record["feat"] != "Ability Score Improvement"
            or type(record["increase"]) is not dict):
        return reject("invalid_asi_record")
    replay = {ability: base_scores[ability] + background_bonuses.get(ability, 0)
              for ability in feat_rules.ABILITIES}
    detached = {**replay, "class": class_name, "level": level}
    delta = feat_rules.apply_feat_choice(detached, record["feat"],
                                         {"source": "class_asi", "increase": record["increase"]})
    if delta["status"] != "applied":
        return reject(delta["reason"])
    for change in delta["changes"]:
        replay[change["ability"]] = change["to"]
    if replay != scores:
        return reject("score_delta_mismatch")
    return {"consistent": True, "reason": None}


def validate_saved(player: dict[str, Any], world: dict[str, Any], *, saved: bool = False) -> None:
    """Validate applied choices, not completion of the selected feature effects."""
    _validate_asi_choice_storage(player, saved=saved)
    for each in registered():
        each.validate_class_fields(player)
    handler = for_class(player.get("class"))
    handler.validate_state(player, world)
    if not any(field in player for field in ("progression_level", "metamagic", "subclass_id")):
        return
    applied = player.get("progression_level", 1)
    level = player.get("level", 1)
    if type(applied) is not int or type(level) is not int or not 1 <= applied <= level <= 20:
        raise ValueError("Kayıt uygulanmış ilerleme seviyesi geçersiz.")
    if not has_table(player):
        if applied != 1 or player.get("metamagic") or "subclass_id" in player:
            raise ValueError("Kayıt ilerleme tablosu olmayan sınıf için ilerleme iddia ediyor.")
        return
    if applied > _supported_level(player["class"]):
        raise ValueError("Kayıt desteklenmeyen ilerleme seviyesi iddia ediyor.")
    handler.validate_applied(player, world, applied)


def _reject(reason: str) -> dict[str, Any]:
    return {"status": "rejected", "reason": reason, "changes": [], "effects_pending": []}


def _check_choices(session: Any, preview: dict[str, Any], choices: Any) -> str | None:
    if not isinstance(choices, dict):
        return "choices_required"
    required = preview["choices_required"]
    if set(choices) - set(required):
        return "unsupported_choice"
    return for_class(session.character["class"]).check_choices(session, preview, choices)


def apply_level_choices(session: Any, preview: Any, choices: Any) -> dict[str, Any]:
    """Apply one previewed level-up atomically. A rejection changes nothing; applying the same preview twice is refused."""
    if not isinstance(preview, dict) or preview.get("status") != "ready":
        return _reject("preview_not_ready")
    character = session.character
    if type(preview.get("to_level")) is int and preview["to_level"] <= applied_level(character):
        return _reject("already_applied")
    current = preview_level_up(session, preview.get("to_level"))
    if current != preview:
        return _reject("preview_not_current")
    problem = _check_choices(session, preview, choices)
    if problem:
        return _reject(problem)
    return for_class(character["class"]).apply_level(session, preview, choices)


def _apply_asi_score_delta(character, feat_delta):
    """Apply the recomputed C03 delta, preserving authoritative save offsets."""
    import feat_rules
    for change in feat_delta["changes"]:
        ability = change["ability"]
        old_modifier = (change["from"] - 10) // 2
        new_modifier = (change["to"] - 10) // 2
        character[ability] = change["to"]
        character[ability + "_mod"] = new_modifier
        character["modifiers"][ability] = new_modifier
        character["saving_throw_mods"][ability] += new_modifier - old_modifier
    # Creation-only hints are not live authorities; actual consumers derive
    # their values. Do not change DEX/AC/initiative or NPC caches.
    for key in ("spell_save_dc", "spell_attack_bonus", "passive_perception"):
        character.pop(key, None)
    character["final_ability_scores"] = {a: character[a] for a in feat_rules.ABILITIES}


def create_at_level(session: Any, spec: dict[str, Any], level: int = 1, level_choices: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a level-1 character with the real creation path, then reach `level` through the same preview/apply steps.

    Everything is checked before the character is created, so an unsupported level or missing choices leaves no half-made level.
    """
    from api.character_creation import configure_character
    if type(level) is not int or not 1 <= level <= 20:
        raise ValueError("invalid_target_level")
    if level > 1:
        class_name = spec.get("character_class")
        for_class(class_name).validate_start_choices(level, level_choices)
        if table(spec.get("character_class")) is None:
            raise ValueError("class_table_not_available")
        if level > 5:  # Higher creation stays bounded independently of future progression.
            raise ValueError("progression_level_not_supported")
        if level >= 4 and (type(level_choices) is not dict
                           or set(level_choices) != {str(n) for n in range(2, level + 1)}
                           or any(type(value) is not dict for value in level_choices.values())):
            raise ValueError("exact_creation_level_choices_required")
        missing = [str(n) for n in range(2, level + 1) if not isinstance((level_choices or {}).get(str(n)), dict)]
        if missing:
            raise ValueError(f"choices_required_for_levels_{','.join(missing)}")
    snapshot = session._capture_runtime_snapshot()
    try:
        for field in ("progression_level", "metamagic", "subclass_id", "hit_dice"):
            session.character.pop(field, None)
        configure_character(session, mode="custom", **spec)
        if level >= 4:
            # New-character initialization, not migration or a paid XP award.
            session._persisted_engine_format = 6 if level == 5 else 4
            session._xp_level_up = None
            session.world_state.setdefault("xp_awarded_event_ids", [])
        for step in range(2, level + 1):
            if step == 5:
                import xp
                xp._apply_numeric_level(session.character, 5)
            delta = apply_level_choices(session, preview_level_up(session, step), level_choices[str(step)])
            if delta["status"] != "applied":
                raise ValueError(delta["reason"])
        session.character.setdefault("progression_level", 1)
        # Starting XP is initialization, not an award: choices above already
        # applied the level's HP/resources. Keep this inside atomic creation.
        import xp
        session.character["xp"] = dict(xp.LEVEL_THRESHOLDS)[level]
        if level >= 4:
            # Only fresh creation ends full. Advancement's maximum-only ASI
            # setter must continue to preserve an existing character's wounds.
            session.character["current_hp"] = session.character["max_hp"]
            session._validate_save_payload(session.serialize_game_state())
        return session.character
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        raise

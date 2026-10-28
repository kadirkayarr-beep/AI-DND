"""K07: evaluate a source-backed numeric rule case against the REAL engine resolver.

`content/manifest/rule-oracles.json` holds hand-written expectations with their PHB 2024 page; this module only runs the
engine's own resolver for a case and reports the actual value next to the expected one. It never computes an expectation,
so an oracle can never be "filled in" from the engine under test. Families still listed as `open_leaves` are OPEN: asking
to evaluate one is an error, not a pass.
"""
from __future__ import annotations

import json
from pathlib import Path

ORACLE_PATH = Path(__file__).resolve().parents[1] / "content" / "manifest" / "rule-oracles.json"


class OpenRule(ValueError):
    """The rule family has no covered leaf; it is open, never complete."""


def load_oracles(path: Path = ORACLE_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _case(oracles: dict, case_id: str):
    leaf_id, _, number = case_id.partition("#")
    for leaf in oracles["leaves"]:
        if leaf["leaf_id"] == leaf_id:
            for case in leaf["cases"]:
                if case["id"] == number:
                    return leaf, case
    if any(open_leaf["rule"] in case_id for open_leaf in oracles["open_leaves"]):
        raise OpenRule(f"{case_id} belongs to an OPEN rule family")
    raise KeyError(case_id)


def _ability_modifier(case):
    import game
    from api import dnd_2024_rules
    first, second = game.get_modifier(case["input"]["score"]), dnd_2024_rules.get_modifier(case["input"]["score"])
    if first != second:
        raise AssertionError("two engine resolvers disagree on the same score")
    return first


def _advantage_disadvantage(case):
    from api.core_resolution import roll_d20
    values = iter(case["input"]["rolls"])
    result = roll_d20(lambda: next(values), advantage=case["input"]["advantage"], disadvantage=case["input"]["disadvantage"])
    return {"rolled": len(result["raw_rolls"]), "selected": result["selected_roll"]}


def _expertise_once(case):
    from api.tests.test_species_traits import make_session
    given = case["input"]
    session = make_session("Aasimar", level=3)
    skill = "Athletics"
    result = session.perform_skill_check(
        skill, 10, session.character["modifiers"], [skill] if given["proficient"] else [],
        given["proficiency_bonus"], expertise_skills=[skill] if given["expertise"] else [])
    return result["resolution"]["modifier_breakdown"]["proficiency_modifier"]


def _temp_hp_lost_first(case):
    from api.tests.test_species_traits import make_session
    given = case["input"]
    session = make_session("Aasimar", level=3)
    session.character.update(max_hp=given["hp"], current_hp=given["hp"])
    session.character["species_trait_state"]["temporary_hit_points"] = given["temp"]
    result = session._apply_attack_damage_to_player(given["damage"], False, True)
    return {"temp": result["temporary_hp_after"], "hp": session.character["current_hp"]}


def _proficiency_bonus_by_level(case):
    from api import dnd_2024_rules
    try:
        return dnd_2024_rules.proficiency_bonus_for_level(case["input"]["level"])
    except ValueError:
        return "rejected"


def _long_rest(case):
    from api.tests.test_species_traits import make_session
    given = case["input"]
    session = make_session("Human", level=1)
    session.character.update(max_hp=given["max_hp"], current_hp=given["hp"], exhaustion=given["exhaustion"])
    if given.get("combat_active"):
        from api.tests.test_death_system import start_test_combat  # a REAL started encounter, not a hand-set flag
        start_test_combat(session)
        if not session.world_state["combat"]["active"]:
            raise AssertionError("fixture failed to start combat")
    try:
        session.resolve_species_trait_action("long_rest", elapsed_seconds=given["elapsed_seconds"])
    except ValueError as error:
        # the refusal must come for the EXPECTED reason: an unknown message is reported as such and fails the case
        known = {"süresi geçersiz": "duration_invalid", "Çatışma sırasında": "combat_active",
                 "Bilinçsiz karakter": "player_cannot_act", "Ölü karakter": "player_cannot_act"}
        reason = next((code for text, code in known.items() if text in str(error)), "unclassified: " + str(error))
        return {"status": "rejected", "reason": reason}
    return {"status": "completed", "hp": session.character["current_hp"], "exhaustion": session.character.get("exhaustion", 0)}


def _turn_resource_budgets(case):
    """Run the steps against the REAL combat owner (`action_economy`) in a started encounter on the player's turn."""
    import action_economy
    from api.tests.test_death_system import make_session, start_test_combat
    from combat_lifecycle import CombatRequestError
    session = make_session()
    start_test_combat(session)
    results = []
    for step in case["input"]["steps"]:
        op = step["op"]
        try:
            if op == "action_names":
                results.append(sorted(name.capitalize() for name in action_economy.ACTION_TYPES - {"feature"}))
                continue
            if op == "consume":
                action_economy.consume_action(session, "player", step["kind"], step["resource"])
            elif op == "grant_bonus":
                action_economy.grant(session, "player", "oracle_feature", [step.get("kind", "disengage")], resource="bonus")
            elif op == "set_speed":
                session.character["speed_ft"] = step["feet"]
            elif op == "move":
                action_economy.move(session, "player", step["feet"])
            elif op == "dash":
                action_economy.dash(session, "player")
            elif op == "begin_turn":
                action_economy.begin_turn(session, "player")
            elif op == "begin_round":
                action_economy.begin_round(session)
            elif op == "spend_reaction":
                action_economy.ensure(session)["player"]["reaction_spent"] = True
            elif op == "reaction_spent":
                results.append(action_economy.ensure(session)["player"]["reaction_spent"])
                continue
            elif op == "incapacitate":
                session.character["conditions"] = ["incapacitated"]
            else:
                raise KeyError(op)
            results.append("ok")
        except CombatRequestError as error:
            results.append(error.code)
    return results


def _saving_throw_and_skill_list(case):
    import game
    from api import dnd_2024_rules
    given = case["input"]
    if given["op"] == "skill_abilities":  # both engine copies of the table are run, never assumed equal
        if given["owner"] == "rules":
            return {skill: data["ability"] for skill, data in dnd_2024_rules.SKILL_DEFINITIONS.items()}
        return dict(game.SKILLS)
    if given["op"] == "class_saves":
        return {name: sorted(data["saving_throws"]) for name, data in dnd_2024_rules.CLASS_DEFINITIONS.items()}
    return dnd_2024_rules.calculate_derived_stats(given["class"], "Human", given["scores"])["saving_throw_mods"]


DISPATCH = {
    "K07.saving_throw_and_skill_list": _saving_throw_and_skill_list,
    "K07.turn_resource_budgets": _turn_resource_budgets,
    "K07.long_rest_hp_exhaustion_duration": _long_rest,
    "K07.proficiency_bonus_by_level": _proficiency_bonus_by_level,
    "K07.ability_modifier": _ability_modifier,
    "K07.advantage_disadvantage": _advantage_disadvantage,
    "K07.expertise_once": _expertise_once,
    "K07.temp_hp_lost_first": _temp_hp_lost_first,
}


def evaluate_rule_case(case_id: str, oracles: dict | None = None) -> dict:
    oracles = oracles or load_oracles()
    leaf, case = _case(oracles, case_id)
    actual = DISPATCH[leaf["leaf_id"]](case)
    return {"case_id": case_id, "leaf_id": leaf["leaf_id"], "kind": case["kind"], "expected": case["expected"],
            "actual": actual, "match": actual == case["expected"], "source_ref": leaf["source_ref"]}

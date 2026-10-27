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


DISPATCH = {
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

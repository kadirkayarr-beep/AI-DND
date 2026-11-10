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


def _death_saves_temp_hp_at_zero(case):
    from api.tests.test_death_system import make_session
    given = case["input"]
    session = make_session()
    session.character.update(
        race="Orc",
        species="Orc",
        max_hp=given["max_hp"],
        current_hp=given["max_hp"],
    )
    session.ensure_death_state()["mode"] = "PERMADEATH"
    session._apply_player_damage(given["damage"], took_damage=True)
    death = session.ensure_death_state()
    death.update(successes=given["successes"], failures=given["failures"])
    session.grant_temporary_hit_points(given["temporary_hit_points"])
    return {
        "temporary_hit_points": session._species_trait_state()["temporary_hit_points"],
        "hp": session.character["current_hp"],
        "status": session.world_state["player_combat_status"],
        "successes": death["successes"],
        "failures": death["failures"],
        "stable": death["stable"],
        "dead": death["dead"],
    }


def _death_saves_core(case):
    from unittest.mock import patch
    import game
    from api.tests.test_death_system import make_session, start_test_combat
    given = case["input"]
    session = make_session()
    session.ensure_death_state()["mode"] = "PERMADEATH"
    session.character["max_hp"] = given.get("max_hp", 20)
    session.character["current_hp"] = session.character["max_hp"]
    if given["op"] == "instant":
        session.character["current_hp"] = given["hp"]
        session._apply_player_damage(given["damage"], took_damage=True)
        death = session.ensure_death_state()
        result = {"dead": death["dead"], "status": session.world_state["player_combat_status"],
                  "hp": session.character["current_hp"]}
        if not death["dead"]:
            result["failures"] = death["failures"]
        return result
    if given["op"] in ("death_save", "stable_no_save"):
        start_test_combat(session)
    session._apply_player_damage(session.character["current_hp"], took_damage=True)
    death = session.ensure_death_state()
    death.update(successes=given.get("successes", 0), failures=given.get("failures", 0))

    if given["op"] == "death_save":
        save_bonus = None
        if "constitution" in given:
            from api.dnd_2024_rules import calculate_derived_stats
            scores = {"strength": 10, "dexterity": 10, "constitution": given["constitution"],
                      "intelligence": 10, "wisdom": 10, "charisma": 10}
            derived = calculate_derived_stats("Fighter", "Human", scores)
            session.character.update(
                constitution=given["constitution"],
                proficiency_bonus=derived["proficiency_bonus"],
                saving_throws=derived["saving_throws"],
                saving_throw_mods=derived["saving_throw_mods"],
            )
            save_bonus = derived["saving_throw_mods"]["constitution"]
        outcomes = []
        for index, roll in enumerate(given["rolls"]):
            if index:
                session.world_state["combat"]["round"] += 1
            with patch("game.roll_d20", return_value=roll):
                result = session._resolve_player_death_turn()
            outcomes.append(result["outcome"])
        result = {"outcomes": outcomes, "successes": death["successes"], "failures": death["failures"],
                  "stable": death["stable"], "dead": death["dead"], "hp": session.character["current_hp"],
                  "status": session.world_state["player_combat_status"]}
        if save_bonus is not None:
            result["constitution_save_bonus"] = save_bonus
        return result

    if given["op"] == "stable_no_save":
        with patch.object(session.rng, "randint", return_value=1):
            session.stabilize_player()
        with patch("game.roll_d20", side_effect=AssertionError("Stable creature must not roll")):
            result = session._resolve_player_death_turn()
        return {"result": result, "stable": death["stable"], "successes": death["successes"],
                "failures": death["failures"], "hp": session.character["current_hp"],
                "status": session.world_state["player_combat_status"]}

    if given["op"] == "damage":
        session._apply_player_damage(given["damage"], critical=given["critical"], took_damage=True)
        result = {"dead": death["dead"], "status": session.world_state["player_combat_status"]}
        if given["damage"] < session.character["max_hp"]:
            result["failures"] = death["failures"]
        return result

    if given["op"] == "medicine":
        session.world_state["npcs"].append({
            "id": "oracle-medic", "location": session.world_state["location"],
            "current_hp": 5, "combat_status": "active", "medicine_bonus": 0,
        })
        with patch("game.roll_d20", return_value=given["roll"]):
            result = session.attempt_player_stabilization("oracle-medic")
        return {"success": result["success"], "stable": death["stable"],
                "successes": death["successes"], "failures": death["failures"],
                "hp": session.character["current_hp"], "status": session.world_state["player_combat_status"]}

    if given["op"] == "stable_damage":
        with patch.object(session.rng, "randint", return_value=1):
            session.stabilize_player()
        session._apply_player_damage(given["damage"], took_damage=True)
        return {"failures": death["failures"], "stable": death["stable"],
                "dead": death["dead"], "status": session.world_state["player_combat_status"]}

    if given["op"] == "recovery":
        session.commit_location_change("tavern")
        with patch.object(session.rng, "randint", return_value=given["hours"]):
            session.stabilize_player()
        session.advance_campaign_time(given.get("wait_seconds", given["hours"] * 3600), "wait")
        return {"hp": session.character["current_hp"], "stable": death["stable"],
                "status": session.world_state["player_combat_status"]}
    raise KeyError(given["op"])


def _death_saves_unconscious_condition(case):
    from unittest.mock import patch
    from api.tests.test_death_system import make_session
    given = case["input"]
    session = make_session()
    session.ensure_death_state()["mode"] = "PERMADEATH"
    session.character.update(max_hp=20, current_hp=20)
    session._apply_player_damage(20, took_damage=True)
    death = session.ensure_death_state()
    if given["op"] == "heal":
        session.heal_player(given["amount"])
        return {"hp": session.character["current_hp"], "status": session.world_state["player_combat_status"],
                "prone": death["prone"]}
    if given["op"] == "ranged_hit":
        enemy = {
            "id": "oracle-archer", "name": "Oracle Archer", "location": session.world_state["location"],
            "combat_status": "active", "current_hp": 10, "max_hp": 10, "armor_class": 10, "attack_bonus": 0,
            "distance_ft": given["distance_ft"], "weapon_id": "shortbow", "inventory": ["Shortbow"],
            "equipment": {"main_hand": "shortbow", "off_hand": None}, "dexterity": 14, "dexterity_mod": 2,
            "proficiency_bonus": 2, "weapon_proficiencies": ["simple"], "weapon_masteries": [],
            "ammunition": {"arrow": 20},
        }
        session.world_state["npcs"].append(enemy)
        with patch("game.roll_d20", side_effect=[10, 14]), patch("game.roll_damage", return_value=2):
            result = session.resolve_enemy_attack(enemy)
        return {"critical": result["critical"], "failures": death["failures"], "dead": death["dead"]}
    raise KeyError(given["op"])


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


def _hit_dice_rests(case):
    """Drive the REAL rest owners (`resolve_species_trait_action`) for a created character; one result per step."""
    from unittest.mock import patch
    import hit_dice
    from api.tests.test_campaign_time_edges import event
    from api.tests.test_roadmap_k07_hit_dice import fighter, sorcerer
    given = case["input"]
    session = fighter() if given["who"] == "fighter" else sorcerer(2)
    session.character["current_hp"], session.character["max_hp"] = given["current_hp"], given["max_hp"]
    if "constitution" in given:
        session.character["modifiers"]["constitution"] = given["constitution"]
    results = []
    for step in given["steps"]:
        op = step["op"]
        try:
            if op == "interrupt_after":
                event(session, "oracle-interruption", step["seconds"], step["seconds"] + 600, behavior="FORCED", summary="Interruption.")
            elif op in ("short_rest", "long_rest"):
                done = session.resolve_species_trait_action(op)["effects"].get("rest_completed", True)
                results.append("ok" if done else "interrupted")
            elif op == "spend":
                with patch.object(session.rng, "randint", return_value=step["roll"]):
                    results.append(session.resolve_species_trait_action("spend_hit_die")["effects"]["healing"])
            elif op == "remaining":
                results.append(hit_dice.remaining(session.character))
            else:
                raise KeyError(op)
        except ValueError as error:
            known = {"yeni bitirmiş": "no_window", "kalmadı": "no_dice", "en yüksek": "full_hp", "Çatışma": "combat"}
            results.append(next((f"refused:{code}" for text, code in known.items() if text in str(error)), "refused:unclassified"))
    return results


def _conditions(case):
    """Real owners: `action_economy` (Speed, movement, actions) and `weapon_attack` (attack-roll sources, saves)."""
    from unittest.mock import patch
    import action_economy as ae
    import weapon_attack as attack
    from api.tests.test_weapon_attack import armed, resolve
    from combat_lifecycle import CombatRequestError
    given = case["input"]
    session, enemy = armed()
    session.character.update(speed_ft=given.get("speed_ft", 30), conditions=list(given.get("conditions", [])),
                             exhaustion=given.get("exhaustion", 0))
    enemy["conditions"] = list(given.get("target_conditions", []))
    results = []
    for step in given["steps"]:
        op = step["op"]
        if op == "speed":
            results.append(ae.speed(session, "player"))
        elif op in ("move", "action"):
            try:
                ae.move(session, "player", step["feet"]) if op == "move" else ae.consume_action(session, "player", "attack", "action")
                results.append("ok")
            except CombatRequestError as error:
                results.append(error.code)
        elif op == "attack_advantage":
            results.append(sorted(resolve(session, enemy, rolls=(10, 15))["advantage_sources"]))
        elif op == "save":
            with patch.object(session, "roll_d20", side_effect=list(step["rolls"])):
                outcome = attack.save(session, enemy["id"], [step["ability"]], step["dc"], step["ability"])
            results.append("auto_fail" if outcome.get("automatic_failure") else outcome["outcome"])
        else:
            raise KeyError(op)
    return results


def _dodge_benefits(case):
    """Source-bound observations from existing attack/save owners; no rule calculation."""
    from unittest.mock import patch
    import action_economy as ae
    import weapon_attack as attack
    from api.tests.test_weapon_attack import armed
    given = case["input"]
    session, enemy = armed()
    enemy.update(conditions=list(given["conditions"]), speed_ft=given["speed_ft"],
                 dexterity_mod=0, dexterity_save_bonus=0, exhaustion=0)
    resource = ae.ensure(session)[enemy["id"]]
    resource["dodging"] = True
    resource["movement_used"] = resource["movement_available"]
    session.world_state["attack_environment"] = {"pairs": {
        "player|" + enemy["id"]: {"distance_ft": 5, "attacker_sees_target": True,
                                  "target_sees_attacker": given["sees_attacker"]}}}
    context = attack.prepare(session, "player", enemy["id"], "Longsword")
    with patch.object(session, "roll_d20", side_effect=given["rolls"]) as roller:
        result = attack.save(session, enemy["id"], ["dexterity"], 12)
    return {"attack_dodge_source": "target_dodging" in context["disadvantage_sources"],
            "save_roll_count": roller.call_count, "save_outcome": result["outcome"]}


def _invisible_initiative(case):
    from unittest.mock import patch
    from api.tests.test_initiative import actors
    given = case["input"]
    session, enemies = actors([{"conditions": given["conditions"],
                               "surprised_at_combat_start": given["surprised"]}])
    with patch("game.roll_d20", side_effect=given["rolls"]):
        session.start_combat(enemies[0])
    result = session.world_state["combat"]["initiative_results"][enemies[0]["id"]]
    return {"raw_rolls": result["raw_rolls"], "total": result["final_total"],
            "advantage_sources": result["advantage_sources"],
            "disadvantage_sources": result["disadvantage_sources"]}


def _long_rest_spacing(case):
    from api.tests.test_campaign_time import scene
    session = scene()
    given = case["input"]
    session.resolve_species_trait_action("long_rest")
    if given["wait"]:
        session.advance_campaign_time(given["wait"], "wait")
    if given.get("short_rest"):
        session.resolve_species_trait_action("short_rest")
    try:
        session.resolve_species_trait_action("long_rest", elapsed_seconds=given["duration"])
        status = "completed"
    except ValueError as error:
        if str(error) != "Yeni uzun dinlenmeye başlamadan önce son tamamlanmadan 16 oyun saati geçmeli.":
            raise
        status = "spacing_refused"
    return {"status": status, "clock": session.world_state["campaign_time"]["elapsed_seconds"],
            "completed_at": session.world_state["last_long_rest_completed_at"]}


def _initiative_exhaustion(case):
    from unittest.mock import patch
    from api.tests.test_initiative import actors
    given = case["input"]
    session, enemies = actors(player={"exhaustion": given["level"],
        "conditions": given["conditions"], "surprised_at_combat_start": given["surprised"]})
    with patch("game.roll_d20", side_effect=given["rolls"]):
        session.start_combat(enemies[0])
    result = session.world_state["combat"]["initiative_results"]["player"]
    return {"raw_rolls": result["raw_rolls"], "total": result["final_total"],
            "modifiers": result["additional_modifiers"]}


def _eligible_source_aggregation(case):
    from unittest.mock import patch
    from api.tests.test_weapon_attack import armed, resolve
    from api.tests.test_initiative import actors
    given = case["input"]
    rules = {"advantage_sources": given["advantage_sources"],
             "disadvantage_sources": given["disadvantage_sources"]}
    session, enemy = armed()
    session.character["attack_rules"] = rules
    attack = resolve(session, enemy, rolls=(3, 17))
    session, enemies = actors(player={"initiative_rules": rules})
    with patch("game.roll_d20", side_effect=[3, 17, 1]):
        session.start_combat(enemies[0])
    initiative = session.world_state["combat"]["initiative_results"]["player"]
    return {"weapon": {"raw": attack["attack_rolls"], "selected": attack["attack_roll"],
                       "advantage": attack["advantage_sources"], "disadvantage": attack["disadvantage_sources"]},
            "initiative": {"raw": initiative["raw_rolls"], "selected": initiative["selected_roll"],
                           "advantage": initiative["advantage_sources"], "disadvantage": initiative["disadvantage_sources"]}}


def _invisible_sight(case):
    from api.tests.test_weapon_attack import armed, resolve
    given = case["input"]
    session, enemy = armed()
    session.character["conditions"] = given["player_conditions"]
    enemy["conditions"] = given["target_conditions"]
    session.world_state["attack_environment"] = {"pairs": {
        "player|" + enemy["id"]: {"distance_ft": 5, **given["sight"]}}}
    result = resolve(session, enemy, rolls=(3, 17))
    return {"invisible_advantage": "invisible_attacker" in result["advantage_sources"],
            "invisible_disadvantage": "invisible_target" in result["disadvantage_sources"],
            "raw": result["attack_rolls"], "selected": result["attack_roll"]}


def _charmed_attack(case):
    import copy
    from api.tests.test_weapon_attack import armed, resolve
    from combat_lifecycle import CombatRequestError
    given = case["input"]
    session, enemy = armed()
    session.character["conditions"] = given["conditions"]
    if given["source"] == "target":
        session.character["charmed_by"] = enemy["id"]
    elif given["source"] == "other":
        session.character["charmed_by"] = "another-actor"
    before = copy.deepcopy((session.world_state, session.character, session.rng.getstate()))
    try:
        resolve(session, enemy)
    except CombatRequestError as error:
        if error.code != "charmed_target_forbidden":
            raise
        return {"status": error.code, "unchanged": (session.world_state, session.character, session.rng.getstate()) == before}
    return {"status": "allowed", "unchanged": (session.world_state, session.character, session.rng.getstate()) == before}


DISPATCH = {
    "K07.charmed_attack_charmer": _charmed_attack,
    "K07.invisible_attack_explicit_sight_exception": _invisible_sight,
    "K07.advantage_disadvantage_source_aggregation.weapon_and_initiative": _eligible_source_aggregation,
    "K07.initiative_exhaustion_penalty": _initiative_exhaustion,
    "K07.long_rest_start_spacing": _long_rest_spacing,
    "K07.initiative_invisible": _invisible_initiative,
    "K07.dodge_benefits_loss": _dodge_benefits,
    "K07.conditions_speed_actions_attacks_saves": _conditions,
    "K07.hit_dice_short_and_long_rest": _hit_dice_rests,
    "K07.saving_throw_and_skill_list": _saving_throw_and_skill_list,
    "K07.turn_resource_budgets": _turn_resource_budgets,
    "K07.long_rest_hp_exhaustion_duration": _long_rest,
    "K07.proficiency_bonus_by_level": _proficiency_bonus_by_level,
    "K07.ability_modifier": _ability_modifier,
    "K07.advantage_disadvantage": _advantage_disadvantage,
    "K07.expertise_once": _expertise_once,
    "K07.temp_hp_lost_first": _temp_hp_lost_first,
    "K07.death_saves_and_stable.temp_hp_at_zero": _death_saves_temp_hp_at_zero,
    "K07.death_saves_and_stable.core": _death_saves_core,
    "K07.death_saves_and_stable.unconscious_condition": _death_saves_unconscious_condition,
}


def evaluate_rule_case(case_id: str, oracles: dict | None = None) -> dict:
    oracles = oracles or load_oracles()
    leaf, case = _case(oracles, case_id)
    actual = DISPATCH[leaf["leaf_id"]](case)
    return {"case_id": case_id, "leaf_id": leaf["leaf_id"], "kind": case["kind"], "expected": case["expected"],
            "actual": actual, "match": actual == case["expected"], "source_ref": leaf["source_ref"]}

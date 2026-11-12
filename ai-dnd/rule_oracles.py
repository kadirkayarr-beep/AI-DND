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
    # A pending leaf (page-cited, no resolver yet) is OPEN by its own leaf id: its open_rule name ("spell_bless") is not a
    # substring of its case ids ("4C.spell.bless#01"), so the family check below cannot catch it.
    if any(pending["leaf_id"] == leaf_id for pending in oracles.get("pending_leaves", [])):
        raise OpenRule(f"{case_id} belongs to a pending leaf without an engine resolver")
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


# 4C.4b: the first-cut spell leaves (page-cited in 4C.4a) run the real spell owner in a fight on the test_spell_scope
# fixture. Only dice and d20s are fixed (patched); every number reported is the engine's own.

def _spell_fight(cls, level=1, *, cantrips=(), prepared=(), table=False, ability_score=16):
    import copy
    import character_progression
    import spell_scope
    from api.dnd_2024_rules import CLASS_DEFINITIONS, proficiency_bonus_for_level
    from api.tests.test_spell_scope import caster
    session, enemy = caster(cls=cls)
    character = session.character
    character.update(level=level, proficiency_bonus=proficiency_bonus_for_level(level),
                     **({"progression_level": level} if table else {}))
    character[CLASS_DEFINITIONS[cls]["spellcasting_ability"]] = ability_score
    state = session.world_state["spellcasting_v1"]
    if cantrips:
        state["cantrips"] = list(cantrips)
        character["cantrips"] = list(cantrips)
    if prepared:
        state["prepared"] = list(prepared)
    state["slots"] = character_progression.slot_capacity(character) or copy.deepcopy(CLASS_DEFINITIONS[cls]["spell_slots"])
    spell_scope.validate(state, character)
    enemy["speed_ft"] = 30
    return session, enemy


def _cast_with(session, spell, target, *, d20=None, dice=(), slot_level=None):
    from unittest.mock import patch
    import spell_scope
    with patch("game.roll_d20", return_value=d20 if d20 is not None else 10), \
            patch.object(session.rng, "randint", side_effect=list(dice) or [1] * 8):
        return spell_scope.cast(session, spell, target, slot_level)


def _until_next(session, actor):
    """Advance initiative until `actor` begins its next turn (no creature acts)."""
    for _ in range(12):
        session.advance_combat_turn()
        if session.world_state["combat"]["current_actor_id"] == actor:
            return
    raise AssertionError(f"{actor} never began a turn")


def _ray_of_frost(case):
    import action_economy
    import spell_scope
    given = case["input"]
    session, enemy = _spell_fight("Wizard", given["caster_level"], cantrips=["Ray of Frost"])
    before = action_economy.speed(session, enemy["id"])
    result = _cast_with(session, "Ray of Frost", enemy["id"], d20=19 if given["attack"] == "hit" else 1,
                        dice=given.get("dice_rolled", ()))
    penalty = before - action_economy.speed(session, enemy["id"])
    if not result["hit"]:
        return {"damage": result["damage"], "target_speed_penalty_ft": penalty}
    _until_next(session, enemy["id"])
    during_target_turn = spell_scope.speed_penalty(session, enemy["id"])
    _until_next(session, "player")
    until = ("start_of_caster_next_turn" if during_target_turn and not spell_scope.speed_penalty(session, enemy["id"])
             else "other")
    return {"damage": result["damage"], "damage_type": result["damage_type"], "target_speed_penalty_ft": penalty,
            "penalty_until": until}


def _shocking_grasp(case):
    import action_economy
    import spell_scope
    given = case["input"]
    session, enemy = _spell_fight("Wizard", given["caster_level"], cantrips=["Shocking Grasp"])
    enemy["distance_ft"] = 5
    session.world_state["attack_environment"]["pairs"][f"player|{enemy['id']}"]["distance_ft"] = 5
    result = _cast_with(session, "Shocking Grasp", enemy["id"], d20=19 if given["attack"] == "hit" else 1,
                        dice=given.get("dice_rolled", ()))
    can_oa = not spell_scope.opportunity_attacks_blocked(session, enemy["id"])
    if not result["hit"]:
        return {"damage": result["damage"], "target_can_make_opportunity_attacks": can_oa}
    if given.get("target_reaction") == "other_than_opportunity_attack":
        reacts = (action_economy.can_act(session, enemy["id"])
                  and not action_economy.ensure(session)[enemy["id"]]["reaction_spent"])
        return {"damage": result["damage"], "target_reaction_blocked": not reacts}
    _until_next(session, enemy["id"])
    until = "start_of_target_next_turn" if not spell_scope.opportunity_attacks_blocked(session, enemy["id"]) else "other"
    return {"damage": result["damage"], "damage_type": result["damage_type"],
            "target_can_make_opportunity_attacks": can_oa, "rider_until": until}


def _toll_the_dead(case):
    given = case["input"]
    session, enemy = _spell_fight("Cleric", given["caster_level"], cantrips=["Toll the Dead"])
    enemy.update(current_hp=given["target_hp"], max_hp=given["target_max_hp"])
    result = _cast_with(session, "Toll the Dead", enemy["id"], d20=2 if given["save"] == "fail" else 19,
                        dice=given.get("dice_rolled", ()))
    if not result["hit"]:
        return {"damage": result["damage"]}
    return {"die": result["damage_die"], "damage": result["damage"], "damage_type": result["damage_type"]}


def _healing_word(case):
    import action_economy
    given = case["input"]
    level = 3 if given["slot_level"] > 1 else 1
    session, _ = _spell_fight("Cleric", level, prepared=["Healing Word"], table=level > 1,
                              ability_score=10 + 2 * given["spellcasting_modifier"])
    session.character.update(max_hp=60, current_hp=10)
    result = _cast_with(session, "Healing Word", "player", dice=given["dice_rolled"], slot_level=given["slot_level"])
    economy = action_economy.ensure(session)["player"]
    resource = ("bonus_action" if economy["bonus_action_spent"] and not economy["base_action_spent"] else "other")
    return {"healing": result["healing"], "heal_source": result["heal_source"],
            "slot_spent": result["slot_level"] if result["slot_spent"] else 0, "resource": resource}


def _blessed_fight(bless=True):
    session, enemy = _spell_fight("Cleric", 1, prepared=["Bless", "Healing Word"])
    if bless:
        _cast_with(session, "Bless", "player")
    from weapon_catalog import lookup
    session.world_state["inventory"] = ["Mace"]
    session.world_state["equipment"] = {"main_hand": lookup("Mace")["weapon_id"], "off_hand": None}
    session.character.update(weapon_proficiencies=["simple"], conditions=[], current_hp=30, max_hp=30)
    enemy.update(distance_ft=5, armor_class=12)
    session.world_state["attack_environment"]["pairs"][f"player|{enemy['id']}"]["distance_ft"] = 5
    _until_next(session, "player")  # a fresh Action for the roll (Bless spent this turn's)
    return session, enemy


def _bless_total(session, enemy, roll, bless_die):
    """The engine's total for one roll of this kind with a fixed d20 and Bless d4."""
    from unittest.mock import patch
    import weapon_attack
    with patch("game.roll_d20", return_value=10), patch.object(session.rng, "randint", return_value=bless_die):
        if roll == "attack_roll":
            return weapon_attack.resolve(session, "player", enemy["id"], "Mace")["attack_total"]
        if roll == "saving_throw":
            return weapon_attack.save(session, "player", ["wisdom"], 10)["total"]
        modifiers = {name: (session.character.get(name, 10) - 10) // 2 for name in
                     ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")}
        result = session.perform_skill_check("Athletics", 10, modifiers, [], session.character["proficiency_bonus"])
        return result["resolution"]["total"]


def _bless(case):
    import spell_concentration
    given = case["input"]
    if given.get("op") == "max_targets":
        return {"targets": spell_concentration.bless_max_targets(given["slot_level"])}
    with_bless = _blessed_fight()
    if given.get("concentration") == "lost":
        import spell_scope
        spell_scope.end_concentration(with_bless[0])
    added = (_bless_total(*with_bless, given["roll"], given["bless_die"])
             - _bless_total(*_blessed_fight(bless=False), given["roll"], given["bless_die"]))
    return {"total": given["d20_total"] + added}


def _concentration(case):
    from unittest.mock import patch
    import action_economy
    import spell_concentration
    given = case["input"]
    if given["op"] == "save_dc":
        return {"dc": spell_concentration.save_dc(given["damage"])}
    session, enemy = _blessed_fight()
    held = spell_concentration.current(session.world_state)
    if given["op"] == "damage_save":
        session.character.setdefault("modifiers", {})["constitution"] = 0
        session.character.setdefault("saving_throw_mods", {})["constitution"] = 0
        # The held spell is Bless: its d4 (fixed at 1) is part of this save's total.
        with patch("game.roll_d20", return_value=given["save_total"] - 1), patch.object(session.rng, "randint", return_value=1):
            check = session._apply_attack_damage_to_player(given["damage"], False, True)["concentration_check"]
        if check["total"] != given["save_total"]:
            raise AssertionError("the save total is not the case's total")
        return {"kept": check["kept"]}
    if given["op"] == "start_casting":
        _until_next(session, "player")
        _cast_with(session, given["holding"] if given["casting_requires_concentration"] else "Healing Word", "player")
    elif given["op"] == "condition":
        session.character["conditions"] = [given["condition"]]
        spell_concentration.settle(session)
    elif given["op"] == "dies":
        session._apply_attack_damage_to_player(1000, False, True)
    elif given["op"] == "end_voluntarily":
        before = dict(action_economy.ensure(session)["player"])
        action_economy.execute(session, {"steps": [{"kind": "end_concentration"}]})
        after = action_economy.ensure(session)["player"]
        spent = any(after[key] != before[key] for key in ("base_action_spent", "bonus_action_spent", "reaction_spent"))
        return {"kept": spell_concentration.current(session.world_state) == held, "action_spent": spent}
    return {"kept": spell_concentration.current(session.world_state) == held}

DISPATCH = {
    "4C.spell.ray_of_frost": _ray_of_frost,
    "4C.spell.shocking_grasp": _shocking_grasp,
    "4C.spell.toll_the_dead": _toll_the_dead,
    "4C.spell.healing_word": _healing_word,
    "4C.spell.bless": _bless,
    "4C.concentration": _concentration,
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
            "actual": actual, "match": actual == case["expected"], "source_ref": case.get("source_ref", leaf["source_ref"])}

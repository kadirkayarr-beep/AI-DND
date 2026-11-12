"""Dilim 4C Task 4b, part 1: the must-fix parks of the independent 4C.4a review.

(a) a case of a pending (resolver-less) oracle leaf is an OPEN rule, never a KeyError; (b) the surrendered-foe question
is bound per target and per blow: one "evet" passes only the creatures and the blow it asked about; (c) the spell rules
kernel `spell_registry.cast_spell` has no product caller (the player's casts go through the gated turn path); (d) a typed
weapon blow's "evet" needs no model over HTTP, and a healing or a different spell typed after the question is handled
truthfully; (g) D-038 stays unreachable (no cast outside a fight) and the preparation view answers 409, not 500, on an
unreadable saved state. Engine tests on the 4C.0 fixture (fixed session seed); HTTP on the C19 Quickened harness
(fixed street via CampaignApiTests.asyncSetUp)."""
from __future__ import annotations

import copy
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import combat_lifecycle
import game
import living_world
import monster_combat
import rule_oracles
import spell_preparation
import spell_scope
from api.tests import test_dilim4b_combat_xp as t1
from api.tests import test_spell_scope as scope_fixtures
from api.tests.test_dilim4c_surrender_spells import become, caster_fight, held, magic
from api.tests.test_dilim4c_surrender_spells_http import SurrenderedSpellHttp

AI_DND = Path(__file__).resolve().parents[2]  # the ai-dnd package root


class PendingOracleCasesAreOpen(unittest.TestCase):
    """(a) `_case` matched open rules by substring: `spell_bless` is not inside `4C.spell.bless#01`, so a KeyError."""

    def synthetic(self):
        oracles = copy.deepcopy(rule_oracles.load_oracles())
        oracles["pending_leaves"] = [{"leaf_id": "4C.spell.tripwire", "open_rule": "spell_tripwire",
                                      "cases": [{"id": "01", "kind": "normal", "input": {}, "expected": {}}]}]
        oracles["open_leaves"].append({"family": "spell", "rule": "spell_tripwire", "status": "OPEN", "reason": "test"})
        return oracles

    def test_a_pending_leaf_case_raises_open_rule(self):
        with self.assertRaises(rule_oracles.OpenRule):
            rule_oracles.evaluate_rule_case("4C.spell.tripwire#01", self.synthetic())

    def test_every_case_of_every_pending_leaf_is_open(self):
        oracles = rule_oracles.load_oracles()
        for leaf in oracles.get("pending_leaves", []):
            for case in leaf["cases"]:
                with self.subTest(leaf=leaf["leaf_id"], case=case["id"]):
                    with self.assertRaises(rule_oracles.OpenRule):
                        rule_oracles.evaluate_rule_case(f"{leaf['leaf_id']}#{case['id']}", oracles)

    def test_an_unknown_case_is_still_a_key_error(self):
        with self.assertRaises(KeyError):
            rule_oracles.evaluate_rule_case("4C.spell.no_such_leaf#01", self.synthetic())


def surrender(s, foe):
    """Plant the fight's accepted SURRENDER for this foe (the 4C.0 saved record) and re-read the participant records."""
    cid = s.world_state["combat"]["combat_id"]
    monster_combat.state(s, foe["id"]).setdefault("proposals", []).append(
        {"proposal_id": f"{cid}:1:{foe['id']}:0:SURRENDER_PROPOSED", "type": "SURRENDER_PROPOSED",
         "status": "accepted", "actor_id": foe["id"]})
    s._sync_combat_participant_records(s.world_state["combat"])


def three_foes():
    """n surrendered, `other` fighting (keeps the fight going), `third` surrendered too."""
    s, n, other = caster_fight()
    third = t1.person("brute2", "muhafız", distance_ft=5)
    s.world_state["npcs"].append(third)
    with patch("game.roll_initiative", return_value=1):
        s.join_combat_participants([third["id"]])
    surrender(s, third)
    assert s.world_state["combat"]["active"]
    return s, n, other, third


def blows(*targets):
    return {"steps": [{"kind": "attack", "target_id": t} for t in targets]}


class QuestionIsBoundPerTarget(unittest.TestCase):
    """(b) the question named only the first surrendered target, and one yes passed the whole command."""

    def test_a_command_at_two_surrendered_foes_asks_about_both(self):
        s, n, other, third = three_foes()
        result = combat_lifecycle.surrendered_strike_question(s, "Hamle.", None, blows(n["id"], third["id"]))
        self.assertEqual(result["action_result"]["outcome"], "surrendered_target")
        self.assertEqual(s._surrender_strike_asked["ids"], [n["id"], third["id"]])
        names = [living_world.public_npc_name(foe) for foe in (n, third)]
        self.assertTrue(result["narration"].startswith(f"{names[0]} ve {names[1]} teslim oldu;"), result["narration"])

    def test_a_yes_about_one_foe_does_not_pass_a_blow_at_another(self):
        s, n, other, third = three_foes()
        self.assertIsNotNone(combat_lifecycle.surrendered_strike_question(s, "Hamle.", None, blows(n["id"])))
        again = combat_lifecycle.surrendered_strike_question(s, "Hamle.", None, blows(n["id"], third["id"]))
        self.assertIsNotNone(again)  # third was never asked about
        self.assertIn(third["id"], s._surrender_strike_asked["ids"])

    def test_the_asked_command_again_passes(self):
        s, n, other, third = three_foes()
        command = blows(n["id"], third["id"])
        combat_lifecycle.surrendered_strike_question(s, "Hamle.", None, command)
        self.assertIsNone(combat_lifecycle.surrendered_strike_question(s, "Hamle.", None, command))

    def test_a_fighting_foe_in_the_command_is_not_asked_about(self):
        s, n, other, third = three_foes()
        combat_lifecycle.surrendered_strike_question(s, "Hamle.", None, blows(other["id"], n["id"]))
        self.assertEqual(s._surrender_strike_asked["ids"], [n["id"]])

    def test_the_gate_reads_harm_from_the_spell_owner_not_a_tuple_shape(self):
        self.assertTrue(spell_scope.harmful("Fire Bolt"))
        self.assertFalse(spell_scope.harmful("Cure Wounds"))
        self.assertFalse(spell_scope.harmful("No Such Spell"))
        with patch.dict(spell_scope.CATALOG, {"Test Bolt": (0, 60, 8, "fire", "extra")}):
            self.assertTrue(spell_scope.harmful("Test Bolt"))


class QuestionIsBoundPerBlow(unittest.TestCase):
    """(d) engine half: what is typed after the question."""

    def test_a_different_harmful_spell_after_the_question_is_asked_again(self):
        s, n, other = caster_fight()
        s.run_player_turn("Hamle.", combat_action=magic("Fire Bolt", n["id"]))
        before = held(s)
        result = s.run_player_turn("Hamle.", combat_action=magic("Magic Missile", n["id"]))
        self.assertEqual(result["action_result"]["outcome"], "surrendered_target")
        self.assertEqual(held(s), before)  # no slot spent, no damage

    def test_a_weapon_blow_after_a_spell_question_is_asked_again(self):
        s, n, other = caster_fight()
        s.run_player_turn("Hamle.", combat_action=magic("Fire Bolt", n["id"]))
        result = s.run_player_turn("Hamle.", combat_action=blows(n["id"]))
        self.assertEqual(result["action_result"]["outcome"], "surrendered_target")
        self.assertEqual(n["current_hp"], 10)

    def test_healing_typed_after_the_question_heals_and_forgets_the_question(self):
        s, n, other = caster_fight()
        become(s, "Bard")
        s.run_player_turn("Muhafıza saldırıyorum", target_id=n["id"])
        self.assertIsNotNone(s._surrender_strike_asked)
        s.character["current_hp"] = 5
        with patch.object(s.rng, "randint", return_value=4):
            healed = s.run_player_turn("Yara iyileştirme büyüsünü kendime yapıyorum")
        self.assertEqual(healed["action_result"]["status"], "resolved")
        self.assertEqual(healed["action_result"]["spell"], "Cure Wounds")
        self.assertGreater(s.character["current_hp"], 5)
        self.assertIsNone(s._surrender_strike_asked)
        self.assertIsNone(combat_lifecycle.answered_surrender_question(s, "evet"))
        self.assertEqual(n["current_hp"], 10)


class SpellKernelHasNoProductCaller(unittest.TestCase):
    """(c) `spell_registry.cast_spell` calls `spell_scope.cast` with no surrender gate; it is a rules kernel with no
    product caller. The player's casts (typed, button, HTTP) reach `spell_scope.cast` only through the gated turn path.
    A new product caller must add the gate first: this tripwire names it."""

    def test_no_module_outside_tests_calls_cast_spell(self):
        callers = []
        self.assertTrue((AI_DND / "spell_scope.py").is_file())  # the scan must look at the real package
        for path in AI_DND.rglob("*.py"):
            relative = path.relative_to(AI_DND).as_posix()
            if "/tests/" in f"/{relative}" or path.name.startswith("test_") or relative == "spell_registry.py":
                continue
            if re.search(r"\bcast_spell\s*\(", path.read_text(encoding="utf-8", errors="replace")):
                callers.append(relative)
        self.assertEqual(callers, [])

    def test_spell_scope_cast_is_reached_only_from_the_gated_magic_step(self):
        callers = []
        self.assertTrue((AI_DND / "spell_scope.py").is_file())  # the scan must look at the real package
        for path in AI_DND.rglob("*.py"):
            relative = path.relative_to(AI_DND).as_posix()
            if "/tests/" in f"/{relative}" or path.name.startswith("test_") or relative in {"spell_scope.py", "spell_registry.py"}:
                continue
            if re.search(r"\bspell_scope\.cast\s*\(", path.read_text(encoding="utf-8", errors="replace")):
                callers.append(relative)
        # rule_oracles runs the real cast for the K07 spell leaves (an oracle harness on test fixtures, never a turn).
        self.assertEqual(sorted(callers), ["action_economy.py", "rule_oracles.py"])


class D038HasNoReachableCast(unittest.TestCase):
    """(g) D-038: re-preparing after a cast while the clock stands still needs a cast outside a fight. A slot spell outside
    a fight is still refused (below); the narrative cantrips of 4C.5 cast outside a fight but need no prepared list, so
    they leave the window open (test_dilim4c_5_narrative_spells.D038CantripLeavesTheWindows)."""

    def test_a_cast_outside_combat_is_refused_and_the_long_rest_window_stands(self):
        s, enemy = scope_fixtures.caster(cls="Cleric")
        s.end_combat("test_setup")
        state = s.world_state["spellcasting_v1"]
        state["prepared"] = ["Cure Wounds"]
        state["prepare_window"] = {"opened_second": spell_scope.clock_second(s.world_state), "reason": "long_rest"}
        s.character["current_hp"] = 3
        before = copy.deepcopy((s.world_state, s.character))
        with self.assertRaises(combat_lifecycle.CombatRequestError) as raised:
            spell_scope.cast(s, "Cure Wounds", "player")
        self.assertEqual(raised.exception.code, "unsupported_spell_mode")
        self.assertEqual(copy.deepcopy((s.world_state, s.character)), before)
        self.assertTrue(spell_preparation.window_open(s))

    def test_a_fight_closes_the_long_rest_window_before_any_cast(self):
        s, enemy = scope_fixtures.caster(cls="Cleric")
        s.end_combat("test_setup")
        s.world_state["spellcasting_v1"]["prepare_window"] = {
            "opened_second": spell_scope.clock_second(s.world_state), "reason": "long_rest"}
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            s.start_combat(enemy)
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertIsNone(s.world_state["spellcasting_v1"]["prepare_window"])


class ReviewFixesHttp(unittest.IsolatedAsyncioTestCase):
    """The 4C.4a HTTP harness, borrowed (not inherited, so its own test does not run twice)."""
    asyncSetUp = SurrenderedSpellHttp.asyncSetUp
    asyncTearDown = SurrenderedSpellHttp.asyncTearDown
    create_campaign = SurrenderedSpellHttp.create_campaign
    encounter = SurrenderedSpellHttp.encounter
    post = SurrenderedSpellHttp.post
    snapshot = SurrenderedSpellHttp.snapshot
    surrendered = SurrenderedSpellHttp.surrendered

    async def test_a_typed_weapon_yes_needs_no_model(self):
        a, r, command, rakip, other = await self.surrendered()
        s = r.game_session
        npc = next(n for n in s.world_state["npcs"] if n["id"] == rakip)
        asked = await self.post(a, {"message": "Rakip'e saldırıyorum", "action_id": str(uuid4()), "target_id": rakip})
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertIn("teslim olmuş birine saldırıyorsun", asked.json()["narration"])
        self.assertEqual(npc["current_hp"], 100)

        self.app.state.ollama_adapter = None
        yes = {"message": "evet", "action_id": str(uuid4()), "target_id": other["id"]}
        with patch("api.tests.test_campaign_api.FakeOllamaClient.chat",
                   side_effect=AssertionError("the answer called the model")) as chat, \
                patch("game.roll_d20", return_value=19):
            struck = await self.post(a, yes)
        chat.assert_not_called()
        self.assertEqual(struck.status_code, 200, struck.text)
        self.assertNotEqual(struck.json()["combat_result"].get("status"), "clarification")
        self.assertEqual(struck.json()["combat_result"].get("target_id"), rakip)
        self.assertEqual(other["current_hp"], 30)

    async def test_the_preparation_view_answers_409_on_an_unreadable_state(self):
        a, r, command, rakip, other = await self.surrendered()
        r.game_session.world_state["spellcasting_v1"]["slots"] = "broken"
        view = await self.http.get(f"/api/game/sessions/{a['session_id']}/spellcasting/prepare")
        self.assertEqual(view.status_code, 409, view.text)
        self.assertEqual(view.json()["detail"]["code"], "prepare_unavailable")


if __name__ == "__main__":
    unittest.main()

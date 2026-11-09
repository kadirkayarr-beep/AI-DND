"""Task 38: in a fight the player's words are the move made (H241, H123, H124, H131, H132, H239).

A blow asked about is the asked line's blow, never the weapon that happens to be in hand; a shove tells its save; going
on the defensive is Dodge; a readied reaction tells what it did; a fired crossbow at the one being fought rolls; a
long yes still answers the question. Real app, real engine; only the model client is scripted.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import action_economy
import equipment_economy
import game
from api.tests import test_combat_lifecycle as lifecycle
from api.tests import test_front_proposal as front_table
from api.tests.town_seed import fixed_town

CROSSBOW = "Ağır Tatar Yayı & 20 Ok"


class AskedBlowsAreTheAskedMove(unittest.IsolatedAsyncioTestCase):
    # FrontTable's harness without its own tests (a subclass would run them all again)
    asyncSetUp = front_table.FrontTable.asyncSetUp
    asyncTearDown = front_table.FrontTable.asyncTearDown
    campaign_with_npc = front_table.FrontTable.campaign_with_npc
    open_job = front_table.FrontTable.open_job
    line = front_table.FrontTable.line

    async def begin(self, **kwargs):
        with fixed_town(self, 3801):
            await front_table.FrontTable.begin(self, **kwargs)
        self.npc.update(armor_class=10, max_hp=40, current_hp=40)
        self.session.character.update(max_hp=300, current_hp=300)
        self.world["inventory"] = ["Greatsword", CROSSBOW, "Macera Çantası"]
        self.world["equipment"] = {"main_hand": None, "off_hand": None}
        equipment_economy.materialize(self.world)
        crossbow = next(item for item in self.world["inventory"] if item["name"] == CROSSBOW)
        self.world["equipment"]["main_hand"] = crossbow["item_id"]  # the crossbow is what is in hand (H241)

    def players_last_attack(self):
        return [row for row in self.world["attack_results"] if row["actor"] == "player"][-1]

    async def ask(self, line):
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
        reply = await self.line(line, "Ne yapıyorsun sen?")
        self.assertEqual(reply["turn_outcome"]["status"], "clarification", reply["narration"])
        self.assertIn("kavga", reply["narration"])
        return reply

    async def test_a_trip_said_yes_to_rolls_nothing_until_the_real_move_is_chosen(self):
        # H241 (review B1): 'çelme takıp düşürmeye çalışıyorum' - 'Evet.' was a crossbow shot, then a damaging punch.
        # The engine has no trip: a yes to a line naming no move it reads asks Shove or punch, and nothing rolls.
        await self.begin()
        self.npc.update(max_hp=4, current_hp=4)
        await self.ask("Marek'e çelme takıp yere düşürmeye çalışıyorum")
        reply = await self.line("Evet.")
        self.assertEqual(reply["turn_outcome"]["status"], "clarification", reply["narration"])
        self.assertIn("yumruk", reply["narration"])
        self.assertIn("itiyorum", reply["narration"])
        self.assertEqual(self.npc["current_hp"], 4)
        self.assertFalse(self.world["combat"]["active"])
        self.assertFalse([row for row in self.world.get("attack_results", []) if row["actor"] == "player"])
        reply = await self.line("itiyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(self.players_last_attack()["unarmed_option"], "shove")
        self.assertEqual(self.npc["current_hp"], 4)

    async def test_a_punch_chosen_after_the_trip_question_is_bare_hands_not_the_crossbow(self):
        await self.begin()
        await self.ask("Marek'e çelme takıp yere düşürmeye çalışıyorum")
        await self.line("Evet.")
        reply = await self.line("yumruk atıyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(reply["combat_result"]["weapon"], "Unarmed Strike")
        self.assertNotIn("ranged_in_close_combat", reply["combat_result"].get("disadvantage_sources") or [])

    async def test_an_answer_to_the_trip_question_naming_no_move_starts_nothing(self):
        await self.begin()
        await self.ask("Marek'e çelme takıp yere düşürmeye çalışıyorum")
        await self.line("Evet.")
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("boşver, konuşalım", "Peki.")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertFalse(self.world["combat"]["active"])

    async def test_the_yes_carries_the_asked_words(self):
        # The asked line said a shove; 'Evet.' alone must not lose it to the weapon in hand.
        await self.begin()
        await self.ask("Marek'i duvara doğru itiyorum")
        reply = await self.line("Evet.")
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(self.players_last_attack()["unarmed_option"], "shove")

    async def test_a_long_yes_still_answers_the_question(self):
        # H239: 'Evet, iri yarı adamı itiyorum.' (five words) was lost and became talk.
        await self.begin()
        await self.ask("Marek'i itip yere devirmeye çalışıyorum")
        reply = await self.line("Evet, şu adamı sertçe itiyorum.")
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(reply["turn_outcome"]["target_name"], self.npc["name"])

    async def test_a_long_answer_that_takes_it_back_starts_nothing(self):
        await self.begin()
        await self.ask("Marek'i itip yere devirmeye çalışıyorum")
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("evet ama itmiyorum, sadece bakıyorum", "Peki.")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertFalse(self.world["combat"]["active"])

    async def test_a_shove_tells_its_save_not_zero_damage(self):
        # H123: the shove was a Strength save the narration never showed: 'bir darbe alır: 0 hasar'.
        await self.begin()
        await self.ask("Marek'i itip yere devirmeye çalışıyorum")
        reply = await self.line("Evet, şu adamı sertçe itiyorum.")
        shove = self.players_last_attack()
        self.assertEqual(shove["unarmed_option"], "shove")
        self.assertNotIn("0 hasar", reply["narration"])
        save = shove["resolution"]
        self.assertIn(f"DC {save['dc']}", reply["narration"])
        self.assertIn(str(save["total"]), reply["narration"])

    async def test_a_crossbow_fired_at_the_one_being_fought_rolls(self):
        # H132: in a fight, with the target chosen, 'tatar yayımı ... ateş ediyorum' went to the narrator: no roll.
        await self.begin()
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"], "thing_word": "yumruk"}
        first = await self.line("Marek'e bir yumruk atıyorum", "Ne yapıyorsun sen?")
        self.assertEqual(first["turn_outcome"]["action"], "attack", first["narration"])
        self.assertTrue(self.world["combat"]["active"], first["narration"])
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
        reply = await self.line("Ağır tatar yayımı Marek'in bacağına doğrultup ateş ediyorum", target=True)
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(reply["combat_result"]["weapon"], "Heavy Crossbow")
        self.assertIsNotNone(reply["combat_result"]["attack_roll"])

    async def test_a_blow_on_the_chosen_opponent_stays_on_them_whoever_else_the_words_name(self):
        # Review M3: with the opponent chosen in the UI, the strike keeps that id even when the words name someone else.
        await self.begin()
        sera = next(npc for npc in self.world["npcs"] if npc["id"] == "npc_private_sera")
        sera.update(name_known_to_player=True, armor_class=10, max_hp=40, current_hp=40, combat_status="active")
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"], "thing_word": "yumruk"}
        await self.line("Marek'e bir yumruk atıyorum", "Ne yapıyorsun sen?")
        self.assertTrue(self.world["combat"]["active"])
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
        reply = await self.line("Sera bakarken tatar yayımı doğrultup ateş ediyorum", target=True)
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(self.players_last_attack()["target_id"], self.npc["id"])
        self.assertEqual(sera["current_hp"], 40)


class TheFightsOwnMoves(unittest.TestCase):
    def fight(self):
        session, npc = lifecycle.ready()
        token = game._ACTIVE_SESSION.set(session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        return session, npc

    def test_going_on_the_defensive_is_dodge_where_the_attacker_is_known_seen(self):
        # H124: 'Savunmaya geçiyorum' only ended the turn; Dodge was never applied.
        session, npc = self.fight()
        # NOT the town-fight setup: this test writes the sight fact itself, because Dodge's attack Disadvantage needs
        # the attacker seen (K07 leaf). Town fights never write it (review I1, parked); see the test below.
        session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})[f"{npc['id']}|player"] = {
            "distance_ft": 5, "attacker_sees_target": True, "target_sees_attacker": True}
        command = action_economy.natural_command(session, "Savunmaya geçiyorum.")
        self.assertEqual(command["steps"][0]["kind"], "dodge")
        result = action_economy.execute(session, command)
        steps = result["action_result"]["economy_steps"]
        blows = [enemy for step in steps for enemy in step.get("enemy_actions") or []
                 if enemy.get("action") == "enemy_attack"]
        self.assertTrue(blows, result["narration"])
        self.assertIn("target_dodging", blows[0]["disadvantage_sources"])
        self.assertIn("Dodge", result["narration"])

    def test_in_a_town_fight_dodge_gives_only_the_dexterity_save_advantage(self):
        # Review I1 (parked, K07 Dodge owner): no sight fact is written in a plain fight, so attacks roll normally;
        # the Dexterity-save Advantage is what Dodge gives here, and the narration claims nothing more.
        import weapon_attack
        session, npc = self.fight()
        action_economy.execute(session, {"steps": [{"kind": "dodge"}]})
        with patch.object(session, "roll_d20", side_effect=[1, 20]) as roll:
            saved = weapon_attack.save(session, "player", ("dexterity",), 12)
        self.assertEqual((roll.call_count, saved["outcome"]), (2, "SUCCESS"))
        result = action_economy.execute(session, {"steps": [{"kind": "end_turn"}]})
        blows = [enemy for step in result["action_result"]["economy_steps"] for enemy in step.get("enemy_actions") or []
                 if enemy.get("action") == "enemy_attack"]
        self.assertTrue(blows, result["narration"])
        self.assertNotIn("target_dodging", blows[0]["disadvantage_sources"])

    def test_the_typed_dodge_step_is_the_dodge_action(self):
        # Review M5: the API's own step, through the schema and the turn owner.
        from api.schemas import CombatActionInput
        session, _ = self.fight()
        command = CombatActionInput.model_validate({"steps": [{"kind": "dodge"}]}).model_dump(exclude_none=True)
        result = session.run_player_turn("Hamle.", combat_action=command)
        self.assertEqual(result["action_result"]["economy_steps"][0]["kind"], "dodge")
        self.assertTrue(action_economy.ensure(session)["player"]["dodging"])
        self.assertIn("Dodge", result["narration"])

    def test_no_action_left_is_no_dodge_and_says_so(self):
        session, npc = self.fight()
        action_economy.consume_action(session, "player", "dash")  # the Action went on something else
        command = action_economy.natural_command(session, "Savunmaya geçiyorum.")
        self.assertEqual([step["kind"] for step in command["steps"]], ["end_turn"])
        result = action_economy.execute(session, command)
        self.assertIn("Dodge için eylemin kalmadı", result["narration"])

    def test_the_word_dodge_is_the_dodge_action_and_a_save_keeps_it(self):
        session, _ = self.fight()
        command = action_economy.natural_command(session, "Dodge kullanıyorum.")
        self.assertEqual(command["steps"], [{"kind": "dodge"}])
        action_economy.execute(session, command)
        self.assertTrue(action_economy.ensure(session)["player"]["dodging"])
        payload = session.serialize_game_state()
        game._validate_save_payload(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dodge.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            session.load_game(path)
        player = action_economy.ensure(session)["player"]
        self.assertEqual((player["dodging"], player["base_action_spent"]), (True, True))

    def test_waiting_is_still_only_the_end_of_the_turn(self):
        session, _ = self.fight()
        self.assertEqual(action_economy.natural_command(session, "bekliyorum")["steps"], [{"kind": "end_turn"}])

    def test_a_readied_reaction_tells_what_it_did(self):
        # H131: 'Hazırladığım tepkiyi kullanıyorum' said only 'Hazırladığın tepkiyi uygularsın.'
        session, npc = self.fight()
        action_economy.prepare_ready(session, "player", trigger={"event": "actor_moves", "actor_id": npc["id"]},
                                     response={"kind": "attack", "target_id": npc["id"]})
        session.advance_combat_turn()
        npc["speed_ft"] = 30
        action_economy.move(session, npc["id"], 5)
        identity = action_economy.ensure(session)["player"]["opportunity"]["id"]
        with patch("game.roll_attack", return_value=1):
            result = action_economy.execute(session, {"steps": [{"kind": "react", "opportunity_id": identity}]})
        self.assertIn("ıskalar", result["narration"])

    def test_a_readied_move_is_told_too(self):
        # Review M5: a readied move response is narrated with its distance.
        session, npc = self.fight()
        action_economy.prepare_ready(session, "player", trigger={"event": "actor_moves", "actor_id": npc["id"]},
                                     response={"kind": "move", "distance_ft": 10})
        session.advance_combat_turn()
        npc["speed_ft"] = 30
        action_economy.move(session, npc["id"], 5)
        identity = action_economy.ensure(session)["player"]["opportunity"]["id"]
        result = action_economy.execute(session, {"steps": [{"kind": "react", "opportunity_id": identity}]})
        self.assertIn("Hazırladığın tepkiyi uygularsın. 10 feet ilerlersin.", result["narration"])

    def test_a_push_that_did_not_apply_gives_no_reason_the_engine_does_not_know(self):
        # Review M2: the engine knew no position, not that there was no room.
        result = {"unarmed_option": "shove", "outcome": "hit", "target_name": "Marek",
                  "resolution": {"ability": "strength", "total": 5, "dc": 13, "outcome": "FAILURE"},
                  "additional_effects": [{"kind": "push", "applied": False, "reason": "position_unresolved_or_blocked"}]}
        text = game._combat_narration(result)
        self.assertNotIn("itecek yer yok", text)
        self.assertIn("itme uygulanamadı", text)


if __name__ == "__main__":
    unittest.main()

"""Explicit turn completion uses real scheduling, not mocked combat receipts."""
import copy
import unittest
from unittest.mock import patch

from api.tests import test_action_economy as economy_tests
from api.tests.test_campaign_time import scene
from api.tests.test_initiative import battle
from api.tests.test_spell_scope import caster
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


from api.tests.auth_fixture import TEST_PLAYER
def opponents(session):
    """Three supported legacy Python NPC attacks, not Monster Manual imports."""
    npcs = []
    for name in ("Birinci muhafız", "İkinci muhafız", "Üçüncü muhafız"):
        npc = session.create_npc_from_ai(
            {"name": name, "role": "Guard", "location": "tavern"}
        )
        npc.update(name_known_to_player=True, current_hp=100, max_hp=100, hostile=True, distance_ft=5,
                   attack_damage_type="bludgeoning", initiative_modifier=0)
        npcs.append(npc)
        session.world_state.setdefault("monster_perception", {})[npc["id"]] = {
            "player": {"visible": True}
        }
    session.character.update(current_hp=100, max_hp=100, armor_class=12)
    with patch("game.roll_d20", side_effect=[20, 3, 2, 1]):
        session.start_combat(npcs[0])
    return npcs


def assert_exchange(test, result, session, npcs):
    actions = result["action_result"]["economy_steps"][-1]["enemy_actions"]
    test.assertEqual([a["actor_id"] for a in actions], [n["id"] for n in npcs])
    test.assertEqual([a["outcome"] for a in actions], ["miss", "hit", "critical_hit"])
    test.assertEqual([a["damage"] for a in actions], [0, 4, 4])
    narration = result["narration"]
    sentences = [
        f"{npcs[0]['name']} adlı rakibinin karşı saldırısı seni ıskalar.",
        f"{npcs[1]['name']} adlı rakibinin karşı saldırısı sana isabet eder; 4 hasar alırsın.",
        f"{npcs[2]['name']} adlı rakibinin kritik karşı saldırısı sana isabet eder; 4 hasar alırsın.",
        "Bilincin açık; 92/100 canın kaldı.",
    ]
    positions = [narration.index(sentence) for sentence in sentences]
    test.assertEqual(positions, sorted(positions))
    for sentence in sentences:
        test.assertEqual(narration.count(sentence), 1)
    test.assertNotIn("Saldırın hedefi", narration)
    test.assertEqual(session.character["current_hp"], 92)
    test.assertEqual(session.world_state["combat"]["current_actor_id"], "player")
    test.assertEqual(session.world_state["combat"]["round"], 2)
    test.assertEqual(result["model_calls"], 0)


class EndTurnNarrationTests(unittest.TestCase):
    def test_spell_narration_does_not_hide_the_explicit_end_turn_exchange(self):
        session, _ = caster(scene())
        session.end_combat()
        session.world_state["npcs"] = []
        npcs = opponents(session)
        session.world_state["attack_environment"] = {"pairs": {
            "player|" + npcs[0]["id"]: {
                "distance_ft": 5, "attacker_sees_target": True,
                "target_sees_attacker": True, "cover": "none",
            },
        }}
        with patch("game.roll_d20", side_effect=[1, 15, 20]), \
             patch("game.roll_damage", return_value=4), \
             patch.object(session.rng, "randint", return_value=2):
            result = session.run_player_turn("Hamle.", combat_action={"steps": [
                {"kind": "magic", "ability": "Magic Missile", "target_id": npcs[0]["id"]},
                {"kind": "end_turn"},
            ]})
        self.assertLess(result["narration"].index("Magic Missile"),
                        result["narration"].index("Turunu bitirirsin."))
        assert_exchange(self, result, session, npcs)

    def test_structured_and_natural_end_turn_show_all_attacks_in_order(self):
        for message, command in (
            ("Hamle.", {"steps": [{"kind": "end_turn"}]}),
            ("Turumu bitiriyorum", None),
            ("end turn", None),
        ):
            with self.subTest(message=message):
                session = scene()
                npcs = opponents(session)
                with patch("game.roll_d20", side_effect=[1, 15, 20]), \
                     patch("game.roll_damage", return_value=4):
                    result = session.run_player_turn(message, combat_action=command)
                assert_exchange(self, result, session, npcs)

    def test_final_status_follows_scheduler_death_save_and_damage_results(self):
        for status, hp, maximum, damage, rolls, stable, expected in (
            ("unconscious", 1, 100, 4, [15, 10, 1, 1, 10, 1, 1, 10], True, "Bilincini kaybedersin."),
            ("dead", 1, 4, 8, [15], False, "Ölürsün."),
            ("active", 1, 100, 4, [15, 20], False, "Bilincin açık; 1/100 canın kaldı."),
        ):
            with self.subTest(status=status):
                session, npcs = battle(player={"current_hp": hp, "max_hp": maximum, "armor_class": 12})
                session.world_state["death_state"]["mode"] = "PERMADEATH"
                session.world_state["monster_perception"] = {
                    npcs[0]["id"]: {"player": {"visible": True}}
                }
                with patch("game.roll_d20", side_effect=rolls), \
                     patch("game.roll_damage", return_value=damage):
                    result = session.run_player_turn(
                        "Hamle.", combat_action={"steps": [{"kind": "end_turn"}]}
                    )
                actions = result["action_result"]["economy_steps"][0]["enemy_actions"]
                self.assertEqual(actions[0]["outcome"], "hit")
                self.assertIn(f"{damage} hasar alırsın.", result["narration"])
                self.assertTrue(result["narration"].endswith(expected), result["narration"])
                self.assertEqual(session.world_state["player_combat_status"], status)
                self.assertEqual(session.world_state["death_state"]["stable"], stable)
                self.assertEqual(session.character["current_hp"], 1 if status == "active" else 0)
                if status != "dead":
                    saves = [a for a in actions if a["action"] == "death_save"]
                    self.assertEqual(saves[-1]["outcome"], "stable" if stable else "revived")
                self.assertEqual(result["model_calls"], 0)

    def test_third_successful_death_save_stops_before_another_enemy_attack(self):
        for next_attack_roll in (1, 15):
            for message, command in (
                ("Hamle.", {"steps": [{"kind": "end_turn"}]}),
                ("Turumu bitiriyorum", None),
            ):
                with self.subTest(next_attack_roll=next_attack_roll, message=message):
                    session, npcs = battle(player={
                        "current_hp": 1, "max_hp": 100, "armor_class": 12,
                    })
                    session.world_state["death_state"]["mode"] = "PERMADEATH"
                    session.world_state["monster_perception"] = {
                        npcs[0]["id"]: {"player": {"visible": True}}
                    }
                    combat = session.world_state["combat"]
                    order = copy.deepcopy(combat["initiative_order"])
                    initiative_results = copy.deepcopy(combat["initiative_results"])
                    # Hit to knock out, then three successful saves with two
                    # intervening misses (advantage against an unconscious target).
                    rolls = [15, 10, 1, 1, 10, 1, 1, 10]
                    with patch("game.roll_d20", side_effect=(
                        rolls + [next_attack_roll, next_attack_roll]
                    )) as roller, patch("game.roll_damage", return_value=4):
                        result = session.run_player_turn(message, combat_action=command)
                    actions = result["action_result"]["economy_steps"][0]["enemy_actions"]
                    self.assertEqual([a["action"] for a in actions], [
                        "enemy_attack", "death_save", "enemy_attack", "death_save",
                        "enemy_attack", "death_save",
                    ])
                    self.assertEqual([a["outcome"] for a in actions],
                                     ["hit", "success", "miss", "success", "miss", "stable"])
                    self.assertEqual(roller.call_count, len(rolls))
                    self.assertEqual(session.character["current_hp"], 0)
                    self.assertEqual(session.world_state["player_combat_status"], "unconscious")
                    death = session.world_state["death_state"]
                    self.assertTrue(death["stable"])
                    self.assertFalse(death["dead"])
                    self.assertFalse(death["terminal"])
                    self.assertEqual((death["successes"], death["failures"]), (0, 0))
                    self.assertTrue(combat["active"])
                    self.assertEqual(combat["current_actor_id"], "player")
                    self.assertEqual(combat["round"], 4)
                    self.assertEqual(combat["initiative_order"], order)
                    self.assertEqual(combat["initiative_results"], initiative_results)
                    self.assertEqual(result["model_calls"], 0)


class EndTurnNarrationApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = economy_tests.ActionEconomyApiTests.asyncSetUp
    asyncTearDown = economy_tests.ActionEconomyApiTests.asyncTearDown
    request = economy_tests.ActionEconomyApiTests.request
    post = economy_tests.ActionEconomyApiTests.post
    command = economy_tests.ActionEconomyApiTests.command

    async def test_end_turn_response_and_saved_receipt_keep_ordered_narration(self):
        for natural in (False, True):
            with self.subTest(natural=natural):
                session = self.manager.get(self.sid).game_session
                session.end_combat()
                session.world_state["npcs"] = []
                npcs = opponents(session)
                command = self.command(session, npcs[0], {"kind": "end_turn"})
                if natural:
                    command.pop("combat_action")
                    command["message"] = "Turumu bitiriyorum"
                with patch("game.roll_d20", side_effect=[1, 15, 20]), \
                     patch("game.roll_damage", return_value=4):
                    response = await self.post(command)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                # The public response exposes narration and the authoritative result.
                assert_exchange(self, {"action_result": body["combat_result"],
                                       "narration": body["narration"], "model_calls": 0},
                                session, npcs)
                before = copy.deepcopy((session.world_state, session.character, session.rng.getstate()))
                with patch("game.roll_d20", side_effect=AssertionError("receipt rerolled")):
                    replay = await self.post(command)
                self.assertEqual(replay.json(), body)
                self.assertEqual((session.world_state, session.character, session.rng.getstate()), before)
                manager = SessionManager(session_factory=scene,
                                         campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
                _, restored, _, _, _ = manager.resume_campaign(self.created["campaign_id"])
                saved = manager.get_turn_action(restored, command["action_id"])["response"]
                self.assertEqual(saved["narration"], body["narration"])
                self.assertEqual(saved["combat_result"], body["combat_result"])
                self.assertEqual(restored.game_session.character["current_hp"], 92)

"""D-233: Dragonborn Draconic Ancestry and Breath Weapon (PHB 2024 p.187; dice guide 5.2, 6, 9.E).

Breath Weapon replaces one attack of the Attack action: a 15-foot Cone or a 30-foot Line, a Dexterity save against
DC 8 + Constitution modifier + Proficiency Bonus, the ancestry's damage on a failure and half on a success; 1d10, 2d10
at level 5, 3d10 at 11, 4d10 at 17; uses equal the Proficiency Bonus, all back on a Long Rest.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import action_economy
import dragonborn_breath
import game
from api.tests.test_combat_lifecycle import ready
from api.tests.test_species_traits import make_session


def dragonborn(level=5, ancestry="red", distance=5):
    session = make_session("Dragonborn", level=level)
    if ancestry is not None:
        session.character["draconic_ancestry"] = ancestry
    session, npc = ready(session)
    npc.update(distance_ft=distance, dexterity_mod=1, dexterity_save_bonus=1)
    return session, npc


def breathe(session, shape="cone", target_id=None):
    return session.resolve_species_trait_action("breath_weapon", shape=shape, target_id=target_id)


class DraconicAncestryTests(unittest.TestCase):
    def test_the_ancestry_is_chosen_once_out_of_combat(self):
        session = make_session("Dragonborn")
        result = session.resolve_species_trait_action("choose_draconic_ancestry", draconic_ancestry="silver")
        self.assertEqual(session.character["draconic_ancestry"], "silver")
        self.assertEqual(result["effects"], {"draconic_ancestry": "silver", "damage_type": "cold"})
        with self.assertRaises(ValueError):
            session.resolve_species_trait_action("choose_draconic_ancestry", draconic_ancestry="red")
        self.assertEqual(session.character["draconic_ancestry"], "silver")

    def test_only_a_dragonborn_chooses_a_known_dragon(self):
        with self.assertRaises(ValueError):
            make_session("Human").resolve_species_trait_action("choose_draconic_ancestry", draconic_ancestry="red")
        with self.assertRaises(ValueError):
            make_session("Dragonborn").resolve_species_trait_action("choose_draconic_ancestry", draconic_ancestry="pink")

    def test_the_ancestry_gives_resistance_to_its_damage_type(self):
        session, _ = dragonborn(ancestry="white")
        self.assertEqual(game.weapon_attack.mitigate(session, "player", "cold", 9)["final_damage"], 4)
        self.assertEqual(game.weapon_attack.mitigate(session, "player", "fire", 9)["final_damage"], 9)


class BreathWeaponTests(unittest.TestCase):
    def test_a_failed_save_takes_the_whole_roll_of_the_ancestry_type(self):
        session, npc = dragonborn(level=5)
        with patch.object(session, "roll_damage", return_value=13) as damage, patch.object(session, "roll_d20", return_value=2):
            result = breathe(session, target_id=npc["id"])
        damage.assert_called_once_with(10, 2, 0)  # level 5: 2d10, rolled once for the area
        self.assertEqual(npc["current_hp"], 27)
        target = result["effects"]["targets"][0]
        self.assertEqual((target["target_id"], target["saved"], target["damage"]), (npc["id"], False, 13))
        self.assertEqual(result["effects"]["save_dc"], 12)  # 8 + Constitution +2 + Proficiency +2
        self.assertEqual(result["effects"]["damage_type"], "fire")
        self.assertEqual(result["effects"]["uses_remaining"], 1)
        self.assertEqual(session.character["breath_weapon_spent"], 1)

    def test_a_successful_save_takes_half(self):
        session, npc = dragonborn(level=1)
        with patch.object(session, "roll_damage", return_value=7) as damage, patch.object(session, "roll_d20", return_value=20):
            result = breathe(session, target_id=npc["id"])
        damage.assert_called_once_with(10, 1, 0)
        self.assertTrue(result["effects"]["targets"][0]["saved"])
        self.assertEqual(npc["current_hp"], 37)

    def test_it_replaces_one_attack_of_the_attack_action(self):
        session, npc = dragonborn()
        with patch.object(session, "roll_damage", return_value=3), patch.object(session, "roll_d20", return_value=2):
            breathe(session, target_id=npc["id"])
        resources = action_economy.ensure(session)["player"]
        self.assertTrue(resources["base_action_spent"])
        limit = action_economy.attacks_per_action(session, "player")
        self.assertEqual(resources["attack_action"]["remaining_attacks"], limit - 1)

    def test_no_attack_left_or_an_unknown_save_is_refused_in_turkish_and_changes_nothing(self):
        # Review (DÜŞÜK): these came back as an English 409 ("No matching rule-defined resource is available.").
        session, npc = dragonborn()
        action_economy.consume_action(session, "player", "dodge")  # the Action is gone, no Attack action taken
        before = copy.deepcopy((session.world_state, session.character))
        with self.assertRaisesRegex(ValueError, "Saldırı"):
            breathe(session, target_id=npc["id"])
        self.assertEqual((session.world_state, session.character), before)
        unknown, foe = dragonborn()
        for key in ("dexterity_mod", "dexterity_save_bonus"):
            foe.pop(key, None)
        before = copy.deepcopy((unknown.world_state, unknown.character))
        with self.assertRaisesRegex(ValueError, "Çeviklik"):
            breathe(unknown, target_id=foe["id"])
        self.assertEqual((unknown.world_state, unknown.character), before)

    def test_the_shape_sets_the_reach(self):
        session, npc = dragonborn(distance=20)
        before = copy.deepcopy((session.world_state, session.character))
        with self.assertRaises(ValueError):
            breathe(session, "cone", npc["id"])
        self.assertEqual((session.world_state, session.character), before)
        with patch.object(session, "roll_damage", return_value=4), patch.object(session, "roll_d20", return_value=2):
            result = breathe(session, "line", npc["id"])
        self.assertEqual(result["effects"]["area_ft"], 30)
        self.assertEqual(npc["current_hp"], 36)

    def test_without_a_shape_the_nearest_fitting_one_is_used(self):
        for distance, shape in ((10, "cone"), (25, "line")):
            session, npc = dragonborn(distance=distance)
            with patch.object(session, "roll_damage", return_value=4), patch.object(session, "roll_d20", return_value=2):
                result = breathe(session, None, npc["id"])
            self.assertEqual(result["effects"]["shape"], shape)

    def test_no_uses_no_ancestry_or_no_fight_changes_nothing(self):
        session, npc = dragonborn()
        session.character["breath_weapon_spent"] = 2
        cases = [session]
        no_ancestry, npc2 = dragonborn(ancestry=None)
        cases.append(no_ancestry)
        calm = make_session("Dragonborn")
        calm.character["draconic_ancestry"] = "red"
        cases.append(calm)
        for case in cases:
            before = copy.deepcopy((case.world_state, case.character))
            with self.assertRaises(ValueError):
                breathe(case, "cone", None)
            self.assertEqual((case.world_state, case.character), before)

    def test_a_long_rest_brings_every_use_back(self):
        session = make_session("Dragonborn")
        session.character.update(draconic_ancestry="red", breath_weapon_spent=2)
        session.resolve_species_trait_action("long_rest")
        self.assertEqual(session.character.get("breath_weapon_spent", 0), 0)

    def test_the_words_in_a_fight_use_it(self):
        session, npc = dragonborn()
        with patch.object(session, "roll_damage", return_value=5), patch.object(session, "roll_d20", return_value=2):
            result = session.run_player_turn("ejderha nefes silahımı kullanıyorum", target_id=npc["id"],
                                             action_id=str(uuid4()))
        self.assertNotIn("karşılığı yok", result["narration"])
        self.assertEqual(npc["current_hp"], 35, result["narration"])
        self.assertEqual(session.character["breath_weapon_spent"], 1)

    def test_out_of_breath_attacking_is_a_blow_not_the_breath(self):
        # Review (ORTA): "nefes nefese saldırıyorum" is a winded attack; "sal" must never match "saldır".
        session, npc = dragonborn()
        token = game._ACTIVE_SESSION.set(session)
        try:
            self.assertFalse(dragonborn_breath.named(session, "nefes nefese saldırıyorum"))
            for line in ("nefes salıyorum", "nefesimi salıveriyorum", "ejderha nefesimi püskürtüyorum",
                         "nefes silahımı kullanıyorum"):
                with self.subTest(line=line):
                    self.assertTrue(dragonborn_breath.named(session, line))
        finally:
            game._ACTIVE_SESSION.reset(token)
        blows = lambda: [row for row in session.world_state.get("attack_results", []) if row.get("actor") == "player"]
        self.assertEqual(blows(), [])
        with patch.object(session, "roll_damage", return_value=3), patch.object(session, "roll_d20", return_value=15):
            session.run_player_turn("nefes nefese saldırıyorum", target_id=npc["id"], action_id=str(uuid4()))
        self.assertNotIn("breath_weapon_spent", session.character, "no breath use was spent")
        self.assertEqual(len(blows()), 1, "the line was one normal attack by the hero (the foes' blows follow it)")

    def test_the_fight_reading_leaves_the_breath_to_the_engine(self):
        # Kadir's playtest (seq 34/35): the model read the line as a blow and the engine asked which move it was.
        import front_proposal
        session, npc = dragonborn()
        token = game._ACTIVE_SESSION.set(session)
        try:
            with patch.object(front_proposal, "enabled", return_value=True),                     patch.object(front_proposal, "note") as note:
                read = game._front_step("ejderha nefes silahımı kullanıyorum", npc["id"], None, None, None)
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertIsNone(read)
        note.assert_not_called()  # no reading started: the fight's own words own the line


class BreathSaveTests(unittest.TestCase):
    def test_the_choice_and_the_spent_uses_survive_a_save(self):
        session, _ = dragonborn()
        session.character["breath_weapon_spent"] = 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "breath.json"
            session.save_game(path)
            reopened = make_session("Dragonborn")
            reopened.load_game(path)
        self.assertEqual(reopened.character["draconic_ancestry"], "red")
        self.assertEqual(reopened.character["breath_weapon_spent"], 1)

    def test_an_older_save_without_the_fields_spent_nothing(self):
        session = make_session("Dragonborn")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.json"
            session.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("breath_weapon_spent", payload["player"])
            reopened = make_session("Dragonborn")
            reopened.load_game(path)
        self.assertIsNone(reopened.character.get("draconic_ancestry"))
        self.assertEqual(reopened.character.get("breath_weapon_spent", 0), 0)

    def test_a_save_with_impossible_values_is_refused(self):
        for change in ({"breath_weapon_spent": 3}, {"breath_weapon_spent": -1}, {"draconic_ancestry": "pink"},
                       {"race": "Human", "species": "Human", "draconic_ancestry": "red"}):
            with self.subTest(change=change):
                session = make_session("Dragonborn")
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "bad.json"
                    session.save_game(path)
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["player"].update(change)
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        make_session("Dragonborn").load_game(path)


class BreathPanelRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import httpx
        from api.auth import FixedAuthenticator
        from api.main import create_app
        from api.ollama_adapter import AuthenticatedOllamaAdapter
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from api.tests.auth_fixture import TEST_PLAYER
        from api.tests.test_campaign_time import scene
        from api.tests.test_model_failure_never_locks import ScriptedModel
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = CampaignStore(Path(directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.manager = SessionManager(session_factory=scene, campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(ScriptedModel())
        self.enterContext(adapter.engine_binding())
        app = create_app(session_manager=self.manager, ollama_adapter=adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        self.addAsyncCleanup(self.http.aclose)

    async def campaign(self):
        from api.tests.town_seed import fixed_town
        with fixed_town(self, 23301):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        session = self.manager.get(session_id).game_session
        session.character.update(race="Dragonborn", species="Dragonborn")
        return session_id, session

    async def test_the_panel_chooses_the_dragon_and_the_state_shows_the_uses(self):
        session_id, session = await self.campaign()
        body = {"action": "choose_draconic_ancestry", "draconic_ancestry": "blue", "action_id": str(uuid4())}
        first = await self.http.post(f"/api/game/sessions/{session_id}/species-actions", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        character = first.json()["state"]["character"]
        self.assertEqual(character["draconic_ancestry"], "blue")
        self.assertEqual(character["breath_weapon_uses_remaining"], session.character["proficiency_bonus"])
        again = await self.http.post(f"/api/game/sessions/{session_id}/species-actions", json=body)
        self.assertEqual(again.json()["result"], first.json()["result"])  # the stored receipt answers a retry

    async def test_a_shape_or_target_for_another_action_is_refused(self):
        session_id, _ = await self.campaign()
        for extra in ({"shape": "cone"}, {"target_id": "x"}):
            refused = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                           json={"action": "long_rest", "action_id": str(uuid4()), **extra})
            self.assertEqual(refused.status_code, 422, refused.text)

    async def test_a_request_without_the_new_fields_keeps_its_old_receipt_hash(self):
        # A retry stored before D-233 must still replay: the absent new fields stay out of the hash.
        import hashlib
        session_id, _ = await self.campaign()
        action_id = str(uuid4())
        sent = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                    json={"action": "short_rest", "action_id": action_id})
        self.assertEqual(sent.status_code, 200, sent.text)
        old = {"command": "species_action", "action": "short_rest", "form": None, "ancestry": None, "armed": None,
               "healing_amount": None, "remove_poisoned": None}
        expected = hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False,
                                             separators=(",", ":")).encode("utf-8")).hexdigest()
        record = self.manager.get(session_id)
        self.assertEqual(self.manager.get_turn_action(record, action_id)["request_hash"], expected)


if __name__ == "__main__":
    unittest.main()

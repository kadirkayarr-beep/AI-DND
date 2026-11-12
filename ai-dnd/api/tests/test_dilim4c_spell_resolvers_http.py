"""Dilim 4C Task 4b through HTTP: a Bless button spends one slot and starts Concentration, its receipt replays without
a second cast, the store and a resume hold the same Concentration, Undo gives the slot back and ends it, and a new cast
spends once. Healing Word's public result names heal_source 'spell'.

Harness: CampaignApiTests (store + app) with a fixed town (`fixed_town`); the player made a level-1 Cleric through the
real initializer (test_spell_preparation_4c2.prepper) and put in a fight with one guard."""
from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as campaign_fixtures
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_spell_preparation_4c2 import prepper
from api.tests.town_seed import fixed_town

KEY = "spell_concentration_v1"


class SpellResolversHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def fight(self, seed, cls="Cleric"):
        with fixed_town(self, seed):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        record = self.manager.get(campaign["session_id"])
        s = record.game_session
        prepper(cls, s)
        state = s.world_state["spellcasting_v1"]
        if cls == "Cleric":
            state.update(prepared=["Bless", "Healing Word"], prepare_window=None)
        else:  # a Paladin does not prepare from a window: its creation list is what it prepared
            self.assertEqual((state["prepare_window"], state["spellbook"]), (None, None))
            self.assertIn("Bless", state["prepared"])
        s.character.update(max_hp=40, current_hp=40, conditions=[])
        s.commit_location_change("tavern")
        npc = s.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": "tavern"})
        npc.update(current_hp=100, max_hp=100, armor_class=12, hostile=True, distance_ft=30,
                   attack_damage_type="bludgeoning")
        s.world_state.setdefault("monster_perception", {})[npc["id"]] = {"player": {"visible": True}}
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            s.start_combat(npc)
        s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
        self.manager.save_campaign(campaign["campaign_id"])
        return campaign, record

    async def post(self, campaign, body):
        return await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn", json=body)

    def stored(self, campaign):
        return self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]

    async def test_bless_receipt_store_resume_undo_and_one_spend(self):
        campaign, record = await self.fight(4401)
        s = record.game_session
        bless = {"message": "Hamle.", "action_id": str(uuid4()), "combat_action": {"steps": [
            {"kind": "magic", "ability": "Bless", "target_id": "player"}]}}
        cast = await self.post(campaign, bless)
        self.assertEqual(cast.status_code, 200, cast.text)
        self.assertEqual({k: cast.json()["combat_result"][k] for k in ("spell", "slot_spent", "target_id")},
                         {"spell": "Bless", "slot_spent": True, "target_id": "player"})
        held = s.world_state[KEY]
        self.assertEqual((held["spell_id"], held["targets"]), ("Bless", ["player"]))
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})
        self.assertEqual(self.stored(campaign)[KEY], held)

        with patch("spell_scope.cast", side_effect=AssertionError("replay recast")):
            replay = await self.post(campaign, bless)
        self.assertEqual((replay.status_code, replay.json()), (200, cast.json()))
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})

        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _, resumed, *_ = manager.resume_campaign(campaign["campaign_id"])
        self.assertEqual(resumed.game_session.world_state[KEY], held)

        undone = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/undo",
                                      json={"action_id": str(uuid4()), "target_action_id": bless["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text)
        s = record.game_session
        self.assertIsNone(s.world_state.get(KEY))
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 2})
        self.assertIsNone(self.stored(campaign).get(KEY))

        again = await self.post(campaign, {**bless, "action_id": str(uuid4())})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})
        self.assertEqual(s.world_state[KEY]["spell_id"], "Bless")

    async def test_healing_word_names_its_heal_source(self):
        campaign, record = await self.fight(4402)
        s = record.game_session
        s.character["current_hp"] = 10
        self.manager.save_campaign(campaign["campaign_id"])
        with patch.object(s.rng, "randint", return_value=2):
            healed = await self.post(campaign, {"message": "Hamle.", "action_id": str(uuid4()), "combat_action": {
                "steps": [{"kind": "magic", "ability": "Healing Word", "target_id": "player"}]}})
        self.assertEqual(healed.status_code, 200, healed.text)
        result = healed.json()["combat_result"]
        self.assertEqual({k: result[k] for k in ("spell", "healing", "heal_source", "damage_type")},
                         {"spell": "Healing Word", "healing": 7, "heal_source": "spell", "damage_type": None})
        self.assertEqual(s.character["current_hp"], 17)


    async def test_a_paladin_casts_bless_over_http(self):
        campaign, record = await self.fight(4403, "Paladin")
        s = record.game_session
        before = dict(s.world_state["spellcasting_v1"]["slots"])
        spells = list(s.world_state["spellcasting_v1"]["prepared"])
        cast = await self.post(campaign, {"message": "Hamle.", "action_id": str(uuid4()), "combat_action": {"steps": [
            {"kind": "magic", "ability": "Bless", "target_id": "player"}]}})
        self.assertEqual(cast.status_code, 200, cast.text)
        self.assertEqual(cast.json()["combat_result"]["spell"], "Bless")
        self.assertEqual(s.world_state[KEY]["spell_id"], "Bless")
        self.assertEqual(s.world_state["spellcasting_v1"]["prepared"], spells)  # Concentration is not in this state
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], before["1"] - 1)
        self.assertEqual(self.stored(campaign)[KEY], s.world_state[KEY])

    async def test_undo_of_an_enemy_turn_that_broke_concentration(self):
        campaign, record = await self.fight(4404)
        s = record.game_session
        npc = next(n for n in s.world_state["npcs"] if n.get("hostile"))
        npc["distance_ft"] = 5
        bless = await self.post(campaign, {"message": "Hamle.", "action_id": str(uuid4()), "combat_action": {"steps": [
            {"kind": "magic", "ability": "Bless", "target_id": "player"}]}})
        self.assertEqual(bless.status_code, 200, bless.text)
        held, hp = dict(s.world_state[KEY]), s.character["current_hp"]
        rolls = iter([19] + [2] * 20)  # the guard hits; the Constitution save fails
        end = {"message": "Hamle.", "action_id": str(uuid4()), "combat_action": {"steps": [{"kind": "end_turn"}]}}
        with patch("game.roll_d20", side_effect=lambda *a, **k: next(rolls)), patch.object(s.rng, "randint", return_value=1):
            ended = await self.post(campaign, end)
        self.assertEqual(ended.status_code, 200, ended.text)
        self.assertIn("Konsantrasyonun bozulur", ended.json()["narration"])
        self.assertIsNone(s.world_state[KEY])
        self.assertLess(s.character["current_hp"], hp)
        undone = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/undo",
                                      json={"action_id": str(uuid4()), "target_action_id": end["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text)
        s = record.game_session
        self.assertEqual((s.world_state[KEY], s.character["current_hp"]), (held, hp))
        self.assertEqual(self.stored(campaign)[KEY], held)


if __name__ == "__main__":
    unittest.main()

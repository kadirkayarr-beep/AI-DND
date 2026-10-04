"""Read-only exposure of existing spell state, never a new mechanic owner."""
import copy
import unittest
from uuid import uuid4
from unittest.mock import patch

from api.serializers import serialize_session_state
from api.tests.test_spell_scope import caster
from api.tests import test_campaign_api as fixtures


class SpellProjectionTests(unittest.TestCase):
    def test_missing_state_is_null_and_never_inferred_from_character(self):
        session, _ = caster(cls="Wizard")
        session.world_state.pop("spellcasting_v1")
        self.assertTrue(session.character["spells"])
        self.assertIsNone(serialize_session_state(session)["spellcasting"])
        self.assertNotIn("spellcasting_v1", session.world_state)

    def test_projection_copies_exact_values_and_does_not_alias_owner(self):
        session, _ = caster()
        owned = session.world_state["spellcasting_v1"]
        owned["slots"]["1"] = 0
        owned["slot_turn"] = ["combat-existing", 2, 3]
        before = copy.deepcopy(owned)
        actual = serialize_session_state(session)["spellcasting"]
        self.assertEqual(actual, {k: owned[k] for k in ("cantrips", "prepared", "slots", "slot_turn")})
        actual["cantrips"].append("not a grant")
        actual["prepared"].clear()
        actual["slots"]["1"] = 999
        actual["slot_turn"][1] = 99
        self.assertEqual(owned, before)

    def test_wizard_spellbook_is_not_projected_as_preparation(self):
        session, _ = caster(cls="Wizard")
        self.assertTrue(session.character["spells"])
        self.assertEqual(serialize_session_state(session)["spellcasting"]["prepared"], [])

    def test_repeated_projection_does_not_consume_slots_rng_or_time(self):
        session, _ = caster()
        before = copy.deepcopy(session.world_state["spellcasting_v1"])
        rng = session.rng.getstate()
        clock = copy.deepcopy(session.world_state.get("campaign_time"))
        for _ in range(4):
            self.assertEqual(serialize_session_state(session)["spellcasting"]["slots"], before["slots"])
        self.assertEqual(session.world_state["spellcasting_v1"], before)
        self.assertEqual(session.rng.getstate(), rng)
        self.assertEqual(session.world_state.get("campaign_time"), clock)


class SpellProjectionApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    async def test_get_turn_replay_and_resume_use_actual_resources(self):
        campaign = await self.create_campaign()
        record = self.manager.get(campaign["session_id"])
        session, enemy = caster(record.game_session)
        self.manager.save_campaign(campaign["campaign_id"])
        root = f"/api/game/sessions/{campaign['session_id']}"
        before = await self.http.get(root + "/state")
        self.assertEqual(before.status_code, 200, before.text)
        self.assertEqual(before.json()["spellcasting"]["slots"], {"1": 2})
        command = {"message": "Resolve the selected spell.", "action_id": str(uuid4()),
                   "combat_action": {"steps": [{"kind": "magic", "ability": "Magic Missile",
                                               "target_id": enemy["id"]}]}}
        cast = await self.http.post(root + "/turn", json=command)
        self.assertEqual(cast.status_code, 200, cast.text)
        projected = cast.json()["state"]["spellcasting"]
        self.assertEqual(projected["slots"], {"1": 1})
        self.assertEqual(projected["prepared"], session.world_state["spellcasting_v1"]["prepared"])
        self.assertEqual(projected["slot_turn"], session.world_state["spellcasting_v1"]["slot_turn"])
        self.assertIsNotNone(projected["slot_turn"])
        with patch("spell_scope.cast", side_effect=AssertionError("presentation replay recast")):
            replay = await self.http.post(root + "/turn", json=command)
        self.assertEqual(replay.json(), cast.json())
        resumed = await self.http.post(f"/api/game/campaigns/{campaign['campaign_id']}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"]["spellcasting"], projected)
"""D-073: the player's held Concentration is in the public state (`GameState.concentration`), so the panel can show it.

The field is read only: it is the held record while it still holds right now (`spell_concentration.holds`), never a
finished fight's or an expired one's; it carries no combat id. Turn and Undo responses carry it, so Geri Al shows the
Concentration it gave back or took away.

Harness: the Bless-over-HTTP fight of test_dilim4c_spell_resolvers_http (fixed town, level-1 Cleric, one guard)."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

from api.serializers import serialize_session_state
from api.tests import test_dilim4c_spell_resolvers_http as bless_http

KEY = "spell_concentration_v1"
BLESS = {"spell_id": "Bless", "slot_level": 1, "started_round": 1, "targets": ["player"]}


class ConcentrationStateHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = bless_http.SpellResolversHttp.asyncSetUp
    asyncTearDown = bless_http.SpellResolversHttp.asyncTearDown
    fight = bless_http.SpellResolversHttp.fight
    post = bless_http.SpellResolversHttp.post

    async def bless(self, campaign):
        body = {"message": "Hamle.", "action_id": str(uuid4()), "combat_action": {"steps": [
            {"kind": "magic", "ability": "Bless", "target_id": "player"}]}}
        cast = await self.post(campaign, body)
        self.assertEqual(cast.status_code, 200, cast.text)
        return body, cast.json()

    async def undo(self, campaign, target):
        undone = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/undo",
                                      json={"action_id": str(uuid4()), "target_action_id": target})
        self.assertEqual(undone.status_code, 200, undone.text)
        return undone.json()

    async def test_cast_shows_it_and_undo_takes_it_back(self):
        campaign, record = await self.fight(7301)
        before = await self.http.get(f"/api/game/sessions/{campaign['session_id']}/state")
        self.assertEqual(before.status_code, 200, before.text)
        self.assertIsNone(before.json()["concentration"])
        body, cast = await self.bless(campaign)
        self.assertEqual(cast["state"]["concentration"], BLESS)
        undone = await self.undo(campaign, body["action_id"])
        self.assertIsNone(record.game_session.world_state.get(KEY))
        self.assertIsNone(undone["state"]["concentration"])

    async def test_undo_of_the_turn_that_broke_it_shows_it_again(self):
        campaign, record = await self.fight(7302)
        s = record.game_session
        next(n for n in s.world_state["npcs"] if n.get("hostile"))["distance_ft"] = 5
        await self.bless(campaign)
        rolls = iter([19] + [2] * 20)  # the guard hits; the Constitution save fails
        end = {"message": "Hamle.", "action_id": str(uuid4()), "combat_action": {"steps": [{"kind": "end_turn"}]}}
        with patch("game.roll_d20", side_effect=lambda *a, **k: next(rolls)), patch.object(s.rng, "randint", return_value=1):
            ended = await self.post(campaign, end)
        self.assertEqual(ended.status_code, 200, ended.text)
        self.assertIsNone(s.world_state[KEY])
        self.assertIsNone(ended.json()["state"]["concentration"])
        undone = await self.undo(campaign, end["action_id"])
        self.assertEqual(undone["state"]["concentration"], BLESS)


class ConcentrationProjection(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = bless_http.SpellResolversHttp.asyncSetUp
    asyncTearDown = bless_http.SpellResolversHttp.asyncTearDown
    fight = bless_http.SpellResolversHttp.fight

    async def held(self, seed):
        campaign, record = await self.fight(seed)
        s = record.game_session
        combat = s.world_state["combat"]
        s.world_state[KEY] = {"spell_id": "Bless", "combat_id": combat["combat_id"], "started_round": combat["round"],
                              "slot_level": 1, "targets": ["player"]}
        return s

    async def test_projection_is_a_copy_and_reads_nothing_else(self):
        s = await self.held(7303)
        owned = copy.deepcopy(s.world_state[KEY])
        rng = s.rng.getstate()
        projected = serialize_session_state(s)["concentration"]
        self.assertEqual(projected, BLESS)
        projected["targets"].append("guard")
        self.assertEqual((s.world_state[KEY], s.rng.getstate()), (owned, rng))

    async def test_a_record_that_no_longer_holds_is_not_shown(self):
        s = await self.held(7304)
        s.world_state[KEY]["combat_id"] = "a-finished-fight"
        self.assertIsNone(serialize_session_state(s)["concentration"])
        s = await self.held(7305)
        s.world_state["combat"]["round"] = s.world_state[KEY]["started_round"] + 11  # past its minute
        self.assertIsNone(serialize_session_state(s)["concentration"])
        self.assertIsNotNone(s.world_state[KEY])  # the projection only reads; settling stays the engine's job


if __name__ == "__main__":
    unittest.main()

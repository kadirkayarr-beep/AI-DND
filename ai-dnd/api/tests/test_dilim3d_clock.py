"""Dilim 3D Task 1 (#3, #167, #166): one length said twice in a line moves the clock once, through the API.

A line that names two different lengths of one unit moves nothing and asks; Undo and a replayed action id stay whole.
"""
import copy
import os
import unittest
import uuid
from unittest.mock import patch

import campaign_time
import front_proposal
from api.tests import test_campaign_api as fixtures
from api.tests.journeys.runner import ScriptedClient
from api.tests.test_campaign_time import Q167
from api.tests.town_seed import fixed_town

START = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
         "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}


class DurationSaidTwiceTurn(unittest.IsolatedAsyncioTestCase):
    asyncSetUp_base = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    post_scene_turn = fixtures.CampaignApiTests.post_scene_turn

    async def asyncSetUp(self):
        await self.asyncSetUp_base()
        self.client = ScriptedClient({})
        with fixed_town(self, 4501):
            created = await self.http.post("/api/game/campaigns", json={"campaign_start": START})
        self.assertEqual(created.status_code, 200, created.text)
        self.session_id = created.json()["session_id"]

    def session(self):
        return self.manager.get(self.session_id).game_session

    def elapsed(self):
        return self.session().world_state["campaign_time"]["elapsed_seconds"]

    def snapshot(self):
        session = self.session()
        return copy.deepcopy({"world_state": session.world_state, "messages": session.messages})

    async def turn(self, line, *, front=None, action_id=None):
        """One API turn; front given = the front reading is on and answers it."""
        self.client.script = {"front": front} if front is not None else {}
        self._last_action_id = action_id or str(uuid.uuid4())
        with patch.dict(os.environ, {front_proposal.FLAG: "1" if front is not None else "0"}):
            return await self.post_scene_turn(f"/api/game/sessions/{self.session_id}/turn", self.client,
                                              {"message": line, "action_id": self._last_action_id})

    async def undo(self):
        reply = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                     json={"action_id": str(uuid.uuid4()), "target_action_id": self._last_action_id})
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply

    async def test_167_turn_moves_the_clock_sixteen_hours(self):
        before = self.elapsed()
        reply = await self.turn(Q167)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.elapsed() - before, 16 * 3600)
        self.assertNotIn("32 saat", reply.json()["narration"])

    async def test_167_read_as_a_wait_by_the_front_moves_sixteen_hours(self):
        before = self.elapsed()
        reply = await self.turn(Q167, front={"kind": "wait"})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.elapsed() - before, 16 * 3600)
        self.assertNotIn("32 saat", reply.json()["narration"])

    async def test_replayed_action_id_moves_the_clock_once(self):
        before = self.elapsed()
        action_id = str(uuid.uuid4())
        first = await self.turn(Q167, action_id=action_id)
        again = await self.turn(Q167, action_id=action_id)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["narration"], first.json()["narration"])
        self.assertEqual(self.elapsed() - before, 16 * 3600)

    async def test_undo_takes_the_sixteen_hours_back(self):
        before = self.snapshot()  # world_state, messages
        reply = await self.turn(Q167)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertNotEqual(self.snapshot(), before)
        await self.undo()
        self.assertEqual(self.snapshot(), before)

    async def test_a_conflict_moves_nothing_and_asks(self):
        before = self.snapshot()
        reply = await self.turn("2 saat bekliyorum, yok 3 saat")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn(campaign_time.DURATION_CONFLICT, reply.json()["narration"])
        self.assertEqual(self.elapsed(), before["world_state"]["campaign_time"]["elapsed_seconds"])

    async def test_a_conflict_read_as_a_wait_by_the_front_moves_nothing_and_asks(self):
        before = self.snapshot()
        reply = await self.turn("2 saat bekliyorum, yok 3 saat", front={"kind": "wait"})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn(campaign_time.DURATION_CONFLICT, reply.json()["narration"])
        self.assertEqual(self.elapsed(), before["world_state"]["campaign_time"]["elapsed_seconds"])

    async def test_166_a_second_long_rest_too_soon_says_so(self):
        first = await self.turn("8 saat uyuyorum. Uzun dinlenme yapıyorum.")  # QA #028, verbatim
        self.assertEqual(first.status_code, 200, first.text)
        reply = await self.turn("sekiz saat uyuyarak uzun dinlenme yapıyorum.")  # QA #166's sleep clause
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn("Daha yeni dinlenmiştin", reply.json()["narration"])
        self.assertNotEqual(reply.json()["narration"].strip(), "8 saat geçiyor.")


class TimedOwnersAsk(unittest.TestCase):
    """Both timed owners turn two lengths of one unit into the same clarification and move nothing."""

    def setUp(self):
        from api.tests import test_death_system as death_fixtures
        self.session = death_fixtures.make_session()
        campaign_time.initialize(self.session.world_state)
        self.before = copy.deepcopy(self.session.world_state)

    def assert_asks(self, result):
        self.assertEqual(result["direct_response"], campaign_time.DURATION_CONFLICT)
        self.assertEqual(result["status"], "clarification")
        self.assertFalse(result["success"])
        self.assertEqual(self.session.world_state, self.before)

    def test_pass_time_asks(self):
        import timed_gameplay
        self.assert_asks(timed_gameplay.pass_time(self.session, "2 saat bekliyorum, yok 3 saat"))

    def test_resolve_input_asks(self):
        import timed_gameplay
        self.assert_asks(timed_gameplay.resolve_input(self.session, "2 saat bekliyorum, yok 3 saat"))

    def test_resolve_input_asks_before_a_rest(self):
        import timed_gameplay
        self.assert_asks(timed_gameplay.resolve_input(self.session, "8 saat uyuyorum, yok 9 saat"))


class DurationConflictWhileDown(unittest.TestCase):
    """game._down_outside_combat_turn reads the line's length: two lengths read as none, the body sleeps till it wakes."""

    def test_a_stable_body_with_two_lengths_sleeps_until_it_wakes(self):
        from api.tests import test_death_system as death_fixtures
        session = death_fixtures.make_session()
        campaign_time.initialize(session.world_state)
        session._apply_player_damage(session.character["current_hp"], took_damage=True)
        with patch.object(session.rng, "randint", return_value=1):
            session.stabilize_player()
        recovery_at = session.ensure_death_state()["recovery"]["at"]
        session.run_player_turn("2 saat bekliyorum, yok 3 saat")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], recovery_at)
        self.assertEqual(session.character["current_hp"], 1)


if __name__ == "__main__":
    unittest.main()

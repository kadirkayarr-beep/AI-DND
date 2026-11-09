"""The world panel's way out (Dilim 3, Task 5): the state names the same way out a flight would take; reading writes nothing."""
from __future__ import annotations

import copy
from unittest.mock import patch

import combat_lifecycle
from api.serializers import serialize_session_state
from api.tests.journeys.runner import JourneyCase
from api.tests import test_exits
from api.tests.test_exits import CITY, SIDE, SUCCESS


class ExitsViewTests(JourneyCase):
    scene = test_exits.ExitsTests.scene  # the same harness setup, without rerunning ExitsTests' own tests

    async def test_the_view_names_the_same_way_out_as_flight(self):
        session = await self.scene("09c_escape_start_scene", fight=True)
        before = copy.deepcopy(session.world_state["locations"])
        state = serialize_session_state(session)
        self.assertEqual(state["way_out"]["name"], "Neverwinter Ara Sokağı")
        self.assertNotIn(SIDE, session.world_state["locations"])
        self.assertEqual(session.world_state["locations"], before)
        with patch.object(session, "perform_skill_check", create=True, return_value=dict(SUCCESS)):
            combat_lifecycle.flee(session)
        self.assertEqual(session.world_state["location"], SIDE)
        self.assertEqual(serialize_session_state(session)["way_out"]["id"], CITY)

    async def test_no_exit_reads_null(self):
        session = await self.scene("09b_escape_no_exit")
        self.assertIsNone(serialize_session_state(session)["way_out"])

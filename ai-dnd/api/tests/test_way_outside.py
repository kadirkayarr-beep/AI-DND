"""The front list says where 'outside' leads (Dilim 3, Task 10; 42, K4): the row names the street it opens onto, from
the inn's door and from a room behind a door alike. The measured chain already carried 'dışarı çıkıyorum' to that
street, so only the row's label changes; no repair for a far pick was written."""

from __future__ import annotations

import front_proposal
import game
from api.tests.journeys.runner import JourneyCase
from api.tests import test_exits
from api.tests.test_exits import CITY


class WayOutsideTests(JourneyCase):
    # the worlds are test_exits' own: the same harness setups, borrowed rather than rewritten
    scene = test_exits.ExitsTests.scene
    city_world = test_exits.ExitsTests.city_world
    house_with_inner_room_world = test_exits.ExitsTests.house_with_inner_room_world

    def outside_rows(self, session):
        token = game._ACTIVE_SESSION.set(session)
        try:
            return [row for row in front_proposal.listing(session)["places"] if row["id"] == CITY]
        finally:
            game._ACTIVE_SESSION.reset(token)

    async def test_the_outside_row_names_where_it_leads(self):
        session = await self.scene("09a_escape_exit")
        self.assertEqual(self.outside_rows(session), [{"id": CITY, "name": "dışarı: Neverwinter"}])

    async def test_from_an_inner_room_outside_is_the_street(self):
        await self.house_with_inner_room_world()
        session = self.manager.get(self.last_session_id).game_session
        session.world_state["location"] = self.hall_id
        self.assertEqual(self.outside_rows(session), [{"id": CITY, "name": "dışarı: Neverwinter"}])

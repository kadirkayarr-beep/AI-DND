"""A journey is written on its own town (D-383), and repeat seeds stay clear of a sibling's seed (D-384).

The messenger chain (journey 36) is bound to town 10: which person is heard at the harbour, and when each sent caller
reaches the player, are the seed's (``world_happenings.tie``: "the hours are the seed's"). On another town the same
steps meet other rumours and other hours. That is a town fact, not a game fault; this test pins it so the chain's
seed is never changed or dropped without noticing.
"""

from __future__ import annotations

import dataclasses

import local_places
import world_threads
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase
from api.tests.journeys.schema import load_scenario

CHAIN = SCENARIO_DIR / "36_messenger_chain.json"
CHAIN_TOWN = 10
OTHER_TOWN = 11
HARBOUR_STEP = 3
WAIT_STEPS = (7, 8)


class MessengerChainIsBoundToItsTown(JourneyCase):
    async def _chain(self, town: int, *, front: bool) -> dict[int, tuple[str, tuple[str, ...]]]:
        scenario = load_scenario(CHAIN)
        setup = {**scenario.setup, "campaign_seed": town, "front_proposal": front}
        results = await self.run_scenario(dataclasses.replace(scenario, setup=setup))
        return {r.index: (r.status, r.failures) for r in results}

    def _heard_at_arrival(self, step: int) -> list[str]:
        journal = self.last_observations[step - 1]["gunluk"]
        return [trail["ne"] for trail in journal["iz"] if trail["kaynak"] == "duyulan"]

    async def test_the_chain_is_written_on_its_own_town(self):
        scenario = load_scenario(CHAIN)
        self.assertEqual(scenario.setup["campaign_seed"], CHAIN_TOWN)
        for front in (False, True):
            with self.subTest(front=front):
                results = await self._chain(CHAIN_TOWN, front=front)
                self.assertEqual({i: r for i, r in results.items() if r[0] != "pass"}, {})
                self.assertEqual(self._heard_at_arrival(HARBOUR_STEP), [])
                await self.asyncTearDown()
                await self.asyncSetUp()

    async def test_town_eleven_hears_a_posting_at_the_harbour_and_sends_its_callers_later(self):
        for front in (False, True):
            with self.subTest(front=front):
                results = await self._chain(OTHER_TOWN, front=front)
                self.assertEqual(results[HARBOUR_STEP][0], "new_break")
                self.assertEqual(self._heard_at_arrival(HARBOUR_STEP),
                                 ["Şorven İskelesi kullanım dışı halatlarını ayıracak yardımcı aranıyor."])
                world = self.manager.get(self.last_session_id).game_session.world_state
                town = local_places.settlement_of(world, world["location"])
                coming = [link for link in world_threads.view(world)["links"]
                          if link["kind"] == "caller" and link["settlement_id"] == town]
                self.assertEqual(len(coming), 2)
                for link in coming:
                    self.assertIsNotNone(link["fires_at"], "no sent caller has reached the player by hour seven")
                for step in WAIT_STEPS:
                    self.assertEqual(results[step][0], "new_break")
                await self.asyncTearDown()
                await self.asyncSetUp()

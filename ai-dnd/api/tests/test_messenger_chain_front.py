"""The messenger chain (journey 36) played twice, with the front reading on and off.

The front reading is how a line is understood, not what it may change: money, the bag, the running jobs and the
journal's trails must stand the same after every step either way. The narration is not compared.
"""

from __future__ import annotations

import dataclasses

from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase
from api.tests.journeys.schema import load_scenario

CHAIN = SCENARIO_DIR / "36_messenger_chain.json"


def _state(observed: dict) -> dict:
    """What a step leaves behind that the reading must not change: purse, bag, running jobs, trail count."""
    return {"kese": observed["kese"], "envanter": observed["envanter"], "gorev": observed["gorev"]["aktif"],
            "iz": len((observed["gunluk"] or {}).get("iz") or [])}


class MessengerChainFrontTest(JourneyCase):
    async def _chain(self, front: bool) -> list[dict]:
        scenario = load_scenario(CHAIN)
        scenario = dataclasses.replace(scenario, setup={**scenario.setup, "front_proposal": front})
        results = await self.run_scenario(scenario)
        self.assertEqual([(r.index, r.status, r.failures) for r in results if r.status != "pass"], [],
                         f"front {'on' if front else 'off'}")
        return [_state(observed) for observed in self.last_observations]

    async def test_money_bag_jobs_and_trails_are_the_same_with_the_reading_on_and_off(self):
        on = await self._chain(True)
        # The scenario's fixed campaign seed is the campaign's id: the second play needs a store of its own.
        await self.asyncTearDown()
        await self.asyncSetUp()
        off = await self._chain(False)
        self.assertEqual(len(on), len(load_scenario(CHAIN).steps))
        for number, (with_reading, without) in enumerate(zip(on, off), start=1):
            self.assertEqual(with_reading, without, f"adım {number}")

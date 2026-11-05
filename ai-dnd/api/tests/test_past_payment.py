"""Play-note item 3: reporting a past payment must not offer/pay again or advance half an hour."""
import copy
from dataclasses import replace

from api.tests.journeys.runner import JourneyCase, SCENARIO_DIR
from api.tests.journeys.schema import load_scenario


class PastPaymentEvidence(JourneyCase):
    async def _play(self, session_id, step, model):
        session = self.manager.get(session_id).game_session
        world = session.world_state
        before = {"currency": copy.deepcopy(world.get("currency")),
                  "ledger": copy.deepcopy((world.get("flags", {}).get("economic_ledger") or {}).get("operations") or {}),
                  "time": (world.get("campaign_time") or {}).get("elapsed_seconds", 0)}
        failures = await super()._play(session_id, step, model)
        if step.say == "az önce 5 bakır verdim":
            world = self.manager.get(session_id).game_session.world_state
            self.assertEqual(world.get("currency"), before["currency"])
            self.assertEqual((world.get("flags", {}).get("economic_ledger") or {}).get("operations") or {}, before["ledger"])
            self.assertEqual((world.get("campaign_time") or {}).get("elapsed_seconds", 0), before["time"])
            self.assertFalse(any(o.get("status") == "prepared"
                                 for o in (world.get("flags", {}).get("economic_offers") or {}).values()))
            self.assertNotIn("Yarım saat geçiyor", self.last_narration)
            self.history_steps += 1
        return failures

    async def test_original_item_three_scenario_preserves_clock_and_payment_ledger(self):
        self.history_steps = 0
        scenario = load_scenario(SCENARIO_DIR / "16_past_tense.json")
        self.assertEqual(scenario.source_items, (3,))
        self.assertFalse(any(s.known_broken or s.real_chain for s in scenario.steps))
        results = await self.run_scenario(scenario)
        self.assertEqual([r.status for r in results], ["pass", "pass"], results)
        self.assertEqual(self.history_steps, 2)

    async def test_a_real_confirmed_payment_is_not_repeated_when_reported(self):
        self.history_steps = 0
        scenario = load_scenario(SCENARIO_DIR / "16_past_tense.json")
        original = scenario.steps[1]
        prepare = replace(original, say=None, script={}, economic_action={"kind": "prepare",
            "proposal": {"purpose": "gift", "recipient_id": "barman", "amount_cp": 5}},
            expect={"kese": 100, "kart": {"max_total_cp": 5}})
        confirm = replace(original, say=None, script={}, economic_action={"kind": "confirm"},
                          expect={"kese": 95, "kart": None})
        history = replace(original, expect={"kese": 95, "kart": None})
        results = await self.run_scenario(replace(scenario, steps=(prepare, confirm, history)))
        self.assertEqual([r.status for r in results], ["pass"] * 3, results)
        self.assertEqual(self.history_steps, 1)
        world = self.manager.get(self.last_session_id).game_session.world_state
        operations = world["flags"]["economic_ledger"]["operations"]
        self.assertEqual(sum(op.get("net_debit_cp", 0) for op in operations.values()), 5)
        self.assertIn("5 bakır", self.last_speech_input)

    async def test_explicit_say_past_payment_does_not_open_a_card_or_advance_time(self):
        self.history_steps = 0
        scenario = load_scenario(SCENARIO_DIR / "16_past_tense.json")
        step = replace(scenario.steps[1], konus="barman")
        results = await self.run_scenario(replace(scenario, steps=(step,)))
        self.assertEqual([r.status for r in results], ["pass"], results)
        self.assertEqual(self.history_steps, 1)
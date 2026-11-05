"""Task 22.3b evidence for handoff: measure three scripted prompts, never a real model."""
import json
from dataclasses import replace
from unittest.mock import patch

import npc_told
import truth_card
from api.tests.journeys.runner import JourneyCase, SCENARIO_DIR
from api.tests.journeys.schema import load_scenario


class HandoffPromptMeasurement(JourneyCase):
    async def _play(self, session_id, step, model):
        captured = {"truth": [], "memory": []}

        def capture(kind, original):
            def wrapped(*args, **kwargs):
                value = original(*args, **kwargs)
                captured[kind].append(value)
                return value
            return wrapped

        with patch.object(truth_card, "npc_view", capture("truth", truth_card.npc_view)), \
             patch.object(truth_card, "narrator_view", capture("truth", truth_card.narrator_view)), \
             patch.object(npc_told, "view", capture("memory", npc_told.view)):
            failures = await super()._play(session_id, step, model)
        index = self.measured_scenario.steps.index(step) + 1
        if index in self.wanted_steps:
            for lane, prompt in (("speech", self.last_speech_input), ("narration", self.last_narrator_input)):
                views = {kind: list(dict.fromkeys(v for v in values if v and prompt and v in prompt))
                         for kind, values in captured.items()}
                record = {"scenario": self.measured_scenario.id, "step": index, "lane": lane,
                          "prompt_bytes": None if prompt is None else len(prompt.encode("utf-8")),
                          "truth_bytes": sum(len(v.encode("utf-8")) for v in views["truth"]),
                          "memory_bytes": sum(len(v.encode("utf-8")) for v in views["memory"]),
                          "shortened_views": [v for values in views.values() for v in values if "kısaltıldı" in v]}
                self.measurements.append(record)
                print("HANDOFF_PROMPT_BYTES " + json.dumps(record, ensure_ascii=False))
        return failures

    async def measure(self, filename, steps, stop=None):
        scenario = load_scenario(SCENARIO_DIR / filename)
        if stop is not None:
            scenario = replace(scenario, steps=scenario.steps[:stop])
        self.measured_scenario = scenario
        self.wanted_steps = steps
        self.measurements = []
        results = await self.run_scenario(scenario)
        self.assertEqual([r.status for r in results], ["pass"] * len(scenario.steps), results)
        self.assertEqual(len(self.measurements), len(steps) * 2)
        return self.measurements

    async def test_memory_recall_step_8_prompt_bytes(self):
        rows = await self.measure("24_personal_memory.json", {8}, stop=8)
        speech = next(r for r in rows if r["lane"] == "speech")
        self.assertGreater(speech["memory_bytes"], 0)
        self.assertLessEqual(speech["memory_bytes"], 600)
        self.assertGreater(speech["prompt_bytes"], speech["memory_bytes"])

    async def test_truth_card_steps_2_and_3_prompt_bytes(self):
        rows = await self.measure("26_truth_card_price.json", {2, 3})
        for step, lane in ((2, "speech"), (3, "narration")):
            row = next(r for r in rows if r["step"] == step and r["lane"] == lane)
            self.assertGreater(row["truth_bytes"], 0)
            self.assertLessEqual(row["truth_bytes"], 600)
            self.assertGreater(row["prompt_bytes"], row["truth_bytes"])
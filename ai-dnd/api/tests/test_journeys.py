"""Every journey scenario file, run with the scripted model.

A new break fails the suite; so does a known-broken marker on a step that now passes (remove the marker).
Known breaks are counted, not failed. The summary line is printed for the report and the handoff.
"""

from __future__ import annotations

import unittest

from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems, summary_line
from api.tests.journeys.schema import ScenarioError, load_scenario


class JourneysTest(JourneyCase):
    async def test_every_scenario_file(self):
        results = {}
        for path in sorted(SCENARIO_DIR.glob("*.json")):
            with self.subTest(path.stem):
                try:
                    scenario = load_scenario(path)
                except ScenarioError as error:
                    self.fail(str(error))
                steps = await self.run_scenario(scenario)
                results[scenario.id] = steps
                problems = describe_problems(steps)
                if problems:
                    self.fail(f"{scenario.id}:\n" + "\n".join(problems))
        print(f"\nYolculuklar: {summary_line(results)}")


if __name__ == "__main__":
    unittest.main()

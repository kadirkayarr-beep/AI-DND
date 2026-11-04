"""Every journey scenario file, run with the scripted model.

A new break fails the suite; so does a known-broken marker on a step that now passes (remove the marker).
Known breaks are counted, not failed. The summary line is printed for the report and the handoff.
"""

from __future__ import annotations

import unittest

from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems, summary_line
from api.tests.journeys.schema import ScenarioError, load_scenario

# The scenario files there were when this check was written; a renamed or emptied folder must not pass as green.
MIN_SCENARIOS = 32


class JourneysTest(JourneyCase):
    async def test_every_scenario_file(self):
        results = {}
        for path in sorted(SCENARIO_DIR.glob("*.json")):
            with self.subTest(path.stem):
                try:
                    scenario = load_scenario(path)
                except ScenarioError as error:
                    self.fail(str(error))
                # Ruling R19: every marker names the failures it stands for, so it cannot absorb another one.
                unnamed = [number for number, step in enumerate(scenario.steps, start=1)
                           if step.known_broken and not step.broken_because]
                self.assertEqual(unnamed, [], f"{scenario.id}: known_broken without broken_because")
                steps = await self.run_scenario(scenario)
                results[scenario.id] = steps
                problems = describe_problems(steps)
                if problems:
                    self.fail(f"{scenario.id}:\n" + "\n".join(problems))
        self.assertGreaterEqual(len(results), MIN_SCENARIOS, f"only {len(results)} scenario files ran")
        print(f"\nYolculuklar: {summary_line(results)}")


if __name__ == "__main__":
    unittest.main()

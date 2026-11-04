"""Every journey scenario file, run with the scripted model.

A new break fails the suite; so does a known-broken marker on a step that now passes (remove the marker).
Known breaks are counted, not failed. The summary line is printed for the report and the handoff.
"""

from __future__ import annotations

import re
import unittest
from types import SimpleNamespace

from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems, summary_line
from api.tests.journeys.schema import ScenarioError, load_scenario

# The scenario files there were when this check was written; a renamed or emptied folder must not pass as green.
MIN_SCENARIOS = 32

# An expectation mismatch as schema.check_expect writes it: "<key>: beklenen X, gözlenen Y".
_MISMATCH = re.compile(r"^[\w.]+: beklenen .*, gözlenen ")


def loose_causes(step, failures) -> list[str]:
    """The expectation mismatches of a known break that no cause pins to its observed value.

    A cause such as "kese: beklenen" covers every value of the key, so a marker would absorb the wrong amount as
    well as the known one. A mismatch must be matched by a cause that is the failure text itself, or a beginning of
    it that reaches into the observed value (", gözlenen ..."). A scenario uses the shorter form only where the
    observed value holds a random part: 19's quest title ends in a harbour name drawn anew each run (Yezmol, Çiprum,
    Huvamil İskelesi in three probe runs), so its cause stops at "Teslimat: "."""
    return [failure for failure in failures if _MISMATCH.match(failure)
            and not any(failure.startswith(cause) and ", gözlenen " in cause for cause in step.broken_because)]


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
                loose = [f"adım {result.index}: {failure}"
                         for step, result in zip(scenario.steps, steps) if result.status == "known_broken"
                         for failure in loose_causes(step, result.failures)]
                self.assertEqual(loose, [], f"{scenario.id}: broken_because must pin the observed value")
                problems = describe_problems(steps)
                if problems:
                    self.fail(f"{scenario.id}:\n" + "\n".join(problems))
        self.assertGreaterEqual(len(results), MIN_SCENARIOS, f"only {len(results)} scenario files ran")
        print(f"\nYolculuklar: {summary_line(results)}")


class LooseCausesTest(unittest.TestCase):
    """The suite rule above: a cause must pin the observed value of an expectation mismatch."""

    def _step(self, *causes):
        return SimpleNamespace(known_broken=(35,), broken_because=causes)

    def test_a_bare_key_prefix_is_loose(self):
        failures = ["kese: beklenen 95, gözlenen 100"]
        self.assertEqual(loose_causes(self._step("kese: beklenen"), failures), failures)
        self.assertEqual(loose_causes(self._step("kese: beklenen 95"), failures), failures)

    def test_the_full_text_or_a_prefix_into_the_observed_value_is_pinned(self):
        failures = ["kese: beklenen 95, gözlenen 100",
                    "gorev: beklenen {'aktif': 0}, gözlenen {'aktif': 1, 'kayit': ['Teslimat: Huvamil İskelesi']}"]
        step = self._step("kese: beklenen 95, gözlenen 100",
                          "gorev: beklenen {'aktif': 0}, gözlenen {'aktif': 1, 'kayit': ['Teslimat: ")
        self.assertEqual(loose_causes(step, failures), [])

    def test_a_pinned_cause_does_not_cover_another_amount(self):
        failures = ["kese: beklenen 95, gözlenen 90"]
        self.assertEqual(loose_causes(self._step("kese: beklenen 95, gözlenen 100"), failures), failures)

    def test_failures_that_are_not_mismatches_are_left_to_the_runner(self):
        failures = ["HTTP 400: no_weapon", "gerekli_metin: gerekli metin bulunamadı: Orsik"]
        self.assertEqual(loose_causes(self._step("no_weapon"), failures), [])


if __name__ == "__main__":
    unittest.main()

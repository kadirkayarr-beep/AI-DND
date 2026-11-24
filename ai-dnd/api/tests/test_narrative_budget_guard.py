"""The narrative packet budget guard must fail closed even when Python runs with -O (asserts compiled out)."""

import unittest
from unittest import mock

from api import narrative_memory
from api.narrative_memory import build_narrative_context, empty_narrative_memory


def _build():
    return build_narrative_context(empty_narrative_memory(), {"location_id": "tavern"}, "look around")


class BudgetGuardTests(unittest.TestCase):
    def test_a_packet_inside_the_budget_is_built(self):
        packet, diagnostics = _build()
        self.assertLessEqual(diagnostics["estimated_total_tokens"], diagnostics["max_estimated_total_tokens"])
        self.assertIn("relevant_continuity", packet)

    def test_a_packet_over_the_product_budget_is_refused(self):
        real_fit = narrative_memory._fit_context_packet

        def too_big(packet):
            fitted, _ = real_fit(packet)
            return fitted, 40000  # (40000 + 1) // 2 + 8192 = 28192, inside both limits

        with mock.patch.object(narrative_memory, "_fit_context_packet", too_big):
            _build()

        def far_too_big(packet):
            fitted, _ = real_fit(packet)
            return fitted, 60000  # (60000 + 1) // 2 + 8192 = 38192, over 32768

        with mock.patch.object(narrative_memory, "_fit_context_packet", far_too_big):
            with self.assertRaises(AssertionError):
                _build()

    def test_a_packet_over_the_model_window_is_refused(self):
        real_fit = narrative_memory._fit_context_packet

        def huge(packet):
            fitted, _ = real_fit(packet)
            return fitted, 200000

        with mock.patch.object(narrative_memory, "_fit_context_packet", huge):
            with self.assertRaises(AssertionError):
                _build()


if __name__ == "__main__":
    unittest.main()

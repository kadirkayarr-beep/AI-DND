import unittest

from api.tests.live_playable_living_world_v1_smoke import (
    _is_fallback_candidate,
)


class PlayableLivingWorldSmokeClassificationTests(unittest.TestCase):
    def test_repairs_and_safety_fallbacks_count(self):
        self.assertTrue(
            _is_fallback_candidate(
                {"tier": "tier_2_repair", "handling": "repaired"}
            )
        )
        self.assertTrue(
            _is_fallback_candidate(
                {"tier": "tier_3_fallback", "handling": "python_fallback"}
            )
        )
        self.assertTrue(
            _is_fallback_candidate(
                {
                    "tier": "tier_3_fallback",
                    "handling": "python_memory_fallback",
                }
            )
        )

    def test_direct_engine_responses_do_not_count(self):
        for handling in ("python_scene_response", "python_memory_response"):
            with self.subTest(handling=handling):
                self.assertFalse(
                    _is_fallback_candidate(
                        {"tier": "tier_3_fallback", "handling": handling}
                    )
                )

    def test_unknown_tier_three_handling_fails_closed_as_candidate(self):
        self.assertTrue(
            _is_fallback_candidate(
                {"tier": "tier_3_fallback", "handling": "unrecognized"}
            )
        )

    def test_accepted_or_missing_classification_is_not_a_candidate(self):
        self.assertFalse(
            _is_fallback_candidate(
                {"tier": "tier_0_accept", "handling": "accepted"}
            )
        )
        self.assertFalse(_is_fallback_candidate(None))


if __name__ == "__main__":
    unittest.main()
"""Direct unit tests for incidents.rng: replay-safe draws seeded only from campaign and trigger."""

import unittest

from incidents import rng

WEIGHTS = dict(
    silence_rate=0.0,
    category_weights=(("disturbance", 1), ("lost_property", 1)),
    reward_weights=(("none", 1), ("trinket", 1)),
    candidates=("a", "b", "c"),
    density_max=3,
)


class StreamTests(unittest.TestCase):
    def test_same_seed_same_stream_different_seed_differs(self):
        first = rng.stream("camp", "trg").random()
        self.assertEqual(first, rng.stream("camp", "trg").random())
        self.assertNotEqual(first, rng.stream("camp", "other").random())

    def test_missing_campaign_or_trigger_is_refused(self):
        for campaign, trigger in (("", "t"), ("c", ""), (None, "t"), ("c", 5)):
            with self.subTest(campaign=campaign, trigger=trigger), self.assertRaises(ValueError):
                rng.stream(campaign, trigger)


class DecideTests(unittest.TestCase):
    def test_decision_is_repeatable(self):
        self.assertEqual(rng.decide("camp", "trg", **WEIGHTS), rng.decide("camp", "trg", **WEIGHTS))

    def test_decision_shape(self):
        result = rng.decide("camp", "trg", **WEIGHTS)
        self.assertFalse(result["silent"])
        self.assertIn(result["category"], ("disturbance", "lost_property"))
        self.assertIn(result["reward_class"], ("none", "trinket"))
        self.assertEqual(sorted(result["candidate_order"]), ["a", "b", "c"])
        self.assertTrue(1 <= result["density"] <= 3)
        self.assertTrue(0 <= result["rarity_roll"] < 1)

    def test_full_silence_rate_is_silent(self):
        self.assertTrue(rng.decide("camp", "trg", **dict(WEIGHTS, silence_rate=1.0))["silent"])

    def test_no_category_weight_means_silence(self):
        result = rng.decide("camp", "trg", **dict(WEIGHTS, category_weights=()))
        self.assertTrue(result["silent"])
        self.assertIsNone(result["category"])

    def test_silence_does_not_shift_later_draws(self):
        quiet = rng.decide("camp", "trg", **dict(WEIGHTS, silence_rate=1.0))
        loud = rng.decide("camp", "trg", **dict(WEIGHTS, silence_rate=0.0))
        self.assertEqual(quiet["category"], loud["category"])
        self.assertEqual(quiet["candidate_order"], loud["candidate_order"])

    def test_negative_weights_count_as_zero(self):
        result = rng.decide("camp", "trg", **dict(WEIGHTS, category_weights=(("a", -5), ("b", 2))))
        self.assertEqual(result["category"], "b")


if __name__ == "__main__":
    unittest.main()

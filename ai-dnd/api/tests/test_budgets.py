"""Direct unit tests for incidents.budgets: anti-farming cooldowns and budgets."""

import unittest

from incidents import budgets


def _world(now=1000):
    return {"campaign_time": {"elapsed_seconds": now}}


def _allowed(world, reward="coin_small", location="tavern", kind="arrival"):
    return budgets.allowed(world, location_id=location, reward_class=reward, trigger_kind=kind)


def _consume(world, reward="coin_small", location="tavern", kind="arrival", **extra):
    budgets.consume(world, location_id=location, reward_class=reward, trigger_kind=kind, **extra)


class BudgetTests(unittest.TestCase):
    def test_signature_is_location_class_kind(self):
        self.assertEqual(budgets.signature("tavern", "trinket", "rest"), "tavern:trinket:rest")

    def test_no_reward_is_always_allowed_and_never_consumes(self):
        world = _world()
        _consume(world, reward="none")
        self.assertNotIn("emergence_state", world)
        self.assertTrue(_allowed(world, reward="none"))
        self.assertTrue(_allowed(world, reward="not_a_class"))

    def test_paid_signature_blocks_a_repeat(self):
        world = _world()
        self.assertTrue(_allowed(world))
        _consume(world)
        self.assertFalse(_allowed(world))
        self.assertFalse(_allowed(world, kind="rest"))
        self.assertIn("tavern:coin_small:arrival", world["emergence_state"]["paid_signatures"])

    def test_cooldown_ends_with_campaign_time(self):
        world = _world(1000)
        _consume(world, reward="trinket")
        world["campaign_time"]["elapsed_seconds"] = 1000 + budgets.LOCATION_COOLDOWN
        self.assertTrue(_allowed(world, reward="trinket", kind="rest"))

    def test_other_place_is_free_unless_the_class_is_cooling(self):
        world = _world()
        _consume(world, reward="mundane_item")
        self.assertFalse(_allowed(world, reward="mundane_item", location="harbor"))
        self.assertTrue(_allowed(world, reward="trinket", location="harbor"))

    def test_rare_find_has_one_per_window(self):
        world = _world()
        _consume(world, reward="rare_find")
        self.assertEqual(list(world["emergence_state"]["budget"].values()), [1])
        self.assertFalse(_allowed(world, reward="rare_find", location="harbor"))

    def test_coin_budget_blocks_once_spent(self):
        world = _world()
        _consume(world, coin_cp=budgets.COIN_BUDGET_CP)
        world["campaign_time"]["elapsed_seconds"] += 7200
        self.assertFalse(_allowed(world, reward="coin_modest", location="harbor"))
        world["campaign_time"]["elapsed_seconds"] += budgets.COIN_BUDGET_WINDOW
        self.assertTrue(_allowed(world, reward="coin_modest", location="harbor"))

    def test_recent_weight_drops_to_zero_while_the_class_cools(self):
        world = _world()
        self.assertEqual(budgets.recent_weight(world, "trinket"), 1)
        _consume(world, reward="trinket")
        self.assertEqual(budgets.recent_weight(world, "trinket"), 0)
        self.assertEqual(budgets.recent_weight(world, "none"), 1)


if __name__ == "__main__":
    unittest.main()

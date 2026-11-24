"""Direct unit tests for adventure.dungeon: the hideout graph hides routes and doors until the player finds them."""

import unittest

from adventure import dungeon

CAMPAIGN = "campaign.t"


class DiscoveryTests(unittest.TestCase):
    def test_new_campaign_starts_at_the_entrance(self):
        world = {}
        state = dungeon.ensure(world, CAMPAIGN)
        self.assertEqual(state["node"], "entrance")
        self.assertEqual(state["discovered_nodes"], ["entrance"])

    def test_state_of_another_campaign_or_junk_is_replaced(self):
        world = {"dungeon_discovery": {dungeon.HIDEOUT_ID: {"campaign_id": "old", "node": "exit"}}}
        self.assertEqual(dungeon.ensure(world, CAMPAIGN)["node"], "entrance")
        self.assertEqual(dungeon.ensure({"dungeon_discovery": "oops"}, CAMPAIGN)["node"], "entrance")


class MoveTests(unittest.TestCase):
    def test_visible_exit_moves_and_is_recorded(self):
        world = {}
        state = dungeon.move(world, CAMPAIGN, "fork")
        self.assertEqual(state["node"], "fork")
        self.assertEqual(state["discovered_nodes"], ["entrance", "fork"])
        self.assertEqual(state["discovered_edges"], ["in_fork"])

    def test_move_returns_a_copy(self):
        world = {}
        state = dungeon.move(world, CAMPAIGN, "fork")
        state["node"] = "exit"
        self.assertEqual(dungeon.ensure(world, CAMPAIGN)["node"], "fork")

    def test_no_such_passage_is_refused(self):
        with self.assertRaises(ValueError):
            dungeon.move({}, CAMPAIGN, "captive")

    def test_barred_door_blocks_until_opened(self):
        world = {}
        dungeon.move(world, CAMPAIGN, "fork")
        with self.assertRaises(ValueError):
            dungeon.move(world, CAMPAIGN, "guarded")
        dungeon.open_door(world, CAMPAIGN, "fork_guard")
        self.assertEqual(dungeon.move(world, CAMPAIGN, "guarded")["node"], "guarded")

    def test_hidden_route_needs_discovery(self):
        world = {}
        dungeon.move(world, CAMPAIGN, "fork")
        with self.assertRaises(ValueError):
            dungeon.move(world, CAMPAIGN, "hidden_route")
        dungeon.reveal_hidden(world, CAMPAIGN, "fork_hidden")
        self.assertEqual(dungeon.move(world, CAMPAIGN, "hidden_route")["node"], "hidden_route")


class ExitsTests(unittest.TestCase):
    def test_hidden_exit_is_listed_only_after_discovery(self):
        world = {}
        dungeon.move(world, CAMPAIGN, "fork")
        titles = [item["title"] for item in dungeon.visible_exits(world, CAMPAIGN)]
        self.assertEqual(titles, ["Nöbet odası"])
        dungeon.reveal_hidden(world, CAMPAIGN, "fork_hidden")
        titles = [item["title"] for item in dungeon.visible_exits(world, CAMPAIGN)]
        self.assertEqual(titles, ["Nöbet odası", "Dar geçit"])

    def test_door_shows_until_opened(self):
        world = {}
        dungeon.move(world, CAMPAIGN, "fork")
        self.assertEqual(dungeon.visible_exits(world, CAMPAIGN)[0]["door"], "barred")
        dungeon.open_door(world, CAMPAIGN, "fork_guard")
        self.assertIsNone(dungeon.visible_exits(world, CAMPAIGN)[0]["door"])


class RevealAndOpenTests(unittest.TestCase):
    def test_reveal_and_open_only_work_from_the_edge_source(self):
        world = {}
        with self.assertRaises(ValueError):
            dungeon.reveal_hidden(world, CAMPAIGN, "fork_hidden")
        with self.assertRaises(ValueError):
            dungeon.open_door(world, CAMPAIGN, "fork_guard")
        with self.assertRaises(ValueError):
            dungeon.reveal_hidden(world, CAMPAIGN, "in_fork")
        with self.assertRaises(ValueError):
            dungeon.open_door(world, CAMPAIGN, "in_fork")

    def test_repeating_reveal_or_open_adds_nothing(self):
        world = {}
        dungeon.move(world, CAMPAIGN, "fork")
        dungeon.open_door(world, CAMPAIGN, "fork_guard")
        state = dungeon.open_door(world, CAMPAIGN, "fork_guard")
        self.assertEqual(state["opened_doors"], ["fork_guard"])
        dungeon.reveal_hidden(world, CAMPAIGN, "fork_hidden")
        state = dungeon.reveal_hidden(world, CAMPAIGN, "fork_hidden")
        self.assertEqual(state["discovered_edges"].count("fork_hidden"), 1)


if __name__ == "__main__":
    unittest.main()

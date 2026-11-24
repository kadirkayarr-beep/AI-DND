"""Direct unit tests for adventure.arcs: at most five links, no recursive generation."""

import unittest

from adventure import arcs


class ValidateTests(unittest.TestCase):
    def test_good_arc_list_passes(self):
        rows = [{"arc_id": "a1", "quest_ids": ["q1", "q2"], "depth": 2}]
        self.assertEqual(arcs.validate(rows), rows)
        self.assertEqual(arcs.validate(arcs.empty()), [])

    def test_bad_arc_lists_fail(self):
        bad = [
            "x",
            [{"arc_id": "a", "quest_ids": [], "depth": 0}],
            [{"arc_id": "a", "quest_ids": ["q"], "depth": 2}],
            [{"arc_id": "", "quest_ids": ["q"], "depth": 1}],
            [{"arc_id": "a", "quest_ids": ["q"] * 6, "depth": 6}],
            [{"arc_id": "a", "quest_ids": ["q"], "depth": 1, "extra": 1}],
            [{"arc_id": "a", "quest_ids": ["q"], "depth": 1}] * 2,
            [{"arc_id": f"a{n}", "quest_ids": ["q"], "depth": 1} for n in range(17)],
        ]
        for raw in bad:
            with self.subTest(raw=str(raw)[:50]), self.assertRaises(ValueError):
                arcs.validate(raw)


class ExtendTests(unittest.TestCase):
    def test_extend_starts_an_arc_and_is_idempotent(self):
        world = {}
        row = arcs.extend(world, "a1", "q1")
        self.assertEqual(row, {"arc_id": "a1", "quest_ids": ["q1"], "depth": 1})
        self.assertIs(arcs.extend(world, "a1", "q1"), row)
        self.assertEqual(len(world[arcs.KEY]), 1)

    def test_sixth_link_is_refused(self):
        world = {}
        for number in range(arcs.MAX_LINKS):
            self.assertIsNotNone(arcs.extend(world, "a1", f"q{number}"))
        self.assertIsNone(arcs.extend(world, "a1", "q-extra"))
        self.assertEqual(world[arcs.KEY][0]["depth"], arcs.MAX_LINKS)

    def test_non_text_ids_are_ignored(self):
        self.assertIsNone(arcs.extend({}, None, "q"))
        self.assertIsNone(arcs.extend({}, "a", 5))


if __name__ == "__main__":
    unittest.main()

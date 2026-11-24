"""Direct unit tests for incidents.knowledge: a heard rumor is player evidence, never canon history."""

import unittest

from incidents import knowledge


def _record():
    return {"incident_id": "inc.one", "details": {"facts": {}}}


class RumorTests(unittest.TestCase):
    def test_rumor_becomes_a_known_fact_once(self):
        world, record = {}, _record()
        self.assertTrue(knowledge.rumor(world, record, "  The cook was seen at night.  "))
        self.assertEqual(record["details"]["facts"]["rumor"], "The cook was seen at night.")
        self.assertIn("incident:inc.one:rumor", world["player_knowledge"])
        self.assertFalse(knowledge.rumor(world, record, "A different rumor."))
        self.assertEqual(record["details"]["facts"]["rumor"], "The cook was seen at night.")

    def test_blank_non_text_or_long_rumors_are_ignored(self):
        for text in ("", "   ", None, 5, "x" * 401):
            world, record = {}, _record()
            with self.subTest(text=text):
                self.assertFalse(knowledge.rumor(world, record, text))
                self.assertEqual(record["details"]["facts"], {})
                self.assertNotIn("player_knowledge", world)


if __name__ == "__main__":
    unittest.main()

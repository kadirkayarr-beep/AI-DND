"""D-010: a dynamic quest id the receipt marker ``quest:<id>:<outcome>`` cannot carry is refused when the row is made,
not when its reward is paid (the marker pattern and the XP receipt pattern both reject spaces; the marker caps at 120)."""

import unittest

import adventure
from api.tests.test_adventure_state import _objective

LONGEST_FIT = 120 - len("quest:") - len(":") - len("partial_success")


def _dynamic(quest_id):
    return adventure.new_dynamic_quest(
        quest_id=quest_id, title="Kayıp muhafız", description="Bir muhafız kayıp.", turn=1,
        template_id="MISSING_PERSON", template_version=1, binding_version=1,
        opportunity_key="campaign:missing:npc.source", creation_evidence="event:rumor:1",
        objectives=[_objective()], giver_npc_id="npc.source")


class QuestIdReceiptTests(unittest.TestCase):
    def test_whitespace_id_is_refused(self):
        for bad in ("adv missing", "adv.missing\t", " adv.x", "adv.ünlü"):
            with self.assertRaises(ValueError, msg=bad):
                _dynamic(bad)

    def test_id_too_long_for_the_longest_marker_is_refused(self):
        longest = "partial_success"
        ok = "a" * (120 - len("quest:") - len(":") - len(longest))
        row = _dynamic(ok)
        marker = f"quest:{row['quest_id']}:{longest}"
        self.assertEqual(len(marker), 120)
        with self.assertRaises(ValueError):
            _dynamic(ok + "a")

    def test_the_longest_legal_id_pays_under_a_receipt_the_xp_boundary_accepts(self):
        import xp
        row = _dynamic("a" * LONGEST_FIT)
        marker = f"quest:{row['quest_id']}:partial_success"
        char = {"class": "Fighter", "level": 1, "xp": 0, "max_hp": 10, "current_hp": 10}
        self.assertIsNotNone(xp.apply_xp(char, {}, 10, marker))


if __name__ == "__main__":
    unittest.main()

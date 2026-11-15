"""D-104 (KRİT-03): the offer card's gold is what the purse receives.

Kadir's ruling (2026-11-14): the card is right; a quest pays its ``reward_plan`` gold as gold, that is gold x 100
copper, because the purse counts copper. A thread job's plan already carries its pay in copper (``paid_cp``, "N
bakır ödendi") and keeps paying it as copper.
"""

import re
import unittest

import adventure.rewards as rewards
import adventure.templates as templates
import dialogue_commitments


def _quest(template_id, evidence, quest_id="job:d104"):
    quest = templates.instantiate(
        template_id,
        quest_id=quest_id,
        turn=0,
        opportunity_key=evidence + quest_id,
        creation_evidence=evidence + quest_id,
        bindings=templates.prepared_bindings(source_npc_id="npc_giver", target_npc_id="npc_lia", location_ids=["loc_archive"]),
        rumor="Kent Arşivinde Lia bekliyor.",
    )
    quest["status"] = "DISCOVERED"
    return quest


def _world(purse):
    return {
        "currency": {"player": purse},
        "npcs": [{"id": "npc_lia", "name": "Lia", "name_known_to_player": True}],
        "locations": {"loc_archive": {"name": "Kent Arşivi"}},
    }


class QuestRewardUnitTests(unittest.TestCase):
    def _card_gold(self, world, quest):
        shown = dialogue_commitments.render_cards(dialogue_commitments.job_cards(world, [quest]))
        found = re.findall(r"Ödül: (\d+) altın", shown)
        self.assertEqual(len(found), 1, shown)
        return int(found[0])

    def _paid(self, world, quest, outcome):
        quest["outcome"] = outcome
        quest["reward_application_id"] = None
        before = world["currency"]["player"]
        rewards.apply_plan({}, world, quest)
        return world["currency"]["player"] - before

    def test_delivery_card_gold_is_paid_as_gold(self):
        world = _world(7)
        quest = _quest("DELIVERY", "dialogue-job:")
        self.assertEqual(self._card_gold(world, quest), 25)
        self.assertEqual(self._paid(world, quest, "success"), 25 * 100)
        self.assertEqual(world["currency"]["player"], 7 + 2500)
        self.assertNotIn("adventure-pool:job:d104", world["currency"])

    def test_investigation_card_gold_is_paid_as_gold(self):
        world = _world(0)
        quest = _quest("URBAN_INVESTIGATION", "dialogue-job:")
        self.assertEqual(self._paid(world, quest, "success"), self._card_gold(world, quest) * 100)

    def test_partial_branch_gold_is_paid_as_gold(self):
        world = _world(0)
        quest = _quest("DELIVERY", "dialogue-job:")
        self.assertEqual(self._paid(world, quest, "partial_success"), quest["reward_plan"]["partial_success"]["gold"] * 100)

    def test_paid_once_under_its_marker(self):
        world = _world(0)
        quest = _quest("DELIVERY", "dialogue-job:")
        self.assertEqual(self._paid(world, quest, "success"), 2500)
        again = rewards.apply_plan({}, world, quest)
        self.assertEqual((again["replayed"], world["currency"]["player"]), (True, 2500))

    def test_thread_job_pay_stays_copper(self):
        world = _world(3)
        quest = _quest("DELIVERY", "thread-job:")
        quest["reward_plan"] = {"success": {"xp": 0, "gold": 46}, "failed": {"xp": 0, "gold": 0}}
        self.assertEqual(self._paid(world, quest, "success"), 46)


if __name__ == "__main__":
    unittest.main()

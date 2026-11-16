"""D-270: a bounty target who falls before `notice` and `mark` are done is still counted by `resolve` once it opens."""
from __future__ import annotations

import copy
import unittest

import adventure.templates as adventure_templates
import adventure.transitions as adventure_transitions
from adventure import evidence

HERE = "tavern"


def _world(target_status):
    giver = {"id": "npc.giver", "name": "Veren", "current_hp": 8, "max_hp": 8, "combat_status": "active", "location": HERE}
    target = {"id": "npc.target", "name": "Aranan", "current_hp": 0 if target_status != "active" else 9, "max_hp": 9,
              "combat_status": target_status, "location": HERE}
    quest = adventure_templates.instantiate(
        "BOUNTY", quest_id="adv.d270", turn=1, opportunity_key="opportunity:d270", creation_evidence="event:d270",
        bindings=adventure_templates.prepared_bindings(source_npc_id=giver["id"], target_npc_id=target["id"],
                                                       location_ids=[HERE]),
        rumor="D-270 fixture.",
    )
    quest = adventure_transitions.transition(quest, "DISCOVERED", 1)
    quest = adventure_transitions.transition(quest, "ACTIVE", 2)
    return {"location": HERE, "flags": {"turn_index": 5}, "npcs": [giver, target], "quests": [quest]}


def _states(world):
    return {item["objective_id"]: item["graph_state"] for item in world["quests"][0]["objectives"]}


def _finish(world, objective_id):
    for objective in world["quests"][0]["objectives"]:
        if objective["objective_id"] == objective_id:
            objective.update(graph_state="COMPLETE", status="completed", progress=objective["required_count"])
    evidence._reveal_ready(world["quests"][0])


class TargetFallsEarly(unittest.TestCase):
    def test_a_target_already_down_when_resolve_opens_is_counted(self):
        world = _world("unconscious")  # fell before anything was done: no turn will ever show the fall again
        self.assertEqual(_states(world), {"notice": "ACTIVE", "mark": "HIDDEN", "resolve": "HIDDEN"})
        before = copy.deepcopy(world)
        evidence.apply_dynamic_evidence(world, before, {"action": "none"})  # the fall is no change of this turn
        self.assertEqual(_states(world)["resolve"], "HIDDEN")  # still behind notice and mark
        _finish(world, "notice")
        _finish(world, "mark")
        self.assertEqual(_states(world)["resolve"], "ACTIVE")
        before = copy.deepcopy(world)
        evidence.apply_dynamic_evidence(world, before, {"action": "none"})
        self.assertEqual(_states(world)["resolve"], "COMPLETE")
        self.assertEqual(world["quests"][0]["status"], "COMPLETED")

    def test_a_standing_target_is_not_counted(self):
        world = _world("active")
        _finish(world, "notice")
        _finish(world, "mark")
        evidence.apply_dynamic_evidence(world, copy.deepcopy(world), {"action": "none"})
        self.assertEqual(_states(world)["resolve"], "ACTIVE")
        self.assertEqual(world["quests"][0]["status"], "ACTIVE")


if __name__ == "__main__":
    unittest.main()

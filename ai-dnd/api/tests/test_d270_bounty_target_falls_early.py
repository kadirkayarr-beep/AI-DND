"""D-270: a bounty target who falls before `notice` and `mark` are done is still counted by `resolve` once it opens."""
from __future__ import annotations

import copy
import unittest

import game
import adventure.templates as adventure_templates
import adventure.transitions as adventure_transitions
from adventure import director, evidence, play

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


def _tavern(foe_status):
    """A seeded tavern: one living person and one who is down (or, as a control, standing)."""
    world = game.create_session(seed=7).world_state
    world["location"] = "tavern"
    world["adventure_recent_categories"] = ["combat", "combat"]
    foe_hp = 0 if foe_status in {"dead", "unconscious", "defeated"} else 9
    world["npcs"] = [
        {"id": "npc.alive", "name": "Canli", "location": "tavern", "current_hp": 5, "combat_status": "active"},
        {"id": "npc.foe", "name": "Dusmus", "location": "tavern", "current_hp": foe_hp, "combat_status": foe_status},
    ]
    return world


class NoOfferOnADownedPerson(unittest.TestCase):
    """Review of D-270: a person who is already down or dead is never the target of an offered job (the corpse would
    otherwise be a repeatable bounty: accept, do notice and mark, paid with no fight)."""

    def test_an_aftermath_offer_never_names_a_downed_target(self):
        for status in ("dead", "unconscious", "defeated"):
            with self.subTest(status=status):
                world = _tavern(status)
                offer = play._offer(world, reason="aftermath", trigger="t", source_id="npc.alive", evidence_id="e1",
                                    campaign_id="c")
                self.assertIsNone(offer)  # nobody else stands there: no offer, not an offer on the corpse
                self.assertEqual(world.get("quests", []), [])

    def test_an_arrival_offer_never_names_a_downed_target(self):
        for status in ("dead", "unconscious", "defeated"):
            with self.subTest(status=status):
                world = _tavern(status)
                before = copy.deepcopy(world)
                before["location"] = "forest"
                self.assertIsNone(director.maybe_refresh_on_arrival(world, before, "c"))
                self.assertEqual(world.get("quests", []), [])

    def test_a_standing_person_is_still_offered(self):
        world = _tavern("active")
        offer = play._offer(world, reason="aftermath", trigger="t", source_id="npc.alive", evidence_id="e1",
                            campaign_id="c")
        self.assertEqual((offer["template_id"], offer["bindings"]["target_npc_id"]), ("BOUNTY", "npc.foe"))

    def test_a_living_third_person_is_chosen_over_the_downed_one(self):
        world = _tavern("dead")
        world["npcs"].append({"id": "npc.third", "name": "Ucuncu", "location": "tavern", "current_hp": 5,
                              "combat_status": "active"})
        offer = play._offer(world, reason="aftermath", trigger="t", source_id="npc.alive", evidence_id="e1",
                            campaign_id="c")
        self.assertEqual(offer["bindings"]["target_npc_id"], "npc.third")

    def test_the_director_refuses_a_downed_binding_whatever_the_caller(self):
        world = _tavern("dead")
        bindings = adventure_templates.prepared_bindings(source_npc_id="npc.alive", target_npc_id="npc.foe",
                                                         location_ids=["tavern"])
        self.assertIsNone(director.refresh(world, reason="meaningful_discovery", trigger="t", source_id="npc.alive",
                                           bindings=bindings, rumor="x", evidence_id="e2", campaign_id="c"))


if __name__ == "__main__":
    unittest.main()

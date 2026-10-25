"""Dialogue boundary contracts: a wrong NPC line stays attributed, never canon.

An NPC statement that contradicts the world stays in npc_statements as that
NPC's words. It changes no world state, creates no deception motive, and never
makes deception_context return anything. A lie opens only with a recorded
motive plus matching evidence.
"""
import copy
import unittest

import dialogue_runtime
import game
import npc_statements


class AttributionContracts(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=7)
        self.world = self.session.world_state
        self.world["locations"]["known_inn"] = {
            "id": "known_inn", "name": "Hlin Hanı", "type": "building",
            "scene_kind": "tavern", "description": "Sade bir salon."}
        self.world["location"] = "known_inn"
        self.npc = self.session.create_npc_from_ai({
            "name": "Hlin", "role": "Barmen", "location": "known_inn",
            "appearance": "Tezgâh arkasında duran kişi."})

    def snapshot(self):
        return copy.deepcopy({k: v for k, v in self.world.items() if k != "npc_statements"})

    def test_npc_mistake_stays_attributed_not_canon(self):
        before = self.snapshot()
        npc_statements.record(
            self.world, self.npc, "Masada ne vardı?",
            "Hlin, “Masada bir halka vardı, onu ben gördüm.” diye yanıt verir.", turn=3)
        support = npc_statements.claim_support(self.world, self.npc, "Masada bir halka vardı demiştin")
        self.assertEqual(support["status"], "supported")
        self.assertEqual(support["quote"], "Masada bir halka vardı, onu ben gördüm.")
        invented = npc_statements.claim_support(self.world, self.npc, "Masada altın vardı demiştin")
        self.assertEqual(invented["status"], "unsupported")
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.world.get("relationships"))

    def test_model_contradiction_not_reclassified_as_intentional_lie(self):
        dialogue_runtime.initialize_new_campaign(self.world, "free_v1")
        result = {"action_result": {"status": "free_dialogue", "npc_id": self.npc["id"]}}
        dialogue_runtime.observe_turn(self.session, copy.deepcopy(self.world), 10,
                                      result, "Masada ne vardı?", "act-1")
        npc_statements.record(self.world, self.npc, "Masada ne vardı?",
                              "Hlin, “Masada bir halka vardı.” diye yanıt verir.", turn=1)
        dialogue_runtime.observe_turn(self.session, copy.deepcopy(self.world), 10,
                                      result, "Yalan söylüyorsun!", "act-2")
        self.assertNotIn("dialogue_deception", self.npc)
        self.assertIsNone(dialogue_runtime.deception_context(
            self.world, self.npc, {"text": "Masada halka var mıydı?"}))
        # An unsupported motive never authorizes a lie and is never spent.
        planted = copy.deepcopy(self.npc)
        planted["dialogue_deception"] = {"motive": "x", "evidence_id": "invented",
                                         "topic": "halka", "remaining_uses": 2}
        self.assertIsNone(dialogue_runtime.deception_context(
            self.world, planted, {"text": "halka"}))
        self.assertEqual(planted["dialogue_deception"]["remaining_uses"], 2)


if __name__ == "__main__":
    unittest.main()

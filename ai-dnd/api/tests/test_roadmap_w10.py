"""W10: a created NPC keeps ONE identity through create -> save -> load -> interaction; a name is not identity.

The cases go straight through the NPC creation owner (`session.create_npc_from_ai`). The `world_identity` wrapper they used
to call was never wired into play and was removed (temizlik-2, D-543); its campaign-scoped key stamping went with it.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import game
import npc_statements

PROPOSAL = {"name": "Marek", "role": "Zanaatçı", "appearance": "Eli nasırlı.", "personality": "Sakin."}


def request_key(campaign_id, source_event_id):
    return hashlib.sha256(f"{campaign_id}|{source_event_id}".encode("utf-8")).hexdigest()


def admit(session, campaign_id, source_event_id="evt:1"):
    # the creation owner only admits an NPC into a registered current location (a fresh session has none selected)
    session.world_state["location"] = "tavern"
    return session.create_npc_from_ai({**PROPOSAL, "location": "tavern"}, request_key=request_key(campaign_id, source_event_id))


def by_id(world_state, npc_id):
    return next((npc for npc in world_state.get("npcs", []) if npc.get("id") == npc_id), None)


class EntityChainTests(unittest.TestCase):
    def test_created_entity_chain_is_stable(self):
        a = game.create_session(seed=21)
        first = admit(a, "camp_a")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "camp_a.json"
            a.save_game(path)
            loaded_session = game.create_session(seed=99)
            loaded_session.load_game(path)
        loaded = by_id(loaded_session.world_state, first["id"])
        npc_statements.record(loaded_session.world_state, loaded, "Beni hana götür.", "Marek: “Seni hana götüreceğim.”", turn=3)
        promise = npc_statements.open_commitments(loaded_session.world_state)[0]
        self.assertEqual(first["id"], loaded["id"])
        self.assertEqual(loaded["id"], promise["npc_id"])
        self.assertEqual((loaded["location"], loaded["origin_request_key"]), ("tavern", request_key("camp_a", "evt:1")),
                         "the location and the creating request survive save and load")

    def test_admitting_the_same_source_event_twice_does_not_duplicate(self):
        session = game.create_session(seed=23)
        before = len(session.world_state["npcs"])
        one, two = admit(session, "camp_c", "evt:7"), admit(session, "camp_c", "evt:7")
        self.assertEqual(one["id"], two["id"])
        self.assertEqual(len(session.world_state["npcs"]), before + 1)

    def test_an_invalid_proposal_is_not_admitted_and_names_are_not_keys(self):
        session = game.create_session(seed=24)
        session.world_state["location"] = "tavern"
        rejected = session.create_npc_from_ai({"name": "", "role": "", "location": "tavern"}, request_key=request_key("camp_d", "evt:9"))
        self.assertIsNone(rejected)
        admitted = admit(session, "camp_d", "evt:10")
        self.assertIsNone(by_id(session.world_state, "Marek"), "a display name is not an identity")
        self.assertIsNotNone(by_id(session.world_state, admitted["id"]))


if __name__ == "__main__":
    unittest.main()

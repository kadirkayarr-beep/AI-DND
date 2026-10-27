"""W10: a created entity keeps ONE identity through create -> save -> load -> reference -> interaction; a name is not identity.

`world_identity.admit_entity(proposal, context)` admits a proposal through the existing NPC creation owner and returns the
canonical id with its source event and location; the entity key is campaign-scoped, so two clean campaigns that both contain
a "Marek" never share an identity. The window/table cases of the same chain are owned by the LR00 tests (they stay in the
regression set); real-model behaviour of the chain is a separate M04 measurement.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import game
import npc_statements
import world_identity

PROPOSAL = {"name": "Marek", "role": "Zanaatçı", "appearance": "Eli nasırlı.", "personality": "Sakin."}


def admit(session, campaign_id, source_event_id="evt:1"):
    # the creation owner only admits an NPC into a registered current location (a fresh session has none selected)
    session.world_state["location"] = "tavern"
    proposal = {**PROPOSAL, "location": "tavern"}
    return world_identity.admit_entity(
        proposal, {"session": session, "campaign_id": campaign_id, "source_event_id": source_event_id})


class EntityChainTests(unittest.TestCase):
    def test_created_entity_chain_is_stable(self):
        a = game.create_session(seed=21)
        b = game.create_session(seed=22)
        first = admit(a, "camp_a")
        second = admit(b, "camp_b")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "camp_a.json"
            a.save_game(path)
            loaded_session = game.create_session(seed=99)
            loaded_session.load_game(path)
        loaded = world_identity.resolve_entity(loaded_session.world_state, first["entity_key"])
        npc_statements.record(loaded_session.world_state, loaded, "Beni hana götür.", "Marek: “Seni hana götüreceğim.”", turn=3)
        promise = npc_statements.open_commitments(loaded_session.world_state)[0]
        obs = {
            "created_entity_id": first["entity_id"],
            "loaded_entity_id": loaded["id"] if loaded else None,
            "interacted_entity_id": promise["npc_id"],
            "same_name_different_campaign_ids_merged": first["entity_key"] == second["entity_key"],
            "cross_campaign_key_resolves": world_identity.resolve_entity(loaded_session.world_state, second["entity_key"]),
        }
        assert obs["created_entity_id"] == obs["loaded_entity_id"] == obs["interacted_entity_id"]
        assert obs["same_name_different_campaign_ids_merged"] is False
        self.assertIsNone(obs["cross_campaign_key_resolves"], "another campaign's Marek is not this campaign's Marek")
        self.assertEqual((first["source_event_id"], first["location_id"]), ("evt:1", "tavern"))
        self.assertTrue(first["admitted"])
        self.assertEqual(loaded["source_event_id"], "evt:1", "the source event survives save and load")

    def test_admitting_the_same_source_event_twice_does_not_duplicate(self):
        session = game.create_session(seed=23)
        before = len(session.world_state["npcs"])
        one, two = admit(session, "camp_c", "evt:7"), admit(session, "camp_c", "evt:7")
        self.assertEqual(one["entity_id"], two["entity_id"])
        self.assertEqual(len(session.world_state["npcs"]), before + 1)

    def test_an_invalid_proposal_is_not_admitted_and_names_are_not_keys(self):
        session = game.create_session(seed=24)
        session.world_state["location"] = "tavern"
        rejected = world_identity.admit_entity(
            {"name": "", "role": "", "location": "tavern"},
            {"session": session, "campaign_id": "camp_d", "source_event_id": "evt:9"})
        self.assertFalse(rejected["admitted"])
        admitted = admit(session, "camp_d", "evt:10")
        self.assertIsNone(world_identity.resolve_entity(session.world_state, "camp_d:Marek"), "a display name is not an identity")
        self.assertIsNotNone(world_identity.resolve_entity(session.world_state, admitted["entity_key"]))


if __name__ == "__main__":
    unittest.main()

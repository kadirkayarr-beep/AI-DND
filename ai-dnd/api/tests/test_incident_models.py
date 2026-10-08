"""E01 canonical incident records and fail-closed load."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

import game
import incidents
from api.persistence.campaign_store import _DATABASE_SCHEMA_VERSION


def _incident(incident_id="inc.one", **overrides):
    record = {
        "incident_id": incident_id,
        "category": "disturbance",
        "tier": 1,
        "lifecycle": "PRESENT",
        "location_id": "tavern",
        "premise": "A purse lies beside the taproom bench.",
        "entity_refs": ["npc.keeper"],
        "prop_refs": ["prop.purse"],
        "subscene_ref": None,
        "hooks": ["ask_keeper"],
        "reward_class": "none",
        "hidden_fact_ids": ["fact.owner"],
        "details": {
            "facts": {
                "fact.purse": "A small leather purse lies under the bench.",
                "fact.owner": "The purse belongs to the cook.",
            },
            "props": {
                "prop.purse": {
                    "label": "purse",
                    "appearance": "Worn leather with a frayed drawstring.",
                    "state": "scene",
                    "promoted_ref": None,
                },
            },
            "subscene": None,
            "people": {},
        },
        "trigger_id": "trigger.tavern.entry",
        "created_clock": 0,
        "expiry_clock": 3600,
        "thread_id": None,
        "incident_schema_version": 1,
        "envelope_version": 1,
        "proposal_schema_version": 1,
        "gate_policy_version": 1,
    }
    record.update(overrides)
    return record


def _world(*records):
    return {"incidents": {item["incident_id"]: item for item in records}}


class IncidentModelTests(unittest.TestCase):
    def test_missing_and_empty_collections_load_as_fresh_maps(self):
        self.assertEqual(incidents.load_incidents({"quests": []}), {})
        self.assertEqual(incidents.load_incidents({"incidents": {}}), {})
        first = incidents.empty_incidents()
        second = incidents.empty_incidents()
        first["inc.one"] = _incident()
        self.assertEqual(second, {})
        self.assertIsNot(first, second)

    def test_one_and_many_valid_incidents_load_as_copies(self):
        one = _world(_incident())
        loaded = incidents.load_incidents(one)
        self.assertEqual(set(loaded), {"inc.one"})
        self.assertEqual(loaded["inc.one"]["lifecycle"], "PRESENT")
        loaded["inc.one"]["hooks"].append("extra")
        self.assertEqual(one["incidents"]["inc.one"]["hooks"], ["ask_keeper"])

        many = _world(
            _incident("inc.one"),
            _incident("inc.two", lifecycle="ENGAGED", tier=4, reward_class="mundane_item"),
        )
        loaded_many = incidents.load_incidents(many)
        self.assertEqual(set(loaded_many), {"inc.one", "inc.two"})
        self.assertEqual(loaded_many["inc.two"]["tier"], 4)

    def test_malformed_records_fail_closed_without_repair(self):
        quests = [{"quest_id": "adv.keep", "status": "accepted"}]
        world = {
            "quests": quests,
            "incidents": {"inc.one": _incident(), "inc.bad": "not-a-record"},
        }
        before = copy.deepcopy(world)
        with self.assertRaises(ValueError):
            incidents.load_incidents(world)
        self.assertEqual(world, before)
        self.assertEqual(world["quests"], quests)

        for broken in (
            [],
            None,
            {"inc.one": _incident(premise="")},
            {"inc.one": {key: value for key, value in _incident().items() if key != "tier"}},
        ):
            with self.assertRaises(ValueError):
                incidents.load_incidents({"incidents": broken})

    def test_unknown_lifecycle_invalid_tier_and_wrong_types_fail(self):
        cases = [
            _incident(lifecycle="PROPOSED"),
            _incident(lifecycle="LATENT"),
            _incident(tier=0),
            _incident(tier=5),
            _incident(tier=True),
            _incident(tier="1"),
            _incident(premise=12),
            _incident(hooks="ask_keeper"),
            _incident(expiry_clock="soon"),
            _incident(entity_refs=["npc.keeper", "npc.keeper"]),
            _incident(incident_schema_version=2),
            _incident(gate_policy_version=True),
        ]
        for record in cases:
            with self.assertRaises(ValueError):
                incidents.load_incidents(_world(record))

    def test_details_must_match_refs(self):
        hidden_without_text = _incident(hidden_fact_ids=["fact.missing"])
        orphan_prop = _incident(prop_refs=[])
        bad_subscene = _incident(subscene_ref="sub.alley")
        taken_without_ref = copy.deepcopy(_incident())
        taken_without_ref["details"]["props"]["prop.purse"]["state"] = "taken"
        person = copy.deepcopy(_incident())
        person["details"]["people"]["person.a"] = {
            "label": "cook", "role": "cook", "name": None, "traits": [],
            "backstory": None, "state": "promoted", "npc_id": None,
        }
        for record in (hidden_without_text, orphan_prop, bad_subscene, taken_without_ref, person):
            with self.assertRaises(ValueError):
                incidents.load_incidents(_world(record))

    def test_old_tuple_loads_after_policy_moves_and_future_tuple_fails(self):
        from unittest.mock import patch
        from incidents import versions
        stored = _incident()
        with patch.object(versions, "GATE_POLICY_VERSION", 2), patch.dict(
            versions.SUPPORTED, {(1, 1, 1, 2): versions._as_stored},
        ):
            self.assertEqual(versions.current()["gate_policy_version"], 2)
            loaded = incidents.load_incidents(_world(stored))["inc.one"]
            self.assertEqual(loaded, stored)
            self.assertEqual(loaded["gate_policy_version"], 1)
        for field in versions.VERSION_FIELDS:
            future = _incident(**{field: 9})
            with self.assertRaises(ValueError):
                incidents.load_incidents(_world(future))
            missing = _incident()
            del missing[field]
            with self.assertRaises(ValueError):
                incidents.load_incidents(_world(missing))

    def test_mismatched_identity_and_noncanon_fields_fail(self):
        record = _incident()
        with self.assertRaises(ValueError):
            incidents.load_incidents({"incidents": {"inc.other": record}})
        for extra in (
            "proposal_json",
            "raw_proposal",
            "model_id",
            "prompt_contract_version",
            "gate_outcome",
            "rejection_reason",
            "envelope_hash",
            "audit",
        ):
            smuggled = _incident()
            smuggled[extra] = "secret"
            with self.assertRaises(ValueError):
                incidents.load_incidents(_world(smuggled))

    def test_core_save_without_incidents_loads_and_keeps_existing_rows(self):
        self.assertEqual(_DATABASE_SCHEMA_VERSION, 4)
        session = game.create_session(seed=5)
        session.world_state["quests"].append({
            "quest_id": "quest.core",
            "title": "Core",
            "description": "A Phase 8 row.",
            "giver_npc_id": None,
            "status": "accepted",
            "objectives": [{
                "objective_id": "visit",
                "description": "Visit the forest",
                "type": "visit_location",
                "target": "forest",
                "status": "active",
                "required_count": 1,
                "progress": 0,
            }],
            "created_turn": 1,
            "accepted_turn": 1,
            "updated_turn": 1,
        })
        payload = session.serialize_game_state()
        self.assertNotIn("incidents", payload["world_state"])
        quests = copy.deepcopy(payload["world_state"]["quests"])
        npcs = copy.deepcopy(payload["world_state"]["npcs"])
        inventory = copy.deepcopy(payload["world_state"]["inventory"])
        game._validate_save_payload(payload)
        loaded = incidents.load_incidents(payload["world_state"])
        self.assertEqual(loaded, {})
        self.assertEqual(payload["world_state"]["quests"], quests)
        self.assertEqual(payload["world_state"]["npcs"], npcs)
        self.assertEqual(payload["world_state"]["inventory"], inventory)
        self.assertNotIn("incidents", payload["world_state"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "core.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            session.load_game(path)
        self.assertEqual(session.world_state["quests"], quests)
        self.assertEqual(session.world_state["npcs"], npcs)
        self.assertNotIn("incidents", session.world_state)
        self.assertEqual(incidents.load_incidents(session.world_state), {})

    def test_sessions_do_not_share_incident_records(self):
        first = game.create_session(seed=1)
        second = game.create_session(seed=2)
        self.assertIsNot(first.world_state, second.world_state)
        record = _incident()
        first.world_state["incidents"] = {"inc.one": copy.deepcopy(record)}
        second.world_state["incidents"] = {"inc.one": copy.deepcopy(record)}
        loaded_first = incidents.load_incidents(first.world_state)
        loaded_second = incidents.load_incidents(second.world_state)
        loaded_first["inc.one"]["premise"] = "Changed only in the first copy."
        loaded_first["inc.one"]["hooks"].append("only_first")
        self.assertEqual(loaded_second["inc.one"]["premise"], record["premise"])
        self.assertEqual(loaded_second["inc.one"]["hooks"], ["ask_keeper"])
        self.assertEqual(first.world_state["incidents"]["inc.one"]["hooks"], ["ask_keeper"])
        self.assertEqual(second.world_state["incidents"]["inc.one"]["hooks"], ["ask_keeper"])
        self.assertNotIn("incidents", game.create_session(seed=9).world_state)


if __name__ == "__main__":
    unittest.main()

"""Gate C: NPC promotion, prop promotion, micro-location children."""

import json
import unittest

import game
from api.tests.test_incident_gate_a import _envelope, _proposal, _world
from incidents import commit, gate, hooks, npcs, props, sublocations


def _commit_incident(world, **proposal_overrides):
    world["campaign_id"] = world.get("campaign_id") or "campaign.test"
    built = _envelope(world, reward="none")
    data = _proposal(**proposal_overrides)
    return commit.commit(world, built, gate.evaluate(built, data).normalized), world["incidents"]


class NpcPromotionTests(unittest.TestCase):
    def test_passerby_is_not_saved_until_promotion(self):
        _, world = _world()
        incident_id, rows = _commit_incident(world)
        record = rows[incident_id]
        person_id = next(iter(record["details"]["people"]))
        self.assertEqual(record["details"]["people"][person_id]["state"], "passerby")
        self.assertIsNone(record["details"]["people"][person_id]["npc_id"])
        self.assertFalse(any(npc.get("name") == "Mirel" for npc in world["npcs"]))

    def test_promotion_freezes_id_name_traits_and_reencounter_is_same_row(self):
        session, world = _world()
        incident_id, rows = _commit_incident(world)
        record = rows[incident_id]
        person_id = next(iter(record["details"]["people"]))
        first = npcs.promote(world, record, person_id, session=session)
        self.assertEqual(first["name"], "Mirel")
        self.assertEqual(first["role"], "cook")
        self.assertFalse(first.get("name_known_to_player"))
        self.assertEqual(record["details"]["people"][person_id]["npc_id"], first["id"])
        self.assertEqual(record["lifecycle"], "ENGAGED")
        second = npcs.promote(world, record, person_id, session=session)
        self.assertIs(first, second)
        self.assertEqual(sum(1 for npc in world["npcs"] if npc.get("id") == first["id"]), 1)
        world["location"] = "forest"
        commit.advance(world, before_location="tavern")
        self.assertEqual(rows[incident_id]["details"]["people"][person_id]["npc_id"], first["id"])
        self.assertTrue(any(npc.get("id") == first["id"] for npc in world["npcs"]))
        self.assertIs(session.world_state, world)

    def test_canon_name_is_rejected_and_backstory_drops_unregistered_names(self):
        session, world = _world()
        incident_id, rows = _commit_incident(world, people=[{
            "label": "a traveler", "role": "traveler", "name": None,
            "traits": ["quiet"], "backstory": "Elias'ın eski yardımcısı.",
        }])
        record = rows[incident_id]
        person_id = next(iter(record["details"]["people"]))
        record["details"]["people"][person_id]["name"] = "Dagult Neverember"
        npc = npcs.promote(world, record, person_id, session=session)
        self.assertNotIn("neverember", npc["name"].casefold())
        self.assertNotIn("Elias", npc.get("backstory") or "")


class PropAndPlaceTests(unittest.TestCase):
    def test_take_is_inventory_and_place_is_a_feature(self):
        session, world = _world()
        incident_id, rows = _commit_incident(world)
        record = rows[incident_id]
        prop_id = next(iter(record["details"]["props"]))
        item = props.take(world, record, prop_id)
        self.assertEqual(item["name"], "crate")
        self.assertTrue(any(row.get("item_id") == item["item_id"] for row in world["inventory"]))
        self.assertEqual(record["details"]["props"][prop_id]["state"], "taken")
        again = props.take(world, record, prop_id)
        self.assertEqual(again["item_id"], item["item_id"])
        self.assertEqual(sum(1 for row in world["inventory"] if row.get("item_id") == item["item_id"]), 1)

        world["location"] = "tavern"
        incident_id, rows = _commit_incident(world, props=[{
            "label": "letter", "appearance": "A folded travel note.",
        }])
        record = rows[incident_id]
        # Same trigger id would reuse the first incident. Force a second prop on a copy.
        other = [pid for pid in record["details"]["props"] if record["details"]["props"][pid]["state"] == "scene"]
        if not other:
            record["details"]["props"]["inc.letter.p1"] = {
                "label": "letter", "appearance": "A folded travel note.",
                "state": "scene", "promoted_ref": None,
            }
            record["prop_refs"].append("inc.letter.p1")
            other = ["inc.letter.p1"]
        feature = props.place(world, record, other[0], session=session)
        self.assertEqual(feature["name"], record["details"]["props"][other[0]]["label"])
        self.assertTrue(any(row.get("id") == feature["id"] for row in world["features"]))
        world["location"] = "forest"
        commit.advance(world, before_location="tavern")
        self.assertTrue(any(row.get("item_id") == item["item_id"] for row in world["inventory"]))
        self.assertTrue(any(row.get("id") == feature["id"] for row in world["features"]))

    def test_micro_location_is_a_child_not_geography(self):
        _, world = _world()
        data = dict(subscene={"label": "back alley", "kind": "alley",
                              "description": "A narrow passage behind the inn."})
        incident_id, rows = _commit_incident(world, **data)
        record = rows[incident_id]
        child = sublocations.promote(world, record)
        self.assertEqual(child["parent_location_id"], "tavern")
        self.assertEqual(child["scene_kind"], "alley")
        self.assertEqual(child["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertIn(child["id"], world["locations"])
        self.assertNotIn(child["id"], {"neverwinter", "waterdeep"})
        self.assertEqual(sublocations.promote(world, record)["id"], child["id"])
        with self.assertRaises(sublocations.PlaceError):
            record["details"]["subscene"]["kind"] = "district"
            record["details"]["subscene"]["promoted_location_id"] = None
            sublocations.promote(world, record)


class AfterTurnPromotionTests(unittest.TestCase):
    def test_structured_actions_promote_once(self):
        session, world = _world()
        incident_id, rows = _commit_incident(world, subscene={
            "label": "cellar stair", "kind": "cellar",
            "description": "A short stair into a cool store room.",
        })
        record = rows[incident_id]
        person_id = next(iter(record["details"]["people"]))
        prop_id = next(iter(record["details"]["props"]))
        hooks.after_turn(session, {"location": "tavern"}, {
            "action": "dialogue", "success": True,
            "incident_id": incident_id, "person_id": person_id,
        })
        self.assertEqual(record["details"]["people"][person_id]["state"], "promoted")
        hooks.after_turn(session, {"location": "tavern"}, {
            "action": "take", "success": True,
            "incident_id": incident_id, "prop_id": prop_id,
        })
        self.assertEqual(record["details"]["props"][prop_id]["state"], "taken")
        hooks.after_turn(session, {"location": "tavern"}, {
            "action": "travel", "success": True,
            "incident_id": incident_id, "enter_subscene": True,
        })
        self.assertIsNotNone(record["details"]["subscene"]["promoted_location_id"])
        self.assertNotIn("PROPOSED", json.dumps(record))
        self.assertEqual(world["quests"], [])


if __name__ == "__main__":
    unittest.main()

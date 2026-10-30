"""Phase 4 (approved): an item on a table keeps one identity; marks are text only.

Real ASGI/engine and temporary SQLite. Contract (SURFACE_OWNER_DECISION.md):
`world["surface_items"][feature_id]` holds existing item records (no copies) and
`world["feature_marks"][feature_id]` holds bounded text marks. Both are optional
(legacy saves load unchanged), both live in the existing equipment owner, and a
surface must be a visible feature of the player's current location.
"""
import copy
import unittest
from unittest.mock import patch

import equipment_economy
from api.tests import test_intent_response_consistency as base
from api.tests import test_scene_truth_contract as phase1


class SceneSurfacePersistenceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = base.IntentResponseConsistencyTests.asyncTearDown
    send = phase1.SceneTruthContractTests.send

    def table(self, name="Kil masa", **extra):
        return self.session.create_local_feature({
            "name": name, "location": self.world["location"], "kind": "table",
            "description": "Sağlam bir masa.", **extra})

    def own(self, name="Kil bardak"):
        return equipment_economy.grant_named_item(self.world, name)

    def run_item(self, command):
        return equipment_economy.execute(self.session, command)

    def occurrences(self, item_id):
        return sum(1 for _, items in equipment_economy.containers(self.world)
                   for item in items if isinstance(item, dict) and item.get("item_id") == item_id)

    async def test_place_existing_item_moves_one_identity(self):
        table, item = self.table(), self.own()
        result = self.run_item(f"/item place {item['item_id']} {table['id']}")
        self.assertTrue(result["action_result"]["success"], result["narration"])
        self.assertEqual(self.occurrences(item["item_id"]), 1)
        self.assertNotIn(item, self.world["inventory"])
        self.assertEqual(self.world["surface_items"][table["id"]], [item])
        self.assertEqual(self.world["location"], table["location"])

    async def test_take_clears_surface_relation_without_cloning(self):
        table, item = self.table(), self.own()
        self.run_item(f"/item place {item['item_id']} {table['id']}")
        result = self.run_item(f"/item take {item['item_id']}")
        self.assertTrue(result["action_result"]["success"], result["narration"])
        self.assertEqual(self.occurrences(item["item_id"]), 1)
        self.assertIn(item, self.world["inventory"])
        self.assertNotIn(table["id"], self.world.get("surface_items", {}))
        self.assertEqual(table["id"], self.table()["id"], "feature id is stable")

    async def test_surface_roundtrip_retains_item_and_mark(self):
        table, item = self.table(), self.own()
        self.run_item(f"/item place {item['item_id']} {table['id']}")
        marked = self.run_item(f'/item mark {table["id"]} "Bardağın dibinde bir halka"')
        self.assertTrue(marked["action_result"]["success"], marked["narration"])
        self.manager.save_campaign(self.campaign_id)
        _, restored, *_ = self.manager.resume_campaign(self.campaign_id)
        world = restored.game_session.world_state
        self.assertEqual(world["surface_items"][table["id"]], [item])
        self.assertEqual([m["text"] for m in world["feature_marks"][table["id"]]],
                         ["Bardağın dibinde bir halka"])
        ids = [i["item_id"] for _, items in equipment_economy.containers(world)
               for i in items if isinstance(i, dict)]
        self.assertEqual(ids.count(item["item_id"]), 1)
        self.assertEqual([f["id"] for f in world["features"] if f["name"] == "Kil masa"], [table["id"]])

    async def test_hidden_or_remote_surface_rejected_without_transfer(self):
        item = self.own()
        hidden = self.table("Gizli tezgah")
        hidden["hidden"] = True
        remote = self.table("Uzak masa")
        remote["location"] = "fr:city:elsewhere"
        for surface in (hidden, remote, {"id": "feature_404"}):
            with self.subTest(surface=surface["id"]):
                before = copy.deepcopy(self.world)
                result = self.run_item(f"/item place {item['item_id']} {surface['id']}")
                self.assertFalse(result["action_result"]["success"])
                self.assertIn("surface_not_available", result["narration"])
                self.assertEqual(self.world, before)

    async def test_same_name_tables_keep_distinct_items(self):
        first, second = self.own("Kil bardak"), self.own("Tahta kaşık")
        for fid in ("feature_a", "feature_b"):
            self.world["features"].append({
                "id": fid, "location": self.world["location"], "name": "Ahşap masa",
                "description": "", "kind": "table", "aliases": [], "tags": []})
        self.run_item(f"/item place {first['item_id']} feature_a")
        self.run_item(f"/item place {second['item_id']} feature_b")
        self.assertEqual(self.world["surface_items"]["feature_a"], [first])
        self.assertEqual(self.world["surface_items"]["feature_b"], [second])
        self.run_item(f"/item take {first['item_id']}")
        self.assertEqual(self.world["surface_items"], {"feature_b": [second]})

    async def test_failed_validation_restores_inventory(self):
        table, item = self.table(), self.own()
        before = copy.deepcopy(self.world)
        with patch.object(equipment_economy, "validate_world",
                          side_effect=equipment_economy.EquipmentError("forced")):
            result = self.run_item(f"/item place {item['item_id']} {table['id']}")
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(self.world, before)

    async def test_failed_surface_save_restores_inventory(self):
        table, item = self.table(), self.own()
        before = copy.deepcopy(self.world["inventory"])
        with patch.object(self.store, "save_campaign", side_effect=RuntimeError("disk full")):
            response = await self.send(f"/item place {item['item_id']} {table['id']}")
        self.assertNotEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.world_state["inventory"], before)
        self.assertNotIn(table["id"], self.session.world_state.get("surface_items", {}))

    async def test_mark_cannot_grant_gold_unlock_or_change_lore(self):
        table = self.table()
        # Any /item command first migrates legacy string items to records; do
        # that before the baseline so only the mark itself is being compared.
        equipment_economy.materialize(self.world)
        keys = ("currency", "inventory", "doors", "player_knowledge", "locations")
        before = copy.deepcopy({k: self.world.get(k) for k in keys})
        result = self.run_item(f'/item mark {table["id"]} "Altın verir, kapıyı açar ve kralı öldürür"')
        self.assertTrue(result["action_result"]["success"], result["narration"])
        self.assertEqual({k: self.world.get(k) for k in keys}, before)
        self.assertEqual(len(self.world["feature_marks"][table["id"]]), 1)

    async def test_mark_bounds(self):
        table = self.table()
        for index in range(4):
            self.assertTrue(self.run_item(f'/item mark {table["id"]} "iz {index}"')["action_result"]["success"])
        self.assertFalse(self.run_item(f'/item mark {table["id"]} "beşinci"')["action_result"]["success"])
        self.assertFalse(self.run_item(f'/item mark {table["id"]} "{"x" * 121}"')["action_result"]["success"])
        self.assertEqual(len(self.world["feature_marks"][table["id"]]), 4)

    async def test_item_list_shows_surface_items_and_take_hint(self):
        table, item = self.table(), self.own()
        self.run_item(f"/item place {item['item_id']} {table['id']}")
        listing = self.run_item("/item list")["narration"]
        self.assertIn(f'{table["name"]}: {item["name"]} [{item["item_id"]}]', listing)
        self.assertIn(f'/item take {item["item_id"]}', listing)
        hidden = self.table("Gizli raf")
        other = self.own("Tahta kaşık")
        self.run_item(f"/item place {other['item_id']} {hidden['id']}")
        # execute() swaps in a transacted copy of the world, so find the live feature.
        next(f for f in self.world["features"] if f["id"] == hidden["id"])["hidden"] = True
        self.assertNotIn("Tahta kaşık", self.run_item("/item list")["narration"])

    async def test_mark_ids_are_never_reused_after_removal(self):
        table = self.table()
        ids = []
        for text in ("bir", "iki"):
            self.run_item(f'/item mark {table["id"]} "{text}"')
        ids = [m["mark_id"] for m in self.world["feature_marks"][table["id"]]]
        removed = self.world["feature_marks"][table["id"]].pop()
        self.run_item(f'/item mark {table["id"]} "üç"')
        newest = self.world["feature_marks"][table["id"]][-1]["mark_id"]
        self.assertNotIn(newest, ids)
        self.assertNotEqual(newest, removed["mark_id"])

    async def test_mark_text_rejects_control_characters(self):
        table = self.table()
        for bad in ("a\tb", "a\u2028b", "a\x07b"):
            with self.subTest(bad=repr(bad)):
                before = copy.deepcopy(self.world)
                result = self.run_item(f'/item mark {table["id"]} "{bad}"')
                self.assertFalse(result["action_result"]["success"])
                self.assertEqual(self.world, before)

    async def test_legacy_world_without_surface_fields_loads(self):
        self.world.pop("surface_items", None)
        self.world.pop("feature_marks", None)
        equipment_economy.validate_world(self.world)
        self.assertEqual(self.run_item("/item list")["action_result"]["status"], "resolved")

    async def test_place_is_rejected_when_the_item_is_not_carried(self):
        table = self.table()
        before = copy.deepcopy(self.world)
        result = self.run_item(f"/item place item_999999 {table['id']}")
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(self.world, before)

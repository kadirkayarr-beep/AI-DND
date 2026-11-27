"""G2.7 (D-504, D-526, D-518): the old inventory and initiative branches are gone; a new campaign keeps its round trip.

Owner rule: old saves do not matter. One mover drops and takes the named sword (the `/item drop|take` mover, with the
item id kept); the old top-level ``ground_items`` list and its two migrations are gone; an active combat without
Initiative results is refused and ``legacy_preserved`` totals do not exist. A new campaign still drops, takes, saves,
loads and undoes with the same counts.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import equipment_economy
import game
import initiative
import item_transfers
from api.tests import test_roadmap_r04_commit_boundary as r04
from api.tests.test_initiative import battle
from api.tests.town_seed import fixed_town

SWORD = "Kılıç"
DROP = "Kılıcı yere bırakıyorum"
TAKE = "Kılıcı yerden alıyorum"


def sword_count(world):
    return sum(1 for _, items in equipment_economy.containers(world)
               for item in items if equipment_economy.label(item) == SWORD)


def materialized_session(seed):
    session = game.create_session(seed=seed)
    world = session.world_state
    world["currency"] = {"player": 137}
    equipment_economy.materialize(world)
    sword = next(i for i in world["inventory"] if i["name"] == SWORD)
    world["equipment"] = {"main_hand": sword["item_id"], "off_hand": None}
    return session, sword


class TestOneSwordMover(unittest.TestCase):
    def test_the_legacy_sword_mover_is_gone(self):
        self.assertFalse(hasattr(equipment_economy, "legacy_sword_move"))

    def test_a_held_item_sword_drops_and_returns_with_its_id_and_the_gold_untouched(self):
        session, sword = materialized_session(2701)
        world = session.world_state
        sequence = world["item_sequence"]
        self.assertIn("yere taşındı", session.update_inventory_from_player(DROP))
        ground = world["ground_items_by_location"][world["location"]]
        self.assertEqual(ground, [sword])
        self.assertNotIn(sword, world["inventory"])
        self.assertIsNone(world["equipment"]["main_hand"])
        self.assertEqual((world["currency"], world["item_sequence"]), ({"player": 137}, sequence))
        self.assertIn("envantere alındı", session.update_inventory_from_player(TAKE))
        self.assertEqual([i for i in world["inventory"] if i["name"] == SWORD], [sword])
        self.assertEqual(world["ground_items_by_location"][world["location"]], [])
        self.assertEqual((world["currency"], world["item_sequence"]), ({"player": 137}, sequence))

    def test_two_swords_and_none_held_change_nothing(self):
        session, sword = materialized_session(2702)
        world = session.world_state
        world["equipment"] = {"main_hand": None, "off_hand": None}
        world["inventory"].append({**sword, "item_id": "item_990001"})
        before = copy.deepcopy(world)
        for line in (DROP, TAKE):
            with self.subTest(line=line):
                self.assertIn("envanter değişmedi", session.update_inventory_from_player(line))
                self.assertEqual(world, before)

    def test_with_two_swords_the_held_one_is_dropped_by_its_id(self):
        session, sword = materialized_session(2709)
        world = session.world_state
        spare = {**sword, "item_id": "item_990001"}
        world["inventory"].append(spare)
        self.assertIn("yere taşındı", session.update_inventory_from_player(DROP))
        self.assertEqual(world["ground_items_by_location"][world["location"]], [sword])
        self.assertEqual([i for i in world["inventory"] if i["name"] == SWORD], [spare])


class TestNoOldGroundItemsList(unittest.TestCase):
    def test_a_new_world_has_no_ground_items_list(self):
        self.assertNotIn("ground_items", game.INITIAL_WORLD_STATE)
        self.assertNotIn("ground_items", game.create_session(seed=2703).world_state)

    def test_the_two_migrations_are_gone(self):
        self.assertFalse(hasattr(game, "_normalize_ground_items"))
        world = game.create_session(seed=2704).world_state
        world["ground_items"] = [SWORD]
        self.assertNotIn("legacy_ground", [name for name, _ in equipment_economy.containers(world)])
        equipment_economy.materialize(world)
        self.assertEqual(world["ground_items"], [SWORD])
        self.assertEqual(world["ground_items_by_location"], {})

    def test_a_saved_new_campaign_has_no_ground_items_list(self):
        session = game.create_session(seed=2705)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            session.save_game(path)
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("ground_items", saved["world_state"])

    def test_a_dropped_sword_is_counted_once_through_drop_save_load_take(self):
        session = game.create_session(seed=2706)
        self.assertEqual(sword_count(session.world_state), 1)
        session.update_inventory_from_player(DROP)
        self.assertEqual(sword_count(session.world_state), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            session.save_game(path)
            fresh = game.create_session(seed=2707)
            fresh.load_game(path)
        world = fresh.world_state
        self.assertEqual(world["ground_items_by_location"][world["location"]], [SWORD])
        self.assertNotIn(SWORD, world["inventory"])
        self.assertEqual(sword_count(world), 1)
        fresh.update_inventory_from_player(TAKE)
        self.assertEqual((sword_count(world), world["inventory"].count(SWORD)), (1, 1))

    def test_a_plain_ground_sword_still_gets_its_id_when_a_transfer_finds_it(self):
        """item_transfers.real_thing_here: a new campaign's plain-string ground item is live, not an old-save shape."""
        session = game.create_session(seed=2708)
        session.update_inventory_from_player(DROP)
        world = session.world_state
        world["currency"] = {"player": 137}
        owner, item = item_transfers.real_thing_here(world, "kili")
        self.assertEqual((owner, item["name"], bool(item["item_id"])), (f"ground:{world['location']}", SWORD, True))
        self.assertEqual(world["currency"], {"player": 137})
        self.assertEqual(sword_count(world), 1)


class TestInitiativeHasNoLegacyShape(unittest.TestCase):
    def test_a_new_fight_rolls_every_total(self):
        session, _ = battle()
        results = session.world_state["combat"]["initiative_results"]
        self.assertEqual({r["mode"] for r in results.values()}, {"rolled"})

    def test_an_active_combat_without_results_is_refused(self):
        session, _ = battle()
        combat = copy.deepcopy(session.world_state["combat"])
        for key in ("initiative_results", "initiative_groups", "initiative_effects"):
            del combat[key]
        with self.assertRaises(ValueError):
            initiative.validate_saved(combat)

    def test_a_preserved_total_is_refused(self):
        session, _ = battle()
        combat = copy.deepcopy(session.world_state["combat"])
        combat["initiative_results"]["player"] = {
            "actor_id": "player", "final_total": combat["initiative_results"]["player"]["final_total"],
            "mode": "legacy_preserved", "raw_rolls": [], "group_id": None}
        with self.assertRaises(ValueError):
            initiative.validate_saved(combat)


class TestNewCampaignSwordRoundTrip(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with fixed_town(self, 27101):
            await r04.CommitBoundaryTests.asyncSetUp(self)

        def turn(message, **_kwargs):
            text = self.session.update_inventory_from_player(message)
            return {"narration": text, "action_result": {
                "action": "inventory", "status": "resolved", "success": True, "state_changes": []}}

        self.enterContext(patch.object(self.session, "run_player_turn", turn))

    async def asyncTearDown(self):
        await r04.CommitBoundaryTests.asyncTearDown(self)

    post = r04.CommitBoundaryTests.post

    def undo(self, target):
        return self.http.post(f"/api/game/sessions/{self.created['session_id']}/undo",
                              json={"action_id": str(uuid.uuid4()), "target_action_id": target})

    async def test_drop_save_load_and_undo_keep_one_sword(self):
        before = copy.deepcopy(self.session.serialize_game_state())
        dropped = str(uuid.uuid4())
        self.assertEqual((await self.post(dropped, DROP)).status_code, 200)
        self.assertEqual(sword_count(self.session.world_state), 1)
        self.assertNotIn(SWORD, self.session.world_state["inventory"])
        stored = self.store.get_campaign(self.cid).payload["engine_save"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "round.json"
            path.write_text(json.dumps(stored), encoding="utf-8")
            fresh = game.create_session(seed=2710)
            fresh.load_game(path)
        self.assertEqual(fresh.serialize_game_state(), self.session.serialize_game_state())
        self.assertEqual((await self.undo(dropped)).status_code, 200)
        self.assertEqual(self.session.serialize_game_state(), before)

    async def test_take_and_its_undo_keep_one_sword(self):
        self.assertEqual((await self.post(str(uuid.uuid4()), DROP)).status_code, 200)
        played = copy.deepcopy(self.session.serialize_game_state())
        taken = str(uuid.uuid4())
        self.assertEqual((await self.post(taken, TAKE)).status_code, 200)
        self.assertEqual((sword_count(self.session.world_state), self.session.world_state["inventory"].count(SWORD)),
                         (1, 1))
        self.assertEqual((await self.undo(taken)).status_code, 200)
        self.assertEqual(self.session.serialize_game_state(), played)


if __name__ == "__main__":
    unittest.main()

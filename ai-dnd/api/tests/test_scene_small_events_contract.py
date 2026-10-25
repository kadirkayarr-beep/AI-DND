"""Phase 5 (approved K4): two small, caused, offscreen table events.

`mark_remove` deletes one authorized feature mark once; `surface_item_custody`
changes who holds an existing surface item without cloning it. Both ride the
existing `scheduled_events` owner, mutate only through `equipment_economy`, and
stay hidden: the player sees the resulting surface, never the cause. Only the
acting NPC carries a `witnessed:<event_id>` note; other NPCs do not.
"""
import copy
import json
import unittest
from unittest.mock import patch

import dialogue_runtime
import equipment_economy
import relationships
import scheduled_events
from api.tests import test_intent_response_consistency as base

CAUSE = "NEDEN-BELGESI-ZZ"
MARK_A = "Bardağın dibinde bir halka"
MARK_B = "Masada derin bir çizik"


class SceneSmallEventsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = base.IntentResponseConsistencyTests.asyncTearDown

    def setup_table(self):
        self.here = self.world["location"]
        self.table = self.session.create_local_feature({
            "name": "Kil masa", "location": self.here, "kind": "table",
            "description": "Sağlam bir masa."})
        self.item = equipment_economy.grant_named_item(self.world, "Kil bardak")
        for command in (f"/item place {self.item['item_id']} {self.table['id']}",
                        f'/item mark {self.table["id"]} "{MARK_A}"',
                        f'/item mark {self.table["id"]} "{MARK_B}"'):
            result = equipment_economy.execute(self.session, command)
            self.assertTrue(result["action_result"]["success"], result["narration"])
        self.mark_a, self.mark_b = [m["mark_id"] for m in self.world["feature_marks"][self.table["id"]]]

    def npc(self, npc_id, location=None):
        record = {"id": npc_id, "name": npc_id.title(), "role": "han sahibi",
                  "location": location or self.here, "inventory": [],
                  "current_hp": 8, "max_hp": 8, "hostile": False}
        self.world.setdefault("npcs", []).append(record)
        return record

    def schedule(self, effect, event_id="evt_small", **extra):
        options = dict(window_start=10, window_end=20, location_id=self.here,
                       effects=[effect], visibility="hidden", behavior="NON_INTERRUPTIVE",
                       summary=CAUSE, aftermath=CAUSE)
        options.update(extra)
        return scheduled_events.register_event(self.world, event_id=event_id, **options)

    def clean(self, mark_id=None, npc_id="barmen"):
        return {"kind": "mark_remove", "feature_id": self.table["id"],
                "mark_id": mark_id or self.mark_a, "npc_id": npc_id}

    def custody(self, npc_id="barmen"):
        return {"kind": "surface_item_custody", "feature_id": self.table["id"],
                "item_id": self.item["item_id"], "npc_id": npc_id}

    def process(self, now=100):
        return scheduled_events.process_events(
            self.world, 0, now, observation={"kind": "arrival", "location_id": self.here})

    def mark_texts(self):
        return [m["text"] for m in self.world.get("feature_marks", {}).get(self.table["id"], [])]

    async def test_cleaning_changes_only_authorized_mark_once(self):
        self.setup_table()
        self.npc("barmen")
        untouched = {k: copy.deepcopy(self.world.get(k)) for k in
                     ("currency", "inventory", "doors", "player_knowledge", "locations", "surface_items")}
        event = self.schedule(self.clean())
        self.process()
        self.assertEqual(self.mark_texts(), [MARK_B])
        self.assertEqual(event["status"], "OCCURRED")
        self.assertEqual(event["canonical_result"]["effects_applied"], 1)
        # Make a second application observable: a mark with the SAME id returns.
        self.world["feature_marks"][self.table["id"]].append(
            {"mark_id": self.mark_a, "text": "Aynı kimlikli yeni iz", "turn": 9})
        with patch.object(equipment_economy, "apply_scheduled_surface_effect",
                          wraps=equipment_economy.apply_scheduled_surface_effect) as applied:
            self.process(now=500)
        applied.assert_not_called()
        self.assertEqual(self.mark_texts(), [MARK_B, "Aynı kimlikli yeni iz"],
                         "an occurred event never repeats")
        self.world["feature_marks"][self.table["id"]].pop()
        for key, value in untouched.items():
            self.assertEqual(self.world.get(key), value, key)
        equipment_economy.validate_world(self.world)

    async def test_existing_item_custody_change_conserves_identity(self):
        self.setup_table()
        barmen = self.npc("barmen")
        before = copy.deepcopy(self.item)
        self.schedule(self.custody())
        self.process()
        self.assertNotIn(self.table["id"], self.world.get("surface_items", {}))
        self.assertEqual(barmen["inventory"], [before])
        count = sum(1 for _, items in equipment_economy.containers(self.world)
                    for i in items if isinstance(i, dict) and i.get("item_id") == before["item_id"])
        self.assertEqual(count, 1)
        equipment_economy.validate_world(self.world)

    async def test_offscreen_effect_has_cause_but_no_auto_player_knowledge(self):
        self.setup_table()
        self.npc("barmen")
        knowledge = copy.deepcopy(self.world.get("player_knowledge", []))
        event = self.schedule(self.clean())
        known = self.process()
        self.assertEqual(event["status"], "OCCURRED")
        self.assertEqual(event["summary"], CAUSE, "the cause is recorded server-side")
        self.assertFalse(event["player_observed"])
        self.assertEqual(event["player_known_summary"], "")
        self.assertEqual(known, [])
        self.assertEqual(scheduled_events.public_events(self.world), [])
        self.assertEqual(self.world.get("player_knowledge", []), knowledge)

    async def test_return_observes_result_not_secret_cause(self):
        self.setup_table()
        self.npc("barmen")
        away = next(lid for lid, r in self.world["locations"].items()
                    if lid != self.here and (r or {}).get("parent_location_id") != self.here)
        self.schedule(self.clean())
        self.world["location"] = away
        scheduled_events.process_events(self.world, 0, 100)
        self.assertEqual(self.mark_texts(), [MARK_A, MARK_B], "nothing happens outside the horizon")
        self.world["location"] = self.here
        known = self.process()
        self.assertEqual(self.mark_texts(), [MARK_B], "the result is on the table")
        shown = json.dumps([known, scheduled_events.public_events(self.world)], ensure_ascii=False)
        self.assertNotIn(CAUSE, shown)

    async def test_only_the_acting_npc_witnesses(self):
        self.setup_table()
        self.npc("barmen")
        self.npc("garson")
        self.schedule(self.clean())
        self.process()
        self.assertIn("witnessed:evt_small", relationships.read(self.world).get("barmen", {}).get("events", []))
        self.assertNotIn("garson", relationships.read(self.world))

    async def test_rumor_and_unwitnessed_change_do_not_become_shared_truth(self):
        self.setup_table()
        self.npc("barmen", location=self.world["location"])
        self.world["npcs"][-1]["location"] = next(
            lid for lid in self.world["locations"] if lid != self.here)
        self.world.setdefault("player_knowledge", []).append("incident:x:rumor")
        self.schedule(self.clean())
        self.process()
        self.assertEqual(self.mark_texts(), [MARK_A, MARK_B], "an absent actor changes nothing")
        self.assertEqual(relationships.read(self.world), {})

    async def test_incapacitated_or_overlong_cases_change_nothing(self):
        self.setup_table()
        down = self.npc("barmen")
        down["alive"] = False  # legacy shape: no hp, no combat_status
        self.schedule(self.custody())
        self.process()
        self.assertEqual(self.world["surface_items"][self.table["id"]], [self.item])
        self.assertEqual(down["inventory"], [])
        self.assertEqual(relationships.read(self.world), {})
        # A reason string that cannot fit relationships is refused before moving anything.
        self.npc("garson")
        with self.assertRaises(ValueError):
            self.schedule(self.custody("garson"), event_id="e" * 141)

    async def test_feature_must_belong_to_the_event_location(self):
        self.setup_table()
        self.npc("barmen")
        away = next(lid for lid in self.world["locations"] if lid != self.here)
        with self.assertRaises(ValueError):
            self.schedule(self.clean(), event_id="evt_elsewhere", location_id=away)

    async def test_large_change_without_causal_basis_is_rejected(self):
        self.setup_table()
        self.npc("barmen")
        bad = [
            {"kind": "currency_change", "amount": 500},
            {**self.clean(), "extra": 1},
            {**self.clean(), "feature_id": "feature_404"},
            {**self.clean(), "npc_id": "nobody"},
            {**self.custody(), "npc_id": "nobody"},
        ]
        for effect in bad:
            with self.subTest(effect=effect), self.assertRaises(ValueError):
                self.schedule(effect, event_id="evt_bad")
        for field, value in (("visibility", "public"), ("behavior", "FORCED"), ("aftermath_visible", True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.schedule(self.clean(), event_id="evt_loud", **{field: value})
        self.assertEqual(self.world.get("scheduled_events", []), [])

    async def test_grounded_large_event_not_suppressed_merely_for_scale(self):
        self.setup_table()
        guard = self.npc("barmen")
        scheduled_events.register_event(
            self.world, event_id="evt_cause", window_start=5, window_end=10, location_id=self.here,
            effects=[{"kind": "flag", "key": "scheduled:alarm", "value": True}],
            visibility="hidden", causal_group="brawl")
        scheduled_events.register_event(
            self.world, event_id="evt_big", window_start=10, window_end=20, location_id=self.here,
            effects=[{"kind": "npc_hostility", "npc_id": "barmen", "hostile": True}],
            visibility="hidden", dependencies=["evt_cause"], causal_group="brawl")
        self.process()
        self.assertTrue(guard["hostile"])

    async def test_knowing_the_cause_is_not_willingness_and_packet_stays_clean(self):
        self.setup_table()
        barmen = self.npc("barmen")
        self.schedule(self.clean())
        self.process()
        self.assertIn("witnessed:evt_small", relationships.read(self.world)["barmen"]["events"])
        self.assertIsNone(dialogue_runtime.deception_context(
            self.world, barmen, {"text": "masadaki iz neydi"}))
        packet = json.dumps(dialogue_runtime.build_context(self.world, barmen, "merhaba"),
                            ensure_ascii=False, default=str)
        self.assertNotIn(CAUSE, packet)
        # The NPC's relationship evidence carries only the opaque marker; neither
        # the removed mark's text nor the event's cause reaches the model.
        evidence = json.loads(packet)["persona"]["relationship"]["evidence"]
        self.assertEqual(evidence, ["witnessed:evt_small"])
        self.assertNotIn(MARK_A, packet)


if __name__ == "__main__":
    unittest.main()

"""Direct unit tests for incidents.bridge: an incident reaches the adventure director only by rule."""

import unittest
from types import SimpleNamespace
from unittest import mock

from incidents import bridge
from incidents.possibilities import fact_id_for


def _lore(*possibility_ids):
    return SimpleNamespace(adventure_possibility_ids=tuple(possibility_ids))


def _record(**over):
    record = {"incident_id": "inc.one", "location_id": "tavern", "premise": "A purse was lost.", "details": {"people": {}}}
    record.update(over)
    return record


def _world(*npcs):
    return {"npcs": [{"id": npc_id, "location": "tavern"} for npc_id in npcs]}


class BindTests(unittest.TestCase):
    def test_nothing_binds_without_lore_record_or_possibility(self):
        world = _world("npc.a", "npc.b")
        with mock.patch.object(bridge.director, "refresh") as refresh:
            self.assertIsNone(bridge.bind(world, _record(), None))
            self.assertIsNone(bridge.bind(world, "junk", _lore()))
            self.assertIsNone(bridge.bind(world, _record(incident_id=5), _lore()))
            self.assertIsNone(bridge.bind(world, _record(), _lore()))
            self.assertIsNone(bridge.bind(world, _record(location_id=None), _lore(fact_id_for("inc.one"))))
            refresh.assert_not_called()

    def test_fewer_than_two_people_present_binds_nothing(self):
        with mock.patch.object(bridge.director, "refresh") as refresh:
            self.assertIsNone(bridge.bind(_world("npc.a"), _record(), _lore(fact_id_for("inc.one"))))
            refresh.assert_not_called()

    def test_promoted_people_come_first_then_people_present(self):
        record = _record(details={"people": {"p1": {"state": "promoted", "npc_id": "npc.promoted"}, "p2": {"state": "scene"}}})
        with mock.patch.object(bridge.director, "refresh", return_value="ROW") as refresh:
            result = bridge.bind(_world("npc.a", "npc.b"), record, _lore(fact_id_for("inc.one")), campaign_id="camp")
        self.assertEqual(result, "ROW")
        kwargs = refresh.call_args.kwargs
        self.assertEqual(kwargs["bindings"]["source_npc_id"], "npc.promoted")
        self.assertEqual(kwargs["bindings"]["target_npc_id"], "npc.a")
        self.assertEqual(kwargs["bindings"]["location_ids"], ["tavern"])
        self.assertEqual(kwargs["source_id"], "inc.one")
        self.assertEqual(kwargs["rumor"], "A purse was lost.")
        self.assertEqual(kwargs["campaign_id"], "camp")


class AftermathSeedTests(unittest.TestCase):
    def test_closed_structured_adventure_seeds_an_aftermath(self):
        self.assertEqual(
            bridge.aftermath_seed({"adventure_status": "FAILED", "quest_id": "q1"}),
            {"status": "FAILED", "source_event_id": "q1"},
        )
        self.assertEqual(
            bridge.aftermath_seed({"action": "adventure_completed", "source_id": "q2"}),
            {"status": "COMPLETED", "source_event_id": "q2"},
        )

    def test_open_or_malformed_results_seed_nothing(self):
        for result in (None, "x", {}, {"quest_status": "ACTIVE", "quest_id": "q"}, {"quest_status": "FAILED"},
                       {"quest_status": "FAILED", "quest_id": ""}):
            with self.subTest(result=result):
                self.assertIsNone(bridge.aftermath_seed(result))


if __name__ == "__main__":
    unittest.main()

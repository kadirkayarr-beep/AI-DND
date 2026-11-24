"""Direct unit tests for incidents.sublocations: a micro-location becomes one child of a verified place, never a city."""

import unittest

from incidents import sublocations


def _record(kind="cellar", label="Damp cellar", description="Barrels and dust.", **over):
    record = {
        "incident_id": "inc.one",
        "location_id": "tavern",
        "lifecycle": "ENGAGED",
        "details": {"subscene": {"kind": kind, "label": label, "description": description}},
    }
    record.update(over)
    return record


def _world():
    return {"locations": {"tavern": {"id": "tavern", "name": "Tavern"}}}


class PromoteTests(unittest.TestCase):
    def test_subscene_becomes_a_campaign_local_child_row(self):
        world = _world()
        row = sublocations.promote(world, _record())
        self.assertEqual(row["id"], "location_001")
        self.assertEqual(row["parent_location_id"], "tavern")
        self.assertEqual(row["exit_location_id"], "tavern")
        self.assertEqual(row["scene_kind"], "cellar")
        self.assertIn("campaign_local", row["tags"])
        self.assertIs(world["locations"]["location_001"], row)
        self.assertEqual(world["next_location_number"], 2)

    def test_promoting_twice_returns_the_same_row(self):
        world, record = _world(), _record()
        first = sublocations.promote(world, record)
        self.assertIs(sublocations.promote(world, record), first)
        self.assertEqual(len(world["locations"]), 2)

    def test_same_label_under_the_same_parent_is_reused(self):
        world = _world()
        first = sublocations.promote(world, _record())
        again = sublocations.promote(world, _record(incident_id="inc.two"))
        self.assertIs(first, again)

    def test_next_id_skips_taken_numbers(self):
        world = _world()
        world["locations"]["location_001"] = {"id": "location_001"}
        self.assertEqual(sublocations.promote(world, _record())["id"], "location_002")

    def test_refusals_carry_their_reason(self):
        def refused(record, world, reason):
            with self.assertRaises(sublocations.PlaceError) as caught:
                sublocations.promote(world, record)
            self.assertEqual(str(caught.exception), reason)

        no_subscene = _record()
        no_subscene["details"]["subscene"] = None
        refused(no_subscene, _world(), "no_subscene")
        refused(_record(kind="district"), _world(), "geography")
        refused(_record(label="The old castle"), _world(), "geography")
        refused(_record(description="A temple annex."), _world(), "geography")
        refused(_record(location_id="void"), _world(), "unknown_parent")
        full = _world()
        full["locations"].update({f"l{n}": {} for n in range(sublocations.MAX_LOCATIONS)})
        refused(_record(), full, "location_cap")
        stale = _record()
        stale["details"]["subscene"]["promoted_location_id"] = "gone"
        refused(stale, _world(), "missing_location")


class ApplyActionTests(unittest.TestCase):
    def test_only_a_successful_enter_action_promotes(self):
        world = _world()
        world["incidents"] = {"inc.one": _record()}
        action = {"success": True, "enter_subscene": True, "incident_id": "inc.one"}
        self.assertEqual(sublocations.apply_action(world, action)["id"], "location_001")

    def test_other_actions_promote_nothing(self):
        world = _world()
        world["incidents"] = {"inc.one": _record()}
        for action in (
            None,
            {"success": False, "enter_subscene": True, "incident_id": "inc.one"},
            {"success": True, "incident_id": "inc.one"},
            {"success": True, "enter_subscene": True, "incident_id": "missing"},
        ):
            with self.subTest(action=action):
                self.assertIsNone(sublocations.apply_action(world, action))
        self.assertEqual(len(world["locations"]), 1)

    def test_refused_promotion_returns_none_instead_of_raising(self):
        world = _world()
        world["incidents"] = {"inc.one": _record(kind="district")}
        action = {"success": True, "enter_subscene": True, "incident_id": "inc.one"}
        self.assertIsNone(sublocations.apply_action(world, action))


if __name__ == "__main__":
    unittest.main()

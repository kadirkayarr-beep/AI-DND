"""Direct unit tests for incidents.drift: the engine records a mismatch and never rewrites canon."""

import unittest
from unittest import mock

from incidents import drift, profiles


class FlagTests(unittest.TestCase):
    def test_flag_appends_an_audit_entry_and_trims_the_reason(self):
        world = {}
        entry = drift.flag(world, {"incident_id": "inc.a"}, "x" * 400)
        self.assertEqual(entry["incident_id"], "inc.a")
        self.assertEqual(len(entry["reason"]), 160)
        self.assertEqual(world["lore_drift_flags"], [entry])

    def test_empty_reason_records_nothing(self):
        world = {}
        self.assertIsNone(drift.flag(world, {}, ""))
        self.assertIsNone(drift.flag(world, {}, None))
        self.assertNotIn("lore_drift_flags", world)

    def test_only_the_last_32_flags_are_kept(self):
        world = {}
        for index in range(40):
            drift.flag(world, {"incident_id": f"inc.{index}"}, "r")
        self.assertEqual(len(world["lore_drift_flags"]), 32)
        self.assertEqual(world["lore_drift_flags"][0]["incident_id"], "inc.8")

    def test_corrupt_flag_list_is_replaced(self):
        world = {"lore_drift_flags": "oops"}
        drift.flag(world, None, "r")
        self.assertEqual(world["lore_drift_flags"], [{"incident_id": None, "reason": "r"}])


class ProfileConflictTests(unittest.TestCase):
    def test_claiming_the_active_profile_is_fine(self):
        world = {}
        with mock.patch.object(profiles, "resolve", return_value={"profile_id": "p.tavern"}):
            self.assertIsNone(drift.profile_conflict(world, "tavern", "p.tavern"))
        self.assertNotIn("lore_drift_flags", world)

    def test_claiming_another_profile_is_flagged(self):
        world = {}
        with mock.patch.object(profiles, "resolve", return_value={"profile_id": "p.tavern"}):
            entry = drift.profile_conflict(world, "tavern", "p.city")
        self.assertEqual(entry["reason"], "profile_conflict")

    def test_no_active_profile_is_flagged(self):
        world = {}
        with mock.patch.object(profiles, "resolve", return_value=None):
            self.assertEqual(drift.profile_conflict(world, "tavern", "p.x")["reason"], "profile_conflict")


if __name__ == "__main__":
    unittest.main()

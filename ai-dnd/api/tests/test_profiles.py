"""Direct unit tests for incidents.profiles: a place without a reviewed profile generates nothing."""

import unittest
from unittest import mock

from incidents import profiles


def _world(location, **record):
    return {"locations": {location: record}}


class LoadTests(unittest.TestCase):
    def test_generic_profile_loads_as_a_copy_with_protected_names(self):
        first = profiles.load("generic.tavern")
        self.assertEqual(first["profile_id"], "generic.tavern")
        self.assertIn("Dagult Neverember", first["protected_names"])
        first["silence_rate"] = 0.0
        self.assertEqual(profiles.PROFILES["generic.tavern"]["silence_rate"], 0.7)

    def test_unknown_and_disabled_profiles_load_nothing(self):
        self.assertIsNone(profiles.load("nope"))
        self.assertIsNone(profiles.load("waterdeep.v1"))
        self.assertIsNone(profiles.load("baldurs_gate.v1"))

    def test_review_required_profile_needs_a_verified_pack(self):
        with mock.patch.object(profiles, "_pack_coverage", return_value="INCOMPLETE"):
            self.assertIsNone(profiles.load("neverwinter.v1"))
        with mock.patch.object(profiles, "_pack_coverage", return_value="VERIFIED_PARTIAL"):
            loaded = profiles.load("neverwinter.v1")
        self.assertEqual(loaded["review_status"], "VERIFIED_PARTIAL")

    def test_profile_with_an_unknown_reward_class_is_refused(self):
        bad = dict(profiles.PROFILES["generic.tavern"], reward_weights=(("dragon_hoard", 1),))
        with mock.patch.dict(profiles.PROFILES, {"generic.tavern": bad}):
            self.assertIsNone(profiles.load("generic.tavern"))

    def test_every_shipped_profile_uses_known_reward_classes(self):
        for profile_id in profiles.PROFILES:
            with self.subTest(profile=profile_id), mock.patch.object(profiles, "_pack_coverage", return_value="VERIFIED"):
                loaded = profiles.load(profile_id)
                if loaded is not None:
                    self.assertTrue(loaded["silence_rate"] > 0)


class GenerationFlagTests(unittest.TestCase):
    def test_live_generation_is_off_until_the_campaign_flag_is_true(self):
        self.assertFalse(profiles.generation_enabled({}))
        self.assertFalse(profiles.generation_enabled({"flags": {profiles.LIVE_FLAG: 1}}))
        self.assertFalse(profiles.generation_enabled({"flags": "x"}))
        self.assertFalse(profiles.generation_enabled(None))
        self.assertTrue(profiles.generation_enabled({"flags": {profiles.LIVE_FLAG: True}}))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(profiles, "_pack_coverage", return_value="INCOMPLETE")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _id(self, world, location):
        profile = profiles.resolve(world, location)
        return None if profile is None else profile["profile_id"]

    def test_unreviewed_cities_generate_nothing(self):
        for location in ("waterdeep", "fr:city:waterdeep", "baldurs_gate", "fr:city:baldurs_gate"):
            with self.subTest(location=location):
                self.assertIsNone(self._id(_world(location), location))

    def test_tavern_falls_back_to_the_generic_tavern_without_a_verified_pack(self):
        self.assertEqual(self._id(_world("tavern"), "tavern"), "generic.tavern")
        self.assertEqual(self._id(_world("back", scene_kind="inn"), "back"), "generic.tavern")
        self.assertEqual(self._id(_world("back", type="tavern"), "back"), "generic.tavern")

    def test_neverwinter_without_a_verified_pack_has_no_profile(self):
        self.assertIsNone(self._id(_world("neverwinter"), "neverwinter"))
        self.assertIsNone(self._id(_world("gate", parent_location_id="neverwinter"), "gate"))
        self.assertIsNone(self._id(_world("gate", settlement_id="fr:city:neverwinter"), "gate"))

    def test_wilderness_road_and_camp_have_their_own_profiles(self):
        self.assertEqual(self._id(_world("forest"), "forest"), "generic.wilderness")
        self.assertEqual(self._id(_world("x", type="wilderness"), "x"), "generic.wilderness")
        self.assertEqual(self._id(_world("x", scene_kind="road"), "x"), "generic.road")
        self.assertEqual(self._id(_world("x", type="road"), "x"), "generic.road")
        self.assertEqual(self._id(_world("x", scene_kind="camp"), "x"), "generic.camp")

    def test_unknown_place_has_no_profile(self):
        self.assertIsNone(self._id(_world("library"), "library"))
        self.assertIsNone(self._id({}, "nowhere"))
        self.assertIsNone(self._id({"locations": {"x": "junk"}}, "x"))


if __name__ == "__main__":
    unittest.main()

"""An unknown person is told apart by something visible, not by a shared stock label."""

from __future__ import annotations

import unittest

import game
import living_world


def person(session, name, role, location="forest"):
    return session.create_npc_from_ai({"name": name, "role": role, "location": location})


class VisibleLabelTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=1729)
        self.world = self.session.world_state
        self.world["npcs"] = []
        self.world["location"] = "forest"

    def test_two_strangers_read_differently_and_keep_their_label(self):
        first, second = person(self.session, "Oren", "Kent sakini"), person(self.session, "Sefa", "Yolcu")
        one, two = living_world.public_npc_name(first), living_world.public_npc_name(second)
        self.assertNotEqual(one, two)
        for label in (one, two):
            self.assertNotIn("Yakındaki kişi", label)
            self.assertNotIn("Yolcu", label)
            self.assertNotIn("sakini", label)
        self.assertEqual(one, living_world.public_npc_name(person(self.session, "Oren", "Kent sakini")))

    def test_a_save_without_the_stored_trait_still_gets_a_stable_visible_label(self):
        old = {"id": "npc_old", "name": "Dara", "role": "Druid", "name_known_to_player": False,
               "role_known_to_player": False}
        label = living_world.public_npc_name(old)
        self.assertNotEqual(label, "Yakındaki kişi")
        self.assertNotIn("Druid", label)
        self.assertEqual(label, living_world.public_npc_name(dict(old)))

    def test_a_plainly_visible_role_keeps_its_label_and_two_of_them_differ(self):
        one, two = person(self.session, "Cael", "Muhafız"), person(self.session, "Tor", "Muhafız")
        self.assertEqual(living_world.public_npc_name(one), "Bir muhafız")
        self.assertNotEqual(living_world.public_npc_name(two), "Bir muhafız")
        self.assertIn("muhafız", living_world.public_npc_name(two))

    def test_scene_list_uses_the_same_labels(self):
        first, second = person(self.session, "Oren", "Kent sakini"), person(self.session, "Tor", "Muhafız")
        listed = living_world.public_scene_people([first, second])
        label = living_world.public_npc_name(first)
        self.assertIn(label[:1].lower() + label[1:], listed)
        self.assertIn("bir muhafız", listed)
        self.assertNotIn("bir kişi", listed)

    def test_the_trait_can_be_used_to_address_the_person(self):
        first, second = person(self.session, "Oren", "Kent sakini"), person(self.session, "Sefa", "Yolcu")
        trait = living_world.npc_visible_trait(first)
        found = self.session.resolve_npc_reference(f"{trait} olanla konuşmak istiyorum")
        self.assertEqual(found["npc"]["id"], first["id"])

    def test_the_label_is_not_read_as_an_invented_person(self):
        first = person(self.session, "Oren", "Kent sakini")
        self.assertTrue(game._is_generic_speaker_label(living_world.public_npc_name(first)))


if __name__ == "__main__":
    unittest.main()

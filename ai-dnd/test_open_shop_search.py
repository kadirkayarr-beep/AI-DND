"""An open-shop search is not shop creation or permission to unlock a door."""
import copy
import json
import unittest
from unittest.mock import patch

import game
import grounded_action as grounded


class OpenShopSearchTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=3)
        self.world = self.session.world_state
        self.world.update(location="city", locations={"city": {
            "id": "city", "name": "Neverwinter", "type": "city",
        }}, doors=[], shops=[], npcs=[], features=[])
        self.world.pop("campaign_time", None)
        self.session.character["current_hp"] = 12
        self.token = game._ACTIVE_SESSION.set(self.session)
        self.addCleanup(game._ACTIVE_SESSION.reset, self.token)
        self.model = patch.object(game, "ask_dungeon_master", side_effect=AssertionError("model forbidden"))
        self.model.start()
        self.addCleanup(self.model.stop)

    def shop(self, identity, *, opened=False, locked=True, hidden=False):
        self.world["locations"][identity] = {
            "id": identity, "name": identity + " Dükkânı", "type": "building",
            "parent_location_id": "city", "scene_kind": "building",
            "place_kind": None, "generic_noun": "dukkan", "aliases": ["dükkân"],
            "hidden": hidden,
        }
        self.world["doors"].append({
            "id": "venue-door:" + identity, "name": identity + " Kapısı",
            "location": "city", "open": opened, "locked": locked, "broken": False,
        })

    def resolve(self, text):
        result = grounded.resolve_turn(self.session, text, allow_model=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["action_result"]["grounding"]["model_calls"], 0)
        return result["action_result"]["steps"][0]

    def test_open_adjectives_are_not_creation_commands(self):
        for text in ("Açık bir dükkân arıyorum.", "açılmış bşr dükkan arıyorum",
                     "açılmış bir dükkan arıyorum", "açık bir dükkan arıyorum"):
            with self.subTest(text=text):
                self.assertFalse(game._explicit_campaign_shop_request(text))

    def test_genuine_creation_commands_still_match(self):
        for text in ("Bir dükkan açıyorum", "Dükkan kuruyorum", "Create a shop", "Open a shop"):
            with self.subTest(text=text):
                self.assertTrue(game._explicit_campaign_shop_request(text))

    def test_unknown_open_shop_is_not_created(self):
        before = copy.deepcopy(self.world["locations"])
        step = self.resolve("Açık bir dükkân arıyorum.")
        self.assertFalse(step.get("found", True))
        self.assertEqual(self.world["locations"], before)
        self.assertEqual(self.world["doors"], [])

    def test_repeated_search_and_typo_do_not_create_or_unlock(self):
        self.shop("Cora")
        before = copy.deepcopy(self.world["doors"])
        for text in ("Açık bir dükkân arıyorum.", "açılmış bşr dükkan arıyorum",
                     "açılmış bir dükkan arıyorum", "açık bir dükkan arıyorum"):
            with self.subTest(text=text):
                self.assertFalse(self.resolve(text).get("found", True))
        self.assertEqual(self.world["doors"], before)
        self.assertEqual(len(self.world["locations"]), 2)
        self.assertEqual(self.world["shops"], [])
        self.assertEqual(self.world["npcs"], [])

    def test_selects_open_not_locked_shop(self):
        self.shop("Cora")
        self.shop("Mira", opened=True, locked=False)
        before = copy.deepcopy(self.world["doors"])
        step = self.resolve("Açık bir dükkân arıyorum.")
        self.assertEqual(step["target_id"], "Mira")
        self.assertEqual(self.world["doors"], before)
        self.assertEqual(self.world["location"], "city")

    def test_closed_unlocked_is_not_known_open(self):
        self.shop("Cora", locked=False)
        self.assertFalse(self.resolve("Açık bir dükkân arıyorum.").get("found", True))

    def test_hidden_open_shop_is_not_revealed(self):
        self.shop("Hidden", opened=True, locked=False, hidden=True)
        self.assertFalse(self.resolve("Açık bir dükkân arıyorum.").get("found", True))

    def test_undiscovered_door_is_not_used_as_open_evidence(self):
        self.shop("Cora", opened=True, locked=False)
        self.world["doors"][0]["discovered"] = False
        before = copy.deepcopy(self.world["doors"])
        self.assertFalse(self.resolve("Açık bir dükkân arıyorum.").get("found", True))
        self.assertEqual(self.world["doors"], before)

    def test_purpose_search_preserves_open_constraint(self):
        self.shop("Cora")
        self.assertFalse(self.resolve(
            "Açık bir dükkân aramak için tabelaları inceliyorum."
        ).get("found", True))

    def test_unknown_named_open_shop_is_not_substituted(self):
        self.shop("Cora", opened=True, locked=False)
        before = copy.deepcopy(self.world["locations"])
        for text in ("Açık Zümrüt Dükkânı arıyorum.", "açık zümrüt dükkanı arıyorum",
                     "Açık Zümrüt Dükkânı aramak için tabelaları inceliyorum."):
            with self.subTest(text=text):
                self.assertFalse(self.resolve(text).get("found", True))
        self.assertEqual(self.world["locations"], before)

    def test_known_named_open_shop_remains_findable(self):
        self.shop("Cora", opened=True, locked=False)
        self.assertEqual(self.resolve("Açık Cora Dükkânı arıyorum.")["target_id"], "Cora")

    def test_current_time_filler_preserves_generic_open_search(self):
        self.shop("Cora", opened=True, locked=False)
        self.assertEqual(self.resolve("Şu an açık bir dükkân arıyorum.")["target_id"], "Cora")

    def test_still_open_filler_preserves_generic_search(self):
        self.shop("Cora", opened=True, locked=False)
        self.assertEqual(self.resolve("Hâlâ açık bir dükkân arıyorum.")["target_id"], "Cora")

    def test_named_locked_shop_is_not_replaced_by_other(self):
        self.shop("Cora")
        self.shop("Mira", opened=True, locked=False)
        self.assertFalse(self.resolve("Açık Cora Dükkânı arıyorum.").get("found", True))

    def test_plain_named_search_still_reports_locked_place(self):
        self.shop("Cora")
        step = self.resolve("Cora Dükkânı arıyorum.")
        self.assertEqual(step["target_id"], "Cora")
        self.assertTrue(step["door_state"]["locked"])

    def test_generic_kind_lookup_recognizes_saved_shop(self):
        self.shop("Cora")
        run = grounded._Run(self.session, "dükkan arıyorum")
        self.assertEqual(grounded._places_of_kind(run, "city", "generic", noun="dukkan"), ["Cora"])

    def test_saved_world_round_trip_preserves_constraint_and_lock(self):
        self.shop("Cora")
        self.resolve("Açık bir dükkân arıyorum.")
        saved = json.loads(json.dumps(self.world))
        self.world.clear()
        self.world.update(saved)
        self.assertFalse(self.resolve("açılmış bşr dükkan arıyorum").get("found", True))
        self.assertTrue(self.world["doors"][0]["locked"])
        self.assertEqual(self.world["shops"], [])

    def test_broken_or_unknown_door_does_not_claim_open_business(self):
        self.shop("Cora", opened=True, locked=False)
        self.world["doors"][0]["broken"] = True
        self.assertFalse(self.resolve("Açık bir dükkân arıyorum.").get("found", True))
        self.world["doors"].clear()
        self.assertFalse(self.resolve("Açık bir dükkân arıyorum.").get("found", True))

    def test_other_open_shop_excludes_current_front_door(self):
        self.shop("Cora", opened=True, locked=False)
        grounded.note_near(self.world, "venue-door:Cora")
        self.assertFalse(self.resolve("Başka açık bir dükkân arıyorum.").get("found", True))

    def test_complete_turn_does_not_fall_through_to_shop_creation(self):
        self.shop("Cora")
        with patch.object(game, "ask_dungeon_master", side_effect=AssertionError("model forbidden")) as model:
            for text in ("Açık bir dükkân arıyorum.", "açılmış bşr dükkan arıyorum"):
                result = self.session.run_player_turn(text)
                self.assertEqual(result["action_result"]["action"], "grounded_action")
                self.assertFalse(result["action_result"]["steps"][0]["found"])
            model.assert_not_called()
        self.assertEqual(self.world["shops"], [])
        self.assertEqual(self.world["npcs"], [])


if __name__ == "__main__":
    unittest.main()

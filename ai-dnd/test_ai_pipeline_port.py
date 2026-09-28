"""Offline checks for the imported V10 intent, query and narration behavior."""
import copy
import unittest

import game


class PipelinePortTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=8)
        self.session.world_state["location"] = "tavern"
        self.npc = {
            "id": "npc_001", "name": "Gromm", "role": "Barmen",
            "location": "tavern", "personality": "", "appearance": "",
            "relationship": "neutral", "knowledge": [], "memory": [],
        }
        self.session.world_state["npcs"] = [self.npc]

    def test_queries_do_not_travel_even_when_a_place_is_mentioned(self):
        for phrase, expected in (
            ("Buranın adı ne?", "location"),
            ("Tavernanın adı ne?", "location"),
            ("Tavernada kim var?", "presence"),
            ("Burada kimler var?", "presence"),
        ):
            with self.subTest(phrase=phrase):
                normalized = self.session.normalize_intent({"intent": "travel"}, phrase)
                self.assertEqual(normalized["intent"], "query")
                self.assertEqual(normalized["query_type"], expected)
                self.assertEqual(self.session.validate_intent(normalized, phrase)["intent"], "query")
                self.assertFalse(self.session._has_travel_language(phrase))

    def test_known_name_matches_suffix_but_not_similar_names(self):
        self.assertTrue(self.session._entity_reference_in_text("Gromm", "Gromm'la konuşuyorum"))
        self.assertFalse(self.session._entity_reference_in_text("Gromm", "Grommish'le konuşuyorum"))
        self.assertEqual(self.session.resolve_npc_reference("Gromm'la konuşuyorum")["status"], "found")

    def test_observation_is_not_a_skill_check_or_world_mutation(self):
        before = copy.deepcopy(self.session.world_state)
        phrase = "Etrafıma bakıyorum"
        intent = self.session.validate_intent(
            self.session.normalize_intent({"intent": "unknown"}, phrase), phrase
        )
        self.assertEqual(intent["intent"], "explore")
        self.assertEqual(intent["explore_type"], "observe")
        result = self.session.execute_intent(intent, phrase)
        self.assertEqual(result["action"], "explore")
        self.assertNotIn("dice", result)
        self.assertEqual(before, self.session.world_state)

    def test_narrator_does_not_invent_player_action(self):
        result = {"action": "travel", "status": "completed", "success": True}
        self.assertTrue(self.session._narration_is_unsafe(
            "Kılıcını savurursun.", "Tavernaya gidiyorum", action_result=result
        ))
        self.assertTrue(self.session._narration_is_unsafe(
            "Eğer tavernaya girersen kapı açılır.", "Tavernaya gidiyorum", action_result=result
        ))

    def test_narrator_accepts_only_committed_arrival(self):
        result = {"action": "travel", "status": "completed", "success": True}
        self.assertFalse(self.session._narration_is_unsafe(
            f"{self.session.character['name']} tavernaya ulaşır.",
            "Tavernaya gidiyorum", action_result=result
        ))
        self.assertTrue(self.session._narration_is_unsafe(
            f"{self.session.character['name']} kılıcını savurur.",
            "Tavernaya gidiyorum", action_result=result
        ))

    def test_npc_speech_not_confused_with_player_action(self):
        result = {"action": "dialogue", "status": "resolved"}
        self.assertFalse(self.session._narration_is_unsafe(
            'Gromm, "Burada ne arıyorsun?" diye sorar.',
            "Gromm'a selam veriyorum", npc_target=self.npc, action_result=result
        ))

    def test_pipe_does_not_let_model_move_player_on_location_question(self):
        before = copy.deepcopy(self.session.world_state)
        phrase = "Tavernanın adı ne?"
        bogus = {"intent": "travel", "target": {"type": "location", "reference": "forest"},
                 "completion": "completed"}
        validated = self.session.validate_intent(self.session.normalize_intent(bogus, phrase), phrase)
        result = self.session.execute_intent(validated, phrase, self.npc)
        self.assertEqual(result["action"], "query")
        self.assertEqual(result["query_type"], "location")
        self.assertEqual(self.session.world_state, before)


if __name__ == "__main__":
    unittest.main()
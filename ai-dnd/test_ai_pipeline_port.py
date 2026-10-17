"""Offline checks for the imported V10 intent, query and narration behavior."""
import copy
import json
import unittest
from unittest.mock import patch

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

    def test_travel_override_requires_unquoted_positive_movement_verbs(self):
        cases = (
            (
                "Han binasının girişindeki taş işçiliğini inceliyorum.",
                {"intent": "investigation", "target": {"type": "location", "reference": "Han"}},
                "investigation",
                False,
            ),
            (
                "İçeri girmiyorum.",
                {"intent": "travel", "target": {"type": "location", "reference": "Han"}},
                "unknown",
                False,
            ),
            (
                "“İçeri giriyorum.” diye alıntı yapıyorum.",
                {"intent": "travel", "target": {"type": "location", "reference": "Han"}},
                "unknown",
                False,
            ),
            (
                "İçeri giriyorum.",
                {"intent": "travel", "target": {"type": "location", "reference": "Han"}},
                "travel",
                True,
            ),
            (
                "Neverwinter'a gidiyorum.",
                {"intent": "travel", "target": {"type": "location", "reference": "Neverwinter"}},
                "travel",
                True,
            ),
        )
        for phrase, raw_intent, expected, has_travel in cases:
            with self.subTest(phrase=phrase):
                normalized = self.session.normalize_intent(raw_intent, phrase)
                self.assertEqual(normalized["intent"], expected)
                self.assertEqual(self.session._has_travel_language(phrase), has_travel)
                if raw_intent["intent"] == "travel" and not has_travel:
                    self.assertEqual(normalized["target"], {"type": "none", "reference": ""})

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

    def test_four_missing_skill_routes_use_the_canonical_check(self):
        cases = (
            ("Onu bana güvenmeye ikna etmeye çalışıyorum.", "persuasion", "Persuasion", "charisma"),
            ("Gromm'a yalan söyleyerek kendimi nöbetçi olarak tanıtıyorum.", "deception", "Deception", "charisma"),
            ("İp üzerinde dengede yürüyorum.", "acrobatics", "Acrobatics", "dexterity"),
            ("Ormandaki izleri takip ediyorum.", "survival", "Survival", "wisdom"),
            ("Ormandaki hayvanın taze izlerini takip ederek hangi yöne gittiğini bulmaya çalışıyorum.", "survival", "Survival", "wisdom"),
        )
        self.session.character["modifiers"].update({
            "charisma": 2, "dexterity": 2, "wisdom": 2,
        })
        self.session.character["proficiency_bonus"] = 2

        for phrase, intent_name, skill, ability in cases:
            with self.subTest(skill=skill, proficiency=True):
                self.session.character["proficient_skills"] = [skill]
                intent = self.session.validate_intent(
                    self.session.normalize_intent({"intent": "unknown"}, phrase), phrase
                )
                self.assertEqual(intent["intent"], intent_name)
                with patch("game.roll_d20", return_value=12) as roll:
                    result = self.session.execute_intent(intent, phrase)
                roll.assert_called_once_with()
                self.assertEqual(result["action"], "skill_check")
                self.assertEqual(result["skill"], skill)
                self.assertEqual(result["ability"], ability)
                self.assertEqual(result["modifier"], 2)
                self.assertEqual(result["proficiency_bonus"], 2)
                self.assertEqual(result["total"], 16)
                self.assertEqual(result["dc"], game.DIFFICULTY_DC["medium"])
                self.assertEqual(result["outcome"], "success")

            with self.subTest(skill=skill, proficiency=False):
                self.session.character["proficient_skills"] = []
                intent = self.session.validate_intent(
                    self.session.normalize_intent({"intent": "unknown"}, phrase), phrase
                )
                with patch("game.roll_d20", return_value=12) as roll:
                    result = self.session.execute_intent(intent, phrase)
                roll.assert_called_once_with()
                self.assertEqual(result["skill"], skill)
                self.assertEqual(result["ability"], ability)
                self.assertEqual(result["proficiency_bonus"], 0)
                self.assertEqual(result["total"], 14)
                self.assertEqual(result["outcome"], "failure")

    def test_semantic_skill_intents_cannot_author_mechanics(self):
        cases = (
            ("Muhafıza makul bir teklif sunarak geçiş izni istiyorum.", "persuasion", "Persuasion", "charisma"),
            ("Muhafıza kendimi saray habercisi olarak tanıtıyorum.", "deception", "Deception", "charisma"),
            ("Dar taş korkuluğun üzerinden zarifçe geçiyorum.", "acrobatics", "Acrobatics", "dexterity"),
            ("Kırık dalları okuyarak ormandaki rotayı kestiriyorum.", "survival", "Survival", "wisdom"),
        )
        self.session.character["modifiers"].update({
            "charisma": 0, "dexterity": 0, "wisdom": 0,
        })
        self.session.character["proficient_skills"] = []

        for phrase, intent_name, skill, ability in cases:
            with self.subTest(skill=skill):
                semantic_result = {
                    "intent": intent_name,
                    "skill": "Perception",
                    "ability": "wisdom",
                    "dc": 1,
                    "dice": 20,
                    "outcome": "success",
                }
                intent = self.session.normalize_intent(semantic_result, phrase)
                self.assertEqual(intent["intent"], intent_name)
                for forbidden in ("skill", "ability", "dc", "dice", "outcome"):
                    self.assertNotIn(forbidden, intent)
                intent = self.session.validate_intent(intent, phrase)
                with patch("game.roll_d20", return_value=12):
                    result = self.session.execute_intent(intent, phrase)
                self.assertEqual(result["skill"], skill)
                self.assertEqual(result["ability"], ability)
                self.assertEqual(result["dice"], 12)
                self.assertEqual(result["dc"], game.DIFFICULTY_DC["medium"])
                self.assertEqual(result["outcome"], "failure")

    def test_invalid_or_ordinary_skill_intent_does_not_consume_rng(self):
        for phrase, raw_intent, expected_intent in (
            ("Gromm'a merhaba diyorum.", {"intent": "persuasion"}, "dialogue"),
            ("Sessizce bekliyorum.", {"intent": ["persuasion"], "skill": "Persuasion"}, "unknown"),
        ):
            with self.subTest(phrase=phrase):
                before_rng = self.session.rng.getstate()
                intent = self.session.validate_intent(
                    self.session.normalize_intent(raw_intent, phrase), phrase
                )
                self.assertEqual(intent["intent"], expected_intent)
                result = self.session.execute_intent(intent, phrase)
                self.assertNotIn("dice", result)
                self.assertEqual(self.session.rng.getstate(), before_rng)

    def test_skill_roll_isolated_to_the_owning_session(self):
        other_session = game.create_session(seed=99)
        other_rng = other_session.rng.getstate()
        own_rng = self.session.rng.getstate()
        phrase = "Onu bana güvenmeye ikna etmeye çalışıyorum."
        intent = self.session.validate_intent(
            self.session.normalize_intent({"intent": "unknown"}, phrase), phrase
        )
        with patch("game.roll_d20", wraps=game.roll_d20) as roll:
            result = self.session.execute_intent(intent, phrase)
        roll.assert_called_once_with()
        self.assertEqual(result["skill"], "Persuasion")
        self.assertNotEqual(self.session.rng.getstate(), own_rng)
        self.assertEqual(other_session.rng.getstate(), other_rng)

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

    def test_narration_prompt_uses_scene_adaptive_length_without_changing_schema(self):
        captured = {}

        def fake_chat(**kwargs):
            captured.update(kwargs)
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "world_updates": {
                                "create_locations": [],
                                "create_npcs": [],
                                "update_npcs": [],
                                "create_features": [],
                                "events": [],
                            },
                            "narration": "Şu an Taverna'dasın.",
                            "lore_claims": [],
                        },
                        ensure_ascii=False,
                    )
                }
            }

        with patch("game.ollama.chat", side_effect=fake_chat):
            result = self.session.ask_dungeon_master(
                messages=self.session.messages,
                player_input="Neredeyim?",
                action_result={"action": "query", "query_type": "location"},
                return_details=True,
            )

        system_text = captured["messages"][0]["content"]
        user_text = captured["messages"][1]["content"]
        self.assertTrue(result["valid_response"])
        self.assertIn("doğrudan sorulara özlü yanıt", system_text)
        self.assertIn("2–5 paragraf", system_text)
        self.assertIn("2–5 paragraf", user_text)
        self.assertIn("sıradan turları uzatma", system_text)
        self.assertNotIn("Narration en fazla iki kısa cümle olsun", user_text)
        self.assertNotIn("Kısa ve doğal Türkçe anlat.", system_text)
        self.assertEqual(captured["format"], game.DM_RESPONSE_SCHEMA)
        self.assertEqual(
            set(game.DM_RESPONSE_SCHEMA["properties"]),
            {"world_updates", "narration", "lore_claims"},
        )
        self.assertIn("create_shops", game.WORLD_UPDATE_SCHEMA["properties"])
        self.assertNotIn("create_shops", game.WORLD_UPDATE_SCHEMA["required"])
        self.assertEqual(captured["options"]["num_predict"], 700)

    def test_multi_paragraph_temporary_texture_stays_noncanonical_and_deduplicated(self):
        narration = (
            "Lambaların sarı ışığı, masa kenarlarında ince gölgeler bırakır. "
            "Uzakta bir kupa tezgâha konurken kısa bir tını duyulur.\n\n"
            "Odun dumanı hafifçe havaya karışır. Alçak konuşmalar, odanın içinde "
            "kesintisiz bir uğultu oluşturur."
        )
        action_result = {
            "action": "explore",
            "status": "resolved",
            "explore_type": "observe",
        }
        before = copy.deepcopy(self.session.world_state)

        first = self.session.finalize_narration(
            narration, "Etrafıma bakıyorum", action_result=action_result
        )
        second = self.session.finalize_narration(
            narration, "Etrafıma bakıyorum", action_result=action_result
        )

        self.assertEqual(first, game.clean_dm_response(narration))
        self.assertEqual(first.count("\n"), 1)
        self.assertNotEqual(second, narration)
        self.assertEqual(self.session.world_state, before)

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
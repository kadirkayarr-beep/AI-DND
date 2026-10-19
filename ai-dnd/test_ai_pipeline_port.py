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

    def test_negated_speech_act_does_not_open_dialogue(self):
        for phrase in ("Gromm'la konuşmuyorum.", "Gromm'a soru sormayacağım."):
            with self.subTest(phrase=phrase):
                self.assertFalse(self.session.is_npc_dialogue_input(phrase))

    def test_intent_parser_gets_bounded_public_scene_candidates_for_descriptive_address(self):
        self.npc.update({
            "appearance": "Kırmızı atkılı, kısa boylu cüce; tezgâhın arkasında duruyor.",
            "personal_profile": {"private_secret": "GİZLİ_SIR_721"},
        })
        hidden = {
            "id": "hidden_001", "name": "Veil", "role": "spy",
            "location": "tavern", "appearance": "Görünmez gölge",
            "name_known_to_player": False, "role_known_to_player": False,
            "hidden": True, "personal_profile": {"password": "HIDDEN_PASS_41"},
        }
        self.session.world_state["npcs"].append(hidden)
        captured = {}

        def fake_chat(**kwargs):
            captured.update(kwargs)
            return {"message": {"content": json.dumps({
                "intent": "dialogue", "action": "ask", "target": {
                    "type": "npc", "reference": "kırmızı atkılı kişi",
                }, "completion": "unclear", "confidence": 1.0,
            }, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=fake_chat):
            self.session.parse_player_intent(
                "Kırmızı atkılı kısa cüceye söylüyorum, limanı soracağım."
            )

        schema = captured["format"]
        target = schema["properties"]["target"]["properties"]
        self.assertEqual(target["npc_id"]["enum"], ["npc_001"])
        prompt = captured["messages"][-1]["content"]
        self.assertIn("Kırmızı atkılı", prompt)
        self.assertNotIn("GİZLİ_SIR_721", prompt)
        self.assertNotIn("HIDDEN_PASS_41", prompt)
        self.assertNotIn("Veil", prompt)

    def test_scene_candidate_resolution_requires_an_exact_player_quote(self):
        self.npc["appearance"] = "Kırmızı atkılı, kısa boylu cüce."
        raw = {"target": {
            "npc_id": "npc_001",
            "evidence_quote": "kısa boylu cüceye",
        }}
        self.assertEqual(
            self.session._validated_scene_npc_id(
                raw, "Kısa boylu cüceye limanın durumunu soruyorum."
            )["id"],
            "npc_001",
        )
        self.assertIsNone(self.session._validated_scene_npc_id(
            raw, "Limanın durumu hakkında konuşmak istiyorum."
        ))
        forged = {"target": {
            "npc_id": "hidden_001",
            "evidence_quote": "kısa boylu cüceye",
        }}
        self.assertIsNone(self.session._validated_scene_npc_id(
            forged, "Kısa boylu cüceye limanı soruyorum."
        ))

    def test_local_person_proposal_is_bounded_and_not_world_state(self):
        before = copy.deepcopy(self.session.world_state)
        proposal = {
            "local_person_proposal": {
                "name": "Neris",
                "role": "kıyı balıkçısı",
                "appearance": "Yosun lekeli pelerinli yaşlı biri",
                "reason": "Liman söylentileri hakkında konuşabilir.",
            }
        }
        self.assertEqual(
            self.session._validated_local_person_proposal(proposal),
            proposal["local_person_proposal"],
        )
        self.assertIsNone(self.session._validated_local_person_proposal({
            "local_person_proposal": {
                "name": "Neris",
                "role": "x" * 61, "appearance": "kişi", "reason": "öneri",
            }
        }))
        self.assertEqual(before, self.session.world_state)

    def test_descriptive_address_routes_only_to_a_present_scene_person(self):
        self.npc["appearance"] = "Kırmızı atkılı, kısa boylu cüce."

        def fake_chat(**kwargs):
            packet = {
                "intent": "dialogue",
                "action": "dialogue",
                "target": {
                    "type": "npc",
                    "reference": "kırmızı atkılı kişi",
                    "npc_id": "npc_001",
                    "evidence_quote": "kırmızı atkılı kişiye",
                },
                "completion": "unclear",
                "confidence": 1.0,
            }
            if "narration" in kwargs["format"]["properties"]:
                packet["narration"] = "Gromm selamını alıyor."
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=fake_chat) as model:
            result = self.session.run_player_turn(
                "Kırmızı atkılı kişiye selam veriyorum.", interaction_mode="do"
            )
        self.assertEqual(result["action_result"]["npc_id"], "npc_001")
        self.assertLessEqual(model.call_count, 2)
        self.assertEqual([npc["id"] for npc in self.session.world_state["npcs"]], ["npc_001"])

    def test_absent_local_person_is_suggested_without_becoming_canonical(self):
        before = copy.deepcopy(self.session.world_state)

        def fake_chat(**kwargs):
            packet = {
                "intent": "dialogue", "action": "dialogue",
                "target": {"type": "none", "reference": ""},
                "completion": "unclear", "confidence": 1.0,
            }
            if "local_person_proposal" in kwargs["format"]["properties"]:
                packet["local_person_proposal"] = {
                    "name": "Neris",
                    "role": "kıyı balıkçısı",
                    "appearance": "Yosun lekeli pelerin giyen yaşlı biri",
                    "reason": "Liman söylentilerini duymuş olabilir.",
                }
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        with patch("game.ollama.chat", side_effect=fake_chat):
            result = self.session.run_player_turn(
                "Sahnede olmayan bir balıkçıya liman söylentilerini sormak istiyorum.",
                interaction_mode="say",
            )
        self.assertEqual(result["action_result"]["status"], "created_local_person")
        self.assertEqual(result["action_result"]["npc_id"], self.session.world_state["npcs"][-1]["id"])
        self.assertEqual(len(self.session.world_state["npcs"]), 2)
        self.assertEqual(self.session.world_state["npcs"][-1]["name"], "Neris")
        self.assertEqual(self.session.world_state["locations"], before["locations"])
        self.assertEqual(self.session.world_state["npcs"][-1]["knowledge"], [])
        self.assertEqual(self.session.world_state["npcs"][-1]["backstory"], "")

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
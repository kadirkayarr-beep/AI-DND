"""F04 scoped dialogue quality: greeting relevance and player agency.

Only synthetic providers; no live model, database, or browser required.
"""
import copy
import json
import unittest
from unittest.mock import patch

import game
from api.tests.test_stage10a_gameplay_repairs import city_session, place_npc

RECORDED_LIVE_FOLLOWUP = (
    "Bir dükkâncı, sakin ve dikkatli bir şekilde başını hafifçe sallar. "
    "'Bu işlerinizi kendi gözlerinizle görmedim,' diye mırıldanır. "
    "Arven, küçük bir selamla karşılık verir; bu da dükkânın sahibinin "
    "gülümsemesine neden olur. Sokağın köşesindeki çeşmenin öğleden "
    "sonra kalabalıklaşacağına dair bir söz de ederken, dükkâncının "
    "günün geri kalanında işleri bitirmeye çalışmasıyla ilgili bir plan "
    "ortaya çıkar. Bu kısa etkileşim, Neverwinter'daki yerel yaşamın "
    "sade ve düzenli ritmine uygun bir örnektir."
)


class F04GreetingAndAgencyTests(unittest.TestCase):
    def setUp(self):
        self.session = city_session()
        self.session.character["name"] = "Arven"
        place_npc(self.session, "npc_001", "Neris")
        self.npc = self.session.world_state["npcs"][-1]
        self.npc["name"] = "Neris"
        self.npc["role"] = "Shopkeeper"
        self.npc["knowledge"] = []
        self.npc["relationship"] = "neutral"

    def turn(self, user_message, narration, *, lore_claims=None):
        narrator_payload = {
            "world_updates": {},
            "narration": narration,
            "lore_claims": [] if lore_claims is None else lore_claims,
        }
        phases = []

        def phase_aware_chat(*args, **kwargs):
            properties = kwargs.get("format", {}).get("properties", {})
            if "intent" in properties:
                phases.append("scene_intent")
                packet = {
                    "intent": "dialogue",
                    "action": "dialogue",
                    "target": {"type": "none", "reference": ""},
                    "completion": "unclear",
                    "confidence": 1.0,
                    "interaction": {"operation": "none", "quote": user_message},
                }
            elif "narration" in properties:
                phases.append("narrator")
                packet = narrator_payload
            else:
                raise AssertionError(
                    f"Unexpected model phase schema: {sorted(properties)}"
                )
            return {
                "message": {
                    "content": json.dumps(packet, ensure_ascii=False)
                }
            }

        before = copy.deepcopy({
            "inventory": self.session.world_state.get("inventory"),
            "currency": self.session.world_state.get("currency"),
            "quests": self.session.world_state.get("quests"),
            "relationships": self.session.world_state.get("relationships"),
        })
        with patch("game.ollama.chat", side_effect=phase_aware_chat) as provider:
            result = self.session.run_player_turn(user_message, interaction_mode="say")
        self.assertEqual(phases, ["scene_intent", "narrator"])
        self.assertEqual(provider.call_count, 2)
        telemetry = result["_engine_event_evidence"]["telemetry"]
        self.assertEqual(telemetry["intent_model_calls"], 1)
        self.assertEqual(telemetry["narration_model_calls"], 1)
        self.assertEqual(telemetry["total_model_calls"], 2)
        self.assertEqual(
            {key: self.session.world_state.get(key) for key in before}, before
        )
        return result, telemetry

    def test_recorded_live_greeting_cannot_invent_player_reply_or_meta_summary(self):
        result, telemetry = self.turn("Merhaba.", RECORDED_LIVE_FOLLOWUP)
        self.assertNotEqual(telemetry["narration_source"], "qwen", telemetry)
        self.assertNotEqual(telemetry["narration_validation_result"], "accepted")
        self.assertIn(telemetry["fallback_reason"], (
            "PLAYER_NAME_IN_NARRATION", "INVENTED_PLAYER_ACTION", "UNRELATED_GREETING_REPLY", "META_NARRATOR_COMMENTARY"
        ))
        self.assertNotIn("Arven, küçük bir selamla karşılık verir", result["narration"])
        self.assertNotIn("Bu kısa etkileşim", result["narration"])
        self.assertNotIn("Bu işlerinizi kendi gözlerinizle görmedim", result["narration"])

    def test_greeting_does_not_ask_npc_to_revisit_old_claim(self):
        narrator = (
            "Bir dükkâncı başını kaldırır. "
            "'Bu işlerinizi kendi gözlerimle görmedim,' der."
        )
        result, telemetry = self.turn("Merhaba.", narrator)
        self.assertNotEqual(telemetry["narration_source"], "qwen", telemetry)
        self.assertEqual(telemetry["fallback_reason"], "UNRELATED_GREETING_REPLY")
        self.assertNotIn("Bu işlerinizi kendi gözlerimle görmedim", result["narration"])

    def test_greeting_meta_editorial_aside_is_not_accepted(self):
        narrator = (
            "Bir dükkâncı kısaca selam verir. "
            "Bu kısa etkileşim, şehir yaşamının bir örneğidir."
        )
        result, telemetry = self.turn("Merhaba.", narrator)
        self.assertNotEqual(telemetry["narration_source"], "qwen", telemetry)
        self.assertEqual(telemetry["fallback_reason"], "META_NARRATOR_COMMENTARY")
        self.assertNotIn("Bu kısa etkileşim", result["narration"])

    def test_lore_rejection_preserves_greeting_in_final_player_turn(self):
        # Exercise the full turn and the actual lore-claim rejection branch,
        # rather than directly calling a fallback helper.
        invented = (
            "Bir dükkâncı selam verir."  # Model cites a nonexistent lore fact below.
        )
        result, telemetry = self.turn(
            "Merhaba.", invented,
            lore_claims=[{"fact_id": "unverified:fictional_ruler"}],
        )
        self.assertEqual(result["action_result"]["action"], "dialogue")
        self.assertEqual(result["action_result"]["status"], "answered_smalltalk")
        self.assertEqual(telemetry["narration_source"], "deterministic_fallback")
        self.assertEqual(telemetry["narration_validation_result"], "python_fallback")
        self.assertEqual(telemetry["fallback_reason"], "UNVERIFIED_LORE_CLAIM",
                         (result["narration"], self.session.last_narration_safety))
        self.assertIn("selamına karşılık verir", result["narration"])
        self.assertIn("Neris", result["narration"])
        for forbidden in (
            "güvenilir bir doğrulamam yok", "kral", "yüz altın",
            "görev", "Elara", "Arven",
        ):
            self.assertNotIn(forbidden.casefold(), result["narration"].casefold())
        self.assertEqual(self.session.last_narration_safety["reason_code"],
                         "UNVERIFIED_LORE_CLAIM")

    def test_recorded_live_lore_prose_rejection_keeps_final_greeting(self):
        # Real recorded Qwen prose, exercised through the full turn pipeline.
        raw = (
            "Arven, dükkânın sahibine küçük bir selamla karşılık verir. "
            "Bu, dükkâncının gülümsemesine neden olur. "
            "Sokağın köşesindeki çeşme öğleden sonra kalabalıklaşır; "
            "Arven'in gözünde bu da bir anlam taşır gibi görünür. "
            "Dükkâncı sakin ve dikkatli bir şekilde başını hafifçe sallar: "
            "'Bu işlerinizi kendi gözlerinizle görmedim.' "
            "Arven, bu yanıtı alçak sesle onaylar ve alışverişe geçerken, "
            "dükkânın içinden çıkan küçük bir çığrtı duyulur. "
            "Bu an, Neverwinter'da geçen ilk gerçek anlayışlı etkileşimdir. "
            "Yeni bir gün, yeni bir hikaye ile devam ediyor."
        )
        result, telemetry = self.turn("Merhaba.", raw)
        self.assertEqual(telemetry["fallback_reason"], "UNVERIFIED_LORE_CLAIM",
                         (result["narration"], self.session.last_narration_safety))
        self.assertEqual(telemetry["narration_source"], "deterministic_fallback")
        self.assertEqual(telemetry["narration_validation_result"], "python_fallback")
        self.assertIn("selamına karşılık verir", result["narration"])
        for forbidden in ("Arven", "çeşme", "alışverişe", "güvenilir bir doğrulamam yok"):
            self.assertNotIn(forbidden.casefold(), result["narration"].casefold())

    def test_short_genuine_npc_greeting_remains_model_accepted(self):
        narrator = "Bir dükkâncı başını sallayarak seni selamlar."
        result, telemetry = self.turn("Merhaba.", narrator)
        self.assertEqual(telemetry["narration_source"], "qwen", telemetry)
        self.assertEqual(telemetry["narration_validation_result"], "accepted")
        self.assertEqual(result["narration"], narrator)

    def test_explicit_player_greeting_action_is_not_erased(self):
        narrator = "Başını sallayıp merhaba diyorsun. Neris de sana gülümser."
        result, telemetry = self.turn(
            "Başımı sallayıp merhaba diyorum.", narrator
        )
        self.assertEqual(telemetry["narration_source"], "qwen", telemetry)
        self.assertEqual(telemetry["narration_validation_result"], "accepted")
        self.assertEqual(result["narration"], narrator)

    def test_turkish_noun_substring_does_not_authorize_invented_movement(self):
        decision = game._narration_safety_decision(
            "Sonra hana girersin.",
            "Han girişindeki taş işçiliğini dikkatlice inceliyorum.",
            action_result={},
        )
        self.assertTrue(decision["unsafe"], decision)
        self.assertEqual(decision["reason_code"], "INVENTED_PLAYER_ACTION")

    def test_genuinely_reported_player_movement_remains_valid(self):
        decision = game._narration_safety_decision(
            "içeri girersin.",
            "içeri giriyorum.",
            action_result={},
        )
        self.assertFalse(decision["unsafe"], decision)

    def test_repaired_npc_answer_keeps_safe_text_after_invented_feeling(self):
        narration = (
            "Neris gülümser. Korkmuş hissedersin. "
            "'Gün iyi geçsin,' diye yanıt verir."
        )
        result, _ = self.turn("Başımı sallayıp merhaba diyorum.", narration)
        self.assertIn("Gün iyi geçsin", result["narration"])
        self.assertNotIn("Korkmuş hissedersin", result["narration"])

    def test_dialogue_repair_requires_bound_substantive_speech(self):
        npc = {"id": "npc_neris", "name": "Neris"}
        self.assertTrue(game._dialogue_repair_has_attributed_answer(
            "'Gün iyi geçsin,' diye yanıt verir.",
            npc,
            {"action": "dialogue", "npc_id": "npc_neris"},
        ))
        self.assertTrue(game._dialogue_repair_has_attributed_answer(
            "Bu hanı ailemden devraldım; kapatmak istemedim.",
            npc,
            {
                "action": "dialogue",
                "status": "experimental_attributed_speech",
                "npc_id": "npc_neris",
            },
        ))
        self.assertFalse(game._dialogue_repair_has_attributed_answer(
            "Neris gülümser.",
            npc,
            {
                "action": "dialogue",
                "status": "experimental_attributed_speech",
                "npc_id": "npc_neris",
            },
        ))
        self.assertFalse(game._dialogue_repair_has_attributed_answer(
            "“Gün iyi geçsin.”",
            npc,
            {"action": "explore", "npc_id": "npc_neris"},
        ))
        self.assertFalse(game._dialogue_repair_has_attributed_answer(
            "“Gün iyi geçsin.”",
            npc,
            {
                "action": "dialogue",
                "status": "experimental_attributed_speech",
                "npc_id": "npc_other",
            },
        ))

    def test_repair_rejects_a_second_invented_claim_in_the_remainder(self):
        narration = (
            "Neris gülümser. Sonra hana girersin. "
            "Ardından dışarı çıkarsın. 'Kuzeyden geldim,' diye yanıt verir."
        )
        result, telemetry = self.turn("Başımı sallayıp merhaba diyorum.", narration)
        self.assertNotIn("hana girersin", result["narration"])
        self.assertNotIn("dışarı çıkarsın", result["narration"])
        self.assertNotEqual(
            telemetry["narration_validation_result"], "accepted",
            telemetry,
        )


if __name__ == "__main__":
    unittest.main()

"""W09: speech, a quoted report, a threat, a condition, a negation and an OOC remark never become an attack.

`intent_contract.resolve_intent(text, mode, context)` classifies one player message (Turkish and English) into a single intent
kind; `build_narration_request(intent, delta, knowledge)` turns it into a concrete narrator task that keeps a line with its
speaker, asks for concrete content ("şaka yap" -> an actual joke), and forbids choosing the player's feelings, goals or
actions; `unauthorized_player_decisions` counts such choices in a narration; `risk_gate` stops only for a NEW perceivable risk.
The five free-outcome families never change attack/save/death rules: this module only reads text and returns data.
"""
from __future__ import annotations

import unittest

import intent_contract as ic

CONTEXT = {"player_name": "Aria", "npcs": [{"id": "npc_marek", "name": "Marek"}, {"id": "npc_gromm", "name": "Gromm"}]}

FIXTURES = {
    "tr": {
        "attack": ["Muhafıza kılıçla saldırıyorum."],
        "threat": ["Seni pişman edeceğim, uyarıyorum."],
        "quote": ["Haydut bağırdı: “Sana saldırıyorum!” diye."],
        "condition": ["Eğer bana saldırırsa kendimi savunacağım.", "Muhafız saldırırsa ona vuracağım."],
        "negation": ["Muhafıza saldırmıyorum.", "Gromm'a saldırmak istemiyorum."],
        "ooc": ["(OOC: bir saniye, su alıp geliyorum)"],
    },
    "en": {
        "attack": ["I attack the guard with my sword."],
        "threat": ["I'm warning you, I'll make you regret this."],
        "quote": ["The bandit shouted, \"I attack you!\" and ran."],
        "condition": ["If he attacks me, I will strike back."],
        "negation": ["I don't attack the guard.", "I won't attack him."],
        "ooc": ["[OOC] brb, grabbing water"],
    },
}


def counts(language):
    return {category: sum(ic.resolve_intent(text, "do", CONTEXT)["kind"] == "attack" for text in texts)
            for category, texts in FIXTURES[language].items()}


class IntentTests(unittest.TestCase):
    def test_intent_speech_and_quote_do_not_create_attack(self):
        speech = ic.resolve_intent('Marek\'e "Kapıyı aç" diyorum.', "do", CONTEXT)
        joke = ic.build_narration_request(ic.resolve_intent("Marek'e bir şaka yap.", "do", CONTEXT), {}, {})
        good = "Marek gülümsedi. “Kapı neden sinirli? Çünkü herkes ona vuruyor!” dedi."
        bad_decisions = [
            "Sen korkuyorsun ve kaçmaya karar veriyorsun.",
            "You feel angry and decide to leave.",
            "Içeri girmek istiyorsun.",
        ]
        obs = {
            "attack_counts": counts("tr"),
            "attack_counts_en": counts("en"),
            "unauthorized_player_decisions": ic.unauthorized_player_decisions(good, speech),
            "speaker_assignment_correct": (speech["speaker"] == "player" and speech["addressee"] == "npc_marek"
                                           and speech["line"] == "Kapıyı aç"),
            "concrete_joke_produced": (joke["task"]["concrete_content_required"] == "joke_text"
                                       and ic.narration_satisfies(joke, good)
                                       and not ic.narration_satisfies(joke, "Marek şaka yapıyor ve herkes gülüyor.")),
        }
        assert obs["attack_counts"] == {"attack": 1, "threat": 0, "quote": 0, "condition": 0, "negation": 0, "ooc": 0}
        assert obs["attack_counts_en"] == {"attack": 1, "threat": 0, "quote": 0, "condition": 0, "negation": 0, "ooc": 0}
        assert obs["unauthorized_player_decisions"] == 0
        assert obs["speaker_assignment_correct"] is True
        assert obs["concrete_joke_produced"] is True
        for text in bad_decisions:
            self.assertGreaterEqual(ic.unauthorized_player_decisions(text, speech), 1, text)

    def test_every_category_resolves_to_its_own_kind(self):
        for language, groups in FIXTURES.items():
            for category, texts in groups.items():
                for text in texts:
                    self.assertEqual(ic.resolve_intent(text, "do", CONTEXT)["kind"], category, (language, text))

    def test_spoken_mode_is_never_an_action(self):
        for text in ("Seni öldüreceğim!", "I attack you!", "Muhafıza saldırıyorum"):
            kind = ic.resolve_intent(text, "say", CONTEXT)["kind"]
            self.assertIn(kind, {"speech", "threat"}, text)

    def test_request_keeps_the_line_with_its_speaker_and_forbids_player_decisions(self):
        intent = ic.resolve_intent('Marek\'e "Sana güveniyorum" diyorum.', "do", CONTEXT)
        request = ic.build_narration_request(intent, {"changes": []}, {"known": []})
        self.assertEqual(request["speaker"], "player")
        self.assertNotEqual(request["speaker"], "npc_marek")
        self.assertIn("player_feelings", request["forbidden"])
        self.assertIn("player_goals", request["forbidden"])
        self.assertIn("player_actions", request["forbidden"])
        self.assertFalse(request["invent_mechanical_result"])

    def test_known_risk_is_not_confirmed_again_but_a_new_perceivable_one_stops(self):
        intent = ic.resolve_intent("Kapıyı açıyorum.", "do", CONTEXT)
        known = ic.risk_gate(intent, {"known_risk_ids": ["risk:trap_door"]}, [{"id": "risk:trap_door", "significant": True}])
        new = ic.risk_gate(intent, {"known_risk_ids": ["risk:trap_door"]}, [{"id": "risk:poison_gas", "significant": True, "perceivable": True}])
        hidden = ic.risk_gate(intent, {"known_risk_ids": []}, [{"id": "risk:secret_pit", "significant": True, "perceivable": False}])
        minor = ic.risk_gate(intent, {"known_risk_ids": []}, [{"id": "risk:dust", "significant": False, "perceivable": True}])
        self.assertFalse(known["needs_confirmation"])
        self.assertTrue(new["needs_confirmation"])
        self.assertEqual(new["risk_ids"], ["risk:poison_gas"])
        self.assertFalse(hidden["needs_confirmation"], "an unperceivable risk is not disclosed by asking")
        self.assertFalse(minor["needs_confirmation"])


if __name__ == "__main__":
    unittest.main()

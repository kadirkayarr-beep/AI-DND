"""Closed-family narration checks. No model call and no world write."""
import unittest

import narration_claims


def packet(**overrides):
    base = {
        "action": None,
        "outcome": None,
        "target": None,
        "damage": None,
        "damage_values": [],
        "critical": False,
        "dead": False,
        "perception": None,
        "dodge": False,
        "any_hit": False,
        "any_miss": False,
        "door_name": "Han Kapısı",
        "door_open": None,
        "door_locked": None,
        "player_hidden": None,
        "required": [],
    }
    base.update(overrides)
    return base


class NarrationClaimTests(unittest.TestCase):
    @staticmethod
    def combat_packet(player_outcome, enemy_outcome, player_status="active",
                      enemy_damage=0):
        result = {
            "action": "attack",
            "outcome": player_outcome,
            "target_name": "Sentinel",
            "damage": 0 if player_outcome == "miss" else 4,
            "target_status": "active",
            "enemy_action": {
                "actor_name": "Sentinel",
                "outcome": enemy_outcome,
                "damage": enemy_damage,
            },
            "combat": {"player_combat_status": player_status},
        }
        return narration_claims.packet_from_result(result)

    def test_fatal_exchange_rejects_enemy_miss_and_unharmed_reversal(self):
        facts = self.combat_packet("miss", "hit", "dead", enemy_damage=30)
        verdict = narration_claims.assess(
            "Rakibin ıskalar; sapasağlamsın.", facts
        )
        self.assertTrue(verdict["reject"], verdict)

    def test_explicit_player_miss_enemy_hit_and_death_remains_valid(self):
        facts = self.combat_packet("miss", "hit", "dead", enemy_damage=30)
        text = (
            "Saldırın ıskalar. Rakibinin saldırısı sana isabet eder; "
            "hayatını kaybedersin."
        )
        self.assertFalse(narration_claims.assess(text, facts)["reject"])

    def test_player_miss_after_enemy_hit_keeps_subject_change(self):
        facts = self.combat_packet("miss", "hit", "active", enemy_damage=3)
        text = "Rakibin sana isabet eder; saldırın ıskalar."
        self.assertFalse(narration_claims.assess(text, facts)["reject"])

    def test_enemy_miss_is_bound_to_enemy_not_to_a_blow_keyword(self):
        hit_facts = self.combat_packet("miss", "hit", "active", enemy_damage=3)
        text = "Rakibin bir darbe savurur ama ıskalar; sapasağlamsın."
        self.assertTrue(narration_claims.assess(text, hit_facts)["reject"])

        miss_facts = self.combat_packet("miss", "miss")
        true_miss = "Saldırın ıskalar. Rakibin bir darbe savurur ama ıskalar."
        self.assertFalse(narration_claims.assess(true_miss, miss_facts)["reject"])

    def test_negated_death_is_not_a_death_claim_but_alive_claim_conflicts(self):
        wording = "Saldırın ıskalar. Ölürsün denemez; hayattasın."
        active_facts = self.combat_packet("miss", "hit", "active", enemy_damage=3)
        dead_facts = self.combat_packet("miss", "hit", "dead", enemy_damage=30)
        self.assertFalse(narration_claims.assess(wording, active_facts)["reject"])
        denied = narration_claims.assess(wording, dead_facts)
        self.assertTrue(denied["reject"], denied)
        self.assertEqual(denied["reason"], "COMBAT_RESULT_CONTRADICTION")

        actual = narration_claims.assess(
            "Saldırın ıskalar. Rakibinin saldırısı sana isabet eder; "
            "hayatını kaybedersin.",
            dead_facts,
        )
        self.assertFalse(actual["reject"], actual)

    def test_true_miss_and_nonfatal_hit_narration_remain_valid(self):
        miss_facts = self.combat_packet("miss", "miss")
        self.assertFalse(narration_claims.assess(
            "Saldırın ıskalar; rakibinin saldırısı da ıskalar.", miss_facts
        )["reject"])

        hit_facts = self.combat_packet("hit", "hit", enemy_damage=3)
        self.assertFalse(narration_claims.assess(
            "Saldırın isabet eder. Rakibin sana isabet eder; 3 hasar alırsın.",
            hit_facts,
        )["reject"])

    def test_open_door_accepts_two_wordings_and_rejects_the_locked_wording(self):
        facts = packet(door_open=True, door_locked=False, required=["door_open"])
        for sentence in ("Kapı gıcırdayarak açılır.", "Kilit çözülür ve kapı aralanır."):
            with self.subTest(sentence=sentence):
                verdict = narration_claims.assess(sentence, facts)
                self.assertFalse(verdict["reject"], verdict)
        locked = narration_claims.assess("Kapı kilitli kalır.", facts)
        self.assertTrue(locked["reject"])
        self.assertEqual(locked["reason"], "DOOR_RESULT_CONTRADICTION")

    def test_negated_open_claim_is_the_closed_family(self):
        facts = packet(door_open=False, door_locked=True, required=["door_closed"])
        verdict = narration_claims.assess("Kapı artık açık değil.", facts)
        self.assertFalse(verdict["reject"], verdict)

    def test_perception_chain_is_rejected_when_the_packet_has_none(self):
        verdict = narration_claims.assess(
            "Muhafız sesi duyup sana bakar.",
            packet(),
        )
        self.assertTrue(verdict["reject"])
        self.assertEqual(verdict["reason"], "PERCEPTION_NOT_RESOLVED")
        for texture in (
            "Pencerede yağmurun düzenli sesi duyulur.",
            "Gromm elinde bir bardak tutarken sana baktı.",
        ):
            with self.subTest(texture=texture):
                self.assertFalse(narration_claims.assess(texture, packet())["reject"])

    def test_unrecognized_texture_is_not_rejected(self):
        verdict = narration_claims.assess("Sokakta rüzgâr var.", packet())
        self.assertFalse(verdict["reject"], verdict)

    def test_damage_number_must_match_and_a_hit_without_a_number_stands(self):
        facts = packet(
            action="attack",
            outcome="hit",
            target="Goblin",
            damage=14,
            damage_values=[14],
            any_hit=True,
            required=["hit"],
        )
        wrong = narration_claims.assess("Goblin 14 hasar alır.", packet(
            action="attack", outcome="hit", target="Goblin",
            damage=4, damage_values=[4], any_hit=True, required=["hit"],
        ))
        self.assertTrue(wrong["reject"])
        self.assertEqual(wrong["reason"], "MECHANICAL_NUMBER")
        blow = narration_claims.assess("Ağır bir darbe alır.", facts)
        self.assertFalse(blow["reject"], blow)

    def test_greeting_and_name_are_not_closed_claims(self):
        for sentence in ("Merhaba yolcu.", "Benim adım Arven."):
            with self.subTest(sentence=sentence):
                verdict = narration_claims.assess(sentence, packet())
                self.assertFalse(verdict["reject"], verdict)

    def test_fallback_sentences_agree_with_their_packets(self):
        samples = [
            packet(door_open=True, required=["door_open"]),
            packet(door_open=False, required=["door_closed"]),
            packet(player_hidden=True, required=["hidden"]),
            packet(player_hidden=False, required=["not_hidden"]),
            packet(
                action="attack", outcome="hit", target="Haydut",
                damage=14, damage_values=[14], critical=True, dead=True,
                dodge=True, any_hit=True, required=["hit", "critical", "death", "dodge"],
            ),
            packet(
                action="attack", outcome="miss", any_miss=True, required=["miss"],
            ),
        ]
        for facts in samples:
            sentence = narration_claims.fallback_sentence(facts)
            verdict = narration_claims.assess(sentence, facts)
            self.assertFalse(verdict["reject"], (sentence, verdict))

    def test_checker_does_not_call_a_model(self):
        source = narration_claims.__loader__.get_source(narration_claims.__name__)
        self.assertNotIn("ollama", source)
        self.assertNotIn("chat(", source)


if __name__ == "__main__":
    unittest.main()

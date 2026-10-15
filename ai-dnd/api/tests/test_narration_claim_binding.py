"""Actor, target, and result must stay bound. No model and no world write."""
import unittest

import narration_claims


def attack(**overrides):
    result = {
        "action": "attack",
        "outcome": "hit",
        "target_name": "Goblin",
        "damage": 4,
        "target_status": "alive",
    }
    result.update(overrides)
    return narration_claims.packet_from_result(result)


class NarrationClaimBindingTests(unittest.TestCase):
    def test_wrong_target_is_not_accepted_because_the_damage_number_matches(self):
        facts = attack()
        verdict = narration_claims.assess("Ork bir darbe alır: 4 hasar.", facts)
        self.assertTrue(verdict["reject"], verdict)
        self.assertEqual(verdict["reason"], "COMBAT_RESULT_CONTRADICTION")

    def test_named_target_accepts_its_own_damage_and_a_wording_without_a_number(self):
        facts = attack()
        for sentence in (
            "Goblin bir darbe alır: 4 hasar.",
            "Goblin sendeleyerek bir darbe alır.",
            "Ağır bir darbe alır.",
        ):
            with self.subTest(sentence=sentence):
                verdict = narration_claims.assess(sentence, facts)
                self.assertFalse(verdict["reject"], verdict)

    def test_enemy_damage_is_not_the_players_damage_on_the_named_target(self):
        facts = attack(enemy_actions=[{
            "actor_name": "Goblin",
            "outcome": "hit",
            "damage": 9,
        }])
        stolen = narration_claims.assess("Goblin bir darbe alır: 9 hasar.", facts)
        self.assertTrue(stolen["reject"], stolen)
        self.assertIn(stolen["reason"], {"COMBAT_RESULT_CONTRADICTION", "MECHANICAL_NUMBER"})
        own = narration_claims.assess(
            "Goblin bir darbe alır: 4 hasar. Sana 9 hasar verir.",
            facts,
        )
        self.assertFalse(own["reject"], own)
        player_hit = narration_claims.assess(
            "Karşı saldırı sana isabet eder; 9 hasar alırsın.",
            facts,
        )
        self.assertFalse(player_hit["reject"], player_hit)

    def test_critical_and_miss_stay_on_the_exchange_they_name(self):
        normal = attack()
        crit = narration_claims.assess("Goblin kritik bir darbe alır.", normal)
        self.assertTrue(crit["reject"], crit)
        missed = narration_claims.assess("Saldırın Goblin'i ıskalar.", normal)
        self.assertTrue(missed["reject"], missed)

        critical = attack(outcome="critical_hit")
        self.assertFalse(narration_claims.assess(
            "Goblin kritik bir darbe alır: 4 hasar.", critical,
        )["reject"])

        miss = attack(outcome="miss", damage=None)
        self.assertFalse(narration_claims.assess(
            "Saldırın hedefi ıskalar.", miss,
        )["reject"])
        false_hit = narration_claims.assess("Goblin bir darbe alır.", miss)
        self.assertTrue(false_hit["reject"], false_hit)

        enemy_crit = attack(enemy_actions=[{
            "actor_name": "Goblin",
            "outcome": "critical_hit",
            "damage": 9,
        }])
        stolen_crit = narration_claims.assess(
            "Goblin kritik bir darbe alır: 4 hasar.", enemy_crit,
        )
        self.assertTrue(stolen_crit["reject"], stolen_crit)
        bound_crit = narration_claims.assess(
            "Goblin bir darbe alır: 4 hasar. "
            "Rakibin kritik karşı saldırısı sana isabet eder; 9 hasar alırsın.",
            enemy_crit,
        )
        self.assertFalse(bound_crit["reject"], bound_crit)

    def test_negated_hit_contradicts_a_landed_blow_and_fits_a_miss(self):
        landed = narration_claims.assess("Goblin bir darbe almaz.", attack())
        self.assertTrue(landed["reject"], landed)
        miss = attack(outcome="miss", damage=None)
        self.assertFalse(narration_claims.assess(
            "Goblin bir darbe almaz.", miss,
        )["reject"])

    def test_a_true_hit_does_not_authorize_a_later_hearing_reaction(self):
        facts = attack()
        verdict = narration_claims.assess(
            "Goblin bir darbe alır. Muhafız ayak seslerini işiterek sana yönelir.",
            facts,
        )
        self.assertTrue(verdict["reject"], verdict)
        self.assertEqual(verdict["reason"], "PERCEPTION_NOT_RESOLVED")
        self.assertFalse(narration_claims.assess(
            "Goblin bir darbe alır. Sokakta rüzgâr var.", facts,
        )["reject"])
        quiet = narration_claims.packet_from_result({})
        for texture in (
            "Pencerede yağmurun düzenli sesi duyulur.",
            "Gromm elinde bir bardak tutarken sana baktı.",
        ):
            with self.subTest(texture=texture):
                self.assertFalse(narration_claims.assess(texture, quiet)["reject"])
                beside_hit = f"Goblin bir darbe alır. {texture}"
                self.assertFalse(narration_claims.assess(beside_hit, facts)["reject"])

    def test_ordinary_olur_is_not_a_death_and_a_real_death_stays_bound(self):
        alive = attack()
        quiet = narration_claims.packet_from_result({})
        for sentence in ("Her şey yolunda olur.", "Ne oldu, her şey yolunda olur."):
            with self.subTest(sentence=sentence):
                verdict = narration_claims.assess(sentence, quiet)
                self.assertFalse(verdict["reject"], verdict)
        beside_hit = narration_claims.assess(
            "Goblin bir darbe alır. Her şey yolunda olur.", alive,
        )
        self.assertFalse(beside_hit["reject"], beside_hit)
        bare = narration_claims.assess("Her şey yolunda olur.", alive)
        self.assertNotEqual(bare.get("reason"), "COMBAT_RESULT_CONTRADICTION")

        false_death = narration_claims.assess("Goblin ölür.", alive)
        self.assertTrue(false_death["reject"], false_death)
        self.assertEqual(false_death["reason"], "COMBAT_RESULT_CONTRADICTION")

        dead = attack(target_status="dead")
        self.assertFalse(narration_claims.assess(
            "Goblin bir darbe alır ve ölür.", dead,
        )["reject"])
        other = narration_claims.assess("Goblin bir darbe alır. Ork öldü.", dead)
        self.assertTrue(other["reject"], other)
        self.assertEqual(other["reason"], "COMBAT_RESULT_CONTRADICTION")

    def test_checker_does_not_call_a_model_or_write_state(self):
        source = narration_claims.__loader__.get_source(narration_claims.__name__)
        self.assertNotIn("ollama", source)
        self.assertNotIn("chat(", source)
        facts = attack()
        before = dict(facts)
        narration_claims.assess("Ork bir darbe alır: 4 hasar.", facts)
        self.assertEqual(facts, before)


if __name__ == "__main__":
    unittest.main()

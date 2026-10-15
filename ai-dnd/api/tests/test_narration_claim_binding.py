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

    def test_named_enemy_actor_keeps_its_own_damage_and_critical(self):
        facts = attack(enemy_actions=[
            {"actor_name": "Goblin", "outcome": "critical_hit", "damage": 9},
            {"actor_name": "Ork", "outcome": "hit", "damage": 2},
        ])
        mixed = narration_claims.assess(
            "Goblin bir darbe alır. Ork sana kritik bir saldırıyla 9 hasar verir.",
            facts,
        )
        self.assertTrue(mixed["reject"], mixed)
        unnamed = attack(enemy_actions=[{
            "outcome": "critical_hit",
            "damage": 9,
            "actor": "npc_goblin",
        }])
        borrowed = narration_claims.assess(
            "Ork sana kritik bir saldırıyla 9 hasar verir.",
            unnamed,
        )
        self.assertTrue(borrowed["reject"], borrowed)
        bound = narration_claims.assess(
            "Goblin bir darbe alır: 4 hasar. "
            "Goblin sana kritik bir saldırıyla 9 hasar verir. "
            "Ork sana 2 hasar verir.",
            facts,
        )
        self.assertFalse(bound["reject"], bound)
        generic = narration_claims.assess(
            "Goblin bir darbe alır. "
            "Rakibin kritik karşı saldırısı sana isabet eder; 9 hasar alırsın.",
            unnamed,
        )
        self.assertFalse(generic["reject"], generic)

    def test_every_blow_in_one_sentence_binds_to_its_own_subject(self):
        facts = attack()
        for sentence in (
            "Goblin bir darbe alır ve Ork bir darbe alır.",
            "Goblin bir darbe alır ama Goblin bir darbe almaz.",
            "Ork bir darbe alır; Goblin izler.",
        ):
            with self.subTest(sentence=sentence):
                verdict = narration_claims.assess(sentence, facts)
                self.assertTrue(verdict["reject"], verdict)
                self.assertEqual(verdict["reason"], "COMBAT_RESULT_CONTRADICTION")
        for sentence in (
            "Goblin bir darbe alır. Goblin izler.",
            "Goblin bir darbe alır ve sendeleyerek durur.",
            "Goblin sendeleyerek bir darbe alır.",
        ):
            with self.subTest(sentence=sentence):
                self.assertFalse(narration_claims.assess(sentence, facts)["reject"])

    def test_supported_damage_spellings_stay_on_the_named_target(self):
        facts = attack(enemy_actions=[{
            "actor_name": "Goblin",
            "outcome": "hit",
            "damage": 9,
        }])
        for sentence in (
            "Goblin bir darbe alır: 9 puan hasar.",
            "Goblin bir darbe alır: hasar 9.",
        ):
            with self.subTest(sentence=sentence):
                verdict = narration_claims.assess(sentence, facts)
                self.assertTrue(verdict["reject"], verdict)
                self.assertIn(verdict["reason"], {"MECHANICAL_NUMBER", "COMBAT_RESULT_CONTRADICTION"})
        for sentence in (
            "Goblin bir darbe alır: 4 puan hasar.",
            "Goblin bir darbe alır: hasar 4.",
            "Goblin bir darbe alır: 4 hasar. Sana 9 puan hasar verir.",
        ):
            with self.subTest(sentence=sentence):
                self.assertFalse(narration_claims.assess(sentence, facts)["reject"])

    def test_multiword_target_fallback_agrees_with_its_packet(self):
        facts = attack(target_name="Ork Savaşçısı", damage=4, target_status="dead")
        sentence = narration_claims.fallback_sentence(facts)
        self.assertEqual(
            sentence,
            "Ork Savaşçısı, bir darbe alır: 4 hasar. Ork Savaşçısı ölür.",
        )
        verdict = narration_claims.assess(sentence, facts)
        self.assertFalse(verdict["reject"], verdict)
        partial = narration_claims.assess("Ork Savaşçısı bir darbe alır. Ork ölür.", facts)
        self.assertTrue(partial["reject"], partial)
        self.assertEqual(partial["reason"], "COMBAT_RESULT_CONTRADICTION")
        alive = attack(target_name="Ork Savaşçısı", damage=4)
        ordinary = narration_claims.assess(
            "Ork Savaşçısı bir darbe alır. Her şey yolunda olur.",
            alive,
        )
        self.assertFalse(ordinary["reject"], ordinary)
        spoken = narration_claims.assess("Ne oldu, her şey yolunda olur.", alive)
        self.assertNotEqual(spoken.get("reason"), "COMBAT_RESULT_CONTRADICTION")

    def test_received_damage_binds_without_the_word_sana(self):
        facts = attack(enemy_actions=[{
            "actor_name": "Goblin",
            "outcome": "hit",
            "damage": 9,
        }])
        stolen = narration_claims.assess(
            "Goblin bir darbe alır: 4 hasar. 4 hasar alırsın.",
            facts,
        )
        self.assertTrue(stolen["reject"], stolen)
        self.assertEqual(stolen["reason"], "MECHANICAL_NUMBER")
        own = narration_claims.assess(
            "Goblin bir darbe alır: 4 hasar. 9 hasar alırsın.",
            facts,
        )
        self.assertFalse(own["reject"], own)
        for sentence in (
            "Goblin bir darbe alır: 4 hasar. 4 puan hasar alırsın.",
            "Goblin bir darbe alır: 4 hasar. Hasar 4 alırsın.",
        ):
            with self.subTest(sentence=sentence):
                verdict = narration_claims.assess(sentence, facts)
                self.assertTrue(verdict["reject"], verdict)
                self.assertEqual(verdict["reason"], "MECHANICAL_NUMBER")
        for sentence in (
            "Goblin bir darbe alır: 4 hasar. 9 puan hasar alırsın.",
            "Goblin bir darbe alır: 4 hasar. Hasar 9 alırsın.",
        ):
            with self.subTest(sentence=sentence):
                self.assertFalse(narration_claims.assess(sentence, facts)["reject"])

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

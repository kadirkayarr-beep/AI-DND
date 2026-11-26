"""G2.4: a roll comes before the speech it decides, and the words that follow keep to the roll (D-226, D-241, D-242,
D-251, D-012). The rolled scare turn route is pinned by journey 87; the plain line has no scenario file here, so a
scenario is written to a temporary folder and run by the same journey runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import town_knowledge
from api.tests.journeys.runner import JourneyCase, describe_problems
from api.tests.journeys.schema import load_scenario

PLAIN_SCARE = "Önümden çekil, yoksa başın belaya girer!"
UNMOVED = "Kavşim kollarını kavuşturup sana yukarıdan bakıyor; geri adım atmıyor, sözlerin ona işlemiyor."
BANNED = ["geri adım atmıyor", "sözlerin ona işlemiyor", "Anladım.", "Hı. Duydum.", "Devam et, dinliyorum.",
          "Sen bilirsin.", "Peki.", "Bak sen.", "Öyle olsun bakalım.", "Yavaş ol."]


class TestAPlainScareAnswersTheRoll(JourneyCase):
    """D-226: no 'çalışıyorum' in the line; the reading names the try, the roll still decides the reply."""

    async def test_a_won_plain_scare_is_not_told_as_unmoved(self):
        scenario = {
            "id": "d226_plain_scare", "title": "Plain scare line, roll before the reply (D-226)", "source_items": [226],
            "setup": {"npcs": [{"id": "kavsim", "name": "Kavşim", "role": "Muhafız", "current_hp": 12}],
                      "currency": {"player": 40, "kavsim": 60}, "inventory": [], "seed": 6,
                      "campaign_seed": 22601, "front_proposal": True},
            "steps": [{"say": PLAIN_SCARE,
                       "script": {"front": {"kind": "speak_to", "check": "Intimidation", "person_id": "kavsim"},
                                  "narration": UNMOVED},
                       "expect": {"zar": {"beceri": "Intimidation", "sonuc": "success", "zar_var": True},
                                  "gerekli_metin": ["yutkunuyor"], "yasak_metin": BANNED}}],
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d226_plain_scare.json"
            path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
            steps = await self.run_scenario(load_scenario(path))
        self.assertEqual(describe_problems(steps), [])


class TestAFluentWinAfterALostRollIsNotKept(unittest.TestCase):
    """D-241: the failure line stands alone when the narration tells the win in words no short list holds."""

    FAILED = {"action": "skill_check", "status": "resolved", "outcome": "failure", "skill": "Intimidation"}
    SAID = "Muhafızı korkutmaya çalışıyorum"

    def setUp(self):
        session = game.create_session(seed=2411)
        token = game._ACTIVE_SESSION.set(session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)

    def told(self, narration):
        return game._states_the_failed_check(narration, self.FAILED, self.SAID)

    def test_a_win_told_fluently_is_dropped(self):
        for narration in ("Muhafız yutkunuyor ve kenara çekiliyor.", "Muhafızın yüzü soluyor; yolu açıyor.",
                          "Muhafız boyun eğip sana yol veriyor.", "Muhafız razı oluyor ve geri çekiliyor."):
            with self.subTest(narration=narration):
                out = self.told(narration)
                self.assertTrue(out.startswith("Yetenek kontrolün başarısız olur"), out)
                self.assertNotIn(narration.split()[1], out)
                self.assertEqual(out, game._fallback_for_action_result(self.SAID, self.FAILED))

    def test_the_safety_check_refuses_a_lost_try_told_as_won(self):
        for narration in ("Muhafız yutkunuyor ve kenara çekiliyor.", "Muhafız boyun eğip sana yol veriyor."):
            with self.subTest(narration=narration):
                decision = game._session()._narration_safety_decision(narration, self.SAID, None, self.FAILED)
                self.assertEqual(decision["reason_code"], "SKILL_RESULT_CONTRADICTION", decision)
        kept = "Muhafız geri çekilmiyor; gözünü kırpmadan sana bakıyor."
        self.assertFalse(game._session()._narration_safety_decision(kept, self.SAID, None, self.FAILED)["unsafe"])

    def test_a_room_that_carries_on_keeps_its_text(self):
        out = self.told("Bu sırada arkada bir kâtip satırı yeniden okuyor.")
        self.assertIn("Bu sırada arkada", out)


class TestARefusedJobShowsNoTerms(unittest.TestCase):
    """D-242: the owner's terms are added to a reply that left them out, never to one that turns the work down."""

    TERMS = "Mektubu götürürsün; ücret 14 bakır."

    def terms_for(self, reply):
        thread = {"owner_line": self.TERMS, "terms": {"pay": 14}}
        with patch.object(town_knowledge, "_offerable", return_value=thread), \
                patch.object(town_knowledge.world_threads, "owner_mood", return_value="yes"):
            return town_knowledge.terms_to_add({}, {"id": "npc"}, "iş var mı", reply, asked_about_work=True)

    def test_a_refusal_gets_no_terms(self):
        for reply in ("Bugün iş yok, git başka kapıyı çal.", "Sana verecek bir işim yok.",
                      "Şu an kimseye ihtiyacım yok.", "Hayır, böyle bir iş vermem."):
            with self.subTest(reply=reply):
                self.assertIsNone(self.terms_for(reply))

    def test_a_reply_that_skipped_the_terms_still_gets_them(self):
        self.assertEqual(self.terms_for("Dinliyorum, anlat bakalım."), self.TERMS)


class TestATravelLineIsNotSaidTwice(unittest.TestCase):
    """D-251: the fixed 'no road' line changes between draws (the same rule the theft tables follow)."""

    LOST = {"action": "travel", "status": "failed", "target_reference": "hedef"}
    WANTED = {"action": "travel", "status": "intended", "target_reference": "Tapınak"}

    def setUp(self):
        session = game.create_session(seed=2511)
        token = game._ACTIVE_SESSION.set(session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)

    def draws(self, result):
        return [game._fallback_for_action_result("kuzeye gidiyorum", result) for _ in range(8)]

    def test_two_draws_in_a_row_differ(self):
        for result in (self.LOST, self.WANTED):
            with self.subTest(status=result["status"]):
                lines = self.draws(result)
                self.assertTrue(all(lines), lines)
                self.assertTrue(all(a != b for a, b in zip(lines, lines[1:], strict=False)), lines)


class TestTheRealAwardMayBeSaidInTheModelsWords(unittest.TestCase):
    """D-012 (owner S21 a): the real amount may be said; another amount is still refused."""

    def setUp(self):
        self.session = game.create_session(seed=1201)
        token = game._ACTIVE_SESSION.set(self.session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        self.session._remember_xp_award({"previous_level": 3, "new_level": 3, "xp_gained": 25, "hit_points_gained": 0})

    def decide(self, narration):
        return self.session._narration_safety_decision(
            narration, "bitirdim", None, {"action": "explore", "status": "resolved"})

    def test_the_real_amount_passes(self):
        for narration in ("Bu iş için 25 deneyim puanı kazandın.", "25 XP kazandın, güzel iş.",
                          "Kazandığın 25 deneyim puanı hak ettiğin bir ödül."):
            with self.subTest(narration=narration):
                self.assertNotEqual(self.decide(narration).get("reason_code"), "CANONICAL_XP_CONTRADICTION")

    def test_another_amount_is_still_refused(self):
        for narration in ("Bu iş için 50 deneyim puanı kazandın.", "Deneyim puanı kazandın.",
                          "25 deneyim puanı kazandın ve 40 XP daha aldın."):
            with self.subTest(narration=narration):
                self.assertEqual(self.decide(narration).get("reason_code"), "CANONICAL_XP_CONTRADICTION")


if __name__ == "__main__":
    unittest.main()

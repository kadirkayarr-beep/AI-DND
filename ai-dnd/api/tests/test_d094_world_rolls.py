"""D-094, D-173 (G1.1): a risky try that needs the world (Stealth, Athletics, Perception) is rolled by the engine too.

The front reading may name the check; the engine validates it (a hide still needs cover or the dark, D-171), sets the
DC and rolls, so the outcome is the engine's and never the narration's. D-173: a theft line with words after it
("... çalmak için zar atıyorum, kimse görmesin", a typo in "atıyorum") is still a try.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bold_acts
import front_proposal
import game
import world_threads
from api.tests.test_front_proposal import FrontTable
from api.tests.town_seed import fixed_town

WORLD_CHECKS = ("Stealth", "Athletics", "Perception")
LINES = {
    "Stealth": "Muhafızın yanından gizlice geçiyorum",
    "Athletics": "Nehrin karşısına yüzerek geçmeye çalışıyorum",
    "Perception": "Muhafızların ne konuştuğunu kulak kabartıp anlamaya çalışıyorum",
}


def reading(check, kind="attempt"):
    return {"front": {"kind": kind, "check": check, "timing": "now"}}


class TheReadingMayNameAWorldCheck(unittest.TestCase):
    def test_a_present_try_keeps_its_world_check(self):
        for skill in WORLD_CHECKS:
            with self.subTest(skill=skill):
                self.assertIn(skill, front_proposal.CHECKS)
                self.assertEqual(front_proposal.check_in(reading(skill), LINES[skill]), skill)

    def test_a_question_or_a_line_that_is_no_try_now_names_no_check(self):
        for skill in WORLD_CHECKS:
            for line in ("gizlice geçebilir miyim?", "yarın gizlice geçeceğim", "dün gizlice geçtim",
                         "gizlice geçmiyorum"):
                with self.subTest(skill=skill, line=line):
                    self.assertEqual(front_proposal.check_in(reading(skill), line), "")

    def test_the_engine_turns_the_reading_into_the_roll(self):
        session = game._session()
        saved = getattr(session, "_front_check", None)
        self.addCleanup(setattr, session, "_front_check", saved)
        for skill in WORLD_CHECKS:
            session._front_check = skill
            with self.subTest(skill=skill):
                self.assertEqual(game.deterministic_check_for_action(LINES[skill]),
                                 {"action_type": "check", "skill": skill, "difficulty": "medium"})


class TheEngineRollsTheWorldTry(FrontTable):
    async def roll(self, skill, *, night):
        with fixed_town(self, 10941):
            await self.begin()
        self.client.front = {"kind": "attempt", "check": skill}
        with patch.object(world_threads, "_in_the_night", return_value=night):
            return await self.line(LINES[skill])

    async def test_each_world_try_rolls_its_skill_and_the_engine_decides_the_outcome(self):
        for skill in WORLD_CHECKS:
            with self.subTest(skill=skill):
                reply = await self.roll(skill, night=True)
                result = reply["skill_check_result"]
                self.assertIsNotNone(result, reply["narration"])
                self.assertEqual(result["skill"], skill)
                self.assertIn(result["outcome"], {"success", "failure", "critical_success", "critical_failure"})
                self.assertEqual(result["total"], result["d20"] + result["total_modifier"])

    async def test_a_hide_in_the_open_by_day_still_rolls_nothing(self):
        reply = await self.roll("Stealth", night=False)  # D-171: no cover, no roll
        self.assertIsNone(reply.get("skill_check_result"))


class ATheftWithWordsAfterItIsStillATry(unittest.TestCase):
    session = SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos)

    def test_trailing_words_and_a_typo_still_roll(self):
        for line in ("kesesini çalmak için zar atıyorum, kimse görmesin",
                     "kesesini çalmak için zar atıyorm",
                     "kesesini fark ettirmeden çalmak için zar atıyorum, kimse görmesin"):
            with self.subTest(line=line):
                self.assertTrue(bold_acts.is_theft(self.session, line))

    def test_a_refusal_a_plan_a_past_line_and_a_question_stay_no_theft(self):
        for line in ("kesesini çalmayacağım, zar atmıyorum", "kesesini çalmak için zar atıyorum diye bağırıyorum",
                     "kesesini çalmak için zar atıyorum ama vazgeçiyorum", "kesesini çalmak için zar atıyorum dün",
                     "kesesini çalmak için zar atıyorum sonra", "kesesini çalmak için zar atıyor",
                     "kesesini çalmak için zar atıyorum?", "muhafıza saldırıyorum, kesesini çalmak için zar atıyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts.is_theft(self.session, line))

    def test_reported_past_pretended_or_unfinished_tails_are_no_theft(self):
        base = "kesesini çalmak için zar atıyorum"
        for tail in ("dedim", "dedi", "demiştim", "diyor", "sanıyordum", "geçen hafta", "mesela", "şaka",
                     "gibi yapıyorum", "ya da atmıyorum", "ve geri veriyorum", "mu", "mu acaba"):
            with self.subTest(tail=tail):
                self.assertFalse(bold_acts.is_theft(self.session, f"{base} {tail}"))

    def test_a_quiet_wish_tail_still_rolls(self):
        for tail in ("kimse görmesin", "kimse görmeden", "kimse fark etmesin"):
            with self.subTest(tail=tail):
                self.assertTrue(bold_acts.is_theft(self.session, f"kesesini çalmak için zar atıyorum, {tail}"))


if __name__ == "__main__":
    unittest.main()

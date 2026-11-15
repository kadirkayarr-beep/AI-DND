"""D-094 general fix: the front reading may name the check a risky try needs; the engine validates it, sets the DC and
rolls (Q17 "the engine referees, the model writes", ZAR_KURALLARI 2.2: roll only for a real, present try).

Only the skills whose outcome needs no world precondition and moves no coin are open to the reading: Intimidation,
Deception, Persuasion, Insight. A pickpocket is the reading's deed=steal, never a check (R-7, after three reviews found
coin moved by a Sleight of Hand reading on hiding, palming, putting and giving back). A question, a
reading of another kind and a fight give no check. The turn route is pinned by journeys 51 and 51b.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import bold_acts
import front_proposal
import game
from api.tests.test_d094_dice_words import NOT_TRIES, TRIES

LISTED = {key: [] for key in ("people", "places", "offers", "things", "bag", "parcels", "jobs", "goods", "wants")}


def reading(kind="attempt", check="Deception", **rest):
    return {"front": {"kind": kind, "check": check, **rest}}


class TheReadingNamesTheCheck(unittest.TestCase):
    def test_the_schema_asks_for_one_of_the_open_checks(self):
        schema = front_proposal.schema(LISTED)
        self.assertEqual(schema["properties"]["check"]["enum"], [*front_proposal.CHECKS, front_proposal.NONE])
        self.assertIn("check", schema["required"])
        self.assertEqual(front_proposal.CHECKS, ("Intimidation", "Deception", "Persuasion", "Insight"))
        for skill in front_proposal.CHECKS:
            self.assertIn(skill, game.SKILLS)
        self.assertIn("check:", front_proposal.guidance(LISTED))

    def test_a_present_try_of_an_open_kind_keeps_its_check(self):
        for kind in ("attempt", "speak_to", "unclear", "grab"):
            for skill in front_proposal.CHECKS:
                with self.subTest(kind=kind, skill=skill):
                    self.assertEqual(front_proposal.check_in(reading(kind, skill), "muhafızı kandırıyorum"), skill)

    def test_no_check_for_a_question_another_kind_or_a_closed_skill(self):
        cases = (
            (reading(), "muhafızı kandırabilir miyim?"),
            (reading(), "muhafızı kandırsam mı"),
            (reading("look"), "muhafıza bakıyorum"),
            (reading("go_to"), "kapıya gidiyorum"),
            (reading("offer_answer"), "tamam"),
            (reading("attempt", "Stealth"), "fark edilmeden geçmeye çalışıyorum"),
            (reading("attempt", "Athletics"), "duvara tırmanmaya çalışıyorum"),
            (reading("attempt", "none"), "muhafızı kandırıyorum"),
            (reading("attempt", None), "muhafızı kandırıyorum"),
            ({"front": "x"}, "muhafızı kandırıyorum"),
            ({}, "muhafızı kandırıyorum"),
            (None, "muhafızı kandırıyorum"),
            (reading(), None),
            # the real local model named a check for these (2026-11-15 live run); not a try this turn
            (reading("attempt", "Deception"), "yarın muhafızı kandıracağım"),
            (reading("attempt", "Sleight of Hand"), "kesesini almaya çalışıyorum"),
            (reading("attempt", "Deception"), "dün muhafızı kandırmaya çalıştım"),
            (reading("attempt", "Deception"), "muhafızı kandırmıyorum"),
            (reading("attempt", "Intimidation"), "keşke onu korkutabilsem"),
        )
        for reply, line in cases:
            with self.subTest(reply=reply, line=line):
                self.assertEqual(front_proposal.check_in(reply, line), "")


class TheEngineRollsTheReadingsCheck(unittest.TestCase):
    def setUp(self):
        self.session = game._session()
        self.saved = getattr(self.session, "_front_check", None)

    def tearDown(self):
        self.session._front_check = self.saved

    def test_a_social_check_from_the_reading_is_a_medium_check(self):
        for skill in ("Intimidation", "Deception", "Persuasion", "Insight"):
            with self.subTest(skill=skill):
                self.session._front_check = skill
                self.assertEqual(game.deterministic_check_for_action("muhafıza dik dik bakıp sesimi alçaltıyorum"),
                                 {"action_type": "check", "skill": skill, "difficulty": "medium"})

    def test_the_readings_skill_wins_over_a_word_list_guess(self):
        self.session._front_check = "Insight"  # D-175: the word list says Deception for spotting a lie
        self.assertEqual(game.deterministic_check_for_action(
            "muhafızın yalan söyleyip söylemediğini anlamaya çalışıyorum")["skill"], "Insight")

    def test_a_named_skill_and_the_words_still_decide_without_a_reading(self):
        self.session._front_check = ""
        self.assertEqual(game.deterministic_check_for_action("muhafıza dik dik bakıp sesimi alçaltıyorum"), None)
        self.session._front_check = "Deception"
        self.assertEqual(game.deterministic_check_for_action("ikna zarı atıyorum")["skill"], "Persuasion")

    def test_the_readings_social_skill_never_overrides_a_world_check(self):
        self.session._front_check = "Persuasion"  # R-4: a climb or a hide keeps its own skill
        for line, skill in (("duvara tırmanmaya çalışıyorum", None), ("gölgelere saklanmaya çalışıyorum", None)):
            with self.subTest(line=line):
                self.session._front_check = ""
                skill = (game.deterministic_check_for_action(line) or {}).get("skill")
                self.session._front_check = "Persuasion"
                self.assertEqual((game.deterministic_check_for_action(line) or {}).get("skill"), skill)
                self.assertNotEqual(skill, "Persuasion")

    def test_the_check_does_not_outlive_its_turn(self):
        self.session._front_check = "Intimidation"
        front_proposal.end(self.session)
        self.assertEqual(self.session._front_check, "")

    def test_a_pickpocket_is_no_plain_check(self):
        self.session._front_check = "Sleight of Hand"  # the theft route owns it, with the coin
        self.assertIsNone(game.deterministic_check_for_action("muhafıza dik dik bakıp sesimi alçaltıyorum"))


class ASocialCheckIsAnActNotAStockAnswer(unittest.TestCase):
    def test_a_social_check_read_as_an_act_is_no_speech(self):
        for kind in ("attempt", "unclear", "grab"):
            session = SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos, _front_check="Deception",
                                      _front_kind=kind)
            with self.subTest(kind=kind):
                self.assertTrue(bold_acts.is_act_not_talk(session, "muhafızı kandırmaya çalışıyorum"))
        session = SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos, _front_check="Deception",
                                  _front_kind="speak_to")
        self.assertFalse(bold_acts.is_act_not_talk(session, "muhafıza yalan söylüyorum"))


class TheReadingsCheckNeverMovesCoin(unittest.TestCase):
    """R-7: Sleight of Hand is also hiding, palming, putting and giving back; a reading's check is never a theft. A
    pickpocket is the reading's own deed=steal (the live local model gave it on every steal line) or the engine's words."""

    def session(self, check="Sleight of Hand", kind="attempt"):
        return SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos, _front_check=check,
                               _front_kind=kind)

    def test_a_sleight_of_hand_reading_without_a_deed_is_no_theft(self):
        for line in ("kesesini almaya çalışıyorum", "muhafızın cebinden anahtarı aşırıyorum",
                     "Hançeri kınından sessizce çekiyorum", "Anahtarı kilitten yavaşça çekiyorum",
                     "Düşürdüğü kesesini yerden alıyorum ve ona geri veriyorum", "Kesesine gizlice bir bakır koyuyorum",
                     "Cebimdeki zarı avucumda gizlice değiştiriyorum", "Bıçağımı kolumun içine gizliyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(self.session(), line, ""))

    def test_every_line_that_is_no_try_stays_no_theft_whatever_the_reading_said(self):
        for line in NOT_TRIES + ("dün kesesini aldım", "“Keseni alıyorum” diyorum", "kesesini almıyorum",
                                 "dün muhafızın kesesini çalmaya çalıştım"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(self.session(), line, ""))

    def test_the_engines_own_open_tries_stay_thefts(self):
        for line in TRIES:
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(self.session(), line, ""))


class TheReadingsStealDeed(unittest.TestCase):
    def session(self, kind="attempt"):
        return SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos, _front_check="", _front_kind=kind)

    def test_a_present_steal_the_reading_found_is_a_theft(self):
        for line in ("kesesini almaya çalışıyorum", "muhafızın cebinden anahtarı aşırıyorum", "kesesini çalıyorum",
                     "kesesini aşırayım", "kesesini kapıp kaçıyorum", "muhafızın cebini yokluyorum",
                     "Kavşim arkasını dönünce kesesini çalıyorum", "kesesini çalıyorum, tamam",
                     "yaklaşıp sonra kesesini çalıyorum"):
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(self.session(), line, "steal"))

    def test_a_wish_speech_change_of_mind_past_or_giving_back_is_no_theft(self):
        for line in ("Kesesini çalmak istiyorum", "“Kesesini çalıyorum” diyorum", "Kesesini çalmaktan vazgeçiyorum",
                     "Kesesini çalmayı düşünüyorum", "Eğer bakmazsa kesesini çalarım", "Kesesini çalmam",
                     "Belki kesesini çalarım", "Rüyamda kesesini çalıyorum", "Kesesini çalıyormuş gibi yapıyorum",
                     "dün muhafızın kesesini çalmaya çalıştım", "kesesini çaldım", "kesesini çalmıyorum",
                     "kesesini çalmaya çalışmıyorum", "Muhafız: kesesini çalıyorum",
                     "Düşürdüğü kesesini yerden alıyorum ve ona geri veriyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(self.session(), line, "steal"))
        self.assertFalse(bold_acts._steals(self.session(kind="speak_to"), "kesesini çalıyorum", "steal"))
        self.assertFalse(bold_acts._steals(self.session(), "kesesini alsam mı?", "steal"))
        self.assertFalse(bold_acts._steals(self.session(), "kesesini çalıyorum", "burn"))

if __name__ == "__main__":
    unittest.main()

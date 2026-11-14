"""D-094 general fix: the front reading may name the check a risky try needs; the engine validates it, sets the DC and
rolls (Q17 "the engine referees, the model writes", ZAR_KURALLARI 2.2: roll only for a real, present try).

Only the skills whose outcome needs no world precondition are open to the reading: Sleight of Hand (a pickpocket, through
the engine's own theft route, which alone moves coin), Intimidation, Deception, Persuasion, Insight. A question, a
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
        self.assertEqual(front_proposal.CHECKS,
                         ("Sleight of Hand", "Intimidation", "Deception", "Persuasion", "Insight"))
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
            (reading("attempt", "Sleight of Hand"), "dün muhafızın kesesini çalmaya çalıştım"),
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


class TheReadingsPickpocketGoesThroughTheft(unittest.TestCase):
    def session(self, check="Sleight of Hand", kind="attempt"):
        return SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos, _front_check=check,
                               _front_kind=kind)

    def test_a_pickpocket_check_is_a_theft_when_no_deed_was_read(self):
        self.assertTrue(bold_acts._steals(self.session(), "kesesini almaya çalışıyorum", ""))

    def test_every_line_that_is_no_try_stays_no_theft_whatever_the_reading_said(self):
        for line in NOT_TRIES + ("dün kesesini aldım", "“Keseni alıyorum” diyorum", "kesesini almıyorum",
                                 "dün muhafızın kesesini çalmaya çalıştım"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(self.session(), line, ""))

    def test_ones_own_things_or_giving_is_no_theft_whatever_the_reading_said(self):
        for line in ("Cebimdeki zarı avucumda gizlice değiştiriyorum", "Kesesine gizlice bir bakır koyuyorum",
                     "Bıçağımı kolumun içine gizliyorum", "Kesesini ona geri veriyorum", "Anahtarı ona geri veriyorum",
                     "Cebine sahte mektubu gizlice yerleştiriyorum", "Kesemdeki altınları sayıyorum",
                     "Anahtarımı kilide sokuyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(self.session(), line, ""))

    def test_a_read_pickpocket_takes_something_of_someone(self):
        for line in ("muhafızın cebinden anahtarı aşırıyorum", "muhafızın cebini boşaltmaya çalışıyorum",
                     "muhafızın kesesini almayı deniyorum", "keseyi kemerinden çekmeye çalışıyorum"):
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(self.session(), line, ""))

    def test_a_read_steal_deed_on_a_wish_speech_or_change_of_mind_is_no_theft(self):
        for line in ("Kesesini çalmak istiyorum", "“Kesesini çalıyorum” diyorum", "Kesesini çalmaktan vazgeçiyorum",
                     "Kesesini çalmayı düşünüyorum", "Eğer bakmazsa kesesini çalarım", "Kesesini çalmam",
                     "Belki kesesini çalarım", "Rüyamda kesesini çalıyorum", "Kesesini çalıyormuş gibi yapıyorum",
                     "Kesesini çalmadan önce etrafa bakıyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(self.session(check=""), line, "steal"))
        self.assertFalse(bold_acts._steals(self.session(check="", kind="speak_to"), "kesesini çalıyorum", "steal"))
        for line in ("kesesini aşırayım", "kesesini kapıp kaçıyorum", "muhafızın cebini yokluyorum"):
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(self.session(check=""), line, "steal"))

    def test_a_read_steal_deed_on_a_past_or_refused_line_is_no_theft(self):
        for line in ("dün muhafızın kesesini çalmaya çalıştım", "kesesini çaldım", "kesesini çalmıyorum",
                     "kesesini çalmaya çalışmıyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(self.session(check=""), line, "steal"))
        self.assertTrue(bold_acts._steals(self.session(check=""), "kesesini çalıyorum", "steal"))

    def test_the_open_tries_are_still_thefts_with_the_reading(self):
        for line in TRIES + ("kesesini almaya çalışıyorum", "muhafızın kesesini gizlice almaya çalışıyorum"):
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(self.session(), line, ""))

    def test_no_theft_for_speech_a_question_another_check_or_a_read_deed(self):
        self.assertFalse(bold_acts._steals(self.session(kind="speak_to"), "kesesini almaya çalışıyorum", ""))
        self.assertFalse(bold_acts._steals(self.session(), "kesesini alsam mı?", ""))
        self.assertFalse(bold_acts._steals(self.session(check="Deception"), "kesesini almaya çalışıyorum", ""))
        self.assertFalse(bold_acts._steals(self.session(check=""), "kesesini almaya çalışıyorum", ""))
        self.assertFalse(bold_acts._steals(self.session(), "kesesini almaya çalışıyorum", "burn"))
        self.assertFalse(bold_acts._steals(self.session(), "muhafızın gırtlağını kesip kesesini alıyorum", ""))


if __name__ == "__main__":
    unittest.main()

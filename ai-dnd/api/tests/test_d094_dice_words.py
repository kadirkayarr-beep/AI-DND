"""D-094, D-099, D-098: the engine rolls for a steal or a scare whatever the model's reading says (Q17, refined by
ZAR_KURALLARI 2.2: a roll only for a real, present, first-person try; a question, a refusal, a past or reported line,
a quoted one and somebody else's act roll nothing).

The turn route is pinned by journeys 50 and 50b; here the word rules are pinned, hits and false positives side by side
(the false-positive list is the independent review's, 2026-11-14).
"""

from __future__ import annotations

import unittest

import bold_acts
import game


class _Words:
    """What bold_acts needs of a session to fold a line."""

    def _normalize_turkish_typos(self, text):
        return game._normalize_turkish_typos(text)


SESSION = _Words()

TRIES = (
    "kesesini fark ettirmeden çalmak için zar atıyorum", "muhafızın kesesini çalmaya çalışıyorum",
    "muhafızın kesesini çalmayı deniyorum", "KESESİNİ ÇALMAK İÇİN ZAR ATIYORUM.", "parasını çalmak için zar atıyorum",
    "muhafızın yanına yaklaşıp kesesini çalmak için zar atıyorum", "kesesini çalmak için yaklaşıyorum", "yüzüğünü çalmaya çalışıyorum", "bıçağını çalmaya çalışıyorum",
    "kapının yanındaki muhafızın kesesini çalmak için yaklaşıyorum", "davulcunun kesesini çalmak için yaklaşıyorum",
    "zilin yanındaki keseyi çalmak için elimi uzatıyorum",
)
NOT_TRIES = (
    # past, future, reported, somebody else's act, a plan, a refusal
    "dün kesesini çalmaya çalıştım ama yakalandım", "kesesini çalmaya çalışacağım",
    "kesesini çalmaya çalışırken yakalandım", "muhafıza “kesesini çalmak için geldim” diyorum",
    "adam kesemi çalmak için elini uzatıyor, onu itiyorum", "kesesini çalmak istiyorum ama vazgeçiyorum",
    "kesemi çalmaya çalışan hırsızı yakalıyorum", "kesesini çalmak için gelmedim",
    "kesesini çalmak için değil, bakmak için yaklaşıyorum", "kesesini çalmak için bir plan düşünüyorum",
    "kesesini çalmaya çalışmıyorum", "kesesini çalmak istemiyorum",
    # an attack with the wish tacked on
    "kılıcımla muhafıza saldırıyorum, kesesini çalmak için",
    # not theft at all: music, a whistle, a bell, a heart, a door
    "ıslık çalmak için dudaklarımı büzüyorum", "ıslık çalmaya çalışıyorum", "gitar çalmaya çalışıyorum",
    "bağlama çalmak istiyorum", "kaval çalmak için çıkarıyorum", "boruyu çalmak için kaldırıyorum",
    "alarm çalmak için koşuyorum", "onun kalbini çalmak istiyorum", "dikkatini çalmak için öksürüyorum",
    "kapıyı çalmak için yaklaşıyorum", "zili çalmak için uzanıyorum", "kapıyı çalıyorum", "davul çalmak istiyorum",
    # round-2 review: wishes, plans, conditions, speech, somebody else's purse, music for money, attack plus wish
    "kesesini çalmak istiyorum", "yarın kesesini çalmak istiyorum", "muhafız uyuyunca kesesini çalmak istiyorum",
    "kesesini çalmak için değil konuşmak için zar atıyorum", "kesemi çalmak istiyorum",
    "eğer bakmazsa kesesini çalmak için zar atıyorum", "arkadaşım kesesini çalmak için zar atıyorum",
    "ben olsam kesesini çalmak için zar atıyorum", "muhafıza diyorum ki kesesini çalmak için zar atıyorum",
    "para kazanmak için bağlama çalmak istiyorum", "altın çanı çalmaya çalışıyorum", "bakır çanı çalmak istiyorum",
    "kitaptaki notaları çalmaya çalışıyorum", "muhafıza saldırıyorum çünkü kesesini çalmak istiyorum",
    "kılıcımı çekip muhafıza saldırıyorum, kesesini çalmak için zar atıyorum",
    "muhafızı öldürüyorum, sonra kesesini çalmak istiyorum",
    # round-3 review: a blow first, a wish or a dream, somebody's "Name:" line, a front ("cephe")
    "Muhafızın gırtlağını kesip kesesini çalmaya çalışıyorum", "Muhafızın boğazını kesip kesesini çalmak için zar atıyorum",
    "Muhafızı hançerleyip kesesini çalmaya çalışıyorum", "Muhafızı boğazlayıp kesesini çalmaya çalışıyorum",
    "Muhafızı tekmeleyip kesesini çalmaya çalışıyorum", "Muhafızı yumruklayıp kesesini çalmaya çalışıyorum",
    "Hançerimi muhafızın böğrüne saplayıp kesesini çalmaya çalışıyorum", "Muhafızı deşip kesesini çalmaya çalışıyorum",
    "Keşke kesesini çalmaya çalışıyorum", "Belki kesesini çalmaya çalışıyorum", "Rüyamda kesesini çalmaya çalışıyorum",
    "Muhafız: kesesini çalmaya çalışıyorum", "Cepheye gidip borazanı çalmaya çalışıyorum",
    # round-4 review: a deed first (-ip/-arak), a supposition
    "Muhafızı boğup kesesini çalmaya çalışıyorum", "Muhafızı yere serip kesesini çalmaya çalışıyorum",
    "Diyelim ki kesesini çalmaya çalışıyorum", "Farz et ki kesesini çalmaya çalışıyorum",
    "Varsayalım kesesini çalmak için zar atıyorum",
    # a question
    "kesesini çalmak için zar atsam mı?", "kesesini çalmak için zar atsam mı",
)


class OpenTryToSteal(unittest.TestCase):
    def test_a_present_first_person_try_is_theft_by_the_words(self):
        for line in TRIES:
            with self.subTest(line=line):
                self.assertTrue(bold_acts.is_theft(SESSION, line))

    def test_a_found_deed_of_none_still_lets_an_open_try_roll(self):
        for line in TRIES:
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(SESSION, line, ""))

    def test_every_other_line_rolls_nothing_whatever_the_reading_said(self):
        for line in NOT_TRIES:
            with self.subTest(line=line):
                self.assertFalse(bold_acts.is_theft(SESSION, line))
                self.assertFalse(bold_acts._steals(SESSION, line, ""))

    def test_the_readings_own_steal_is_not_blocked_by_a_door_or_a_bell_nearby(self):
        for line in ("kapının yanındaki muhafızın kesesini çalmak için yaklaşıyorum",
                     "kapıdaki adamın kesesini çalmaya çalışıyorum", "zilin yanındaki keseyi çalmak için uzanıyorum"):
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(SESSION, line, "steal"))

    def test_words_said_to_somebody_are_no_pickpocket_when_the_reading_heard_speech(self):
        class Heard(_Words):
            _front_kind = "speak_to"

        line = "kesesini çalmak için zar atıyorum"
        self.assertTrue(bold_acts._steals(SESSION, line, ""))
        self.assertFalse(bold_acts._steals(Heard(), line, ""))
        self.assertTrue(bold_acts._steals(Heard(), line, "steal"))

    def test_the_reading_still_owns_the_old_word_lines(self):
        for line in ("kesesini çaldım", "kesesini çalacağım", "kesesini çalıyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(SESSION, line, ""))
        self.assertTrue(bold_acts._steals(SESSION, "kesesini çalıyorum", "steal"))
        self.assertFalse(bold_acts._steals(SESSION, "kesesini çalmaya çalışıyorum", "burn"))
        self.assertFalse(bold_acts._steals(SESSION, "kesesini çalmaya çalışıyorum", "yield"))
        self.assertFalse(bold_acts._steals(SESSION, "kapıyı çalıyorum", "steal"))

    def test_the_old_theft_words_are_unchanged(self):
        for line in ("kesesini çalıyorum", "kesesini çalıp kaçıyorum", "kesesini yürütüyorum", "kesesini aşırıyorum"):
            with self.subTest(line=line):
                self.assertTrue(bold_acts.is_theft(SESSION, line))
        for line in ("zili çalıyorum", "kapıyı çalıp giriyorum", "flüt çalıyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts.is_theft(SESSION, line))


class ScareIsACheck(unittest.TestCase):
    def skill_of(self, line):
        return (game.deterministic_check_for_action(line) or {}).get("skill")

    def test_a_present_first_person_scare_is_intimidation(self):
        for line in ("muhafızı korkutmaya çalışıyorum", "muhafızı korkutmak için zar atıyorum",
                     "tüccara gözdağı vermeye çalışıyorum", "tüccarı tehdit etmeye çalışıyorum",
                     "Muhafızı korkutmaya çalışıyorum."):
            with self.subTest(line=line):
                self.assertEqual(self.skill_of(line), "Intimidation")

    def test_past_reported_quoted_and_somebody_elses_scare_is_no_check(self):
        for line in ("muhafızı korkutmaya çalışmıyorum", "karanlıktan korkuyorum", "muhafızı korkutsam mı?",
                     "muhafızı korkutmaya çalışmalı mıyım?", "dün muhafızı korkutmaya çalıştım",
                     "muhafıza “seni korkutacağım” diyorum", "adam beni korkutmaya çalışıyor",
                     "beni korkutmaya çalışan adama bakıyorum", "kimseyi korkutmak istiyorum demedim",
                     "onu korkutuyorum mu", "seni korkutmaya çalışıyorum",
                     "Kaptan, seni korkutmaya çalışıyorum", "Muhafız: seni korkutmaya çalışıyorum",
                     "Belki muhafızı korkutmaya çalışıyorum", "Rüyamda muhafızı korkutmaya çalışıyorum",
                     "Atı korkutmaya çalışıyorum", "Diyelim ki muhafızı korkutmaya çalışıyorum",
                     "Muhafızı bıçaklayarak korkutmaya çalışıyorum", "muhafıza diyorum ki seni korkutmaya çalışıyorum",
                     "özür dilerim, seni korkutmaya çalışıyorum",
                     "yarın muhafızı korkutmaya çalışıyorum", "kuşları korkutuyorum"):
            with self.subTest(line=line):
                self.assertNotEqual(self.skill_of(line), "Intimidation")


class LookingAPersonOver(unittest.TestCase):
    def test_looking_someone_over_is_an_act_not_speech(self):
        for line in ("muhafızın üstünü inceliyorum", "muhafızın zırhını kontrol ediyorum",
                     "adamın kıyafetlerini süzüyorum", "Muhafızın üstünü inceliyorum.",
                     "muhafızın üstünü dikkatle inceliyorum"):
            with self.subTest(line=line):
                self.assertTrue(bold_acts.looks_person_over(SESSION, line))
                self.assertTrue(bold_acts.is_act_not_talk(SESSION, line))

    def test_speech_questions_and_quotes_stay_speech(self):
        for line in ("muhafıza “üstünü inceliyorum” diyorum", "muhafızın üstünü inceleyebilir miyim?", "merhaba muhafız",
                     "muhafıza üstünü kontrol etmesini söylüyorum", "muhafıza zırhını inceleyebilir miyim diye soruyorum",
                     "silahını kontrol et dedim", "muhafızın üstünü inceleyeceğim",
                     "masanın üstünü inceliyorum", "cesedin üstünü inceliyorum", "tezgahtaki kılıcın üzerini inceliyorum"):
            with self.subTest(line=line):
                self.assertFalse(bold_acts.looks_person_over(SESSION, line))
                self.assertFalse(bold_acts.is_act_not_talk(SESSION, line))


if __name__ == "__main__":
    unittest.main()

"""D-224 (Kadir playtest 2026-11-15): "Muhafızın kesesi var mı diye inceliyorum." was read deed=steal and 7 copper
moved. A line that only looks (incele, bak, kontrol et, süz, gözden geçir) and names no taking is no theft, whatever
the reading says. Narrow on purpose: D-177's wider guard waits for a real-model measurement, and every real theft
(RealTheftsStillCount, journey 51b) must stay a theft.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import bold_acts
import game
from api.tests.test_d094_model_check import RealTheftsStillCount


def session():
    return SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos, _front_check="",
                           _front_kind="bag")


LOOKS = (
    "Muhafızın kesesi var mı diye inceliyorum.",
    "Muhafızın kesesine bakıyorum",
    "Adamın kesesini kontrol ediyorum",
    "Kadının kesesini dikkatle süzüyorum",
    "Muhafızın cebini gözden geçiriyorum",
    "Kesesine şöyle bir göz atıyorum",
    # review 2026-11-16: words that only begin like a take verb ("altın", "çalışıyorum", "kapıdaki", "dalgın")
    "Kesesini incelemeye çalışıyorum",
    "Muhafızın kesesinde altın var mı diye inceliyorum",
    "Kapıdaki muhafızın kesesine bakıyorum",
    "Dalgın muhafızın kesesine bakıyorum",
    "Sokaktaki adamın kesesini süzüyorum",
    "Çekmecenin üstündeki keseyi inceliyorum",
)

# Re-review 2026-11-16 (probe224, probe224b): lines that only look, never a theft unasked. With a look word they are
# asked (``_looks_before_stealing``); a yes plays the theft, so a missed word costs one question, never coin.
MORE_LOOKS = (
    "Muhafızın üstünde sakladığı bir kese var mı diye bakıyorum", "Muhafızın kesesi var mı diye arıyorum",
    "Kesesine bir bakış atıyorum", "Kesesini gözlüyorum", "Kesesini izliyorum", "Kesesini dikkatle inceliyorum",
    "Muhafızın saklı cebine bakıyorum", "Yere uzanmış sarhoşun kesesini inceliyorum", "Kesesine bakıp çekip gidiyorum",
    "Kesesini kontrol ediyorum", "Cebime bakıyorum",
    "Kesesine kesik bir bakış atıyorum", "Kesesine kesik kesik bakıyorum", "Alnındaki yara izine ve kesesine bakıyorum",
    "Kapalı keseye bakıyorum", "Çarşıdaki adamın kesesine bakıyorum", "Sakladığı bir şey var mı diye bakıyorum",
    "Saklı bir kese var mı diye inceliyorum", "Alçak sesle konuşan adamın kesesine bakıyorum", "Kalabalığa bakıyorum",
    "Çalgıcının kesesine bakıyorum", "Kapkara cüppesini inceliyorum", "Çekingen adamın kesesini süzüyorum",
    "Dalgalı saçlı adamın kesesine bakıyorum", "Sokulgan adamın kesesine bakıyorum",
    "Kesik kulaklı muhafızın kesesine bakıyorum", "Uzanmış yatan sarhoşun kesesine bakıyorum",
    "Yoklama listesini inceliyorum", "Uzaktaki adamın kesesine bakıyorum", "Çarpık burunlu adamın kesesine bakıyorum",
    "Alacakaranlıkta kesesine bakıyorum", "Alımlı kadının kesesine bakıyorum", "Kapüşonlu adamın kesesine bakıyorum",
    "Çalıntı olup olmadığına bakıyorum", "Kesesine uzanan eli inceliyorum",
    "Kesesini aldığını gördüğüm adama bakıyorum", "Adamın aldığı keseyi inceliyorum", "Kesesine almadan bakıyorum",
    "Kesesine dokunmadan bakıyorum", "Kesesini almayı düşünmeden inceliyorum", "Kesesini çalmadan önce bakıyorum",
    "Altın kesesine bakıyorum", "Elinde kesesi var mı bakıyorum", "Kesesinin ağzı açık mı kontrol ediyorum",
    "Masaya uzanmış adamın kesesine bakıyorum", "Kesesine göz atıyorum, sonra kapıya bakıyorum",
    "Sakallı adamın kesesine bakıyorum", "Kesesine bakıyorum ama almıyorum", "Kesesini almıyorum, sadece bakıyorum",
    "Çalmıyorum, yalnızca bakıyorum", "Kesesine bakarak yürüyorum", "Kesesini inceleyip geri çekiliyorum",
    "Kesesine bakıp geri çekiliyorum", "Kesesine bakıp kapıya yürüyorum", "Kesesine bakıp kaçıyorum",
    "Kesesine bakıp sokağa çıkıyorum", "Kesesine bakıp uzaklaşıyorum", "Kesesine bakıp alçak sesle konuşuyorum",
    "Kesesine bakıp kesesini övüyorum",
    # third review: looks that fell to the plain theft question
    "Kesesinin ağırlığını tartıyorum", "Kesesini gözetliyorum", "Kesesini kolluyorum", "Kesesine bakarken alay ediyorum",
)
# Plain looks among them: these are asked, not dropped (the others say no, later or never and are not asked)
ASKED_LOOKS = (
    "Muhafızın kesesi var mı diye arıyorum", "Kesesine bir bakış atıyorum", "Kesesini gözlüyorum",
    "Kesesini izliyorum", "Muhafızın saklı cebine bakıyorum", "Yere uzanmış sarhoşun kesesini inceliyorum",
    "Kesesine bakıp çekip gidiyorum", "Cebime bakıyorum",
    "Kesesinin ağırlığını tartıyorum", "Kesesini gözetliyorum", "Kesesini kolluyorum", "Kesesine bakarken alay ediyorum",
)

TAKES = (
    "kesesini almaya çalışıyorum",  # journey 51b
    "Kesesine bakıp çalıyorum",
    "Kesesini inceleyip aşırıyorum",
    "Kimse bakmazken kesesini alıyorum",
    "Muhafız başka yere bakarken kesesini kapıyorum",
    "Kesesini kontrol edip cebime indiriyorum",
    "Kesesini yokluyorum",
    "Parmaklarımı keseye daldırıyorum",
    # review 2026-11-16: look first, then take with a word the first guard missed
    "Etrafa bakıp kesesini götürüyorum",
    "Muhafıza bakarak kesesini hafifletiyorum",
    "Kesesine bakıp çarpıyorum",
    "Kesesine bakıp koparıyorum",
    "Kontrol edip kesesini cebe atıyorum",
    "Bakıp kesesini tırtıklıyorum",
    "Kesesine bakıp elimi atıyorum",
    "Kesesini inceleyip alıyorum",
    "Kesesine bakıp çekip alıyorum",
    # re-review 2026-11-16: taking words, dialect and the "-ıver" form
    "Bakıp kesesini alıveriyorum", "Bakıp kesesini çalıveriyorum", "Bakıp kesesini kaldırıyorum",
    "Bakıp kesesine el koyuyorum", "Bakıp kesesini ele geçiriyorum", "Bakıp keseyi yakalıyorum",
    "Bakıp keseyi kavrıyorum", "Bakıp keseyi avuçluyorum", "Bakıp keseyi gizlice çözüyorum",
    "Bakarak kesesini alıyom", "Bakıp kesesini kapıyom", "Bakıp kesesini cebime koyuyorum",
    "Bakıp kesesini cebime saklıyorum", "Kesesine bakıp çekiyorum", "Bakıp kesesini sıyırıyorum",
)

# The rest of probe224's takes (the past "aşırdım"/"aldım", the later "alacağım" and the habit "alırım" are no theft
# this turn and stay out): each is a theft, plainly or after the asked question
ASKED_TAKES = (
    "Bakıp kesesini alıyorum", "Kesesine bakıp alıyorum", "İnceleyip aşırıyorum", "Göz atıp yürütüyorum",
    "Kontrol edip cebime indiriyorum", "Bakıp kesesini kapıyorum", "Bakıp kesesini çalıyorum", "Bakıp kesesini kesiyorum",
    "Kesesine bakıp ipini kesip alıyorum", "Bakıp kesesini cebime sokuyorum", "Bakıp kesesini cebime atıyorum",
    "Bakıp kesesini kapıp kaçıyorum", "Kesesine bakıp yürütüveriyorum", "Bakıp kesesini cebe indiriyorum",
    "Bakıp kesesini mideye indiriyorum", "Bakıp kesesini kopartıyorum", "Bakıp kesesini kesip cebime koyuyorum",
    "Kesesini kontrol edip alıyorum", "Bakıp kesesini hırsızlıyorum", "Bakıp kesesini yokluyorum",
    "Kesesine bakıp kesesini çekiştiriyorum", "Bakıp kesesini alçaktan çekiyorum", "Bakıp keseyi tutup çekiyorum",
    "Bakıp keseyi koynuma sokuyorum", "Bakıp keseyi koluma takıyorum", "Bakıp kesesinin ipini çözüp alıyorum",
    "Bakıp keseyi ceketimin altına sokuşturuyorum", "Bakıp keseyi el çabukluğuyla alıyorum", "Bakıp keseyi alıp gidiyorum",
    "Bakıp kesesinden birkaç sikke alıyorum", "Bakıp kesesinden sikke çekiyorum", "Bakıp keseyi kesiyorum",
    "Bakıp keseyi aşırmaya çalışıyorum", "Bakıp keseyi almaya çalışıyorum", "Bakıp keseyi çalmaya çalışıyorum",
    "Bakıp keseyi kapmaya çalışıyorum",
)


class AnInspectionIsNoTheft(unittest.TestCase):
    def test_a_line_that_only_looks_is_no_steal_whatever_the_reading_says(self):
        for line in LOOKS:
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(session(), line, "steal"))

    def test_a_line_that_looks_and_takes_stays_a_steal(self):
        for line in TAKES:
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(session(), line, "steal"))

    def test_more_lines_that_only_look_are_never_a_theft_unasked(self):
        for line in MORE_LOOKS:
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(session(), line, "steal"))

    def test_a_plain_look_the_reading_calls_a_theft_is_asked(self):
        for line in (*LOOKS, *ASKED_LOOKS):
            with self.subTest(line=line):
                self.assertTrue(bold_acts._looks_before_stealing(session(), line, "steal"))
                self.assertFalse(bold_acts._looks_before_stealing(session(), line, ""))  # no reading: never asked

    def test_every_take_is_a_theft_plainly_or_once_asked(self):
        for line in (*TAKES, *ASKED_TAKES):
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(session(), line, "steal")
                                or bold_acts._looks_before_stealing(session(), line, "steal"))

    def test_the_real_theft_guard_lines_keep_their_steal_reading(self):
        # every guard line the reading's steal took before D-224 still takes it
        before = [line for line in RealTheftsStillCount.LINES if ":" not in line]
        for line in before:
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(session(), line, "steal"))


class TheAskedLook(unittest.TestCase):
    """The look the reading calls a theft is asked with its own question; nothing moves until a yes plays it."""

    LINE = "Muhafızın kesesi var mı diye inceliyorum."

    def setUp(self):
        from api.tests.test_species_traits import make_session
        self.session = make_session("Human")
        self.world = self.session.world_state
        self.guard = self.session.create_npc_from_ai({"name": "Kavşim", "role": "Muhafız",
                                                      "location": self.world["location"]})
        self.world["currency"][self.guard["id"]] = 7

    def test_a_look_is_asked_and_moves_nothing(self):
        import copy
        before = copy.deepcopy(self.world)
        asked = []
        reply = bold_acts.resolve(self.session, self.LINE, "steal", ask=lambda act: asked.append(act) or {"asked": act})
        self.assertEqual(asked, ["steal_look"])
        self.assertEqual(reply, {"asked": "steal_look"})
        self.assertEqual(self.world, before)

    def test_without_an_ask_a_look_is_no_theft(self):
        import copy
        before = copy.deepcopy(self.world)
        self.assertIsNone(bold_acts.resolve(self.session, self.LINE, "steal"))
        self.assertEqual(self.world, before)

    def test_the_question_says_it_is_a_look_first(self):
        line = game._ask_before_the_heavy({"what": "deed", "id": None, "deed": "steal_look", "said": "x"})["narration"]
        self.assertIn("çalmaya mı çalışıyorsun", line)
        self.assertIn("suç olarak kayda geçer", line)

    def resolve_after(self, confirmed, deed=""):
        """The line read again after the answer; the new reading (deed) is no theft."""
        from unittest.mock import patch
        self.session._heavy_confirmed = confirmed
        asked = []
        won = {"result": "BAŞARILI", "skill": "Sleight of Hand"}
        with patch.object(bold_acts, "_check", return_value=won), \
                patch.object(bold_acts, "_hand_to_whom", return_value=self.guard):
            reply = bold_acts.resolve(self.session, self.LINE, deed, ask=lambda act: asked.append(act))
        return reply, asked

    def test_a_yes_to_the_asked_look_takes_whatever_the_new_reading_says(self):
        # third review 2026-11-16: after "evet" the line is read again; a new reading that was no theft left the yes doing
        # nothing at all
        for deed in ("", None, "talk"):
            with self.subTest(deed=deed):
                self.setUp()
                wallets = self.world["currency"]
                player = wallets.get("player", 0)
                reply, asked = self.resolve_after({"said": self.LINE, "allowed": [["deed", None, "steal_look"]]}, deed)
                self.assertEqual(asked, ["steal_look"])
                self.assertIsNotNone(reply)
                taken = 7 - wallets[self.guard["id"]]
                self.assertGreater(taken, 0)  # the coin comes out of the guard's purse, none is made
                self.assertEqual(wallets["player"], player + taken)

    def test_a_stale_or_other_yes_takes_nothing(self):
        import copy
        for confirmed in (None, {"said": "başka bir satır", "allowed": [["deed", None, "steal_look"]]},
                          {"said": self.LINE, "allowed": [["deed", None, "steal"]]}, {"said": self.LINE, "allowed": 5},
                          "evet"):
            with self.subTest(confirmed=confirmed):
                self.setUp()
                before = copy.deepcopy(self.world)
                reply, asked = self.resolve_after(confirmed)
                self.assertIsNone(reply)
                self.assertEqual(asked, [])
                self.assertEqual(self.world, before)


if __name__ == "__main__":
    unittest.main()

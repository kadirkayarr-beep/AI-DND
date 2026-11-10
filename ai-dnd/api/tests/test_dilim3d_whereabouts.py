"""Dilim 3D Task 8: a person who is elsewhere is not seated "over there" (QA #150, #155)."""

from __future__ import annotations

import unittest

import npc_speech_boundary
from api.tests.test_quest_log import QuestLogCase
from api.tests.town_seed import fixed_town

Q155_SPEECH = ("“Organizatörlerden birini mi? Tuna masada oturuyor, onu bulamamak için bir sebep yok; "
               "ben gidip kimseyi zorla getiremem, ama parmağımla gösterebilirim.”")       # QA #155
TURN_SPEECH = "Organizatörlerden birini mi? Tuna masada oturuyor, onu bulamamak için bir sebep yok."
Q150_SPEECH = "“Gidip parmağımla göstereyim o zaman, bak şuradaki masada oturuyor işte.”"   # QA #150 (no name)


class Whereabouts(QuestLogCase):
    SEED = 4571

    async def asyncSetUp(self):
        await super().asyncSetUp()
        world = await self.world_with_town_errand()
        self.tuna_npc = self.recipient(world)
        self.tuna_npc["name_known_to_player"] = True      # a name the player has not heard is cut by an older filter
        self.here = self.giver(world).get("location") or world["location"]
        self.tuna_npc["location"] = next(p for p in world["locations"] if p != self.here)


class FalsePresence(Whereabouts):
    def cut(self, text):
        return npc_speech_boundary.without_false_presence(self.world, text, self.here)

    async def test_155_sentence_is_cut_when_the_contact_is_elsewhere(self):
        out = self.cut(Q155_SPEECH)
        self.assertNotIn("Tuna masada oturuyor", out)
        self.assertIn("parmağımla gösterebilirim", out)

    async def test_unchanged_when_the_contact_is_here(self):
        self.tuna_npc["location"] = self.here
        self.assertEqual(self.cut(Q155_SPEECH), Q155_SPEECH)

    async def test_a_line_with_no_name_is_left_alone(self):
        self.assertEqual(self.cut(Q150_SPEECH), Q150_SPEECH)

    async def test_a_suffixed_name_is_caught(self):
        self.assertNotIn("Tuna'yı", self.cut("“Tuna'yı köşedeki masada görürsün. Ben işime bakayım.”"))

    async def test_a_name_without_a_here_word_stays(self):
        line = "“Tuna iskelede çalışır.”"
        self.assertEqual(self.cut(line), line)

    async def test_all_sentences_cut_leaves_empty(self):
        self.assertEqual(self.cut("“Tuna şurada oturuyor.”"), "")


class FalseCutsStay(Whereabouts):
    """Fix round 1: truthful or unrelated sentences are not cut."""

    def stays(self, line):
        self.assertEqual(npc_speech_boundary.without_false_presence(self.world, line, self.here), line, line)

    async def test_buradan_is_not_burada(self):
        self.stays("“Tuna buradan ayrıldı.”")

    async def test_truthful_absence_stays(self):
        for line in ("“Tuna burada değil, değirmende oturuyor.”", "“Tuna'yı burada göremezsin.”",
                     "“Tuna gelmedi, burada kimse yok.”"):
            with self.subTest(line=line):
                self.stays(line)

    async def test_another_place_stays(self):
        place = self.world["locations"][self.tuna_npc["location"]]["name"]
        self.stays(f"“Tuna {place} yakınında bekliyor, oraya git.”")

    async def test_the_speakers_own_presence_stays(self):
        self.stays("“Tuna'ya söyle, burada bekliyorum.”")

    async def test_an_object_stays(self):
        self.stays("“Tuna'nın mektubu şurada duruyor.”")

    async def test_no_here_place_cuts_nothing(self):
        self.assertEqual(npc_speech_boundary.without_false_presence(self.world, Q155_SPEECH, None), Q155_SPEECH)


class FalsePresenceFixRound(Whereabouts):
    """Review 11 / Jarvis A8-A10, A12: the speaker's own presence, a comma between name and place, a place named
    in another clause, and two quoted sentences."""
    SEED = 4645

    def cut(self, line):
        return npc_speech_boundary.without_false_presence(self.world, line, self.here)

    async def test_waiting_for_the_person_here_is_the_speakers_own_presence(self):
        for line in ("“Tuna'yı burada bekliyorum.”", "“Tuna’yı burada bekliyorum.”", "Tuna'yı burada bekliyorum."):
            with self.subTest(line=line):
                self.assertEqual(self.cut(line), line)

    async def test_a_comma_between_the_name_and_the_here_word_still_cuts(self):
        self.assertEqual(self.cut("“Tuna, şurada oturuyor.”"), "")
        self.assertEqual(self.cut("“Tuna şurada oturuyor.”"), "")

    async def test_an_unrelated_place_name_later_does_not_exempt_the_claim(self):
        self.world["locations"][self.tuna_npc["location"]]["name"] = "Kırlangıç Hanı"
        out = self.cut("“Tuna burada bekliyor, Kırlangıç Hanı kapalı.”")
        self.assertNotIn("Tuna burada bekliyor", out)
        # the same place named in the person's own clause is still another place
        line = "“Tuna Kırlangıç Hanı yakınında bekliyor, oraya git.”"
        self.assertEqual(self.cut(line), line)

    async def test_two_quote_spans_cut_only_the_offending_sentence(self):
        self.assertIn("Ben işime bakıyorum", self.cut("“Tuna şurada oturuyor.” “Ben işime bakıyorum.”"))
        self.assertNotIn("Tuna", self.cut("“Tuna şurada oturuyor.” “Ben işime bakıyorum.”"))
        self.assertIn("Ben işime bakıyorum", self.cut("“Tuna şurada oturuyor.” Ben işime bakıyorum."))
        self.assertNotIn("Tuna", self.cut("“Tuna şurada oturuyor.” Ben işime bakıyorum."))


class WhereaboutsTurn(Whereabouts):      # seed 4571
    async def test_the_giver_does_not_seat_the_contact_here(self):
        reply = await self.say("Halil, bu iş için kime gideyim?", front={"kind": "speak_to", "person_id": "potter"},
                               spoken=TURN_SPEECH)
        self.assertIn("Organizatörlerden birini mi?", reply.json()["narration"])   # the rest of the speech reached the player
        self.assertNotIn("masada oturuyor", reply.json()["narration"])

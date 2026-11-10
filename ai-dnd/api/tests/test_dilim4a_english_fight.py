"""Dilim 4A Task 2: a fight started in English (QA #013-#016) is answered like the Turkish one.

The first line asks once ("kavga mı başlatıyorsun?"); an English yes (short, or leading a longer line that still
stands behind the blow) finishes it; an English refusal or a question starts nothing. Real app, scripted model.
"""

from __future__ import annotations

import unittest

from api.tests import test_front_proposal as proposal
from api.tests.town_seed import fixed_town

Q013 = "I shove the guard back with both hands, trying to push him five feet away without using a weapon."   # #013
Q014 = ("Yes, I am initiating combat with the guard. I want to shove him five feet, using the relevant D&D 2024 "
        "contest. Roll initiative and resolve my first turn.")                                              # #014
Q015 = "I attack the guard with my quarterstaff. I swing at his shoulder to knock him back. Roll initiative now."  # #015
Q016 = "Evet, muhafızla kavgayı başlatıyorum. İnisiyatif atıyorum, onunla savaşıyorum."                      # #016 (Türkçe)


class _Table(unittest.IsolatedAsyncioTestCase):
    first_seed = 4711
    # FrontTable's table without its own tests (each inherited test would run again here).
    asyncSetUp = proposal.FrontTable.asyncSetUp
    asyncTearDown = proposal.FrontTable.asyncTearDown
    campaign_with_npc = proposal.FrontTable.campaign_with_npc
    open_job = proposal.FrontTable.open_job
    line = proposal.FrontTable.line
    status = proposal.FrontTable.status
    offer = proposal.FrontTable.offer
    routes = proposal.FrontTable.routes

    async def begin(self):
        with fixed_town(self, self.first_seed):
            await proposal.FrontTable.begin(self)
        # the line says "guard": whoever of the town it reads as is what a person of the town really carries
        for person in self.world["npcs"]:
            person.update(armor_class=10, max_hp=12, current_hp=12)

    async def ask(self, line, *, owns=None):
        await self.begin()
        if owns:  # the player of #015 does carry the quarterstaff the line names
            self.world["inventory"].append(owns)
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
        return await self.line(line, "Ne yapıyorsun sen?")

    def assert_no_blow(self, reply):
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertFalse(self.world["combat"]["active"])


class EnglishFightStart(_Table):

    async def test_013_then_a_long_yes_starts_the_fight(self):
        self.assert_no_blow(await self.ask(Q013))
        reply = await self.line(Q014)
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertTrue(self.world["combat"]["active"])

    async def test_015_then_a_bare_yes_starts_the_fight(self):
        self.assert_no_blow(await self.ask(Q015, owns="Quarterstaff"))
        reply = await self.line("Yes")
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])

    async def test_a_punch_names_a_move_so_the_yes_lands_without_a_second_question(self):
        self.assert_no_blow(await self.ask("I punch the guard"))
        reply = await self.line("yes")
        self.assertEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_english_refusals_start_nothing(self):
        # one campaign, the question asked again before each answer (fixed_town seeds stay within 4711-4719)
        self.assert_no_blow(await self.ask(Q013))
        for answer in ("No, I don't attack him", "I'm not saying yes", "Yes? what do you mean", "never"):
            with self.subTest(answer=answer):
                self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
                self.assert_no_blow(await self.line(Q013, "Ne yapıyorsun sen?"))
                self.assert_no_blow(await self.line(answer))

    async def test_turkish_yes_unchanged(self):
        self.assert_no_blow(await self.ask("Muhafızı iki elimle itiyorum, silahsız beş adım geri."))
        reply = await self.line(Q016)
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])

    async def test_a_yes_with_no_question_asked_starts_nothing(self):
        await self.begin()
        self.assert_no_blow(await self.line("yes", "Evet mi?"))


class EnglishYesNeedsAMoveAtTheTarget(_Table):
    """Fix round 1: a long yes starts a fight only if the rest of the line names a move aimed at the proposed person."""
    first_seed = 4731

    async def test_long_yes_lines_that_name_no_move_at_him_start_nothing(self):
        self.assert_no_blow(await self.ask(Q013))
        for answer in ("Yes. I punch the wall in anger", "Yes, tell me about the guard",
                       "Sure, I'll kick the door open", "Yes, I trip on the stairs", "Yes, he hit me yesterday"):
            with self.subTest(answer=answer):
                self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
                self.assert_no_blow(await self.line(Q013, "Ne yapıyorsun sen?"))
                self.assert_no_blow(await self.line(answer))

    async def _starts(self, answer):
        self.assert_no_blow(await self.ask(Q013))
        reply = await self.line(answer)
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])

    async def test_a_punch_at_him_starts(self):
        await self._starts("Yes. I punch him.")

    async def test_a_kick_at_the_guard_starts(self):
        await self._starts("Sure, I kick the guard")

    async def test_a_mixed_yes_with_a_punch_at_him_starts(self):
        await self._starts("Evet, I punch him")

    async def test_yes_sir_starts(self):
        await self._starts("yes sir")

    async def test_english_move_words_keep_a_named_weapon_armed(self):
        import weapon_attack
        await self.begin()
        self.world["inventory"].append("Greatsword")
        for line in ("I swing my greatsword in a triple strike", "I swing my greatsword and strip his belt",
                     "I swing my greatsword, kicking up dust", "I swing my greatsword on a day trip",
                     "I swing my greatsword as he slaps it away"):
            with self.subTest(line=line):
                self.assertEqual(weapon_attack.natural_choice(self.session, line)[0], "greatsword")
        self.assertEqual(weapon_attack.natural_choice(self.session, "I kick the guard")[0], "unarmed")
        self.assertEqual(weapon_attack.natural_choice(self.session, "I punch the guard")[0], "unarmed")


class EnglishYesGuards(_Table):
    """Fix round 2: Turkish lines read as on base; English conditionals, threats, quotes and hold words start nothing."""
    first_seed = 4741

    def says(self, line):
        import combat_lifecycle
        return combat_lifecycle._says_yes(self.session, line, self.npc["id"])

    async def test_turkish_lines_with_ok_and_her_are_still_a_yes(self):
        await self.begin()
        for line in ("Evet, yayımı çekip ona bir ok atıyorum", "Evet, her şeyi göze alıp muhafızla kavgayı başlatıyorum.",
                     "Evet, muhafıza doğru bir ok atıyorum, kavgayı başlatıyorum"):
            with self.subTest(line=line):
                self.assertTrue(self.says(line))

    async def test_english_conditionals_threats_quotes_and_hold_words_are_no_yes(self):
        await self.begin()
        for line in ("Yes, I punch him if he comes any closer", "\"Yes, I'll punch him,\" I tell the guard",
                     "Yes, I'll punch him when he turns around", "Yes, unless he backs off I kick him",
                     "Yes, I threaten to punch him", "Yes, wait", "Yes, later", "Ok, stop", "Yes, hold on"):
            with self.subTest(line=line):
                self.assertFalse(self.says(line))

    async def test_the_qa_013_wording_with_without_still_starts(self):
        await self.begin()
        self.assertTrue(self.says("Yes, I shove him back without a weapon"))


class EnglishYesAllowlist(_Table):
    """Fix round 3: an English-led yes starts a fight only if the rest of the line is empty or only a known move and its
    person; any other word is no yes (the engine asks again). A Turkish line that begins with 'ok' is Turkish."""
    first_seed = 4751
    STARTS = ("Yes", "yes", "Do it", "Yep punch him", "Sure, I shove him", "Okay, I kick him", "Yes, I punch him",
              "Yes. I punch him.", "Sure, I kick the guard", "yes sir", "Yes, I shove him back without a weapon", Q014)
    NOT_YES = (
        "Yes, I punch him after he talks", "Yes, I punch him before he moves", "Yes, I punch him as soon as he turns",
        "Yes, I punch him whenever he looks away", "Yes, I will punch him in a moment",
        "Yes, I punch him provided he agrees", "Yes, in case he resists I punch him",
        "Yes, assuming he is armed I punch him", "Yes, supposing he draws I punch him",
        "Yes, I would punch him", "Yes, I might punch him", "Yes, probably punch him",
        "Yes, I want to maybe punch him", "Yes, I punch him, he said", "Yes, I punch him lol",
        "Yes, I punch him - kidding", "Yes, I punch him nope", "Yes, say I punch him", "yes. I hug him",
        "Yes, I hug him", "Yes, I leave", "Yes, I punch them all", "Yes, I punch everyone",
        "Yes, I punch him and then I hug him", "Yes, I punch the wall in anger", "Yes, tell me about the guard",
        "Yes, I trip on the stairs", "Yes, he hit me yesterday")
    TURKISH_OK = ("Ok atmıyorum", "Ok atmam", "Ok atmayacağım", "Ok atsam mı", "Ok atarsam ne olur", "Ok, dur",
                  "Ok, sonra bakarız", "Ok yok", "Ok bırakıyorum", "Ok atıyorum", "ok", "Ok")

    def says(self, line):
        import combat_lifecycle
        return combat_lifecycle._says_yes(self.session, line, "npc_private_sera")  # the town guard, "the guard" of the lines

    async def test_known_yes_lines_start(self):
        await self.begin()
        for line in self.STARTS:
            with self.subTest(line=line):
                self.assertTrue(self.says(line))

    async def test_any_other_word_is_no_yes(self):
        await self.begin()
        for line in self.NOT_YES:
            with self.subTest(line=line):
                self.assertFalse(self.says(line))

    async def test_a_turkish_line_that_begins_with_ok_is_read_as_on_base(self):
        await self.begin()
        for line in self.TURKISH_OK:
            with self.subTest(line=line):
                self.assertFalse(self.says(line))


if __name__ == "__main__":
    unittest.main()



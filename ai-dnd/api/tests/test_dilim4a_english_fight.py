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
                       "Sure, I'll kick the door open", "Yes, I trip on the stairs", "Yes, he hit me yesterday",
                       "Evet, tell me about the guard"):
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


if __name__ == "__main__":
    unittest.main()


"""What the player did stays done: real play lines from the long Carius check.

Each test posts the player's own Turkish through the HTTP turn with a mocked
model, so it proves what Python decides on its own.
"""

import game
from api.tests.test_three_plays import FIGHTER, PlayClient, ThreePlaysTests


class OwnWordsAndConfessions(ThreePlaysTests):
    async def scene(self, *people):
        await self.begin(FIGHTER)
        self.session._experimental_npc_dialogue_enabled = True  # as api.local_play runs it
        self.world["npcs"].clear()
        return [self.add_person(name, role) for name, role in people]

    def test_saying_it_again_is_not_a_claim_about_their_words(self):
        for line in ("paket bende mi şimdi çantama koyuyorum. tariq nerde dedim sana",
                     "ee kalila kol gücü lazım mı dedim, altın kazanacak iş var mı sende",
                     "iş var mı diyorum sana"):
            self.assertFalse(game.is_npc_historical_claim(line), line)

    def test_what_they_said_still_counts_as_a_claim(self):
        for line in ("sen bana dokuz bakır dedin", "bana söz verdin", "kalila öyle dedi", "adımı söyledim sana"):
            self.assertTrue(game.is_npc_historical_claim(line), line)

    async def test_a_repeated_question_gets_an_answer_not_a_denial(self):
        await self.scene(("Kalila", "Usta"))
        client = PlayClient(spoken="Sabret biraz, işim bitsin de söyleyeyim.")
        await self.say("selam kalila, iş var mı", client)
        out = await self.say("paket bende mi şimdi çantama koyuyorum. tariq nerde dedim sana", client)
        self.assertIn("Sabret biraz", out["narration"])
        self.assertNotEqual(out["turn_outcome"]["status"], "unverified")

    async def test_a_past_killing_said_to_someone_else_is_speech_not_an_attack(self):
        await self.scene(("Isolde", "Nöbetçi Çavuş"))
        self.world["npcs"].append(dict(self.world["npcs"][0], id="npc_kalila", name="Kalila", role="Usta",
                                       combat_status="dead", location="elsewhere"))
        client = PlayClient(spoken="Ne dedin sen?")
        out = await self.say(
            "peki şunu söyleyim o zaman: quenna atölyesindeki kalilayı ben öldürdüm, atölyeyi de ben yaktım. ne yapacaksın",
            client)
        self.assertNotEqual(out["turn_outcome"]["status"], "clarification", out["narration"])
        self.assertNotIn("Kime saldırıyorsun", out["narration"])

    async def test_a_past_blow_at_the_person_here_stays_an_attack(self):
        await self.scene(("Isolde", "Nöbetçi Çavuş"))
        with self.app.state.ollama_adapter.engine_binding():
            import combat_lifecycle
            self.assertTrue(combat_lifecycle.is_attack_decision(self.session, "isoldeye vurdum"))
            self.assertTrue(combat_lifecycle.is_attack_decision(self.session, "çavuşa saldırıyorum"))
            self.assertFalse(combat_lifecycle.is_attack_decision(self.session, "adamı dün gece ben öldürdüm"))


class WaitingPassesTime(ThreePlaysTests):
    def elapsed(self):
        return self.world["campaign_time"]["elapsed_seconds"]

    async def test_a_wait_with_a_length_passes_that_time_even_with_more_said(self):
        await self.begin(FIGHTER)
        before = self.elapsed()
        out = await self.say("bir duvarın dibine oturup yarım saat kadar bekliyorum, atölyeye ne oluyor izliyorum")
        self.assertEqual(self.elapsed() - before, 1800, out["narration"])
        self.assertIn("Yarım saat", out["narration"])

    async def test_a_bare_wait_passes_a_little_time_instead_of_asking_how_long(self):
        for line in ("bekliyorum", "biraz bekliyorum", "bir süre bekliyorum"):
            with self.subTest(line=line):
                await self.begin(FIGHTER)
                before = self.elapsed()
                out = await self.say(line)
                self.assertGreater(self.elapsed(), before, out["narration"])
                self.assertNotIn("Kaç dakika", out["narration"])

    async def test_waiting_until_evening_reaches_evening(self):
        await self.begin(FIGHTER)
        self.world["campaign_time"]["start_second"] = 10 * 3600
        await self.say("akşama kadar burada bekliyorum")
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], 8 * 3600)

    async def test_in_a_fight_waiting_still_ends_the_turn(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.add_person("Dorn", "Muhafız")
        await self.say("muhafıza saldırıyorum", PlayClient(intent="attack"))
        self.assertTrue(self.world["combat"]["active"])
        before = self.elapsed()
        out = await self.say("bekliyorum")
        self.assertEqual(out["turn_outcome"]["action"], "action_economy", out["narration"])
        self.assertLess(self.elapsed() - before, 60)

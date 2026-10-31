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

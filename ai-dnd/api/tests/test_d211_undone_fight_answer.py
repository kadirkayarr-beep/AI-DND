"""D-211 review: Undo of the turn that ANSWERED "kavga mı başlatıyorsun?" (the fight-question twin of the surrender case).

Undo of the answer turn put the question back open (the runtime snapshot carries it, PR #58), so the same blow sent
again, or a bare yes, struck without being asked. Like the surrendered-foe question (D-211), Undo closes it: the same
blow is asked about again and a later yes starts nothing.
"""

from __future__ import annotations

import unittest
import uuid

from api.tests import test_dilim4a_english_fight as fight


class UndoneFightAnswer(fight._Table):
    first_seed = 4751

    def live(self):
        return self.manager.get(self.turn_url.rsplit("/turn", 1)[0].rsplit("/", 1)[1]).game_session

    async def struck_then_undone(self, line):
        self.assert_no_blow(await self.ask(line))
        yes_id = str(uuid.uuid4())
        struck = await self.http.post(self.turn_url, json={"message": "yes", "action_id": yes_id})
        self.assertEqual(struck.status_code, 200, struck.text)
        self.assertEqual(struck.json()["turn_outcome"]["action"], "attack", struck.json()["narration"])
        undo = await self.http.post(self.turn_url.rsplit("/turn", 1)[0] + "/undo",
                                    json={"action_id": str(uuid.uuid4()), "target_action_id": yes_id})
        self.assertEqual(undo.status_code, 200, undo.text)
        self.world = self.live().world_state
        self.assertFalse(self.world["combat"]["active"])

    async def test_the_same_blow_after_undoing_its_yes_is_asked_again(self):
        await self.struck_then_undone("I punch the guard")
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
        reply = await self.line("I punch the guard", "Ne yapıyorsun sen?")
        self.assert_no_blow(reply)
        self.assertIn("kavga mı başlatıyorsun", reply["narration"])

    async def test_a_bare_yes_after_undoing_the_answer_starts_nothing(self):
        await self.struck_then_undone("I punch the guard")
        self.client.front = {"kind": "unclear"}
        self.assert_no_blow(await self.line("yes", "Evet mi?"))


if __name__ == "__main__":
    unittest.main()

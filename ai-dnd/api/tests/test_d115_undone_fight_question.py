"""D-115 / YÜK-12: an undone "kavga mı başlatıyorsun?" question is gone; a later unrelated yes starts no fight.

The question lives on the session for one sitting. Undo puts the game back to the state before the turn that asked
it, so the question must go back too; otherwise the next "evet" answers a question the player no longer sees.
"""

from __future__ import annotations

import unittest
import uuid

from api.tests import test_dilim4a_english_fight as fight


class UndoneFightQuestion(fight._Table):
    first_seed = 4751

    async def asked_turn(self, line):
        """Play the line that asks the fight question through the real turn route; return that turn's id."""
        await self.begin()
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
        self.client.narration = "Ne yapıyorsun sen?"
        action_id = str(uuid.uuid4())
        response = await self.http.post(self.turn_url, json={"message": line, "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        reply = response.json()
        self.assert_no_blow(reply)
        self.assertIn("kavga mı başlatıyorsun", reply["narration"])
        return action_id

    async def test_undone_fight_question_does_not_answer_a_later_yes(self):
        asked = await self.asked_turn("Muhafızı iki elimle itiyorum, silahsız beş adım geri.")
        undo = await self.http.post(
            self.turn_url.rsplit("/turn", 1)[0] + "/undo",
            json={"action_id": str(uuid.uuid4()), "target_action_id": asked},
        )
        self.assertEqual(undo.status_code, 200, undo.text)
        self.client.front = {"kind": "unclear"}
        self.assert_no_blow(await self.line("evet", "Evet mi?"))

    async def test_undone_surrender_question_goes_back_with_its_turn(self):
        # D-115 review: the surrendered-foe question ("Yine de vuruyor musun?") is the same kind of sitting-only
        # question; a rolled-back or undone turn that asked it must not leave it open for a later yes.
        await self.begin()
        session = self.manager.get(self.turn_url.rsplit("/turn", 1)[0].rsplit("/", 1)[1]).game_session
        before = session._capture_runtime_snapshot()
        session._surrender_strike_asked = {"ids": [self.npc["id"]], "blow": ["attack"], "said": "vur", "command": None}
        session._restore_runtime_snapshot(before)
        self.assertIsNone(getattr(session, "_surrender_strike_asked", None))
        session._surrender_strike_asked = {"ids": [self.npc["id"]], "blow": ["attack"], "said": "vur", "command": None}
        asked = session._capture_runtime_snapshot()
        session._surrender_strike_asked = None
        session._restore_runtime_snapshot(asked)
        self.assertEqual(session._surrender_strike_asked["ids"], [self.npc["id"]])


if __name__ == "__main__":
    unittest.main()

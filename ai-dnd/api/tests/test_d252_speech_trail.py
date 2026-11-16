"""D-252: the route log says which speech check changed or replaced a person's reply.

Names only, never the player's words or the model's text, so a play log can count what the cleanup took.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.tests import test_town_knowledge as cases
from api.tests.town_seed import fixed_town


class SpeechTrail(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = cases.ThroughTheRealTurn.asyncSetUp
    asyncTearDown = cases.ThroughTheRealTurn.asyncTearDown
    campaign_with_npc = cases.ThroughTheRealTurn.campaign_with_npc
    start = cases.ThroughTheRealTurn.start
    say = cases.ThroughTheRealTurn.say

    async def ready(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.route_file = Path(folder.name) / "routes.jsonl"
        self.enterContext(patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1",
                                                  "AI_DND_ROUTE_LOG": str(self.route_file)}))
        with fixed_town(self, 2718):
            await self.start()

    def last_route(self):
        return json.loads(self.route_file.read_text(encoding="utf-8").splitlines()[-1])

    async def test_a_reply_used_as_said_logs_no_check(self):
        await self.ready()
        await self.say("Selam, nasılsın?", "İyiyim, sağ ol.")
        self.assertEqual(self.last_route()["speech"], [])

    async def test_an_unusable_reply_logs_why_python_spoke(self):
        await self.ready()
        await self.say("Selam.", "Selam.")
        await self.say("Bu nasıl şehir, bana anlatır mısın?", "")
        speech = self.last_route()["speech"]
        self.assertIn("invalid_or_empty", speech)
        self.assertIn("python_town_lead", speech)
        self.assertNotIn("şehir", json.dumps(self.last_route(), ensure_ascii=False))

    async def test_a_turn_without_speech_carries_no_speech_field(self):
        await self.ready()
        await self.say("Etrafa bakıyorum.", "Sokak sakin.", mode=None)
        self.assertNotIn("speech", self.last_route())


if __name__ == "__main__":
    unittest.main()

"""A proposal marker must never reach the player on a turn that cannot propose.

Live Gemma copied [[n1]] onto an existing NPC in 2 of 10 narrations. Only the
world-update path removed markers, and a narration-only turn skips that path.
"""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

import game
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness

MARKED = 'Gözlerindeki hafif bir tebessümle seni karşılayan [[n1]] Marek, omuzlarını silkerek karşılık verdi: "Merhaba."'


class NarrationClient(harness.ScriptedNpcSpeechClient):
    def __init__(self, marked):
        super().__init__()
        self.marked = marked
        self.narration_calls = 0

    def chat(self, *args, **kwargs):
        properties = (copy.deepcopy(kwargs.get("format")) or {}).get("properties", {})
        if "narration" not in properties or "intent" in properties:
            return super().chat(*args, **kwargs)
        self.narration_calls += 1
        return {"message": {"content": json.dumps({
            "world_updates": {"create_locations": [], "create_npcs": [], "update_npcs": [],
                              "create_features": [], "events": []},
            "narration": self.marked,
            "lore_claims": [],
        }, ensure_ascii=False)}}


class NarrationProposalMarkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    campaign_with_npc = harness.ExperimentalNpcDialogueTests.campaign_with_npc

    async def narrated(self, marked):
        *_, turn_url, _ = await self.campaign_with_npc()
        client = NarrationClient(marked)
        with patch.object(self.app.state.ollama_adapter, "_client", client):
            response = await self.http.post(turn_url, json={
                "message": "Marek'in yanına gidip başımla selam veriyorum.",
                "action_id": str(uuid.uuid4()),
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.narration_calls, 1)
        return response.json()["narration"]

    async def test_a_marker_on_a_narration_only_turn_never_reaches_the_player(self):
        shown = await self.narrated(MARKED)
        self.assertNotIn("[[", shown)
        self.assertIn("karşılayan Marek,", shown)

    async def test_every_marker_category_is_removed_and_other_brackets_stay(self):
        cleaned = game._strip_proposal_markers("[[n1]]Marek, [[l2]]arşiv, [[f12]]kapı [[s1]]dükkân [not] [[x1]]")
        self.assertEqual(cleaned, "Marek, arşiv, kapı dükkân [not] [[x1]]")
        self.assertEqual(game._strip_proposal_markers(None), None)


if __name__ == "__main__":
    unittest.main()

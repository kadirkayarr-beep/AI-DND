"""D-003: an experience award paid outside the play turn is announced by the command that paid it.

The species-actions panel route can pay XP (D-105: Inner Radiance drops a bounty target; the fight's XP and the
bounty's XP are paid). The award's line ("+70 deneyim puanı.") must reach the player in that command's own answer and
stored history entry, not one turn late in the next play turn; and undoing that next turn must not announce it again.
"""
from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx

import xp
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_model_failure_never_locks import ScriptedModel
from api.tests.test_species_action_quest_evidence import _stage_radiant_bounty
from api.tests.town_seed import fixed_town

LINE = "+70 deneyim puanı."


class OutOfTurnXpLine(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # A stored campaign (so the history is real) and a model that answers the later play turns' narration only.
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3",
                                   bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(ScriptedModel())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")

    async def asyncTearDown(self):
        await self.http.aclose()

    async def paid_by_the_panel(self):
        with fixed_town(self, 10531):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign = created.json()
        session_id = self.campaign["session_id"]
        session = self.manager.get(session_id).game_session
        _stage_radiant_bounty(session, target_hp=1)
        xp_before = session.character.get("xp", 0)
        with patch.object(session.rng, "randint", return_value=1):
            response = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                            json={"action": "healing_hands", "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(session.character["xp"] - xp_before, 70)  # 60 bounty XP + the fallen foe's 10
        return session_id, session, response.json()

    async def turn(self, session_id, action_id=None):
        response = await self.http.post(f"/api/game/sessions/{session_id}/turn",
                                        json={"message": "Etrafıma bakıyorum.",
                                              "action_id": action_id or str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def history(self):
        return self.store.get_campaign(self.campaign["campaign_id"]).history

    async def test_the_panel_command_that_pays_announces_the_award(self):
        _session_id, session, answer = await self.paid_by_the_panel()
        self.assertEqual(xp.award_line({"previous_level": 3, "new_level": 3, "xp_gained": 70,
                                        "hit_points_gained": 0}), LINE)
        message = answer["result"]["message"]
        self.assertTrue(message.endswith(" " + LINE), message)
        self.assertEqual(message.count("deneyim puanı"), 1)
        self.assertIsNone(session._xp_level_up, "nothing is left pending for a later turn")
        self.assertEqual(self.history()[-1]["narration"], message)

    async def test_the_next_turn_does_not_carry_the_panel_award(self):
        session_id, _session, _answer = await self.paid_by_the_panel()
        later = await self.turn(session_id)
        self.assertIsNone(later.get("level_up"))
        self.assertNotIn("deneyim puanı", later["narration"])

    async def test_undoing_the_next_turn_does_not_announce_the_award_again(self):
        session_id, session, _answer = await self.paid_by_the_panel()
        paid_xp = session.character["xp"]
        later_id = str(uuid.uuid4())
        await self.turn(session_id, later_id)
        undone = await self.http.post(f"/api/game/sessions/{session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": later_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        again = await self.turn(session_id)
        self.assertIsNone(again.get("level_up"))
        self.assertNotIn("deneyim puanı", again["narration"])
        narrations = [entry.get("narration") or "" for entry in self.history()]
        self.assertEqual(sum(text.count(LINE) for text in narrations), 1, narrations)
        self.assertEqual(self.manager.get(session_id).game_session.character["xp"], paid_xp)  # Undo kept the panel's pay


if __name__ == "__main__":
    unittest.main()

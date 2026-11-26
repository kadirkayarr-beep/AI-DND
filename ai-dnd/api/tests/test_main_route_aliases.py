"""D-531 / D-532 (G1.4): pins for the routes still moving out of api.main.create_app and for the legacy aliases.

- the ambient-event action route: each exit is driven through the real HTTP route (conflict, replay, resolved event,
  no campaign, engine failure) and a refusal changes nothing;
- the death rollback of a turn never writes the campaign journal (the one rule no test pinned);
- no route is registered under the legacy /api/sessions family (the canonical family is /api/game/sessions) and no
  (method, path) pair is registered twice.
"""
from __future__ import annotations

import copy
import os
import unittest
import uuid
from typing import Any
from unittest.mock import patch

import httpx

os.environ.setdefault("AI_DND_DISABLE_DEFAULT_APP", "1")

from api.main import create_app  # noqa: E402
from api.session_manager import SessionManager  # noqa: E402
import api.tests.test_campaign_api as campaign_api  # noqa: E402
from api.tests.town_seed import default_town  # noqa: E402

NEVERWINTER_START = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}


class AmbientEventRouteExitsTests(unittest.IsolatedAsyncioTestCase):
    http: httpx.AsyncClient
    manager: SessionManager
    asyncSetUp = campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_api.CampaignApiTests.asyncTearDown
    create_campaign = campaign_api.CampaignApiTests.create_campaign
    install_test_ambient_event = campaign_api.CampaignApiTests.install_test_ambient_event

    async def stage(self):
        created = await self.create_campaign()
        self.session_id = created["session_id"]
        self.record = self.manager.get(self.session_id)
        self.live = self.record.game_session
        self.instance = self.install_test_ambient_event(self.live)
        self.url = f"/api/game/sessions/{self.session_id}/ambient-events/{self.instance}/actions"

    async def click(self, action="interact", action_id=None):
        return await self.http.post(self.url, json={"action_id": action_id or str(uuid.uuid4()), "action": action})

    def observed(self):
        return (copy.deepcopy(self.live.serialize_game_state()), copy.deepcopy(self.record.journal))

    async def test_ambient_event_route_exits(self):
        await self.stage()
        # exit: no campaign to save into
        saved_campaign_id = self.record.campaign_id
        self.record.campaign_id = None
        before = self.observed()
        refused = await self.click()
        self.assertEqual(refused.status_code, 200, refused.text)
        self.assertEqual(refused.json()["result"]["status"], "REJECTED", refused.text)
        self.assertEqual(refused.json()["result"]["reason_code"], "campaign_persistence_required")
        self.assertEqual(self.observed(), before)
        self.record.campaign_id = saved_campaign_id

        # exit: the engine fails; 500 event_persistence_error, nothing changed, session still usable
        before = self.observed()
        with patch.object(self.live, "resolve_ambient_event_action", side_effect=RuntimeError("engine broke")):
            failed = await self.click()
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(failed.json()["detail"]["code"], "event_persistence_error")
        self.assertNotIn("engine broke", failed.text)
        self.assertEqual(self.observed(), before)
        self.assertTrue(self.record.usable)

        # exit: the failure comes after the journal was already rewritten; the old journal and world come back
        before = self.observed()
        with patch("api.main.append_ambient_event_outcome", side_effect=RuntimeError("late failure")):
            failed = await self.click()
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(failed.json()["detail"]["code"], "event_persistence_error")
        self.assertEqual(self.observed(), before)
        self.assertTrue(self.record.usable)

        # exit: applied; then same id replays (ALREADY_APPLIED), same id other action conflicts (REJECTED),
        # a new id on the resolved event is ALREADY_APPLIED with the canonical event
        action_id = str(uuid.uuid4())
        applied = await self.click(action_id=action_id)
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["result"]["status"], "APPLIED", applied.text)
        canonical = applied.json()["result"]["canonical_event_id"]
        self.assertIsNotNone(canonical)
        settled = self.observed()
        replay = await self.click(action_id=action_id)
        self.assertEqual((replay.status_code, replay.json()["result"]["status"],
                          replay.json()["result"]["reason_code"]), (200, "ALREADY_APPLIED", "event_already_resolved"))
        conflict = await self.click(action="observe", action_id=action_id)
        self.assertEqual((conflict.status_code, conflict.json()["result"]["status"],
                          conflict.json()["result"]["reason_code"]), (200, "REJECTED", "action_id_conflict"))
        again = await self.click()
        self.assertEqual((again.status_code, again.json()["result"]["status"],
                          again.json()["result"]["reason_code"]), (200, "ALREADY_APPLIED", "event_already_resolved"))
        self.assertEqual(again.json()["result"]["canonical_event_id"], canonical)
        self.assertEqual(self.observed(), settled)


class DeathRollbackWritesNoJournalTests(unittest.IsolatedAsyncioTestCase):
    http: httpx.AsyncClient
    manager: SessionManager
    asyncSetUp = campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_api.CampaignApiTests.asyncTearDown

    async def turn_journal(self, **extra):
        with default_town(self, campaign_api.TOWN_SEED):
            response = await self.http.post("/api/game/campaigns", json={"campaign_start": NEVERWINTER_START})
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        npc = session.create_npc_from_ai({"name": "Haydut", "role": "Bandit", "location": session.world_state["location"]})
        self.assertIsNotNone(npc, session.world_state["location"])
        npc_id = npc["id"]
        record.journal = copy.deepcopy(record.journal)
        answer = {"narration": "Kapıdan hafif bir ses geliyor.",
                  "action_result": {"action": "interact", "status": "resolved", "success": True, "npc_id": npc_id,
                                    "state_changes": [], **extra}}
        session.run_player_turn = lambda _message, **_kwargs: answer
        before = copy.deepcopy(record.journal)
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return before, record.journal

    async def test_journal_not_written_on_death_rollback(self):
        before, after = await self.turn_journal(death_resolution={"rolled_back": True})
        self.assertEqual(after, before)

    async def test_the_same_turn_without_a_rollback_does_write_the_journal(self):
        before, after = await self.turn_journal()
        self.assertNotEqual(after, before, "control: a normal turn changes the journal, so the rollback case means something")


class TurnIndexAndUndoTests(unittest.IsolatedAsyncioTestCase):
    http: httpx.AsyncClient
    manager: SessionManager
    asyncSetUp = campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_api.CampaignApiTests.asyncTearDown

    async def test_a_turn_advances_the_index_once_and_undo_restores_it(self):
        with default_town(self, campaign_api.TOWN_SEED):
            response = await self.http.post("/api/game/campaigns", json={"campaign_start": NEVERWINTER_START})
        self.assertEqual(response.status_code, 200, response.text)
        session_id = response.json()["session_id"]
        session = self.manager.get(session_id).game_session
        flags = session.world_state["flags"]
        index_before, messages_before = flags.get("turn_index", 0), len(session.messages)
        action_id = str(uuid.uuid4())
        turn = await self.http.post(f"/api/game/sessions/{session_id}/turn",
                                    json={"message": "Etrafa bakıyorum.", "action_id": action_id})
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertEqual(flags.get("turn_index", 0), index_before + 1)
        undone = await self.http.post(f"/api/game/sessions/{session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        restored = self.manager.get(session_id).game_session
        self.assertEqual(restored.world_state["flags"].get("turn_index", 0), index_before)
        self.assertEqual(len(restored.messages), messages_before)


class RouteTableAliasesTests(unittest.TestCase):
    def routes(self):
        app = create_app(ollama_adapter=None, authenticator=None)
        routes: list[Any] = list(app.routes)  # Mount and websocket routes have no methods or no name; read them untyped
        return [(method, route.path, route.name) for route in routes for method in sorted(getattr(route, "methods", None) or [])]

    def test_no_duplicate_method_path_pairs(self):
        pairs = [(method, path) for method, path, _ in self.routes()]
        self.assertEqual(sorted(pair for pair in set(pairs) if pairs.count(pair) > 1), [])

    def test_no_legacy_sessions_alias_routes(self):
        legacy = [(method, path) for method, path, _ in self.routes() if path.startswith("/api/sessions")]
        self.assertEqual(legacy, [])
        self.assertNotIn("resolve_species_trait_action_compat", [name for _, _, name in self.routes()])

    def test_live_smoke_and_security_gate_paths_exist(self):
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        known = {re.sub(r"\{[^}]+\}", "{}", path) for _, path, _ in self.routes()}
        found = []
        for rel in ("api/live_smoke.py", "scripts/security_gate.py"):
            text = (root / rel).read_text(encoding="utf-8")
            found += [("/api" + m) for m in re.findall(r'api_path\(f?"(/(?:game/)?sessions[^"]*)"', text)]
            found += re.findall(r'f?"(/api/game/sessions[^"]*)"', text)
        self.assertTrue(found)
        missing = [p for p in found if re.sub(r"\{[^}]+\}", "{}", p) not in known]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()

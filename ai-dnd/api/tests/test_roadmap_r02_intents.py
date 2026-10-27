"""R02 server-side action intents: one open action per campaign, and a server-proven way out.

Contract under test (single design; there is no second authority next to the receipts):

* A play-turn request first records an INTENT (campaign + action id + request hash) atomically.
  An intent is OPEN until the same action id gains a receipt (applied) or a durable refusal (not applied).
* While an intent is open, a request with a DIFFERENT action id in the same campaign is refused with
  409 ``unresolved_action`` (it names the open id).  The refusal of the new id is durable, so the
  answer ``not_applied: true`` is true.  Other campaigns are never blocked.
* The same action id may always be retried; a different request body under that id is ``action_id_conflict``.
* GET  .../actions/unresolved        -> the open intent of this campaign, or null.
* GET  .../actions/{id}              -> applied (with the stored response) / not_applied / open / unknown.
  ``unknown`` and ``open`` are never evidence that nothing happened.
* POST .../actions/{id}/abandon      -> applied if a receipt exists; ``processing`` if the turn lock is
  held (identity kept); otherwise a durable refusal is written and the answer is ``not_applied``.  A late
  request with that id can then never apply (the receipt insert checks the refusal in its own transaction).
* Nothing expires: an open intent is closed only by a receipt or a refusal, never by age.

Real FastAPI app, real SessionManager, real SQLite campaign store; only the model boundary is faked.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

import httpx

from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignNotFoundError, CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import PLAYER_B, TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from dialogue_runtime import DialogueProviderError

OK_TURN = {"narration": "Kapıdan hafif bir ses geliyor.",
           "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}


class RoadmapR02IntentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.clients = []
        self.calls = []
        self.manager, self.http, self.session_id = await self.boot(self.store, create=True)

    async def boot(self, store, create=False, campaign_id=None):
        manager = SessionManager(campaign_store=store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        app = create_app(session_manager=manager, ollama_adapter=adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        self.clients.append(http)
        if create:
            created = await http.post("/api/game/campaigns", json={})
            self.assertEqual(created.status_code, 200, created.text)
            self.campaign_id = created.json()["campaign_id"]
            session_id = created.json()["session_id"]
        else:
            session_id, *_ = manager.resume_campaign(campaign_id or self.campaign_id)
        manager.get(session_id).game_session.run_player_turn = self.counted_turn
        return manager, http, session_id

    def counted_turn(self, _message, **_kwargs):
        self.calls.append(True)
        return dict(OK_TURN)

    async def asyncTearDown(self):
        for http in self.clients:
            await http.aclose()
        self.temporary_directory.cleanup()

    # --- helpers -------------------------------------------------------------------------------------
    def body(self, text="Kapının arkasından ses dinliyorum."):
        return {"message": text, "action_id": str(uuid.uuid4())}

    def turn(self, body, http=None, session_id=None):
        return (http or self.http).post(f"/api/game/sessions/{session_id or self.session_id}/turn", json=body)

    def unresolved(self, http=None, session_id=None):
        return (http or self.http).get(f"/api/game/sessions/{session_id or self.session_id}/actions/unresolved")

    def status(self, action_id, http=None, session_id=None):
        return (http or self.http).get(f"/api/game/sessions/{session_id or self.session_id}/actions/{action_id}")

    def abandon(self, action_id, http=None, session_id=None):
        return (http or self.http).post(f"/api/game/sessions/{session_id or self.session_id}/actions/{action_id}/abandon")

    async def leave_open_by_outage(self, body):
        """A pre-effect, retryable failure: the intent was recorded, no terminal result exists."""
        def outage(_message, **_kwargs):
            raise DialogueProviderError("provider down")

        session = self.manager.get(self.session_id).game_session
        good = session.run_player_turn
        session.run_player_turn = outage
        failed = await self.turn(body)
        session.run_player_turn = good
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertNotIn("not_applied", failed.json()["detail"])

    # --- 1. concurrent different UUIDs --------------------------------------------------------------
    async def test_a_different_uuid_is_refused_atomically_while_the_first_is_in_flight(self):
        started, release = threading.Event(), threading.Event()

        def slow(_message, **_kwargs):
            self.calls.append("slow")
            started.set()
            release.wait(10)
            return dict(OK_TURN)

        self.manager.get(self.session_id).game_session.run_player_turn = slow
        first_body, second_body = self.body(), self.body("Başka bir şey yapıyorum.")
        first = asyncio.create_task(self.turn(first_body))
        self.assertTrue(await asyncio.to_thread(started.wait, 5))

        second = await self.turn(second_body)  # arrives while the first is still unresolved
        self.assertEqual(second.status_code, 409, second.text)
        detail = second.json()["detail"]
        self.assertEqual(detail["code"], "unresolved_action")
        self.assertEqual(detail["unresolved_action_id"], first_body["action_id"])
        self.assertIs(detail["not_applied"], True, "the refusal of the new id is durable, so the claim is true")

        release.set()
        self.assertEqual((await first).status_code, 200)
        self.assertEqual(self.calls, ["slow"], "only the first action ran")

        again = await self.turn(second_body)  # same refused id later: still refused, never applied
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["detail"]["code"], "unresolved_action")
        self.assertEqual(self.calls, ["slow"])
        fresh = await self.turn(self.body("Bilinçli yeni seçim."))
        self.assertEqual(fresh.status_code, 200, fresh.text)

    async def test_the_same_uuid_may_always_retry_while_open(self):
        body = self.body()
        await self.leave_open_by_outage(body)
        retry = await self.turn(body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((await self.unresolved()).json()["unresolved"], None)

    async def test_a_different_body_under_an_open_id_is_an_id_conflict(self):
        body = self.body()
        await self.leave_open_by_outage(body)
        changed = await self.turn({**body, "message": "Tamamen başka bir hamle."})
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["detail"]["code"], "action_id_conflict")
        self.assertNotIn("not_applied", changed.json()["detail"])
        self.assertEqual(self.calls, [])

    async def test_other_campaigns_are_never_blocked(self):
        await self.leave_open_by_outage(self.body())
        other = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(other.status_code, 200, other.text)
        other_session = other.json()["session_id"]
        self.manager.get(other_session).game_session.run_player_turn = self.counted_turn
        free = await self.turn(self.body(), session_id=other_session)
        self.assertEqual(free.status_code, 200, free.text)
        self.assertEqual(len(self.calls), 1)

    # --- 2. crash windows, restart, second tab, re-login ----------------------------------------------
    async def test_intent_without_effect_survives_a_restart_and_blocks_another_uuid(self):
        body = self.body()
        await self.leave_open_by_outage(body)  # intent recorded -> crash before any effect
        manager, http, session_id = await self.boot(CampaignStore(self.store.path, bound_principal=TEST_PLAYER))  # restart / second tab / re-login
        found = (await self.unresolved(http, session_id)).json()["unresolved"]
        self.assertEqual(found["action_id"], body["action_id"])
        self.assertEqual(found["state"], "open")
        blocked = await self.turn(self.body("Yeni oturumdan farklı bir hamle."), http, session_id)
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["detail"]["unresolved_action_id"], body["action_id"])
        self.assertEqual(self.calls, [])
        # The identity was kept: the original request, retried with its own id, still applies exactly once.
        retried = await self.turn(body, http, session_id)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone((await self.unresolved(http, session_id)).json()["unresolved"])

    async def test_effect_then_lost_terminal_is_reconciled_from_the_stored_receipt(self):
        body = self.body()
        first = await self.turn(body)  # committed; the client never saw this reply
        status = (await self.status(body["action_id"])).json()
        self.assertEqual(status["state"], "applied")
        self.assertEqual(status["response"]["action_id"], body["action_id"])
        self.assertEqual(status["response"]["narration"], first.json()["narration"])
        after_restart_manager, http, session_id = await self.boot(CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        again = (await self.status(body["action_id"], http, session_id)).json()
        self.assertEqual(again["state"], "applied")
        self.assertEqual(len(self.calls), 1)
        # Abandoning an applied action never turns it into a refusal.
        abandoned = (await self.abandon(body["action_id"], http, session_id)).json()
        self.assertEqual(abandoned["state"], "applied")

    async def test_abandon_closes_an_open_intent_and_a_late_original_can_never_apply(self):
        body = self.body()
        await self.leave_open_by_outage(body)
        result = await self.abandon(body["action_id"])
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["state"], "not_applied")
        self.assertIs(result.json()["detail"]["not_applied"], True)
        late = await self.turn(body)  # the old request arrives afterwards (retry timer, second tab, proxy)
        self.assertEqual(late.status_code, 409, late.text)
        self.assertIs(late.json()["detail"]["not_applied"], True)
        self.assertEqual(self.calls, [], "the abandoned id must never run the engine")
        self.assertEqual(len(self.store.get_campaign(self.campaign_id).history), 0)
        self.assertIsNone((await self.unresolved()).json()["unresolved"])
        fresh = await self.turn(self.body("Oyuncunun açık yeni seçimi."))
        self.assertEqual(fresh.status_code, 200, fresh.text)

    async def test_abandon_during_a_running_turn_keeps_identity_and_does_not_guess(self):
        body = self.body()
        await self.leave_open_by_outage(body)
        session = self.manager.get(self.session_id).game_session
        gate_in, gate_out = threading.Event(), threading.Event()
        autosave = self.manager.autosave_turn

        def paused_autosave(*args, **kwargs):
            gate_in.set()
            gate_out.wait(10)
            return autosave(*args, **kwargs)

        session.run_player_turn = self.counted_turn
        with patch.object(self.manager, "autosave_turn", side_effect=paused_autosave):
            running = asyncio.create_task(self.turn(body))
            self.assertTrue(await asyncio.to_thread(gate_in.wait, 5))
            # The turn holds the lock and is about to commit: abandon must keep identity, not guess.
            held = (await self.abandon(body["action_id"])).json()
            self.assertEqual(held["state"], "processing")
            # An unknown outcome is never bypassed by abandon: no refusal was written and a different UUID is still blocked.
            self.assertEqual((await self.status(body["action_id"])).json()["state"], "open")
            blocked = await self.turn(self.body("Başka bir hamle."))
            self.assertEqual(blocked.status_code, 409, blocked.text)
            self.assertEqual(blocked.json()["detail"]["unresolved_action_id"], body["action_id"])
            gate_out.set()
            self.assertEqual((await running).status_code, 200)
        self.assertEqual((await self.status(body["action_id"])).json()["state"], "applied")

    async def test_unknown_id_is_not_evidence_but_abandon_makes_the_late_arrival_harmless(self):
        ghost = str(uuid.uuid4())
        status = (await self.status(ghost)).json()
        self.assertEqual(status["state"], "unknown", "never seen is not proof that it never will arrive")
        self.assertEqual((await self.abandon(ghost)).json()["state"], "not_applied")
        late = await self.turn({"message": "Geç kalan istek.", "action_id": ghost})
        self.assertEqual(late.status_code, 409, late.text)
        self.assertIs(late.json()["detail"]["not_applied"], True)
        self.assertEqual(self.calls, [])

    async def test_nothing_expires_by_age(self):
        body = self.body()
        await self.leave_open_by_outage(body)
        connection = sqlite3.connect(self.store.path)
        try:
            with connection:
                connection.execute("UPDATE campaign_action_intents SET created_at = '2001-01-01T00:00:00+00:00'")
        finally:
            connection.close()
        found = (await self.unresolved()).json()["unresolved"]
        self.assertEqual(found["action_id"], body["action_id"], "an old open intent is not silently dropped")
        blocked = await self.turn(self.body())
        self.assertEqual(blocked.status_code, 409)

    async def test_a_stale_tab_is_rejected_before_it_can_claim_an_intent_and_never_blocks_the_live_tab(self):
        old_session = self.session_id
        # A second process (another tab on another worker) resumes the campaign and moves it on.
        manager, other_http, new_session = await self.boot(CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        free = await self.turn(self.body("Güncel oturumdan hamle."), other_http, new_session)
        self.assertEqual(free.status_code, 200, free.text)  # the campaign moved on without the old session
        stale_body = self.body()
        stale = await self.turn(stale_body, session_id=old_session)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["detail"]["code"], "campaign_stale")
        self.assertNotIn("not_applied", stale.json()["detail"], "a retryable stale answer proves nothing was closed")
        self.assertEqual(len(self.calls), 1)
        # A stale tab is rejected BEFORE an intent is claimed: it leaves nothing open that could block the live tab.
        self.assertIsNone((await self.unresolved(other_http, new_session)).json()["unresolved"])
        self.assertEqual((await self.status(stale_body["action_id"], other_http, new_session)).json()["state"], "unknown")
        later = await self.turn(self.body("Yine güncel oturum."), other_http, new_session)
        self.assertEqual(later.status_code, 200, later.text)
        self.assertEqual(len(self.calls), 2)

    async def test_a_stale_claimer_never_removes_the_intent_another_session_is_running(self):
        # Session A claims X and stops before its engine; session B (second manager, same database) moves the campaign
        # on through a save that does not look at intents, then runs the SAME action X (existing intent) and stays inside
        # its engine. When A finally finds itself stale it must leave X open: X is running in B.
        a_in_lock, a_go = threading.Event(), threading.Event()
        b_in_engine, b_go = threading.Event(), threading.Event()
        manager_b, http_b, session_b = await self.boot(CampaignStore(self.store.path, bound_principal=TEST_PLAYER))

        def b_engine(_message, **_kwargs):
            self.calls.append("b")
            b_in_engine.set()
            b_go.wait(10)
            return dict(OK_TURN)

        manager_b.get(session_b).game_session.run_player_turn = b_engine
        real_get_turn_action = self.manager.get_turn_action

        def gated_get_turn_action(*args, **kwargs):
            a_in_lock.set()
            a_go.wait(10)
            return real_get_turn_action(*args, **kwargs)

        x = self.body()
        with patch.object(self.manager, "get_turn_action", side_effect=gated_get_turn_action):
            a_request = asyncio.create_task(self.turn(x))
            self.assertTrue(await asyncio.to_thread(a_in_lock.wait, 5), "A claimed X and holds its turn lock")
            saved = await http_b.post(f"/api/game/campaigns/{self.campaign_id}/save")  # no intent check on this path
            self.assertEqual(saved.status_code, 200, saved.text)
            b_request = asyncio.create_task(self.turn(x, http_b, session_b))
            self.assertTrue(await asyncio.to_thread(b_in_engine.wait, 5), "B runs X inside its engine")
            a_go.set()
            a_result = await a_request
            self.assertEqual(a_result.status_code, 409, a_result.text)
            self.assertEqual(a_result.json()["detail"]["code"], "campaign_stale")
            self.assertNotIn("not_applied", a_result.json()["detail"], "A proved nothing about X")
            self.assertEqual((await self.status(x["action_id"], http_b, session_b)).json()["state"], "open",
                             "X is still running in B and must stay open")
            other = await self.turn(self.body("Başka bir hamle."), http_b, session_b)
            self.assertEqual(other.status_code, 409, other.text)
            self.assertEqual(other.json()["detail"]["code"], "unresolved_action")
            self.assertEqual(other.json()["detail"]["unresolved_action_id"], x["action_id"])
            self.assertEqual(self.calls, ["b"], "only X, inside B, ever ran the engine")
            b_go.set()
            self.assertEqual((await b_request).status_code, 200)

    async def test_an_abandoned_species_action_in_a_transient_session_can_never_run_late(self):
        created = await self.http.post("/api/game/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        transient = created.json()["session_id"]
        record = self.manager.get(transient)
        self.assertIsNone(record.campaign_id, "this is a transient (non-campaign) session")
        session = record.game_session
        session.character.update({"species": "Aasimar", "race": "Aasimar", "level": 3, "proficiency_bonus": 2,
                                  "current_hp": 1, "max_hp": 20, "charisma_mod": 1})
        session.initialize_species_trait_state()
        action_id = str(uuid.uuid4())
        closed = (await self.abandon(action_id, session_id=transient)).json()
        self.assertEqual(closed["state"], "not_applied")
        character_before, rng_before = dict(session.character), session.rng.getstate()
        with patch.object(session, "resolve_species_trait_action", side_effect=AssertionError("the engine must not run")) as engine:
            late = await self.http.post(f"/api/game/sessions/{transient}/species-actions",
                                        json={"action": "healing_hands", "action_id": action_id})
        self.assertEqual(late.status_code, 409, late.text)
        self.assertEqual(late.json()["detail"]["code"], "action_abandoned")
        self.assertIs(late.json()["detail"]["not_applied"], True)
        engine.assert_not_called()
        self.assertEqual(session.character, character_before)
        self.assertEqual(session.rng.getstate(), rng_before)
        self.assertNotIn(action_id, record.turn_action_receipts, "no receipt was created")
        self.assertEqual((await self.status(action_id, session_id=transient)).json()["state"], "not_applied")
        # A fresh id still works: the closed id is the only thing refused.
        with patch.object(session.rng, "randint", return_value=1):
            fresh = await self.http.post(f"/api/game/sessions/{transient}/species-actions",
                                         json={"action": "healing_hands", "action_id": str(uuid.uuid4())})
        self.assertEqual(fresh.status_code, 200, fresh.text)

    async def test_transient_cache_pressure_evicts_ordinary_refusals_before_an_abandoned_one(self):
        from api.session_manager import MAX_TRANSIENT_REFUSED_ACTIONS
        created = await self.http.post("/api/game/sessions")
        transient = created.json()["session_id"]
        record = self.manager.get(transient)
        abandoned = str(uuid.uuid4())
        self.assertEqual((await self.abandon(abandoned, session_id=transient)).json()["state"], "not_applied")
        for _ in range(MAX_TRANSIENT_REFUSED_ACTIONS + 40):  # ordinary refusals from refused turns, far past the cap
            self.manager.record_refused_action(record, str(uuid.uuid4()), "a" * 64, 409, {"code": "x", "message": "x", "not_applied": True})
        self.assertLessEqual(len(record.refused_actions), MAX_TRANSIENT_REFUSED_ACTIONS)
        self.assertEqual((await self.status(abandoned, session_id=transient)).json()["state"], "not_applied",
                         "the player's abandon outlives ordinary cache pressure (still process-memory only, still capped)")

    async def test_species_action_on_a_campaign_session_keeps_early_refusal_and_receipt_priority(self):
        session = self.manager.get(self.session_id).game_session
        session.character.update({"species": "Aasimar", "race": "Aasimar", "level": 3, "proficiency_bonus": 2,
                                  "current_hp": 1, "max_hp": 20, "charisma_mod": 1})
        session.initialize_species_trait_state()
        url = f"/api/game/sessions/{self.session_id}/species-actions"
        abandoned_id = str(uuid.uuid4())
        self.assertEqual((await self.abandon(abandoned_id)).json()["state"], "not_applied")
        with patch.object(session, "resolve_species_trait_action", side_effect=AssertionError("the engine must not run")) as engine:
            late = await self.http.post(url, json={"action": "healing_hands", "action_id": abandoned_id})
        self.assertEqual((late.status_code, late.json()["detail"]["code"]), (409, "action_abandoned"))
        engine.assert_not_called()
        # A receipt always wins: an applied species action replays, and abandoning it never turns it into a refusal.
        applied_id = str(uuid.uuid4())
        with patch.object(session.rng, "randint", return_value=1):
            first = await self.http.post(url, json={"action": "healing_hands", "action_id": applied_id})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual((await self.abandon(applied_id)).json()["state"], "applied")
        replay = await self.http.post(url, json={"action": "healing_hands", "action_id": applied_id})
        self.assertEqual((replay.status_code, replay.json()["action_id"]), (200, applied_id))
        changed = await self.http.post(url, json={"action": "long_rest", "action_id": applied_id})
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["detail"]["code"], "action_id_conflict")

    # --- schema: the tables belong to the schema from the first open, survive reopen, cascade, and are validated -----
    def _tables(self):
        connection = sqlite3.connect(self.store.path)
        try:
            return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            connection.close()

    async def test_intent_and_refusal_tables_exist_from_the_first_open_and_a_rejected_request_does_not_change_the_schema(self):
        fresh = CampaignStore(Path(self.temporary_directory.name) / "fresh.sqlite3", bound_principal=TEST_PLAYER)
        connection = sqlite3.connect(fresh.path)
        try:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            connection.close()
        self.assertTrue({"campaign_action_intents", "campaign_refused_actions"} <= names, "created at open, not lazily inside a request")
        # An older database without them is upgraded on open (no version bump, IF NOT EXISTS), and reopening is idempotent.
        connection = sqlite3.connect(self.store.path)
        try:
            connection.execute("DROP TABLE campaign_action_intents")
            connection.execute("DROP TABLE campaign_refused_actions")
            connection.commit()
        finally:
            connection.close()
        reopened = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        self.assertTrue({"campaign_action_intents", "campaign_refused_actions"} <= self._tables())
        self.assertIsNone(reopened.unresolved_action(self.campaign_id))

    async def test_a_damaged_intent_table_makes_the_store_refuse_to_open(self):
        connection = sqlite3.connect(self.store.path)
        try:
            connection.execute("DROP TABLE campaign_action_intents")
            connection.execute("CREATE TABLE campaign_action_intents (campaign_id TEXT)")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(Exception) as caught:
            CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        self.assertIn("schema", str(caught.exception).lower())

    async def test_deleting_a_campaign_removes_its_intents_and_refusals_and_only_its_own(self):
        other = await self.http.post("/api/game/campaigns", json={})
        other_id, other_session = other.json()["campaign_id"], other.json()["session_id"]
        self.manager.get(other_session).game_session.run_player_turn = self.counted_turn
        await self.leave_open_by_outage(self.body())
        await self.abandon(str(uuid.uuid4()))
        outage_body = self.body()
        session = self.manager.get(other_session).game_session
        good = session.run_player_turn
        session.run_player_turn = lambda *_a, **_k: (_ for _ in ()).throw(DialogueProviderError("down"))
        await self.turn(outage_body, session_id=other_session)
        session.run_player_turn = good
        deleted = await self.http.delete(f"/api/game/campaigns/{self.campaign_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        connection = sqlite3.connect(self.store.path)
        try:
            intents = connection.execute("SELECT campaign_id FROM campaign_action_intents").fetchall()
            refused = connection.execute("SELECT campaign_id FROM campaign_refused_actions").fetchall()
        finally:
            connection.close()
        self.assertEqual({row[0] for row in intents}, {other_id}, "only the other campaign keeps its open intent")
        self.assertNotIn(self.campaign_id, {row[0] for row in refused})

    async def test_live_bodies_match_the_contract_fixture_the_client_tests_use(self):
        import json
        fixture = json.loads((Path(__file__).parent / "fixtures" / "r02_intent_contract.json").read_text(encoding="utf-8"))
        ids = fixture["ids"]
        await self.leave_open_by_outage({"message": "Kapıyı dinliyorum.", "action_id": ids["open"]})
        refused = await self.turn({"message": "Başka bir şey.", "action_id": ids["newer"]})
        self.assertEqual((refused.status_code, refused.json()), (fixture["unresolved_action_refusal"]["status"], fixture["unresolved_action_refusal"]["body"]))
        listed = await self.unresolved()
        live = listed.json()
        live["unresolved"]["created_at"] = "<timestamp>"
        self.assertEqual((listed.status_code, live), (fixture["unresolved_list"]["status"], fixture["unresolved_list"]["body"]))
        opened = await self.status(ids["open"])
        self.assertEqual((opened.status_code, opened.json()), (fixture["status_open"]["status"], fixture["status_open"]["body"]))
        unknown = await self.status(ids["never_seen"])
        self.assertEqual((unknown.status_code, unknown.json()), (fixture["status_unknown"]["status"], fixture["status_unknown"]["body"]))
        closed = await self.abandon(ids["open"])
        self.assertEqual((closed.status_code, closed.json()), (fixture["abandon_not_applied"]["status"], fixture["abandon_not_applied"]["body"]))

    # --- 3. ownership --------------------------------------------------------------------------------
    async def test_another_principal_cannot_read_or_close_the_intents(self):
        body = self.body()
        await self.leave_open_by_outage(body)
        other = CampaignStore(self.store.path, bound_principal=PLAYER_B)
        with self.assertRaises(CampaignNotFoundError):
            other.unresolved_action(self.campaign_id)
        with self.assertRaises(CampaignNotFoundError):
            other.abandon_action(self.campaign_id, body["action_id"])
        self.assertEqual((await self.unresolved()).json()["unresolved"]["action_id"], body["action_id"])


if __name__ == "__main__":
    unittest.main()

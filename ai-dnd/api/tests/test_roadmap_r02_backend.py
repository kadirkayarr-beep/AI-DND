"""R02 backend contract: a turn's fate is decided under the session turn lock and its receipt/refusal.

Uses the real FastAPI app, real SessionManager and a temporary campaign store; only the model boundary is
the FakeOllamaClient already used by the campaign API tests. No game server, no personal saves.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

import httpx

import api.main as main_module
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from dialogue_runtime import DialogueProviderError


class RoadmapR02BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.session = self.manager.get(self.created["session_id"]).game_session
        self.calls = []

        def counted_turn(_message, **_kwargs):
            self.calls.append(True)
            return {"narration": "Kapıdan hafif bir ses geliyor.",
                    "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}

        self.session.run_player_turn = counted_turn

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def turn(self, body):
        return self.http.post(f"/api/game/sessions/{self.created['session_id']}/turn", json=body)

    def status(self, action_id):
        return self.http.get(f"/api/game/sessions/{self.created['session_id']}/actions/{action_id}")

    async def test_certain_pre_commit_refusal_stays_refused_even_if_state_later_matches(self):
        action_id = str(uuid.uuid4())
        body = {"message": "Kapıyı dinliyorum.", "action_id": action_id,
                "combat_id": "combat-x", "combat_round": 1, "combat_turn_index": 0}
        first = await self.turn(body)
        self.assertEqual(first.status_code, 409, first.text)
        detail = first.json()["detail"]
        self.assertEqual(detail["code"], "stale_combat")
        self.assertIs(detail["not_applied"], True)
        self.assertEqual(self.calls, [])

        # Later the combat context the request named becomes true (another path moved the world).
        self.session.world_state["combat"] = {"active": True, "combat_id": "combat-x", "round": 1, "current_turn_index": 0}
        second = await self.turn(body)
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(second.json()["detail"]["code"], "stale_combat")
        self.assertIs(second.json()["detail"]["not_applied"], True)
        self.assertEqual(self.calls, [], "a refused action id can never be applied later")
        self.assertEqual(len(self.store.get_campaign(self.created["campaign_id"]).history), 0)

    async def test_refusal_is_bound_to_the_request_content(self):
        action_id = str(uuid.uuid4())
        stale = {"message": "Kapıyı dinliyorum.", "action_id": action_id,
                 "combat_id": "combat-x", "combat_round": 1, "combat_turn_index": 0}
        self.assertEqual((await self.turn(stale)).status_code, 409)
        changed = await self.turn({"message": "Başka bir şey yapıyorum.", "action_id": action_id})
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["detail"]["code"], "action_id_conflict")
        self.assertNotIn("not_applied", changed.json()["detail"], "a conflict makes no claim about the first request")

    async def test_commit_then_lost_reply_replays_the_same_receipt_once(self):
        body = {"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())}
        first = await self.turn(body)  # the client never sees this reply
        self.assertEqual(first.status_code, 200, first.text)
        retry = await self.turn(body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json(), first.json())
        self.assertEqual(len(self.calls), 1)

    async def test_retry_during_the_original_waits_and_never_sees_an_absent_receipt(self):
        started, release = threading.Event(), threading.Event()

        def slow_turn(_message, **_kwargs):
            self.calls.append(True)
            started.set()
            release.wait(10)
            return {"narration": "Yavaş cevap.", "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}

        self.session.run_player_turn = slow_turn
        body = {"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())}
        original = asyncio.create_task(self.turn(body))
        self.assertTrue(await asyncio.to_thread(started.wait, 5))
        retry = asyncio.create_task(self.turn(body))
        await asyncio.sleep(0.4)
        self.assertFalse(retry.done(), "the retry waits for the turn lock instead of reporting a missing receipt")
        release.set()
        first, second = await asyncio.gather(original, retry)
        self.assertEqual((first.status_code, second.status_code), (200, 200), (first.text, second.text))
        self.assertEqual(second.json(), first.json())
        self.assertEqual(len(self.calls), 1)

    async def test_late_original_after_the_retry_committed_replays_instead_of_applying_twice(self):
        body = {"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())}
        retry_first = await self.turn(body)  # the retry reached the server first
        late_original = await self.turn(body)  # the original arrives afterwards
        self.assertEqual((retry_first.status_code, late_original.status_code), (200, 200))
        self.assertEqual(late_original.json(), retry_first.json())
        self.assertEqual(len(self.calls), 1)

    async def test_fresh_manager_resume_replays_the_persisted_receipt_without_applying_again(self):
        body = {"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())}
        first = await self.turn(body)
        self.assertEqual(first.status_code, 200, first.text)
        # A restart or a second process has no client lock and no in-memory state: it resumes the campaign into a new session (NOT a model of re-login or another principal).
        reloaded = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        resumed_id, *_ = reloaded.resume_campaign(self.created["campaign_id"])
        resumed_session = reloaded.get(resumed_id).game_session
        resumed_calls = []
        resumed_session.run_player_turn = lambda *_a, **_k: resumed_calls.append(True)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        other_app = create_app(session_manager=reloaded, ollama_adapter=adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=other_app), base_url="http://testserver") as other:
            replay = await other.post(f"/api/game/sessions/{resumed_id}/turn", json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["action_id"], body["action_id"])
        self.assertEqual(resumed_calls, [], "the persisted receipt answers; the move is not applied again")


    # --- failures that happen AFTER the engine ran but are fully rolled back under the turn lock ---

    def fresh_body(self):
        return {"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())}

    async def assert_refused_for_good(self, body, code):
        first = await self.turn(body)
        self.assertEqual(first.status_code, 500, first.text)
        self.assertEqual(first.json()["detail"]["code"], code)
        self.assertIs(first.json()["detail"]["not_applied"], True, "a completed rollback means the action was never applied")
        return first

    async def assert_stays_refused_and_new_id_works(self, body, code, calls_before):
        again = await self.turn(body)  # everything works now, but this action id is closed for good
        self.assertEqual(again.status_code, 500, again.text)
        self.assertEqual(again.json()["detail"]["code"], code)
        self.assertIs(again.json()["detail"]["not_applied"], True)
        self.assertEqual(len(self.calls), calls_before, "the refused id must not run the engine again")
        self.assertEqual(len(self.store.get_campaign(self.created["campaign_id"]).history), 0)
        fresh = await self.turn(self.fresh_body())
        self.assertEqual(fresh.status_code, 200, fresh.text)

    async def test_generic_engine_failure_after_rollback_is_tombstoned(self):
        def boom(_message, **_kwargs):
            self.calls.append(True)
            raise RuntimeError("engine blew up")

        good = self.session.run_player_turn
        self.session.run_player_turn = boom
        body = self.fresh_body()
        await self.assert_refused_for_good(body, "engine_error")
        self.session.run_player_turn = good
        await self.assert_stays_refused_and_new_id_works(body, "engine_error", calls_before=1)

    async def test_invalid_engine_result_after_rollback_is_tombstoned(self):
        good = self.session.run_player_turn
        self.session.run_player_turn = lambda *_a, **_k: (self.calls.append(True), {"narration": "", "action_result": {}})[1]
        body = self.fresh_body()
        await self.assert_refused_for_good(body, "engine_error")
        self.session.run_player_turn = good
        await self.assert_stays_refused_and_new_id_works(body, "engine_error", calls_before=1)

    async def test_narrative_memory_failure_after_rollback_is_tombstoned(self):
        body = self.fresh_body()
        with patch.object(main_module, "update_narrative_memory", side_effect=RuntimeError("memory")):
            await self.assert_refused_for_good(body, "narrative_memory_error")
        await self.assert_stays_refused_and_new_id_works(body, "narrative_memory_error", calls_before=1)

    async def test_journal_failure_after_rollback_is_tombstoned(self):
        body = self.fresh_body()
        with patch.object(main_module, "serialize_session_state", side_effect=RuntimeError("journal")):
            await self.assert_refused_for_good(body, "journal_error")
        await self.assert_stays_refused_and_new_id_works(body, "journal_error", calls_before=1)

    async def test_failed_restore_is_never_called_not_applied(self):
        def boom(_message, **_kwargs):
            raise RuntimeError("engine blew up")

        self.session.run_player_turn = boom
        with patch.object(main_module, "_restore_session", side_effect=RuntimeError("restore failed")):
            response = await self.turn(self.fresh_body())
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "session_restore_failed")
        self.assertNotIn("not_applied", response.json()["detail"], "if the rollback itself failed nothing can be claimed")

    async def test_rolled_back_persistence_failure_stays_unresolved_and_retries_with_the_same_id(self):
        body = self.fresh_body()
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("disk")):
            failed = await self.turn(body)
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(failed.json()["detail"]["code"], "persistence_error")
        # Rolled back, but whether the commit reached the disk is not known: no claim, the id stays unresolved.
        self.assertNotIn("not_applied", failed.json()["detail"], "the commit boundary is R04's; no claim is made here")
        self.assertEqual(len(self.store.get_campaign(self.created["campaign_id"]).history), 0)
        self.assertEqual((await self.status(body["action_id"])).json()["state"], "open")
        blocked = await self.turn(self.fresh_body())
        self.assertEqual(blocked.status_code, 409, "an uncertain action blocks a different UUID")
        self.assertEqual(blocked.json()["detail"]["unresolved_action_id"], body["action_id"])
        retry = await self.turn(body)  # the safe path: the same id (receipt replay if it had committed)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(len(self.calls), 2, "the failed attempt ran once, the retry once; nothing ran twice after a commit")
        fresh = await self.turn(self.fresh_body())
        self.assertEqual(fresh.status_code, 200, fresh.text)

    async def test_persistence_failure_after_the_receipt_committed_makes_no_never_applied_claim(self):
        body = self.fresh_body()
        real_autosave = self.manager.autosave_turn

        def commit_then_fail(*args, **kwargs):
            real_autosave(*args, **kwargs)  # the receipt is durably stored ...
            raise RuntimeError("late failure")  # ... but the caller sees an error

        with patch.object(self.manager, "autosave_turn", side_effect=commit_then_fail):
            failed = await self.turn(body)
        # R04: a stored receipt with this exact result is a committed-but-unconfirmed turn, reported as such (never success).
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()["detail"]["commit_status"], "committed_unconfirmed")
        self.assertNotIn("not_applied", failed.json()["detail"], "a stored receipt means it may well have been applied")
        self.assertEqual((await self.status(body["action_id"])).json()["state"], "applied")

    async def test_an_uncertain_persistence_failure_is_closed_only_by_the_players_server_proven_abandon(self):
        body = self.fresh_body()
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("disk")):
            failed = await self.turn(body)
        self.assertEqual(failed.status_code, 500, failed.text)
        blocked = await self.turn(self.fresh_body())
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "unresolved_action")
        # The explicit, owner-authenticated abandon writes a durable refusal (no receipt exists): only then is the id closed.
        closed = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/actions/{body['action_id']}/abandon")
        self.assertEqual(closed.json()["state"], "not_applied")
        late = await self.turn(body)
        self.assertEqual(late.status_code, 409, late.text)
        self.assertIs(late.json()["detail"]["not_applied"], True)
        self.assertEqual(len(self.calls), 1, "the abandoned id never runs the engine again")
        fresh = await self.turn(self.fresh_body())
        self.assertEqual(fresh.status_code, 200, fresh.text)

    async def test_transient_model_outage_stays_retryable_with_the_same_id(self):
        def outage(_message, **_kwargs):
            raise DialogueProviderError("provider down")

        good = self.session.run_player_turn
        self.session.run_player_turn = outage
        body = self.fresh_body()
        failed = await self.turn(body)
        self.assertEqual(failed.status_code, 503, failed.text)
        # The owner rejected a campaign held by one bad model reply: the rollback is proven and the intent released, so the
        # claim is true and closes the browser's pending record. The same id stays a safe retry.
        self.assertIs(failed.json()["detail"]["not_applied"], True)
        self.assertIsNone((await self.http.get(f"/api/game/sessions/{self.created['session_id']}/actions/unresolved")).json()["unresolved"])
        self.session.run_player_turn = good
        retry = await self.turn(body)
        self.assertEqual(retry.status_code, 200, retry.text)

    async def test_a_failed_release_makes_no_never_applied_claim_and_keeps_the_intent_open(self):
        def outage(_message, **_kwargs):
            raise DialogueProviderError("provider down")

        good = self.session.run_player_turn
        body = self.fresh_body()
        for failure in ({"side_effect": RuntimeError("store down")}, {"return_value": False}):
            with self.subTest(failure=failure):
                self.session.run_player_turn = outage
                with patch.object(self.manager, "release_action_intent", **failure) as release:
                    failed = await self.turn(body)
                release.assert_called_once()
                self.assertEqual(failed.status_code, 503, failed.text)
                self.assertNotIn("not_applied", failed.json()["detail"], "the browser must not close its record")
                unresolved = await self.http.get(f"/api/game/sessions/{self.created['session_id']}/actions/unresolved")
                self.assertEqual(unresolved.json()["unresolved"]["action_id"], body["action_id"])
                blocked = await self.turn(self.fresh_body())
                self.assertEqual(blocked.status_code, 409, blocked.text)
        self.session.run_player_turn = good
        retry = await self.turn(body)
        self.assertEqual(retry.status_code, 200, retry.text)

    async def test_an_old_released_id_arriving_after_another_move_runs_once_as_a_new_move(self):
        def outage(_message, **_kwargs):
            raise DialogueProviderError("provider down")

        good = self.session.run_player_turn
        old = self.fresh_body()
        self.session.run_player_turn = outage
        self.assertIs((await self.turn(old)).json()["detail"]["not_applied"], True)
        self.session.run_player_turn = good
        between = await self.turn(self.fresh_body())
        self.assertEqual(between.status_code, 200, between.text)
        late = await self.turn(old)
        self.assertEqual(late.status_code, 200, late.text)
        self.assertEqual((await self.turn(old)).json(), late.json(), "its receipt answers from now on")

    async def test_rolled_back_failures_really_restore_what_the_engine_changed(self):
        before_flags = dict(self.session.world_state.get("flags", {}))
        before_turn = getattr(self.session, "turn_index", None)
        before_xp = self.session.character.get("xp")

        def mutate_then_return(_message, **_kwargs):
            self.calls.append(True)
            self.session.world_state.setdefault("flags", {})["r02_probe"] = True
            self.session.character["xp"] = (before_xp or 0) + 999
            return {"narration": "Bir şey oldu.", "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}

        self.session.run_player_turn = mutate_then_return
        body = self.fresh_body()
        with patch.object(main_module, "serialize_session_state", side_effect=RuntimeError("journal")):
            failed = await self.turn(body)
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertIs(failed.json()["detail"]["not_applied"], True)
        self.assertNotIn("r02_probe", self.session.world_state.get("flags", {}), "the engine's world change was rolled back")
        self.assertEqual(self.session.world_state.get("flags", {}), before_flags)
        self.assertEqual(self.session.character.get("xp"), before_xp, "the engine's character change was rolled back")
        self.assertEqual(getattr(self.session, "turn_index", None), before_turn)
        self.assertEqual(len(self.store.get_campaign(self.created["campaign_id"]).history), 0)

    async def test_engine_time_failure_restores_what_the_engine_changed_before_raising(self):
        before_xp = self.session.character.get("xp")

        def mutate_then_raise(_message, **_kwargs):
            self.session.world_state.setdefault("flags", {})["r02_probe"] = True
            self.session.character["xp"] = (before_xp or 0) + 999
            raise RuntimeError("engine blew up after changing state")

        self.session.run_player_turn = mutate_then_raise
        failed = await self.turn(self.fresh_body())
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertIs(failed.json()["detail"]["not_applied"], True)
        self.assertNotIn("r02_probe", self.session.world_state.get("flags", {}))
        self.assertEqual(self.session.character.get("xp"), before_xp)

    async def test_lore_authority_state_is_restored_on_engine_time_and_post_engine_failures(self):
        record = self.manager.get(self.created["session_id"])
        expected = record.lore_authority

        def tamper_then_raise(_message, **_kwargs):
            self.session.campaign_lore_state = "TAMPERED"
            raise RuntimeError("engine blew up after touching the lore state")

        self.session.run_player_turn = tamper_then_raise
        engine_time = await self.turn(self.fresh_body())
        self.assertEqual(engine_time.status_code, 500, engine_time.text)
        self.assertIsNot(self.session.campaign_lore_state, "TAMPERED")
        self.assertIs(self.session.campaign_lore_state, expected)

        def tamper_then_succeed(_message, **_kwargs):
            self.session.campaign_lore_state = "TAMPERED"
            return {"narration": "Bir şey oldu.", "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}

        self.session.run_player_turn = tamper_then_succeed
        with patch.object(main_module, "serialize_session_state", side_effect=RuntimeError("journal")):
            post_engine = await self.turn(self.fresh_body())
        self.assertEqual(post_engine.status_code, 500, post_engine.text)
        self.assertIsNot(self.session.campaign_lore_state, "TAMPERED")
        self.assertIs(self.session.campaign_lore_state, expected)

    # --- the refusal record must be as durable as a receipt: restart, a new session record, a late arrival ---

    async def resumed_app(self):
        reloaded = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        resumed_id, *_ = reloaded.resume_campaign(self.created["campaign_id"])
        resumed_session = reloaded.get(resumed_id).game_session
        calls = []
        resumed_session.run_player_turn = lambda *_a, **_k: (calls.append(True), {
            "narration": "Kapıdan hafif bir ses geliyor.",
            "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}})[1]
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        app = create_app(session_manager=reloaded, ollama_adapter=adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        self.addAsyncCleanup(client.aclose)
        return client, resumed_id, resumed_session, calls

    async def test_a_refusal_survives_a_restart_and_a_new_session_record(self):
        body = {"message": "Kapıyı dinliyorum.", "action_id": str(uuid.uuid4()),
                "combat_id": "combat-x", "combat_round": 1, "combat_turn_index": 0}
        first = await self.turn(body)
        self.assertEqual(first.status_code, 409, first.text)
        self.assertIs(first.json()["detail"]["not_applied"], True)

        client, resumed_id, resumed_session, calls = await self.resumed_app()
        # In the new record the combat context the refused request named is true, so a fresh evaluation WOULD apply it.
        resumed_session.world_state["combat"] = {"active": True, "combat_id": "combat-x", "round": 1, "current_turn_index": 0}
        late = await client.post(f"/api/game/sessions/{resumed_id}/turn", json=body)
        self.assertEqual(late.status_code, 409, late.text)
        self.assertEqual(late.json()["detail"]["code"], "stale_combat")
        self.assertIs(late.json()["detail"]["not_applied"], True)
        self.assertEqual(calls, [], "the refused action id stays closed in every later session record")

    async def test_a_rolled_back_engine_failure_is_also_durable(self):
        def boom(_message, **_kwargs):
            raise RuntimeError("engine blew up")

        self.session.run_player_turn = boom
        body = self.fresh_body()
        failed = await self.turn(body)
        self.assertIs(failed.json()["detail"]["not_applied"], True)
        client, resumed_id, _session, calls = await self.resumed_app()
        again = await client.post(f"/api/game/sessions/{resumed_id}/turn", json=body)
        self.assertEqual(again.status_code, 500, again.text)
        self.assertIs(again.json()["detail"]["not_applied"], True)
        self.assertEqual(calls, [])

    async def test_a_refusal_never_closes_the_same_id_in_another_campaign(self):
        def boom(_message, **_kwargs):
            raise RuntimeError("engine blew up")

        self.session.run_player_turn = boom
        body = self.fresh_body()
        self.assertEqual((await self.turn(body)).status_code, 500)
        other = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(other.status_code, 200, other.text)
        other_session = self.manager.get(other.json()["session_id"]).game_session
        other_calls = []
        other_session.run_player_turn = lambda *_a, **_k: (other_calls.append(True), {
            "narration": "Başka kampanya.",
            "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}})[1]
        reply = await self.http.post(f"/api/game/sessions/{other.json()['session_id']}/turn", json=body)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(len(other_calls), 1, "an unrelated campaign is never blocked by another campaign's refusal")

    async def test_a_refusal_without_a_durable_record_makes_no_never_applied_claim(self):
        def boom(_message, **_kwargs):
            raise RuntimeError("engine blew up")

        self.session.run_player_turn = boom
        with patch.object(self.manager, "record_refused_action", side_effect=RuntimeError("disk full")):
            failed = await self.turn(self.fresh_body())
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertNotIn("not_applied", failed.json()["detail"], "no durable record, no claim")

    async def test_the_live_refusal_body_matches_the_contract_fixture_the_client_tests_use(self):
        import json
        fixture = json.loads((Path(__file__).parent / "fixtures" / "r02_refusal_409.json").read_text(encoding="utf-8"))
        body = {"message": "Kapıyı dinliyorum.", "action_id": str(uuid.uuid4()),
                "combat_id": "combat-x", "combat_round": 1, "combat_turn_index": 0}
        live = await self.turn(body)
        self.assertEqual(live.status_code, fixture["status"])
        self.assertEqual(live.json(), fixture["body"], "the client contract fixture must be the real backend body")

    async def test_a_new_tab_or_relogin_finds_the_committed_move_in_the_authoritative_history(self):
        body = {"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())}
        committed = await self.turn(body)  # the reply is lost and the tab (with its pending id) is gone
        self.assertEqual(committed.status_code, 200, committed.text)
        client, _resumed_id, _session, calls = await self.resumed_app()
        detail = await client.get(f"/api/game/campaigns/{self.created['campaign_id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        history = detail.json()["history"]
        self.assertTrue(any(entry["player_message"] == body["message"] for entry in history),
                        "without any browser record the server history still shows the move, so the player can decide with facts")
        self.assertEqual(calls, [])

    async def test_a_receipt_can_never_be_committed_for_an_action_id_that_was_durably_refused(self):
        # Simulates a second worker that already passed its own refusal check: the database itself must refuse.
        body = {"message": "Kapıyı dinliyorum.", "action_id": str(uuid.uuid4()),
                "combat_id": "combat-x", "combat_round": 1, "combat_turn_index": 0}
        self.assertEqual((await self.turn(body)).status_code, 409)
        self.assertIsNotNone(self.store.get_refused_action(self.created["campaign_id"], body["action_id"], principal=TEST_PLAYER))

        self.session.world_state["combat"] = {"active": False}
        # Same body and id again, with the in-process refusal check and the combat precheck bypassed.
        with patch.object(self.manager, "get_refused_action", return_value=None),                 patch.object(main_module.combat_lifecycle, "validate_request", return_value=None):
            late = await self.turn(body)
        self.assertNotEqual(late.status_code, 200, "the receipt commit must be refused by the database, not only by the in-process check")
        self.assertIsNone(self.store.get_turn_action(self.created["campaign_id"], body["action_id"], principal=TEST_PLAYER))
        self.assertEqual(len(self.store.get_campaign(self.created["campaign_id"]).history), 0)


if __name__ == "__main__":
    unittest.main()

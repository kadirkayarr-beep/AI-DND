"""B1 (step 0): failures around the save boundary, proven one seam at a time before any fix.

Real FastAPI app, real SessionManager and a temporary SQLite campaign store; the model boundary is the
FakeOllamaClient and the engine turn is a small fake where a test needs one. Each seam is injected where it really is:
before the save (response build, save refused before its transaction), after the SQL commit but before the session's
revision token moves, and after the save has returned. The owner's real saves and keys are never read.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
import unittest
import uuid
from unittest.mock import patch

import httpx

import front_proposal
import game
import quest_catalog
import world_reactions
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient

_TRANSIENTS = ("_handed_note", "_coin_paid", "_front_coin", "_bribe_held_out", "_counter_held")
_FRONT_ON = {front_proposal.FLAG: "1", front_proposal.ROUTE_LOG: ""}


def runtime_facts(session: Any) -> dict[str, Any]:
    """Everything the rollback snapshot promises to give back, as plain data: no secrets, no logs."""
    return {
        "save": json.loads(json.dumps(session.serialize_game_state(), ensure_ascii=False, default=str)),
        "character": copy.deepcopy(session.character),
        "rng": session.rng.getstate(),
        "messages": copy.deepcopy(session.messages),
        "recent_narrations": copy.deepcopy(session.recent_dm_narrations),
        "pending_xp": copy.deepcopy(getattr(session, "_xp_level_up", None)),
        "persisted_engine_format": copy.deepcopy(session.__dict__.get("_persisted_engine_format")),
        "persistence_token": getattr(session, "_campaign_persistence_version", None),
    }


def record_facts(record: Any) -> dict[str, Any]:
    return {
        **runtime_facts(record.game_session),
        "journal": copy.deepcopy(record.journal),
        "narrative_memory": copy.deepcopy(record.narrative_memory),
        "lore_authority": record.lore_authority,
    }


class Step0CommitFailureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        # An unhandled server error must come back as a 500 the test can read, not as a raised exception.
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
                                      base_url="http://testserver")
        await self.new_campaign()

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    async def new_campaign(self):
        created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.cid, self.sid = body["campaign_id"], body["session_id"]
        self.record = self.manager.get(self.sid)
        self.session = self.record.game_session

    def durable(self) -> dict[str, Any]:
        stored = self.store.get_campaign(self.cid)
        return {"payload": stored.payload, "revision": stored.metadata["revision"], "history": len(stored.history)}

    def turn(self, message="Kapıyı itiyorum.", action_id=None):
        return self.http.post(f"/api/game/sessions/{self.sid}/turn",
                              json={"message": message, "action_id": action_id or str(uuid.uuid4())})

    def quest_definition(self) -> dict[str, Any]:
        return {
            "quest_id": "quest.step0-boundary",
            "title": "Orman Yolu",
            "description": "Ormana ulaş.",
            "objectives": [{"objective_id": "visit-forest", "description": "Ormana git.",
                            "type": "visit_location", "target": "forest"}],
        }

    def quest_url(self, command: str) -> str:
        return f"/api/game/sessions/{self.sid}/quests/quest.step0-boundary/{command}"

    @staticmethod
    def quest_status(engine_save: dict[str, Any]) -> str | None:
        quests = engine_save.get("world_state", {}).get("quests", [])
        found = [quest for quest in quests if quest.get("quest_id") == "quest.step0-boundary"]
        return found[0]["status"] if found else None

    # --- Step 1: the save boundary -------------------------------------------------------------------------------

    async def test_response_build_failure_restores_live_and_durable(self):
        trusted_before = record_facts(self.record)
        durable_before = self.durable()

        def engine_turn(_message, **_kwargs):
            self.session.rng.random()
            self.session.character["current_hp"] = 1  # the effect that must not outlive the failed answer
            return {"narration": "Kapı gıcırdayarak açılıyor.", "action_result": {}}

        self.session.run_player_turn = engine_turn
        with patch("api.main._turn_outcome", side_effect=RuntimeError("synthetic response build failure")):
            failed = await self.turn()

        self.assertEqual(failed.status_code, 500, failed.text)
        live_after_presave_failure = record_facts(self.record)
        durable_after_presave_failure = self.durable()
        self.assertEqual(live_after_presave_failure, trusted_before)
        self.assertEqual(durable_after_presave_failure, durable_before)
        self.assertTrue(self.record.usable, "a verified pre-commit restore keeps the session open")

    async def test_quest_save_ack_loss_does_not_revert_committed_state(self):
        original_transaction = CampaignStore._transaction

        def commit_then_lose_ack():
            fired = []

            @contextlib.contextmanager
            def transaction(store):
                with original_transaction(store) as connection:
                    yield connection
                if not fired:
                    fired.append(True)
                    raise sqlite3.OperationalError("synthetic: committed, acknowledgement lost")

            return patch.object(CampaignStore, "_transaction", transaction)

        def save_returns_then_fails():
            real_save = self.manager.save_campaign_locked

            def save(record, *args, **kwargs):
                real_save(record, *args, **kwargs)
                raise CampaignStorageError("synthetic: saved, then the answer was lost")

            return patch.object(self.manager, "save_campaign_locked", side_effect=save)

        seams = {
            "after SQL commit, before the revision token moves": commit_then_lose_ack,
            "after the save returned": save_returns_then_fails,
        }
        for seam, fault in seams.items():
            with self.subTest(seam=seam):
                await self.new_campaign()
                with patch.object(quest_catalog, "CATALOG", (self.quest_definition(),)):
                    revision_before = self.durable()["revision"]
                    with fault():
                        answered = await self.http.post(self.quest_url("accept"))
                    durable_after_lost_ack = self.durable()
                    committed_state = durable_after_lost_ack["payload"]["engine_save"]
                    self.assertEqual(durable_after_lost_ack["revision"], revision_before + 1)
                    self.assertEqual(self.quest_status(committed_state), "accepted")
                    # The database holds the accepted quest, so the live game may not be blindly put back before it.
                    self.assertEqual(runtime_facts(self.session)["save"], committed_state, answered.text)
                    self.assertTrue(self.record.usable)
                    self.assertEqual(answered.status_code, 200, answered.text)
                    self.assertEqual(answered.json()["quest"]["status"], "accepted")
                    # A later save and a resume keep the committed quest; nothing older is written back over it.
                    saved = await self.http.post(f"/api/game/campaigns/{self.cid}/save")
                    self.assertEqual(saved.status_code, 200, saved.text)
                    self.assertEqual(self.quest_status(self.durable()["payload"]["engine_save"]), "accepted")
                    resumed = await self.http.post(f"/api/game/campaigns/{self.cid}/resume")
                    self.assertEqual(resumed.status_code, 200, resumed.text)
                    self.assertEqual([q["status"] for q in resumed.json()["state"]["quests"]], ["accepted"])

    async def test_quest_presave_fault_restores_lore(self):
        with patch.object(quest_catalog, "CATALOG", (self.quest_definition(),)):
            lore_before = self.record.lore_authority
            # The engine's own copy of the lore can differ from the record's; the command adopts it for its view.
            self.session.campaign_lore_state = dataclasses.replace(
                lore_before, lore_discoveries=(*lore_before.lore_discoveries, "step0-synthetic-discovery"),
            )
            trusted_before = runtime_facts(self.session)
            durable_before = self.durable()
            with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("synthetic presave fault")):
                failed = await self.http.post(self.quest_url("accept"))

            self.assertEqual(failed.status_code, 503, failed.text)
            self.assertEqual(runtime_facts(self.session), trusted_before)
            self.assertEqual(self.durable(), durable_before)
            self.assertEqual(self.record.lore_authority, lore_before, "a refused save must not leave the adopted lore")
            self.assertTrue(self.record.usable)

    async def test_silent_rng_restore_error_quarantines(self):
        durable_before = self.durable()

        def failing_turn(_message, **_kwargs):
            for _ in range(5):
                self.session.rng.random()
            self.session.character["current_hp"] = 1
            raise RuntimeError("synthetic engine failure after dice were drawn")

        self.session.run_player_turn = failing_turn
        # The restore "succeeds" but leaves the dice where the failed turn put them.
        with patch.object(self.session.rng, "setstate", lambda _state: None):
            failed = await self.turn()

        self.assertGreaterEqual(failed.status_code, 400, failed.text)
        self.assertIs(self.record.usable, False, "an unverified dice restore must close the session")
        self.assertEqual(self.durable(), durable_before)

    # --- Step 2: undo and the turn's passing fields ---------------------------------------------------------------

    async def test_undo_then_old_action_does_not_reapply(self):
        engine_calls = []

        def engine_turn(message, **_kwargs):
            engine_calls.append(message)
            wallets = self.session.world_state.setdefault("currency", {})
            if message == "Keseme bakıyorum.":
                wallets["player"] = 100
            else:
                wallets["player"] = wallets.get("player", 0) - 4
            return {"narration": f"Kese: {wallets['player']} bakır.", "action_result": {}}

        self.session.run_player_turn = engine_turn
        setup = await self.turn("Keseme bakıyorum.")
        self.assertEqual(setup.status_code, 200, setup.text)
        paid_id = str(uuid.uuid4())
        paid = await self.turn("Barmene 4 bakır veriyorum.", paid_id)
        self.assertEqual(paid.status_code, 200, paid.text)
        self.assertEqual(self.session.world_state["currency"]["player"], 96)
        undone = await self.http.post(f"/api/game/sessions/{self.sid}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": paid_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.session.world_state["currency"]["player"], 100)

        old = await self.turn("Barmene 4 bakır veriyorum.", paid_id)
        self.assertEqual(old.status_code, 200, old.text)
        self.assertEqual(old.json(), paid.json(), "the old id answers with its historical receipt")
        self.assertEqual(len(engine_calls), 2, "the old action is not run again")
        self.assertEqual(self.session.world_state["currency"]["player"], 100)
        self.assertEqual(self.durable()["payload"]["engine_save"]["world_state"]["currency"]["player"], 100)

    async def test_failed_front_read_does_not_leak_coin_note(self):
        barman = {"id": "npc_step0_barman", "name": "Barmen"}

        def failing_front_read(*_args, **_kwargs):
            # What a reading leaves behind once it has seen coin leave the hand, before it fails.
            self.session._front_ahead = True
            self.session._front_coin = 5
            self.session._coin_paid = (5, barman)
            self.session._handed_note = "5 bakır"
            self.session._counter_held = barman
            self.session._bribe_held_out = 5
            raise RuntimeError("synthetic front read failure")

        self.session.front_read_ahead = failing_front_read
        with patch.dict(os.environ, _FRONT_ON):
            failed = await self.turn("Barmene beş bakır uzatıyorum.")
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual({name: getattr(self.session, name, None) for name in _TRANSIENTS if getattr(self.session, name, None)},
                         {}, "nothing from the failed reading is left for the next action")

        seen = {}

        def typed_turn(_message, **_kwargs):
            seen.update({name: getattr(self.session, name, None) for name in _TRANSIENTS})
            return {"narration": "Çantanda bir şey değişmedi.", "action_result": {}}

        self.session.run_player_turn = typed_turn
        environment = {key: value for key, value in os.environ.items() if key != front_proposal.FLAG}
        with patch.dict(os.environ, environment, clear=True):
            typed = await self.turn("/item list")
        self.assertEqual(typed.status_code, 200, typed.text)
        self.assertEqual({name: value for name, value in seen.items() if value}, {})

    async def test_bribe_held_out_does_not_survive_combat_turn(self):
        session = self.session

        def combat_turn(*_args, **_kwargs):
            session._bribe_held_out = 40  # the reading saw coin held out to the guard making an arrest
            world = session.world_state
            combat_before = copy.deepcopy(world.get("combat"))
            world["combat"] = {**(combat_before or {}), "active": True}
            result = {"narration": "Kılıçlar çekiliyor.", "action_result": {}}
            world_reactions.answer(session, result)  # in a fight it returns at once and settles no law
            if combat_before is None:
                world.pop("combat", None)
            else:
                world["combat"] = combat_before
            return result

        with patch.dict(os.environ, _FRONT_ON), patch.object(game, "_run_player_turn", combat_turn):
            session.run_player_turn("Muhafıza kırk bakır uzatıp kılıcımı çekiyorum.")

        self.assertFalse(getattr(session, "_bribe_held_out", 0), "the held-out coin ended with its turn")
        with patch.object(world_reactions, "arrester", return_value={"id": "npc_step0_guard"}), \
                patch.object(world_reactions, "bribe", return_value=["rüşvet"]) as bribe:
            world_reactions._settle_the_law(session)
        bribe.assert_not_called()


if __name__ == "__main__":
    unittest.main()

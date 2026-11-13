"""Which source wrote each saved turn's narration: the `campaign_history_sources` sidecar.

The strict `campaign_history` rows never change. The source is kept beside them by sequence, in the same
transaction, and read back as an optional `narration_source` key. A row saved before this record existed has no
sidecar row and comes back without the key. Temporary SQLite only.
"""

from __future__ import annotations

import ast
import copy
import sqlite3
import unittest
import uuid
from functools import wraps
from pathlib import Path
from unittest.mock import patch

import httpx

import game
from api.auth import FixedAuthenticator
from api.history_view import UNDO_HISTORY_MARKER
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence import campaign_store
from api.persistence.campaign_models import CampaignStaleError, CampaignValidationError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_ambient_actions as ambient
from api.tests import test_campaign_api
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.journeys.runner import _campaign_seeded
from api.tests.test_campaign_api import FakeOllamaClient, create_city_with_locked_tavern
from api.tests.test_economic_action_http import TIP, EconomicHttpFixture
from api.tests.test_owner_play1 import OwnerPlayBase
from api.tests.test_spell_preparation_4c2 import prepper
from api.tests.town_seed import fixed_town

ENGINE_SOURCES = {"qwen", "python_memory_response", "deterministic_fallback", "deterministic_system"}
SIDECAR = "campaign_history_sources"
# Every table the store made before this record existed (schema version 6); the old-database test rebuilds exactly this.
V6_TABLES = {
    "campaigns", "campaign_history", "campaign_combat_history", "campaign_turn_actions",
    "campaign_emergence_attempts", "campaign_turn_actions_archive", "campaign_refused_actions",
    "campaign_action_intents",
}


def saved_rows(path, campaign_id):
    """(sequence, player line, saved source or None) straight from the file, bound by sequence."""
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            f"""SELECT h.sequence, h.player_message, s.narration_source
                FROM campaign_history h LEFT JOIN {SIDECAR} s
                  ON s.campaign_id = h.campaign_id AND s.sequence = h.sequence
                WHERE h.campaign_id = ? ORDER BY h.sequence""", (campaign_id,)).fetchall()
    finally:
        connection.close()


def tables(path):
    connection = sqlite3.connect(path)
    try:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()


def user_version(path):
    connection = sqlite3.connect(path)
    try:
        return connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()


class TypedTurnSource(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        with _campaign_seeded({"campaign_seed": 1}):
            _, self.session_id, _, self.turn_url, _, _ = await create_city_with_locked_tavern(self)
        self.campaign_id = self.manager.get(self.session_id).campaign_id

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    def history(self, store=None):
        return (store or self.store).get_campaign(self.campaign_id).history

    async def turn(self, message="Etrafıma bakıyorum.", *, forced=None, http=None, url=None, session=None):
        """Play one typed turn; return (action id, response, the source the engine reported for it).

        `forced` replaces the engine's reported source ("absent" removes the engine evidence whole).
        """
        session = session or self.manager.get(self.session_id).game_session
        real_turn = session.run_player_turn
        reported = []

        @wraps(real_turn)
        def observed(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            if forced == "absent":
                result.pop("_engine_event_evidence", None)
            elif forced is not None:
                result["_engine_event_evidence"]["telemetry"]["narration_source"] = forced[0]
            evidence = result.get("_engine_event_evidence") or {}
            reported.append(copy.deepcopy((evidence.get("telemetry") or {}).get("narration_source")))
            return result

        action_id = str(uuid.uuid4())
        with patch.object(session, "run_player_turn", new=observed):
            response = await (http or self.http).post(
                url or self.turn_url, json={"message": message, "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(reported), 1)
        return action_id, response.json(), reported[0]

    async def undo(self, target):
        response = await self.http.post(f"/api/game/sessions/{self.session_id}/undo", json={
            "action_id": str(uuid.uuid4()), "target_action_id": target})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_a_typed_turn_saves_the_source_the_engine_reported(self):
        _, played, reported = await self.turn()
        self.assertIn(reported, ENGINE_SOURCES)
        row = self.history()[-1]
        self.assertEqual(row["narration"], played["narration"])
        self.assertEqual(row["narration_source"], reported)
        # The turn answer itself is unchanged: the source is a history record, not a turn field.
        self.assertNotIn("narration_source", played)
        detail = await self.http.get(f"/api/game/campaigns/{self.campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["history"][-1]["narration_source"], reported)

    async def test_a_turn_the_engine_reports_no_source_for_saves_none(self):
        # Some engine routes (this walk among them) hand back no telemetry; nothing is guessed for them.
        _, played, reported = await self.turn("Tapınağa gidiyorum.")
        self.assertIsNone(reported)
        row = self.history()[-1]
        self.assertEqual(row["narration"], played["narration"])
        self.assertNotIn("narration_source", row)
        self.assertIsNone(saved_rows(self.store.path, self.campaign_id)[-1][2])

    async def test_a_replayed_action_answers_alike_and_another_body_is_refused_with_rows_unchanged(self):
        action_id, played, reported = await self.turn()
        rows = saved_rows(self.store.path, self.campaign_id)
        self.assertEqual(rows[-1][2], reported)
        replay = await self.http.post(self.turn_url, json={"message": "Etrafıma bakıyorum.", "action_id": action_id})
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), played)
        self.assertEqual(saved_rows(self.store.path, self.campaign_id), rows)
        other = await self.http.post(self.turn_url, json={"message": "Tapınağa gidiyorum.", "action_id": action_id})
        self.assertEqual(other.status_code, 409, other.text)
        self.assertEqual(other.json()["detail"]["code"], "action_id_conflict")
        self.assertEqual(saved_rows(self.store.path, self.campaign_id), rows)
        self.assertEqual(self.history()[-1]["narration_source"], reported)

    async def test_each_engine_value_is_kept_as_reported(self):
        for source in sorted(ENGINE_SOURCES):
            with self.subTest(source=source):
                _, _, reported = await self.turn(forced=(source,))
                self.assertEqual(reported, source)
                self.assertEqual(self.history()[-1]["narration_source"], source)

    async def test_an_unknown_or_missing_source_never_fails_the_turn_and_saves_no_source(self):
        for forced in (("gpt-9",), ("",), (None,), (7,), ({"qwen": 1},), (["qwen"],), "absent"):
            with self.subTest(forced=forced):
                before = len(saved_rows(self.store.path, self.campaign_id))
                _, played, _ = await self.turn(forced=forced)
                rows = saved_rows(self.store.path, self.campaign_id)
                self.assertEqual(len(rows), before + 1)
                self.assertIsNone(rows[-1][2])
                last = self.history()[-1]
                self.assertEqual(last["narration"], played["narration"])
                self.assertNotIn("narration_source", last)

    async def test_undo_keeps_every_source_on_its_own_row_and_survives_a_reload(self):
        first_id, _, first_source = await self.turn()
        first_sequence = saved_rows(self.store.path, self.campaign_id)[-1][0]
        await self.undo(first_id)
        _, _, second_source = await self.turn(forced=("python_memory_response",))
        rows = saved_rows(self.store.path, self.campaign_id)
        self.assertEqual(
            [(sequence, source) for sequence, _, source in rows[-3:]],
            [(first_sequence, first_source), (first_sequence + 1, "deterministic_system"),
             (first_sequence + 2, second_source)],
        )
        self.assertEqual(rows[-2][1], UNDO_HISTORY_MARKER)
        self.assertNotEqual(first_source, second_source)  # the rows are told apart by their own value
        undone, marker, after = self.history()[-3:]
        self.assertEqual((undone.get("undone"), undone["narration_source"]), (True, first_source))
        self.assertEqual((marker.get("undo_note"), marker["narration_source"]), (True, "deterministic_system"))
        self.assertEqual((after.get("undone"), after["narration_source"]), (None, second_source))
        # No sidecar row without its history row.
        connection = sqlite3.connect(self.store.path)
        try:
            orphans = connection.execute(
                f"""SELECT COUNT(*) FROM {SIDECAR} s WHERE NOT EXISTS (
                    SELECT 1 FROM campaign_history h
                    WHERE h.campaign_id = s.campaign_id AND h.sequence = s.sequence)""").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(orphans, 0)
        # A reload from disk reads the same story with the same sources.
        reopened = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        self.assertEqual(self.history(reopened), self.history())
        manager = SessionManager(campaign_store=reopened)
        app = create_app(session_manager=manager, ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
            resumed = await http.post(f"/api/game/campaigns/{self.campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(
            [row.get("narration_source") for row in resumed.json()["history"][-3:]],
            [first_source, "deterministic_system", second_source],
        )

    async def test_a_database_saved_before_the_record_loads_as_before_and_only_new_turns_get_a_source(self):
        await self.turn()
        path = self.store.path
        # Back to the file the earlier code wrote: the sidecar is the only thing this record added.
        connection = sqlite3.connect(path)
        try:
            connection.execute(f"DROP TABLE IF EXISTS {SIDECAR}")
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(tables(path), V6_TABLES)
        self.assertEqual(user_version(path), 6)
        old_rows = saved_rows_without_sidecar(path, self.campaign_id)
        self.assertGreaterEqual(len(old_rows), 2)

        # Opened like a running server opens it: no migration approval is given.
        store = CampaignStore(path, bound_principal=TEST_PLAYER)
        self.assertEqual(user_version(path), 6)
        self.assertEqual(tables(path), V6_TABLES | {SIDECAR})
        loaded = store.get_campaign(self.campaign_id).history
        self.assertEqual([(row["player_message"], row["narration"]) for row in loaded],
                         [(message, narration) for _, message, narration in old_rows])
        for row in loaded:
            self.assertNotIn("narration_source", row)

        manager = SessionManager(campaign_store=store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        app = create_app(session_manager=manager, ollama_adapter=adapter,
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
            resumed = await http.post(f"/api/game/campaigns/{self.campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(len(resumed.json()["history"]), len(old_rows))
            for row in resumed.json()["history"]:
                self.assertNotIn("narration_source", row)
            session_id = resumed.json()["session_id"]
            _, _, reported = await self.turn(
                http=http, url=f"/api/game/sessions/{session_id}/turn",
                session=manager.get(session_id).game_session)
            detail = await http.get(f"/api/game/campaigns/{self.campaign_id}")
        self.assertIn(reported, ENGINE_SOURCES)
        history = detail.json()["history"]
        self.assertEqual(len(history), len(old_rows) + 1)
        for row in history[:-1]:
            self.assertNotIn("narration_source", row)
        self.assertEqual(history[-1]["narration_source"], reported)
        self.assertEqual([source for _, _, source in saved_rows(path, self.campaign_id)],
                         [None] * len(old_rows) + [reported])

    async def test_a_stored_value_outside_the_list_is_not_shown(self):
        await self.turn()
        sequence = saved_rows(self.store.path, self.campaign_id)[-1][0]
        connection = sqlite3.connect(self.store.path)
        try:
            connection.execute(f"UPDATE {SIDECAR} SET narration_source = 'someone-else' WHERE sequence = ?",
                               (sequence,))
            connection.commit()
        finally:
            connection.close()
        self.assertNotIn("narration_source", self.history()[-1])

    async def test_deleting_the_campaign_deletes_its_sources(self):
        await self.turn()
        self.assertTrue(self.store.delete_campaign(self.campaign_id))
        connection = sqlite3.connect(self.store.path)
        try:
            self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {SIDECAR}").fetchone()[0], 0)
        finally:
            connection.close()


def saved_rows_without_sidecar(path, campaign_id):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT sequence, player_message, narration FROM campaign_history WHERE campaign_id = ? "
            "ORDER BY sequence", (campaign_id,)).fetchall()
    finally:
        connection.close()


class CardSource(EconomicHttpFixture):
    """A card step is told by Python alone (economic_actions never calls a model)."""

    async def test_prepare_confirm_cancel_and_undo_rows_are_engine_rows(self):
        card = await self.card(**TIP)
        confirmed, body = await self.confirm(card)
        self.assertEqual(confirmed["economic_resolution"]["status"], "applied")
        undone = await self.undo(body["action_id"])
        self.assertEqual(undone.status_code, 200, undone.text)
        await self.cancel(card["offer_id"])
        rows = saved_rows(self.store.path, self.campaign["campaign_id"])[-4:]
        self.assertEqual([message for _, message, _ in rows],
                         ["Teklif hazırla", "Teklifi onayla", UNDO_HISTORY_MARKER, "Teklifi iptal et"])
        self.assertEqual([source for _, _, source in rows], ["deterministic_system"] * 4)
        self.assertEqual([sequence for sequence, _, _ in rows], list(range(rows[0][0], rows[0][0] + 4)))
        history = self.store.get_campaign(self.campaign["campaign_id"]).history[-4:]
        self.assertEqual([row.get("undone") for row in history], [None, True, None, None])
        self.assertEqual([row["narration_source"] for row in history], ["deterministic_system"] * 4)


class CommandSource(unittest.IsolatedAsyncioTestCase):
    """Species actions and spell preparation answer with the engine's own message."""

    asyncSetUp = test_campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = test_campaign_api.CampaignApiTests.asyncTearDown

    async def campaign(self):
        with fixed_town(self, 4301):
            response = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_a_species_action_row_is_an_engine_row(self):
        created = await self.campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.character.update({"species": "Aasimar", "race": "Aasimar", "level": 3, "proficiency_bonus": 2,
                                  "current_hp": 1, "max_hp": 20, "charisma_mod": 1})
        session.initialize_species_trait_state()
        with patch.object(session.rng, "randint", return_value=1):
            response = await self.http.post(f"/api/game/sessions/{created['session_id']}/species-actions",
                                            json={"action": "healing_hands"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(saved_rows(self.store.path, created["campaign_id"])[-1][1:],
                         ("healing_hands", "deterministic_system"))

    async def test_a_spell_preparation_row_is_an_engine_row(self):
        import campaign_time
        created = await self.campaign()
        session = self.manager.get(created["session_id"]).game_session
        campaign_time.initialize(session.world_state)
        prepper("Wizard", session)
        response = await self.http.post(f"/api/game/sessions/{created['session_id']}/spellcasting/prepare",
                                        json={"action_id": str(uuid.uuid4()), "prepared": ["Magic Missile"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(saved_rows(self.store.path, created["campaign_id"])[-1][1:],
                         ("spell_prepare", "deterministic_system"))


class JoinedEventSource(OwnerPlayBase):
    """A joined ambient event is told by `ambient_actions.resolve` from the scene's own description."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.base_world = copy.deepcopy(self.world)
        self.base_journal = copy.deepcopy(self.record.journal)

    record = ambient.AmbientActionsTests.record
    live_session = ambient.AmbientActionsTests.live_session
    stage = ambient.AmbientActionsTests.stage
    state = ambient.AmbientActionsTests.state
    state_with_event = ambient.AmbientActionsTests.state_with_event
    click = ambient.AmbientActionsTests.click
    undo = ambient.AmbientActionsTests.undo

    async def test_the_click_row_and_its_undo_are_engine_rows(self):
        await self.state_with_event()
        click = await self.click("interact")
        self.assertEqual(click["result"]["status"], "APPLIED")
        self.assertEqual((await self.undo(target_action_id=click["result"]["action_id"])).status_code, 200)
        rows = saved_rows(self.store.path, self.record.campaign_id)[-2:]
        self.assertEqual([(message, source) for _, message, source in rows],
                         [("Yanlarına gidiyorum.", "deterministic_system"),
                          (UNDO_HISTORY_MARKER, "deterministic_system")])
        story = self.store.get_campaign(self.record.campaign_id).history[-2:]
        self.assertEqual([(row.get("undone"), row.get("undo_note"), row["narration_source"]) for row in story],
                         [(True, None, "deterministic_system"), (None, True, "deterministic_system")])


class WriterBoundary(unittest.IsolatedAsyncioTestCase):
    """The save itself: a value outside the list writes the turn and no source."""

    asyncSetUp = test_campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = test_campaign_api.CampaignApiTests.asyncTearDown

    async def test_autosave_ignores_values_outside_the_list(self):
        with fixed_town(self, 4311):
            created = (await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})).json()
        record = self.manager.get(created["session_id"])
        for value, saved in (("qwen", "qwen"), ("QWEN", None), ("drop table", None), (None, None), (3, None),
                             ({"a": 1}, None), ("deterministic_system", "deterministic_system")):
            with self.subTest(value=value):
                with record.turn_lock:
                    self.manager.autosave_turn(record, "satır", "anlatı", narration_source=value)
                self.assertEqual(saved_rows(self.store.path, created["campaign_id"])[-1][1:], ("satır", saved))
        # Left out, as every caller did before: the turn is saved and no source is.
        with record.turn_lock:
            self.manager.autosave_turn(record, "eski çağrı", "anlatı")
        self.assertEqual(saved_rows(self.store.path, created["campaign_id"])[-1][1:], ("eski çağrı", None))

    async def started(self, seed):
        with fixed_town(self, seed):
            created = (await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})).json()
        return created["campaign_id"], self.manager.get(created["session_id"])

    def receipt(self, action_id=None):
        action_id = action_id or str(uuid.uuid4())
        return {"action_id": action_id, "request_hash": "a" * 64, "response": {"action_id": action_id}}

    async def test_a_save_refused_after_both_rows_were_written_keeps_them_in_step(self):
        campaign_id, record = await self.started(4312)
        with record.turn_lock:
            self.manager.autosave_turn(record, "ilk", "anlatı", narration_source="qwen")
        before = saved_rows(self.store.path, campaign_id)
        revision = self.store.get_campaign(campaign_id).metadata["revision"]
        # A durably refused action id is only seen after the history row and its source row are written.
        refused = self.receipt()
        self.assertTrue(self.store.record_refused_action(
            campaign_id, refused["action_id"], refused["request_hash"], 409, {"code": "x", "message": "x"}))
        with record.turn_lock, self.assertRaises(CampaignStaleError):
            self.manager.autosave_turn(record, "reddedilen", "anlatı", turn_action_receipt=refused,
                                       narration_source="python_memory_response")
        self.assertEqual(saved_rows(self.store.path, campaign_id), before)
        self.assertEqual(self.store.get_campaign(campaign_id).metadata["revision"], revision)
        with record.turn_lock:
            self.manager.autosave_turn(record, "sonraki", "anlatı", narration_source="deterministic_fallback")
        self.assertEqual(saved_rows(self.store.path, campaign_id),
                         [*before, (before[-1][0] + 1, "sonraki", "deterministic_fallback")])

    async def test_a_second_save_under_a_committed_action_id_writes_nothing(self):
        campaign_id, record = await self.started(4313)
        receipt = self.receipt()
        with record.turn_lock:
            self.manager.autosave_turn(record, "ilk", "anlatı", turn_action_receipt=receipt, narration_source="qwen")
        before = saved_rows(self.store.path, campaign_id)
        self.assertEqual(before[-1][1:], ("ilk", "qwen"))
        with record.turn_lock, self.assertRaises(CampaignValidationError):
            self.manager.autosave_turn(record, "ikinci", "anlatı",
                                       turn_action_receipt=self.receipt(receipt["action_id"]),
                                       narration_source="deterministic_system")
        self.assertEqual(saved_rows(self.store.path, campaign_id), before)

    async def test_a_session_without_a_campaign_keeps_working(self):
        response = await self.http.post("/api/sessions")
        self.assertEqual(response.status_code, 200, response.text)
        record = self.manager.get(response.json()["session_id"])
        self.assertIsNone(record.campaign_id)
        with record.turn_lock:
            self.assertIsNone(self.manager.autosave_turn(record, "satır", "anlatı", narration_source="qwen"))


def drop_source_table(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"DROP TABLE {SIDECAR}")
        connection.commit()
    finally:
        connection.close()


class FileWithoutTheSourceTable(unittest.IsolatedAsyncioTestCase):
    """The file under an already open store has no source table (an older file put in its place while the server
    runs): the adventure still loads, without sources, and the next save still lands."""

    asyncSetUp = TypedTurnSource.asyncSetUp
    asyncTearDown = TypedTurnSource.asyncTearDown
    history = TypedTurnSource.history
    turn = TypedTurnSource.turn

    def plain_rows(self):
        return saved_rows_without_sidecar(self.store.path, self.campaign_id)

    async def test_the_adventure_loads_without_sources(self):
        _, played, reported = await self.turn()
        self.assertEqual(self.history()[-1]["narration_source"], reported)
        drop_source_table(self.store.path)
        self.assertNotIn(SIDECAR, tables(self.store.path))
        # The same open store, the normal read path.
        stored = self.store.get_campaign(self.campaign_id)
        self.assertEqual([(row["player_message"], row["narration"]) for row in stored.history],
                         [(message, narration) for _, message, narration in self.plain_rows()])
        self.assertEqual(stored.history[-1]["narration"], played["narration"])
        for row in stored.history:
            self.assertNotIn("narration_source", row)
        # The HTTP history route and a resume.
        detail = await self.http.get(f"/api/game/campaigns/{self.campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(len(detail.json()["history"]), len(stored.history))
        for row in detail.json()["history"]:
            self.assertNotIn("narration_source", row)
        resumed = await self.http.post(f"/api/game/campaigns/{self.campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(len(resumed.json()["history"]), len(stored.history))
        # Reading wrote nothing: the table is still absent.
        self.assertNotIn(SIDECAR, tables(self.store.path))

    async def test_a_turn_still_saves_and_its_source_is_kept_from_then_on(self):
        await self.turn()
        drop_source_table(self.store.path)
        old = self.plain_rows()
        _, played, reported = await self.turn()
        self.assertIn(reported, ENGINE_SOURCES)
        self.assertEqual(len(self.plain_rows()), len(old) + 1)
        self.assertEqual(saved_rows(self.store.path, self.campaign_id),
                         [*((sequence, message, None) for sequence, message, _ in old),
                          (old[-1][0] + 1, "Etrafıma bakıyorum.", reported)])
        history = self.history()
        self.assertEqual(history[-1]["narration"], played["narration"])
        self.assertEqual(history[-1]["narration_source"], reported)
        for row in history[:-1]:
            self.assertNotIn("narration_source", row)

    async def test_a_save_without_a_source_lands_and_leaves_the_file_as_it_was(self):
        await self.turn()
        drop_source_table(self.store.path)
        before = len(self.plain_rows())
        record = self.manager.get(self.session_id)
        with record.turn_lock:
            self.manager.autosave_turn(record, "satır", "anlatı")
        self.assertEqual(len(self.plain_rows()), before + 1)
        self.assertNotIn(SIDECAR, tables(self.store.path))
        self.assertNotIn("narration_source", self.history()[-1])

    async def test_a_refused_save_does_not_leave_the_table_behind(self):
        await self.turn()
        drop_source_table(self.store.path)
        before = self.plain_rows()
        record = self.manager.get(self.session_id)
        action_id = str(uuid.uuid4())
        self.assertTrue(self.store.record_refused_action(
            self.campaign_id, action_id, "a" * 64, 409, {"code": "x", "message": "x"}))
        with record.turn_lock, self.assertRaises(CampaignStaleError):
            self.manager.autosave_turn(
                record, "reddedilen", "anlatı", narration_source="qwen",
                turn_action_receipt={"action_id": action_id, "request_hash": "a" * 64,
                                     "response": {"action_id": action_id}})
        self.assertEqual(self.plain_rows(), before)
        self.assertNotIn(SIDECAR, tables(self.store.path))


def reported_sources(source):
    """Every string literal a module gives `narration_source`: assigned to a name `narration_source` or
    `narration_src`, set under the dict key "narration_source", or passed as that keyword."""
    names = {"narration_source", "narration_src"}
    found = set()
    for node in ast.walk(ast.parse(source)):
        values = []
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id in names for target in node.targets):
                values.append(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id in names and node.value is not None:
                values.append(node.value)
        elif isinstance(node, ast.Dict):
            values.extend(value for key, value in zip(node.keys, node.values)
                          if isinstance(key, ast.Constant) and key.value == "narration_source")
        elif isinstance(node, ast.keyword) and node.arg in names:
            values.append(node.value)
        for value in values:
            # A conditional expression gives either arm; a name (the variable itself) is read at its own assignment.
            for part in ast.walk(value):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    found.add(part.value)
    return found


ENGINE_ROOT = Path(game.__file__).resolve().parent
# The two engine modules that write turn telemetry (`_engine_event_evidence`): game.py sets the source in
# `_narrate_resolved_turn` and `_run_player_turn_internal`, dialogue_runtime.py in its free-dialogue result.
# Scanned: literals assigned to `narration_source` / `narration_src`, the dict key "narration_source", and
# that keyword argument. `test_no_other_engine_module_reports_a_source` keeps this pair complete.
ENGINE_REPORTERS = ("game.py", "dialogue_runtime.py")


class TheListIsTheEngines(unittest.TestCase):
    """The store keeps exactly the values the engine can report: a new engine value must be decided here first."""

    def engine_values(self, extra_source=""):
        found = set()
        for name in ENGINE_REPORTERS:
            found |= reported_sources((ENGINE_ROOT / name).read_text(encoding="utf-8"))
        return found | reported_sources(extra_source)

    def test_the_store_list_equals_what_the_engine_reports(self):
        self.assertEqual(self.engine_values(), set(campaign_store._NARRATION_SOURCES))
        self.assertEqual(ENGINE_SOURCES, set(campaign_store._NARRATION_SOURCES))

    def test_the_scan_sees_each_way_a_value_is_written(self):
        for line in ('narration_source = "x"', 'narration_src = "x"', 'narration_source: str = "x"',
                     't = {"narration_source": "x"}', 'f(narration_source="x")',
                     'narration_source = "x" if a else "y"'):
            with self.subTest(line=line):
                self.assertIn("x", reported_sources(line))
        self.assertEqual(reported_sources('narration_source = "x" if a else "y"'), {"x", "y"})
        self.assertEqual(reported_sources('other = "x"\nt = {"intent_source": "x"}'), set())
        # A value the engine does not report today would break the equality above.
        self.assertNotEqual(self.engine_values('narration_source = "a_new_engine_value"'),
                            set(campaign_store._NARRATION_SOURCES))

    def test_no_other_engine_module_reports_a_source(self):
        # Engine code only (the API layer passes the engine's values on; tests and evidence scripts read them).
        skipped = {"api", "docs", "scripts", "reports", "legacy_debug", "saves"}
        mentioning = set()
        for path in ENGINE_ROOT.rglob("*.py"):
            relative = path.relative_to(ENGINE_ROOT)
            if relative.parts[0] in skipped or path.name.startswith(("test_", "live_")) or "tests" in relative.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "narration_source" in text or "narration_src" in text:
                mentioning.add(relative.as_posix())
        self.assertEqual(mentioning, set(ENGINE_REPORTERS))


if __name__ == "__main__":
    unittest.main()

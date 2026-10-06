"""Persistence boundaries missing from the existing subsystem/CTM suites."""
import copy
import asyncio
from contextlib import closing, ExitStack
from datetime import datetime, timedelta
from functools import wraps
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import game
import httpx
from api.main import create_app, TurnResponse

from api.persistence.campaign_store import CampaignStore, MAX_COMBAT_HISTORY_ENTRIES
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures
from api.tests import test_spell_scope as spells
from api.tests import test_campaign_time as clocks
from api.tests.test_action_economy_reactions import interrupted, assert_continuation
import json
from api.persistence.campaign_models import CampaignError, CampaignStaleError


class PersistenceIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign
    install_test_ambient_event = fixtures.CampaignApiTests.install_test_ambient_event

    def prepare_spell(self, a):
        record = self.manager.get(a["session_id"])
        s, enemy = spells.caster(record.game_session)
        s.ensure_combat_state()
        if record.campaign_id is not None:
            self.manager.save_campaign(record.campaign_id)
        command = {"message": "Resolve the selected spell.", "action_id": str(uuid4()),
                   "combat_action": {"steps": [{"kind": "magic", "ability": "Magic Missile",
                                               "target_id": enemy["id"]}]}}
        return record, command

    def snapshot(self, record):
        return copy.deepcopy((record.game_session.serialize_game_state(),
                              record.game_session.rng.getstate(), record.journal,
                              record.narrative_memory, record.lore_authority.to_dict(),
                              record.combat_history, record.turn_action_receipts,
                              self.store.get_campaign(record.campaign_id)
                              if record.campaign_id is not None else None))

    async def post(self, a, body):
        return await self.http.post(f"/api/game/sessions/{a['session_id']}/turn", json=body)

    async def simultaneous(self, a, bodies):
        # Both real sync FastAPI worker handlers arrive before either can lock.
        barrier = threading.Barrier(2)
        original = self.manager.get

        def rendezvous(sid):
            record = original(sid)
            barrier.wait(timeout=10)
            return record

        with patch.object(self.manager, "get", side_effect=rendezvous):
            return await asyncio.wait_for(asyncio.gather(
                *(self.post(a, body) for body in bodies)
            ), timeout=20)

    async def assert_corrupt_saved_receipt_blocks_retry(
        self, corruption, operation="turn", *, conflicting_action=None,
        conflicting_message=None, conflicting_combat_step=None, malformed_hash="g" * 64,
        conflicting_combat_context=None, conflicting_target_id=None,
    ):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        endpoint = "turn"
        if operation == "turn":
            record, command = self.prepare_spell(created)
        elif operation in ("short_rest", "long_rest"):
            endpoint = "species-actions"
            session.commit_location_change("tavern")
            session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
            session.initialize_species_trait_state()
            session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
            self.manager.save_campaign(created["campaign_id"])
            command = {"action": operation, "action_id": str(uuid4())}
        elif operation in ("react", "decline_reaction"):
            session.commit_location_change("tavern")
            npcs, opportunity_id = interrupted(session)
            self.manager.save_campaign(created["campaign_id"])
            command = {
                "message": "Hamle.", "action_id": str(uuid4()),
                "combat_action": {"steps": [{
                    "kind": operation, "opportunity_id": opportunity_id,
                }]},
                "combat_id": session.world_state["combat"]["combat_id"],
                "combat_round": session.world_state["combat"]["round"],
                "combat_turn_index": session.world_state["combat"]["current_turn_index"],
            }
        else:
            self.fail(f"Unknown operation: {operation}")
        if conflicting_target_id is not None:
            self.assertEqual(operation, "turn")
            command["target_id"] = command["combat_action"]["steps"][0]["target_id"]
        if conflicting_combat_context is not None or conflicting_target_id is not None:
            self.assertEqual(operation, "turn")
            if conflicting_combat_context is not None:
                self.assertIn(
                    conflicting_combat_context,
                    ("combat_id", "combat_round", "combat_turn_index"),
                )
            combat = session.world_state["combat"]
            command.update(
                combat_id=combat["combat_id"], combat_round=combat["round"],
                combat_turn_index=combat["current_turn_index"],
            )
        before_operation = copy.deepcopy(session.serialize_game_state())
        path = f"/api/game/sessions/{created['session_id']}/{endpoint}"
        # Real mechanics and persistence; fix only combat dice to keep the
        # accepted reaction deterministic and nonfatal.
        with patch("game.roll_attack", return_value=1), \
             patch("game.roll_d20", return_value=15), \
             patch("game.roll_damage", return_value=4):
            accepted = await self.http.post(path, json=command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertNotEqual(session.serialize_game_state(), before_operation)
        if operation in ("short_rest", "long_rest"):
            self.assertEqual(accepted.json()["result"]["action"], operation)
            self.assertEqual(
                session.character["species_trait_state"]["adrenaline_rush_uses_remaining"],
                session.character["proficiency_bonus"],
            )
            self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"],
                             3600 if operation == "short_rest" else 28800)
            if operation == "long_rest":
                self.assertEqual(session.character["current_hp"], 20)
        elif operation in ("react", "decline_reaction"):
            assert_continuation(
                self, {"action_result": accepted.json()["combat_result"],
                       "narration": accepted.json()["narration"]},
                session, npcs, operation, ["hit", "hit"], [4, 4],
            )
        campaign_id = created["campaign_id"]
        committed = copy.deepcopy(self.store.get_campaign(campaign_id))
        receipt = self.store.get_turn_action(campaign_id, command["action_id"])
        self.assertEqual(receipt["response"], accepted.json())
        self.assertEqual(len(committed.history), 1)

        if corruption == "hash":
            # Hash shape corruption is not an ordinary request mismatch.
            sql = "UPDATE campaign_turn_actions SET request_hash = ? WHERE campaign_id = ? AND action_id = ?"
            value = malformed_hash
            expected_status, expected_code = 409, "campaign_unavailable"
        elif corruption == "json":
            sql = "UPDATE campaign_turn_actions SET response_json = ? WHERE campaign_id = ? AND action_id = ?"
            value = '{"action_id":'
            expected_status, expected_code = 503, "campaign_storage_unavailable"
        elif corruption == "action_id":
            sql = "UPDATE campaign_turn_actions SET response_json = ? WHERE campaign_id = ? AND action_id = ?"
            response = copy.deepcopy(accepted.json())
            response["action_id"] = str(uuid4())
            value = json.dumps(response)
            expected_status, expected_code = 409, "campaign_unavailable"
        elif isinstance(corruption, tuple):
            field_path, mode, invalid_value = corruption
            sql = "UPDATE campaign_turn_actions SET response_json = ? WHERE campaign_id = ? AND action_id = ?"
            response = copy.deepcopy(accepted.json())
            parent = response
            for field in field_path[:-1]:
                parent = parent[field]
            if mode == "missing":
                del parent[field_path[-1]]
            else:
                parent[field_path[-1]] = invalid_value
            self.assertIsInstance(response, dict)
            self.assertEqual(response["action_id"], command["action_id"])
            value = json.dumps(response)
            expected_status, expected_code = 409, "campaign_unavailable"
        else:
            self.fail(f"Unknown receipt corruption: {corruption}")
        retry_command = copy.deepcopy(command)
        if conflicting_message is not None:
            self.assertEqual(operation, "turn")
            self.assertTrue(corruption == "hash" or isinstance(corruption, tuple))
            retry_command["message"] = conflicting_message
            self.assertNotEqual(retry_command["message"], command["message"])
            self.assertEqual(retry_command["action_id"], command["action_id"])
            if corruption != "hash":
                expected_status, expected_code = 409, "action_id_conflict"
        if conflicting_action is not None:
            self.assertIn(operation, ("short_rest", "long_rest"))
            self.assertTrue(corruption == "hash" or isinstance(corruption, tuple))
            retry_command["action"] = conflicting_action
            self.assertNotEqual(retry_command["action"], command["action"])
            self.assertEqual(retry_command["action_id"], command["action_id"])
            if corruption != "hash":
                expected_status, expected_code = 409, "action_id_conflict"
        if conflicting_combat_step is not None:
            self.assertEqual(operation, "turn")
            self.assertIsInstance(corruption, tuple)
            self.assertIsNone(conflicting_message)
            retry_command["combat_action"]["steps"][0].update(conflicting_combat_step)
            self.assertNotEqual(retry_command["combat_action"], command["combat_action"])
            self.assertEqual(retry_command["message"], command["message"])
            self.assertEqual(retry_command["action_id"], command["action_id"])
            expected_status, expected_code = 409, "action_id_conflict"
        if conflicting_combat_context is not None:
            self.assertIsInstance(corruption, tuple)
            self.assertIsNone(conflicting_message)
            self.assertIsNone(conflicting_combat_step)
            self.assertIsNone(conflicting_action)
            field = conflicting_combat_context
            retry_command[field] = (
                str(uuid4()) if field == "combat_id" else command[field] + 1
            )
            self.assertNotEqual(retry_command[field], command[field])
            # Exactly one context field changes; the accepted action is identical.
            self.assertEqual(
                {key: value for key, value in retry_command.items() if key != field},
                {key: value for key, value in command.items() if key != field},
            )
            expected_status, expected_code = 409, "action_id_conflict"
        if conflicting_target_id is not None:
            self.assertIsInstance(corruption, tuple)
            self.assertIsNone(conflicting_message)
            self.assertIsNone(conflicting_combat_step)
            self.assertIsNone(conflicting_action)
            self.assertIsNone(conflicting_combat_context)
            retry_command["target_id"] = conflicting_target_id
            self.assertNotEqual(retry_command["target_id"], command["target_id"])
            # The independent top-level selection is the only changed hash input:
            # message, action ID, structured step target and combat context stay fixed.
            self.assertEqual(
                {key: value for key, value in retry_command.items() if key != "target_id"},
                {key: value for key, value in command.items() if key != "target_id"},
            )
            expected_status, expected_code = 409, "action_id_conflict"
        with self.store._transaction() as connection:
            updated = connection.execute(sql, (value, campaign_id, command["action_id"]))
            self.assertEqual(updated.rowcount, 1)
        self.assertEqual(self.store.get_campaign(campaign_id), committed)
        if corruption == "hash":
            with closing(self.store._connect()) as connection:
                damaged_row = connection.execute(
                    "SELECT request_hash, response_json FROM campaign_turn_actions WHERE campaign_id = ? AND action_id = ?",
                    (campaign_id, command["action_id"]),
                ).fetchone()
            self.assertEqual(damaged_row["request_hash"], malformed_hash)
            self.assertEqual(json.loads(damaged_row["response_json"]), accepted.json())
        elif (conflicting_action is not None or conflicting_message is not None
              or conflicting_combat_step is not None
              or conflicting_combat_context is not None
              or conflicting_target_id is not None):
            damaged_receipt = self.store.get_turn_action(campaign_id, command["action_id"])
            self.assertEqual(damaged_receipt["request_hash"], receipt["request_hash"])
            self.assertEqual(damaged_receipt["response"], response)
            self.assertNotEqual(damaged_receipt["response"], accepted.json())

        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://reload") as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = fresh.get(sid)
            self.assertIsNot(restored.game_session, record.game_session)
            reopened = fresh_store.get_campaign(campaign_id)
            self.assertEqual(reopened.payload, committed.payload)
            self.assertEqual(reopened.metadata["revision"], committed.metadata["revision"])
            self.assertEqual(reopened.history, committed.history)
            self.assertEqual(reopened.combat_history, committed.combat_history)
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertEqual(restored.game_session.serialize_game_state(),
                             record.game_session.serialize_game_state())
            self.assertEqual(restored.game_session.rng.getstate(),
                             record.game_session.rng.getstate())
            before_runtime = self.snapshot(restored)
            before_auxiliary = copy.deepcopy((
                restored.game_session.messages,
                restored.game_session.world_metadata,
            ))
            before_species_resources = copy.deepcopy(
                restored.game_session.character["species_trait_state"],
            )
            # Include raw metadata and the damaged receipt, neither of which may
            # be repaired or overwritten by the retry. Resume alone may mark played.
            with closing(fresh_store._connect()) as connection:
                before_rows = [
                    tuple(row) for row in connection.execute(
                        "SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)
                    )
                ]
                before_receipts = [
                    tuple(row) for row in connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? ORDER BY action_id",
                        (campaign_id,),
                    )
                ]
                before_database = tuple(connection.iterdump())

            async def guarded_retry(body, target_endpoint=endpoint):
                guards = (
                    (game, "run_player_turn"),
                    (game, "resolve_species_trait_action"),
                    (restored.game_session, "resolve_ambient_event_action"),
                    (restored.game_session.rng, "randint"),
                    (restored.game_session.rng, "random"),
                    (restored.game_session.rng, "getrandbits"),
                    (fresh, "autosave_turn"),
                    (fresh, "save_campaign_locked"),
                    (fresh_store, "save_campaign"),
                    (fresh_store, "_transaction"),
                )
                if (conflicting_combat_step is not None
                        or conflicting_combat_context is not None
                        or conflicting_target_id is not None):
                    # A changed combat request must fail at hash comparison,
                    # before even attempting to validate the damaged reply.
                    guards += ((TurnResponse, "model_validate"),)
                with ExitStack() as stack:
                    spies = [
                        stack.enter_context(patch.object(
                            target, method,
                            side_effect=AssertionError(f"Receipt retry invoked {method}"),
                        ))
                        for target, method in guards
                    ]
                    reply = await client.post(
                        f"/api/game/sessions/{sid}/{target_endpoint}", json=body,
                    )
                for spy in spies:
                    spy.assert_not_called()
                return reply

            cross_family_requests = []
            if corruption == "hash":
                # A shared persisted owner must be validated even when the
                # receiving command would ordinarily report a request conflict.
                cross_family_requests = [
                    ("species-actions", {
                        "action": "short_rest", "action_id": command["action_id"],
                    }) if endpoint == "turn" else ("turn", {
                        "message": "Different request.", "action_id": command["action_id"],
                    }),
                    (f"ambient-events/{uuid4()}/actions", {
                        "action": "observe", "action_id": command["action_id"],
                    }),
                ]
            for target_endpoint, body in [(endpoint, retry_command), *cross_family_requests]:
                with self.subTest(retry_endpoint=target_endpoint):
                    retry = await guarded_retry(body, target_endpoint)
                    self.assertEqual(retry.status_code, expected_status, retry.text)
                    self.assertEqual(retry.json()["detail"]["code"], expected_code)
                    self.assertIsInstance(retry.json()["detail"]["message"], str)
                    self.assertTrue(retry.json()["detail"]["message"])
                    self.assertEqual(self.snapshot(restored), before_runtime)
                    self.assertEqual(restored.game_session.character["species_trait_state"],
                                     before_species_resources)
                    self.assertEqual((
                        restored.game_session.messages,
                        restored.game_session.world_metadata,
                    ), before_auxiliary)
                    self.assertEqual(fresh_store.get_campaign(campaign_id), reopened)
                    with closing(fresh_store._connect()) as connection:
                        self.assertEqual([
                            tuple(row) for row in connection.execute(
                                "SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)
                            )
                        ], before_rows)
                        self.assertEqual([
                            tuple(row) for row in connection.execute(
                                "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? ORDER BY action_id",
                                (campaign_id,),
                            )
                        ], before_receipts)
                        self.assertEqual(tuple(connection.iterdump()), before_database)

            if corruption == "hash":
                # Only the test repairs the hash; the saved response remains intact.
                with fresh_store._transaction() as connection:
                    updated = connection.execute(
                        sql, (receipt["request_hash"], campaign_id, command["action_id"]),
                    )
                    self.assertEqual(updated.rowcount, 1)
                self.assertEqual(
                    fresh_store.get_turn_action(campaign_id, command["action_id"]), receipt,
                )
                with closing(fresh_store._connect()) as connection:
                    repaired_database = tuple(connection.iterdump())
                replay = await guarded_retry(command)
                expected = copy.deepcopy(accepted.json())
                expected["session_id"] = sid
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json(), expected)
                self.assertEqual(self.snapshot(restored), before_runtime)
                self.assertEqual((
                    restored.game_session.messages, restored.game_session.world_metadata,
                ), before_auxiliary)
                with closing(fresh_store._connect()) as connection:
                    self.assertEqual(tuple(connection.iterdump()), repaired_database)
                conflict_requests = list(cross_family_requests)
                if conflicting_action is not None or conflicting_message is not None:
                    conflict_requests.append((endpoint, retry_command))
                for target_endpoint, body in conflict_requests:
                    with self.subTest(valid_hash_conflict=target_endpoint):
                        conflict = await guarded_retry(body, target_endpoint)
                        if target_endpoint.startswith("ambient-events/"):
                            self.assertEqual(conflict.status_code, 200, conflict.text)
                            self.assertEqual(conflict.json()["result"]["status"], "REJECTED")
                            self.assertEqual(
                                conflict.json()["result"]["reason_code"], "action_id_conflict",
                            )
                        else:
                            self.assertEqual(conflict.status_code, 409, conflict.text)
                            self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
                        self.assertEqual(self.snapshot(restored), before_runtime)
                        self.assertEqual((
                            restored.game_session.messages, restored.game_session.world_metadata,
                        ), before_auxiliary)
                        with closing(fresh_store._connect()) as connection:
                            self.assertEqual(tuple(connection.iterdump()), repaired_database)

    async def test_corrupt_saved_receipt_hash_blocks_http_retry_after_resume(self):
        for operation in ("turn", "short_rest", "long_rest"):
            for label, malformed in (
                ("short", "a" * 63),
                ("overlong", "a" * 65),
                ("nonhex", "g" * 64),
                ("uppercase", "A" * 64),
            ):
                for changed in (False, True):
                    with self.subTest(operation=operation, hash=label, changed=changed):
                        kwargs = {}
                        if changed:
                            if operation == "turn":
                                kwargs["conflicting_message"] = "Resolve a different selected spell."
                            else:
                                kwargs["conflicting_action"] = (
                                    "long_rest" if operation == "short_rest" else "short_rest"
                                )
                        await self.assert_corrupt_saved_receipt_blocks_retry(
                            "hash", operation, malformed_hash=malformed, **kwargs,
                        )

    async def test_corrupt_saved_receipt_json_blocks_http_retry_after_resume(self):
        await self.assert_corrupt_saved_receipt_blocks_retry("json")

    async def test_corrupt_saved_receipt_action_id_blocks_http_retry_after_resume(self):
        await self.assert_corrupt_saved_receipt_blocks_retry("action_id")

    async def test_incomplete_turn_response_blocks_http_retry_after_resume(self):
        for field_path, invalid_value in (
            (("session_id",), 123),
            (("narration",), []),
            (("state",), []),
        ):
            for mode in ("missing", "wrong_type"):
                with self.subTest(field=field_path, mode=mode):
                    await self.assert_corrupt_saved_receipt_blocks_retry(
                        (field_path, mode, invalid_value),
                    )

    async def test_changed_turn_request_conflicts_before_damaged_response_after_resume(self):
        for field_path, invalid_value in (
            (("session_id",), 123),
            (("narration",), []),
            (("state",), []),
        ):
            for mode in ("missing", "wrong_type"):
                with self.subTest(field=field_path, mode=mode):
                    # The committed request hash must reject a changed ordinary
                    # turn before the damaged saved reply reaches validation.
                    await self.assert_corrupt_saved_receipt_blocks_retry(
                        (field_path, mode, invalid_value),
                        conflicting_message="Resolve a different selected spell.",
                    )

    async def test_changed_combat_command_conflicts_before_damaged_response_after_resume(self):
        for changed_step in (
            {"ability": "Fire Bolt"},
            {"target_id": "different-combat-target"},
        ):
            for field_path, invalid_value in (
                (("session_id",), 123),
                (("narration",), []),
                (("state",), []),
            ):
                for mode in ("missing", "wrong_type"):
                    with self.subTest(changed_step=changed_step, field=field_path, mode=mode):
                        await self.assert_corrupt_saved_receipt_blocks_retry(
                            (field_path, mode, invalid_value),
                            conflicting_combat_step=changed_step,
                        )

    async def test_changed_top_level_target_conflicts_before_damaged_response_after_resume(self):
        for field_path, invalid_value in (
            (("session_id",), 123),
            (("narration",), []),
            (("state",), []),
        ):
            for mode in ("missing", "wrong_type"):
                with self.subTest(field=field_path, mode=mode):
                    await self.assert_corrupt_saved_receipt_blocks_retry(
                        (field_path, mode, invalid_value),
                        conflicting_target_id="different-selected-target",
                    )

    async def test_unchanged_top_level_target_replays_saved_receipt_after_resume(self):
        created = await self.create_campaign()
        record, command = self.prepare_spell(created)
        session = record.game_session
        # The selected target is a separate TurnRequest field, not merely the
        # target embedded in the structured spell command.
        command["target_id"] = command["combat_action"]["steps"][0]["target_id"]
        combat = session.world_state["combat"]
        command.update(
            combat_id=combat["combat_id"], combat_round=combat["round"],
            combat_turn_index=combat["current_turn_index"],
        )
        original_command = copy.deepcopy(command)
        before_turn = self.snapshot(record)
        accepted = await self.post(created, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        expected = copy.deepcopy(accepted.json())
        self.assertNotEqual(self.snapshot(record)[:7], before_turn[:7])
        self.assertTrue(expected["combat_result"]["success"])
        campaign_id = created["campaign_id"]
        committed = self.snapshot(record)
        original_receipt = self.store.get_turn_action(campaign_id, command["action_id"])
        self.assertEqual(original_receipt["response"], expected)
        self.assertEqual(len(committed[-1].history), 1)
        self.assertEqual(len(committed[-1].combat_history), 1)

        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://reload") as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = fresh.get(sid)
            self.assertNotEqual(sid, created["session_id"])
            self.assertIsNot(restored.game_session, session)
            self.assertEqual(self.snapshot(restored)[:7], committed[:7])
            self.assertEqual(resumed.json()["history"], committed[-1].history)
            self.assertEqual(fresh.get_turn_action(restored, command["action_id"]),
                             original_receipt)

            def saved_rows():
                with closing(fresh_store._connect()) as connection:
                    return {
                        table: [tuple(row) for row in connection.execute(
                            f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                            (campaign_id,),
                        )]
                        for table in ("campaigns", "campaign_turn_actions",
                                      "campaign_history", "campaign_combat_history")
                    }

            # Resume may mark the campaign played. Capture complete runtime and
            # raw persistence baselines only after that legitimate write.
            before_retry = self.snapshot(restored)
            before_auxiliary = copy.deepcopy((
                restored.game_session.messages, restored.game_session.world_metadata,
            ))
            before_rows = saved_rows()
            retry_command = copy.deepcopy(command)
            self.assertEqual(retry_command, original_command)
            guards = (
                (restored.game_session, "run_player_turn"),
                (game, "run_player_turn"),
                (restored.game_session.rng, "randint"),
                (restored.game_session.rng, "random"),
                (restored.game_session.rng, "getrandbits"),
                (fresh, "autosave_turn"),
                (fresh, "save_campaign_locked"),
                (fresh_store, "save_campaign"),
                (fresh_store, "_transaction"),
            )
            with ExitStack() as stack:
                spies = [
                    stack.enter_context(patch.object(
                        target, method,
                        side_effect=AssertionError(f"Receipt replay invoked {method}"),
                    ))
                    for target, method in guards
                ]
                replay = await client.post(
                    f"/api/game/sessions/{sid}/turn", json=retry_command,
                )
            for spy in spies:
                spy.assert_not_called()
            expected["session_id"] = sid
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), expected)
            self.assertEqual(self.snapshot(restored), before_retry)
            self.assertEqual((
                restored.game_session.messages, restored.game_session.world_metadata,
            ), before_auxiliary)
            self.assertEqual(saved_rows(), before_rows)
            self.assertEqual(fresh_store.get_turn_action(campaign_id, command["action_id"]),
                             original_receipt)

    async def assert_changed_combat_context_conflicts_before_damaged_response(self, context_field):
        for field_path, invalid_value in (
            (("session_id",), 123),
            (("narration",), []),
            (("state",), []),
        ):
            for mode in ("missing", "wrong_type"):
                with self.subTest(context=context_field, field=field_path, mode=mode):
                    await self.assert_corrupt_saved_receipt_blocks_retry(
                        (field_path, mode, invalid_value),
                        conflicting_combat_context=context_field,
                    )

    async def test_changed_combat_id_conflicts_before_damaged_response_after_resume(self):
        await self.assert_changed_combat_context_conflicts_before_damaged_response("combat_id")

    async def test_changed_combat_round_conflicts_before_damaged_response_after_resume(self):
        await self.assert_changed_combat_context_conflicts_before_damaged_response("combat_round")

    async def test_changed_combat_turn_index_conflicts_before_damaged_response_after_resume(self):
        await self.assert_changed_combat_context_conflicts_before_damaged_response("combat_turn_index")

    async def test_incomplete_species_response_blocks_http_retry_after_resume(self):
        for operation in ("short_rest", "long_rest"):
            for field_path, invalid_value in (
                (("session_id",), 123),
                (("state",), []),
                (("result",), []),
                (("result", "action"), 123),
                (("result", "message"), []),
                (("result", "effects"), []),
            ):
                for mode in ("missing", "wrong_type"):
                    with self.subTest(operation=operation, field=field_path, mode=mode):
                        await self.assert_corrupt_saved_receipt_blocks_retry(
                            (field_path, mode, invalid_value), operation,
                        )

    async def test_changed_species_request_conflicts_before_damaged_response_after_resume(self):
        for operation, conflicting_action in (
            ("short_rest", "long_rest"),
            ("long_rest", "short_rest"),
        ):
            for field_path, invalid_value in (
                (("session_id",), 123),
                (("state",), []),
                (("result",), []),
                (("result", "action"), 123),
                (("result", "message"), []),
                (("result", "effects"), []),
            ):
                for mode in ("missing", "wrong_type"):
                    with self.subTest(operation=operation, field=field_path, mode=mode):
                        # A valid committed hash must win over response-schema
                        # damage when the same ID is used for a different request.
                        await self.assert_corrupt_saved_receipt_blocks_retry(
                            (field_path, mode, invalid_value), operation,
                            conflicting_action=conflicting_action,
                        )

    async def assert_persisted_species_receipt_isolation(self, *, edit_input=False):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        session.commit_location_change("tavern")
        session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
        session.initialize_species_trait_state()
        session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
        campaign_id = created["campaign_id"]
        self.manager.save_campaign(campaign_id)
        command = {"action": "long_rest", "action_id": str(uuid4())}
        path = f"/api/game/sessions/{created['session_id']}/species-actions"
        with patch.object(self.manager, "autosave_turn",
                          wraps=self.manager.autosave_turn) as autosave:
            accepted = await self.http.post(path, json=command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        autosave.assert_called_once()
        supplied = autosave.call_args.kwargs["turn_action_receipt"]
        expected = accepted.json()
        self.assertEqual(expected["result"]["action"], "long_rest")
        self.assertEqual(expected["result"]["effects"]["current_hp"], 20)
        self.assertEqual(expected["result"]["effects"]["refreshed"]["adrenaline_rush"],
                         session.character["proficiency_bonus"])
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 28800)
        original = copy.deepcopy(self.store.get_turn_action(campaign_id, command["action_id"]))
        self.assertEqual(original["response"], expected)
        self.assertEqual(supplied["response"], expected)
        self.assertEqual(supplied["request_hash"], original["request_hash"])
        self.assertEqual(supplied["action_id"], command["action_id"])
        supplied_original = copy.deepcopy(supplied)
        saved = copy.deepcopy(self.store.get_campaign(campaign_id))

        if edit_input:
            committed = self.snapshot(record)
            auxiliary_before = copy.deepcopy((session.messages, session.world_metadata))
            # Keep the actual autosave argument, not a lookup copy: ingress must
            # detach caller-owned nested effects and state before storing them.
            effects = supplied["response"]["result"]["effects"]
            effects["refreshed"]["adrenaline_rush"] = -1
            effects["time_result"].clear()
            state = supplied["response"]["state"]
            state["character"]["species_trait_state"]["adrenaline_rush_uses_remaining"] = -1
            state["character"]["current_hp"] = 0
            state["character"]["species_trait_state"]["caller_only"] = {"edits": ["local"]}
            self.assertNotEqual(supplied, supplied_original)
            self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
            self.assertEqual(self.store.get_turn_action(campaign_id, command["action_id"]), original)
            self.assertEqual(self.snapshot(record), committed)
            with patch.object(session, "resolve_species_trait_action",
                              side_effect=AssertionError("Replay repeated species mechanics")) as mechanics, \
                 patch("game.resolve_species_trait_action",
                       side_effect=AssertionError("Replay repeated rest")) as rest, \
                 patch.object(session.rng, "randint",
                              side_effect=AssertionError("Replay consumed RNG")) as rng, \
                 patch.object(self.manager, "autosave_turn",
                              side_effect=AssertionError("Replay autosaved")) as autosave, \
                 patch.object(self.store, "save_campaign",
                              side_effect=AssertionError("Replay persisted")) as save:
                replay = await self.http.post(path, json=command)
            for guard in (mechanics, rest, rng, autosave, save):
                guard.assert_not_called()
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), expected)
            self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
            self.assertEqual(self.store.get_turn_action(campaign_id, command["action_id"]), original)
            self.assertEqual(self.snapshot(record), committed)
            self.assertEqual((session.messages, session.world_metadata), auxiliary_before)

        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://reload") as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = fresh.get(sid)
            self.assertIsNot(restored.game_session, session)
            self.assertEqual(restored.game_session.serialize_game_state(),
                             session.serialize_game_state())
            self.assertEqual(restored.game_session.rng.getstate(), session.rng.getstate())
            reopened = copy.deepcopy(fresh_store.get_campaign(campaign_id))
            self.assertEqual(reopened.payload, saved.payload)
            self.assertEqual(reopened.history, saved.history)
            self.assertEqual(reopened.combat_history, saved.combat_history)
            self.assertEqual(reopened.metadata["revision"], saved.metadata["revision"])
            # Resume refreshes last_played_at; freeze state only after that write.
            before = self.snapshot(restored)
            auxiliary = copy.deepcopy((
                restored.game_session.messages, restored.game_session.world_metadata,
            ))
            with closing(fresh_store._connect()) as connection:
                receipt_rows = [
                    tuple(row) for row in connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? ORDER BY action_id",
                        (campaign_id,),
                    )
                ]
            with patch.object(restored.game_session, "resolve_species_trait_action",
                              side_effect=AssertionError("Replay repeated species mechanics")) as mechanics, \
                 patch("game.resolve_species_trait_action",
                       side_effect=AssertionError("Replay repeated rest")) as rest, \
                 patch.object(restored.game_session.rng, "randint",
                              side_effect=AssertionError("Replay consumed RNG")) as rng, \
                 patch.object(fresh, "autosave_turn",
                              side_effect=AssertionError("Replay autosaved")) as autosave, \
                 patch.object(fresh_store, "save_campaign",
                              side_effect=AssertionError("Replay persisted")) as save:
                caller_receipt = fresh.get_turn_action(restored, command["action_id"])
                self.assertEqual(caller_receipt, original)
                effects = caller_receipt["response"]["result"]["effects"]
                effects["refreshed"]["adrenaline_rush"] = -1
                effects["time_result"].clear()
                state = caller_receipt["response"]["state"]
                state["character"]["species_trait_state"]["adrenaline_rush_uses_remaining"] = -1
                state["character"]["current_hp"] = 0
                state["character"]["species_trait_state"]["caller_only"] = {"edits": ["local"]}
                self.assertNotEqual(caller_receipt, original)
                self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original)
                self.assertEqual(fresh_store.get_turn_action(campaign_id, command["action_id"]),
                                 original)
                self.assertEqual(self.snapshot(restored), before)
                replay = await client.post(
                    f"/api/game/sessions/{sid}/species-actions", json=command,
                )
            for guard in (mechanics, rest, rng, autosave, save):
                guard.assert_not_called()
            self.assertEqual(replay.status_code, 200, replay.text)
            replay_expected = copy.deepcopy(expected)
            replay_expected["session_id"] = sid
            self.assertEqual(replay.json(), replay_expected)
            self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original)
            self.assertEqual(fresh_store.get_turn_action(campaign_id, command["action_id"]),
                             original)
            self.assertEqual(self.snapshot(restored), before)
            self.assertEqual((
                restored.game_session.messages, restored.game_session.world_metadata,
            ), auxiliary)
            self.assertEqual(fresh_store.get_campaign(campaign_id), reopened)
            with closing(fresh_store._connect()) as connection:
                self.assertEqual([
                    tuple(row) for row in connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? ORDER BY action_id",
                        (campaign_id,),
                    )
                ], receipt_rows)

    async def test_resumed_species_receipt_isolated_from_nested_caller_edits(self):
        await self.assert_persisted_species_receipt_isolation()

    async def test_persisted_species_receipt_isolated_from_autosave_input_edits(self):
        await self.assert_persisted_species_receipt_isolation(edit_input=True)

    async def assert_transient_response_validation(
        self, operation, *, envelope_only=False, conflicting_request=False,
    ):
        created = await self.http.post("/api/game/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        created = created.json()
        record = self.manager.get(created["session_id"])
        self.assertIsNone(record.campaign_id)
        session = record.game_session
        endpoint = "turn" if operation == "turn" else "species-actions"
        if operation == "turn":
            record, command = self.prepare_spell(created)
            fields = (
                (("session_id",), 123),
                (("narration",), []),
                (("state",), []),
            )
        else:
            session.commit_location_change("tavern")
            session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
            session.initialize_species_trait_state()
            session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
            command = {"action": operation, "action_id": str(uuid4())}
            fields = (
                (("session_id",), 123),
                (("state",), []),
                (("result",), []),
                (("result", "action"), 123),
                (("result", "message"), []),
                (("result", "effects"), []),
            )
        path = f"/api/game/sessions/{created['session_id']}/{endpoint}"
        before_action = copy.deepcopy(session.serialize_game_state())
        with patch.object(self.manager, "autosave_turn",
                          wraps=self.manager.autosave_turn) as autosave:
            accepted = await self.http.post(path, json=command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        autosave.assert_called_once()
        supplied = autosave.call_args.kwargs["turn_action_receipt"]
        expected = accepted.json()
        original = copy.deepcopy(record.turn_action_receipts[command["action_id"]])
        self.assertEqual(original["response"], expected)
        self.assertEqual(original["action_id"], command["action_id"])
        self.assertRegex(original["request_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
        changed_command = copy.deepcopy(command)
        if operation == "turn":
            changed_command["message"] = "Resolve a different spell request."
        else:
            changed_command["action"] = (
                "long_rest" if operation == "short_rest" else "short_rest"
            )
        self.assertEqual(changed_command["action_id"], command["action_id"])
        self.assertNotEqual(changed_command, command)
        self.assertNotEqual(session.serialize_game_state(), before_action)
        if operation == "turn":
            self.assertTrue(record.combat_history)
        else:
            self.assertEqual(expected["result"]["action"], operation)
            self.assertEqual(
                session.character["species_trait_state"]["adrenaline_rush_uses_remaining"],
                session.character["proficiency_bonus"],
            )
            self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"],
                             3600 if operation == "short_rest" else 28800)
            if operation == "long_rest":
                self.assertEqual(session.character["current_hp"], 20)

        def runtime_snapshot():
            # Messages are transient narration history; the shared snapshot also
            # covers canonical state, RNG, journal, memories and combat history.
            return copy.deepcopy((
                self.snapshot(record), session.messages, session.world_metadata,
            ))

        async def retry_without_effects(
            status, *, body=None, error_code="campaign_unavailable",
        ):
            before_retry = runtime_snapshot()
            with patch.object(session, "run_player_turn",
                              side_effect=AssertionError("Replay executed a turn")) as engine, \
                 patch.object(session, "resolve_species_trait_action",
                              side_effect=AssertionError("Replay repeated species mechanics")) as species, \
                 patch.object(session.rng, "randint",
                              side_effect=AssertionError("Replay consumed dice")) as dice, \
                 patch.object(self.manager, "autosave_turn",
                              side_effect=AssertionError("Replay replaced a receipt")) as save, \
                 patch.object(self.store, "save_campaign",
                              side_effect=AssertionError("Transient replay persisted")) as persisted:
                retry = await self.http.post(
                    path, json=command if body is None else body,
                )
            self.assertEqual(retry.status_code, status, retry.text)
            if status == 200:
                self.assertEqual(retry.json(), expected)
            else:
                self.assertEqual(retry.json()["detail"]["code"], error_code)
                self.assertIsInstance(retry.json()["detail"]["message"], str)
                self.assertTrue(retry.json()["detail"]["message"])
            for guard in (engine, species, dice, save, persisted):
                guard.assert_not_called()
            self.assertEqual(runtime_snapshot(), before_retry)

        committed = runtime_snapshot()
        # Both receipt ingress and lookup must detach nested caller-owned data.
        # Damage only these copies first: a valid HTTP replay must still succeed.
        for caller_receipt in (
            supplied, self.manager.get_turn_action(record, command["action_id"]),
        ):
            caller_receipt["response"]["state"].clear()
            if operation == "turn":
                del caller_receipt["response"]["narration"]
            else:
                caller_receipt["response"]["result"]["effects"].clear()
                del caller_receipt["response"]["result"]["message"]
            self.assertNotEqual(caller_receipt, original)
            self.assertEqual(record.turn_action_receipts[command["action_id"]], original)
            self.assertEqual(runtime_snapshot(), committed)
            await retry_without_effects(200)

        if envelope_only:
            damaged_receipts = [
                ("non_dictionary", value) for value in (None, [], "", 0, False, ["receipt"])
            ]
            for field in ("request_hash", "response"):
                damaged = copy.deepcopy(original)
                del damaged[field]
                damaged_receipts.append((f"missing_{field}", damaged))
                for value in (None, [], 123, ""):
                    damaged = copy.deepcopy(original)
                    damaged[field] = value
                    damaged_receipts.append((f"invalid_{field}_{value!r}", damaged))
            for corruption, damaged in damaged_receipts:
                with self.subTest(operation=operation, corruption=corruption):
                    record.turn_action_receipts[command["action_id"]] = damaged
                    await retry_without_effects(409)
                    self.assertEqual(record.turn_action_receipts[command["action_id"]], damaged)
                    record.turn_action_receipts[command["action_id"]] = copy.deepcopy(original)
                    self.assertEqual(runtime_snapshot(), committed)

        for field_path, invalid_value in (() if envelope_only else fields):
            for mode in ("missing", "wrong_type"):
                with self.subTest(operation=operation, field=field_path, mode=mode):
                    # Deliberately damage the retained owner, not a detached
                    # lookup copy. Identity and request hash remain valid.
                    damaged = copy.deepcopy(original)
                    parent = damaged["response"]
                    for field in field_path[:-1]:
                        parent = parent[field]
                    if mode == "missing":
                        del parent[field_path[-1]]
                    else:
                        parent[field_path[-1]] = invalid_value
                    self.assertEqual(damaged["action_id"], original["action_id"])
                    self.assertEqual(damaged["request_hash"], original["request_hash"])
                    self.assertEqual(damaged["response"]["action_id"], command["action_id"])
                    record.turn_action_receipts[command["action_id"]] = damaged
                    await retry_without_effects(409)
                    if conflicting_request:
                        # A valid retained hash reserves the ID even when the
                        # response cannot pass the route's replay schema.
                        await retry_without_effects(
                            409, body=changed_command, error_code="action_id_conflict",
                        )
                    self.assertEqual(record.turn_action_receipts[command["action_id"]], damaged)
                    record.turn_action_receipts[command["action_id"]] = copy.deepcopy(original)
                    self.assertEqual(runtime_snapshot(), committed)
        # A final intact control rules out a broken route or blanket rejection.
        await retry_without_effects(200)

    async def test_malformed_transient_turn_receipt_blocks_http_retry(self):
        await self.assert_transient_response_validation("turn", envelope_only=True)

    async def test_malformed_transient_species_receipt_blocks_http_retry(self):
        await self.assert_transient_response_validation("short_rest", envelope_only=True)

    async def test_incomplete_transient_turn_response_blocks_http_retry(self):
        await self.assert_transient_response_validation("turn")

    async def test_incomplete_transient_short_rest_response_blocks_http_retry(self):
        await self.assert_transient_response_validation("short_rest")

    async def test_incomplete_transient_long_rest_response_blocks_http_retry(self):
        await self.assert_transient_response_validation("long_rest")

    async def test_damaged_transient_turn_response_keeps_changed_request_conflicting(self):
        await self.assert_transient_response_validation("turn", conflicting_request=True)

    async def test_damaged_transient_short_rest_response_keeps_changed_request_conflicting(self):
        await self.assert_transient_response_validation("short_rest", conflicting_request=True)

    async def test_damaged_transient_long_rest_response_keeps_changed_request_conflicting(self):
        await self.assert_transient_response_validation("long_rest", conflicting_request=True)

    async def test_corrupt_short_rest_receipts_block_http_retry_after_resume(self):
        for corruption in ("hash", "json", "action_id"):
            with self.subTest(corruption=corruption):
                await self.assert_corrupt_saved_receipt_blocks_retry(corruption, "short_rest")

    async def test_corrupt_long_rest_receipts_block_http_retry_after_resume(self):
        for corruption in ("hash", "json", "action_id"):
            with self.subTest(corruption=corruption):
                await self.assert_corrupt_saved_receipt_blocks_retry(corruption, "long_rest")

    async def test_corrupt_reaction_receipts_block_http_retry_after_resume(self):
        for corruption in ("hash", "json", "action_id"):
            with self.subTest(corruption=corruption):
                await self.assert_corrupt_saved_receipt_blocks_retry(corruption, "react")

    async def test_corrupt_declined_reaction_receipts_block_http_retry_after_resume(self):
        for corruption in ("hash", "json", "action_id"):
            with self.subTest(corruption=corruption):
                await self.assert_corrupt_saved_receipt_blocks_retry(corruption, "decline_reaction")

    async def test_independently_loaded_stale_save_cannot_overwrite_newer_truth(self):
        a = await self.create_campaign()
        first = SessionManager(campaign_store=CampaignStore(self.store.path))
        second = SessionManager(campaign_store=CampaignStore(self.store.path))
        _, current, *_ = first.resume_campaign(a["campaign_id"])
        _, stale, *_ = second.resume_campaign(a["campaign_id"])
        current.game_session.character["current_hp"] -= 1
        first.save_campaign(a["campaign_id"])
        committed = copy.deepcopy(self.store.get_campaign(a["campaign_id"]))
        stale.game_session.character["current_hp"] -= 2
        with self.assertRaises(CampaignError):
            second.save_campaign(a["campaign_id"])
        self.assertEqual(self.store.get_campaign(a["campaign_id"]), committed)

    async def test_structured_conflict_response_loss_reload_and_campaign_scoped_ids(self):
        a, b = await self.create_campaign(), await self.create_campaign()
        record, command = self.prepare_spell(a)
        other, second_command = self.prepare_spell(b)
        isolated = self.snapshot(other)
        first = await self.post(a, command)
        self.assertEqual(first.status_code, 200, first.text)
        committed = self.snapshot(record)
        conflict = copy.deepcopy(command)
        conflict["combat_action"]["steps"][0]["ability"] = "Fire Bolt"
        rejected = await self.post(a, conflict)
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["detail"]["code"], "action_id_conflict")
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual(self.snapshot(other), isolated)

        # Discard the first response as if lost; reconstruct without the old object.
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
        sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
        app = create_app(session_manager=fresh, ollama_adapter=None)
        before = self.snapshot(restored)
        with patch("spell_scope.cast", side_effect=AssertionError("replayed mechanics")):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://reload") as client:
                replay = await client.post(f"/api/game/sessions/{sid}/turn",
                                           json=dict(reversed(list(command.items()))))
        expected = first.json()
        expected["session_id"] = sid
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), expected)
        self.assertEqual(self.snapshot(restored), before)
        self.assertIsNot(restored.game_session, record.game_session)
        self.assertEqual(restored.game_session.rng.random(), record.game_session.rng.random())

        second_command["action_id"] = command["action_id"]
        result_b = await self.post(b, second_command)
        self.assertEqual(result_b.status_code, 200, result_b.text)
        self.assertEqual(len(self.store.get_campaign(a["campaign_id"]).history), 1)
        self.assertEqual(len(self.store.get_campaign(b["campaign_id"]).history), 1)
        with self.assertRaises(CampaignError):
            self.store.save_campaign(b["campaign_id"], record.game_session)

    async def test_saved_rest_action_rejects_combat_payload_after_reopen(self):
        for rest_action in ("short_rest", "long_rest"):
            with self.subTest(rest_action=rest_action):
                created = await self.create_campaign()
                campaign_id = created["campaign_id"]
                record = self.manager.get(created["session_id"])
                session = record.game_session
                session.commit_location_change("tavern")
                session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
                session.initialize_species_trait_state()
                session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
                self.manager.save_campaign(campaign_id)
                rest_command = {"action": rest_action, "action_id": str(uuid4())}
                elapsed_before = session.world_state["campaign_time"]["elapsed_seconds"]
                accepted = await self.http.post(
                    f"/api/game/sessions/{created['session_id']}/species-actions",
                    json=rest_command,
                )
                self.assertEqual(accepted.status_code, 200, accepted.text)
                self.assertEqual(accepted.json()["result"]["action"], rest_action)
                self.assertEqual(
                    session.character["species_trait_state"]["adrenaline_rush_uses_remaining"],
                    session.character["proficiency_bonus"],
                )
                self.assertEqual(
                    session.world_state["campaign_time"]["elapsed_seconds"] - elapsed_before,
                    3600 if rest_action == "short_rest" else 28800,
                )
                if rest_action == "long_rest":
                    self.assertEqual(session.character["current_hp"], 20)
                original_receipt = copy.deepcopy(
                    self.store.get_turn_action(campaign_id, rest_command["action_id"])
                )
                self.assertEqual(original_receipt["response"], accepted.json())

                # Populate real retained combat history after the rest, without
                # replacing its receipt. The conflicting request is otherwise a
                # valid combat command in the reopened encounter.
                record, combat_command = self.prepare_spell(created)
                session.character["armor_class"] = 100
                session.character["current_hp"] = 20
                self.manager.save_campaign(campaign_id)
                combat_response = await self.post(created, combat_command)
                self.assertEqual(combat_response.status_code, 200, combat_response.text)
                self.assertEqual(len(record.combat_history), 1)
                committed = self.snapshot(record)
                self.assertEqual(len(committed[-1].history), 2)
                self.assertEqual(
                    self.store.get_turn_action(campaign_id, rest_command["action_id"]),
                    original_receipt,
                )

                fresh_store = CampaignStore(self.store.path)
                fresh = SessionManager(campaign_store=fresh_store)
                app = create_app(session_manager=fresh, ollama_adapter=None)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                            base_url="http://reload") as client:
                    resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
                    self.assertEqual(resumed.status_code, 200, resumed.text)
                    sid = resumed.json()["session_id"]
                    restored = fresh.get(sid)
                    self.assertNotEqual(sid, created["session_id"])
                    self.assertIsNot(restored.game_session, session)
                    self.assertEqual(self.snapshot(restored)[:7], committed[:7])
                    self.assertEqual(resumed.json()["history"], committed[-1].history)
                    self.assertEqual(
                        fresh_store.get_turn_action(campaign_id, rest_command["action_id"]),
                        original_receipt,
                    )

                    retry = copy.deepcopy(combat_command)
                    retry["action_id"] = rest_command["action_id"]
                    combat = restored.game_session.world_state["combat"]
                    self.assertTrue(combat["active"])
                    retry.update(combat_id=combat["combat_id"], combat_round=combat["round"],
                                 combat_turn_index=combat["current_turn_index"])
                    self.assertEqual(retry["action_id"], rest_command["action_id"])
                    self.assertNotEqual(retry, rest_command)
                    # Resume can update metadata; baseline every owner only
                    # after it has completed, including the original SQL receipt.
                    before = self.snapshot(restored)
                    before_auxiliary = copy.deepcopy((
                        restored.game_session.messages, restored.game_session.world_metadata,
                    ))

                    def saved_rows():
                        with closing(fresh_store._connect()) as connection:
                            return {
                                table: [tuple(row) for row in connection.execute(
                                    f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                                    (campaign_id,),
                                )]
                                for table in ("campaigns", "campaign_turn_actions",
                                              "campaign_history", "campaign_combat_history")
                            }

                    before_rows = saved_rows()
                    with patch.object(restored.game_session, "run_player_turn",
                                      side_effect=AssertionError("Rest ID executed combat")) as engine, \
                         patch("game.run_player_turn",
                               side_effect=AssertionError("Rest ID reached core combat")) as core_engine, \
                         patch.object(restored.game_session.rng, "randint",
                                      side_effect=AssertionError("Rest ID consumed dice")) as dice, \
                         patch.object(fresh, "autosave_turn",
                                      side_effect=AssertionError("Rest ID autosaved")) as autosave, \
                         patch.object(fresh_store, "save_campaign",
                                      side_effect=AssertionError("Rest ID saved")) as save:
                        conflict = await client.post(
                            f"/api/game/sessions/{sid}/turn", json=retry,
                        )
                    self.assertEqual(conflict.status_code, 409, conflict.text)
                    self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
                    for guard in (engine, core_engine, dice, autosave, save):
                        guard.assert_not_called()
                    self.assertEqual(self.snapshot(restored), before)
                    self.assertEqual((
                        restored.game_session.messages, restored.game_session.world_metadata,
                    ), before_auxiliary)
                    self.assertEqual(saved_rows(), before_rows)
                    self.assertEqual(
                        fresh_store.get_turn_action(campaign_id, rest_command["action_id"]),
                        original_receipt,
                    )
                    self.assertEqual(
                        fresh.get_turn_action(restored, rest_command["action_id"]),
                        original_receipt,
                    )

    async def test_saved_rest_action_rejects_ambient_event_after_reopen(self):
        for rest_action in ("short_rest", "long_rest"):
            with self.subTest(rest_action=rest_action):
                created = await self.create_campaign()
                campaign_id = created["campaign_id"]
                record = self.manager.get(created["session_id"])
                session = record.game_session
                session.commit_location_change("tavern")
                session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
                session.initialize_species_trait_state()
                session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
                self.manager.save_campaign(campaign_id)
                rest_command = {"action": rest_action, "action_id": str(uuid4())}
                elapsed_before = session.world_state["campaign_time"]["elapsed_seconds"]
                accepted = await self.http.post(
                    f"/api/game/sessions/{created['session_id']}/species-actions",
                    json=rest_command,
                )
                self.assertEqual(accepted.status_code, 200, accepted.text)
                self.assertEqual(accepted.json()["result"]["action"], rest_action)
                self.assertEqual(
                    session.character["species_trait_state"]["adrenaline_rush_uses_remaining"],
                    session.character["proficiency_bonus"],
                )
                self.assertEqual(
                    session.world_state["campaign_time"]["elapsed_seconds"] - elapsed_before,
                    3600 if rest_action == "short_rest" else 28800,
                )
                if rest_action == "long_rest":
                    self.assertEqual(session.character["current_hp"], 20)
                original_receipt = copy.deepcopy(
                    self.store.get_turn_action(campaign_id, rest_command["action_id"])
                )
                self.assertEqual(original_receipt["response"], accepted.json())

                # Materialize a valid, unresolved event after the rest so the
                # rest's elapsed time cannot expire the test's referent.
                event_id = self.install_test_ambient_event(session)
                self.manager.save_campaign(campaign_id)
                committed = self.snapshot(record)
                self.assertEqual(len(committed[-1].history), 1)
                self.assertEqual(
                    self.store.get_turn_action(campaign_id, rest_command["action_id"]),
                    original_receipt,
                )

                fresh_store = CampaignStore(self.store.path)
                fresh = SessionManager(campaign_store=fresh_store)
                app = create_app(session_manager=fresh, ollama_adapter=None)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                            base_url="http://reload") as client:
                    resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
                    self.assertEqual(resumed.status_code, 200, resumed.text)
                    sid = resumed.json()["session_id"]
                    restored = fresh.get(sid)
                    self.assertNotEqual(sid, created["session_id"])
                    self.assertIsNot(restored.game_session, session)
                    self.assertEqual(self.snapshot(restored)[:7], committed[:7])
                    self.assertEqual(resumed.json()["history"], committed[-1].history)
                    self.assertEqual(
                        resumed.json()["state"]["scene"]["ambient_event"]["instance_id"],
                        event_id,
                    )
                    self.assertEqual(
                        fresh_store.get_turn_action(campaign_id, rest_command["action_id"]),
                        original_receipt,
                    )
                    self.assertEqual(
                        fresh.get_turn_action(restored, rest_command["action_id"]),
                        original_receipt,
                    )

                    # Resume may update last-played metadata. Capture every
                    # owner after resume, immediately before the conflict.
                    before = self.snapshot(restored)
                    before_auxiliary = copy.deepcopy((
                        restored.game_session.messages, restored.game_session.world_metadata,
                    ))

                    def saved_rows():
                        with closing(fresh_store._connect()) as connection:
                            return {
                                table: [tuple(row) for row in connection.execute(
                                    f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                                    (campaign_id,),
                                )]
                                for table in ("campaigns", "campaign_turn_actions",
                                              "campaign_history", "campaign_combat_history")
                            }

                    before_rows = saved_rows()
                    event_url = (
                        f"/api/game/sessions/{sid}/ambient-events/{event_id}/actions"
                    )
                    with patch.object(
                        restored.game_session, "resolve_ambient_event_action",
                        side_effect=AssertionError("Rest ID resolved an ambient event"),
                    ) as resolve, \
                         patch.object(restored.game_session.rng, "randint",
                                      side_effect=AssertionError("Rest ID consumed dice")) as dice, \
                         patch.object(fresh, "save_campaign_locked",
                                      side_effect=AssertionError("Rest ID saved an event")) as save_locked, \
                         patch.object(fresh_store, "save_campaign",
                                      side_effect=AssertionError("Rest ID wrote SQL")) as save:
                        conflict = await client.post(event_url, json={
                            "action": "interact", "action_id": rest_command["action_id"],
                        })
                    self.assertEqual(conflict.status_code, 200, conflict.text)
                    result = conflict.json()["result"]
                    self.assertEqual(result["status"], "REJECTED")
                    self.assertEqual(result["reason_code"], "action_id_conflict")
                    self.assertEqual(result["action_id"], rest_command["action_id"])
                    self.assertEqual(result["event_instance_id"], event_id)
                    self.assertIsNone(result["transition_id"])
                    self.assertIsNone(result["canonical_event_id"])
                    for guard in (resolve, dice, save_locked, save):
                        guard.assert_not_called()
                    self.assertEqual(self.snapshot(restored), before)
                    self.assertEqual((
                        restored.game_session.messages, restored.game_session.world_metadata,
                    ), before_auxiliary)
                    self.assertEqual(saved_rows(), before_rows)
                    self.assertEqual(
                        fresh_store.get_turn_action(campaign_id, rest_command["action_id"]),
                        original_receipt,
                    )
                    self.assertEqual(
                        fresh.get_turn_action(restored, rest_command["action_id"]),
                        original_receipt,
                    )

                    # A new ID applies the very same event through the real
                    # engine/API, proving rejection was not an invalid fixture.
                    applied = await client.post(event_url, json={
                        "action": "interact", "action_id": str(uuid4()),
                    })
                    self.assertEqual(applied.status_code, 200, applied.text)
                    self.assertEqual(applied.json()["result"]["status"], "APPLIED")
                    self.assertTrue(applied.json()["result"]["canonical_event_id"])
                    self.assertEqual(
                        fresh_store.get_turn_action(campaign_id, rest_command["action_id"]),
                        original_receipt,
                    )

    async def test_persisted_ambient_receipt_isolated_from_autosave_input_edits(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        event_id = self.install_test_ambient_event(record.game_session)
        self.manager.save_campaign(campaign_id)
        command = {"action": "interact", "action_id": str(uuid4())}
        endpoint = f"ambient-events/{event_id}/actions"

        # The ambient HTTP owner normally uses save_campaign_locked. For this
        # autosave-input regression, forward its real receipt into the real
        # autosave once, before it commits (a committed ID cannot be resaved).
        # Only the persistence entry point is adapted; mechanics, serialization,
        # SQL and replay all remain real.
        def persist_via_autosave(active_record, *, turn_action_receipt):
            return self.manager.autosave_turn(
                active_record, "Interact with the ambient event.", "The traveler responds.",
                turn_action_receipt=turn_action_receipt,
            )

        with patch.object(self.manager, "save_campaign_locked",
                          side_effect=persist_via_autosave) as locked_save, \
             patch.object(self.manager, "autosave_turn",
                          wraps=self.manager.autosave_turn) as autosave:
            accepted = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/{endpoint}", json=command,
            )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
        locked_save.assert_called_once()
        supplied = locked_save.call_args.kwargs["turn_action_receipt"]
        autosave.assert_called_once()
        self.assertIs(autosave.call_args.args[0], record)
        self.assertIs(autosave.call_args.kwargs["turn_action_receipt"], supplied)
        supplied_original = copy.deepcopy(supplied)
        original = copy.deepcopy(self.store.get_turn_action(campaign_id, command["action_id"]))
        self.assertEqual(supplied["action_id"], command["action_id"])
        self.assertEqual(supplied["request_hash"], original["request_hash"])
        self.assertEqual(supplied["response"], original["response"])
        self.assertEqual(original["response"]["ambient_event_response"], accepted.json())
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
        committed = self.snapshot(record)

        # Only edit nested response data: ownership IDs, request hash and the
        # receipt envelope stay valid. Exercise dict and list alias boundaries.
        response = supplied["response"]["ambient_event_response"]
        self.assertTrue(response["result"]["transition_id"])
        self.assertTrue(response["result"]["canonical_event_id"])
        response["result"]["transition_id"] = "caller-only-transition"
        response["result"]["canonical_event_id"] = str(uuid4())
        response["state"]["character"]["current_hp"] = -999
        self.assertTrue(response["state"]["npcs"])
        response["state"]["npcs"][0]["name"] = "Caller-only NPC"
        response["state"]["npcs"].clear()
        self.assertNotEqual(supplied, supplied_original)
        unchanged_envelope = copy.deepcopy(supplied)
        unchanged_envelope["response"]["ambient_event_response"] = copy.deepcopy(
            supplied_original["response"]["ambient_event_response"]
        )
        self.assertEqual(unchanged_envelope, supplied_original)
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
        self.assertEqual(self.store.get_turn_action(campaign_id, command["action_id"]), original)
        self.assertEqual(self.snapshot(record), committed)

        # This owner deliberately projects ALREADY_APPLIED on retry, rather
        # than returning APPLIED again. All other response fields stay exact.
        expected = copy.deepcopy(accepted.json())
        expected["result"].update(
            status="ALREADY_APPLIED", reason_code="event_already_resolved",
        )

        async def assert_replay(client, manager, store, active_record, sid):
            before = self.snapshot(active_record)
            auxiliary = copy.deepcopy((
                active_record.game_session.messages,
                active_record.game_session.world_metadata,
            ))

            def saved_rows():
                with closing(store._connect()) as connection:
                    return {
                        table: [tuple(row) for row in connection.execute(
                            f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                            (campaign_id,),
                        )]
                        for table in ("campaigns", "campaign_turn_actions",
                                      "campaign_history", "campaign_combat_history")
                    }

            rows = saved_rows()
            replay_expected = copy.deepcopy(expected)
            replay_expected["session_id"] = sid
            with patch.object(
                active_record.game_session, "resolve_ambient_event_action",
                side_effect=AssertionError("Replay repeated ambient mechanics"),
            ) as mechanics, \
                 patch.object(active_record.game_session.rng, "randint",
                              side_effect=AssertionError("Replay consumed RNG")) as dice, \
                 patch.object(manager, "autosave_turn",
                              side_effect=AssertionError("Replay autosaved")) as autosave, \
                 patch.object(manager, "save_campaign_locked",
                              side_effect=AssertionError("Replay saved")) as locked_save, \
                 patch.object(store, "save_campaign",
                              side_effect=AssertionError("Replay wrote SQL")) as save:
                replay = await client.post(
                    f"/api/game/sessions/{sid}/{endpoint}", json=command,
                )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), replay_expected)
            for guard in (mechanics, dice, autosave, locked_save, save):
                guard.assert_not_called()
            self.assertEqual(manager.get_turn_action(active_record, command["action_id"]), original)
            self.assertEqual(store.get_turn_action(campaign_id, command["action_id"]), original)
            self.assertEqual(self.snapshot(active_record), before)
            self.assertEqual((
                active_record.game_session.messages,
                active_record.game_session.world_metadata,
            ), auxiliary)
            self.assertEqual(saved_rows(), rows)

        await assert_replay(self.http, self.manager, self.store, record, created["session_id"])
        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://reload") as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = fresh.get(sid)
            self.assertNotEqual(sid, created["session_id"])
            self.assertIsNot(restored.game_session, record.game_session)
            self.assertEqual(self.snapshot(restored)[:7], committed[:7])
            self.assertEqual(fresh_store.get_campaign(campaign_id).payload, committed[-1].payload)
            self.assertEqual(resumed.json()["history"], committed[-1].history)
            self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original)
            self.assertEqual(fresh_store.get_turn_action(campaign_id, command["action_id"]), original)
            # Resume can update last-played metadata. The helper captures full
            # runtime and raw SQL snapshots only after resume, before replay.
            await assert_replay(client, fresh, fresh_store, restored, sid)

    async def test_persisted_ambient_receipt_isolated_from_native_save_input_edits(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        event_id = self.install_test_ambient_event(record.game_session)
        self.manager.save_campaign(campaign_id)
        command = {"action": "interact", "action_id": str(uuid4())}
        endpoint = f"ambient-events/{event_id}/actions"
        before_acceptance = self.snapshot(record)

        # Capture the endpoint's actual caller-owned receipt without adapting
        # persistence: the native locked-save path must commit it itself.
        with patch.object(self.manager, "save_campaign_locked",
                          wraps=self.manager.save_campaign_locked) as locked_save, \
             patch.object(self.manager, "autosave_turn",
                          wraps=self.manager.autosave_turn) as autosave, \
             patch.object(self.store, "save_campaign",
                          wraps=self.store.save_campaign) as save:
            accepted = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/{endpoint}", json=command,
            )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
        locked_save.assert_called_once()
        self.assertIs(locked_save.call_args.args[0], record)
        autosave.assert_not_called()
        save.assert_called_once()
        supplied = locked_save.call_args.kwargs["turn_action_receipt"]
        self.assertIs(save.call_args.kwargs["turn_action_receipt"], supplied)
        supplied_original = copy.deepcopy(supplied)
        original = copy.deepcopy(self.store.get_turn_action(campaign_id, command["action_id"]))
        self.assertEqual(supplied["action_id"], command["action_id"])
        self.assertEqual(supplied["request_hash"], original["request_hash"])
        self.assertEqual(supplied["response"], original["response"])
        self.assertEqual(original["response"]["ambient_event_response"], accepted.json())
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
        committed = self.snapshot(record)
        self.assertNotEqual(committed[0], before_acceptance[0])
        # Unlike the adapted autosave test, native event saves add no turn history.
        self.assertEqual(committed[-1].history, before_acceptance[-1].history)

        def saved_rows(store):
            with closing(store._connect()) as connection:
                return {
                    table: [tuple(row) for row in connection.execute(
                        f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                        (campaign_id,),
                    )]
                    for table in ("campaigns", "campaign_turn_actions",
                                  "campaign_history", "campaign_combat_history")
                }

        committed_rows = saved_rows(self.store)
        auxiliary = copy.deepcopy((
            record.game_session.messages, record.game_session.world_metadata,
        ))
        # Mutate only nested response dictionaries/list data, never ownership
        # IDs, request identity, or the envelope. This is not a corruption test.
        response = supplied["response"]["ambient_event_response"]
        self.assertTrue(response["result"]["transition_id"])
        self.assertTrue(response["result"]["canonical_event_id"])
        response["result"]["transition_id"] = "caller-only-transition"
        response["result"]["canonical_event_id"] = str(uuid4())
        response["state"]["character"]["current_hp"] = -999
        self.assertTrue(response["state"]["npcs"])
        response["state"]["npcs"][0]["name"] = "Caller-only NPC"
        response["state"]["npcs"].clear()
        self.assertNotEqual(supplied, supplied_original)
        unchanged_envelope = copy.deepcopy(supplied)
        unchanged_envelope["response"]["ambient_event_response"] = copy.deepcopy(
            supplied_original["response"]["ambient_event_response"]
        )
        self.assertEqual(unchanged_envelope, supplied_original)
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
        self.assertEqual(self.store.get_turn_action(campaign_id, command["action_id"]), original)
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual((
            record.game_session.messages, record.game_session.world_metadata,
        ), auxiliary)
        self.assertEqual(saved_rows(self.store), committed_rows)

        expected = copy.deepcopy(accepted.json())
        expected["result"].update(
            status="ALREADY_APPLIED", reason_code="event_already_resolved",
        )

        async def assert_replay(client, manager, store, active_record, sid):
            # Take these baselines here, including after resume: reopening may
            # legitimately refresh campaign metadata, but replay must not.
            before = self.snapshot(active_record)
            auxiliary = copy.deepcopy((
                active_record.game_session.messages,
                active_record.game_session.world_metadata,
            ))
            rows = saved_rows(store)
            replay_expected = copy.deepcopy(expected)
            replay_expected["session_id"] = sid
            with patch.object(
                active_record.game_session, "resolve_ambient_event_action",
                side_effect=AssertionError("Replay repeated ambient mechanics"),
            ) as mechanics, \
                 patch.object(active_record.game_session.rng, "randint",
                              side_effect=AssertionError("Replay consumed RNG")) as dice, \
                 patch.object(manager, "autosave_turn",
                              side_effect=AssertionError("Replay autosaved")) as autosave, \
                 patch.object(manager, "save_campaign_locked",
                              side_effect=AssertionError("Replay saved")) as locked_save, \
                 patch.object(store, "save_campaign",
                              side_effect=AssertionError("Replay wrote SQL")) as save:
                replay = await client.post(
                    f"/api/game/sessions/{sid}/{endpoint}", json=command,
                )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), replay_expected)
            for guard in (mechanics, dice, autosave, locked_save, save):
                guard.assert_not_called()
            self.assertEqual(manager.get_turn_action(active_record, command["action_id"]), original)
            self.assertEqual(store.get_turn_action(campaign_id, command["action_id"]), original)
            self.assertEqual(self.snapshot(active_record), before)
            self.assertEqual((
                active_record.game_session.messages,
                active_record.game_session.world_metadata,
            ), auxiliary)
            self.assertEqual(saved_rows(store), rows)

        await assert_replay(self.http, self.manager, self.store, record, created["session_id"])
        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://reload") as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = fresh.get(sid)
            self.assertNotEqual(sid, created["session_id"])
            self.assertIsNot(restored.game_session, record.game_session)
            self.assertEqual(self.snapshot(restored)[:7], committed[:7])
            self.assertEqual(fresh_store.get_campaign(campaign_id).payload, committed[-1].payload)
            self.assertEqual(resumed.json()["history"], committed[-1].history)
            self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original)
            self.assertEqual(fresh_store.get_turn_action(campaign_id, command["action_id"]), original)
            await assert_replay(client, fresh, fresh_store, restored, sid)

    async def test_persisted_ambient_receipt_isolated_from_reader_output_edits(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        event_id = self.install_test_ambient_event(record.game_session)
        self.manager.save_campaign(campaign_id)
        command = {"action": "interact", "action_id": str(uuid4())}
        endpoint = f"ambient-events/{event_id}/actions"
        accepted = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/{endpoint}", json=command,
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
        original = copy.deepcopy(self.store.get_turn_action(campaign_id, command["action_id"]))
        self.assertEqual(original["response"]["ambient_event_response"], accepted.json())
        committed = self.snapshot(record)
        expected = copy.deepcopy(accepted.json())
        expected["result"].update(
            status="ALREADY_APPLIED", reason_code="event_already_resolved",
        )

        def saved_rows(store):
            with closing(store._connect()) as connection:
                return {
                    table: [tuple(row) for row in connection.execute(
                        f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                        (campaign_id,),
                    )]
                    for table in ("campaigns", "campaign_turn_actions",
                                  "campaign_history", "campaign_combat_history")
                }

        async def assert_reader_isolation(client, manager, store, active_record, sid, phase):
            # Resume may refresh campaign timestamps. Capture complete runtime
            # and SQL baselines here, after resume and before any caller edits.
            before = self.snapshot(active_record)
            auxiliary = copy.deepcopy((
                active_record.game_session.messages,
                active_record.game_session.world_metadata,
            ))
            rows = saved_rows(store)
            replay_expected = copy.deepcopy(expected)
            replay_expected["session_id"] = sid

            def assert_unchanged():
                self.assertEqual(
                    manager.get_turn_action(active_record, command["action_id"]), original,
                )
                self.assertEqual(store.get_turn_action(campaign_id, command["action_id"]), original)
                self.assertEqual(self.snapshot(active_record), before)
                self.assertEqual((
                    active_record.game_session.messages,
                    active_record.game_session.world_metadata,
                ), auxiliary)
                self.assertEqual(saved_rows(store), rows)

            readers = {
                "manager": lambda: manager.get_turn_action(active_record, command["action_id"]),
                "store": lambda: store.get_turn_action(campaign_id, command["action_id"]),
            }
            for reader_name, read in readers.items():
                with self.subTest(phase=phase, reader=reader_name):
                    with patch.object(
                        active_record.game_session, "resolve_ambient_event_action",
                        side_effect=AssertionError("Reader edit/replay repeated ambient mechanics"),
                    ) as mechanics, \
                         patch.object(active_record.game_session.rng, "randint",
                                      side_effect=AssertionError("Reader edit/replay consumed RNG")) as dice, \
                         patch.object(manager, "autosave_turn",
                                      side_effect=AssertionError("Reader edit/replay autosaved")) as autosave, \
                         patch.object(manager, "save_campaign_locked",
                                      side_effect=AssertionError("Reader edit/replay saved")) as locked_save, \
                         patch.object(store, "save_campaign",
                                      side_effect=AssertionError("Reader edit/replay wrote SQL")) as save:
                        retrieved = read()
                        self.assertEqual(retrieved, original)
                        # Only returned nested response data is changed. Do not
                        # touch save inputs, receipt identity or the envelope.
                        response = retrieved["response"]["ambient_event_response"]
                        self.assertTrue(response["result"]["transition_id"])
                        self.assertTrue(response["result"]["canonical_event_id"])
                        response["result"]["transition_id"] = "reader-only-transition"
                        response["result"]["canonical_event_id"] = str(uuid4())
                        response["state"]["character"]["current_hp"] = -999
                        self.assertTrue(response["state"]["npcs"])
                        response["state"]["npcs"][0]["name"] = "Reader-only NPC"
                        self.assertNotEqual(retrieved, original)
                        assert_unchanged()
                        response["state"]["npcs"].clear()
                        self.assertNotEqual(
                            response["state"]["npcs"],
                            original["response"]["ambient_event_response"]["state"]["npcs"],
                        )
                        unchanged_envelope = copy.deepcopy(retrieved)
                        unchanged_envelope["response"]["ambient_event_response"] = copy.deepcopy(
                            original["response"]["ambient_event_response"]
                        )
                        self.assertEqual(unchanged_envelope, original)
                        assert_unchanged()
                        replay = await client.post(
                            f"/api/game/sessions/{sid}/{endpoint}", json=command,
                        )
                    self.assertEqual(replay.status_code, 200, replay.text)
                    self.assertEqual(replay.json(), replay_expected)
                    for guard in (mechanics, dice, autosave, locked_save, save):
                        guard.assert_not_called()
                    assert_unchanged()

        await assert_reader_isolation(
            self.http, self.manager, self.store, record, created["session_id"], "before_resume",
        )
        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://reload") as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = fresh.get(sid)
            self.assertNotEqual(sid, created["session_id"])
            self.assertIsNot(restored.game_session, record.game_session)
            self.assertEqual(self.snapshot(restored)[:7], committed[:7])
            self.assertEqual(fresh_store.get_campaign(campaign_id).payload, committed[-1].payload)
            self.assertEqual(resumed.json()["history"], committed[-1].history)
            await assert_reader_isolation(
                client, fresh, fresh_store, restored, sid, "after_resume",
            )

    async def test_saved_ambient_event_action_rejects_rests_after_reopen(self):
        for rest_action in ("short_rest", "long_rest"):
            with self.subTest(rest_action=rest_action):
                created = await self.create_campaign()
                campaign_id = created["campaign_id"]
                record = self.manager.get(created["session_id"])
                session = record.game_session
                session.commit_location_change("tavern")
                session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
                session.initialize_species_trait_state()
                session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
                event_id = self.install_test_ambient_event(session)
                self.manager.save_campaign(campaign_id)
                action_id = str(uuid4())
                accepted = await self.http.post(
                    f"/api/game/sessions/{created['session_id']}/ambient-events/{event_id}/actions",
                    json={"action": "interact", "action_id": action_id},
                )
                self.assertEqual(accepted.status_code, 200, accepted.text)
                self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
                self.assertTrue(accepted.json()["result"]["canonical_event_id"])
                original_receipt = copy.deepcopy(
                    self.store.get_turn_action(campaign_id, action_id)
                )
                self.assertEqual(
                    original_receipt["response"]["ambient_event_response"], accepted.json(),
                )
                committed = self.snapshot(record)
                self.assertTrue(record.journal["notable_events"])

                fresh_store = CampaignStore(self.store.path)
                fresh = SessionManager(campaign_store=fresh_store)
                app = create_app(session_manager=fresh, ollama_adapter=None)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                            base_url="http://reload") as client:
                    resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
                    self.assertEqual(resumed.status_code, 200, resumed.text)
                    sid = resumed.json()["session_id"]
                    restored = fresh.get(sid)
                    self.assertNotEqual(sid, created["session_id"])
                    self.assertIsNot(restored.game_session, session)
                    self.assertEqual(self.snapshot(restored)[:7], committed[:7])
                    self.assertEqual(resumed.json()["history"], committed[-1].history)
                    self.assertEqual(fresh_store.get_turn_action(campaign_id, action_id),
                                     original_receipt)
                    self.assertEqual(fresh.get_turn_action(restored, action_id), original_receipt)

                    # Resume may update last-played metadata; compare complete
                    # runtime and storage owners immediately before the conflict.
                    before = self.snapshot(restored)
                    before_auxiliary = copy.deepcopy((
                        restored.game_session.messages, restored.game_session.world_metadata,
                    ))

                    def saved_rows():
                        with closing(fresh_store._connect()) as connection:
                            return {
                                table: [tuple(row) for row in connection.execute(
                                    f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                                    (campaign_id,),
                                )]
                                for table in ("campaigns", "campaign_turn_actions",
                                              "campaign_history", "campaign_combat_history")
                            }

                    before_rows = saved_rows()
                    rest_url = f"/api/game/sessions/{sid}/species-actions"
                    with patch.object(
                        restored.game_session, "resolve_species_trait_action",
                        side_effect=AssertionError("Ambient ID executed rest mechanics"),
                    ) as resolve, \
                         patch("game.resolve_species_trait_action",
                               side_effect=AssertionError("Ambient ID executed engine rest")) as engine, \
                         patch.object(restored.game_session.rng, "randint",
                                      side_effect=AssertionError("Ambient ID consumed dice")) as dice, \
                         patch.object(fresh, "autosave_turn",
                                      side_effect=AssertionError("Ambient ID autosaved rest")) as autosave, \
                         patch.object(fresh, "save_campaign_locked",
                                      side_effect=AssertionError("Ambient ID saved rest")) as save_locked, \
                         patch.object(fresh_store, "save_campaign",
                                      side_effect=AssertionError("Ambient ID wrote SQL")) as save:
                        conflict = await client.post(rest_url, json={
                            "action": rest_action, "action_id": action_id,
                        })
                    self.assertEqual(conflict.status_code, 409, conflict.text)
                    self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
                    self.assertIsInstance(conflict.json()["detail"]["message"], str)
                    self.assertTrue(conflict.json()["detail"]["message"])
                    for guard in (resolve, engine, dice, autosave, save_locked, save):
                        guard.assert_not_called()
                    self.assertEqual(self.snapshot(restored), before)
                    self.assertEqual((
                        restored.game_session.messages, restored.game_session.world_metadata,
                    ), before_auxiliary)
                    self.assertEqual(fresh_store.get_campaign(campaign_id), before[-1])
                    self.assertEqual(saved_rows(), before_rows)
                    self.assertEqual(fresh_store.get_turn_action(campaign_id, action_id),
                                     original_receipt)
                    self.assertEqual(fresh.get_turn_action(restored, action_id), original_receipt)

                    # The same rest with a fresh ID must really execute and
                    # persist, rather than being rejected by an invalid setup.
                    new_action_id = str(uuid4())
                    elapsed_before = restored.game_session.world_state[
                        "campaign_time"
                    ]["elapsed_seconds"]
                    applied = await client.post(rest_url, json={
                        "action": rest_action, "action_id": new_action_id,
                    })
                    self.assertEqual(applied.status_code, 200, applied.text)
                    self.assertEqual(applied.json()["result"]["action"], rest_action)
                    self.assertEqual(
                        restored.game_session.character["species_trait_state"][
                            "adrenaline_rush_uses_remaining"
                        ],
                        restored.game_session.character["proficiency_bonus"],
                    )
                    self.assertEqual(
                        restored.game_session.world_state["campaign_time"]["elapsed_seconds"]
                        - elapsed_before,
                        3600 if rest_action == "short_rest" else 28800,
                    )
                    if rest_action == "long_rest":
                        self.assertEqual(restored.game_session.character["current_hp"], 20)
                    self.assertEqual(
                        fresh_store.get_turn_action(campaign_id, new_action_id)["response"],
                        applied.json(),
                    )
                    self.assertEqual(
                        len(fresh_store.get_campaign(campaign_id).history),
                        len(before[-1].history) + 1,
                    )
                    self.assertNotEqual(saved_rows(), before_rows)
                    self.assertEqual(fresh_store.get_turn_action(campaign_id, action_id),
                                     original_receipt)
                    self.assertEqual(fresh.get_turn_action(restored, action_id), original_receipt)

    async def test_combat_receipt_replays_original_snapshot_after_later_turn_and_reopen(self):
        a, b = await self.create_campaign(), await self.create_campaign()
        record, command = self.prepare_spell(a)
        other, _ = self.prepare_spell(b)
        isolated = self.snapshot(other)
        session = record.game_session
        # Keep the encounter alive while the next turn resets nested resources.
        session.character["armor_class"] = 100
        self.manager.save_campaign(a["campaign_id"])
        combat = session.world_state["combat"]
        command.update(combat_id=combat["combat_id"], combat_round=combat["round"],
                       combat_turn_index=combat["current_turn_index"])
        first = await self.post(a, command)
        self.assertEqual(first.status_code, 200, first.text)
        expected = copy.deepcopy(first.json())
        # The public API exposes combat.turn_resources as action_economy actors,
        # not as a raw engine combat dictionary.
        resources = expected["state"]["combat"]["action_economy"]["actors"]
        canonical_resources = copy.deepcopy(session.world_state["combat"]["turn_resources"])
        for actor, values in canonical_resources.items():
            for key, value in values.items():
                self.assertEqual(resources[actor][key], value)
        self.assertTrue(resources["player"]["base_action_spent"])
        original_receipt = copy.deepcopy(
            self.manager.get_turn_action(record, command["action_id"])
        )
        self.assertEqual(original_receipt["response"], expected)
        later = await self.post(a, {
            "message": "End this combat turn.", "action_id": str(uuid4()),
            "combat_action": {"steps": [{"kind": "end_turn"}]},
        })
        self.assertEqual(later.status_code, 200, later.text)
        latest_combat = later.json()["state"]["combat"]
        self.assertGreater(latest_combat["round"],
                           expected["state"]["combat"]["round"])
        self.assertFalse(latest_combat["action_economy"]["actors"]["player"]["base_action_spent"])
        self.assertNotEqual(latest_combat["action_economy"]["actors"], resources)
        self.assertNotEqual(session.world_state["combat"]["turn_resources"], canonical_resources)
        self.assertEqual(len(self.store.get_campaign(a["campaign_id"]).history), 2)
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]),
                         original_receipt)
        committed = self.snapshot(record)
        self.assertEqual(self.snapshot(other), isolated)

        # The original combat context is stale, but its receipt must win before
        # context validation, mechanics, RNG, or another autosave can run.
        with patch("game.run_player_turn",
                   side_effect=AssertionError("replayed mechanics")), \
             patch.object(session.rng, "randint",
                          side_effect=AssertionError("replayed RNG")):
            replay = await self.post(a, command)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), expected)
        self.assertEqual(replay.json()["state"]["combat"]["action_economy"]["actors"], resources)
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual(self.snapshot(other), isolated)
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]),
                         original_receipt)

        fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
        resume_time = (
            datetime.fromisoformat(committed[-1].metadata["last_played_at"])
            + timedelta(seconds=2)
        ).isoformat()
        with patch("api.persistence.campaign_store._now",
                   return_value=resume_time) as resume_clock:
            sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
        resume_clock.assert_called_once_with()
        # Resume legitimately updates this one metadata field. Force a clock
        # boundary and preserve exact equality for every other saved field.
        committed_after_resume = copy.deepcopy(committed)
        committed_after_resume[-1].metadata["last_played_at"] = resume_time
        self.assertEqual(self.snapshot(record), committed_after_resume)
        self.assertIsNot(restored.game_session, session)
        self.assertEqual(restored.game_session.serialize_game_state(),
                         session.serialize_game_state())
        self.assertEqual(restored.game_session.rng.getstate(), session.rng.getstate())
        self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original_receipt)
        before = self.snapshot(restored)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        with patch("game.run_player_turn",
                   side_effect=AssertionError("replayed mechanics after reopen")), \
             patch.object(restored.game_session.rng, "randint",
                          side_effect=AssertionError("replayed RNG after reopen")):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://reload") as client:
                replay = await client.post(f"/api/game/sessions/{sid}/turn", json=command)
        # Only the transport session identity changes when reopening a campaign.
        reopened_expected = copy.deepcopy(expected)
        reopened_expected["session_id"] = sid
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), reopened_expected)
        self.assertEqual(replay.json()["state"]["combat"]["action_economy"]["actors"], resources)
        self.assertEqual(self.snapshot(restored), before)
        self.assertEqual(self.snapshot(record), committed_after_resume)
        self.assertEqual(self.snapshot(other), isolated)
        self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original_receipt)

    async def assert_combat_receipt_isolation(self, persisted, *, edit_input=False):
        if persisted:
            a, b = await self.create_campaign(), await self.create_campaign()
        else:
            created = [await self.http.post("/api/game/sessions") for _ in range(2)]
            for response in created:
                self.assertEqual(response.status_code, 200, response.text)
            a, b = [response.json() for response in created]
        record, command = self.prepare_spell(a)
        other, other_command = self.prepare_spell(b)
        self.assertEqual(record.campaign_id is not None, persisted)
        self.assertEqual(other.campaign_id is not None, persisted)
        # Identical action IDs still belong to independent campaign/session owners.
        other_command["action_id"] = command["action_id"]
        other_response = await self.post(b, other_command)
        # Retain the actual caller-owned input, not a lookup copy or an HTTP
        # JSON decode. The real autosave still performs its normal commit.
        with patch.object(self.manager, "autosave_turn",
                          wraps=self.manager.autosave_turn) as autosave:
            first = await self.post(a, command)
        autosave.assert_called_once()
        supplied = autosave.call_args.kwargs["turn_action_receipt"]
        self.assertEqual(other_response.status_code, 200, other_response.text)
        self.assertEqual(first.status_code, 200, first.text)
        expected = copy.deepcopy(first.json())
        original = copy.deepcopy(self.manager.get_turn_action(record, command["action_id"]))
        other_original = copy.deepcopy(
            self.manager.get_turn_action(other, command["action_id"])
        )
        self.assertEqual(original["response"], expected)
        self.assertEqual(supplied["response"], expected)
        self.assertEqual(supplied["request_hash"], original["request_hash"])
        self.assertEqual(supplied["action_id"], command["action_id"])
        supplied_original = copy.deepcopy(supplied)
        self.assertEqual(other_original["response"], other_response.json())
        committed, isolated = self.snapshot(record), self.snapshot(other)

        # Exercise the input-to-owner and owner-to-lookup boundaries separately.
        caller_receipt = (supplied if edit_input else
                          self.manager.get_turn_action(record, command["action_id"]))
        actors = caller_receipt["response"]["state"]["combat"]["action_economy"]["actors"]
        original_actors = original["response"]["state"]["combat"]["action_economy"]["actors"]
        self.assertTrue(actors["player"]["base_action_spent"])
        self.assertGreater(len(actors), 1)
        self.assertIsNot(actors, original_actors)
        actors["player"]["base_action_spent"] = False
        actors["player"]["caller_only"] = {"spent": ["corrupted"]}
        enemy_id = next(actor for actor in actors if actor != "player")
        actors[enemy_id].clear()
        actors["caller_only_actor"] = {"base_action_spent": True}
        self.assertNotEqual(caller_receipt,
                            supplied_original if edit_input else original)
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
        self.assertEqual(self.manager.get_turn_action(other, command["action_id"]), other_original)
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual(self.snapshot(other), isolated)

        with patch("game.run_player_turn", side_effect=AssertionError("replayed mechanics")), \
             patch.object(record.game_session.rng, "randint",
                          side_effect=AssertionError("replayed RNG")), \
             patch.object(other.game_session.rng, "randint",
                          side_effect=AssertionError("replayed isolated RNG")), \
             patch.object(self.manager, "autosave_turn",
                          side_effect=AssertionError("replayed autosave")):
            replay = await self.post(a, command)
            other_replay = await self.post(b, other_command)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(other_replay.status_code, 200, other_replay.text)
        self.assertEqual(replay.json(), expected)
        self.assertEqual(other_replay.json(), other_response.json())
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
        self.assertEqual(self.manager.get_turn_action(other, command["action_id"]), other_original)
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual(self.snapshot(other), isolated)

        if persisted:
            fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
            saved = committed[-1]
            resume_time = (
                datetime.fromisoformat(saved.metadata["last_played_at"])
                + timedelta(days=1)
            ).isoformat(timespec="seconds")
            saved_receipt = copy.deepcopy(
                self.store.get_turn_action(a["campaign_id"], command["action_id"])
            )
            with patch("api.persistence.campaign_store._now",
                       return_value=resume_time) as resume_clock:
                sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
            resume_clock.assert_called_once_with()
            # Force a timestamp boundary without sleeping, then preserve every
            # other committed field and baseline replay after resume.
            reopened = self.store.get_campaign(a["campaign_id"])
            self.assertNotEqual(
                reopened.metadata["last_played_at"], saved.metadata["last_played_at"]
            )
            self.assertEqual(reopened.metadata["last_played_at"], resume_time)
            self.assertEqual(reopened.payload, saved.payload)
            self.assertEqual(reopened.history, saved.history)
            self.assertEqual(reopened.combat_history, saved.combat_history)
            self.assertEqual(
                reopened.metadata,
                {**saved.metadata, "last_played_at": resume_time},
            )
            self.assertEqual(
                self.store.get_turn_action(a["campaign_id"], command["action_id"]),
                saved_receipt,
            )
            committed = (*committed[:-1], reopened)
            self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original)
            before = self.snapshot(restored)
            app = create_app(session_manager=fresh, ollama_adapter=None)
            with patch("game.run_player_turn",
                       side_effect=AssertionError("replayed mechanics after reopen")), \
                 patch.object(restored.game_session.rng, "randint",
                              side_effect=AssertionError("replayed RNG after reopen")), \
                 patch.object(fresh, "autosave_turn",
                              side_effect=AssertionError("replayed autosave after reopen")):
                # The resumed manager's lookup is caller-owned too: mutate
                # nested values without changing the command or saved receipt.
                resumed_receipt = fresh.get_turn_action(restored, command["action_id"])
                self.assertEqual(resumed_receipt, original)
                resumed_actors = resumed_receipt["response"]["state"]["combat"][
                    "action_economy"
                ]["actors"]
                self.assertTrue(resumed_actors["player"]["base_action_spent"])
                self.assertGreater(len(resumed_actors), 1)
                resumed_actors["player"]["base_action_spent"] = False
                resumed_actors["player"]["caller_only"] = {"spent": ["corrupted"]}
                resumed_enemy = next(actor for actor in resumed_actors if actor != "player")
                resumed_actors[resumed_enemy].clear()
                resumed_actors["caller_only_actor"] = {"base_action_spent": True}
                self.assertNotEqual(resumed_receipt, original)
                self.assertEqual(
                    fresh.get_turn_action(restored, command["action_id"]), original
                )
                self.assertEqual(
                    self.store.get_turn_action(a["campaign_id"], command["action_id"]),
                    saved_receipt,
                )
                self.assertEqual(self.snapshot(restored), before)
                self.assertEqual(self.snapshot(record), committed)
                self.assertEqual(self.snapshot(other), isolated)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                            base_url="http://reload") as client:
                    replay = await client.post(f"/api/game/sessions/{sid}/turn", json=command)
            reopened_expected = copy.deepcopy(expected)
            reopened_expected["session_id"] = sid
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), reopened_expected)
            self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original)
            self.assertEqual(
                self.store.get_turn_action(a["campaign_id"], command["action_id"]),
                saved_receipt,
            )
            self.assertEqual(self.snapshot(restored), before)
            self.assertEqual(self.snapshot(record), committed)
            self.assertEqual(self.snapshot(other), isolated)

    async def test_persisted_combat_receipt_isolated_from_caller_edits(self):
        await self.assert_combat_receipt_isolation(persisted=True)

    async def test_transient_combat_receipt_isolated_from_caller_edits(self):
        await self.assert_combat_receipt_isolation(persisted=False)

    async def test_persisted_combat_receipt_isolated_from_autosave_input_edits(self):
        await self.assert_combat_receipt_isolation(persisted=True, edit_input=True)

    async def test_transient_combat_receipt_isolated_from_autosave_input_edits(self):
        await self.assert_combat_receipt_isolation(persisted=False, edit_input=True)

    async def assert_combat_history_input_isolation(self, persisted):
        if persisted:
            a = await self.create_campaign()
        else:
            created = await self.http.post("/api/game/sessions")
            self.assertEqual(created.status_code, 200, created.text)
            a = created.json()
        record, command = self.prepare_spell(a)
        self.assertEqual(record.campaign_id is not None, persisted)
        self.assertEqual(record.combat_history, [])

        # Keep a separate saved campaign with its own accepted combat history.
        b = await self.create_campaign()
        other, other_command = self.prepare_spell(b)
        other_response = await self.post(b, other_command)
        self.assertEqual(other_response.status_code, 200, other_response.text)
        isolated = self.snapshot(other)

        # Observe the exact object passed by the real offline turn. A history
        # lookup or response.json() would only test a detached reader copy.
        with patch.object(self.manager, "autosave_turn",
                          wraps=self.manager.autosave_turn) as autosave:
            response = await self.post(a, command)
        self.assertEqual(response.status_code, 200, response.text)
        autosave.assert_called_once()
        self.assertIs(autosave.call_args.args[0], record)
        supplied = autosave.call_args.kwargs["combat_history_entry"]
        original = copy.deepcopy(supplied)
        # HTTP models also emit unset optional fields as null; compare the
        # accepted fields without mistaking that formatting for history data.
        response_result = response.json()["combat_result"]
        self.assertEqual(original["result"],
                         {key: response_result[key] for key in original["result"]})
        self.assertEqual(original["event_id"],
                         response.json()["combat_history_entry"]["event_id"])
        self.assertEqual(record.combat_history, [original])
        self.assertIsNot(record.combat_history[0], supplied)
        committed = self.snapshot(record)
        self.assertEqual(self.snapshot(other), isolated)
        if persisted:
            stored = self.store.get_campaign(a["campaign_id"])
            self.assertEqual(stored.combat_history, [original])
            self.assertEqual(len(stored.history), 1)

        # Edit existing nested data, rather than only adding a new top-level
        # key: both a nested dict alias and a shallow-copied list must be caught.
        steps = supplied["result"]["economy_steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["kind"], "magic")
        spell_result = steps[0]["result"]
        self.assertGreater(spell_result["damage"], 0)
        spell_result["damage"] = -1
        self.assertNotEqual(supplied, original)
        self.assertEqual(record.combat_history, [original])
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual(self.snapshot(other), isolated)
        steps.clear()
        self.assertNotEqual(supplied, original)
        self.assertEqual(record.combat_history, [original])
        # Includes complete RNG state, game state, journal, narrative memory,
        # lore, combat history, receipts, and the entire persisted campaign.
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual(self.snapshot(other), isolated)

        if persisted:
            self.assertEqual(self.store.get_campaign(a["campaign_id"]), stored)
            fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
            _, restored, *_ = fresh.resume_campaign(a["campaign_id"])
            self.assertIsNot(restored.game_session, record.game_session)
            self.assertEqual(restored.combat_history, [original])
            reopened = self.store.get_campaign(a["campaign_id"])
            self.assertEqual(reopened.combat_history, [original])
            self.assertEqual(reopened.history, stored.history)
            self.assertEqual(reopened.payload, stored.payload)
            # Resume may update last-played metadata, not accepted gameplay or
            # any of the in-memory owners (including the full RNG state).
            self.assertEqual(self.snapshot(restored)[:7], committed[:7])
            self.assertEqual(record.combat_history, [original])
            self.assertEqual(self.snapshot(other), isolated)

    async def test_persisted_combat_history_isolated_from_autosave_input_edits(self):
        await self.assert_combat_history_input_isolation(persisted=True)

    async def test_transient_combat_history_isolated_from_autosave_input_edits(self):
        await self.assert_combat_history_input_isolation(persisted=False)

    async def assert_combat_history_engine_ownership(self, persisted):
        if persisted:
            a = await self.create_campaign()
        else:
            created = await self.http.post("/api/game/sessions")
            self.assertEqual(created.status_code, 200, created.text)
            a = created.json()
        record, command = self.prepare_spell(a)
        self.assertEqual(record.campaign_id is not None, persisted)
        session = record.game_session
        session.character["armor_class"] = 100
        if persisted:
            self.manager.save_campaign(a["campaign_id"])

        b = await self.create_campaign()
        other, other_command = self.prepare_spell(b)
        other_response = await self.post(b, other_command)
        self.assertEqual(other_response.status_code, 200, other_response.text)
        isolated = self.snapshot(other)

        captured = []
        real_turn = session.run_player_turn

        # Keep the actual engine objects, not autosave inputs or decoded HTTP
        # copies. Dispatch inspects this callable to forward scene/action IDs.
        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            captured.append(result)
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(len(captured), 1)
        engine_result = captured[0]["action_result"]
        engine_snapshot = copy.deepcopy(engine_result)
        self.assertEqual(engine_result["action"], "action_economy")
        self.assertEqual(engine_result["status"], "resolved")
        self.assertTrue(engine_result["success"])
        self.assertEqual(len(record.combat_history), 1)
        retained = record.combat_history[0]
        original = copy.deepcopy(retained)
        response_entry = accepted.json()["combat_history_entry"]
        self.assertEqual(original["event_id"], response_entry["event_id"])
        self.assertEqual(original["turn_index"], response_entry["turn_index"])
        # HTTP models include unset optional fields as null; history stores
        # only the fields actually accepted from the engine.
        self.assertEqual(original["result"],
                         {key: response_entry["result"][key] for key in original["result"]})
        self.assertEqual(original["result"],
                         {key: engine_result[key] for key in original["result"]})
        self.assertIsNot(retained["result"]["economy_steps"],
                         engine_result["economy_steps"])
        self.assertIsNot(retained["result"]["economy_steps"][0]["result"],
                         engine_result["economy_steps"][0]["result"])
        resources = copy.deepcopy(session.world_state["combat"]["turn_resources"])
        engine_economy = captured[0]["action_economy_result"]["state"]
        economy_snapshot = copy.deepcopy(engine_economy)
        self.assertTrue(resources["player"]["base_action_spent"])
        self.assertTrue(engine_economy["actors"]["player"]["base_action_spent"])
        round_before = session.world_state["combat"]["round"]
        committed = self.snapshot(record)
        if persisted:
            self.assertEqual(self.store.get_campaign(a["campaign_id"]).combat_history,
                             [original])
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual(self.snapshot(other), isolated)

        later = await self.post(a, {
            "message": "End this combat turn.", "action_id": str(uuid4()),
            "combat_action": {"steps": [{"kind": "end_turn"}]},
        })
        self.assertEqual(later.status_code, 200, later.text)
        combat = session.world_state["combat"]
        self.assertTrue(combat["active"])
        self.assertGreater(combat["round"], round_before)
        self.assertFalse(combat["turn_resources"]["player"]["base_action_spent"])
        self.assertNotEqual(combat["turn_resources"], resources)
        self.assertEqual(len(record.combat_history), 2)
        later_committed = self.snapshot(record)
        self.assertEqual(retained, original)
        self.assertEqual(record.combat_history[0], original)
        self.assertEqual(engine_result, engine_snapshot)
        self.assertEqual(engine_economy, economy_snapshot)

        # Editing a retained engine result must not rewrite accepted history.
        # This probes engine-to-history ownership, not autosave-input ownership.
        steps = engine_result["economy_steps"]
        self.assertEqual(steps[0]["kind"], "magic")
        self.assertGreater(steps[0]["result"]["damage"], 0)
        steps[0]["result"]["damage"] = -1
        self.assertNotEqual(engine_result, engine_snapshot)
        self.assertEqual(retained, original)
        self.assertEqual(self.snapshot(record), later_committed)
        self.assertEqual(self.snapshot(other), isolated)
        steps.clear()
        self.assertEqual(retained, original)
        self.assertEqual(record.combat_history[0], original)
        self.assertEqual(self.snapshot(record), later_committed)
        self.assertEqual(self.snapshot(other), isolated)

        if persisted:
            stored = self.store.get_campaign(a["campaign_id"])
            self.assertEqual(stored.combat_history, record.combat_history)
            self.assertEqual(stored.combat_history[0], original)
            self.assertEqual(len(stored.history), 2)
            fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
            _, restored, *_ = fresh.resume_campaign(a["campaign_id"])
            self.assertIsNot(restored.game_session, session)
            before_observation = self.snapshot(restored)
            self.assertEqual(restored.combat_history, stored.combat_history)
            self.assertEqual(restored.combat_history[0], original)
            self.assertEqual(retained, original)
            reopened = self.store.get_campaign(a["campaign_id"])
            self.assertEqual(reopened.combat_history, stored.combat_history)
            self.assertEqual(reopened.history, stored.history)
            self.assertEqual(reopened.payload, stored.payload)
            # Resume can update last-played metadata. All gameplay owners and
            # the complete RNG state must still match the committed turn.
            self.assertEqual(before_observation[:7], later_committed[:7])
            self.assertEqual(self.snapshot(restored), before_observation)
            self.assertEqual(self.snapshot(record)[:7], later_committed[:7])
            self.assertEqual(self.snapshot(other), isolated)

    async def test_persisted_combat_history_owns_engine_result_after_resource_reset(self):
        await self.assert_combat_history_engine_ownership(persisted=True)

    async def test_transient_combat_history_owns_engine_result_after_resource_reset(self):
        await self.assert_combat_history_engine_ownership(persisted=False)

    async def test_real_combat_history_rollover_preserves_surviving_results_on_resume(self):
        a = await self.create_campaign()
        record, command = self.prepare_spell(a)
        session = record.game_session
        # Enough health for the entire bounded-history window, without replacing
        # combat resolution, dice, history serialization, or autosave.
        session.character.update(current_hp=10000, max_hp=10000)
        enemy_id = command["combat_action"]["steps"][0]["target_id"]
        enemy = next(npc for npc in session.world_state["npcs"]
                     if npc["id"] == enemy_id)
        enemy.update(current_hp=10000, max_hp=10000)
        self.manager.save_campaign(a["campaign_id"])
        self.assertEqual(record.combat_history, [])

        b = await self.create_campaign()
        other, other_command = self.prepare_spell(b)
        other_response = await self.post(b, other_command)
        self.assertEqual(other_response.status_code, 200, other_response.text)
        isolated = self.snapshot(other)

        captured = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            captured.append(result)
            return result

        accepted_entries = []
        with patch.object(session, "run_player_turn", new=capture_turn):
            for index in range(MAX_COMBAT_HISTORY_ENTRIES + 2):
                with self.subTest(turn=index):
                    body = copy.deepcopy(command)
                    body["action_id"] = str(uuid4())
                    # The third entry survives both evictions and has guaranteed
                    # nested damage. Other turns advance the real encounter
                    # without spending spell slots or relying on attack modes.
                    if index != 2:
                        body["combat_action"]["steps"] = []
                    body["combat_action"]["steps"].append({"kind": "end_turn"})
                    response = await self.post(a, body)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(len(captured), index + 1)
                    result = captured[-1]["action_result"]
                    self.assertEqual(result["status"], "resolved")
                    self.assertTrue(result["success"])
                    self.assertTrue(session.world_state["combat"]["active"])
                    entry = record.combat_history[-1]
                    response_entry = response.json()["combat_history_entry"]
                    self.assertEqual(entry["event_id"], response_entry["event_id"])
                    self.assertEqual(entry["result"],
                                     {key: result[key] for key in entry["result"]})
                    self.assertEqual(entry["result"],
                                     {key: response_entry["result"][key]
                                      for key in entry["result"]})
                    accepted_entries.append(copy.deepcopy(entry))
                    if index == 2:
                        retained = entry
                        original = copy.deepcopy(retained)
                        engine_result = result
                        engine_snapshot = copy.deepcopy(engine_result)
                        steps = engine_result["economy_steps"]
                        self.assertEqual(steps[0]["kind"], "magic")
                        self.assertGreater(steps[0]["result"]["damage"], 0)
                    # Check the exact chronological window, not just its size.
                    expected = accepted_entries[-MAX_COMBAT_HISTORY_ENTRIES:]
                    self.assertEqual(record.combat_history, expected)
                    if index >= MAX_COMBAT_HISTORY_ENTRIES - 1:
                        committed = self.snapshot(record)
                        stored = self.store.get_campaign(a["campaign_id"])
                        self.assertEqual(stored.combat_history, expected)
                        self.assertEqual(retained, original)
                        self.assertEqual(engine_result, engine_snapshot)
                        self.assertEqual(self.snapshot(record), committed)
                        self.assertEqual(self.snapshot(other), isolated)

        self.assertEqual(len(record.combat_history), MAX_COMBAT_HISTORY_ENTRIES)
        self.assertEqual(record.combat_history[0], original)
        evicted_ids = {entry["event_id"] for entry in accepted_entries[:2]}
        surviving_ids = {entry["event_id"] for entry in record.combat_history}
        self.assertTrue(evicted_ids.isdisjoint(surviving_ids))
        self.assertEqual(len(surviving_ids), MAX_COMBAT_HISTORY_ENTRIES)

        fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
        _, restored, *_ = fresh.resume_campaign(a["campaign_id"])
        self.assertIsNot(restored.game_session, session)
        before_observation = self.snapshot(restored)
        self.assertEqual(restored.combat_history, expected)
        self.assertEqual(restored.combat_history[0], original)
        reopened = self.store.get_campaign(a["campaign_id"])
        self.assertEqual(reopened.combat_history, record.combat_history)
        self.assertEqual(reopened.history, stored.history)
        self.assertEqual(reopened.payload, stored.payload)
        # Resume can change last-played metadata, but no gameplay owner or RNG.
        self.assertEqual(before_observation[:7], committed[:7])
        self.assertEqual(retained, original)
        self.assertEqual(engine_result, engine_snapshot)
        self.assertEqual(self.snapshot(restored), before_observation)
        self.assertEqual(self.snapshot(record)[:7], committed[:7])
        self.assertEqual(self.snapshot(other), isolated)

    async def test_evicted_combat_action_replays_saved_receipt_after_reopen(self):
        await self.assert_evicted_combat_receipt_after_reopen(changed_payload=False)

    async def test_evicted_combat_action_rejects_changed_payload_after_reopen(self):
        await self.assert_evicted_combat_receipt_after_reopen(changed_payload=True)

    async def test_evicted_combat_action_rejects_rest_commands_after_reopen(self):
        for rest_action in ("short_rest", "long_rest"):
            with self.subTest(rest_action=rest_action):
                await self.assert_evicted_combat_receipt_after_reopen(
                    changed_payload=True, rest_action=rest_action,
                )

    async def test_evicted_combat_action_malformed_hash_blocks_all_families_after_reopen(self):
        for label, malformed_hash in (
            ("short", "a" * 63),
            ("overlong", "a" * 65),
            ("nonhex", "g" * 64),
            ("uppercase", "A" * 64),
        ):
            with self.subTest(hash=label):
                await self.assert_evicted_combat_receipt_after_reopen(
                    changed_payload=False, malformed_hash=malformed_hash,
                )

    async def test_evicted_combat_action_invalid_json_blocks_retry_after_reopen(self):
        await self.assert_evicted_combat_receipt_after_reopen(
            changed_payload=False, response_corruption="json",
        )

    async def test_evicted_combat_action_mismatched_response_blocks_retry_after_reopen(self):
        await self.assert_evicted_combat_receipt_after_reopen(
            changed_payload=False, response_corruption="action_id",
        )

    async def test_evicted_combat_action_incomplete_response_blocks_retry_after_reopen(self):
        for field, invalid_value in (
            ("session_id", 123), ("narration", []), ("state", []),
        ):
            for mode in ("missing", "wrong_type"):
                with self.subTest(field=field, mode=mode):
                    await self.assert_evicted_combat_receipt_after_reopen(
                        changed_payload=False,
                        response_corruption=(field, mode, invalid_value),
                    )

    async def assert_evicted_combat_receipt_after_reopen(
        self, *, changed_payload, rest_action=None, malformed_hash=None,
        response_corruption=None,
    ):
        a = await self.create_campaign()
        record, command = self.prepare_spell(a)
        session = record.game_session
        # Keep real combat alive throughout the retention window.
        session.character.update(current_hp=10000, max_hp=10000)
        enemy_id = command["combat_action"]["steps"][0]["target_id"]
        enemy = next(npc for npc in session.world_state["npcs"]
                     if npc["id"] == enemy_id)
        enemy.update(current_hp=10000, max_hp=10000)
        combat = session.world_state["combat"]
        command.update(combat_id=combat["combat_id"], combat_round=combat["round"],
                       combat_turn_index=combat["current_turn_index"])
        command["combat_action"]["steps"].append({"kind": "end_turn"})
        self.manager.save_campaign(a["campaign_id"])
        self.assertEqual(record.combat_history, [])

        accepted_entries = []
        real_turn = session.run_player_turn
        engine_calls = []

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            engine_calls.append(result)
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            for index in range(MAX_COMBAT_HISTORY_ENTRIES + 1):
                with self.subTest(turn=index):
                    body = command if index == 0 else {
                        "message": "End this combat turn.", "action_id": str(uuid4()),
                        "combat_action": {"steps": [{"kind": "end_turn"}]},
                    }
                    response = await self.post(a, body)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(len(engine_calls), index + 1)
                    result = engine_calls[-1]["action_result"]
                    self.assertEqual(result["status"], "resolved")
                    self.assertTrue(result["success"])
                    self.assertTrue(session.world_state["combat"]["active"])
                    entry = copy.deepcopy(record.combat_history[-1])
                    self.assertEqual(entry["event_id"],
                                     response.json()["combat_history_entry"]["event_id"])
                    accepted_entries.append(entry)
                    self.assertEqual(record.combat_history,
                                     accepted_entries[-MAX_COMBAT_HISTORY_ENTRIES:])
                    if index == 0:
                        expected_response = copy.deepcopy(response.json())
                        original_receipt = self.store.get_turn_action(
                            a["campaign_id"], command["action_id"])
                        self.assertEqual(original_receipt["response"], expected_response)
                        self.assertGreater(result["economy_steps"][0]["result"]["damage"], 0)

        evicted_id = accepted_entries[0]["event_id"]
        surviving = accepted_entries[1:]
        self.assertEqual(len(surviving), MAX_COMBAT_HISTORY_ENTRIES)
        self.assertEqual(record.combat_history, surviving)
        self.assertNotIn(evicted_id, {entry["event_id"] for entry in surviving})
        self.assertEqual(self.store.get_campaign(a["campaign_id"]).combat_history, surviving)
        self.assertEqual(self.store.get_turn_action(a["campaign_id"], command["action_id"]),
                         original_receipt)
        committed = self.snapshot(record)

        def receipt_row(store):
            with closing(store._connect()) as db:
                return dict(db.execute(
                    """SELECT * FROM campaign_turn_actions
                       WHERE campaign_id = ? AND action_id = ?""",
                    (a["campaign_id"], command["action_id"]),
                ).fetchone())

        damaged_column = "request_hash"
        damaged_value = malformed_hash
        expected_error = (409, "campaign_unavailable")
        if response_corruption is not None:
            self.assertIsNone(malformed_hash)
            damaged_column = "response_json"
            damaged_response = copy.deepcopy(expected_response)
            if response_corruption == "json":
                damaged_value = '{"action_id":'
                expected_error = (503, "campaign_storage_unavailable")
            elif response_corruption == "action_id":
                damaged_response["action_id"] = str(uuid4())
                damaged_value = json.dumps(damaged_response)
            else:
                field, mode, invalid_value = response_corruption
                if mode == "missing":
                    del damaged_response[field]
                else:
                    damaged_response[field] = invalid_value
                self.assertEqual(damaged_response["action_id"], command["action_id"])
                damaged_value = json.dumps(damaged_response)
        receipt_update = f"""UPDATE campaign_turn_actions SET {damaged_column} = ?
                            WHERE campaign_id = ? AND action_id = ?"""
        if damaged_value is not None:
            original_row = receipt_row(self.store)
            with self.store._transaction() as db:
                updated = db.execute(
                    receipt_update, (damaged_value, a["campaign_id"], command["action_id"]),
                )
                self.assertEqual(updated.rowcount, 1)
            self.assertEqual(
                receipt_row(self.store), {**original_row, damaged_column: damaged_value},
            )
            if response_corruption is not None:
                self.assertEqual(receipt_row(self.store)["request_hash"],
                                 original_receipt["request_hash"])
            self.assertEqual(self.snapshot(record), committed)

        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
        self.assertNotEqual(sid, a["session_id"])
        self.assertIsNot(restored.game_session, session)
        self.assertEqual(self.snapshot(restored)[:7], committed[:7])
        self.assertEqual(restored.combat_history, surviving)
        if damaged_value is not None:
            await self.assert_damaged_evicted_receipt_retries(
                fresh_store, fresh, sid, restored, command, expected_response,
                original_receipt, original_row, damaged_column, damaged_value,
                receipt_update, expected_error, evicted_id, surviving,
            )
            return
        self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), original_receipt)

        def history_rows():
            with closing(fresh_store._connect()) as db:
                return [tuple(row) for row in db.execute(
                    """SELECT * FROM campaign_combat_history
                       WHERE campaign_id = ? ORDER BY sequence""",
                    (a["campaign_id"],),
                )]

        # Resume may update metadata; baseline all owners after reopening.
        before = self.snapshot(restored)
        before_auxiliary = copy.deepcopy((
            restored.game_session.messages,
            restored.game_session.world_metadata,
        ))
        before_rows = history_rows()
        endpoint = "turn"
        retry_command = copy.deepcopy(command)
        if rest_action is not None:
            endpoint = "species-actions"
            retry_command = {"action": rest_action, "action_id": command["action_id"]}
            self.assertEqual(retry_command["action_id"], command["action_id"])
            self.assertNotEqual(retry_command, command)
        elif changed_payload:
            retry_command["combat_action"]["steps"][0]["ability"] = "Fire Bolt"
            self.assertEqual(retry_command["action_id"], command["action_id"])
            self.assertNotEqual(retry_command["combat_action"], command["combat_action"])
        app = create_app(session_manager=fresh, ollama_adapter=None)
        with patch.object(restored.game_session, "run_player_turn",
                          side_effect=AssertionError("Evicted action executed again")) as engine, \
             patch("game.run_player_turn",
                   side_effect=AssertionError("Evicted action reached engine")) as core_engine, \
             patch.object(restored.game_session, "resolve_species_trait_action",
                          side_effect=AssertionError("Evicted action executed rest")) as rest, \
             patch("game.resolve_species_trait_action",
                   side_effect=AssertionError("Evicted action reached rest engine")) as core_rest, \
             patch.object(fresh, "autosave_turn",
                          side_effect=AssertionError("Evicted action autosaved")) as autosave:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://reload") as client:
                replay = await client.post(
                    f"/api/game/sessions/{sid}/{endpoint}", json=retry_command,
                )
        engine.assert_not_called()
        core_engine.assert_not_called()
        rest.assert_not_called()
        core_rest.assert_not_called()
        autosave.assert_not_called()
        if changed_payload:
            self.assertEqual(replay.status_code, 409, replay.text)
            self.assertEqual(replay.json()["detail"]["code"], "action_id_conflict")
        else:
            expected_response["session_id"] = sid
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), expected_response)
        # Includes complete RNG, canonical gameplay, journals, history and store.
        self.assertEqual(self.snapshot(restored), before)
        self.assertEqual((
            restored.game_session.messages,
            restored.game_session.world_metadata,
        ), before_auxiliary)
        self.assertEqual(history_rows(), before_rows)
        self.assertEqual(restored.combat_history, surviving)
        self.assertEqual(fresh_store.get_campaign(a["campaign_id"]).combat_history, surviving)
        self.assertNotIn(evicted_id, {entry["event_id"] for entry in restored.combat_history})
        self.assertEqual(fresh_store.get_turn_action(a["campaign_id"], command["action_id"]),
                         original_receipt)

    async def assert_damaged_evicted_receipt_retries(
        self, store, manager, sid, record, command, accepted_response,
        receipt, original_row, damaged_column, damaged_value, receipt_update,
        expected_error, evicted_id, surviving,
    ):
        session = record.game_session
        before = self.snapshot(record)
        before_auxiliary = copy.deepcopy((session.messages, session.world_metadata))

        def database_snapshot():
            with closing(store._connect()) as db:
                return tuple(db.iterdump())

        # Resume may mark the campaign played; retries must preserve this baseline,
        # including all SQL history rows and the damaged receipt's raw contents.
        damaged_database = database_snapshot()
        with closing(store._connect()) as db:
            damaged_row = dict(db.execute(
                """SELECT * FROM campaign_turn_actions
                   WHERE campaign_id = ? AND action_id = ?""",
                (record.campaign_id, command["action_id"]),
            ).fetchone())
        self.assertEqual(damaged_row, {**original_row, damaged_column: damaged_value})
        changed_command = copy.deepcopy(command)
        changed_command["combat_action"]["steps"][0]["ability"] = "Fire Bolt"
        conflicts = [
            ("turn", changed_command),
            *[("species-actions", {"action": action, "action_id": command["action_id"]})
              for action in ("short_rest", "long_rest")],
            (f"ambient-events/{uuid4()}/actions",
             {"action": "observe", "action_id": command["action_id"]}),
        ]
        app = create_app(session_manager=manager, ollama_adapter=None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://reload",
        ) as client:
            async def guarded_retry(endpoint, body, expected_database):
                guards = (
                    (session, "run_player_turn"), (game, "run_player_turn"),
                    (session, "resolve_species_trait_action"),
                    (game, "resolve_species_trait_action"),
                    (session, "resolve_ambient_event_action"),
                    (session.rng, "randint"), (session.rng, "random"),
                    (session.rng, "getrandbits"),
                    (manager, "autosave_turn"), (manager, "save_campaign_locked"),
                    (store, "save_campaign"), (store, "_transaction"),
                )
                with ExitStack() as stack:
                    spies = [
                        stack.enter_context(patch.object(
                            target, method,
                            side_effect=AssertionError(f"Evicted receipt retry invoked {method}"),
                        ))
                        for target, method in guards
                    ]
                    response = await client.post(
                        f"/api/game/sessions/{sid}/{endpoint}", json=body,
                    )
                for spy in spies:
                    spy.assert_not_called()
                self.assertEqual(self.snapshot(record), before)
                self.assertEqual((session.messages, session.world_metadata), before_auxiliary)
                self.assertEqual(database_snapshot(), expected_database)
                self.assertEqual(record.combat_history, surviving)
                self.assertEqual(store.get_campaign(record.campaign_id).combat_history, surviving)
                self.assertNotIn(evicted_id, {entry["event_id"] for entry in record.combat_history})
                return response

            # Malformed hashes fail for every command family. Response contract
            # damage is checked by the original native turn owner, with its hash intact.
            damaged_retries = [("turn", command)]
            if damaged_column == "request_hash":
                damaged_retries += conflicts
            for endpoint, body in damaged_retries:
                with self.subTest(damaged_receipt_endpoint=endpoint, body=body):
                    rejected = await guarded_retry(endpoint, body, damaged_database)
                    self.assertEqual(rejected.status_code, expected_error[0], rejected.text)
                    self.assertEqual(rejected.json()["detail"]["code"], expected_error[1])
                    self.assertIsInstance(rejected.json()["detail"]["message"], str)
                    self.assertTrue(rejected.json()["detail"]["message"])

            # Repair only the damaged column, retaining the hash (for response
            # damage), timestamp, absent history entry and every other SQL row.
            with store._transaction() as db:
                updated = db.execute(
                    receipt_update,
                    (original_row[damaged_column], record.campaign_id, command["action_id"]),
                )
                self.assertEqual(updated.rowcount, 1)
                repaired_row = dict(db.execute(
                    """SELECT * FROM campaign_turn_actions
                       WHERE campaign_id = ? AND action_id = ?""",
                    (record.campaign_id, command["action_id"]),
                ).fetchone())
                damaged_literal, original_literal = db.execute(
                    "SELECT quote(?), quote(?)",
                    (damaged_value, original_row[damaged_column]),
                ).fetchone()
            self.assertEqual(repaired_row, original_row)
            self.assertEqual(store.get_turn_action(record.campaign_id, command["action_id"]), receipt)
            self.assertEqual(
                database_snapshot(),
                tuple(line.replace(damaged_literal, original_literal)
                      for line in damaged_database),
            )
            repaired_database = database_snapshot()
            replay = await guarded_retry("turn", command, repaired_database)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), {**accepted_response, "session_id": sid})
            for endpoint, body in conflicts:
                with self.subTest(repaired_hash_conflict=endpoint, body=body):
                    conflict = await guarded_retry(endpoint, body, repaired_database)
                    if endpoint.startswith("ambient-events/"):
                        self.assertEqual(conflict.status_code, 200, conflict.text)
                        self.assertEqual(conflict.json()["result"]["status"], "REJECTED")
                        self.assertEqual(
                            conflict.json()["result"]["reason_code"], "action_id_conflict",
                        )
                    else:
                        self.assertEqual(conflict.status_code, 409, conflict.text)
                        self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")

    async def test_late_receipt_sql_failure_rolls_back_all_writes_then_retry_commits_once(self):
        a = await self.create_campaign()
        record, command = self.prepare_spell(a)
        before = self.snapshot(record)
        with closing(self.store._connect()) as db:
            db.execute("""CREATE TRIGGER reject_receipt BEFORE INSERT ON campaign_turn_actions
                          BEGIN SELECT RAISE(ABORT, 'injected late failure'); END""")
        with patch("game.apply_npc_damage", wraps=game.apply_npc_damage) as damage, patch.object(
            record.game_session.rng, "randint", wraps=record.game_session.rng.randint
        ) as dice:
            failed = await self.post(a, command)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(damage.call_count, 1)
        self.assertEqual(dice.call_count, 3)
        self.assertEqual(self.snapshot(record), before)
        self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
        with closing(self.store._connect()) as db:
            db.execute("DROP TRIGGER reject_receipt")
        successful = await self.post(a, command)
        self.assertEqual(successful.status_code, 200, successful.text)
        committed = self.snapshot(record)
        replay = await self.post(a, command)
        self.assertEqual(replay.json(), successful.json())
        self.assertEqual(self.snapshot(record), committed)
        self.assertEqual(len(self.store.get_campaign(a["campaign_id"]).history), 1)

    async def test_ambient_event_late_receipt_sql_failure_rolls_back_then_retries_and_replays(self):
        created = await self.create_campaign()
        campaign_id, sid = created["campaign_id"], created["session_id"]
        record = self.manager.get(sid)
        session = record.game_session
        event_id = self.install_test_ambient_event(session)
        self.manager.save_campaign(campaign_id)
        command = {"action": "interact", "action_id": str(uuid4())}

        def saved_rows(store):
            with closing(store._connect()) as db:
                return {
                    table: [tuple(row) for row in db.execute(
                        f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                        (campaign_id,),
                    )]
                    for table in ("campaigns", "campaign_history",
                                  "campaign_combat_history", "campaign_turn_actions")
                }

        def auxiliary_state(current):
            return copy.deepcopy((
                current.game_session.messages, current.game_session.world_metadata,
            ))

        async def send(client=self.http, session_id=sid):
            return await client.post(
                f"/api/game/sessions/{session_id}/ambient-events/{event_id}/actions",
                json=command,
            )

        before = self.snapshot(record)
        before_auxiliary = auxiliary_state(record)
        before_rows = saved_rows(self.store)
        revision = before[-1].metadata["revision"]
        with closing(self.store._connect()) as db:
            # This trigger can reject the receipt only AFTER the real save has
            # updated this campaign in the enclosing transaction.
            db.execute(f"""
                CREATE TRIGGER reject_ambient_receipt
                BEFORE INSERT ON campaign_turn_actions
                WHEN NEW.campaign_id = '{campaign_id}'
                    AND NEW.action_id = '{command["action_id"]}'
                    AND (SELECT revision FROM campaigns
                         WHERE campaign_id = NEW.campaign_id) = {revision + 1}
                BEGIN SELECT RAISE(ABORT, 'injected late ambient failure'); END
            """)

        speculative = {}
        original_save = self.store.save_campaign

        def observe_native_save(*args, **kwargs):
            speculative["snapshot"] = self.snapshot(record)
            speculative["receipt"] = copy.deepcopy(kwargs["turn_action_receipt"])
            return original_save(*args, **kwargs)

        with patch.object(self.store, "save_campaign", side_effect=observe_native_save) as save, \
             patch.object(session, "resolve_ambient_event_action",
                          wraps=session.resolve_ambient_event_action) as resolve:
            failed = await send()
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(failed.json()["detail"]["code"], "event_persistence_error")
        self.assertNotIn("injected late ambient failure", failed.text)
        save.assert_called_once()
        resolve.assert_called_once_with(event_id, command["action_id"], "interact")
        self.assertNotEqual(speculative["snapshot"][0], before[0])
        self.assertNotEqual(speculative["snapshot"][2], before[2])
        self.assertEqual(speculative["receipt"]["action_id"], command["action_id"])
        self.assertEqual(
            speculative["receipt"]["response"]["ambient_event_response"]["result"]["status"],
            "APPLIED",
        )
        self.assertEqual(self.snapshot(record), before)
        self.assertEqual(auxiliary_state(record), before_auxiliary)
        self.assertEqual(saved_rows(self.store), before_rows)
        self.assertNotIn(command["action_id"], record.turn_action_receipts)
        self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
        self.assertIsNone(self.store.get_turn_action(campaign_id, command["action_id"]))

        with closing(self.store._connect()) as db:
            db.execute("DROP TRIGGER reject_ambient_receipt")
        with patch.object(session, "resolve_ambient_event_action",
                          wraps=session.resolve_ambient_event_action) as resolve:
            accepted = await send()
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
        resolve.assert_called_once_with(event_id, command["action_id"], "interact")
        committed = self.snapshot(record)
        committed_rows = saved_rows(self.store)
        receipt = self.store.get_turn_action(campaign_id, command["action_id"])
        self.assertEqual(receipt["response"]["ambient_event_response"], accepted.json())
        self.assertEqual(committed[-1].metadata["revision"], revision + 1)
        self.assertNotEqual(committed[0], before[0])
        self.assertNotEqual(committed[2], before[2])
        # Promotion need not consume dice, but neither failure nor retry may
        # introduce unrelated RNG changes.
        self.assertEqual(committed[1], before[1])
        outcomes = [event for event in record.journal["notable_events"]
                    if event.get("event_type") == "ambient_event_outcome"
                    and event["event_result"]["action_id"] == command["action_id"]]
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["event_id"],
                         accepted.json()["result"]["canonical_event_id"])
        self.assertEqual(outcomes[0]["event_result"]["transition_id"],
                         accepted.json()["result"]["transition_id"])
        self.assertEqual(len(committed_rows["campaign_turn_actions"]),
                         len(before_rows["campaign_turn_actions"]) + 1)
        for table in ("campaign_history", "campaign_combat_history"):
            self.assertEqual(committed_rows[table], before_rows[table])

        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://reload") as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            new_sid = resumed.json()["session_id"]
            restored = fresh.get(new_sid)
            self.assertIsNot(restored.game_session, session)
            self.assertEqual(self.snapshot(restored)[:7], committed[:7])
            self.assertEqual(fresh_store.get_campaign(campaign_id).payload,
                             committed[-1].payload)
            self.assertEqual(fresh.get_turn_action(restored, command["action_id"]), receipt)
            # Resume may refresh last_played_at; replay must preserve the
            # metadata captured AFTER reopening, not the old timestamp.
            reopened = self.snapshot(restored)
            reopened_rows = saved_rows(fresh_store)
            reopened_auxiliary = auxiliary_state(restored)
            with patch.object(restored.game_session, "resolve_ambient_event_action",
                              side_effect=AssertionError("Replay reran event mechanics")), \
                 patch.object(fresh, "save_campaign_locked",
                              side_effect=AssertionError("Replay saved the campaign")):
                replay = await send(client, new_sid)
            self.assertEqual(replay.status_code, 200, replay.text)
            expected = copy.deepcopy(accepted.json())
            expected["session_id"] = new_sid
            expected["result"].update(
                status="ALREADY_APPLIED", reason_code="event_already_resolved",
            )
            self.assertEqual(replay.json(), expected)
            self.assertEqual(self.snapshot(restored), reopened)
            self.assertEqual(auxiliary_state(restored), reopened_auxiliary)
            self.assertEqual(saved_rows(fresh_store), reopened_rows)
            self.assertEqual(fresh_store.get_turn_action(campaign_id, command["action_id"]),
                             receipt)

    async def test_late_pruning_sql_failure_preserves_full_combat_history_on_resume_then_retry(self):
        a = await self.create_campaign()
        record, command = self.prepare_spell(a)
        session = record.game_session
        session.character.update(current_hp=10000, max_hp=10000)
        enemy_id = command["combat_action"]["steps"][0]["target_id"]
        enemy = next(npc for npc in session.world_state["npcs"]
                     if npc["id"] == enemy_id)
        enemy.update(current_hp=10000, max_hp=10000)
        self.manager.save_campaign(a["campaign_id"])

        # Fill the real retention window via accepted API turns, not fabricated
        # history rows. End-turn actions leave a spell slot for the failed turn.
        accepted_entries = []
        for index in range(MAX_COMBAT_HISTORY_ENTRIES):
            with self.subTest(turn=index):
                response = await self.post(a, {
                    "message": "End my turn.", "action_id": str(uuid4()),
                    "combat_action": {"steps": [{"kind": "end_turn"}]},
                })
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(session.world_state["combat"]["active"])
                accepted_entries.append(copy.deepcopy(record.combat_history[-1]))
                self.assertEqual(record.combat_history, accepted_entries)
                response_entry = response.json()["combat_history_entry"]
                entry = accepted_entries[-1]
                self.assertEqual(response_entry["event_id"], entry["event_id"])
                self.assertEqual(entry["result"],
                                 {key: response_entry["result"][key]
                                  for key in entry["result"]})
        self.assertEqual(len(record.combat_history), MAX_COMBAT_HISTORY_ENTRIES)
        before = self.snapshot(record)
        oldest = copy.deepcopy(accepted_entries[0])

        def stored_rows():
            with closing(self.store._connect()) as db:
                return [tuple(row) for row in db.execute(
                    """SELECT * FROM campaign_combat_history
                       WHERE campaign_id = ? ORDER BY sequence""",
                    (a["campaign_id"],),
                )]

        before_rows = stored_rows()
        # Unlike the receipt INSERT failure above, this fires AFTER an oldest
        # row is deleted, with the new result and receipt already written.
        # RAISE(ABORT) must roll back the enclosing save, not just that DELETE.
        with closing(self.store._connect()) as db:
            db.execute(f"""
                CREATE TRIGGER reject_combat_pruning
                AFTER DELETE ON campaign_combat_history
                WHEN (SELECT COUNT(*) FROM campaign_combat_history
                      WHERE campaign_id = OLD.campaign_id) = {MAX_COMBAT_HISTORY_ENTRIES}
                 AND EXISTS (SELECT 1 FROM campaign_turn_actions
                             WHERE campaign_id = OLD.campaign_id
                               AND action_id = '{command["action_id"]}')
                BEGIN SELECT RAISE(ABORT, 'injected failure after pruning'); END
            """)
        with patch("game.apply_npc_damage", wraps=game.apply_npc_damage) as damage, \
             patch.object(session.rng, "randint", wraps=session.rng.randint) as dice:
            failed = await self.post(a, command)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(damage.call_count, 1)
        self.assertEqual(dice.call_count, 3)
        self.assertEqual(self.snapshot(record), before)
        self.assertEqual(record.combat_history, accepted_entries)
        self.assertEqual(record.combat_history[0], oldest)
        self.assertEqual(session.rng.getstate(), before[1])
        self.assertEqual(stored_rows(), before_rows)
        stored = self.store.get_campaign(a["campaign_id"])
        self.assertEqual(stored.combat_history, accepted_entries)
        self.assertEqual(stored.history, before[7].history)
        self.assertEqual(stored.payload, before[7].payload)
        self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
        self.assertIsNone(self.store.get_turn_action(a["campaign_id"], command["action_id"]))
        with closing(self.store._connect()) as db:
            db.execute("DROP TRIGGER reject_combat_pruning")

        fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
        sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
        self.assertIsNot(restored.game_session, session)
        # Resume may update last-played metadata, but not history or RNG.
        self.assertEqual(self.snapshot(restored)[:7], before[:7])
        self.assertEqual(restored.combat_history[0], oldest)
        self.assertEqual(restored.game_session.rng.getstate(), before[1])
        self.assertEqual(stored_rows(), before_rows)
        reopened = self.store.get_campaign(a["campaign_id"])
        self.assertEqual(reopened.combat_history, accepted_entries)
        self.assertEqual(reopened.history, stored.history)
        self.assertEqual(reopened.payload, stored.payload)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://testserver") as client:
            successful = await client.post(f"/api/game/sessions/{sid}/turn", json=command)
            self.assertEqual(successful.status_code, 200, successful.text)
            new_entry = copy.deepcopy(restored.combat_history[-1])
            self.assertEqual(new_entry["event_id"],
                             successful.json()["combat_history_entry"]["event_id"])
            expected = accepted_entries[1:] + [new_entry]
            self.assertEqual(restored.combat_history, expected)
            committed = self.store.get_campaign(a["campaign_id"])
            self.assertEqual(committed.combat_history, expected)
            self.assertEqual(len(committed.combat_history), MAX_COMBAT_HISTORY_ENTRIES)
            self.assertNotIn(oldest["event_id"],
                             {entry["event_id"] for entry in committed.combat_history})
            self.assertEqual(stored_rows()[:-1], before_rows[1:])
            self.assertEqual(len(committed.history), len(stored.history) + 1)
            self.assertNotEqual(restored.game_session.rng.getstate(), before[1])
            self.assertEqual(fresh.get_turn_action(restored, command["action_id"])["response"],
                             successful.json())
            after_retry = self.snapshot(restored)
            replay = await client.post(f"/api/game/sessions/{sid}/turn", json=command)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), successful.json())
            self.assertEqual(self.snapshot(restored), after_retry)

    async def test_concurrent_ambient_and_rest_share_only_one_committed_action(self):
        for rest_action in ("short_rest", "long_rest"):
            for winner in ("ambient", "rest"):
                with self.subTest(rest_action=rest_action, winner=winner):
                    created = await self.create_campaign()
                    campaign_id, sid = created["campaign_id"], created["session_id"]
                    record = self.manager.get(sid)
                    session = record.game_session
                    session.commit_location_change("tavern")
                    session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
                    session.initialize_species_trait_state()
                    session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
                    event_id = self.install_test_ambient_event(session)
                    self.manager.save_campaign(campaign_id)
                    before = self.snapshot(record)
                    before_character = copy.deepcopy(session.character)
                    action_id = str(uuid4())
                    commands = {
                        "ambient": (f"ambient-events/{event_id}/actions",
                                    {"action": "interact", "action_id": action_id}),
                        "rest": ("species-actions",
                                 {"action": rest_action, "action_id": action_id}),
                    }
                    loser = "rest" if winner == "ambient" else "ambient"

                    def saved_rows(store):
                        with closing(store._connect()) as connection:
                            return {
                                table: [tuple(row) for row in connection.execute(
                                    f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                                    (campaign_id,),
                                )]
                                for table in ("campaigns", "campaign_turn_actions",
                                              "campaign_history", "campaign_combat_history")
                            }

                    # Start the selected winner first, but block its initial
                    # lookup until BOTH sync handlers arrive. Order only their
                    # real lock acquisition, never mechanics or persistence.
                    barrier = threading.Barrier(2)
                    first_arrived = threading.Event()
                    winner_finished = threading.Event()
                    local = threading.local()
                    original_get, original_lock = self.manager.get, record.turn_lock
                    winning_commit = {}
                    test = self

                    def rendezvous(session_id):
                        found = original_get(session_id)
                        if not hasattr(local, "winner"):
                            local.winner = not first_arrived.is_set()
                            first_arrived.set()
                            barrier.wait(timeout=10)
                        return found

                    class OrderedLock:
                        def __enter__(self):
                            if not local.winner and not winner_finished.wait(timeout=10):
                                raise AssertionError("Winning handler did not finish")
                            original_lock.acquire()

                        def __exit__(self, exc_type, exc_value, traceback):
                            try:
                                if local.winner:
                                    winning_commit["snapshot"] = test.snapshot(record)
                                    winning_commit["auxiliary"] = copy.deepcopy((
                                        session.messages, session.world_metadata,
                                    ))
                                    winning_commit["rows"] = saved_rows(test.store)
                            finally:
                                original_lock.release()
                                if local.winner:
                                    winner_finished.set()

                    async def send(kind, client=self.http, session_id=sid):
                        endpoint, command = commands[kind]
                        return await client.post(
                            f"/api/game/sessions/{session_id}/{endpoint}", json=command,
                        )

                    with patch.object(self.manager, "get", side_effect=rendezvous), \
                         patch.object(record, "turn_lock", OrderedLock()):
                        first = asyncio.create_task(send(winner))
                        try:
                            self.assertTrue(await asyncio.to_thread(first_arrived.wait, 10))
                            accepted, rejected = await asyncio.wait_for(
                                asyncio.gather(first, send(loser)), timeout=20,
                            )
                        finally:
                            if not first.done():
                                first.cancel()
                                await asyncio.gather(first, return_exceptions=True)

                    def assert_conflict(response):
                        if loser == "rest":
                            self.assertEqual(response.status_code, 409, response.text)
                            self.assertEqual(response.json()["detail"]["code"], "action_id_conflict")
                        else:
                            self.assertEqual(response.status_code, 200, response.text)
                            result = response.json()["result"]
                            self.assertEqual(result["status"], "REJECTED")
                            self.assertEqual(result["reason_code"], "action_id_conflict")
                            self.assertEqual(result["action_id"], action_id)
                            self.assertEqual(result["event_instance_id"], event_id)
                            self.assertIsNone(result["transition_id"])
                            self.assertIsNone(result["canonical_event_id"])

                    self.assertEqual(accepted.status_code, 200, accepted.text)
                    assert_conflict(rejected)
                    committed = self.snapshot(record)
                    self.assertEqual(committed, winning_commit["snapshot"])
                    self.assertEqual((session.messages, session.world_metadata),
                                     winning_commit["auxiliary"])
                    self.assertEqual(saved_rows(self.store), winning_commit["rows"])
                    receipt = self.store.get_turn_action(campaign_id, action_id)
                    self.assertEqual(len(winning_commit["rows"]["campaign_turn_actions"]), 1)
                    self.assertEqual(receipt["response"]["action_id"], action_id)
                    self.assertEqual(self.manager.get_turn_action(record, action_id), receipt)
                    elapsed = session.world_state["campaign_time"]["elapsed_seconds"]
                    before_elapsed = before[0]["world_state"]["campaign_time"]["elapsed_seconds"]
                    outcomes = [entry for entry in record.journal["notable_events"]
                                if entry.get("event_type") == "ambient_event_outcome"]
                    if winner == "ambient":
                        result = accepted.json()["result"]
                        self.assertEqual(result["status"], "APPLIED")
                        self.assertTrue(result["transition_id"])
                        self.assertTrue(result["canonical_event_id"])
                        self.assertEqual(receipt["response"]["ambient_event_response"], accepted.json())
                        self.assertEqual(committed[-1].history, before[-1].history)
                        self.assertEqual(len(outcomes), 1)
                        self.assertEqual(outcomes[0]["event_id"], result["canonical_event_id"])
                        self.assertEqual(outcomes[0]["event_result"]["action_id"], action_id)
                        self.assertEqual(session.character, before_character)
                        self.assertEqual(elapsed, before_elapsed)
                    else:
                        self.assertEqual(accepted.json()["result"]["action"], rest_action)
                        self.assertEqual(receipt["response"], accepted.json())
                        self.assertEqual(len(committed[-1].history), len(before[-1].history) + 1)
                        self.assertEqual(committed[-1].history[-1]["player_message"], rest_action)
                        self.assertEqual(record.journal, before[2])
                        self.assertEqual(outcomes, [])
                        self.assertEqual(elapsed - before_elapsed,
                                         3600 if rest_action == "short_rest" else 28800)
                        self.assertEqual(
                            session.character["species_trait_state"]["adrenaline_rush_uses_remaining"],
                            session.character["proficiency_bonus"],
                        )
                        self.assertEqual(session.character["current_hp"],
                                         20 if rest_action == "long_rest" else 1)
                    self.assertEqual(record.combat_history, before[5])
                    self.assertEqual(session.rng.getstate(), before[1])
                    self.assertEqual(committed[-1].metadata["revision"],
                                     before[-1].metadata["revision"] + 1)

                    fresh_store = CampaignStore(self.store.path)
                    fresh = SessionManager(campaign_store=fresh_store)
                    app = create_app(session_manager=fresh, ollama_adapter=None)
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                                base_url="http://reload") as client:
                        resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
                        self.assertEqual(resumed.status_code, 200, resumed.text)
                        new_sid = resumed.json()["session_id"]
                        restored = fresh.get(new_sid)
                        self.assertIsNot(restored.game_session, session)
                        self.assertEqual(self.snapshot(restored)[:7], committed[:7])
                        self.assertEqual(fresh_store.get_campaign(campaign_id).payload,
                                         committed[-1].payload)
                        self.assertEqual(resumed.json()["history"], committed[-1].history)
                        self.assertEqual(fresh.get_turn_action(restored, action_id), receipt)
                        reopened = self.snapshot(restored)
                        rows = saved_rows(fresh_store)
                        auxiliary = copy.deepcopy((
                            restored.game_session.messages, restored.game_session.world_metadata,
                        ))
                        assert_conflict(await send(loser, client, new_sid))
                        replay = await send(winner, client, new_sid)
                        self.assertEqual(replay.status_code, 200, replay.text)
                        if winner == "ambient":
                            self.assertEqual(replay.json()["result"]["status"], "ALREADY_APPLIED")
                            for key in ("action_id", "transition_id", "canonical_event_id"):
                                self.assertEqual(replay.json()["result"][key],
                                                 accepted.json()["result"][key])
                        else:
                            expected = copy.deepcopy(accepted.json())
                            expected["session_id"] = new_sid
                            self.assertEqual(replay.json(), expected)
                        self.assertEqual(self.snapshot(restored), reopened)
                        self.assertEqual((restored.game_session.messages,
                                          restored.game_session.world_metadata), auxiliary)
                        self.assertEqual(saved_rows(fresh_store), rows)
                        self.assertEqual(fresh_store.get_turn_action(campaign_id, action_id), receipt)

    async def test_independent_ambient_and_rest_saves_preserve_first_commit(self):
        await self.assert_independent_ambient_and_rest_race(distinct_ids=False)

    async def test_independent_distinct_action_ids_reject_stale_save_then_retry_once(self):
        await self.assert_independent_ambient_and_rest_race(distinct_ids=True)

    async def assert_independent_ambient_and_rest_race(self, *, distinct_ids):
        for rest_action in ("short_rest", "long_rest"):
            for winner in ("ambient", "rest"):
                with self.subTest(rest_action=rest_action, winner=winner):
                    created = await self.create_campaign()
                    campaign_id = created["campaign_id"]
                    ambient_record = self.manager.get(created["session_id"])
                    session = ambient_record.game_session
                    session.commit_location_change("tavern")
                    session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
                    session.initialize_species_trait_state()
                    session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
                    event_id = self.install_test_ambient_event(session)
                    self.manager.save_campaign(campaign_id)

                    rest_store = CampaignStore(self.store.path)
                    rest_manager = SessionManager(campaign_store=rest_store)
                    rest_sid, rest_record, *_ = rest_manager.resume_campaign(campaign_id)
                    managers = {"ambient": self.manager, "rest": rest_manager}
                    stores = {"ambient": self.store, "rest": rest_store}
                    records = {"ambient": ambient_record, "rest": rest_record}
                    session_ids = {"ambient": created["session_id"], "rest": rest_sid}
                    self.assertIsNot(rest_manager, self.manager)
                    self.assertIsNot(rest_store, self.store)
                    self.assertIsNot(rest_record.turn_lock, ambient_record.turn_lock)
                    self.assertIsNot(rest_record.game_session, session)
                    self.assertEqual(
                        rest_record.game_session._campaign_persistence_version,
                        session._campaign_persistence_version,
                    )
                    before = {kind: self.snapshot(record)[:7] for kind, record in records.items()}
                    self.assertEqual(before["ambient"], before["rest"])
                    auxiliary_before = {
                        kind: copy.deepcopy((record.game_session.messages,
                                             record.game_session.world_metadata))
                        for kind, record in records.items()
                    }
                    saved_before = copy.deepcopy(self.store.get_campaign(campaign_id))
                    shared_id = str(uuid4())
                    action_ids = {
                        "ambient": shared_id,
                        "rest": str(uuid4()) if distinct_ids else shared_id,
                    }
                    if distinct_ids:
                        self.assertNotEqual(action_ids["ambient"], action_ids["rest"])
                    for kind in records:
                        self.assertIsNone(managers[kind].get_turn_action(records[kind], action_ids[kind]))
                    commands = {
                        "ambient": (f"ambient-events/{event_id}/actions",
                                    {"action": "interact", "action_id": action_ids["ambient"]}),
                        "rest": ("species-actions", {"action": rest_action, "action_id": action_ids["rest"]}),
                    }
                    loser = "rest" if winner == "ambient" else "ambient"
                    action_id = action_ids[winner]

                    def saved_rows():
                        with closing(self.store._connect()) as connection:
                            return {
                                table: [tuple(row) for row in connection.execute(
                                    f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                                    (campaign_id,),
                                )]
                                for table in ("campaigns", "campaign_turn_actions",
                                              "campaign_history", "campaign_combat_history")
                            }

                    # Gate only the store boundary. Separate handler locks let
                    # BOTH real engines resolve from the same saved revision.
                    # The loser must enter the real transaction after the winner,
                    # rather than reject at an initial receipt/currentness check.
                    barrier = threading.Barrier(2)
                    winner_finished = threading.Event()
                    speculative, committed = {}, {}
                    save_errors, save_calls = {}, {"ambient": 0, "rest": 0}
                    original_saves = {kind: store.save_campaign for kind, store in stores.items()}

                    def ordered_save(kind):
                        def save(*args, **kwargs):
                            save_calls[kind] += 1
                            speculative[kind] = self.snapshot(records[kind])[:7]
                            self.assertEqual(kwargs["turn_action_receipt"]["action_id"], action_ids[kind])
                            if distinct_ids:
                                # Neither ID has a receipt, even after the other
                                # action commits. Only revision ownership can reject.
                                self.assertIsNone(stores[kind].get_turn_action(campaign_id, action_ids[kind]))
                            self.assertEqual(
                                records[kind].game_session._campaign_persistence_version,
                                (campaign_id, saved_before.metadata["revision"]),
                            )
                            barrier.wait(timeout=10)
                            if kind == loser and not winner_finished.wait(timeout=10):
                                raise AssertionError("Winning store did not commit")
                            if distinct_ids and kind == loser:
                                self.assertIsNone(stores[kind].get_turn_action(campaign_id, action_ids[kind]))
                            try:
                                result = original_saves[kind](*args, **kwargs)
                                if kind == winner:
                                    committed["snapshot"] = self.snapshot(records[kind])
                                    committed["rows"] = saved_rows()
                                    committed["auxiliary"] = copy.deepcopy((
                                        records[kind].game_session.messages,
                                        records[kind].game_session.world_metadata,
                                    ))
                                return result
                            except CampaignError as error:
                                save_errors[kind] = error
                                raise
                            finally:
                                if kind == winner:
                                    winner_finished.set()
                        return save

                    async def send(kind, client, sid=None):
                        endpoint, command = commands[kind]
                        return await client.post(
                            f"/api/game/sessions/{sid or session_ids[kind]}/{endpoint}", json=command,
                        )

                    app = create_app(session_manager=rest_manager, ollama_adapter=None)
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://independent",
                    ) as rest_client:
                        clients = {"ambient": self.http, "rest": rest_client}
                        with patch.object(self.store, "save_campaign", side_effect=ordered_save("ambient")), \
                             patch.object(rest_store, "save_campaign", side_effect=ordered_save("rest")):
                            responses = await asyncio.wait_for(asyncio.gather(
                                send("ambient", clients["ambient"]),
                                send("rest", clients["rest"]),
                            ), timeout=25)
                        responses = dict(zip(("ambient", "rest"), responses))
                        accepted, rejected = responses[winner], responses[loser]
                        self.assertEqual(accepted.status_code, 200, accepted.text)
                        self.assertEqual(save_calls, {"ambient": 1, "rest": 1})
                        self.assertEqual(set(save_errors), {loser})
                        self.assertIsInstance(save_errors[loser], CampaignStaleError)
                        self.assertEqual(rejected.status_code, 409 if loser == "rest" else 500,
                                         rejected.text)
                        self.assertEqual(
                            rejected.json()["detail"]["code"],
                            "campaign_stale" if loser == "rest" else "event_persistence_error",
                        )

                        # Prove both speculative effects existed before the
                        # transaction race; no mechanics are mocked.
                        self.assertNotEqual(speculative["ambient"][0], before["ambient"][0])
                        self.assertNotEqual(speculative["ambient"][2], before["ambient"][2])
                        rest_state = speculative["rest"][0]
                        self.assertEqual(
                            rest_state["world_state"]["campaign_time"]["elapsed_seconds"]
                            - before["rest"][0]["world_state"]["campaign_time"]["elapsed_seconds"],
                            3600 if rest_action == "short_rest" else 28800,
                        )
                        self.assertEqual(
                            rest_state["player"]["species_trait_state"]["adrenaline_rush_uses_remaining"],
                            rest_state["player"]["proficiency_bonus"],
                        )
                        self.assertEqual(rest_state["player"]["current_hp"],
                                         20 if rest_action == "long_rest" else 1)
                        self.assertEqual(self.snapshot(records[loser])[:7], before[loser])
                        self.assertEqual(
                            (records[loser].game_session.messages,
                             records[loser].game_session.world_metadata), auxiliary_before[loser],
                        )
                        self.assertEqual(self.snapshot(records[winner]), committed["snapshot"])
                        self.assertEqual(
                            (records[winner].game_session.messages,
                             records[winner].game_session.world_metadata), committed["auxiliary"],
                        )
                        self.assertEqual(saved_rows(), committed["rows"])
                        self.assertEqual(len(committed["rows"]["campaign_turn_actions"]), 1)
                        stored = self.store.get_campaign(campaign_id)
                        self.assertEqual(stored.metadata["revision"], saved_before.metadata["revision"] + 1)
                        receipt = self.store.get_turn_action(campaign_id, action_id)
                        if distinct_ids:
                            self.assertIsNone(stores[loser].get_turn_action(campaign_id, action_ids[loser]))
                        self.assertEqual(receipt["response"]["action_id"], action_id)
                        self.assertEqual(
                            receipt["response"]["ambient_event_response"] if winner == "ambient"
                            else receipt["response"], accepted.json(),
                        )
                        self.assertEqual(stored.combat_history, saved_before.combat_history)
                        if winner == "ambient":
                            self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
                            self.assertEqual(stored.history, saved_before.history)
                            outcomes = [
                                entry for entry in records[winner].journal["notable_events"]
                                if entry.get("event_type") == "ambient_event_outcome"
                            ]
                            self.assertEqual(len(outcomes), 1)
                            self.assertEqual(outcomes[0]["event_id"],
                                             accepted.json()["result"]["canonical_event_id"])
                        else:
                            self.assertEqual(accepted.json()["result"]["action"], rest_action)
                            self.assertEqual(len(stored.history), len(saved_before.history) + 1)
                            self.assertEqual(stored.history[-1]["player_message"], rest_action)
                            self.assertEqual(records[winner].journal, before[winner][2])

                        # Refresh the actual losing manager (not a third copy).
                        # Resume may touch metadata, so take SQL baselines AFTER it.
                        resumed = await clients[loser].post(
                            f"/api/game/campaigns/{campaign_id}/resume",
                        )
                        self.assertEqual(resumed.status_code, 200, resumed.text)
                        sid = resumed.json()["session_id"]
                        restored = managers[loser].get(sid)
                        self.assertEqual(self.snapshot(restored)[:7], committed["snapshot"][:7])
                        self.assertEqual(stores[loser].get_campaign(campaign_id).payload, stored.payload)
                        self.assertEqual(resumed.json()["history"], stored.history)
                        self.assertEqual(managers[loser].get_turn_action(restored, action_id), receipt)
                        reopened, rows = self.snapshot(restored), saved_rows()
                        auxiliary = copy.deepcopy((restored.game_session.messages,
                                                   restored.game_session.world_metadata))
                        if distinct_ids:
                            self.assertIsNone(managers[loser].get_turn_action(restored, action_ids[loser]))
                            resolver = (
                                "resolve_species_trait_action" if loser == "rest"
                                else "resolve_ambient_event_action"
                            )
                            with patch.object(
                                restored.game_session, resolver,
                                wraps=getattr(restored.game_session, resolver),
                            ) as mechanics, patch.object(
                                stores[loser], "save_campaign", wraps=stores[loser].save_campaign,
                            ) as saves:
                                retried = await send(loser, clients[loser], sid)
                                self.assertEqual(retried.status_code, 200, retried.text)
                                self.assertEqual(mechanics.call_count, 1)
                                self.assertEqual(saves.call_count, 1)
                                if loser == "ambient":
                                    self.assertEqual(retried.json()["result"]["status"], "APPLIED")
                                else:
                                    self.assertEqual(retried.json()["result"]["action"], rest_action)
                                after_retry = self.snapshot(restored)
                                retry_rows = saved_rows()
                                retry_auxiliary = copy.deepcopy((
                                    restored.game_session.messages,
                                    restored.game_session.world_metadata,
                                ))
                                self.assertNotEqual(after_retry[:7], reopened[:7])
                                self.assertEqual(len(retry_rows["campaign_turn_actions"]), 2)
                                self.assertEqual(
                                    after_retry[-1].metadata["revision"],
                                    reopened[-1].metadata["revision"] + 1,
                                )
                                self.assertEqual(stores[loser].get_turn_action(campaign_id, action_id), receipt)
                                retry_receipt = stores[loser].get_turn_action(campaign_id, action_ids[loser])
                                self.assertEqual(
                                    retry_receipt["response"]["ambient_event_response"] if loser == "ambient"
                                    else retry_receipt["response"], retried.json(),
                                )
                                # Both actions' effects survive the fresh commit.
                                self.assertEqual(len(after_retry[-1].history), len(saved_before.history) + 1)
                                self.assertEqual(
                                    after_retry[-1].history[:len(stored.history)], stored.history,
                                )
                                self.assertEqual(after_retry[-1].history[-1]["player_message"], rest_action)
                                self.assertEqual(after_retry[-1].combat_history, saved_before.combat_history)
                                outcomes = [
                                    entry for entry in restored.journal["notable_events"]
                                    if entry.get("event_type") == "ambient_event_outcome"
                                ]
                                self.assertEqual(len(outcomes), 1)
                                ambient_response = accepted if winner == "ambient" else retried
                                self.assertEqual(outcomes[0]["event_id"],
                                                 ambient_response.json()["result"]["canonical_event_id"])
                                final_state = after_retry[0]
                                self.assertEqual(
                                    final_state["world_state"]["campaign_time"]["elapsed_seconds"]
                                    - before[loser][0]["world_state"]["campaign_time"]["elapsed_seconds"],
                                    3600 if rest_action == "short_rest" else 28800,
                                )
                                self.assertEqual(
                                    final_state["player"]["species_trait_state"]["adrenaline_rush_uses_remaining"],
                                    final_state["player"]["proficiency_bonus"],
                                )
                                self.assertEqual(final_state["player"]["current_hp"],
                                                 20 if rest_action == "long_rest" else 1)
                                replay = await send(loser, clients[loser], sid)
                                self.assertEqual(replay.status_code, 200, replay.text)
                                if loser == "ambient":
                                    expected = copy.deepcopy(retried.json())
                                    expected["result"].update(
                                        status="ALREADY_APPLIED", reason_code="event_already_resolved",
                                    )
                                    self.assertEqual(replay.json(), expected)
                                else:
                                    self.assertEqual(replay.json(), retried.json())
                                self.assertEqual(mechanics.call_count, 1)
                                self.assertEqual(saves.call_count, 1)
                            self.assertEqual(self.snapshot(restored), after_retry)
                            self.assertEqual(saved_rows(), retry_rows)
                            self.assertEqual(
                                (restored.game_session.messages, restored.game_session.world_metadata),
                                retry_auxiliary,
                            )
                            self.assertEqual(stores[loser].get_turn_action(campaign_id, action_id), receipt)
                            self.assertEqual(stores[loser].get_turn_action(campaign_id, action_ids[loser]),
                                             retry_receipt)
                            continue
                        conflict = await send(loser, clients[loser], sid)
                        if loser == "rest":
                            self.assertEqual(conflict.status_code, 409, conflict.text)
                            self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
                        else:
                            self.assertEqual(conflict.status_code, 200, conflict.text)
                            result = conflict.json()["result"]
                            self.assertEqual(result["status"], "REJECTED")
                            self.assertEqual(result["reason_code"], "action_id_conflict")
                            self.assertEqual(result["action_id"], action_id)
                            self.assertEqual(result["event_instance_id"], event_id)
                            self.assertIsNone(result["transition_id"])
                            self.assertIsNone(result["canonical_event_id"])
                        self.assertEqual(self.snapshot(restored), reopened)
                        self.assertEqual((restored.game_session.messages,
                                          restored.game_session.world_metadata), auxiliary)
                        self.assertEqual(saved_rows(), rows)
                        self.assertEqual(stores[loser].get_turn_action(campaign_id, action_id), receipt)

    async def assert_independent_duplicate_command(self, operation, winner):
        def runtime_snapshot(record):
            return copy.deepcopy((
                record.game_session.serialize_game_state(),
                record.game_session.rng.getstate(), record.journal,
                record.narrative_memory, record.lore_authority.to_dict(),
                record.combat_history, record.turn_action_receipts,
            ))

        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        first = self.manager.get(created["session_id"])
        session = first.game_session
        session.commit_location_change("tavern")
        session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
        session.initialize_species_trait_state()
        session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
        action_id = str(uuid4())
        if operation == "ambient":
            event_id = self.install_test_ambient_event(session)
            endpoint = f"ambient-events/{event_id}/actions"
            command = {"action": "interact", "action_id": action_id}
            mechanic = "resolve_ambient_event_action"
        else:
            endpoint = "species-actions"
            command = {"action": operation, "action_id": action_id}
            mechanic = "resolve_species_trait_action"
        self.manager.save_campaign(campaign_id)
        second_store = CampaignStore(self.store.path)
        second_manager = SessionManager(campaign_store=second_store)
        second_sid, second, *_ = second_manager.resume_campaign(campaign_id)
        records = (first, second)
        stores = (self.store, second_store)
        managers = (self.manager, second_manager)
        session_ids = (created["session_id"], second_sid)
        loser = 1 - winner
        self.assertIsNot(first.turn_lock, second.turn_lock)
        self.assertIsNot(first.game_session, second.game_session)
        self.assertIsNot(managers[0], managers[1])
        self.assertIsNot(stores[0], stores[1])
        self.assertNotEqual(session_ids[0], session_ids[1])
        before = [runtime_snapshot(record) for record in records]
        self.assertEqual(before[0], before[1])
        auxiliary_before = [
            copy.deepcopy((record.game_session.messages, record.game_session.world_metadata))
            for record in records
        ]
        saved_before = self.store.get_campaign(campaign_id)
        token = (campaign_id, saved_before.metadata["revision"])
        for record in records:
            self.assertEqual(record.game_session._campaign_persistence_version, token)

        def saved_rows():
            with closing(self.store._connect()) as connection:
                return {
                    table: [tuple(row) for row in connection.execute(
                        f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                        (campaign_id,),
                    )]
                    for table in ("campaigns", "campaign_turn_actions",
                                  "campaign_history", "campaign_combat_history")
                }

        # Rendezvous AFTER both real engines resolve, immediately before the
        # store transaction. No manager lock or gameplay method is replaced.
        barrier = threading.Barrier(2)
        committed_event = threading.Event()
        original_saves = [store.save_campaign for store in stores]
        speculative, errors, committed = {}, {}, {}
        save_calls = [0, 0]

        def ordered_save(index):
            def save(*args, **kwargs):
                try:
                    save_calls[index] += 1
                    speculative[index] = runtime_snapshot(records[index])
                    self.assertEqual(kwargs["turn_action_receipt"]["action_id"], action_id)
                    self.assertEqual(records[index].game_session._campaign_persistence_version, token)
                    barrier.wait(timeout=10)
                    if index == loser and not committed_event.wait(timeout=10):
                        raise AssertionError("Duplicate winner did not commit")
                    result = original_saves[index](*args, **kwargs)
                    if index == winner:
                        committed["runtime"] = runtime_snapshot(records[index])
                    return result
                except CampaignError as error:
                    errors[index] = error
                    raise
                except Exception:
                    barrier.abort()
                    raise
                finally:
                    if index == winner:
                        committed_event.set()
            return save

        async def send(client, sid):
            return await client.post(
                f"/api/game/sessions/{sid}/{endpoint}", json=copy.deepcopy(command),
            )

        app = create_app(session_manager=second_manager, ollama_adapter=None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://duplicate",
        ) as second_client:
            clients = (self.http, second_client)
            with ExitStack() as stack:
                mechanics = [
                    stack.enter_context(patch.object(
                        record.game_session, mechanic,
                        wraps=getattr(record.game_session, mechanic),
                    )) for record in records
                ]
                for index, store in enumerate(stores):
                    stack.enter_context(patch.object(
                        store, "save_campaign", side_effect=ordered_save(index),
                    ))
                requests = asyncio.gather(
                    *(send(client, sid) for client, sid in zip(clients, session_ids))
                )
                try:
                    responses = await asyncio.wait_for(asyncio.shield(requests), timeout=25)
                finally:
                    # Cancelling an ASGI request does not stop its sync worker.
                    # Release all test-owned waits and drain both handlers while
                    # patches, clients and the temporary database still exist.
                    barrier.abort()
                    committed_event.set()
                    if not requests.done():
                        await asyncio.shield(requests)
                for spy in mechanics:
                    self.assertEqual(spy.call_count, 1)
            accepted, rejected = responses[winner], responses[loser]
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(rejected.status_code, 500 if operation == "ambient" else 409,
                             rejected.text)
            self.assertEqual(rejected.json()["detail"]["code"],
                             "event_persistence_error" if operation == "ambient" else "campaign_stale")
            self.assertEqual(save_calls, [1, 1])
            self.assertEqual(set(errors), {loser})
            self.assertIsInstance(errors[loser], CampaignStaleError)
            for index in (0, 1):
                state = speculative[index][0]
                if operation == "ambient":
                    self.assertEqual(len(state["world_state"]["npcs"]),
                                     len(before[index][0]["world_state"]["npcs"]) + 1)
                    self.assertEqual(len([
                        event for event in speculative[index][2]["notable_events"]
                        if event.get("event_type") == "ambient_event_outcome"
                    ]), 1)
                else:
                    self.assertEqual(
                        state["world_state"]["campaign_time"]["elapsed_seconds"]
                        - before[index][0]["world_state"]["campaign_time"]["elapsed_seconds"],
                        3600 if operation == "short_rest" else 28800,
                    )
                    self.assertEqual(state["player"]["current_hp"],
                                     20 if operation == "long_rest" else 1)
                    self.assertEqual(
                        state["player"]["species_trait_state"]["adrenaline_rush_uses_remaining"],
                        state["player"]["proficiency_bonus"],
                    )
            self.assertEqual(runtime_snapshot(records[loser]), before[loser])
            self.assertEqual(
                (records[loser].game_session.messages, records[loser].game_session.world_metadata),
                auxiliary_before[loser],
            )
            self.assertEqual(records[loser].game_session._campaign_persistence_version, token)
            self.assertEqual(runtime_snapshot(records[winner]), committed["runtime"])
            committed_rows = saved_rows()
            self.assertEqual(len(committed_rows["campaign_turn_actions"]), 1)
            stored = self.store.get_campaign(campaign_id)
            self.assertEqual(stored.metadata["revision"], token[1] + 1)
            self.assertEqual(stored.combat_history, saved_before.combat_history)
            receipt = self.store.get_turn_action(campaign_id, action_id)
            self.assertEqual(
                receipt["response"]["ambient_event_response"] if operation == "ambient"
                else receipt["response"], accepted.json(),
            )
            if operation == "ambient":
                self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
                self.assertEqual(stored.history, saved_before.history)
                outcomes = [
                    entry for entry in records[winner].journal["notable_events"]
                    if entry.get("event_type") == "ambient_event_outcome"
                ]
                self.assertEqual(len(outcomes), 1)
                self.assertEqual(outcomes[0]["event_id"],
                                 accepted.json()["result"]["canonical_event_id"])
                self.assertEqual(outcomes[0]["event_result"]["transition_id"],
                                 accepted.json()["result"]["transition_id"])
            else:
                self.assertEqual(len(stored.history), len(saved_before.history) + 1)
                self.assertEqual(stored.history[-1]["player_message"], operation)

            # Resume the actual loser; compare SQL only after its legitimate
            # metadata touch. The winner's session identity must not leak.
            resumed = await clients[loser].post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            self.assertNotEqual(sid, session_ids[winner])
            restored = managers[loser].get(sid)
            self.assertEqual(runtime_snapshot(restored), committed["runtime"])
            self.assertEqual(stores[loser].get_campaign(campaign_id).payload, stored.payload)
            self.assertEqual(resumed.json()["history"], stored.history)
            self.assertEqual(managers[loser].get_turn_action(restored, action_id), receipt)
            reopened, rows = self.snapshot(restored), saved_rows()
            auxiliary = copy.deepcopy((restored.game_session.messages,
                                       restored.game_session.world_metadata))
            expected = copy.deepcopy(accepted.json())
            expected["session_id"] = sid
            if operation == "ambient":
                expected["result"].update(status="ALREADY_APPLIED",
                                          reason_code="event_already_resolved")
                expected["state"] = resumed.json()["state"]
            with ExitStack() as stack:
                guards = [
                    stack.enter_context(patch.object(
                        target, method, side_effect=AssertionError(f"Replay called {method}"),
                    ))
                    for target, method in (
                        (restored.game_session, "resolve_ambient_event_action"),
                        (restored.game_session, "resolve_species_trait_action"),
                        (restored.game_session, "run_player_turn"),
                        (restored.game_session.rng, "randint"),
                        (restored.game_session.rng, "random"),
                        (restored.game_session.rng, "getrandbits"),
                        (managers[loser], "autosave_turn"),
                        (managers[loser], "save_campaign_locked"),
                        (stores[loser], "save_campaign"),
                    )
                ]
                for _ in range(2):
                    replay = await send(clients[loser], sid)
                    self.assertEqual(replay.status_code, 200, replay.text)
                    self.assertEqual(replay.json(), expected)
                    self.assertEqual(self.snapshot(restored), reopened)
                    self.assertEqual(saved_rows(), rows)
                    self.assertEqual(stores[loser].get_turn_action(campaign_id, action_id), receipt)
                    self.assertEqual((restored.game_session.messages,
                                      restored.game_session.world_metadata), auxiliary)
                for guard in guards:
                    guard.assert_not_called()

    async def test_independent_duplicate_ambient_interact_rolls_back_and_replays(self):
        for winner in (0, 1):
            with self.subTest(winner=winner):
                await self.assert_independent_duplicate_command("ambient", winner)

    async def test_independent_duplicate_rests_roll_back_and_rebind_replay(self):
        for operation in ("short_rest", "long_rest"):
            for winner in (0, 1):
                with self.subTest(operation=operation, winner=winner):
                    await self.assert_independent_duplicate_command(operation, winner)

    async def test_independent_distinct_short_rests_preserve_first_commit(self):
        for winner in (0, 1):
            with self.subTest(winner=winner):
                await self.assert_independent_distinct_rests(("short_rest", "short_rest"), winner)

    async def test_independent_distinct_long_rests_preserve_first_commit(self):
        for winner in (0, 1):
            with self.subTest(winner=winner):
                await self.assert_independent_distinct_rests(("long_rest", "long_rest"), winner)

    async def test_independent_distinct_mixed_rests_preserve_first_commit(self):
        for actions in (("short_rest", "long_rest"), ("long_rest", "short_rest")):
            for winner in (0, 1):
                with self.subTest(actions=actions, winner=winner):
                    await self.assert_independent_distinct_rests(actions, winner)

    async def assert_independent_distinct_rests(self, actions, winner):
        def runtime_snapshot(record):
            # Do not read SQLite while the worker rendezvous is held.
            return copy.deepcopy((
                record.game_session.serialize_game_state(),
                record.game_session.rng.getstate(), record.journal,
                record.narrative_memory, record.lore_authority.to_dict(),
                record.combat_history, record.turn_action_receipts,
                record.game_session.messages, record.game_session.world_metadata,
            ))

        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        seed = self.manager.get(created["session_id"]).game_session
        seed.commit_location_change("tavern")
        seed.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
        seed.initialize_species_trait_state()
        seed.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
        self.manager.save_campaign(campaign_id)
        stores = [CampaignStore(self.store.path) for _ in range(2)]
        managers = [SessionManager(campaign_store=store) for store in stores]
        resumed = [manager.resume_campaign(campaign_id) for manager in managers]
        session_ids = [result[0] for result in resumed]
        records = [result[1] for result in resumed]
        loser = 1 - winner
        action_ids = [str(uuid4()), str(uuid4())]
        commands = [
            {"action": action, "action_id": action_id}
            for action, action_id in zip(actions, action_ids)
        ]
        self.assertNotEqual(action_ids[0], action_ids[1])
        self.assertIsNot(managers[0], managers[1])
        self.assertIsNot(stores[0], stores[1])
        self.assertIsNot(records[0].turn_lock, records[1].turn_lock)
        self.assertIsNot(records[0].game_session, records[1].game_session)
        self.assertNotEqual(session_ids[0], session_ids[1])
        before = [runtime_snapshot(record) for record in records]
        self.assertEqual(before[0], before[1])
        saved_before = self.store.get_campaign(campaign_id)
        token = (campaign_id, saved_before.metadata["revision"])
        for record in records:
            self.assertEqual(record.game_session._campaign_persistence_version, token)

        def saved_rows():
            with closing(self.store._connect()) as connection:
                return {
                    table: [tuple(row) for row in connection.execute(
                        f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                        (campaign_id,),
                    )]
                    for table in ("campaigns", "campaign_turn_actions",
                                  "campaign_history", "campaign_combat_history")
                }

        barrier = threading.Barrier(2)
        committed_event = threading.Event()
        original_saves = [store.save_campaign for store in stores]
        speculative, errors, committed = {}, {}, {}
        save_calls = [0, 0]

        def ordered_save(index):
            def save(*args, **kwargs):
                try:
                    save_calls[index] += 1
                    speculative[index] = runtime_snapshot(records[index])
                    self.assertEqual(kwargs["turn_action_receipt"]["action_id"], action_ids[index])
                    self.assertEqual(records[index].game_session._campaign_persistence_version, token)
                    barrier.wait(timeout=10)
                    if index == loser and not committed_event.wait(timeout=10):
                        raise AssertionError("Winning rest did not commit")
                    # Distinct IDs cannot take the duplicate-receipt path.
                    self.assertIsNone(stores[index].get_turn_action(campaign_id, action_ids[index]))
                    result = original_saves[index](*args, **kwargs)
                    if index == winner:
                        committed["runtime"] = runtime_snapshot(records[index])
                        committed["rows"] = saved_rows()
                    return result
                except CampaignError as error:
                    errors[index] = error
                    raise
                except Exception:
                    barrier.abort()
                    raise
                finally:
                    if index == winner:
                        committed_event.set()
            return save

        async def send(client, index, sid=None):
            return await client.post(
                f"/api/game/sessions/{sid or session_ids[index]}/species-actions",
                json=copy.deepcopy(commands[index]),
            )

        with ExitStack():
            clients = [
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=create_app(
                        session_manager=manager, ollama_adapter=None,
                    )), base_url="http://rest-race",
                ) for manager in managers
            ]
            try:
                with ExitStack() as race:
                    mechanics = [
                        race.enter_context(patch.object(
                            record.game_session, "resolve_species_trait_action",
                            wraps=record.game_session.resolve_species_trait_action,
                        )) for record in records
                    ]
                    for index, store in enumerate(stores):
                        race.enter_context(patch.object(
                            store, "save_campaign", side_effect=ordered_save(index),
                        ))
                    requests = asyncio.gather(*(send(client, i) for i, client in enumerate(clients)))
                    try:
                        responses = await asyncio.wait_for(asyncio.shield(requests), timeout=25)
                    finally:
                        barrier.abort()
                        committed_event.set()
                        if not requests.done():
                            await asyncio.shield(requests)
                    for spy in mechanics:
                        self.assertEqual(spy.call_count, 1)
                accepted, rejected = responses[winner], responses[loser]
                self.assertEqual(accepted.status_code, 200, accepted.text)
                self.assertEqual(rejected.status_code, 409, rejected.text)
                self.assertEqual(rejected.json()["detail"]["code"], "campaign_stale")
                self.assertEqual(save_calls, [1, 1])
                self.assertEqual(set(errors), {loser})
                self.assertIsInstance(errors[loser], CampaignStaleError)
                for index, action in enumerate(actions):
                    state = speculative[index][0]
                    self.assertEqual(
                        state["world_state"]["campaign_time"]["elapsed_seconds"]
                        - before[index][0]["world_state"]["campaign_time"]["elapsed_seconds"],
                        3600 if action == "short_rest" else 28800,
                    )
                    self.assertEqual(state["player"]["current_hp"], 20 if action == "long_rest" else 1)
                    self.assertEqual(
                        state["player"]["species_trait_state"]["adrenaline_rush_uses_remaining"],
                        state["player"]["proficiency_bonus"],
                    )
                self.assertEqual(runtime_snapshot(records[loser]), before[loser])
                self.assertEqual(records[loser].game_session._campaign_persistence_version, token)
                self.assertEqual(runtime_snapshot(records[winner]), committed["runtime"])
                self.assertEqual(saved_rows(), committed["rows"])
                stored = self.store.get_campaign(campaign_id)
                self.assertEqual(stored.metadata["revision"], token[1] + 1)
                self.assertEqual(stored.payload["engine_save"], committed["runtime"][0])
                self.assertEqual(stored.history[:-1], saved_before.history)
                self.assertEqual(stored.history[-1]["player_message"], actions[winner])
                self.assertEqual(stored.combat_history, saved_before.combat_history)
                self.assertEqual(len(committed["rows"]["campaign_turn_actions"]), 1)
                receipt = stores[winner].get_turn_action(campaign_id, action_ids[winner])
                self.assertEqual(receipt["response"], accepted.json())
                self.assertIsNone(stores[loser].get_turn_action(campaign_id, action_ids[loser]))

                # Without explicit resume, the loser is still stale and must
                # not execute mechanics or reach persistence a second time.
                with patch.object(records[loser].game_session, "resolve_species_trait_action",
                                  side_effect=AssertionError("Stale rest executed")), \
                     patch.object(stores[loser], "save_campaign",
                                  side_effect=AssertionError("Stale rest saved")):
                    stale = await send(clients[loser], loser)
                self.assertEqual(stale.status_code, 409, stale.text)
                self.assertEqual(stale.json()["detail"]["code"], "campaign_stale")
                self.assertEqual(runtime_snapshot(records[loser]), before[loser])
                self.assertEqual(saved_rows(), committed["rows"])

                response = await clients[loser].post(f"/api/game/campaigns/{campaign_id}/resume")
                self.assertEqual(response.status_code, 200, response.text)
                sid = response.json()["session_id"]
                restored = managers[loser].get(sid)
                self.assertEqual(runtime_snapshot(restored)[:6], committed["runtime"][:6])
                self.assertEqual(response.json()["history"], stored.history)
                self.assertEqual(stores[loser].get_campaign(campaign_id).payload, stored.payload)
                reopened = runtime_snapshot(restored)
                retry = await send(clients[loser], loser, sid)
                # Current owner allows consecutive short AND long rests: no
                # cooldown is enforced. This is a new rest, not winner replay.
                self.assertEqual(retry.status_code, 200, retry.text)
                self.assertEqual(retry.json()["action_id"], action_ids[loser])
                self.assertEqual(retry.json()["result"]["action"], actions[loser])
                effects = retry.json()["result"]["effects"]
                if actions[loser] == "short_rest":
                    self.assertEqual(effects["adrenaline_rush_uses_refreshed"], 0)
                else:
                    self.assertEqual(effects["refreshed"]["adrenaline_rush"], 0)
                after = runtime_snapshot(restored)
                self.assertEqual(
                    after[0]["world_state"]["campaign_time"]["elapsed_seconds"]
                    - reopened[0]["world_state"]["campaign_time"]["elapsed_seconds"],
                    3600 if actions[loser] == "short_rest" else 28800,
                )
                self.assertEqual(after[0]["player"]["current_hp"],
                                 20 if "long_rest" in actions else 1)
                self.assertEqual(
                    after[0]["player"]["species_trait_state"]["adrenaline_rush_uses_remaining"],
                    after[0]["player"]["proficiency_bonus"],
                )
                retried_store = stores[loser].get_campaign(campaign_id)
                self.assertEqual(retried_store.history[:-1], stored.history)
                self.assertEqual(retried_store.history[-1]["player_message"], actions[loser])
                self.assertEqual(retried_store.metadata["revision"], token[1] + 2)
                self.assertEqual(stores[loser].get_turn_action(campaign_id, action_ids[winner]), receipt)
                loser_receipt = stores[loser].get_turn_action(campaign_id, action_ids[loser])
                self.assertEqual(loser_receipt["response"], retry.json())
                rows = saved_rows()
                self.assertEqual(len(rows["campaign_turn_actions"]), 2)
                # Both committed IDs replay without time/recovery/history writes.
                with patch.object(restored.game_session, "resolve_species_trait_action",
                                  side_effect=AssertionError("Rest replay executed")), \
                     patch.object(stores[loser], "save_campaign",
                                  side_effect=AssertionError("Rest replay saved")):
                    for index in (winner, loser):
                        replay = await send(clients[loser], index, sid)
                        expected = copy.deepcopy(responses[winner].json() if index == winner else retry.json())
                        expected["session_id"] = sid
                        self.assertEqual(replay.status_code, 200, replay.text)
                        self.assertEqual(replay.json(), expected)
                        self.assertEqual(runtime_snapshot(restored), after)
                        self.assertEqual(saved_rows(), rows)
            finally:
                for client in clients:
                    await client.aclose()

    async def test_concurrent_duplicate_spell_executes_once_and_replays(self):
        a = await self.create_campaign()
        record, command = self.prepare_spell(a)
        with patch("game.apply_npc_damage", wraps=game.apply_npc_damage) as damage, patch.object(
            record.game_session.rng, "randint", wraps=record.game_session.rng.randint
        ) as dice:
            results = await self.simultaneous(a, [command, copy.deepcopy(command)])
        self.assertEqual([r.status_code for r in results], [200, 200])
        self.assertEqual(results[0].json(), results[1].json())
        self.assertEqual(damage.call_count, 1)
        self.assertEqual(dice.call_count, 3)
        self.assertEqual(record.game_session.world_state["spellcasting_v1"]["slots"]["1"], 1)
        self.assertEqual(len(self.store.get_campaign(a["campaign_id"]).history), 1)
        with closing(self.store._connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM campaign_turn_actions").fetchone()[0], 1)

    async def test_concurrent_different_actions_serialize_without_lost_time(self):
        self.manager._session_factory = clocks.scene
        a = await self.create_campaign()
        record = self.manager.get(a["session_id"])
        before_time = record.game_session.world_state["campaign_time"]["elapsed_seconds"]
        before_rng = record.game_session.rng.getstate()
        commands = [{"message": message, "action_id": str(uuid4())}
                    for message in ("1 saat bekle.", "2 saat bekle.")]
        results = await self.simultaneous(a, commands)
        self.assertEqual([r.status_code for r in results], [200, 200])
        self.assertEqual(record.game_session.world_state["campaign_time"]["elapsed_seconds"] - before_time, 10800)
        self.assertEqual(record.game_session.rng.getstate(), before_rng)
        self.assertEqual(len(self.store.get_campaign(a["campaign_id"]).history), 2)
        committed = self.snapshot(record)
        for command in commands:
            self.assertEqual((await self.post(a, command)).status_code, 200)
        self.assertEqual(self.snapshot(record), committed)

    async def test_stale_request_rejects_before_resolution_then_explicit_resume_refreshes(self):
        self.manager._session_factory = clocks.scene
        a = await self.create_campaign()
        record = self.manager.get(a["session_id"])
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
        _, newer, *_ = fresh.resume_campaign(a["campaign_id"])
        newer.game_session.advance_campaign_time(600, "wait")
        fresh.save_campaign(a["campaign_id"])
        before = self.snapshot(record)
        command = {"message": "1 saat bekle.", "action_id": str(uuid4())}
        with patch("game.run_player_turn", side_effect=AssertionError("stale resolution")):
            rejected = await self.post(a, command)
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["detail"]["code"], "campaign_stale")
        self.assertEqual(self.snapshot(record), before)
        sid, refreshed, *_ = self.manager.resume_campaign(a["campaign_id"])
        self.assertEqual(sid, a["session_id"])
        self.assertEqual(refreshed.game_session.rng.getstate(), newer.game_session.rng.getstate())
        self.assertEqual(refreshed.game_session.serialize_game_state(), newer.game_session.serialize_game_state())
        self.assertEqual((await self.post(a, command)).status_code, 200)

    async def test_legacy_v3_upgrade_preserves_payload_receipt_and_rng(self):
        self.manager._session_factory = clocks.scene
        a = await self.create_campaign()
        command = {"message": "1 saat bekle.", "action_id": str(uuid4())}
        original = await self.post(a, command)
        self.assertEqual(original.status_code, 200, original.text)
        with closing(self.store._connect()) as db:
            payload = db.execute("SELECT payload_json FROM campaigns").fetchone()[0]
            receipt = tuple(db.execute("SELECT * FROM campaign_turn_actions").fetchone())
            db.execute("ALTER TABLE campaigns DROP COLUMN revision")
            db.execute("PRAGMA user_version = 3")
        upgraded = CampaignStore(self.store.path)
        with closing(upgraded._connect()) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT payload_json FROM campaigns").fetchone()[0], payload)
            self.assertEqual(tuple(db.execute("SELECT * FROM campaign_turn_actions").fetchone()), receipt)
        fresh = SessionManager(campaign_store=upgraded)
        sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
        self.assertEqual(restored.game_session.rng.getstate(), self.manager.get(a["session_id"]).game_session.rng.getstate())
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://legacy") as client:
            replay = await client.post(f"/api/game/sessions/{sid}/turn", json=command)
        expected = original.json()
        expected["session_id"] = sid
        self.assertEqual(replay.json(), expected)

    async def test_deleted_campaign_revokes_independent_cached_copy_and_cannot_resurrect(self):
        a, b = await self.create_campaign(), await self.create_campaign()
        other = SessionManager(campaign_store=CampaignStore(self.store.path))
        sid, stale, *_ = other.resume_campaign(a["campaign_id"])
        isolated = self.store.get_campaign(b["campaign_id"])
        self.assertTrue(self.manager.delete_campaign(a["campaign_id"])["deleted"])
        with self.assertRaises(LookupError):
            other.get(sid)
        self.assertTrue(stale.revoked)
        with self.assertRaises(CampaignError):
            other.save_campaign_locked(stale)
        with self.assertRaises(CampaignError):
            SessionManager(campaign_store=CampaignStore(self.store.path)).resume_campaign(a["campaign_id"])
        self.assertFalse(self.manager.delete_campaign(a["campaign_id"])["deleted"])
        self.assertEqual(self.store.get_campaign(b["campaign_id"]), isolated)

    async def test_event_action_id_cannot_be_reused_for_other_event_or_turn(self):
        a = await self.create_campaign()
        record = self.manager.get(a["session_id"])
        event_a = self.install_test_ambient_event(record.game_session)
        action_id = str(uuid4())
        path = f"/api/game/sessions/{a['session_id']}/ambient-events"
        applied = await self.http.post(f"{path}/{event_a}/actions",
                                       json={"action_id": action_id, "action": "interact"})
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["result"]["status"], "APPLIED")
        # Existing public outcome remains ALREADY_APPLIED, with the same resolution.
        replay = await self.http.post(f"{path}/{event_a}/actions",
                                      json={"action_id": action_id, "action": "interact"})
        self.assertEqual(replay.json()["result"]["status"], "ALREADY_APPLIED")
        self.assertEqual(replay.json()["result"]["canonical_event_id"],
                         applied.json()["result"]["canonical_event_id"])
        event_b = self.install_test_ambient_event(record.game_session)
        self.manager.save_campaign(a["campaign_id"])
        before = self.snapshot(record)
        conflict = await self.http.post(f"{path}/{event_b}/actions",
                                        json={"action_id": action_id, "action": "interact"})
        self.assertEqual(conflict.json()["result"]["reason_code"], "action_id_conflict")
        turn = await self.post(a, {"message": "1 saat bekle.", "action_id": action_id})
        self.assertEqual(turn.status_code, 409, turn.text)
        self.assertEqual(self.snapshot(record), before)
        # Simulate the pre-hardening event representation; canonical identity is
        # still in the journal, so the ID must not become a new turn.
        with closing(self.store._connect()) as db:
            db.execute("DELETE FROM campaign_turn_actions WHERE action_id = ?", (action_id,))
        CampaignStore(self.store.path)  # Startup imports known structured legacy identities.
        record.journal["notable_events"] = []  # Simulate the existing bounded journal trim.
        self.manager.save_campaign(a["campaign_id"])
        legacy_before = self.snapshot(record)
        legacy_replay = await self.http.post(f"{path}/{event_a}/actions",
                                             json={"action_id": action_id, "action": "interact"})
        self.assertEqual(legacy_replay.json()["result"]["status"], "ALREADY_APPLIED")
        self.assertEqual(legacy_replay.json()["result"]["canonical_event_id"],
                         applied.json()["result"]["canonical_event_id"])
        self.assertEqual((await self.post(a, {"message": "1 saat bekle.", "action_id": action_id})).status_code, 409)
        self.assertEqual(self.snapshot(record), legacy_before)

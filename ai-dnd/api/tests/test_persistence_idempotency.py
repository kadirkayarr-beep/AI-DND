"""Persistence boundaries missing from the existing subsystem/CTM suites."""
import copy
import asyncio
from contextlib import closing
from datetime import datetime, timedelta
from functools import wraps
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import game
import httpx
from api.main import create_app

from api.persistence.campaign_models import CampaignError
from api.persistence.campaign_store import CampaignStore, MAX_COMBAT_HISTORY_ENTRIES
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures
from api.tests import test_spell_scope as spells
from api.tests import test_campaign_time as clocks
from api.tests.test_action_economy_reactions import interrupted, assert_continuation
import json


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

    async def assert_corrupt_saved_receipt_blocks_retry(self, corruption, operation="turn"):
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
            # Correct length, but not hexadecimal: not an ordinary request mismatch.
            sql = "UPDATE campaign_turn_actions SET request_hash = ? WHERE campaign_id = ? AND action_id = ?"
            value = "g" * 64
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
        with self.store._transaction() as connection:
            updated = connection.execute(sql, (value, campaign_id, command["action_id"]))
            self.assertEqual(updated.rowcount, 1)
        self.assertEqual(self.store.get_campaign(campaign_id), committed)

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
            with patch("game.run_player_turn",
                       side_effect=AssertionError("Corrupt receipt executed the engine")) as engine, \
                 patch("game.resolve_species_trait_action",
                       side_effect=AssertionError("Corrupt receipt repeated rest")) as rest, \
                 patch.object(fresh, "autosave_turn",
                              side_effect=AssertionError("Corrupt receipt autosaved")) as autosave, \
                 patch.object(fresh_store, "save_campaign",
                              side_effect=AssertionError("Corrupt receipt saved")) as save:
                retry = await client.post(f"/api/game/sessions/{sid}/{endpoint}", json=command)
            self.assertEqual(retry.status_code, expected_status, retry.text)
            self.assertEqual(retry.json()["detail"]["code"], expected_code)
            self.assertIsInstance(retry.json()["detail"]["message"], str)
            self.assertTrue(retry.json()["detail"]["message"])
            engine.assert_not_called()
            rest.assert_not_called()
            autosave.assert_not_called()
            save.assert_not_called()
            self.assertEqual(self.snapshot(restored), before_runtime)
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

    async def test_corrupt_saved_receipt_hash_blocks_http_retry_after_resume(self):
        await self.assert_corrupt_saved_receipt_blocks_retry("hash")

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

    async def assert_transient_response_validation(self, operation, *, envelope_only=False):
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
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
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

        async def retry_without_effects(status):
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
                retry = await self.http.post(path, json=command)
            self.assertEqual(retry.status_code, status, retry.text)
            if status == 200:
                self.assertEqual(retry.json(), expected)
            else:
                self.assertEqual(retry.json()["detail"]["code"], "campaign_unavailable")
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
        sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
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
        self.assertEqual(self.snapshot(record), committed)
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

    async def assert_evicted_combat_receipt_after_reopen(
        self, *, changed_payload, rest_action=None,
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

        fresh_store = CampaignStore(self.store.path)
        fresh = SessionManager(campaign_store=fresh_store)
        sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
        self.assertNotEqual(sid, a["session_id"])
        self.assertIsNot(restored.game_session, session)
        self.assertEqual(self.snapshot(restored)[:7], committed[:7])
        self.assertEqual(restored.combat_history, surviving)
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

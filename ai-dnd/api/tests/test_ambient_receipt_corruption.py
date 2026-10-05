"""HTTP replay must reject damaged event replies without replaying gameplay."""
import copy
from contextlib import closing
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.schemas import AmbientEventCommandResult
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures
from api.tests import test_persistence_idempotency as idempotency


class AmbientReceiptCorruptionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign
    install_test_ambient_event = fixtures.CampaignApiTests.install_test_ambient_event
    snapshot = idempotency.PersistenceIdempotencyTests.snapshot

    def raw_rows(self, store, campaign_id):
        with closing(store._connect()) as db:
            return (
                [tuple(row) for row in db.execute(
                    "SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,),
                )],
                [tuple(row) for row in db.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? ORDER BY action_id",
                    (campaign_id,),
                )],
                [tuple(row) for row in db.execute(
                    "SELECT * FROM campaign_history WHERE campaign_id = ? ORDER BY sequence",
                    (campaign_id,),
                )],
                [tuple(row) for row in db.execute(
                    "SELECT * FROM campaign_combat_history WHERE campaign_id = ? ORDER BY sequence",
                    (campaign_id,),
                )],
            )

    async def check_reopened_receipt(
        self, mutate=None, legacy=None, conflict=None, *, legacy_projection=None,
    ):
        if legacy_projection is not None:
            legacy = "valid"
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        event_id = self.install_test_ambient_event(record.game_session)
        command = {"action_id": str(uuid4()), "action": "interact"}
        endpoint = f"ambient-events/{event_id}/actions"
        before_apply = copy.deepcopy(record.game_session.serialize_game_state())
        accepted = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/{endpoint}", json=command,
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
        self.assertNotEqual(record.game_session.serialize_game_state(), before_apply)
        committed = self.store.get_campaign(campaign_id)
        receipt = self.store.get_turn_action(campaign_id, command["action_id"])
        self.assertEqual(receipt["response"]["ambient_event_response"], accepted.json())
        damaged = copy.deepcopy(receipt["response"])
        if legacy == "imported":
            # Startup reserves old journal identities without inventing a reply.
            with self.store._transaction() as db:
                db.execute(
                    "DELETE FROM campaign_turn_actions WHERE campaign_id = ? AND action_id = ?",
                    (campaign_id, command["action_id"]),
                )
        else:
            if legacy == "empty":
                damaged = {"action_id": command["action_id"], "legacy_ambient_result": {}}
            elif legacy == "valid":
                damaged = {
                    "action_id": command["action_id"],
                    "legacy_ambient_result": copy.deepcopy(legacy_projection),
                }
            elif legacy == "damaged":
                damaged = {
                    "action_id": command["action_id"],
                    "legacy_ambient_result": {
                        key: accepted.json()["result"][key]
                        for key in ("transition_id", "canonical_event_id")
                    },
                }
            if mutate is not None:
                mutate(damaged)
            self.assertEqual(damaged["action_id"], command["action_id"])
            with self.store._transaction() as db:
                updated = db.execute(
                    "UPDATE campaign_turn_actions SET response_json = ? WHERE campaign_id = ? AND action_id = ?",
                    (json.dumps(damaged), campaign_id, command["action_id"]),
                )
                self.assertEqual(updated.rowcount, 1)
        self.assertEqual(self.store.get_campaign(campaign_id), committed)
        fresh_store = CampaignStore(self.store.path)
        if legacy != "imported":
            loaded = fresh_store.get_turn_action(campaign_id, command["action_id"])
            self.assertEqual(loaded["request_hash"], receipt["request_hash"])
            self.assertEqual(loaded["response"], damaged)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://reload",
        ) as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = fresh.get(sid)
            self.assertIsNot(restored.game_session, record.game_session)
            reopened = fresh_store.get_campaign(campaign_id)
            self.assertEqual(reopened.payload, committed.payload)
            self.assertEqual(reopened.history, committed.history)
            self.assertEqual(reopened.combat_history, committed.combat_history)
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertEqual(restored.game_session.serialize_game_state(),
                             record.game_session.serialize_game_state())
            self.assertEqual(restored.game_session.rng.getstate(),
                             record.game_session.rng.getstate())
            # Resume may update last-played metadata. Snapshot immediately before retry.
            before = self.snapshot(restored)
            auxiliary = copy.deepcopy((
                restored.game_session.messages, restored.game_session.world_metadata,
            ))
            rows = self.raw_rows(fresh_store, campaign_id)
            retry_command = copy.deepcopy(command)
            retry_endpoint = endpoint
            retry_event_id = event_id
            if conflict == "action":
                retry_command["action"] = "observe"
            elif conflict == "event":
                retry_event_id = str(uuid4())
                self.assertNotEqual(retry_event_id, event_id)
                retry_endpoint = f"ambient-events/{retry_event_id}/actions"
            elif conflict is not None:
                self.fail(f"Unknown conflict case: {conflict}")
            reserved = fresh_store.get_turn_action(campaign_id, command["action_id"])
            self.assertIsNotNone(reserved)
            self.assertEqual(reserved["request_hash"], receipt["request_hash"])
            if legacy is not None:
                self.assertNotIn("ambient_event_response", reserved["response"])
                self.assertIn("legacy_ambient_result", reserved["response"])
            if legacy == "valid":
                self.assertEqual(reserved["response"], damaged)
            with patch.object(restored.game_session, "resolve_ambient_event_action",
                              side_effect=AssertionError("Replay executed mechanics")) as mechanics, \
                 patch.object(fresh, "save_campaign_locked",
                              side_effect=AssertionError("Replay attempted persistence")) as locked_save, \
                 patch.object(fresh, "autosave_turn",
                              side_effect=AssertionError("Replay attempted autosave")) as autosave, \
                 patch.object(fresh_store, "save_campaign",
                              side_effect=AssertionError("Replay saved campaign")) as save:
                retry = await client.post(
                    f"/api/game/sessions/{sid}/{retry_endpoint}", json=retry_command,
                )
            if conflict is not None:
                self.assertEqual(retry.status_code, 200, retry.text)
                response = retry.json()
                AmbientEventCommandResult.model_validate(response, strict=True)
                self.assertEqual(response["session_id"], sid)
                self.assertEqual(response["result"], {
                    "event_instance_id": retry_event_id,
                    "action_id": command["action_id"],
                    "status": "REJECTED",
                    "reason_code": "action_id_conflict",
                    "transition_id": None,
                    "canonical_event_id": None,
                })
                self.assertNotIn("ambient_event_response", response)
                self.assertNotIn("legacy_ambient_result", response)
            elif mutate is not None:
                self.assertEqual(retry.status_code, 409, retry.text)
                self.assertEqual(retry.json()["detail"]["code"], "campaign_unavailable")
                self.assertIsInstance(retry.json()["detail"]["message"], str)
                self.assertTrue(retry.json()["detail"]["message"])
            else:
                self.assertEqual(retry.status_code, 200, retry.text)
                expected = copy.deepcopy(accepted.json()["result"])
                expected.update(status="ALREADY_APPLIED", reason_code="event_already_resolved")
                if legacy == "empty":
                    expected.update(transition_id=None, canonical_event_id=None)
                elif legacy == "valid":
                    expected.update(
                        transition_id=legacy_projection.get("transition_id"),
                        canonical_event_id=legacy_projection.get("canonical_event_id"),
                    )
                AmbientEventCommandResult.model_validate(retry.json(), strict=True)
                self.assertEqual(retry.json()["result"], expected)
                self.assertEqual(retry.json()["session_id"], sid)
            for spy in (mechanics, locked_save, autosave, save):
                spy.assert_not_called()
            self.assertEqual(self.snapshot(restored), before)
            self.assertEqual((
                restored.game_session.messages, restored.game_session.world_metadata,
            ), auxiliary)
            self.assertEqual(self.raw_rows(fresh_store, campaign_id), rows)
            self.assertEqual(fresh_store.get_campaign(campaign_id), reopened)

    async def test_incomplete_saved_event_replies_fail_safely_after_resume(self):
        paths = (
            ("ambient_event_response",),
            ("ambient_event_response", "session_id"),
            ("ambient_event_response", "state"),
            ("ambient_event_response", "result"),
            ("ambient_event_response", "result", "event_instance_id"),
            ("ambient_event_response", "result", "action_id"),
            ("ambient_event_response", "result", "status"),
        )
        for path in paths:
            with self.subTest(missing=path):
                def remove(response):
                    parent = response
                    for field in path[:-1]:
                        parent = parent[field]
                    del parent[path[-1]]
                await self.check_reopened_receipt(remove)

    async def test_wrongly_typed_saved_event_replies_fail_safely_after_resume(self):
        cases = (
            (("ambient_event_response",), None),
            (("ambient_event_response",), []),
            (("ambient_event_response",), "broken"),
            (("ambient_event_response", "session_id"), 17),
            (("ambient_event_response", "state"), []),
            (("ambient_event_response", "result"), None),
            (("ambient_event_response", "result"), []),
            (("ambient_event_response", "result"), "broken"),
            (("ambient_event_response", "result", "event_instance_id"), 17),
            (("ambient_event_response", "result", "action_id"), []),
            (("ambient_event_response", "result", "status"), "INVALID"),
            (("ambient_event_response", "result", "transition_id"), {}),
            (("ambient_event_response", "result", "canonical_event_id"), []),
            (("ambient_event_response", "result", "reason_code"), 17),
        )
        for path, value in cases:
            with self.subTest(path=path, value=value):
                def replace(response):
                    parent = response
                    for field in path[:-1]:
                        parent = parent[field]
                    parent[path[-1]] = value
                await self.check_reopened_receipt(replace)

    async def test_valid_saved_event_reply_retains_already_applied_projection(self):
        await self.check_reopened_receipt()

    async def test_malformed_transient_event_receipts_fail_without_repeating_outcomes(self):
        # Event application requires persistence. Obtain a genuine accepted
        # receipt, then seed the transient owner through its normal receipt
        # ingress; the HTTP replay lookup precedes the persistence requirement.
        created = await self.create_campaign()
        source = self.manager.get(created["session_id"])
        event_id = self.install_test_ambient_event(source.game_session)
        command = {"action_id": str(uuid4()), "action": "interact"}
        endpoint = f"ambient-events/{event_id}/actions"
        before_apply = copy.deepcopy(source.game_session.serialize_game_state())
        accepted = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/{endpoint}", json=command,
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
        self.assertNotEqual(source.game_session.serialize_game_state(), before_apply)
        original = self.store.get_turn_action(created["campaign_id"], command["action_id"])
        self.assertEqual(original["response"]["ambient_event_response"], accepted.json())
        # SQL lookup omits the key supplied separately at transient ingress.
        original["action_id"] = command["action_id"]

        transient = await self.http.post("/api/game/sessions")
        self.assertEqual(transient.status_code, 200, transient.text)
        sid = transient.json()["session_id"]
        record = self.manager.get(sid)
        self.assertIsNone(record.campaign_id)
        with record.turn_lock:
            self.manager.autosave_turn(
                record, player_message="", narration="", turn_action_receipt=original,
            )
        self.assertEqual(self.manager.get_turn_action(record, command["action_id"]), original)
        session = record.game_session
        path = f"/api/game/sessions/{sid}/{endpoint}"
        expected_result = copy.deepcopy(accepted.json()["result"])
        expected_result.update(
            status="ALREADY_APPLIED", reason_code="event_already_resolved",
        )
        source_before = self.snapshot(source)
        rows_before = self.raw_rows(self.store, created["campaign_id"])

        def runtime_snapshot():
            return copy.deepcopy((
                self.snapshot(record), session.messages, session.world_metadata,
            ))

        async def retry_without_effects(status):
            before = runtime_snapshot()
            with patch.object(session, "resolve_ambient_event_action",
                              side_effect=AssertionError("Replay repeated event mechanics")) as mechanics, \
                 patch.object(session.rng, "randint",
                              side_effect=AssertionError("Replay rolled dice")) as dice, \
                 patch.object(session.rng, "random",
                              side_effect=AssertionError("Replay consumed RNG")) as random, \
                 patch.object(session.rng, "getrandbits",
                              side_effect=AssertionError("Replay consumed RNG bits")) as bits, \
                 patch.object(self.manager, "save_campaign_locked",
                              side_effect=AssertionError("Replay saved event outcome")) as locked_save, \
                 patch.object(self.manager, "autosave_turn",
                              side_effect=AssertionError("Replay replaced receipt")) as autosave, \
                 patch.object(self.store, "save_campaign",
                              side_effect=AssertionError("Transient replay persisted")) as save, \
                 patch.object(self.store, "get_turn_action",
                              side_effect=AssertionError("Transient replay read persisted receipt")) as lookup:
                retry = await self.http.post(path, json=command)
            self.assertEqual(retry.status_code, status, retry.text)
            if status == 200:
                self.assertEqual(retry.json()["session_id"], sid)
                self.assertEqual(retry.json()["result"], expected_result)
            else:
                self.assertEqual(retry.json()["detail"]["code"], "campaign_unavailable")
                self.assertIsInstance(retry.json()["detail"]["message"], str)
                self.assertTrue(retry.json()["detail"]["message"])
            for guard in (mechanics, dice, random, bits, locked_save, autosave, save, lookup):
                guard.assert_not_called()
            self.assertEqual(runtime_snapshot(), before)
            self.assertEqual(self.snapshot(source), source_before)
            self.assertEqual(self.raw_rows(self.store, created["campaign_id"]), rows_before)
            return retry.json()

        committed = runtime_snapshot()
        valid_replay = await retry_without_effects(200)
        damaged_receipts = [
            ("non_dictionary", value) for value in (None, [], "", 0, False, ["receipt"])
        ]
        for field, invalid_values in (
            ("request_hash", (None, [], 123, "", False, {})),
            ("response", (None, [], 123, "", False)),
        ):
            damaged = copy.deepcopy(original)
            del damaged[field]
            damaged_receipts.append((f"missing_{field}", damaged))
            for value in invalid_values:
                damaged = copy.deepcopy(original)
                damaged[field] = value
                damaged_receipts.append((f"invalid_{field}_{value!r}", damaged))

        for corruption, damaged in damaged_receipts:
            with self.subTest(corruption=corruption):
                record.turn_action_receipts[command["action_id"]] = damaged
                await retry_without_effects(409)
                # Lookup must neither remove, repair nor replace a damaged owner.
                self.assertIn(command["action_id"], record.turn_action_receipts)
                self.assertIs(record.turn_action_receipts[command["action_id"]], damaged)
                record.turn_action_receipts[command["action_id"]] = copy.deepcopy(original)
                self.assertEqual(runtime_snapshot(), committed)
                self.assertEqual(await retry_without_effects(200), valid_replay)

    async def check_mismatched_nested_identity(self, field):
        def replace_identity(response):
            original = copy.deepcopy(response)
            result = response["ambient_event_response"]["result"]
            replacement = str(uuid4())
            self.assertNotEqual(replacement, result[field])
            result[field] = replacement
            # This corruption still satisfies the HTTP schema; only the nested
            # identity changes, not the receipt's outer action or other fields.
            AmbientEventCommandResult.model_validate(
                response["ambient_event_response"], strict=True,
            )
            unchanged = copy.deepcopy(response)
            unchanged["ambient_event_response"]["result"][field] = (
                original["ambient_event_response"]["result"][field]
            )
            self.assertEqual(unchanged, original)

        await self.check_reopened_receipt(replace_identity)

    async def test_wrong_nested_action_identity_fails_safely_after_resume(self):
        await self.check_mismatched_nested_identity("action_id")

    async def test_wrong_nested_event_identity_fails_safely_after_resume(self):
        await self.check_mismatched_nested_identity("event_instance_id")

    async def test_imported_legacy_reservation_replays_without_full_response(self):
        await self.check_reopened_receipt(legacy="imported")

    async def test_empty_legacy_projection_does_not_require_modern_response_fields(self):
        await self.check_reopened_receipt(legacy="empty")

    async def test_valid_legacy_identity_boundaries_preserve_replay_and_conflicts_after_resume(self):
        cases = (
            ("null_transition", {"transition_id": None, "canonical_event_id": "legacy-event"}),
            ("null_event", {"transition_id": "legacy-transition", "canonical_event_id": None}),
            ("both_null", {"transition_id": None, "canonical_event_id": None}),
            ("omitted_transition", {"canonical_event_id": "legacy-event"}),
            ("omitted_event", {"transition_id": "legacy-transition"}),
            ("transition_limit", {
                "transition_id": "t" * 160, "canonical_event_id": "legacy-event",
            }),
            ("event_limit", {
                "transition_id": "legacy-transition", "canonical_event_id": "e" * 36,
            }),
            ("both_limits", {
                "transition_id": "t" * 160, "canonical_event_id": "e" * 36,
            }),
        )
        for boundary, projection in cases:
            # Valid historical projections need neither modern reply fields nor
            # UUID-shaped event identities. Omission and null both project null,
            # but the stored reservation must retain its exact original shape.
            for conflict in (None, "action", "event"):
                with self.subTest(boundary=boundary, conflict=conflict):
                    await self.check_reopened_receipt(
                        legacy_projection=projection, conflict=conflict,
                    )

    async def test_conflicts_precede_corrupt_modern_reply_validation_after_resume(self):
        def missing_response(response):
            del response["ambient_event_response"]

        def missing_session_id(response):
            del response["ambient_event_response"]["session_id"]

        def invalid_result(response):
            response["ambient_event_response"]["result"] = "broken"

        def wrong_action_identity(response):
            response["ambient_event_response"]["result"]["action_id"] = str(uuid4())

        def wrong_event_identity(response):
            response["ambient_event_response"]["result"]["event_instance_id"] = str(uuid4())

        for mutate in (
            missing_response, missing_session_id, invalid_result,
            wrong_action_identity, wrong_event_identity,
        ):
            for conflict in ("action", "event"):
                with self.subTest(corruption=mutate.__name__, conflict=conflict):
                    await self.check_reopened_receipt(mutate, conflict=conflict)

    async def test_conflicts_precede_partial_legacy_projection_after_resume(self):
        for legacy in ("imported", "empty"):
            for conflict in ("action", "event"):
                with self.subTest(legacy=legacy, conflict=conflict):
                    await self.check_reopened_receipt(legacy=legacy, conflict=conflict)

    async def test_damaged_persisted_legacy_projections_preserve_reservations_after_resume(self):
        cases = [
            ((), value) for value in (None, [], "broken", 17, False)
        ]
        for field, limit in (("transition_id", 160), ("canonical_event_id", 36)):
            cases.extend(
                ((field,), value) for value in ({}, [], 17, False, "x" * (limit + 1))
            )
        for path, value in cases:
            # Every damaged projection must both fail an identical retry and
            # retain hash-conflict precedence for a changed action or event.
            for conflict in (None, "action", "event"):
                with self.subTest(path=path, value=value, conflict=conflict):
                    def replace(response):
                        if path:
                            response["legacy_ambient_result"][path[0]] = value
                        else:
                            response["legacy_ambient_result"] = value

                    await self.check_reopened_receipt(
                        replace, legacy="damaged", conflict=conflict,
                    )

"""Malformed retained hashes are corruption, not ordinary request conflicts."""
import copy
from contextlib import ExitStack, closing
import unittest
from unittest.mock import patch
from uuid import uuid4

from api.tests import test_campaign_api as fixtures
from api.tests import test_persistence_idempotency as idempotency


class TransientRequestHashTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign
    install_test_ambient_event = fixtures.CampaignApiTests.install_test_ambient_event
    prepare_spell = idempotency.PersistenceIdempotencyTests.prepare_spell
    snapshot = idempotency.PersistenceIdempotencyTests.snapshot

    async def check_hash_validation(self, owner):
        transient = await self.http.post("/api/game/sessions")
        self.assertEqual(transient.status_code, 200, transient.text)
        created = transient.json()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        self.assertIsNone(record.campaign_id)
        source = None
        event_id = str(uuid4())

        if owner == "turn":
            record, command = self.prepare_spell(created)
            endpoint = "turn"
        elif owner == "species":
            session.commit_location_change("tavern")
            session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
            session.initialize_species_trait_state()
            session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
            command = {"action": "short_rest", "action_id": str(uuid4())}
            endpoint = "species-actions"
        else:
            # Ambient mechanics require a campaign. Seed transient ingress with
            # a genuine committed receipt; lookup precedes that requirement.
            campaign = await self.create_campaign()
            source = self.manager.get(campaign["session_id"])
            event_id = self.install_test_ambient_event(source.game_session)
            command = {"action": "interact", "action_id": str(uuid4())}
            endpoint = f"ambient-events/{event_id}/actions"
            before_action = copy.deepcopy(source.game_session.serialize_game_state())
            accepted = await self.http.post(
                f"/api/game/sessions/{campaign['session_id']}/{endpoint}", json=command,
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
            self.assertNotEqual(source.game_session.serialize_game_state(), before_action)
            original = self.store.get_turn_action(campaign["campaign_id"], command["action_id"])
            original["action_id"] = command["action_id"]
            with record.turn_lock:
                self.manager.autosave_turn(
                    record, player_message="", narration="", turn_action_receipt=original,
                )

        if owner != "ambient":
            before_action = copy.deepcopy(session.serialize_game_state())
            accepted = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/{endpoint}", json=command,
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertNotEqual(session.serialize_game_state(), before_action)
        original = copy.deepcopy(record.turn_action_receipts[command["action_id"]])
        expected = copy.deepcopy(accepted.json())
        if owner == "ambient":
            expected["session_id"] = created["session_id"]
            expected["result"].update(
                status="ALREADY_APPLIED", reason_code="event_already_resolved",
            )
        else:
            self.assertEqual(original["response"], expected)

        requests = {
            "turn": ("turn", {"message": "Different request.", "action_id": command["action_id"]}),
            "species": ("species-actions", {
                "action": "long_rest", "action_id": command["action_id"],
            }),
            "ambient": (f"ambient-events/{event_id}/actions", {
                "action": "observe", "action_id": command["action_id"],
            }),
        }
        replay_request = (endpoint, command)

        def complete_snapshot():
            # Include every database row, not only gameplay payloads, to detect
            # writes/repair to metadata, histories, and the source event receipt.
            with closing(self.store._connect()) as db:
                rows = tuple(db.iterdump())
            return copy.deepcopy((
                self.snapshot(record), session.messages, session.world_metadata,
                (self.snapshot(source), source.game_session.messages,
                 source.game_session.world_metadata) if source else None,
                rows,
            ))

        async def retry_without_effects(request, *, corrupt=False, replay=False):
            before = complete_snapshot()
            retry_endpoint, body = request
            guards = (
                (session, "run_player_turn"),
                (session, "resolve_species_trait_action"),
                (session, "resolve_ambient_event_action"),
                (session.rng, "randint"),
                (session.rng, "random"),
                (session.rng, "getrandbits"),
                (self.manager, "autosave_turn"),
                (self.manager, "save_campaign_locked"),
                (self.store, "save_campaign"),
                (self.store, "get_turn_action"),
            )
            with ExitStack() as stack:
                spies = [
                    stack.enter_context(patch.object(
                        target, method,
                        side_effect=AssertionError(f"Retry invoked {method}"),
                    ))
                    for target, method in guards
                ]
                retry = await self.http.post(
                    f"/api/game/sessions/{created['session_id']}/{retry_endpoint}", json=body,
                )
            if replay:
                self.assertEqual(retry.status_code, 200, retry.text)
                if owner == "ambient":
                    # Ambient replay projects the current session view, unlike
                    # turn/species replay which returns the retained full reply.
                    self.assertEqual(retry.json()["session_id"], expected["session_id"])
                    self.assertEqual(retry.json()["result"], expected["result"])
                else:
                    self.assertEqual(retry.json(), expected)
            elif corrupt:
                self.assertEqual(retry.status_code, 409, retry.text)
                self.assertEqual(retry.json()["detail"]["code"], "campaign_unavailable")
                self.assertTrue(retry.json()["detail"]["message"])
            elif retry_endpoint.startswith("ambient-events/"):
                self.assertEqual(retry.status_code, 200, retry.text)
                self.assertEqual(retry.json()["result"]["status"], "REJECTED")
                self.assertEqual(retry.json()["result"]["reason_code"], "action_id_conflict")
            else:
                self.assertEqual(retry.status_code, 409, retry.text)
                self.assertEqual(retry.json()["detail"]["code"], "action_id_conflict")
            for spy in spies:
                spy.assert_not_called()
            self.assertEqual(complete_snapshot(), before)

        committed = complete_snapshot()
        await retry_without_effects(replay_request, replay=True)
        # These all retain a valid hash: a changed request, including a different
        # command family, must remain an ordinary conflict.
        for target, request in requests.items():
            with self.subTest(owner=owner, valid_hash_conflict=target):
                await retry_without_effects(request)

        for label, malformed in (
            ("short", "a" * 63),
            ("overlong", "a" * 65),
            ("nonhex", "g" * 64),
            ("uppercase", "A" * 64),
        ):
            damaged = copy.deepcopy(original)
            damaged["request_hash"] = malformed
            record.turn_action_receipts[command["action_id"]] = damaged
            for target, request in [("same_request", replay_request), *requests.items()]:
                with self.subTest(owner=owner, hash=label, target=target):
                    await retry_without_effects(request, corrupt=True)
                    self.assertIs(record.turn_action_receipts[command["action_id"]], damaged)
            # Restoration is test-only; no request may repair the retained owner.
            record.turn_action_receipts[command["action_id"]] = copy.deepcopy(original)
            self.assertEqual(complete_snapshot(), committed)
            await retry_without_effects(replay_request, replay=True)

    async def test_damaged_turn_hash_rejected_across_shared_http_boundary(self):
        await self.check_hash_validation("turn")

    async def test_damaged_species_hash_rejected_across_shared_http_boundary(self):
        await self.check_hash_validation("species")

    async def test_damaged_ambient_hash_rejected_across_shared_http_boundary(self):
        await self.check_hash_validation("ambient")

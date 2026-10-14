"""Model-off fault injection for rest persistence and failed runtime restoration."""
import copy
import sqlite3
from contextlib import closing
import unittest
from unittest.mock import patch
from uuid import uuid4

from api.tests import test_persistence_idempotency as persistence
import httpx
from api.auth import FixedAuthenticator
from api.main import create_app
from api.tests.auth_fixture import PLAYER_B
from api.session_manager import SessionManager
from api.persistence.campaign_models import CampaignStorageError


class RestFailureTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = persistence.PersistenceIdempotencyTests.asyncSetUp
    asyncTearDown = persistence.PersistenceIdempotencyTests.asyncTearDown
    create_campaign = persistence.PersistenceIdempotencyTests.create_campaign
    snapshot = persistence.PersistenceIdempotencyTests.snapshot

    async def prepare(self):
        created = await self.create_campaign()
        record = self.manager.get(created['session_id'])
        session = record.game_session
        session.commit_location_change('tavern')
        session.character.update(species='Orc', race='Orc', current_hp=1, max_hp=20)
        session.initialize_species_trait_state()
        session.character['species_trait_state']['adrenaline_rush_uses_remaining'] = 0
        self.manager.save_campaign(created['campaign_id'])
        return created, record

    async def test_short_and_long_rest_storage_failure_roll_back_then_retry_once(self):
        for action in ('short_rest', 'long_rest'):
            with self.subTest(action=action):
                created, record = await self.prepare()
                before = self.snapshot(record)
                auxiliary = copy.deepcopy((record.game_session.messages, record.game_session.world_metadata))
                command = {'action': action, 'action_id': str(uuid4())}
                url = f"/api/game/sessions/{created['session_id']}/species-actions"
                # Fail inside the real SQL transaction at the receipt insert,
                # after the command has changed runtime state and save has begun.
                with closing(sqlite3.connect(self.store.path)) as db:
                    db.execute("CREATE TRIGGER rest_receipt_failure BEFORE INSERT ON campaign_turn_actions BEGIN SELECT RAISE(ABORT, 'synthetic receipt write failure'); END")
                try:
                    with patch.object(self.store, 'save_campaign', wraps=self.store.save_campaign) as failure:
                        response = await self.http.post(url, json=command)
                finally:
                    with closing(sqlite3.connect(self.store.path)) as db:
                        db.execute('DROP TRIGGER rest_receipt_failure')
                self.assertEqual(response.status_code, 503, response.text)
                failure.assert_called_once()
                self.assertEqual(self.snapshot(record), before)
                self.assertEqual((record.game_session.messages, record.game_session.world_metadata), auxiliary)
                self.assertIsNone(self.store.get_turn_action(created['campaign_id'], command['action_id']))
                retry = await self.http.post(url, json=command)
                self.assertEqual(retry.status_code, 200, retry.text)
                committed = self.snapshot(record)
                self.assertEqual(len(committed[-1].history), len(before[-1].history) + 1)
                with patch.object(record.game_session, 'resolve_species_trait_action', side_effect=AssertionError('receipt reran rest')):
                    replay = await self.http.post(url, json=command)
                self.assertEqual(replay.json(), retry.json())
                self.assertEqual(self.snapshot(record), committed)

    async def test_failed_rest_restore_closes_session_without_committing_partial_state(self):
        for action in ('short_rest', 'long_rest'):
            with self.subTest(action=action):
                created, record = await self.prepare()
                before = self.snapshot(record)
                saved = self.store.get_campaign(created['campaign_id'])
                command = {'action': action, 'action_id': str(uuid4())}
                url = f"/api/game/sessions/{created['session_id']}/species-actions"
                with patch.object(self.store, 'save_campaign', side_effect=CampaignStorageError('synthetic disk failure')), patch.object(record.game_session, '_restore_runtime_snapshot', side_effect=RuntimeError('synthetic restore failure')):
                    response = await self.http.post(url, json=command)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()['detail']['code'], 'session_restore_failed')
                self.assertFalse(record.usable)
                self.assertEqual(self.store.get_campaign(created['campaign_id']), saved)
                self.assertIsNone(self.store.get_turn_action(created['campaign_id'], command['action_id']))
                blocked = await self.http.post(url, json=command)
                self.assertEqual(blocked.status_code, 409, blocked.text)

                fresh = SessionManager(campaign_store=self.store)
                _, recovered, *_ = fresh.resume_campaign(created['campaign_id'])
                self.assertTrue(recovered.usable)
                self.assertEqual(self.snapshot(recovered)[:7], before[:7])
                reopened = self.store.get_campaign(created['campaign_id'])
                self.assertEqual((reopened.payload, reopened.history, reopened.combat_history), (saved.payload, saved.history, saved.combat_history))
                self.assertIsNone(fresh.get_turn_action(recovered, command['action_id']))


    async def test_failed_rest_restore_is_isolated_from_other_owner(self):
        adapter = persistence.fixtures.AuthenticatedOllamaAdapter(
            persistence.fixtures.FakeOllamaClient()
        )
        other_app = create_app(
            session_manager=self.manager,
            ollama_adapter=adapter,
            authenticator=FixedAuthenticator(PLAYER_B),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=other_app),
            base_url="http://testserver",
        ) as other_http:
            for action in ('short_rest', 'long_rest'):
                with self.subTest(action=action):
                    created, failed_record = await self.prepare()
                    response = await other_http.post('/api/game/campaigns', json={})
                    self.assertEqual(response.status_code, 200, response.text)
                    other = response.json()
                    other_record = self.manager.get(other['session_id'], principal=PLAYER_B)
                    other_record.game_session.commit_location_change('tavern')
                    self.manager.save_campaign(other['campaign_id'], principal=PLAYER_B)

                    def other_snapshot():
                        return copy.deepcopy((
                            other_record.game_session._capture_runtime_snapshot(),
                            other_record.journal, other_record.narrative_memory,
                            other_record.lore_authority.to_dict(),
                            other_record.combat_history, other_record.turn_action_receipts,
                            self.store.get_campaign(other['campaign_id'], principal=PLAYER_B),
                        ))

                    before = other_snapshot()
                    failed_saved = self.store.get_campaign(created['campaign_id'])
                    command = {'action': action, 'action_id': str(uuid4())}
                    failed_url = f"/api/game/sessions/{created['session_id']}/species-actions"
                    other_url = f"/api/game/sessions/{other['session_id']}/species-actions"
                    original_save = self.store.save_campaign

                    def fail_only_target(campaign_id, *args, **kwargs):
                        if campaign_id == created['campaign_id']:
                            raise CampaignStorageError('synthetic owner-scoped disk failure')
                        return original_save(campaign_id, *args, **kwargs)

                    with patch.object(self.store, 'save_campaign', side_effect=fail_only_target), patch.object(
                        failed_record.game_session, '_restore_runtime_snapshot',
                        side_effect=RuntimeError('synthetic owner-scoped restore failure'),
                    ):
                        failed = await self.http.post(failed_url, json=command)
                        self.assertEqual(failed.status_code, 409, failed.text)
                        self.assertEqual(failed.json()['detail']['code'], 'session_restore_failed')
                        self.assertFalse(failed_record.usable)
                        self.assertTrue(other_record.usable)
                        self.assertEqual(other_snapshot(), before)

                        # Ownership is checked before unusable-session status.
                        denied = await other_http.post(failed_url, json=command)
                        self.assertEqual(denied.status_code, 404, denied.text)
                        denied = await self.http.post(other_url, json=command)
                        self.assertEqual(denied.status_code, 404, denied.text)
                        self.assertEqual(other_snapshot(), before)

                        # The same action UUID in B is independent from failed A.
                        accepted = await other_http.post(other_url, json=command)
                        self.assertEqual(accepted.status_code, 200, accepted.text)
                        committed = other_snapshot()
                        self.assertEqual(len(committed[-1].history), len(before[-1].history) + 1)
                        with patch.object(other_record.game_session, 'resolve_species_trait_action',
                                          side_effect=AssertionError('other owner replay reran rest')):
                            replay = await other_http.post(other_url, json=command)
                        self.assertEqual(replay.status_code, 200, replay.text)
                        self.assertEqual(replay.json(), accepted.json())
                        self.assertEqual(other_snapshot(), committed)
                        for operation in ('resume', 'save'):
                            healthy = await other_http.post(
                                f"/api/game/campaigns/{other['campaign_id']}/{operation}"
                            )
                            self.assertEqual(healthy.status_code, 200, healthy.text)

                    self.assertEqual(self.store.get_campaign(created['campaign_id']), failed_saved)
                    self.assertIsNone(self.store.get_turn_action(created['campaign_id'], command['action_id']))
                    blocked = await self.http.post(failed_url, json=command)
                    self.assertEqual(blocked.status_code, 409, blocked.text)
                    self.assertEqual(blocked.json()['detail']['code'], 'session_restore_failed')


    async def test_failed_restore_blocks_campaign_save_and_same_process_resume(self):
        for action in ('short_rest', 'long_rest'):
            with self.subTest(action=action):
                created, record = await self.prepare()
                saved = self.store.get_campaign(created['campaign_id'])
                command = {'action': action, 'action_id': str(uuid4())}
                with patch.object(self.store, 'save_campaign', side_effect=CampaignStorageError('synthetic disk failure')), patch.object(
                    record.game_session, '_restore_runtime_snapshot', side_effect=RuntimeError('synthetic restore failure')
                ):
                    failure = await self.http.post(
                        f"/api/game/sessions/{created['session_id']}/species-actions", json=command
                    )
                self.assertEqual(failure.status_code, 409, failure.text)
                for operation in ('resume', 'save'):
                    with self.subTest(operation=operation):
                        response = await self.http.post(
                            f"/api/game/campaigns/{created['campaign_id']}/{operation}"
                        )
                        self.assertEqual(response.status_code, 409, response.text)
                        self.assertEqual(response.json()['detail']['code'], 'campaign_not_active')
                        self.assertEqual(self.store.get_campaign(created['campaign_id']), saved)

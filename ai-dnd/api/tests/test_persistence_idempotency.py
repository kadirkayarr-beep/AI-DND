"""Persistence boundaries missing from the existing subsystem/CTM suites."""
import copy
import asyncio
from contextlib import closing
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

    async def assert_corrupt_saved_receipt_blocks_retry(self, corruption):
        created = await self.create_campaign()
        record, command = self.prepare_spell(created)
        accepted = await self.post(created, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
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
            before_runtime = self.snapshot(restored)
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
                 patch.object(fresh, "autosave_turn",
                              side_effect=AssertionError("Corrupt receipt autosaved")) as autosave, \
                 patch.object(fresh_store, "save_campaign",
                              side_effect=AssertionError("Corrupt receipt saved")) as save:
                retry = await client.post(f"/api/game/sessions/{sid}/turn", json=command)
            self.assertEqual(retry.status_code, expected_status, retry.text)
            self.assertEqual(retry.json()["detail"]["code"], expected_code)
            engine.assert_not_called()
            autosave.assert_not_called()
            save.assert_not_called()
            self.assertEqual(self.snapshot(restored), before_runtime)
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
            sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
            # Resume may update last_played_at in this same shared database.
            # Preserve every other committed field, then baseline replay after resume.
            reopened = self.store.get_campaign(a["campaign_id"])
            saved = committed[-1]
            self.assertEqual(reopened.payload, saved.payload)
            self.assertEqual(reopened.history, saved.history)
            self.assertEqual(reopened.combat_history, saved.combat_history)
            self.assertEqual(
                reopened.metadata,
                {**saved.metadata, "last_played_at": reopened.metadata["last_played_at"]},
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
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                            base_url="http://reload") as client:
                    replay = await client.post(f"/api/game/sessions/{sid}/turn", json=command)
            reopened_expected = copy.deepcopy(expected)
            reopened_expected["session_id"] = sid
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), reopened_expected)
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

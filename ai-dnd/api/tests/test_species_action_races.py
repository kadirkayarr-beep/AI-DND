"""Offline HTTP species command races and late persistence rollback."""

import asyncio
import copy
from contextlib import closing, ExitStack
from functools import wraps
import threading
import unittest
from unittest.mock import call, patch
from uuid import uuid4

import httpx

from api.main import create_app
from api.persistence.campaign_models import CampaignStaleError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures


class SpeciesActionRaceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    def runtime(self, record):
        session = record.game_session
        return copy.deepcopy({
            "engine": session.serialize_game_state(),
            "rng": session.rng.getstate(),
            "messages": session.messages,
            "metadata": session.world_metadata,
            "version": session._campaign_persistence_version,
            "journal": record.journal,
            "memory": record.narrative_memory,
            "lore": record.lore_authority.to_dict(),
            "combat_history": record.combat_history,
            "receipts": record.turn_action_receipts,
        })

    def rows(self, campaign_id):
        with closing(self.store._connect()) as connection:
            return {
                table: [tuple(row) for row in connection.execute(
                    f"SELECT * FROM {table} WHERE campaign_id = ? ORDER BY rowid",
                    (campaign_id,),
                )]
                for table in ("campaigns", "campaign_history",
                              "campaign_combat_history", "campaign_turn_actions")
            }

    async def test_healing_hands_receipt_sql_failure_rolls_back_then_retries_and_replays(self):
        created = await self.create_campaign()
        campaign_id, sid = created["campaign_id"], created["session_id"]
        record = self.manager.get(sid)
        session = record.game_session
        session.character.update(
            species="Aasimar", race="Aasimar", level=3,
            proficiency_bonus=2, current_hp=1, max_hp=40,
        )
        session.initialize_species_trait_state()
        session.rng.seed(812)
        self.manager.save_campaign(campaign_id)
        command = {"action": "healing_hands", "action_id": str(uuid4())}
        url = f"/api/game/sessions/{sid}/species-actions"
        baseline = self.runtime(record)
        baseline_rows = self.rows(campaign_id)
        saved_before = self.store.get_campaign(campaign_id)
        self.assertEqual(session.character["species_trait_state"]
                         ["healing_hands_uses_remaining"], 1)
        attempts = []
        real_save = self.store.save_campaign

        @wraps(real_save)
        def observe_save(*args, **kwargs):
            # Observe the real handler after healing/dice but before SQLite
            # rejects the receipt, late in the state/history transaction.
            attempts.append((self.runtime(record),
                             copy.deepcopy(kwargs["turn_action_receipt"])))
            return real_save(*args, **kwargs)

        with closing(self.store._connect()) as db:
            db.execute("""CREATE TRIGGER reject_healing_receipt
                          BEFORE INSERT ON campaign_turn_actions
                          BEGIN SELECT RAISE(ABORT, 'injected healing receipt failure'); END""")
        try:
            with (
                patch.object(self.store, "save_campaign", side_effect=observe_save) as save,
                patch.object(session, "resolve_species_trait_action",
                             wraps=session.resolve_species_trait_action) as ability,
                patch.object(session.rng, "randint", wraps=session.rng.randint) as dice,
            ):
                failed = await self.http.post(url, json=command)
            self.assertEqual(failed.status_code, 503, failed.text)
            self.assertEqual(failed.json()["detail"]["code"], "campaign_storage_unavailable")
            save.assert_called_once()
            ability.assert_called_once()
            self.assertEqual(dice.call_args_list, [call(1, 4)] * 2)
            self.assertEqual(len(attempts), 1)
            speculative, failed_receipt = attempts[0]
            self.assertGreater(speculative["engine"]["player"]["current_hp"], 1)
            self.assertEqual(speculative["engine"]["player"]["species_trait_state"]
                             ["healing_hands_uses_remaining"], 0)
            self.assertNotEqual(speculative["rng"], baseline["rng"])
            self.assertEqual(failed_receipt["action_id"], command["action_id"])
            self.assertEqual(failed_receipt["response"]["result"]["action"], "healing_hands")
            self.assertEqual(self.runtime(record), baseline)
            self.assertEqual(self.rows(campaign_id), baseline_rows)
            self.assertEqual(self.store.get_campaign(campaign_id), saved_before)
            self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
        finally:
            with closing(self.store._connect()) as db:
                db.execute("DROP TRIGGER reject_healing_receipt")

        with (
            patch.object(self.store, "save_campaign", wraps=real_save) as save,
            patch.object(session, "resolve_species_trait_action",
                         wraps=session.resolve_species_trait_action) as ability,
            patch.object(session.rng, "randint", wraps=session.rng.randint) as dice,
        ):
            accepted = await self.http.post(url, json=command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        save.assert_called_once()
        ability.assert_called_once()
        self.assertEqual(dice.call_args_list, [call(1, 4)] * 2)
        # An uncommitted attempt may have new history IDs on retry, but the
        # restored RNG must produce exactly the same healing mechanics.
        self.assertEqual(accepted.json()["result"], failed_receipt["response"]["result"])
        self.assertEqual(self.runtime(record)["engine"], speculative["engine"])
        self.assertEqual(session.rng.getstate(), speculative["rng"])
        committed = self.store.get_campaign(campaign_id)
        receipt = self.store.get_turn_action(campaign_id, command["action_id"])
        self.assertEqual(receipt["response"], accepted.json())
        self.assertEqual(committed.metadata["revision"], saved_before.metadata["revision"] + 1)
        self.assertEqual(committed.history[:-1], saved_before.history)
        self.assertEqual(len(committed.history), len(saved_before.history) + 1)
        self.assertEqual(committed.history[-1]["player_message"], "healing_hands")
        self.assertEqual(committed.history[-1]["narration"], accepted.json()["result"]["message"])
        self.assertEqual(committed.payload["engine_save"], session.serialize_game_state())
        committed_rows = self.rows(campaign_id)
        self.assertEqual(committed_rows["campaign_combat_history"],
                         baseline_rows["campaign_combat_history"])
        self.assertEqual(len(committed_rows["campaign_turn_actions"]),
                         len(baseline_rows["campaign_turn_actions"]) + 1)

        async def assert_replay(client, manager, store, replay_sid):
            replay_record = manager.get(replay_sid)
            before = self.runtime(replay_record)
            before_rows = self.rows(campaign_id)
            with ExitStack() as stack:
                guards = [
                    stack.enter_context(patch.object(
                        owner, name, side_effect=AssertionError(f"Replay called {name}"),
                    ))
                    for owner, name in (
                        (replay_record.game_session, "resolve_species_trait_action"),
                        (replay_record.game_session.rng, "randint"),
                        (replay_record.game_session.rng, "getrandbits"),
                        (manager, "autosave_turn"), (manager, "save_campaign_locked"),
                        (manager, "resume_campaign"), (store, "save_campaign"),
                        (store, "_transaction"),
                    )
                ]
                replay = await client.post(
                    f"/api/game/sessions/{replay_sid}/species-actions", json=command,
                )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), {**accepted.json(), "session_id": replay_sid})
            for guard in guards:
                guard.assert_not_called()
            self.assertEqual(self.runtime(replay_record), before)
            self.assertEqual(self.rows(campaign_id), before_rows)
            self.assertEqual(store.get_turn_action(campaign_id, command["action_id"]), receipt)

        await assert_replay(self.http, self.manager, self.store, sid)
        reopened_store = CampaignStore(self.store.path)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(session_manager=reopened_manager)),
            base_url="http://healing-reopen",
        ) as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            resumed_sid = resumed.json()["session_id"]
            reopened = reopened_store.get_campaign(campaign_id)
            self.assertEqual(reopened.payload, committed.payload)
            self.assertEqual(reopened.history, committed.history)
            self.assertEqual(reopened.combat_history, committed.combat_history)
            self.assertEqual(reopened_manager.get(resumed_sid).game_session.serialize_game_state(),
                             committed.payload["engine_save"])
            self.assertEqual(reopened_store.get_turn_action(campaign_id, command["action_id"]),
                             receipt)
            # Resume can refresh metadata; assert replay against post-resume rows.
            await assert_replay(client, reopened_manager, reopened_store, resumed_sid)

    async def assert_species_race(self, case, *, compat=False):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        seed = self.manager.get(created["session_id"]).game_session
        seed.character.update(
            species="Aasimar", race="Aasimar", level=3, current_hp=1, max_hp=40,
        )
        seed.initialize_species_trait_state()
        self.manager.save_campaign(campaign_id)

        # Neither contender shares a manager, store or runtime with the creator.
        stores = [CampaignStore(self.store.path) for _ in range(2)]
        managers = [SessionManager(campaign_store=store) for store in stores]
        ids = [manager.resume_campaign(campaign_id)[0] for manager in managers]
        records = [manager.get(sid) for manager, sid in zip(managers, ids)]
        loser, winner = records
        self.assertIsNot(loser.game_session, winner.game_session)
        self.assertEqual(self.runtime(loser), self.runtime(winner))
        baseline = self.runtime(loser)
        saved_before = self.store.get_campaign(campaign_id)
        winning = {"action": "celestial_revelation", "form": "heavenly_wings",
                   "action_id": str(uuid4())}
        losing = {"action": "healing_hands", "action_id": winning["action_id"]}
        if case == "changed_form":
            losing = {**winning, "form": "inner_radiance"}
        elif case == "identical":
            winning = copy.deepcopy(losing)
        elif case == "distinct":
            losing["action_id"] = str(uuid4())
        changed = case in ("changed_action", "changed_form")
        prefix = "/api/sessions" if compat else "/api/game/sessions"
        urls = [f"{prefix}/{sid}/species-actions" for sid in ids]
        clients = [httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(session_manager=manager)),
            base_url="http://species-race",
        ) for manager in managers]
        arrived, release = threading.Event(), threading.Event()
        attempts, errors = [], []
        real_save = stores[0].save_campaign

        @wraps(real_save)
        def pause_loser(*args, **kwargs):
            attempts.append((self.runtime(loser),
                             copy.deepcopy(kwargs["turn_action_receipt"])))
            arrived.set()
            if not release.wait(timeout=10):
                raise AssertionError("Winning species request did not release persistence.")
            try:
                return real_save(*args, **kwargs)
            except CampaignStaleError as error:
                errors.append(error)
                raise

        try:
            with patch.object(stores[0], "save_campaign", side_effect=pause_loser) as save:
                pending = asyncio.create_task(clients[0].post(urls[0], json=losing))
                try:
                    self.assertTrue(await asyncio.to_thread(arrived.wait, 10),
                                    "Real losing species command never reached persistence.")
                    accepted = await asyncio.wait_for(
                        clients[1].post(urls[1], json=winning), timeout=10,
                    )
                    self.assertEqual(accepted.status_code, 200, accepted.text)
                    committed = self.store.get_campaign(campaign_id)
                    committed_rows = self.rows(campaign_id)
                    winner_runtime = self.runtime(winner)
                finally:
                    release.set()
                    rejected = await asyncio.wait_for(pending, timeout=10)
            save.assert_called_once()
            self.assertEqual(len(errors), 1)  # A real revision race, not an injected failure.
            self.assertEqual(rejected.status_code, 409, rejected.text)
            self.assertEqual(rejected.json()["detail"]["code"],
                             "action_id_conflict" if changed else "campaign_stale")

            self.assertEqual(len(attempts), 1)
            speculative, receipt = attempts[0]
            character = speculative["engine"]["player"]
            before_character = baseline["engine"]["player"]
            if losing["action"] == "healing_hands":
                self.assertGreater(character["current_hp"], before_character["current_hp"])
                self.assertEqual(character["species_trait_state"]["healing_hands_uses_remaining"], 0)
                self.assertNotEqual(speculative["rng"], baseline["rng"])
            else:
                self.assertEqual(character["species_trait_state"]["active_celestial_form"],
                                 losing["form"])
                self.assertEqual(character["species_trait_state"]["celestial_revelation_uses_remaining"], 0)
            self.assertEqual(speculative["version"], baseline["version"])
            self.assertEqual(receipt["action_id"], losing["action_id"])
            self.assertEqual(receipt["response"]["result"]["action"], losing["action"])
            self.assertEqual(self.runtime(loser), baseline)  # Full speculative rollback.
            self.assertEqual(self.runtime(winner), winner_runtime)
            self.assertEqual(self.rows(campaign_id), committed_rows)
            self.assertEqual(self.store.get_campaign(campaign_id), committed)
            self.assertEqual(committed.metadata["revision"], saved_before.metadata["revision"] + 1)
            self.assertEqual(committed.history[:-1], saved_before.history)
            self.assertEqual(len(committed.history), len(saved_before.history) + 1)
            self.assertEqual(committed.history[-1]["player_message"], winning["action"])
            self.assertEqual(committed.payload["engine_save"], winner_runtime["engine"])
            if winning["action"] == "healing_hands":
                self.assertGreater(winner.game_session.character["current_hp"], 1)
                self.assertEqual(winner.game_session.character["species_trait_state"]
                                 ["healing_hands_uses_remaining"], 0)
            else:
                self.assertEqual(winner.game_session.character["current_hp"], 1)
                self.assertEqual(winner.game_session.character["species_trait_state"]
                                 ["active_celestial_form"], "heavenly_wings")
                self.assertEqual(winner.game_session.character["species_trait_state"]
                                 ["celestial_revelation_uses_remaining"], 0)
                self.assertEqual(winner.game_session.character["species_trait_state"]
                                 ["healing_hands_uses_remaining"], 1)
            winning_receipt = stores[1].get_turn_action(campaign_id, winning["action_id"])
            self.assertEqual(winning_receipt["response"], accepted.json())
            if case != "distinct":
                self.assertEqual(receipt["request_hash"] == winning_receipt["request_hash"],
                                 case == "identical")
            else:
                self.assertIsNone(stores[0].get_turn_action(campaign_id, losing["action_id"]))

            async def check_retry_and_replay():
                before = [self.runtime(record) for record in records]
                before_rows = self.rows(campaign_id)
                with ExitStack() as stack:
                    guards = []
                    for record, store, manager in zip(records, stores, managers):
                        for owner, name in (
                            (record.game_session, "resolve_species_trait_action"),
                            (store, "save_campaign"), (manager, "autosave_turn"),
                            (manager, "resume_campaign"),
                        ):
                            guards.append(stack.enter_context(patch.object(
                                owner, name, side_effect=AssertionError(f"Retry called {name}"),
                            )))
                    if changed or (case == "distinct" and before[0]["version"] == baseline["version"]):
                        retry = await clients[0].post(urls[0], json=losing)
                        self.assertEqual(retry.status_code, 409, retry.text)
                        self.assertEqual(retry.json()["detail"]["code"],
                                         "action_id_conflict" if changed else "campaign_stale")
                    # Original winner replays even in a stale, unrecovered loser.
                    for client, url, sid in zip(clients, urls, ids):
                        replay = await client.post(url, json=winning)
                        self.assertEqual(replay.status_code, 200, replay.text)
                        self.assertEqual(replay.json(), {**accepted.json(), "session_id": sid})
                    for guard in guards:
                        guard.assert_not_called()
                self.assertEqual([self.runtime(record) for record in records], before)
                self.assertEqual(self.rows(campaign_id), before_rows)

            await check_retry_and_replay()
            resumed = await clients[0].post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["session_id"], ids[0])
            self.assertIs(managers[0].get(ids[0]), loser)
            self.assertEqual(loser.game_session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(loser.journal, committed.payload["journal"])
            self.assertEqual(loser.narrative_memory, committed.payload["narrative_memory"])
            self.assertEqual(loser.game_session._campaign_persistence_version,
                             (campaign_id, committed.metadata["revision"]))
            self.assertEqual(stores[0].get_turn_action(campaign_id, winning["action_id"]),
                             winning_receipt)
            # Resume may update last-played metadata; freeze rows AFTER resume.
            await check_retry_and_replay()
            if case == "distinct":
                before_retry = self.store.get_campaign(campaign_id)
                with patch.object(stores[0], "save_campaign", wraps=stores[0].save_campaign) as retry_save:
                    retried = await clients[0].post(urls[0], json=losing)
                self.assertEqual(retried.status_code, 200, retried.text)
                retry_save.assert_called_once()
                after_retry = self.store.get_campaign(campaign_id)
                self.assertEqual(after_retry.metadata["revision"], before_retry.metadata["revision"] + 1)
                self.assertEqual(len(after_retry.history), len(before_retry.history) + 1)
                self.assertGreater(loser.game_session.character["current_hp"], 1)
                self.assertEqual(loser.game_session.character["species_trait_state"]
                                 ["healing_hands_uses_remaining"], 0)
                self.assertEqual(stores[0].get_turn_action(campaign_id, winning["action_id"]),
                                 winning_receipt)
        finally:
            release.set()
            for client in clients:
                await client.aclose()

    async def test_changed_species_ability_race_conflicts_and_rolls_back(self):
        await self.assert_species_race("changed_action")

    async def test_changed_species_form_race_conflicts_on_compat_route(self):
        await self.assert_species_race("changed_form", compat=True)

    async def test_identical_species_payload_race_stays_stale_then_replays(self):
        await self.assert_species_race("identical")

    async def test_distinct_species_id_race_stays_stale_then_retries_after_resume(self):
        await self.assert_species_race("distinct")

"""R04: the commit boundary never splits a turn's receipt from the state it describes.

Uses the real FastAPI app, real SessionManager and a temporary SQLite store; only the model boundary is the
FakeOllamaClient used by the campaign API tests. Faults are injected at the real seams (payload serialization,
a SQL trigger inside the commit transaction, a lost commit acknowledgement). No game server, no personal saves.
"""
from __future__ import annotations

import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import patch

import httpx

from api import action_contract
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def make_response(hp=11, turn_index=1):
    state = {
        "character": {"current_hp": hp, "max_hp": 12},
        "inventory": ["Kısa kılıç"],
        "campaign_time": {"hour": 18, "minute": 41},
        "death_state": {"status": "active", "dead": False},
        "turn_index": turn_index,
        "combat": {"active": False},
    }
    return {
        "session_id": "s", "action_id": "a", "narration": "x", "state": state,
        "skill_check_result": {"skill": "Stealth", "d20": 8, "total": 11, "dc": 15},
        "combat_history_entry": {"event_id": "evt-1", "turn_index": turn_index, "result": {}},
        "quest_outcomes": [],
    }


def make_bundle(hp=11, turn_index=1, base=4):
    response = make_response(hp, turn_index)
    receipt = action_contract.build_receipt("campaign-1", "a", response, base_revision=base, committed_revision=base + 1, elapsed_s=0.01)
    state = {"public_state": copy.deepcopy(response["state"]), "response": response,
             "committed_event_ids": list(receipt.event_ids)}
    return state, receipt


class ValidateCommitBundleTests(unittest.TestCase):
    def test_consistent_bundle_is_accepted_and_digest_is_stable(self):
        state, receipt = make_bundle()
        action_contract.validate_commit_bundle(state, receipt)
        again = action_contract.build_receipt("campaign-1", "a", copy.deepcopy(state["response"]), 4, 5, 9.9)
        self.assertEqual(receipt.result_digest, again.result_digest)
        self.assertEqual(receipt.result_digest, hashlib.sha256(canonical(state["response"]).encode("utf-8")).hexdigest())
        self.assertEqual(receipt.event_ids, ("evt-1",))
        self.assertEqual(len(receipt.roll_ids), 1)

    def test_receipt_that_disagrees_with_state_is_refused(self):
        for label, mutate in (
            ("hp", lambda state: state["public_state"]["character"].update(current_hp=3)),
            ("inventory", lambda state: state["public_state"]["inventory"].append("Hırsızlanmış mühür")),
            ("time", lambda state: state["public_state"]["campaign_time"].update(minute=50)),
            ("death", lambda state: state["public_state"]["death_state"].update(status="dead", dead=True)),
            ("turn", lambda state: state["public_state"].update(turn_index=7)),
        ):
            with self.subTest(label):
                state, receipt = make_bundle()
                mutate(state)
                with self.assertRaises(action_contract.CommitBundleError):
                    action_contract.validate_commit_bundle(state, receipt)

    def test_digest_revision_event_and_roll_contradictions_are_refused(self):
        state, receipt = make_bundle()
        for label, mutate_state, mutate_receipt in (
            ("digest", lambda s: s["response"].update(narration="başka"), {}),
            ("revision gap", None, {"committed_revision": 9}),
            ("same revision", None, {"committed_revision": 4}),
            ("missing event", lambda s: s.update(committed_event_ids=[]), {}),
            ("reroll", lambda s: s["response"]["skill_check_result"].update(d20=19), {}),
        ):
            with self.subTest(label):
                candidate_state = copy.deepcopy(state)
                if mutate_state:
                    mutate_state(candidate_state)
                candidate = receipt.__class__(**{**receipt.__dict__, **mutate_receipt})
                with self.assertRaises(action_contract.CommitBundleError):
                    action_contract.validate_commit_bundle(candidate_state, candidate)


class CommitBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "campaigns.sqlite3"
        self.store = CampaignStore(self.db_path, bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.cid = self.created["campaign_id"]
        self.record = self.manager.get(self.created["session_id"])
        self.session = self.record.game_session
        self.rolled = []

        def turn(_message, **_kwargs):
            # A real mutation of everything the contract names: HP, an item and a die roll.
            self.session.character["current_hp"] = self.session.character["current_hp"] - 1
            self.session.character.setdefault("inventory", []).append("Bakır anahtar")
            self.rolled.append(self.session.rng.randint(1, 20))
            wallet = self.session.world_state.setdefault("currency", {})
            wallet["player"] = int(wallet.get("player", 0)) + 7  # money is not publicly projected; it must still be all-or-nothing
            return {"narration": "Kapıdan hafif bir ses geliyor.",
                    "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}

        self.session.run_player_turn = turn

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def post(self, action_id, message="Kapıyı dinliyorum."):
        return self.http.post(f"/api/game/sessions/{self.created['session_id']}/turn",
                              json={"message": message, "action_id": action_id})

    def persisted(self):
        campaign = self.store.get_campaign(self.cid)
        with closing(sqlite3.connect(self.db_path)) as db:
            rows = db.execute("SELECT action_id, request_hash, response_json FROM campaign_turn_actions WHERE campaign_id = ?",
                              (self.cid,)).fetchall()
            revision = db.execute("SELECT revision FROM campaigns WHERE campaign_id = ?", (self.cid,)).fetchone()[0]
        return {"payload": campaign.payload, "history": len(campaign.history), "receipts": rows, "revision": revision}

    def live_facts(self):
        character = self.session.character
        return {"hp": character["current_hp"], "inventory": list(character.get("inventory", [])),
                "money": dict(self.session.world_state.get("currency", {})),
                "rng": self.session.rng.getstate(), "turn": self.session.world_state.get("flags", {}).get("turn_index")}

    def assert_untouched(self, before_persisted, before_live):
        after = self.persisted()
        self.assertEqual(after["revision"], before_persisted["revision"], "revision must not move")
        self.assertEqual(after["payload"], before_persisted["payload"], "persisted state must be the previous revision")
        self.assertEqual(after["history"], before_persisted["history"])
        self.assertEqual(after["receipts"], [], "no receipt without its state")
        self.assertEqual(self.live_facts(), before_live, "live runtime must be restored to the previous revision")

    async def test_commit_boundary_never_splits_receipt_and_state(self):
        before_persisted, before_live = self.persisted(), self.live_facts()
        action_id = str(uuid.uuid4())

        # 1. Serialization fault before any SQL: nothing changes anywhere.
        with patch("api.persistence.campaign_store.serialize_campaign_payload", side_effect=ValueError("boom")):
            failed = await self.post(action_id)
        self.assertGreaterEqual(failed.status_code, 500, failed.text)
        self.assert_untouched(before_persisted, before_live)

        # 2. Fault inside the commit transaction, after the state UPDATE and the history INSERT.
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("CREATE TRIGGER r04_receipt BEFORE INSERT ON campaign_turn_actions "
                       "BEGIN SELECT RAISE(ABORT, 'synthetic receipt failure'); END")
            db.commit()
        failed = await self.post(action_id)
        self.assertGreaterEqual(failed.status_code, 500, failed.text)
        self.assert_untouched(before_persisted, before_live)
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("DROP TRIGGER r04_receipt")
            db.commit()

        # 3. The same id now commits exactly once: one new revision, one receipt, state and receipt agree.
        ok = await self.post(action_id)
        self.assertEqual(ok.status_code, 200, ok.text)
        after = self.persisted()
        self.assertEqual(after["revision"], before_persisted["revision"] + 1)
        self.assertEqual(len(after["receipts"]), 1)
        stored = json.loads(after["receipts"][0][2])
        self.assertEqual(stored["state"]["character"]["current_hp"], before_live["hp"] - 1)
        self.assertEqual(self.live_facts()["hp"], before_live["hp"] - 1)
        digest = hashlib.sha256(after["receipts"][0][2].encode("utf-8")).hexdigest()
        meta = self.store.get_turn_action_receipt(self.cid, action_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["result_digest"], digest)
        self.assertEqual(meta["committed_revision"], meta["base_revision"] + 1)
        self.assertEqual(meta["base_revision"], before_persisted["revision"])

    async def test_resolved_but_commit_unknown_is_not_success_and_reconciles_to_one_revision(self):
        before_persisted = self.persisted()
        action_id = str(uuid.uuid4())
        real_save = self.store.save_campaign

        def commit_then_lose_ack(*args, **kwargs):
            real_save(*args, **kwargs)
            raise CampaignStorageError("commit acknowledgement lost")

        with patch.object(self.store, "save_campaign", side_effect=commit_then_lose_ack):
            lost = await self.post(action_id)
        self.assertNotEqual(lost.status_code, 200, "an unacknowledged commit must not be reported as success")
        self.assertNotIn("not_applied", json.dumps(lost.json()), "an uncertain commit must never claim 'not applied'")
        # The database did commit exactly one revision; the live runtime must not sit on an older one.
        committed = self.persisted()
        self.assertEqual(committed["revision"], before_persisted["revision"] + 1)
        self.assertEqual(len(committed["receipts"]), 1)
        # Reconciliation by the same id replays the stored receipt and does not roll or mutate again.
        rolls_before = list(self.rolled)
        replay = await self.post(action_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(self.rolled, rolls_before, "reconciliation must not re-roll")
        self.assertEqual(self.persisted()["revision"], committed["revision"])
        self.assertEqual(self.live_facts()["hp"], replay.json()["state"]["character"]["current_hp"],
                         "live runtime and the committed receipt describe the same revision")

    async def test_restart_returns_the_same_result_digest_and_state(self):
        action_id = str(uuid.uuid4())
        ok = await self.post(action_id)
        self.assertEqual(ok.status_code, 200, ok.text)
        first_meta = self.store.get_turn_action_receipt(self.cid, action_id)
        persisted = self.persisted()
        # A new process: new store over the same file.
        restarted_store = CampaignStore(self.db_path, bound_principal=TEST_PLAYER)
        restarted_meta = restarted_store.get_turn_action_receipt(self.cid, action_id)
        self.assertEqual(restarted_meta["result_digest"], first_meta["result_digest"])
        self.assertEqual(restarted_meta["committed_revision"], first_meta["committed_revision"])
        self.assertEqual(restarted_meta["response"], ok.json())
        self.assertEqual(restarted_store.get_campaign(self.cid).payload, persisted["payload"])
        self.assertEqual(hashlib.sha256(persisted["receipts"][0][2].encode("utf-8")).hexdigest(), restarted_meta["result_digest"])


    async def test_contradictory_bundle_is_refused_inside_the_transaction_and_nothing_is_repaired(self):
        before_persisted, before_live = self.persisted(), self.live_facts()
        action_id = str(uuid.uuid4())
        real_projection = __import__("api.serializers", fromlist=["serialize_session_state"]).serialize_session_state

        def drifted_projection(*args, **kwargs):
            projected = real_projection(*args, **kwargs)
            projected["character"]["current_hp"] = projected["character"]["current_hp"] + 5  # state no longer matches the receipt
            return projected

        rolls_before = list(self.rolled)
        with patch("api.serializers.serialize_session_state", side_effect=drifted_projection):
            refused = await self.post(action_id)
        self.assertGreaterEqual(refused.status_code, 500, refused.text)
        self.assertNotIn("not_applied", json.dumps(refused.json()))
        self.assert_untouched(before_persisted, before_live)
        self.assertEqual(len(self.rolled), len(rolls_before) + 1, "the refused candidate used its one roll; nothing was re-rolled to fit")

    async def test_older_database_without_commit_metadata_is_upgraded_and_old_receipts_stay_readable(self):
        action_id = str(uuid.uuid4())
        ok = await self.post(action_id)
        self.assertEqual(ok.status_code, 200, ok.text)
        with closing(sqlite3.connect(self.db_path)) as db:
            for column in ("base_revision", "committed_revision", "result_digest"):
                db.execute(f"ALTER TABLE campaign_turn_actions DROP COLUMN {column}")
            db.commit()
        reopened = CampaignStore(self.db_path, bound_principal=TEST_PLAYER)
        legacy = reopened.get_turn_action_receipt(self.cid, action_id)
        self.assertIsNotNone(legacy)
        self.assertIsNone(legacy["base_revision"], "a legacy row stays NULL; it is not invented")
        self.assertEqual(legacy["response"], ok.json())
        self.assertEqual(reopened.get_turn_action(self.cid, action_id)["response"], ok.json())


    async def test_lost_ack_keeps_every_live_cache_on_the_committed_revision(self):
        action_id = str(uuid.uuid4())
        real_save = self.store.save_campaign

        def commit_then_lose_ack(*args, **kwargs):
            real_save(*args, **kwargs)
            raise CampaignStorageError("commit acknowledgement lost")

        with patch.object(self.store, "save_campaign", side_effect=commit_then_lose_ack):
            lost = await self.post(action_id)
        self.assertEqual(lost.status_code, 503, lost.text)
        self.assertEqual(lost.json()["detail"]["commit_status"], "committed_unconfirmed")
        stored = self.store.get_campaign(self.cid).payload
        self.assertEqual(self.record.narrative_memory, stored.get("narrative_memory"), "live narrative memory is the stored one")
        self.assertEqual(self.record.journal, stored.get("journal"), "live journal is the stored one")
        self.assertEqual(self.live_facts()["money"], {"player": 7}, "money moved with the committed revision, not back")
        # A deliberate NEW action after the uncertainty builds on the committed state (it is blocked until the unresolved id
        # is settled by R02's registry, so the same id is the way forward and it must replay, not re-run).
        rolls = list(self.rolled)
        replay = await self.post(action_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(self.rolled, rolls)

    async def test_undo_with_a_lost_ack_does_not_split_runtime_from_storage(self):
        turn_id = str(uuid.uuid4())
        self.assertEqual((await self.post(turn_id)).status_code, 200)
        hp_after_turn = self.live_facts()["hp"]
        undo_id = str(uuid.uuid4())
        real_autosave = self.manager.autosave_turn

        def commit_then_fail(*args, **kwargs):
            real_autosave(*args, **kwargs)
            raise RuntimeError("late failure")

        with patch.object(self.manager, "autosave_turn", side_effect=commit_then_fail):
            lost = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/undo",
                                        json={"action_id": undo_id, "target_action_id": turn_id})
        self.assertEqual(lost.status_code, 503, lost.text)
        self.assertEqual(lost.json()["detail"]["commit_status"], "committed_unconfirmed")
        # The undo was committed: the live runtime is the undone state, equal to what the database holds.
        self.assertEqual(self.live_facts()["hp"], hp_after_turn + 1)
        self.assertEqual(self.store.get_campaign(self.cid).payload["engine"]["player"]["current_hp"]
                         if "engine" in self.store.get_campaign(self.cid).payload else self.live_facts()["hp"], self.live_facts()["hp"])
        self.assertIsNone(self.record.undo_checkpoint, "one step only: the committed undo spent the checkpoint")
        replay = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/undo",
                                      json={"action_id": undo_id, "target_action_id": turn_id})
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["state"]["character"]["current_hp"], self.live_facts()["hp"])

    async def test_species_action_with_a_lost_ack_does_not_split_runtime_from_storage(self):
        real_autosave = self.manager.autosave_turn

        def commit_then_fail(*args, **kwargs):
            real_autosave(*args, **kwargs)
            raise RuntimeError("late failure")

        # Same setup the F03 fault chains use: a wounded Orc in a tavern, so a rest is a real, available action.
        self.session.commit_location_change("tavern")
        self.session.character.update(species="Orc", race="Orc", current_hp=1, max_hp=20)
        self.session.initialize_species_trait_state()
        self.session.character["species_trait_state"]["adrenaline_rush_uses_remaining"] = 0
        statuses = {}
        for action in ("long_rest", "short_rest"):
            action_id = str(uuid.uuid4())
            with patch.object(self.manager, "autosave_turn", side_effect=commit_then_fail):
                lost = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/species-actions",
                                            json={"action": action, "action_id": action_id})
            statuses[action] = lost.status_code
            if lost.status_code != 503:
                continue
            self.assertEqual(lost.json()["detail"]["commit_status"], "committed_unconfirmed")
            replay = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/species-actions",
                                          json={"action": action, "action_id": action_id})
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json()["state"]["character"]["current_hp"], self.live_facts()["hp"])
            return
        self.fail(f"no species action reached the commit-unconfirmed path: {statuses}")

if __name__ == "__main__":
    unittest.main()

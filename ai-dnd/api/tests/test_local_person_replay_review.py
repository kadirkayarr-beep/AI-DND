"""Independent HTTP review: same-action_id replay of an accepted local person.

Everything below goes through the real FastAPI turn route, the real
SessionManager/CampaignStore on a temporary SQLite file and the real receipt
table. Only the model is a deterministic stand-in. Not live Qwen, not human play.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import httpx

AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStorageError, CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import PLAYER_A, PLAYER_B

_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()

SEARCH_MESSAGE = "Sahilde bir balıkçı bulup liman söylentilerini onunla konuşmak istiyorum."
DESCRIPTION_MESSAGE = "Yosun lekeli pelerinli balıkçıya selam veriyorum."
CAMPAIGN_START = {"campaign_start": {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}}
ROLE = "kıyı balıkçısı"
PRINCIPALS = {"a": PLAYER_A, "b": PLAYER_B}


class CountingLocalPersonModel:
    """Proposes one local person; resolves a described person only by exact quote."""

    def __init__(self):
        self.force_proposal = True
        self.name = "Neris"
        self.appearance = "Yosun lekeli pelerinli, gümüş sakallı biri"
        self.calls = 0

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.calls += 1
        schema = kwargs.get("format", {})
        properties = schema.get("properties", {})
        npc_ids = properties.get("target", {}).get("properties", {}).get(
            "npc_id", {}
        ).get("enum", [])
        npc_id = next((item for item in npc_ids if item), None)
        target = {
            "type": "npc",
            "reference": ROLE,
            "npc_id": npc_id,
            "evidence_quote": "Yosun lekeli pelerinli balıkçıya",
        }
        if "narration" in properties:
            packet = {
                "intent": "dialogue",
                "action": "dialogue",
                "target": target,
                "completion": "unclear",
                "confidence": 1.0,
                "narration": "Balıkçı selamını sıcak bir baş hareketiyle karşılıyor.",
                "interaction": {
                    "operation": "none",
                    "quote": DESCRIPTION_MESSAGE,
                    "conversation": None,
                },
            }
        elif npc_id is not None and not self.force_proposal:
            packet = {
                "intent": "dialogue",
                "action": "dialogue",
                "target": target,
                "completion": "unclear",
                "confidence": 1.0,
            }
        else:
            packet = {
                "intent": "dialogue",
                "action": "dialogue",
                "target": {"type": "none", "reference": ""},
                "completion": "unclear",
                "confidence": 1.0,
            }
            if "local_person_proposal" in properties:
                packet["local_person_proposal"] = {
                    "name": self.name,
                    "role": ROLE,
                    "appearance": self.appearance,
                    "reason": "Liman söylentilerini biliyor olabilir.",
                }
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


def _without_session(payload):
    trimmed = copy.deepcopy(payload)
    trimmed.pop("session_id", None)
    return trimmed


class LocalPersonReplayReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = (Path(self.tempdir.name) / "campaigns.sqlite3").resolve()
        if self.db_path == _LIVE:
            raise RuntimeError("Refusing to use the live campaign database.")
        self.model = CountingLocalPersonModel()
        self.store, self.manager, self.clients = self._boot()
        self.evidence = []
        evidence_dir = os.environ.get("REPLAY_REVIEW_EVIDENCE_DIR")
        if evidence_dir:
            self.addCleanup(self._write_evidence, Path(evidence_dir))

    def _write_evidence(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{self._testMethodName}.json"
        target.write_text(
            json.dumps(self.evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def _note(self, label, campaign_id, response=None):
        counts = self._db_counts(campaign_id)
        self.evidence.append({
            "step": label,
            "http_status": None if response is None else response.status_code,
            "turn_status": (
                response.json().get("turn_outcome", {}).get("status")
                if response is not None and response.status_code == 200 else None
            ),
            "model_calls_total": self.model.calls,
            "history_rows": counts["history"],
            "receipt_rows": counts["receipts"],
            "stored_local_people": [
                {"id": npc["id"], "name": npc["name"], "appearance": npc["appearance"]}
                for npc in counts["stored_local_people"]
            ],
        })

    def _boot(self):
        """One process: store + manager + one HTTP client per signed-in player."""
        store = CampaignStore(self.db_path)
        manager = SessionManager(campaign_store=store)
        adapter = AuthenticatedOllamaAdapter(self.model)
        clients = {}
        for key, principal in PRINCIPALS.items():
            app = create_app(
                session_manager=manager,
                ollama_adapter=adapter,
                authenticator=FixedAuthenticator(principal),
            )
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://isolated-replay-review",
            )
            self.addAsyncCleanup(client.aclose)
            clients[key] = client
        return store, manager, clients

    async def _create_campaign(self, who="a"):
        response = await self.clients[who].post("/api/game/campaigns", json=CAMPAIGN_START)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def _turn(self, session_id, action_id, message=SEARCH_MESSAGE, who="a", mode="say"):
        return await self.clients[who].post(
            f"/api/game/sessions/{session_id}/turn",
            json={"message": message, "interaction_mode": mode, "action_id": action_id},
        )

    def _db_counts(self, campaign_id):
        connection = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        try:
            history = connection.execute(
                "SELECT COUNT(*) FROM campaign_history WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]
            receipts = connection.execute(
                "SELECT COUNT(*) FROM campaign_turn_actions WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]
            payload = json.loads(connection.execute(
                "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0])
        finally:
            connection.close()
        return {
            "history": history,
            "receipts": receipts,
            "stored_local_people": self._local_people(_stored_npcs(payload)),
        }

    @staticmethod
    def _local_people(npcs):
        return [
            npc for npc in npcs
            if npc.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
            and npc.get("role") == ROLE
        ]

    def _live_people(self, manager, session_id, principal=PLAYER_A):
        return self._local_people(
            manager.get(session_id, principal=principal).game_session.world_state["npcs"]
        )

    async def _accept_first_person(self):
        campaign = await self._create_campaign()
        action_id = str(uuid.uuid4())
        first = await self._turn(campaign["session_id"], action_id)
        self.assertEqual(first.status_code, 200, first.text)
        people = self._live_people(self.manager, campaign["session_id"])
        self.assertEqual(len(people), 1, "setup: the controlled proposal must be accepted")
        self._note("first accepted turn", campaign["campaign_id"], first)
        return campaign, action_id, first.json(), people[0]

    # -- 1: same action_id, same session ------------------------------------------

    async def test_same_action_id_replay_returns_receipt_without_new_work(self):
        campaign, action_id, first, person = await self._accept_first_person()
        session = self.manager.get(campaign["session_id"], principal=PLAYER_A).game_session
        calls_after_first = self.model.calls
        counts_after_first = self._db_counts(campaign["campaign_id"])
        world_after_first = copy.deepcopy(session.serialize_game_state())

        replay = await self._turn(campaign["session_id"], action_id)
        self._note("same action_id replay", campaign["campaign_id"], replay)

        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), first, "replay must be the stored receipt")
        self.assertEqual(self.model.calls, calls_after_first, "replay must not call the model")
        self.assertEqual(self._db_counts(campaign["campaign_id"]), counts_after_first)
        self.assertEqual(counts_after_first["history"], 1)
        self.assertEqual(counts_after_first["receipts"], 1)
        self.assertEqual(
            [npc["id"] for npc in counts_after_first["stored_local_people"]], [person["id"]]
        )
        self.assertEqual(session.serialize_game_state(), world_after_first)

        conflict = await self._turn(
            campaign["session_id"], action_id, message="Limana doğru yürüyorum."
        )
        self._note("same action_id, different message", campaign["campaign_id"], conflict)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
        self.assertEqual(self.model.calls, calls_after_first)
        self.assertEqual(self._db_counts(campaign["campaign_id"]), counts_after_first)

    # -- 2: same action_id after save/resume boundaries -----------------------------

    async def test_same_action_id_replay_survives_http_resume_and_cold_restart(self):
        campaign, action_id, first, person = await self._accept_first_person()
        campaign_id = campaign["campaign_id"]
        calls_after_first = self.model.calls
        counts_after_first = self._db_counts(campaign_id)

        saved = await self.clients["a"].post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        warm = await self.clients["a"].post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(warm.status_code, 200, warm.text)
        # While the campaign is still live, resume hands back the same in-memory
        # session; only the cold boundary below reloads from SQLite.
        warm_session_id = warm.json()["session_id"]
        self.assertEqual(warm_session_id, campaign["session_id"])

        warm_replay = await self._turn(warm_session_id, action_id)
        self._note("replay after HTTP save+resume (same process)", campaign_id, warm_replay)
        self.assertEqual(warm_replay.status_code, 200, warm_replay.text)
        self.assertEqual(_without_session(warm_replay.json()), _without_session(first))
        self.assertEqual(self.model.calls, calls_after_first)

        # Cold boundary: a fresh store, manager and app over the same SQLite file,
        # as after a server restart. Nothing is shared in memory with the first run.
        cold_store, cold_manager, cold_clients = self._boot()
        resumed = await cold_clients["a"].post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        cold_session_id = resumed.json()["session_id"]
        self.assertEqual(
            [npc["id"] for npc in self._live_people(cold_manager, cold_session_id)],
            [person["id"]],
        )
        restored = self._live_people(cold_manager, cold_session_id)[0]
        self.assertEqual(restored["origin_request_key"], person["origin_request_key"])

        cold_replay = await cold_clients["a"].post(
            f"/api/game/sessions/{cold_session_id}/turn",
            json={"message": SEARCH_MESSAGE, "interaction_mode": "say", "action_id": action_id},
        )
        self._note("replay after cold restart + HTTP resume", campaign_id, cold_replay)
        self.assertNotEqual(cold_session_id, campaign["session_id"])
        self.assertEqual(cold_replay.status_code, 200, cold_replay.text)
        self.assertEqual(cold_replay.json()["session_id"], cold_session_id)
        self.assertEqual(_without_session(cold_replay.json()), _without_session(first))
        self.assertEqual(self.model.calls, calls_after_first, "cold replay must not call the model")
        self.assertEqual(self._db_counts(campaign_id), counts_after_first)
        self.assertEqual(len(self._live_people(cold_manager, cold_session_id)), 1)
        del cold_store

    # -- 3: same action_id in another campaign / another player ---------------------

    async def test_same_action_id_elsewhere_never_returns_first_campaign_person(self):
        campaign, action_id, first, person = await self._accept_first_person()
        counts_a = self._db_counts(campaign["campaign_id"])

        missing = await self.clients["b"].post(
            f"/api/game/sessions/{uuid.uuid4().hex}/turn",
            json={"message": SEARCH_MESSAGE, "interaction_mode": "say", "action_id": action_id},
        )
        calls_before_foreign = self.model.calls
        foreign = await self._turn(campaign["session_id"], action_id, who="b")
        self._note("player B posts same action_id to A's session", campaign["campaign_id"], foreign)
        self.assertEqual(foreign.status_code, 404, foreign.text)
        self.assertEqual(foreign.status_code, missing.status_code, foreign.text)
        self.assertEqual(foreign.json(), missing.json())
        self.assertNotIn(person["id"], foreign.text)
        self.assertNotIn(person["name"], foreign.text)
        self.assertEqual(self.model.calls, calls_before_foreign)
        self.assertEqual(self._db_counts(campaign["campaign_id"]), counts_a)

        self.model.name = "Taren"
        self.model.appearance = "Tuz izli önlüklü, kısa saçlı biri"
        for who in ("a", "b"):
            with self.subTest(owner=who):
                other = await self._create_campaign(who)
                self.assertNotEqual(other["campaign_id"], campaign["campaign_id"])
                calls_before = self.model.calls
                response = await self._turn(other["session_id"], action_id, who=who)
                self._note(f"same action_id in new campaign of player {who.upper()}",
                           other["campaign_id"], response)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertGreater(self.model.calls, calls_before, "a fresh campaign runs a fresh turn")
                self.assertEqual(body["session_id"], other["session_id"])
                self.assertEqual(body["turn_outcome"]["status"], "created_local_person")
                # NPC ids are campaign-local sequences, so "npc_001" may repeat;
                # identity is proven by content and the campaign-scoped request key.
                self.assertNotIn(person["name"], response.text)
                self.assertNotIn(person["appearance"], response.text)
                self.assertIn(self.model.appearance, body["narration"])
                self.assertNotEqual(_without_session(body), _without_session(first))
                other_people = self._live_people(
                    self.manager, other["session_id"], principal=PRINCIPALS[who]
                )
                self.assertEqual(len(other_people), 1)
                self.assertEqual(other_people[0]["name"], "Taren")
                self.assertEqual(other_people[0]["appearance"], self.model.appearance)
                self.assertNotEqual(
                    other_people[0]["origin_request_key"], person["origin_request_key"]
                )
                self.assertEqual(self._db_counts(other["campaign_id"])["receipts"], 1)
        self.assertEqual(self._db_counts(campaign["campaign_id"]), counts_a)
        first_people = self._live_people(self.manager, campaign["session_id"])
        self.assertEqual([npc["id"] for npc in first_people], [person["id"]])
        self.assertEqual(first_people[0]["name"], "Neris")
        self.assertEqual(first_people[0]["appearance"], person["appearance"])

    # -- 4: rejected proposal and save failure leave no partial person ---------------

    async def test_rejected_proposal_is_replayed_without_creating_a_person(self):
        campaign = await self._create_campaign()
        session = self.manager.get(campaign["session_id"], principal=PLAYER_A).game_session
        session.world_state["npcs"].append({
            "id": "npc_existing_neris",
            "name": "Neris",
            "role": "liman muhafızı",
            "location": session.world_state["location"],
            "reality_layer": "CANON",
            "knowledge": [],
            "backstory": "",
        })
        npcs_before = copy.deepcopy(session.world_state["npcs"])
        action_id = str(uuid.uuid4())

        rejected = await self._turn(campaign["session_id"], action_id)
        self._note("proposal colliding with canonical Neris", campaign["campaign_id"], rejected)
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["turn_outcome"]["status"], "proposal_rejected")
        self.assertEqual(session.world_state["npcs"], npcs_before)
        calls_after = self.model.calls
        counts_after = self._db_counts(campaign["campaign_id"])
        self.assertEqual(counts_after["stored_local_people"], [])

        replay = await self._turn(campaign["session_id"], action_id)
        self._note("same action_id replay of rejection", campaign["campaign_id"], replay)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), rejected.json())
        self.assertEqual(self.model.calls, calls_after)
        self.assertEqual(self._db_counts(campaign["campaign_id"]), counts_after)

        retry = await self._turn(campaign["session_id"], str(uuid.uuid4()))
        self._note("retry with new action_id", campaign["campaign_id"], retry)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["turn_outcome"]["status"], "proposal_rejected")
        self.assertEqual(session.world_state["npcs"], npcs_before)
        self.assertEqual(self._db_counts(campaign["campaign_id"])["stored_local_people"], [])

    async def test_save_failure_leaves_no_person_and_retry_creates_exactly_one(self):
        campaign = await self._create_campaign()
        campaign_id = campaign["campaign_id"]
        session = self.manager.get(campaign["session_id"], principal=PLAYER_A).game_session
        state_before = copy.deepcopy(session.serialize_game_state())
        counts_before = self._db_counts(campaign_id)
        action_id = str(uuid.uuid4())

        with patch.object(
            self.store, "save_campaign",
            side_effect=CampaignStorageError("synthetic save failure"),
        ):
            failed = await self._turn(campaign["session_id"], action_id)
        self._note("turn with injected save failure", campaign_id, failed)
        self.assertGreaterEqual(failed.status_code, 500, failed.text)
        self.assertNotIn("Neris", failed.text)
        self.assertEqual(session.serialize_game_state(), state_before)
        self.assertEqual(self._live_people(self.manager, campaign["session_id"]), [])
        self.assertEqual(self._db_counts(campaign_id), counts_before)
        self.assertIsNone(self.store.get_turn_action(campaign_id, action_id, principal=PLAYER_A))

        calls_before_retry = self.model.calls
        retry = await self._turn(campaign["session_id"], action_id)
        self._note("retry with same action_id after failure", campaign_id, retry)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["turn_outcome"]["status"], "created_local_person")
        self.assertGreater(self.model.calls, calls_before_retry)
        people = self._live_people(self.manager, campaign["session_id"])
        self.assertEqual(len(people), 1)
        counts_after_retry = self._db_counts(campaign_id)
        self.assertEqual(counts_after_retry["history"], counts_before["history"] + 1)
        self.assertEqual(counts_after_retry["receipts"], counts_before["receipts"] + 1)
        self.assertEqual(
            [npc["id"] for npc in counts_after_retry["stored_local_people"]], [people[0]["id"]]
        )

        calls_after_retry = self.model.calls
        replay = await self._turn(campaign["session_id"], action_id)
        self._note("same action_id replay after successful retry", campaign_id, replay)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(self.model.calls, calls_after_retry)
        self.assertEqual(self._db_counts(campaign_id), counts_after_retry)

        again = await self._turn(campaign["session_id"], str(uuid.uuid4()))
        self._note("same message with new action_id", campaign_id, again)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["turn_outcome"]["status"], "reused_local_person")
        self.assertEqual(
            [npc["id"] for npc in self._live_people(self.manager, campaign["session_id"])],
            [people[0]["id"]],
        )

    # -- 5: later natural description keeps identity across a cold restart -----------

    async def test_later_description_finds_same_person_after_cold_restart(self):
        campaign, _action_id, _first, person = await self._accept_first_person()
        campaign_id = campaign["campaign_id"]
        saved = await self.clients["a"].post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)

        _store, cold_manager, cold_clients = self._boot()
        resumed = await cold_clients["a"].post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        cold_session_id = resumed.json()["session_id"]
        cold_session = cold_manager.get(cold_session_id, principal=PLAYER_A).game_session

        self.model.force_proposal = False
        greet_id = str(uuid.uuid4())
        greet = await cold_clients["a"].post(
            f"/api/game/sessions/{cold_session_id}/turn",
            json={"message": DESCRIPTION_MESSAGE, "interaction_mode": "do", "action_id": greet_id},
        )
        self._note("description-only greeting after cold restart", campaign_id, greet)
        self.assertNotEqual(cold_session_id, campaign["session_id"])
        self.assertEqual(greet.status_code, 200, greet.text)
        self.assertEqual(cold_session.world_state["flags"].get("last_npc_id"), person["id"])
        self.assertEqual(
            [npc["id"] for npc in self._live_people(cold_manager, cold_session_id)],
            [person["id"]],
        )

        self.model.force_proposal = True
        search_again = await cold_clients["a"].post(
            f"/api/game/sessions/{cold_session_id}/turn",
            json={"message": SEARCH_MESSAGE, "interaction_mode": "say", "action_id": str(uuid.uuid4())},
        )
        self._note("original search sentence again after cold restart", campaign_id, search_again)
        self.assertEqual(search_again.status_code, 200, search_again.text)
        self.assertEqual(search_again.json()["turn_outcome"]["status"], "reused_local_person")
        people = self._live_people(cold_manager, cold_session_id)
        self.assertEqual([npc["id"] for npc in people], [person["id"]])
        self.assertEqual(people[0]["name"], person["name"])
        self.assertEqual(people[0]["appearance"], person["appearance"])
        self.assertEqual(
            [npc["id"] for npc in self._db_counts(campaign_id)["stored_local_people"]],
            [person["id"]],
        )


def _stored_npcs(payload):
    npcs = payload["engine_save"]["world_state"]["npcs"]
    assert isinstance(npcs, list), "persisted NPC list has an unexpected shape"
    return npcs


if __name__ == "__main__":
    unittest.main()

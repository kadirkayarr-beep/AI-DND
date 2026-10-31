"""A bad model reply must never lock a campaign.

Real FastAPI app, real adapter, real engine, real SQLite store; only the Ollama client is scripted. It answers every
call well unless a test arms one fault on one kind of call. The first failing shape comes from a real 20-turn play run:
the classifier repeated one id until the token cap, the turn answered 503 and every later turn of the campaign 409.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
import uuid

import httpx

import game
import interaction_adventure
from api.auth import FixedAuthenticator
from api.identity_suggestion import IdentitySuggestionService
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER

START = {"campaign_start": {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}}
LOOPING_CLASSIFIER_REPLY = (
    '{"intent": "dialogue", "action": "interact", "target": {"type": "none", "reference": ""}, '
    '"completion": "unclear", "confidence": 0.9, "interaction": {"operation": "information", '
    '"quote": "Buralarda koruma arayan bir soylu biliyor musun?", "thread_id": null, "evidence_id": null, '
    '"conversation": {"addressee_id": "npc_002", "candidate_evidence_ids": ["npc_002_appearance'
    + "_001" * 300
)
SPEECH_TURN = "Yakınımdaki birine yaklaşıyorum. Selamlar, ismin nedir?"
CLASSIFIER_TURN = "Yerdeki taşı alıp duvara fırlatıyorum."
GROUNDED_TURN = "İçeri girip tezgâha geçiyorum, bir bira istiyorum."
FREE_TURN = "Çevremi gözlemliyorum."
CALLS = (
    ("classifier", CLASSIFIER_TURN),
    ("grounded_classifier", GROUNDED_TURN),
    ("speech", SPEECH_TURN),
    ("narration", CLASSIFIER_TURN),
)
FAULTS = (
    ("truncated", '{"spoken_text": "' + "_001" * 300),
    ("garbage", "bu bir json degil"),
    ("empty", ""),
    ("timeout", TimeoutError("slow")),
    ("connection", ConnectionError("gone")),
)


def kind_of(schema):
    keys = set((schema or {}).get("properties", {})) if isinstance(schema, dict) else set()
    if "spoken_text" in keys:
        return "speech"
    if "narration" in keys:
        return "narration"
    if "steps" in keys:
        return "grounded_classifier"
    if "intent" in keys:
        return "classifier"
    return "other"


class ScriptedModel:
    """Answers every call well; `fault` (kind, reply-or-exception, times) overrides calls of one kind."""

    def __init__(self):
        self.kinds = []
        self.fault = None

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def arm(self, kind, reply, times=1):
        self.fault = [kind, reply, times]

    def chat(self, *_args, **kwargs):
        kind = kind_of(kwargs.get("format"))
        self.kinds.append(kind)
        if self.fault is not None and self.fault[0] == kind and self.fault[2] > 0:
            self.fault[2] -= 1
            if isinstance(self.fault[1], Exception):
                raise self.fault[1]
            return {"message": {"content": self.fault[1]}, "done_reason": "length"}
        return {"message": {"content": json.dumps(self.good(kind), ensure_ascii=False)}, "done_reason": "stop"}

    @staticmethod
    def good(kind):
        if kind == "speech":
            return {"spoken_text": "Selam, yabancı.", "stage_direction": ""}
        if kind == "narration":
            return {"narration": "Sokak akmaya devam ediyor.", "world_updates": {}, "lore_claims": []}
        if kind == "grounded_classifier":
            return {"steps": []}
        return {"intent": "narrative", "action": "narrative", "target": {"type": "none", "reference": ""},
                "completion": "unclear", "confidence": 0.5,
                "interaction": {"operation": "none", "quote": ""}}


class PlayFixture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = CampaignStore(
            Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER,
        )
        self.model = ScriptedModel()
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(self.model)
        self.enterContext(adapter.engine_binding())
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(
                session_manager=self.manager, ollama_adapter=adapter, authenticator=FixedAuthenticator(TEST_PLAYER),
            )),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.http.aclose)
        created = await self.http.post("/api/game/campaigns", json=START)
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign_id = created.json()["campaign_id"]
        self.session_id = created.json()["session_id"]

    def body(self, text):
        return {"message": text, "action_id": str(uuid.uuid4())}

    def turn(self, body):
        return self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)

    def saved(self):
        return self.store.get_campaign(self.campaign_id)


class RunSixReproduction(PlayFixture):
    async def test_the_looping_classifier_reply_does_not_block_the_next_turn(self):
        await self.turn(self.body(SPEECH_TURN))
        self.model.arm("classifier", LOOPING_CLASSIFIER_REPLY)
        failed = await self.turn(self.body("Buralarda koruma arayan bir soylu biliyor musun?"))
        self.assertEqual(failed.status_code, 503, failed.text)
        following = await self.turn(self.body(FREE_TURN))
        self.assertEqual(following.status_code, 200, following.text)


class EveryModelCallFailsSoftly(PlayFixture):
    """Each model call, each way it can go wrong, through the real route."""

    async def fresh_campaign(self):
        created = await self.http.post("/api/game/campaigns", json=START)
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign_id = created.json()["campaign_id"]
        self.session_id = created.json()["session_id"]

    def assert_natural(self, response):
        detail = response.json()["detail"]
        self.assertIs(detail.get("not_applied"), True, response.text)
        self.assertRegex(detail["message"], r"[ığüşöçİ]", "the player reads Turkish")
        self.assertNotRegex(
            detail["message"].casefold(),
            r"ollama|model|intent|json|api|server|sunucu|parsing|commit|npc|yapay",
            "the player never reads machinery",
        )
        self.assertLess(len(detail["message"]), 120, "short")

    async def assert_untouched(self, before_history, before_engine, before_live):
        saved = self.saved()
        self.assertEqual(len(saved.history), before_history)
        self.assertEqual(saved.payload["engine_save"], before_engine)
        self.assertEqual(self.manager.get(self.session_id).game_session.serialize_game_state(), before_live)
        unresolved = await self.http.get(f"/api/game/sessions/{self.session_id}/actions/unresolved")
        self.assertIsNone(unresolved.json()["unresolved"])

    async def test_a_new_move_after_any_failure_works_and_nothing_was_half_committed(self):
        for kind, text in CALLS:
            for name, fault in FAULTS:
                with self.subTest(call=kind, fault=name):
                    await self.fresh_campaign()
                    live = self.manager.get(self.session_id).game_session
                    before = (len(self.saved().history), self.saved().payload["engine_save"], live.serialize_game_state())
                    self.model.arm(kind, fault)
                    first = await self.turn(self.body(text))
                    self.assertIn(first.status_code, (200, 503), first.text)
                    if first.status_code == 503:
                        self.assert_natural(first)
                        await self.assert_untouched(*before)
                    following = await self.turn(self.body(FREE_TURN))
                    self.assertEqual(following.status_code, 200, following.text)

    async def test_retrying_the_same_action_id_applies_once(self):
        for kind, text in CALLS:
            for name, fault in FAULTS:
                with self.subTest(call=kind, fault=name):
                    await self.fresh_campaign()
                    history = len(self.saved().history)
                    self.model.arm(kind, fault)
                    body = self.body(text)
                    first = await self.turn(body)
                    retry = await self.turn(body)
                    self.assertEqual(retry.status_code, 200, retry.text)
                    self.assertEqual(len(self.saved().history), history + 1, "one move, one history entry")
                    replay = await self.turn(body)
                    self.assertEqual(replay.json(), retry.json(), "the receipt answers, nothing runs again")
                    self.assertEqual(len(self.saved().history), history + 1)
                    if first.status_code == 200:
                        self.assertEqual(retry.json(), first.json())

    async def test_a_model_that_keeps_failing_never_locks_and_play_resumes(self):
        self.model.arm("classifier", LOOPING_CLASSIFIER_REPLY, times=3)
        for _ in range(3):
            response = await self.turn(self.body(CLASSIFIER_TURN))
            self.assertEqual(response.status_code, 503, response.text)
            self.assert_natural(response)
        self.assertEqual(len(self.saved().history), 0)
        self.assertEqual((await self.turn(self.body(CLASSIFIER_TURN))).status_code, 200)

    async def test_an_ollama_outage_found_before_the_turn_does_not_lock_either(self):
        healthy = self.model.list

        def down():
            raise ConnectionError("down")

        self.model.list = down
        failed = await self.turn(self.body(CLASSIFIER_TURN))
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()["detail"]["code"], "ollama_unavailable")
        self.assert_natural(failed)
        self.model.list = healthy
        following = await self.turn(self.body(FREE_TURN))
        self.assertEqual(following.status_code, 200, following.text)

    async def test_a_saved_receipt_is_never_released(self):
        body = self.body(FREE_TURN)
        applied = await self.turn(body)
        self.assertEqual(applied.status_code, 200, applied.text)
        record = self.manager.get(self.session_id)
        self.assertFalse(self.manager.release_action_intent(record, body["action_id"], "0" * 64))
        self.assertEqual((await self.turn(body)).json(), applied.json())


class ClassifierSchemaHasNoRoomToLoop(unittest.TestCase):
    """The loop in the real run was one id growing inside a string: the list already had maxItems, the string had nothing."""

    def unbounded(self, node, path="$"):
        found = []
        if isinstance(node, dict):
            kinds = node.get("type")
            if kinds == "string" and "maxLength" not in node and "enum" not in node and "const" not in node:
                found.append(path)
            if kinds == "array" and "maxItems" not in node:
                found.append(path)
            for key, value in node.items():
                found += self.unbounded(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                found += self.unbounded(value, f"{path}[{index}]")
        return found

    def test_every_free_string_and_list_the_classifier_can_fill_has_a_limit(self):
        for require_conversation in (False, True):
            schema = interaction_adventure.intent_schema(game.INTENT_SCHEMA, require_conversation=require_conversation)
            self.assertEqual(self.unbounded(schema), [])

    def test_a_real_evidence_id_still_fits(self):
        proposal = interaction_adventure.ConversationProposal.model_validate({
            "candidate_evidence_ids": ["npc-profile:npc_procedural_0123456789:v1:reason_for_being_here"],
        })
        self.assertEqual(len(proposal.candidate_evidence_ids), 1)


class IdentitySuggestionFailure(unittest.IsolatedAsyncioTestCase):
    async def test_a_failing_identity_model_touches_no_turn(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = CampaignStore(Path(directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        model = ScriptedModel()
        adapter = AuthenticatedOllamaAdapter(model)
        self.enterContext(adapter.engine_binding())

        def provider(_prompt):
            raise TimeoutError("slow")

        http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(
                session_manager=SessionManager(campaign_store=store), ollama_adapter=adapter,
                authenticator=FixedAuthenticator(TEST_PLAYER),
                identity_suggestions=IdentitySuggestionService(provider, timeout_seconds=2),
            )),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(http.aclose)
        created = await http.post("/api/game/campaigns", json=START)
        session_id = created.json()["session_id"]
        job = await http.post("/api/game/character-identity-suggestions", json={
            "draft_id": "draft-1", "field": "personality", "request_id": "request-1",
            "input_revision": 1, "current_text": "Sakin.", "locked": False,
        })
        self.assertEqual(job.status_code, 200, job.text)
        for _ in range(200):
            state = (await http.get("/api/game/character-identity-suggestions/request-1")).json()
            if state["status"] not in ("queued", "running"):
                break
            await asyncio.sleep(0.01)
        self.assertNotIn(state["status"], ("queued", "running", "ready"), state)
        turn = await http.post(f"/api/game/sessions/{session_id}/turn", json={
            "message": FREE_TURN, "action_id": str(uuid.uuid4()),
        })
        self.assertEqual(turn.status_code, 200, turn.text)


if __name__ == "__main__":
    unittest.main()

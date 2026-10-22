"""NPC first-fix package: conversation-cut diagnosis and safety boundaries.

A scripted model returns safe, in-character replies. The tests record per-turn
telemetry. They do not close the original plan's context, repair, shadow, or
cleanup stages. Records are written as JSON when NPC_STAGE_A_EVIDENCE_DIR is
set. Not live Qwen, not human acceptance.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest
import uuid
from unittest.mock import patch

AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import tempfile

import httpx

from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
import game
import living_world

from api.tests import test_campaign_api
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import create_city_with_locked_tavern

PROTECTED_FIELDS = ("current_hp", "max_hp", "xp", "level", "inventory", "spell_slots_remaining")

CAMPAIGN_START = {"campaign_start": {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}}
CITY = "fr:city:neverwinter"

# Scripted "good model" replies, keyed by a distinctive substring of the input.
REPLIES = [
    ("sıcak bir yemek", "Marek: “Adım Marek. Şehirdeki han kısa bir mola için sakin bir yer; sıcak yemek de bulunur.”"),
    ("seviyor musun", "Marek: “Severim; sohbet insanı dinç tutuyor.”"),
    ("dinlemeyi mi", "Marek: “İkisi de; yerine göre konuşur, yerine göre dinlerim.”"),
    ("dın nedir", "Marek: “Adım Marek.”"),
    ("İsmini öğrenebilir", "Marek: “Adım Marek. Şehirdeki han kısa bir mola için sakin bir yer.”"),
    ("sessizliği mi seversin", "Marek: “Muhabbeti severim; nöbet uzun sürüyor.”"),
    ("arabaları neden kontrol", "Marek: “Arabaları kapıdaki sayım için durduruyoruz; bugün benim görevim bu.”"),
    ("Adınız nedir", "Marek: “Adım Marek. Pazar girişinde görevliyim.”"),
    ("han tavsiye", "Marek: “Şehirdeki han kısa bir mola için sakin bir yer.”"),
    ("kralın yarın", "Marek: “Onu bilmiyorum; saray işleri bize söylenmez.”"),
    ("tercih edersin", "Marek: “Dinlenirken biraz sohbeti severim; insan günü unutuyor.”"),
    ("yemek de var mı", "Marek: “Handa sıcak yemek de olur.”"),
    ("görevliyim", "Marek: “Adım Marek. Pazar girişinde görevliyim.”"),
]
DEFAULT_REPLY = "Marek: “Burada görevliyim; bugün pazar sakin.”"
AGENCY_REPLY = "Marek gülümsüyor. Kapıyı açıp içeri giriyorsun ve masaya oturuyorsun."
GOLD_REPLY = "Marek: “Al, sana 100 altın verdim; han da senin oldu.”"
LEAK_REPLY = "Marek: “Saklanan Veyra her şeyi biliyor; gizli geçidi de o kullanıyor.”"
WRONG_SPEAKER_REPLY = "Taren: “Ben Taren, buranın asıl muhafızıyım.”"
FAKE_ACTION_REPLY = "Marek kapıyı açtı ve hanın anahtarını sana verdi."
CLAIM_CONFIRM_REPLY = "Marek: “Evet, geçen sefer hanın anahtarını sana vermiştim. Adım Marek.”"


class ScriptedNpcModel(test_campaign_api.FakeOllamaClient):
    def __init__(self, npc_id, mode="good"):
        self.npc_id = npc_id
        self.mode = mode
        self.calls = 0
        self.last_user_prompt = ""

    def chat(self, *args, **kwargs):
        self.calls += 1
        schema = kwargs.get("format", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        messages = kwargs.get("messages", [])
        prompt = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        self.last_user_prompt = prompt
        player_text = prompt.rsplit("Current player message: ", 1)[-1].splitlines()[0] \
            if "Current player message: " in prompt else prompt
        if "intent" in properties and "narration" not in properties:
            packet = {
                "intent": "dialogue",
                "action": "dialogue",
                "target": {"type": "none", "reference": ""},
                "completion": "unclear",
                "confidence": 1.0,
            }
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        if self.mode == "agency":
            narration = AGENCY_REPLY
        elif self.mode == "gold":
            narration = GOLD_REPLY
        elif self.mode == "leak":
            narration = LEAK_REPLY
        elif self.mode == "wrong_speaker":
            narration = WRONG_SPEAKER_REPLY
        elif self.mode == "fake_action":
            narration = FAKE_ACTION_REPLY
        elif self.mode == "claim_confirm":
            narration = CLAIM_CONFIRM_REPLY
        elif self.mode == "fake_drop":
            narration = "Marek: “Hanın anahtarını sana bıraktım.”"
        elif self.mode == "wrong_speaker_unlabelled":
            narration = "Marek: “Ben Taren, buranın asıl muhafızıyım.”"
        elif self.mode == "metaphor":
            narration = "Marek: “Sana kalbimin anahtarını verdim.”"
        elif self.mode == "name_unknown":
            narration = "Marek: “Adım Marek. Kralın yarın ne yapacağını bilmiyorum.”"
        elif self.mode == "name_only":
            narration = "Marek: “Adım Marek.”"
        else:
            narration = next(
                (text for key, text in REPLIES if key in player_text), DEFAULT_REPLY
            )
        packet = {
            "intent": "dialogue",
            "action": "dialogue",
            "target": {"type": "none", "reference": ""},
            "completion": "unclear",
            "confidence": 1.0,
            "narration": narration,
            "world_updates": {},
            "lore_claims": [],
            "interaction": {
                "operation": "none",
                "quote": player_text,
                "conversation": None,
            },
        }
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


def _guard(npc_id="npc_stage_a_guard"):
    return {
        "id": npc_id,
        "name": "Marek",
        "role": "guard",
        "role_known_to_player": True,
        "appearance": "Pazar girişinde mavi pelerinli bir muhafız.",
        "location": CITY,
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "personal_profile": {},
        "knowledge": [],
        "status": "active",
        "combat_status": "active",
        "current_hp": 12,
        "memory": [],
    }


class StageADiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = CampaignStore(
            Path(self.temporary_directory.name) / "campaigns.sqlite3",
            bound_principal=TEST_PLAYER,
        )
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(test_campaign_api.FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.http.aclose)
        self.records = []
        evidence_dir = os.environ.get("NPC_STAGE_A_EVIDENCE_DIR")
        if evidence_dir:
            self.addCleanup(self._write_evidence, Path(evidence_dir))

    def _write_evidence(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{self._testMethodName}.json"
        target.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    async def post_scene_turn(self, url, model, body):
        with (
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("External network is disabled in this API test."),
            ),
            patch.object(self.app.state.ollama_adapter, "_client", model),
        ):
            return await self.http.post(url, json=body)

    def _focus(self, session, npc):
        flags = session.world_state["flags"]
        flags["last_npc_id"] = npc["id"]
        flags["active_npc_id"] = npc["id"]
        flags["active_npc_until_turn"] = flags.get("turn_index", 0) + 8

    async def _plain_city_session(self):
        created = await self.http.post("/api/game/campaigns", json=CAMPAIGN_START)
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        session = self.manager.get(session_id).game_session
        return session_id, session, f"/api/game/sessions/{session_id}/turn"

    async def _focused_guard(self, npc_id="npc_stage_a_guard"):
        _sid, session, turn_url = await self._plain_city_session()
        guard = _guard(npc_id)
        session.world_state["npcs"].append(guard)
        self._focus(session, guard)
        return session, turn_url, guard

    async def _say(self, label, session, turn_url, npc_id, message, mode="good",
                   interaction_mode="say"):
        model = ScriptedNpcModel(npc_id, mode=mode)
        captured = {}
        real_turn = session.run_player_turn

        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            captured["result"] = copy.deepcopy(result)
            return result

        character_before = copy.deepcopy(session.character)
        protected_before = {key: copy.deepcopy(session.character.get(key)) for key in PROTECTED_FIELDS}
        started = time.perf_counter()
        with patch.object(session, "run_player_turn", new=capture_turn):
            response = await self.post_scene_turn(turn_url, model, {
                "message": message,
                "interaction_mode": interaction_mode,
                "action_id": str(uuid.uuid4()),
            })
        latency_ms = round((time.perf_counter() - started) * 1000)
        self.assertEqual(response.status_code, 200, response.text)
        result = captured.get("result", {})
        action = result.get("action_result", {}) if isinstance(result, dict) else {}
        evidence = result.get("_engine_event_evidence", {}) if isinstance(result, dict) else {}
        record = {
            "step": label,
            "input": message,
            "interaction_mode": interaction_mode,
            "npc_speech_env": os.environ.get("AI_DND_NPC_SPEECH", "<unset>"),
            "http_status": response.status_code,
            "narration": response.json().get("narration", "")[:300],
            "turn_outcome": response.json().get("turn_outcome"),
            "action": action.get("action"),
            "action_status": action.get("status"),
            "npc_id": action.get("npc_id"),
            "state_changes": action.get("state_changes"),
            "telemetry": evidence.get("telemetry"),
            "client_chat_calls": model.calls,
            "model_saw_full_input": message in model.last_user_prompt,
            "result_model_calls": result.get("model_calls") if isinstance(result, dict) else None,
            "latency_ms": latency_ms,
            "character_unchanged": session.character == character_before,
            "character_diff_keys": sorted(
                key for key in set(character_before) | set(session.character)
                if character_before.get(key) != session.character.get(key)
            ),
            "protected_fields_unchanged": all(
                session.character.get(key) == value
                for key, value in protected_before.items()
            ),
            "npc_count": len(session.world_state["npcs"]),
            "location_count": len(session.world_state["locations"]),
        }
        self.records.append(record)
        return record

    async def test_guard_scene_with_known_locked_tavern(self):
        _city, _sid, session, turn_url, _tavern, _door = \
            await create_city_with_locked_tavern(self)
        # The discovery turn may already have placed a scene guard; reuse it so
        # the description "muhafız" cannot match two people.
        guard = next(
            (npc for npc in session.world_state["npcs"]
             if isinstance(npc, dict) and "guard" in str(npc.get("role", "")).casefold()),
            None,
        )
        if guard is None:
            guard = _guard()
            session.world_state["npcs"].append(guard)
        else:
            guard["name"] = "Marek"
            guard.setdefault("knowledge", [])
            guard.setdefault("memory", [])
        # Keep exactly one person in the scene so the description is unambiguous.
        session.world_state["npcs"] = [guard]
        self._focus(session, guard)

        await self._say(
            "A1 look-around (old irrelevant-claim rejection)", session, turn_url,
            guard["id"],
            "Etrafıma dikkatlice bakıyorum. Yakınımdaki insanları, dükkânları ve yolları gözden geçiriyorum.",
            interaction_mode="do",
        )
        await self._say(
            "A2 approach guard and ask why cars are checked", session, turn_url,
            guard["id"],
            "Pazar girişindeki muhafıza yaklaşıyorum: Merhaba, şehre yeni geldim. Bugün arabaları neden kontrol ediyorsunuz?",
        )
        await self._say(
            "A2b clarify by name, then ask why cars are checked", session,
            turn_url, guard["id"],
            "Marek'i kastediyorum. Bugün arabaları neden kontrol ediyorsunuz?",
        )
        await self._say(
            "A3 multi-part: name + inn recommendation (tavern exists, locked)",
            session, turn_url, guard["id"],
            "Anladım. Adınız nedir? Şehirde sakin bir yerde oturup sıcak bir yemek yiyebileceğim bir han tavsiye eder misiniz?",
        )
        await self._say(
            "A4 follow-up on the inn topic", session, turn_url, guard["id"],
            "Peki orada yemek de var mı?",
        )
        for record in self.records:
            self.assertTrue(record["protected_fields_unchanged"], record)

    async def test_guard_scene_without_any_inn(self):
        _sid, session, turn_url = await self._plain_city_session()
        guard = _guard()
        session.world_state["npcs"].append(guard)
        self._focus(session, guard)
        self.assertFalse(any(
            loc.get("scene_kind") == "tavern"
            for loc in session.world_state["locations"].values()
            if isinstance(loc, dict)
        ))

        await self._say(
            "B1 ask the guard for an inn where none exists yet", session, turn_url,
            guard["id"], "Marek, yakınlarda bildiğin bir han var mı?",
        )
        await self._say(
            "B2 genuinely unknown distant fact", session, turn_url, guard["id"],
            "Kralın yarın ne yapacağını biliyor musun?",
        )
        knowledge_before = copy.deepcopy(guard["knowledge"])
        combined = await self._say(
            "B3 multi-part: answerable name + unknown royal plan", session,
            turn_url, guard["id"],
            "Adın nedir? Bir de kralın yarınki planını söyler misin?",
            mode="name_unknown",
        )
        self.assertTrue(combined["model_saw_full_input"], combined)
        self.assertIn("adım marek", combined["narration"].casefold())
        self.assertIn("bilmiyorum", combined["narration"].casefold())
        self.assertEqual(combined["state_changes"], [])
        self.assertEqual(guard["knowledge"], knowledge_before)
        for record in self.records:
            self.assertTrue(record["protected_fields_unchanged"], record)

    async def test_partial_reply_probe_reports_completion_status(self):
        session, turn_url, guard = await self._focused_guard()
        record = await self._say(
            "partial two-part answer probe",
            session,
            turn_url,
            guard["id"],
            "Adın nedir? Bir de kralın yarınki planını söyler misin?",
            mode="name_only",
        )
        self.assertTrue(record["model_saw_full_input"], record)
        self.assertIn("adım marek", record["narration"].casefold(), record)
        self.assertNotIn("bilmiyorum", record["narration"].casefold())
        self.assertNotIn("kral", record["narration"].casefold(), record)
        record["answer_completeness"] = "incomplete"
        print(
            "PARTIAL_TWO_PART_REPLY_STATUS=incomplete"
            f"; engine_turn_status={record['action_status']}; narration={record['narration']}"
        )

    async def test_smalltalk_preference_and_personal_questions(self):
        _sid, session, turn_url = await self._plain_city_session()
        guard = _guard()
        session.world_state["npcs"].append(guard)
        self._focus(session, guard)

        await self._say(
            "C1 preference question (Elaris pattern)", session, turn_url,
            guard["id"],
            "Dinlenirken yalnız kalmayı mı, sohbet etmeyi mi tercih edersin?",
            interaction_mode="do",
        )
        await self._say(
            "C2 what did you do today", session, turn_url, guard["id"],
            "Bugün neler yaptın?", interaction_mode="do",
        )
        await self._say(
            "C3 how is your day", session, turn_url, guard["id"],
            "Günün nasıl geçiyor?", interaction_mode="do",
        )
        for record in self.records:
            self.assertTrue(record["protected_fields_unchanged"], record)

    async def test_smalltalk_preference_with_speech_flag_enabled(self):
        _sid, session, turn_url = await self._plain_city_session()
        guard = _guard()
        session.world_state["npcs"].append(guard)
        self._focus(session, guard)

        with patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "1"}):
            await self._say(
                "E1 preference question, speech=1, mode=do", session,
                turn_url, guard["id"],
                "Dinlenirken yalnız kalmayı mı, sohbet etmeyi mi tercih edersin?",
                interaction_mode="do",
            )
            await self._say(
                "E2 preference question, speech=1, mode=say", session,
                turn_url, guard["id"],
                "Dinlenirken yalnız kalmayı mı, sohbet etmeyi mi tercih edersin?",
                interaction_mode="say",
            )
        for record in self.records:
            self.assertTrue(record["protected_fields_unchanged"], record)

    async def test_unseen_phrasings(self):
        _sid, session, turn_url = await self._plain_city_session()
        guard = _guard()
        session.world_state["npcs"].append(guard)
        self._focus(session, guard)

        await self._say(
            "F1 unseen preference paraphrase", session, turn_url, guard["id"],
            "Sohbet ederken sessizliği mi seversin, muhabbeti mi?",
            interaction_mode="do",
        )
        await self._say(
            "F2 unseen multi-part: name + a place to stay", session, turn_url,
            guard["id"],
            "İsmini öğrenebilir miyim? Bir de bu şehirde kalınacak sakin bir yer bilir misin?",
        )
        await self._say(
            "F3 unseen personal follow-up", session, turn_url, guard["id"],
            "Bugün işler nasıldı?", interaction_mode="do",
        )
        for record in self.records:
            self.assertTrue(record["protected_fields_unchanged"], record)

    async def test_conversation_start_vs_real_question(self):
        _sid, session, turn_url = await self._plain_city_session()
        guard = _guard()
        session.world_state["npcs"].append(guard)
        self._focus(session, guard)

        openings = [
            "Sohbet edelim mi?",
            "Biraz sohbet edelim.",
            "Marek ile konuşmak istiyorum.",
        ]
        for index, message in enumerate(openings):
            record = await self._say(
                f"H{index + 1} opening: {message}", session, turn_url,
                guard["id"], message, interaction_mode="do",
            )
            self.assertEqual(record["action_status"], "conversation_started", record)

        questions = [
            "Sohbet etmeyi seviyor musun?",
            "Konuşmayı mı seversin, dinlemeyi mi?",
            "Dinlenirken yalnız kalmayı mı, sohbet etmeyi mi tercih edersin?",
        ]
        for index, message in enumerate(questions):
            record = await self._say(
                f"H{index + 4} real question: {message}", session, turn_url,
                guard["id"], message, interaction_mode="do",
            )
            self.assertNotEqual(record["action_status"], "conversation_started", record)
            self.assertNotIn("Seni dinliyorum", record["narration"], record)

        # A real opening may share a turn with an answerable question; the
        # opening must not consume the second clause.
        record = await self._say(
            "H7 opening followed by a real question", session, turn_url,
            guard["id"], "Biraz sohbet edelim. Adın nedir?",
            interaction_mode="do",
        )
        self.assertNotEqual(record["action_status"], "conversation_started", record)
        self.assertTrue(
            "marek" in record["narration"].casefold(),
            record,
        )

    async def test_opening_plus_why_question_is_answered(self):
        _sid, session, turn_url = await self._plain_city_session()
        guard = _guard()
        guard["personal_profile"] = {
            "reason_for_being_here": "Kervan yolundaki haberleri topluyorum."
        }
        session.world_state["npcs"].append(guard)
        self._focus(session, guard)
        record = await self._say(
            "H8 opening plus why question",
            session,
            turn_url,
            guard["id"],
            "Biraz sohbet edelim. Peki buraya neden geldin?",
            interaction_mode="do",
        )
        self.assertEqual(
            game.local_dialogue.personal_question_kind(
                "Peki buraya neden geldin?"
            ),
            "reason_for_being_here",
        )
        self.assertNotEqual(record["action_status"], "conversation_started", record)
        self.assertTrue(record["model_saw_full_input"], record)
        self.assertNotIn("Seni dinliyorum", record["narration"], record)

    async def test_sit_attribute_vs_real_sit_action(self):
        attribute = (
            "Anladım. Adınız nedir? Şehirde sakin bir yerde oturup sıcak bir "
            "yemek yiyebileceğim bir han tavsiye eder misiniz?"
        )
        self.assertNotEqual(living_world.classify_scene_action(attribute), "sit")
        self.assertEqual(
            living_world.classify_scene_action("Sandalyeye oturuyorum."),
            "sit",
        )

        session, turn_url, guard = await self._focused_guard()
        real = await self._say(
            "G1 ask the guard and sit on a chair (real compound action)",
            session, turn_url, guard["id"],
            "Muhafıza soruyorum ve sandalyeye oturuyorum.",
            interaction_mode="do",
        )
        self.assertNotEqual(real["action"], "dialogue", real)
        for record in self.records:
            self.assertTrue(record["protected_fields_unchanged"], record)

    async def test_unrelated_item_or_door_change_does_not_authorize_dialogue_claims(self):
        session, _turn_url, guard = await self._focused_guard()
        token = game._ACTIVE_SESSION.set(session)
        try:
            transfer = game._narration_safety_decision(
                "Marek: “Sana hanın anahtarını verdim.”",
                "Marek, yakınlarda bildiğin bir han var mı?",
                npc_target=guard,
                action_result={
                    "action": "dialogue",
                    "state_changes": ["items.coin"],
                },
            )
            door = game._narration_safety_decision(
                "Marek kapıyı açtı.",
                "Marek, kapıyı açtın mı?",
                npc_target=guard,
                action_result={
                    "action": "dialogue",
                    "state_changes": ["doors.unrelated_door.open"],
                },
            )
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(transfer["reason_code"], "UNVERIFIED_NARRATED_TRANSFER")
        self.assertEqual(door["reason_code"], "UNVERIFIED_NARRATED_TRANSFER")

    async def test_unsafe_model_outputs_are_still_blocked(self):
        # Each harmful packet is a fresh session so a later fallback cannot
        # hide the first safety code behind REPEATED_NARRATION.
        cases = (
            (
                "D1 model invents a completed player action",
                "agency",
                "Şehirde gidebileceğim sakin bir yer önerir misin?",
                "masaya oturuyorsun",
                {"INVENTED_PLAYER_ACTION"},
                False,
            ),
            (
                "D2 model grants gold and property in speech",
                "gold",
                "Şehirde gidebileceğim sakin bir yer önerir misin?",
                "han da senin oldu",
                {"CANONICAL_REWARD_CONTRADICTION", "UNVERIFIED_NARRATED_TRANSFER"},
                False,
            ),
            (
                "D3 model leaks a hidden person's identity",
                "leak",
                "Şehirde gidebileceğim sakin bir yer önerir misin?",
                "Veyra",
                {"HIDDEN_NPC_IDENTITY_DISCLOSURE"},
                True,
            ),
            (
                "D4 model speaks as a different person",
                "wrong_speaker",
                "Şehirde gidebileceğim sakin bir yer önerir misin?",
                "Ben Taren",
                {"WRONG_NPC_SPEAKER_ATTRIBUTION"},
                False,
            ),
            (
                "D5 model narrates an action that never happened",
                "fake_action",
                "Şehirde gidebileceğim sakin bir yer önerir misin?",
                "anahtarını sana verdi",
                {"UNVERIFIED_NARRATED_TRANSFER"},
                False,
            ),
            (
                "D7 model narrates a transfer with a different verb",
                "fake_drop",
                "Şehirde gidebileceğim sakin bir yer önerir misin?",
                "anahtarını sana bıraktım",
                {"UNVERIFIED_NARRATED_TRANSFER"},
                False,
            ),
            (
                "D8 model uses first person to claim a different identity",
                "wrong_speaker_unlabelled",
                "Şehirde gidebileceğim sakin bir yer önerir misin?",
                "Ben Taren",
                {"WRONG_NPC_SPEAKER_ATTRIBUTION"},
                False,
            ),
        )
        for label, mode, message, forbidden, reasons, with_hidden in cases:
            session, turn_url, guard = await self._focused_guard(
                npc_id=f"npc_stage_a_{mode}"
            )
            if with_hidden:
                session.world_state["npcs"].append({
                    "id": "npc_stage_a_hidden",
                    "name": "Veyra",
                    "role": "informant",
                    "location": CITY,
                    "hidden": True,
                    "name_known_to_player": False,
                    "role_known_to_player": False,
                    "reality_layer": "PROCEDURAL_LOCAL_FICTION",
                    "knowledge": [],
                    "status": "active",
                    "combat_status": "active",
                    "current_hp": 10,
                    "memory": [],
                })
            inventory_before = copy.deepcopy(session.world_state["inventory"])
            doors_before = copy.deepcopy(session.world_state["doors"])
            record = await self._say(
                label, session, turn_url, guard["id"], message, mode=mode,
            )
            reason = (record.get("telemetry") or {}).get("fallback_reason")
            self.assertNotIn(forbidden, record["narration"], record)
            self.assertTrue(record["protected_fields_unchanged"], record)
            self.assertIn(reason, reasons, record)
            self.assertEqual(session.world_state["inventory"], inventory_before)
            self.assertEqual(session.world_state["doors"], doors_before)

        session, turn_url, guard = await self._focused_guard(
            npc_id="npc_stage_a_metaphor"
        )
        metaphor = await self._say(
            "D9 harmless figurative key metaphor", session, turn_url,
            guard["id"], "Şehirde gidebileceğim sakin bir yer önerir misin?",
            mode="metaphor",
        )
        self.assertNotEqual(
            (metaphor.get("telemetry") or {}).get("fallback_reason"),
            "UNVERIFIED_NARRATED_TRANSFER",
            metaphor,
        )
        self.assertIn("kalbimin anahtarını", metaphor["narration"])

        session, turn_url, guard = await self._focused_guard(
            npc_id="npc_stage_a_claim"
        )
        inventory_before = copy.deepcopy(session.world_state["inventory"])
        claim = await self._say(
            "D6 model confirms the player's false past claim",
            session, turn_url, guard["id"],
            "Geçen sefer bana hanın anahtarını vermiştin. Adın neydi?",
            mode="claim_confirm",
        )
        self.assertNotIn("vermiştim", claim["narration"], claim)
        self.assertTrue(claim["protected_fields_unchanged"], claim)
        self.assertEqual(session.world_state["inventory"], inventory_before)


if __name__ == "__main__":
    unittest.main()

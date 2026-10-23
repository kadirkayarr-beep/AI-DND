"""Transcript replay baseline for NPC conversation and door actions.

Replays a real player session (Quenna / Orryn Hanı) through the HTTP turn
endpoint with a scripted model and records, per turn, who produced the result:
the deterministic engine, the model, or a fallback. Diagnostic only: it asserts
harness integrity, never that a known defect is absent. Records and a summary
are written when NPC_STAGE_A_EVIDENCE_DIR is set. Not live Qwen.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import living_world
from api.tests import test_campaign_api
from api.tests.test_campaign_api import create_city_with_locked_tavern
from api.tests.test_npc_dialogue_stage_a_diagnostic import (
    PROTECTED_FIELDS,
    StageADiagnosticTests,
)

LORE_REFUSAL_MARKER = "hiçbir söz sağlam görünmüyor"
CLARIFICATION_MARKER = "seçemedim"
NO_CHANGE_MARKER = "çevrede şimdilik belirgin bir değişiklik olmuyor"

# NPC lines taken from the transcript, keyed by a substring of the player text.
QUENNA_REPLIES = [
    ("ismin nedir", "Quenna: “Ben Quenna. Kent sakini olarak buradayım. Bir fırında yardımcı olarak çalışıyorum.”"),
    ("quenna ile konuşmak", "Quenna: “Neden tekrar soruyorsun? İsmim Quenna, işte buradayım.”"),
    ("günün nasıl", "Quenna: “Günler... kuru ekmek ve un kokusuyla geçer genelde. İşten döndüğümde biraz nefes almak için pencere kenarına oturuyorum.”"),
    ("han varmı", "Quenna: “Han mı arıyorsun? Evet, şehir merkezinde birkaç tane var. Bazen oraları doldurup boşaltırım ama ben fırın işlerimi bitirince eve dönerim.”"),
    ("en yakın han", "Quenna: “Şehrin girişine doğru, büyük taş kapının hemen yanındaki sokakta. Ama dikkat et; orası kalabalık olur, özellikle öğlen yemeğinde.”"),
]
QUENNA_OPENING = "Yakındaki kişi: “Hadi bakalım, sana ne işin var? İşlerimi bitirip biraz dinleniyordum.”"
DEFAULT_NARRATION = "Sahne sakin; kimse sana aldırmıyor."


class TranscriptModel(test_campaign_api.FakeOllamaClient):
    def __init__(self):
        self.calls = 0
        self.dialogue_next = False

    def chat(self, *args, **kwargs):
        self.calls += 1
        schema = kwargs.get("format", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        messages = kwargs.get("messages", [])
        prompt = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        player_text = prompt.rsplit("Current player message: ", 1)[-1].splitlines()[0] \
            if "Current player message: " in prompt else prompt
        folded = player_text.casefold()
        dialogue = self.dialogue_next
        packet = {
            "intent": "dialogue" if dialogue else "narrative",
            "action": "dialogue" if dialogue else "narrative",
            "target": {"type": "none", "reference": ""},
            "completion": "unclear" if dialogue else "completed",
            "confidence": 1.0,
        }
        if "intent" in properties and "narration" not in properties:
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        narration = next(
            (text for key, text in QUENNA_REPLIES if key in folded),
            QUENNA_OPENING if dialogue else DEFAULT_NARRATION,
        )
        packet.update({
            "narration": narration,
            "world_updates": {},
            "lore_claims": [],
            "interaction": {"operation": "none", "quote": player_text, "conversation": None},
        })
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


def classify(record, earlier_narrations):
    telemetry = record.get("telemetry") or {}
    narration = record["narration"]
    folded = narration.casefold()
    generic_text = LORE_REFUSAL_MARKER in folded or NO_CHANGE_MARKER in folded
    if telemetry.get("fallback_reason") or generic_text:
        owner = "fallback"
    elif record.get("model_chat_calls", 0) > 0:
        owner = "model"
    else:
        owner = "deterministic"
    return {
        "owner": owner,
        "generic": generic_text or bool(telemetry.get("fallback_reason")),
        "clarification": CLARIFICATION_MARKER in narration
        or record.get("action_status") == "clarification",
        "repeat": bool(narration) and narration in earlier_narrations,
    }


class TranscriptReplayBaseline(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = StageADiagnosticTests.asyncSetUp
    _write_evidence = StageADiagnosticTests._write_evidence
    post_scene_turn = StageADiagnosticTests.post_scene_turn

    async def _turn(self, label, session, turn_url, model, message, mode="do"):
        protected_before = {k: copy.deepcopy(session.character.get(k)) for k in PROTECTED_FIELDS}
        calls_before = model.calls
        captured = {}
        real_turn = session.run_player_turn

        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            captured["result"] = copy.deepcopy(result)
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            response = await self.post_scene_turn(turn_url, model, {
                "message": message,
                "interaction_mode": mode,
                "action_id": str(uuid.uuid4()),
            })
        body = response.json() if response.status_code == 200 else {}
        outcome = body.get("turn_outcome") or {}
        result = captured.get("result") or {}
        evidence = result.get("_engine_event_evidence") or {}
        record = {
            "step": label,
            "input": message,
            "interaction_mode": mode,
            "http_status": response.status_code,
            "narration": body.get("narration", ""),
            "action": outcome.get("action"),
            "action_status": outcome.get("status"),
            "npc_id": (result.get("action_result") or {}).get("npc_id"),
            "active_npc_id_after": session.world_state.get("flags", {}).get("active_npc_id"),
            "telemetry": evidence.get("telemetry"),
            "model_chat_calls": model.calls - calls_before,
            "protected_fields_unchanged": all(
                session.character.get(k) == v for k, v in protected_before.items()
            ),
        }
        earlier = {r["narration"] for r in self.records}
        record.update(classify(record, earlier))
        self.records.append(record)
        return record

    def _write_summary(self):
        directory = os.environ.get("NPC_STAGE_A_EVIDENCE_DIR")
        total = len(self.records) or 1
        summary = {
            "turns": len(self.records),
            "by_owner": {
                owner: sum(1 for r in self.records if r["owner"] == owner)
                for owner in ("deterministic", "model", "fallback")
            },
            "generic_rate": round(sum(r["generic"] for r in self.records) / total, 3),
            "clarification_rate": round(sum(r["clarification"] for r in self.records) / total, 3),
            "repeat_rate": round(sum(r["repeat"] for r in self.records) / total, 3),
        }
        print("REPLAY_SUMMARY=" + json.dumps(summary, ensure_ascii=False))
        for r in self.records:
            print(
                f"{r['step']:<34} owner={r['owner']:<13} generic={int(r['generic'])} "
                f"clar={int(r['clarification'])} repeat={int(r['repeat'])} | {r['narration'][:90]}"
            )
        if directory:
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{self._testMethodName}.summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    async def test_quenna_hidden_name_conversation(self):
        _city, _sid, session, turn_url, _tavern, _door = \
            await create_city_with_locked_tavern(self)
        # Looking around places one unnamed person and one guard, as in the real
        # session. Give that person Quenna's identity, name hidden.
        model = TranscriptModel()
        self.addCleanup(self._write_summary)
        await self._turn(
            "Q1 look around", session, turn_url, model, "Çevreyi gözlemliyorum."
        )
        person = next(
            (npc for npc in session.world_state["npcs"]
             if isinstance(npc, dict) and living_world.public_npc_name(npc) == "Yakındaki kişi"),
            None,
        )
        self.assertIsNotNone(person, [
            {k: npc.get(k) for k in ("id", "name", "role", "name_known_to_player",
                                     "role_known_to_player", "hidden", "location")}
            for npc in session.world_state["npcs"] if isinstance(npc, dict)
        ])
        person["name"] = "Quenna"
        person["name_known_to_player"] = False
        person["role_known_to_player"] = False
        steps = [
            ("Q2 talk to the nearby person", "Yakındaki kişi ile konuşmak istiyorum.", "do", True),
            ("Q2b same, say mode", "Yakındaki kişi ile konuşmak istiyorum.", "say", True),
            ("Q3 ask the name", "Selamlar, ismin nedir?", "say", True),
            ("Q4 end conversation", "Konuşmayı bitiriyorum.", "do", False),
            ("Q5 reopen by name", "Quenna ile konuşmak istiyorum.", "do", True),
            ("Q6 how is your day", "Günün nasıl geçiyor?", "do", True),
            ("Q7 is there an inn", "Buralarda han varmı?", "say", True),
            ("Q8 where is the nearest inn", "En yakın han nerede?", "say", True),
        ]
        for label, message, mode, dialogue in steps:
            model.dialogue_next = dialogue
            await self._turn(label, session, turn_url, model, message, mode)
        for record in self.records:
            self.assertEqual(record["http_status"], 200, record)
            self.assertTrue(record["protected_fields_unchanged"], record)
        by_step = {record["step"].split(" ", 1)[0]: record for record in self.records}
        # Typing the public label back must address that person and keep focus.
        self.assertEqual(by_step["Q2"]["action_status"], "conversation_started", by_step["Q2"])
        self.assertTrue(by_step["Q2"]["npc_id"], by_step["Q2"])
        self.assertEqual(by_step["Q2"]["active_npc_id_after"], by_step["Q2"]["npc_id"])
        self.assertIn("Quenna", by_step["Q3"]["narration"], by_step["Q3"])
        self.assertFalse(any(r["generic"] for r in self.records), self.records)

    async def test_inn_door_and_lockpick_loop(self):
        _city, _sid, session, turn_url, tavern_id, door = \
            await create_city_with_locked_tavern(self)
        inn = session.world_state["locations"][tavern_id].get("name", "Han")
        door_name = door.get("name") or f"{inn} Kapısı"
        model = TranscriptModel()
        self.addCleanup(self._write_summary)
        steps = [
            ("D1 look around", "Çevreyi gözlemliyorum."),
            ("D2 look around again", "Çevreyi gözlemliyorum."),
            ("D3 go to the inn", "Hana doğru gidiyorum"),
            ("D3b go to the inn by name", f"{inn} yoluna çıkıp oraya gidiyorum"),
            ("D4 knock", f"{inn} kapısını tıklatıyorum belki açarlar"),
            ("D5 circle for another entrance", "Hanın etrafında dolaşıyorum, açık pencere kapı arıyorum."),
            ("D6 look around at the inn", "Çevreyi gözlemliyorum."),
            ("D7 try to open", f"{inn} kapısını açmaya çalışıyorum"),
            ("D8 inspect door", "Kapıyı dikkatlice inceliyorum"),
            ("D9 inventory", "Envanterimde neler var?"),
            ("D10 lockpick vague", "Kilidi maymuncukla açmayı deniyorum"),
            ("D11 lockpick vague repeat", "Kilidi maymuncukla açmayı deniyorum"),
            ("D12 lockpick with inn", "Han kapısı kilidi maymuncukla açmayı deniyorum"),
            ("D13 lockpick exact name", f"{door_name} kilidini maymuncukla açmayı deniyorum"),
        ]
        for label, message in steps:
            await self._turn(label, session, turn_url, model, message)
        stuck = [r for r in self.records if r["step"].startswith(("D10", "D11", "D12", "D13"))]
        # Recorded as a defect tag, not asserted: the player never reaches a lock check.
        print("LOCKPICK_LOOP_UNRESOLVED=" + str(all(r["clarification"] or r["generic"] for r in stuck)))
        for record in self.records:
            self.assertEqual(record["http_status"], 200, record)
            self.assertTrue(record["protected_fields_unchanged"], record)


class InteriorBaseline(TranscriptReplayBaseline):
    """Entering a venue must put someone and something in it (creativity metric)."""

    async def test_entering_the_inn_is_not_empty(self):
        from api.tests.test_campaign_api import unlock_venue_door

        _city, _sid, session, turn_url, tavern_id, _door = \
            await create_city_with_locked_tavern(self)
        unlock_venue_door(session.world_state, tavern_id)
        inn = session.world_state["locations"][tavern_id].get("name", "Han")
        model = TranscriptModel()
        self.addCleanup(self._write_summary)
        await self._turn("I1 go to the inn", session, turn_url, model, f"{inn} yoluna çıkıp oraya gidiyorum")
        enter = await self._turn("I2 go inside", session, turn_url, model, "İçeri giriyorum")
        look = await self._turn("I3 look around inside", session, turn_url, model, "Çevreyi gözlemliyorum.")
        people = [
            npc for npc in session.world_state["npcs"]
            if isinstance(npc, dict) and npc.get("location") == tavern_id
        ]
        print(f"INTERIOR_PEOPLE={len(people)} enter={enter['narration'][:120]!r} look={look['narration'][:120]!r}")
        self.assertEqual(session.world_state.get("location"), tavern_id)
        self.assertTrue(people, "the inn is empty")
        self.assertNotIn("İçerisi sessiz", enter["narration"], enter)


class LoreGuardRepairUnitTests(unittest.TestCase):
    def test_generic_npc_label_is_not_a_new_entity(self):
        import game

        for label in ("Yakındaki kişi", "Bir muhafız", "Bir yaşlı kadın"):
            sentence = f"{label}: “Hadi bakalım, sana ne işin var?”"
            self.assertFalse(
                game._has_unregistered_narrative_entity(sentence, {"marek"}, {"marek"}),
                sentence,
            )

    def test_unregistered_name_in_speech_is_still_caught(self):
        import game

        self.assertTrue(game._has_unregistered_narrative_entity(
            "Yakındaki kişi: “Brom adlı kişi burada.”", {"marek"}, {"marek"}
        ))

    def test_repair_keeps_supported_sentences_and_drops_only_the_bad_one(self):
        import game

        narration = "Rüzgâr hafifçe eser. Yolda Brom adlı kişi var. Sokak sessizdir."
        repaired = game._repair_unsupported_lore_narration(narration, [], {}, {})
        self.assertIsNotNone(repaired)
        self.assertIn("Rüzgâr hafifçe eser.", repaired)
        self.assertIn("Sokak sessizdir.", repaired)
        self.assertNotIn("Brom", repaired)

    def test_repair_gives_up_when_nothing_usable_remains(self):
        import game

        self.assertIsNone(game._repair_unsupported_lore_narration(
            "Yolda Brom adlı kişi var.", [], {}, {}
        ))


if __name__ == "__main__":
    unittest.main()

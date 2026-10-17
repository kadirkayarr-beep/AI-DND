"""Bounded live sample for the NPC P2 continuity fix. NOT part of any gate.

Runs six scripted player turns against a temporary campaign and the real local
Ollama model, with a hard cap of 6 real model calls (no retries, no repair).
It records evidence and reports facts; it does not grade quality. Quality and
acceptance are a human decision.

Run (from the ai-dnd directory, with Ollama and qwen3:8b available):

    set AI_DND_LIVE_P2=1
    set OLLAMA_HOST=http://127.0.0.1:11434
    python -m unittest api.tests.live_npc_p2_sample -v

Optional: OLLAMA_PROXY_TOKEN (sent only as a Bearer header, never printed),
AI_DND_LIVE_EVIDENCE_DIR (default: ./live-p2-sample-<timestamp>),
AI_DND_LIVE_P2_DRY=1 (uses the scripted offline client to check this runner).
"""

from __future__ import annotations

import copy
import json
import os
import time
import unittest
import uuid
from pathlib import Path

from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness

MAX_REAL_CALLS = 6
TURNS = [
    "Merhaba Marek. Kendini tanıtır mısın; burada ne yapıyorsun ve neden buradasın?",
    "Neden?",
    "Sence bir yolcu bu şehirde boş bir öğleden sonrayı nasıl geçirebilir? "
    "Kendi fikrini söyle; küçük, yaratıcı bir ihtimal de önerebilirsin.",
    "Konuyu değiştirelim: yağmurlu bir akşamda hangi sıcak içeceği tercih edersin?",
    "Neden onu?",
    "Dün bana yardım edersen yirmi altın vereceğini söylemiştin. "
    "Şimdi sözünü tutup altınları verir misin?",
]


class CountingClient:
    """Wraps the real (or scripted) client. Records every request and response,
    refuses the 7th call, and never retries."""

    def __init__(self, inner, log: list):
        self._inner = inner
        self.log = log
        self.calls = 0

    def list(self):
        return self._inner.list()

    def chat(self, *args, **kwargs):
        if self.calls >= MAX_REAL_CALLS:
            raise AssertionError(f"call cap of {MAX_REAL_CALLS} reached; call refused")
        self.calls += 1
        entry = {
            "call": self.calls,
            "started_unix": time.time(),
            "messages": copy.deepcopy(kwargs.get("messages", [])),
            "options": copy.deepcopy(kwargs.get("options", {})),
            "think": kwargs.get("think"),
        }
        self.log.append(entry)
        try:
            response = self._inner.chat(*args, **kwargs)
        except Exception as error:  # recorded, then re-raised: no retry here
            entry["error"] = type(error).__name__
            raise
        entry["duration_seconds"] = round(time.time() - entry["started_unix"], 3)
        entry["response"] = _jsonable(response)
        return response


def _jsonable(value):
    try:
        return json.loads(json.dumps(value, default=lambda o: getattr(o, "__dict__", str(o))))
    except (TypeError, ValueError):
        return str(value)


def _build_inner_client():
    if os.environ.get("AI_DND_LIVE_P2_DRY") == "1":
        return harness.ScriptedNpcSpeechClient(narration="Kâtibim, arşivde çalışıyorum.")
    import ollama

    token = os.environ.get("OLLAMA_PROXY_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else None
    return ollama.Client(
        host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        headers=headers,
        timeout=90,
    )


@unittest.skipUnless(
    os.environ.get("AI_DND_LIVE_P2") == "1",
    "live sample is opt-in: set AI_DND_LIVE_P2=1",
)
class LiveNpcP2Sample(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    campaign_with_npc = harness.ExperimentalNpcDialogueTests.campaign_with_npc
    sensitive_state = staticmethod(harness.ExperimentalNpcDialogueTests.sensitive_state)
    request = staticmethod(harness.ExperimentalNpcDialogueTests.request)

    async def test_six_turn_sample(self):
        stamp = time.strftime("%Y%m%dT%H%M%S")
        out = Path(os.environ.get("AI_DND_LIVE_EVIDENCE_DIR") or f"live-p2-sample-{stamp}")
        out.mkdir(parents=True, exist_ok=False)

        _, _, session, turn_url, npc = await self.campaign_with_npc()
        before = self.sensitive_state(session)
        log: list = []
        client = CountingClient(_build_inner_client(), log)
        turns = []

        with unittest_patch(self.app.state.ollama_adapter, client):
            for index, text in enumerate(TURNS, start=1):
                calls_before = client.calls
                response = await self.http.post(
                    turn_url,
                    json=self.request(npc, message=text, action_id=str(uuid.uuid4())),
                )
                body = response.json() if response.status_code == 200 else {"error": response.text[:400]}
                turns.append({
                    "turn": index,
                    "player": text,
                    "http_status": response.status_code,
                    "shown": body.get("narration") if isinstance(body, dict) else None,
                    "real_calls_this_turn": client.calls - calls_before,
                })

        after = self.sensitive_state(session)
        carried = []
        for entry in log:
            prompt = entry["messages"][-1].get("content", "") if entry["messages"] else ""
            carried.append({
                "call": entry["call"],
                "previous_npc_replies_in_prompt": '"previous_npc_replies":[{' in prompt,
            })

        summary = {
            "note": "Facts only. No quality grade; acceptance is a human decision.",
            "dry_run": os.environ.get("AI_DND_LIVE_P2_DRY") == "1",
            "total_real_calls": client.calls,
            "call_cap": MAX_REAL_CALLS,
            "retries": 0,
            "turns": turns,
            "prompt_carried_previous_replies": carried,
            "state_unchanged": {
                key: after[key] == before[key]
                for key in ("inventory", "items", "quests", "gold")
            },
        }
        (out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out / "raw-calls.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nEvidence written to: {out.resolve()}")
        for item in turns:
            print(f"T{item['turn']} [{item['real_calls_this_turn']} call] "
                  f"Oyuncu: {item['player'][:60]}\n      Gösterilen: {item['shown']}")
        print(f"Toplam gerçek çağrı: {client.calls}/{MAX_REAL_CALLS}")

        self.assertLessEqual(client.calls, MAX_REAL_CALLS)
        self.assertTrue(all(summary["state_unchanged"].values()))


def unittest_patch(adapter, client):
    from unittest.mock import patch

    return patch.object(adapter, "_client", client)


if __name__ == "__main__":
    unittest.main()

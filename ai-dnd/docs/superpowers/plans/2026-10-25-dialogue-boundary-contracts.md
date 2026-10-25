# Diyalog Sınırı Sözleşmeleri: Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Üç diyalog sınırını testle kilitlemek ve gizli NPC adı bir ay adı olduğunda ay kalıbının yanlış alarm vermesini düzeltmek.

**Architecture:** Atıf ve yalan sınırları bugün zaten doğru çalışıyor (`npc_statements`, `deception_context`, `observe_turn`); onlar yalnız testle kilitlenir. Tek ürün değişikliği `npc_speech_boundary.mask_calendar_month_name` ve onun `game.py::_narration_safety_decision` içindeki tek çağrısıdır.

**Tech Stack:** Python 3.12, `unittest`, mevcut ASGI test koşumu (`IntentResponseConsistencyTests`), betikli model (`ScriptedNpcSpeechClient`).

## Global Constraints

- Python dünya gerçeğinin sahibidir; model metni dünya gerçeği olamaz.
- Yeni kural mevcut sahip modülüne girer: maske `npc_speech_boundary.py`, çağrı `game.py`. `game.py` kuralı bu iş için kullanıcı tarafından gevşetilmiştir.
- Yalan yalnız kayıtlı motif ve kanıtla açılır; çelişen söz işaret veya motif üretmez.
- Ay kalıbı yalnız on iki gerçek Türkçe ay adında çalışır. Rol adları ve diğer homograflar kapsam dışıdır ve reddedilmeye devam eder.
- Canlı model çağrısı yok. Birleştirme yok. Canlı olay UNRESOLVED kalır.
- Yeni test dosyaları LF, mevcut ürün dosyaları CRLF. `PYTHONUTF8=1`.
- Komutlar `ai-dnd` klasöründen çalışır: `C:\Users\Kadir\Desktop\AI-DND-v01-scene-truth\ai-dnd`.

---

### Task 1: Atıf ve yalan sınırını testle kilitle

**Files:**
- Create: `ai-dnd/api/tests/test_dialogue_boundary_contracts.py`

**Interfaces:**
- Consumes: `npc_statements.record(world, npc, player_text, shown_text, *, turn)`, `npc_statements.claim_support(world, npc, claim)` -> `{"status": "supported"|"unsupported"|"absent", ...}`, `dialogue_runtime.deception_context(world, npc, context)` -> `dict|None`, `dialogue_runtime.observe_turn(session, before, old_hp, result, player_text, action_id)`, `dialogue_runtime.initialize_new_campaign(world, mode)`, `game.create_session(seed)`.
- Produces: kilitleme testleri. Ürün kodu değişmez.

- [ ] **Step 1: Write the test file**

```python
"""Dialogue boundary contracts: a wrong NPC line stays attributed, never canon.

An NPC statement that contradicts the world stays in npc_statements as that
NPC's words. It changes no world state, creates no deception motive, and never
makes deception_context return anything. A lie opens only with a recorded
motive plus matching evidence.
"""
import copy
import unittest

import dialogue_runtime
import game
import npc_statements


class AttributionContracts(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=7)
        self.world = self.session.world_state
        self.world["locations"]["known_inn"] = {
            "id": "known_inn", "name": "Hlin Hanı", "type": "building",
            "scene_kind": "tavern", "description": "Sade bir salon."}
        self.world["location"] = "known_inn"
        self.npc = self.session.create_npc_from_ai({
            "name": "Hlin", "role": "Barmen", "location": "known_inn",
            "appearance": "Tezgâh arkasında duran kişi."})

    def snapshot(self):
        return copy.deepcopy({k: v for k, v in self.world.items() if k != "npc_statements"})

    def test_npc_mistake_stays_attributed_not_canon(self):
        before = self.snapshot()
        npc_statements.record(
            self.world, self.npc, "Masada ne vardı?",
            "Hlin, “Masada bir halka vardı, onu ben gördüm.” diye yanıt verir.", turn=3)
        support = npc_statements.claim_support(self.world, self.npc, "Masada bir halka vardı demiştin")
        self.assertEqual(support["status"], "supported")
        self.assertEqual(support["quote"], "Masada bir halka vardı, onu ben gördüm.")
        invented = npc_statements.claim_support(self.world, self.npc, "Masada altın vardı demiştin")
        self.assertEqual(invented["status"], "unsupported")
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.world.get("relationships"))

    def test_model_contradiction_not_reclassified_as_intentional_lie(self):
        dialogue_runtime.initialize_new_campaign(self.world, "free_v1")
        result = {"action_result": {"status": "free_dialogue", "npc_id": self.npc["id"]}}
        dialogue_runtime.observe_turn(self.session, copy.deepcopy(self.world), 10,
                                      result, "Masada ne vardı?", "act-1")
        npc_statements.record(self.world, self.npc, "Masada ne vardı?",
                              "Hlin, “Masada bir halka vardı.” diye yanıt verir.", turn=1)
        dialogue_runtime.observe_turn(self.session, copy.deepcopy(self.world), 10,
                                      result, "Yalan söylüyorsun!", "act-2")
        self.assertNotIn("dialogue_deception", self.npc)
        self.assertIsNone(dialogue_runtime.deception_context(
            self.world, self.npc, {"text": "Masada halka var mıydı?"}))
        # An unsupported motive never authorizes a lie and is never spent.
        planted = copy.deepcopy(self.npc)
        planted["dialogue_deception"] = {"motive": "x", "evidence_id": "invented",
                                         "topic": "halka", "remaining_uses": 2}
        self.assertIsNone(dialogue_runtime.deception_context(
            self.world, planted, {"text": "halka"}))
        self.assertEqual(planted["dialogue_deception"]["remaining_uses"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it**

Run: `python -m unittest api.tests.test_dialogue_boundary_contracts -v`
Expected: 2 tests, OK. These lock existing behavior, so they pass on first run. If one fails, stop: the measured behavior changed and the spec must be revisited before any product code is touched.

- [ ] **Step 3: Commit**

```bash
git add ai-dnd/api/tests/test_dialogue_boundary_contracts.py
git commit -m "test: lock NPC attribution and deception boundaries"
```

### Task 2: Ay adı maskesi (TDD)

**Files:**
- Modify: `ai-dnd/api/tests/test_dialogue_boundary_contracts.py` (append)
- Modify: `ai-dnd/npc_speech_boundary.py` (append function)
- Modify: `ai-dnd/game.py` (`_narration_safety_decision`, one line after the `hidden_identity_scan_text` call)

**Interfaces:**
- Consumes: `npc_speech_boundary.hidden_identity_scan_text(text, identity, world)`, `GameSession._narration_safety_decision(narration, player_input, npc_target=None, action_result=None)` -> `{"unsafe": bool, "reason_code": str|None, ...}`.
- Produces: `npc_speech_boundary.mask_calendar_month_name(text: str, identity: str) -> str`.

- [ ] **Step 1: Append the failing tests**

```python
import npc_speech_boundary


class MonthNameMaskTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=7)
        self.world = self.session.world_state
        self.world["locations"]["known_inn"] = {
            "id": "known_inn", "name": "Hlin Hanı", "type": "building",
            "scene_kind": "tavern", "description": "Sade bir salon."}
        self.world["location"] = "known_inn"
        self.npc = self.session.create_npc_from_ai({
            "name": "Kasım", "role": "Demirci", "location": "known_inn",
            "appearance": "Önlüklü kişi."})
        self.npc.update(name_known_to_player=False, role_known_to_player=False)

    def decision(self, text):
        return self.session._narration_safety_decision(
            text, "Etrafa bakıyorum.",
            action_result={"action": "explore", "status": "observed", "success": True})

    def test_secret_word_in_harmless_smalltalk_does_not_block_speech(self):
        for text in ("Kasım ayı soğuk geçti, rüzgar sertleşiyor.",
                     "Kasım ayında hava soğur.",
                     "KASIM AYINDA kar yağar."):
            with self.subTest(text=text):
                before = copy.deepcopy(self.world)
                self.assertFalse(self.decision(text)["unsafe"])
                self.assertEqual(self.world, before)
                self.assertFalse(self.npc["name_known_to_player"])

    def test_real_identity_claim_is_still_rejected(self):
        for text in ("Kasım gülümsüyor.", "Ben Kasım, demirciyim.",
                     "Kasım ayı soğuk. Kasım gülümsüyor."):
            with self.subTest(text=text):
                result = self.decision(text)
                self.assertTrue(result["unsafe"])
                self.assertEqual(result["reason_code"], "HIDDEN_NPC_IDENTITY_DISCLOSURE")

    def test_non_month_homograph_stays_rejected(self):
        self.npc["name"] = "Yağmur"
        result = self.decision("Yağmur yağıyor, sokaklar ıslandı.")
        self.assertTrue(result["unsafe"])
        self.assertEqual(result["reason_code"], "HIDDEN_NPC_IDENTITY_DISCLOSURE")

    def test_mask_only_covers_real_month_names(self):
        self.assertNotIn("kasım", npc_speech_boundary.mask_calendar_month_name(
            "Kasım ayında kar yağar.", "Kasım").casefold())
        self.assertIn("kasım", npc_speech_boundary.mask_calendar_month_name(
            "Kasım gülümsüyor.", "Kasım").casefold())
        self.assertEqual(npc_speech_boundary.mask_calendar_month_name(
            "Yağmur ayında beklenir.", "Yağmur"), "Yağmur ayında beklenir.")
```

- [ ] **Step 2: Run to verify RED**

Run: `python -m unittest api.tests.test_dialogue_boundary_contracts.MonthNameMaskTests -v`
Expected: 4 FAIL. `test_mask_only_covers_real_month_names` fails with `AttributeError: mask_calendar_month_name`. The decision tests fail because "Kasım ayı" is still rejected.

- [ ] **Step 3: Add the mask**

Append to `npc_speech_boundary.py`:

```python
_MONTH_NAMES = frozenset({
    "ocak", "subat", "mart", "nisan", "mayis", "haziran",
    "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik",
})
_MONTH_PATTERN = re.compile(
    r"(?<!\w)(?P<name>\w+)\s+ay(?:ı|i|ında|inda|ının|inin|ına|ina|ından|indan|larında|larinda)\b",
    re.IGNORECASE,
)


def mask_calendar_month_name(text, identity):
    """Hide a month-name mention from the identity scan, nothing else.

    A hidden NPC named after a real Turkish month ("Kasım") must not make
    "Kasım ayında kar yağar" a disclosure. A bare name, "Ben Kasım" and
    "Kasım gülümsüyor" stay visible, and a name that is not a month is never
    masked. This returns a scan view; the narration itself is unchanged.
    """
    if not isinstance(text, str) or not isinstance(identity, str):
        return text
    if fold(identity) not in _MONTH_NAMES:
        return text

    def mask(match):
        if fold(match.group("name")) != fold(identity):
            return match.group(0)
        start, end = match.span("name")
        relative = start - match.start()
        blank = " " * (end - start)
        return match.group(0)[:relative] + blank + match.group(0)[relative + end - start:]

    return _MONTH_PATTERN.sub(mask, text)
```

- [ ] **Step 4: Call it from the safety decision**

In `game.py::_narration_safety_decision`, directly after the existing line

```python
                identity_view = npc_speech_boundary.hidden_identity_scan_text(
                    identity_view, identity, world_state
                )
```

add one line:

```python
                identity_view = npc_speech_boundary.mask_calendar_month_name(identity_view, identity)
```

- [ ] **Step 5: Run to verify GREEN**

Run: `python -m unittest api.tests.test_dialogue_boundary_contracts -v`
Expected: 6 tests, OK.

- [ ] **Step 6: Commit**

```bash
git add ai-dnd/npc_speech_boundary.py ai-dnd/game.py ai-dnd/api/tests/test_dialogue_boundary_contracts.py
git commit -m "fix: a month name is not a hidden NPC disclosure in calendar speech"
```

### Task 3: Gerçek ASGI yolunda uçtan uca test

**Files:**
- Modify: `ai-dnd/api/tests/test_dialogue_boundary_contracts.py` (append)

**Interfaces:**
- Consumes: `api.tests.test_intent_response_consistency.IntentResponseConsistencyTests` (`asyncSetUp`, `asyncTearDown`, `turn`), `api.tests.test_experimental_npc_dialogue.ScriptedNpcSpeechClient`.

- [ ] **Step 1: Append the end-to-end test**

```python
from contextlib import closing
from unittest.mock import patch

from api.tests import test_intent_response_consistency as fixture
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient


class MonthNameSpeechHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixture.IntentResponseConsistencyTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await fixture.IntentResponseConsistencyTests.asyncTearDown(self)

    async def turn(self, message, **fields):
        return await fixture.IntentResponseConsistencyTests.turn(self, message, **fields)

    def stored(self):
        with closing(self.store._connect()) as db:
            rows = db.execute(
                "SELECT narration FROM campaign_history WHERE campaign_id = ? ORDER BY sequence",
                (self.campaign_id,)).fetchall()
        return [row[0] for row in rows]

    async def test_calendar_speech_passes_but_identity_claim_is_rejected(self):
        await self.turn("Çevreme bakıyorum.")
        speaker = self.world["npcs"][0]
        speaker.update(name="Lysa", name_known_to_player=True)
        hidden = dict(self.world["npcs"][1]) if len(self.world["npcs"]) > 1 else None
        secret = self.session.create_npc_from_ai({
            "name": "Kasım", "role": "Demirci", "location": self.world["location"],
            "appearance": "Önlüklü kişi."})
        secret.update(name_known_to_player=False, role_known_to_player=False)
        before = copy.deepcopy((self.session.character, self.world["inventory"], self.world["location"]))
        harmless = "Kasım ayı soğuk geçti, rüzgar sertleşiyor."
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(
                self.app.state.ollama_adapter, "_client", ScriptedNpcSpeechClient(harmless)):
            shown = await self.turn("Hava nasıl?", target_id=speaker["id"])
        self.assertIn(harmless, shown["narration"])
        self.assertEqual(self.session.last_narration_safety["handling"], "accepted")
        leak = "Kasım gülümsüyor ve adını söylüyor."
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(
                self.app.state.ollama_adapter, "_client", ScriptedNpcSpeechClient(leak)):
            blocked = await self.turn("Peki ya yarın?", target_id=speaker["id"])
        self.assertNotIn("Kasım", blocked["narration"])
        self.assertTrue(any(d.get("reason_code") == "HIDDEN_NPC_IDENTITY_DISCLOSURE"
                            for d in self.session.narration_safety_history))
        self.assertFalse(any("Kasım gülümsüyor" in text for text in self.stored()))
        self.assertEqual(before, (self.session.character, self.world["inventory"], self.world["location"]))
        self.assertFalse(secret["name_known_to_player"])
        if hidden is not None:
            self.assertEqual(self.world["npcs"][1]["name"], hidden["name"])
```

- [ ] **Step 2: Run it**

Run: `python -m unittest api.tests.test_dialogue_boundary_contracts -v`
Expected: 7 tests, OK. If the end-to-end test fails because the starting scene has a different NPC count, keep the `hidden` guard and adjust only the index lookup, never the assertions.

- [ ] **Step 3: Commit**

```bash
git add ai-dnd/api/tests/test_dialogue_boundary_contracts.py
git commit -m "test: calendar month speech survives the real dialogue path"
```

### Task 4: Regresyon ve kapanış

**Files:**
- Create: `ai-dnd/docs/evidence/v02-20261025/V02C_KABUL_NOTU.md`

- [ ] **Step 1: Focused neighbors**

Run, from `ai-dnd` with `PYTHONUTF8=1`:
`python -m unittest api.tests.test_npc_speech_identity_inflection api.tests.test_npc_p2_continuity test_narrative_safety_calibration api.tests.test_dialogue_deception api.tests.test_scene_representation_contract api.tests.test_scene_surface_persistence api.tests.test_scene_small_events_contract`
Expected: all OK.

- [ ] **Step 2: Full regression**

Run `docs/evidence/v01-20261025/run_baseline_windows.py` into `docs/evidence/v02-20261025/v02e-gates.jsonl`, then `test_lr00_grounded_human`, `test_lr00_p1_intent`, `test_wave3_interaction_modes`, `test_campaign_api`.
Expected: identical to the v0.2b baseline. 32 of 33 gates pass, the only failure is the pre-existing `test_runner_inventory` (55 failures, 11 errors, 2 skipped). `test_campaign_api` keeps the same 12 failure ids. `lr00` stays 38/38 and 21/21. `test_wave3_interaction_modes` keeps its 9 environment errors.

- [ ] **Step 3: Independent review**

Dispatch one read-only reviewer subagent on `git diff f549005`. Fix every confirmed defect before closing. Re-run the affected tests.

- [ ] **Step 4: Write the acceptance note and commit**

`V02C_KABUL_NOTU.md` records the verdict, the one product change, the test counts, the regression comparison and the limits that remain open: role-name homographs, non-month homographs such as "Yağmur yağıyor", no live model run, the live incident stays UNRESOLVED, and Phase 7 has not started.

```bash
git add ai-dnd/docs/evidence/v02-20261025
git commit -m "docs: v0.2c acceptance note for dialogue boundary contracts"
git push origin cursor/v02-consistent-world-20261025
```

No merge. Update the research folder status row and regenerate its manifest afterwards.

"""G1.8 (D-530, D-584): the three long turn functions are pinned before they are cut into helpers.

Characterization: `_run_player_turn_internal`, `_dispatch_player_turn` (through `run_player_turn`) and
`_narration_safety_decision` answer exactly what they answered before the split. Fixed town and session seed, model
forbidden (a fallback is the answer). `test_fallbacks_log_when_forced` is a real fix test (D-584): the two broad model
fallbacks of `ask_dungeon_master` log through `model_phase.log_fallback`.
"""
from __future__ import annotations

import os
import unittest
from typing import Any, cast
from unittest.mock import patch

import game
import model_phase
from api.tests.journeys.runner import _campaign_seeded
from api.tests.test_economic_action_http import EconomicHttpFixture

TOWN_SEED = 4242
SESSION_SEED = 11

# (text, interaction_mode) -> (action, status, narration, model_calls, location, hp, number of messages)
TURNS = [
    ("Kuyu Başı'na gidiyorum.", "do"),
    ("Etrafa bakıyorum.", "do"),
    ("Envanterime bakıyorum.", "do"),
    ("Kapıyı itiyorum.", "do"),
    ("Merhaba.", "say"),
    ("Burası neresi?", "ask_dm"),
    ("/rest", "do"),
    ("Zar atıyorum.", "do"),
    ("Kılıcımı çekiyorum.", "do"),
]

EXPECTED_TURNS = {
    ('', "Kuyu Başı'na gidiyorum."): ('travel', 'unverified', 'Oraya giden bir yol bilmiyorsun.', None, 'forest', 12, 0),
    ('', 'Etrafa bakıyorum.'): ('explore', 'observed', 'Orman çevresine göz gezdiriyorsun. Yol kenarında bir gezgin çantasını yere bırakıp haritasını inceler.', None, 'forest', 12, 0),
    ('', 'Envanterime bakıyorum.'): ('inventory', 'resolved', 'Envanterinde: Macera çantası, Kılıç.', 0, 'forest', 12, 1),
    ('', 'Kapıyı itiyorum.'): ('world_interaction', 'blocked', 'Burada açıp kapatabileceğin bir kapı görünmüyor.', None, 'forest', 12, 0),
    ('', 'Merhaba.'): ('dialogue', 'clarification', 'Burada konuşabileceğin kimse yok.', None, 'forest', 12, 0),
    ('', 'Burası neresi?'): ('dialogue', 'unverified', 'Bu konudaki söylentiler belirsiz; kulağına çalınan her ağız başka konuşuyor.', None, 'forest', 12, 0),
    ('', '/rest'): ('unknown', 'resolved', 'Çevrede şimdilik belirgin bir değişiklik olmuyor.', None, 'forest', 12, 0),
    ('', 'Zar atıyorum.'): ('unknown', 'resolved', 'Çevrede şimdilik belirgin bir değişiklik olmuyor.', None, 'forest', 12, 0),
    ('', 'Kılıcımı çekiyorum.'): ('unknown', 'resolved', 'Çevrede şimdilik belirgin bir değişiklik olmuyor.', None, 'forest', 12, 0),
    ('1', "Kuyu Başı'na gidiyorum."): ('travel', 'unverified', 'Oraya giden bir yol bilmiyorsun.', None, 'forest', 12, 0),
    ('1', 'Etrafa bakıyorum.'): ('explore', 'observed', 'Orman çevresine göz gezdiriyorsun. Yol kenarında bir gezgin çantasını yere bırakıp haritasını inceler.', None, 'forest', 12, 0),
    ('1', 'Envanterime bakıyorum.'): ('inventory', 'resolved', 'Envanterinde: Macera çantası, Kılıç.', 0, 'forest', 12, 1),
    ('1', 'Kapıyı itiyorum.'): ('world_interaction', 'blocked', 'Burada açıp kapatabileceğin bir kapı görünmüyor.', None, 'forest', 12, 0),
    ('1', 'Merhaba.'): ('dialogue', 'clarification', 'Burada konuşabileceğin kimse yok.', None, 'forest', 12, 0),
    ('1', 'Burası neresi?'): ('dialogue', 'unverified', 'Bu konudaki söylentiler belirsiz; kulağına çalınan her ağız başka konuşuyor.', None, 'forest', 12, 0),
    ('1', '/rest'): ('unknown', 'resolved', 'Çevrede şimdilik belirgin bir değişiklik olmuyor.', None, 'forest', 12, 0),
    ('1', 'Zar atıyorum.'): ('unknown', 'resolved', 'Çevrede şimdilik belirgin bir değişiklik olmuyor.', None, 'forest', 12, 0),
    ('1', 'Kılıcımı çekiyorum.'): ('unknown', 'resolved', 'Çevrede şimdilik belirgin bir değişiklik olmuyor.', None, 'forest', 12, 0),
}

# (narration, player_input, action_result) -> (unsafe, reason_code, trigger_span, scene_type)
DECISIONS = [
    ("", "Etrafa bakıyorum.", {"action": "explore", "status": "observed"}),
    ("Orman sessiz.", "Etrafa bakıyorum.", {"action": "explore", "status": "observed"}),
    ("Sana 50 altın verdi ve kapı açıldı.", "Kapıyı itiyorum.", {"action": "world_interaction", "status": "blocked"}),
    ("Kapı sertçe çarpıldı.", "Kapıyı itiyorum.", {"action": "world_interaction", "status": "resolved", "success": False}),
    ("Geçitten geçtin ve Neverwinter'a ulaştın.", "Yürüyorum.", {"action": "travel", "status": "unverified"}),
    ("Rüzgar yaprakları savuruyor.", "Merhaba.", {"action": "dialogue", "status": "clarification"}),
]
EXPECTED_DECISIONS = [(True, 'EMPTY_NARRATION', None, 'exploration'),
    (False, None, None, 'exploration'),
    (True, 'UNSUPPORTED_ITEM_TRANSFER', 'altın verdi', 'exploration'),
    (False, None, None, 'exploration'),
    (True, 'INVENTED_PLAYER_ACTION', 'geçtin', 'travel'),
    (False, None, None, 'conversation'),
]


def run_turn(flag, text, mode):
    with _campaign_seeded({"campaign_seed": TOWN_SEED}), patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": flag}), \
            patch("game.ollama.chat", side_effect=AssertionError("model")):
        s = game.create_session(seed=SESSION_SEED)
        s.world_state["location"] = "forest"
        s.world_state["locations"]["t11_kuyu"] = {"id": "t11_kuyu", "name": "Kuyu Başı", "type": "city",
                                                  "description": ""}
        out = cast(Any, game.run_player_turn)(text, interaction_mode=mode, session=s)
    result = out.get("action_result") or {}
    return (result.get("action"), result.get("status"), out.get("narration"), out.get("model_calls"),
            s.world_state["location"], s.character.get("current_hp"), len(out.get("messages") or []))


def decide(narration, text, action_result):
    with _campaign_seeded({"campaign_seed": TOWN_SEED}):
        s = game.create_session(seed=SESSION_SEED)
        s.world_state["location"] = "forest"
        with patch.object(game, "_session", return_value=s):
            d = game._narration_safety_decision(narration, text, None, action_result)
    return (d["unsafe"], d["reason_code"], d["trigger_span"], d["scene_type"])


class TestTurnLongFunctionsPin(unittest.TestCase):
    def test_run_player_turn_table_both_flags(self):
        for flag in ("", "1"):
            for text, mode in TURNS:
                with self.subTest(flag=flag, text=text):
                    self.assertEqual(run_turn(flag, text, mode), EXPECTED_TURNS[(flag, text)])

    def test_narration_safety_decision_table(self):
        for (narration, text, result), expected in zip(DECISIONS, EXPECTED_DECISIONS, strict=True):
            with self.subTest(narration=narration):
                self.assertEqual(decide(narration, text, result), expected)

    def test_fallbacks_log_when_forced(self):
        """D-584: a package-validation error and a narration-only model error log through model_phase.log_fallback."""
        for case, action_result in (
            ("exploration", {"action": "exploration_resolved", "status": "resolved", "direct_response": "Orman sessiz."}),
            ("interaction", {"action": "interaction", "operation": "talk", "status": "resolved",
                             "direct_response": "Marek selam veriyor."}),
        ):
            with self.subTest(case=case), _campaign_seeded({"campaign_seed": TOWN_SEED}):
                s = game.create_session(seed=SESSION_SEED)
                s.world_state["location"] = "forest"
                with patch.object(game, "_session", return_value=s), \
                        patch.object(game, "_extract_json_object", side_effect=RuntimeError("forced")), \
                        patch.object(game.ollama, "chat", return_value={"message": {"content": "{}"}}), \
                        patch.object(model_phase, "log_fallback") as logged:
                    game.ask_dungeon_master([], "Etrafa bakıyorum.", action_result=action_result,
                                            narration_only=True, return_details=True)
                self.assertEqual(logged.call_count, 1, case)
                self.assertIsInstance(logged.call_args.args[1], RuntimeError)

    def test_a_speech_debug_trail_that_cannot_write_warns_and_never_raises(self):
        """D-584: the third broad except (game._speech_debug_trail) logs a warning; the turn still never sees an error."""
        import tempfile
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"AI_DND_SPEECH_DEBUG": folder}),
            self.assertLogs("game", level="WARNING") as logged,
        ):
            game._speech_debug_trail({"x": 1})  # a folder, not a file: open(..., "a") fails
        self.assertEqual(len(logged.records), 1)
        self.assertIn("could not be written", logged.records[0].getMessage())


class TestTurnIndexAndUndoPin(EconomicHttpFixture):
    async def test_ordinary_turn_counts_once_and_undo_restores_it(self):
        before = self.money()
        turn_id, body = await self.real_turn("Tezgâha yaslanıp salonu dinliyorum.")
        after = self.money()
        self.assertNotEqual(before, after)
        index = lambda text: __import__("json").loads(text)["turn_index"]  # noqa: E731
        self.assertEqual(index(after), index(before) + 1)
        undone = await self.undo(turn_id)
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.money(), before)
        self.assertIn("“Tezgâha yaslanıp salonu dinliyorum.”", undone.json()["narration"])


if __name__ == "__main__":
    unittest.main()

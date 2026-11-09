"""Refusal texts (Dilim 2, Task 13): a fight's refusal is Turkish and says why; the HTTP 400 adds the same text as
`public_message`; a refused move becomes a turn note the narrator reads."""
import unittest
from pathlib import Path
from types import SimpleNamespace

import action_economy
import game
import refusals
from combat_lifecycle import CombatRequestError
from api.tests import test_combat_lifecycle as lifecycle

ROOT = Path(__file__).resolve().parents[2]


class RefusalTexts(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = lifecycle.ready()
        self._token = game._ACTIVE_SESSION.set(self.session)
        self.addCleanup(game._ACTIVE_SESSION.reset, self._token)

    def test_ready_without_a_trigger_says_what_is_missing(self):
        with self.assertRaises(CombatRequestError) as raised:
            action_economy.prepare_ready(self.session, "player", trigger=None, response={"kind": "attack"})
        turn = game.combat_refusal_turn(raised.exception)
        self.assertEqual(turn["narration"], refusals.REFUSAL_TEXT["invalid_ready_trigger"])
        self.assertEqual(turn["action_result"]["status"], "fight_refused")

    def test_the_old_vague_line_is_gone(self):
        self.assertNotIn("Dövüşün ortasında bu olmuyor", (ROOT / "game.py").read_text(encoding="utf-8"))
        self.assertFalse(hasattr(game, "_FIGHT_REFUSALS"))
        for code in ("combat_travel", "out_of_turn", "no_weapon", "invalid_ready_trigger"):
            with self.subTest(code=code):
                self.assertEqual(game.combat_refusal_turn(CombatRequestError(code, "English engine text"))["narration"],
                                 refusals.REFUSAL_TEXT[code])

    def test_a_refused_fight_move_is_also_a_note_for_the_narrator(self):
        self.session._turn_notes = []
        game.combat_refusal_turn(CombatRequestError("out_of_turn", "English engine text"))
        self.assertEqual(self.session._turn_notes, [(None, "olmadı: " + refusals.REFUSAL_TEXT["out_of_turn"])])

    def test_note_adds_one_turn_note_with_the_prefix(self):
        session = SimpleNamespace(_turn_notes=[])
        text = refusals.note(session, "no_weapon", npc_id="barman")
        self.assertEqual(session._turn_notes, [("barman", "olmadı: " + refusals.REFUSAL_TEXT["no_weapon"])])
        self.assertEqual(text, session._turn_notes[0][1])
        refusals.note(session, "nothing_to_draw", have="yok")
        self.assertEqual(session._turn_notes[1],
                         (None, "olmadı: istediğin silah çantanda yok; hiçbir şey çekilmedi (çantadaki silahlar: yok)."))
        self.assertFalse(session._turn_notes[1][1].startswith("olmadı: olmadı:"))   # the text already says it

    def test_the_plain_notes_of_the_job_paths_keep_their_words(self):
        session = SimpleNamespace(_turn_notes=[])
        refusals.note(session, "parcel_not_here", item="Paket")
        refusals.note(session, "which_parcel")
        refusals.note(session, "which_item_to_give", npc_id="barman")
        self.assertEqual(session._turn_notes, [
            (None, "olmadı: Paket burada değil"),
            (None, "olmadı: hangi işin eşyasını kastettiğin belli değil"),
            ("barman", "olmadı: hangi eşyayı verdiğin belli değil")])

    def test_an_unknown_code_is_logged_and_still_turkish(self):
        with self.assertLogs("refusals", level="WARNING") as logged:
            self.assertEqual(refusals.text_for("no_such_code"), "Bu hamle şu an işlemedi; başka bir şey dene.")
        self.assertIn("no_such_code", "\n".join(logged.output))


class HttpRefusals(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = lifecycle.CombatLifecycleApiTests.asyncSetUp
    asyncTearDown = lifecycle.CombatLifecycleApiTests.asyncTearDown
    setup_combat = lifecycle.CombatLifecycleApiTests.setup_combat
    request = lifecycle.CombatLifecycleApiTests.request
    post = lifecycle.CombatLifecycleApiTests.post

    async def test_http_refusals_carry_a_turkish_public_message(self):
        session, npc = self.setup_combat()
        response = await self.post(self.request(session, npc, target_id="foreign"))
        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "invalid_combat_target")
        self.assertEqual(detail["message"], "Select one valid local target.")   # unchanged: the tests that pin it stay green
        self.assertEqual(detail["public_message"], refusals.text_for(detail["code"]))


if __name__ == "__main__":
    unittest.main()

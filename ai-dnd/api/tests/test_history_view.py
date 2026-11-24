"""Direct unit tests for api.history_view: an undo is proven only by a receipt, never by the player's own words."""

import unittest

from api import history_view as view

MARK = view.UNDO_HISTORY_MARKER


def _row(message, narration, at="t1"):
    return {"player_message": message, "narration": narration, "created_at": at}


def _receipt(action_id, narration=None, at="t1", **response):
    body = None if narration is None and not response else dict(response, narration=narration)
    return {"action_id": action_id, "created_at": at, "response": body}


class UndoNarrationTests(unittest.TestCase):
    def test_player_words_are_quoted(self):
        text = view.undo_narration("kapıyı kır")
        self.assertIn("“kapıyı kır”", text)
        self.assertTrue(text.endswith("sıradaki hamle senin."))

    def test_slash_command_or_nothing_is_never_quoted(self):
        for message in ("/rest", "", None, "   "):
            with self.subTest(message=message):
                self.assertNotIn("“", view.undo_narration(message))

    def test_card_label_replaces_the_player_message(self):
        text = view.undo_narration("whatever", turn_label="Teklifi onayla.")
        self.assertIn("“Teklifi onayla”", text)
        self.assertNotIn("whatever", text)

    def test_long_words_are_cut(self):
        text = view.undo_narration("x" * 300)
        self.assertIn("x" * 117 + "...", text)
        self.assertNotIn("x" * 118, text)

    def test_purse_movement_is_told_only_when_it_moved(self):
        self.assertIn("Kesene 30 bakır geri döndü.", view.undo_narration("a", 30))
        self.assertIn("Kesenden 5 bakır geri alındı.", view.undo_narration("a", -5))
        for delta in (0, None, "7", 1.5):
            with self.subTest(delta=delta):
                self.assertNotIn("Kese", view.undo_narration("a", delta))


class UndoLinksTests(unittest.TestCase):
    def test_a_receipt_proven_undo_links_to_the_turn_it_undid(self):
        rows = [_row("saldır", "Kılıç iner.", "t1"), _row(MARK, "Geri alındı.", "t2")]
        receipts = [_receipt("a1", "Kılıç iner.", "t1"), _receipt("a2", "Geri alındı.", "t2", undone_action_id="a1")]
        self.assertEqual(view.undo_links(rows, receipts), {1: 0})

    def test_typed_marker_without_a_receipt_proves_nothing(self):
        rows = [_row("saldır", "Kılıç iner.", "t1"), _row(MARK, "Geri alındı.", "t2")]
        self.assertEqual(view.undo_links(rows, [_receipt("a1", "Kılıç iner.", "t1")]), {})

    def test_unknown_target_links_to_none(self):
        rows = [_row(MARK, "Geri alındı.", "t2")]
        receipts = [_receipt("a2", "Geri alındı.", "t2", undone_action_id="missing")]
        self.assertEqual(view.undo_links(rows, receipts), {0: None})

    def test_ambiguous_rows_prove_nothing(self):
        rows = [_row("saldır", "Aynı.", "t1"), _row("saldır", "Aynı.", "t1"), _row(MARK, "Geri.", "t2")]
        receipts = [_receipt("a1", "Aynı.", "t1"), _receipt("a2", "Geri.", "t2", undone_action_id="a1")]
        self.assertEqual(view.undo_links(rows, receipts), {2: None})

    def test_two_undos_claiming_one_row_prove_nothing(self):
        rows = [_row("saldır", "Kılıç.", "t1"), _row(MARK, "Geri.", "t2")]
        receipts = [
            _receipt("a1", "Kılıç.", "t1"),
            _receipt("a2", "Geri.", "t2", undone_action_id="a1"),
            _receipt("a3", "Geri.", "t2", undone_action_id="a1"),
        ]
        self.assertEqual(view.undo_links(rows, receipts), {})

    def test_two_undos_naming_one_turn_resolve_neither(self):
        rows = [_row("saldır", "Kılıç.", "t1"), _row(MARK, "Geri bir.", "t2"), _row(MARK, "Geri iki.", "t3")]
        receipts = [
            _receipt("a1", "Kılıç.", "t1"),
            _receipt("a2", "Geri bir.", "t2", undone_action_id="a1"),
            _receipt("a3", "Geri iki.", "t3", undone_action_id="a1"),
        ]
        self.assertEqual(view.undo_links(rows, receipts), {1: None, 2: None})

    def test_ambient_join_turn_is_found_by_its_join_line(self):
        rows = [_row(view.AMBIENT_JOIN_LINE, "Katıldın.", "t1"), _row(MARK, "Geri.", "t2")]
        receipts = [
            {"action_id": "a1", "created_at": "t1", "response": {"ambient_event_response": {}}},
            _receipt("a2", "Geri.", "t2", undone_action_id="a1"),
        ]
        self.assertEqual(view.undo_links(rows, receipts), {1: 0})


class MarkUndoneTests(unittest.TestCase):
    def test_flags_go_on_a_copy(self):
        history = [{"text": "a"}, {"text": "undo"}, {"text": "c"}]
        marked = view.mark_undone(history, {1: 0})
        self.assertEqual(marked[0], {"text": "a", "undone": True})
        self.assertEqual(marked[1], {"text": "undo", "undo_note": True})
        self.assertEqual(marked[2], {"text": "c"})
        self.assertEqual(history[0], {"text": "a"})

    def test_unproven_target_is_flagged_as_unknown(self):
        marked = view.mark_undone([{"text": "undo"}], {0: None})
        self.assertEqual(marked[0], {"text": "undo", "undo_note": True, "undo_target_unknown": True})


class UndoneCombatEventsTests(unittest.TestCase):
    def _combat(self, action_id, event_id):
        return {"action_id": action_id, "response": {"combat_history_entry": {"event_id": event_id}}}

    def _undo(self, action_id, target):
        return {"action_id": action_id, "response": {"undone_action_id": target}}

    def test_event_of_the_named_turn_is_returned(self):
        receipts = [self._combat("a1", "ev.1"), self._undo("a2", "a1")]
        self.assertEqual(view.undone_combat_events(receipts), {"ev.1"})

    def test_turn_named_twice_or_held_by_two_receipts_marks_nothing(self):
        twice = [self._combat("a1", "ev.1"), self._undo("a2", "a1"), self._undo("a3", "a1")]
        self.assertEqual(view.undone_combat_events(twice), set())
        held = [self._combat("a1", "ev.1"), self._combat("a1", "ev.2"), self._undo("a2", "a1")]
        self.assertEqual(view.undone_combat_events(held), set())

    def test_turn_without_a_combat_entry_marks_nothing(self):
        receipts = [{"action_id": "a1", "response": {"narration": "x"}}, self._undo("a2", "a1")]
        self.assertEqual(view.undone_combat_events(receipts), set())
        self.assertEqual(view.undone_combat_events([]), set())


if __name__ == "__main__":
    unittest.main()

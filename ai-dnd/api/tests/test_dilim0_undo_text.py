"""Dilim 0 (52, EK 6/6): the undo sentence never quotes a raw command; the undone turn is found by its receipt link."""
from __future__ import annotations

import asyncio
import sqlite3
import unittest

import httpx

from api.auth import FixedAuthenticator
from api.history_view import UNDO_HISTORY_MARKER, mark_undone, undo_links, undo_narration
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from api.tests.test_economic_action_http import TIP, EconomicHttpFixture

T1, T2, T3 = "2026-11-04T10:00:01+00:00", "2026-11-04T10:00:02+00:00", "2026-11-04T10:00:03+00:00"
UNDO_TEXT = undo_narration("")


def row(message, narration, at):
    return {"player_message": message, "narration": narration, "created_at": at}


def receipt(action_id, at, narration, undone=None):
    response = {"action_id": action_id, "narration": narration}
    if undone is not None:
        response["undone_action_id"] = undone
    return {"action_id": action_id, "created_at": at, "response": response}


class UndoSentence(unittest.TestCase):
    def test_a_slash_command_is_never_quoted(self):
        for message in ("/item shop_buy barman bira 1 0 4", "  /travel stop", ""):
            text = undo_narration(message)
            self.assertTrue(text.startswith("Son tur geri alındı"))
            self.assertNotIn("/", text); self.assertNotIn("shop_buy", text); self.assertNotIn("“", text)

    def test_free_words_are_quoted_as_today(self):
        self.assertEqual(undo_narration("barmene selam veriyorum"),
            "Son tur geri alındı: “barmene selam veriyorum” ve sonuçları yaşanmamış sayılıyor. "
            "Dünya o turdan önceki hâline döndü; sıradaki hamle senin.")
        self.assertIn("“" + "a" * 117 + "...”", undo_narration("a" * 200))


class UndoLinks(unittest.TestCase):
    def test_the_marker_points_at_its_own_turn_not_the_row_before_it(self):
        # buy (T), then prepare a card (P, same second), then undo T: the history is [T, P, marker]
        rows = [row("/item shop_buy barman bira 1 0 4", "Bira aldın.", T1), row("Teklif hazırla", "Kart hazır.", T1),
                row(UNDO_HISTORY_MARKER, UNDO_TEXT, T2)]
        receipts = [receipt("t", T1, "Bira aldın."), receipt("p", T1, "Kart hazır."),
                    receipt("u", T2, UNDO_TEXT, undone="t")]
        links = undo_links(rows, receipts)
        self.assertEqual(links, {2: 0})
        out = mark_undone(rows, links)
        self.assertEqual([x.get("undone", False) for x in out], [True, False, False])
        self.assertEqual([x.get("undo_note", False) for x in out], [False, False, True])
        self.assertNotIn("undone", rows[0])  # input untouched

    def test_each_undo_marks_its_own_turn(self):
        rows = [row("a", "A", T1), row("b", "B", T1), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T2),
                row("c", "C", T2), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T3), row("d", "D", T3)]
        receipts = [receipt("a", T1, "A"), receipt("b", T1, "B"), receipt("u1", T2, UNDO_TEXT, undone="b"),
                    receipt("c", T2, "C"), receipt("u2", T3, UNDO_TEXT, undone="c"), receipt("d", T3, "D")]
        self.assertEqual(undo_links(rows, receipts), {2: 1, 4: 3})

    def test_a_verified_undo_without_a_provable_target_says_so(self):
        # decision 37: the undo receipt proves the undo; the target cannot be proven, so nothing is faded by guess
        rows = [row("a", "A", T1), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T2)]
        for receipts in ([receipt("u", T2, UNDO_TEXT, undone="a")],         # target receipt archived or missing
                         [receipt("a", T1, "başka"), receipt("u", T2, UNDO_TEXT, undone="a")]):  # narration differs
            links = undo_links(rows, receipts)
            self.assertEqual(links, {1: None})
            self.assertEqual(mark_undone(rows, links),
                             [rows[0], {**rows[1], "undo_note": True, "undo_target_unknown": True}])

    def test_marker_text_without_an_undo_receipt_is_not_an_undo(self):
        # decision 36: the player can type the marker text; only an undo receipt makes a row an undo
        rows = [row("a", "A", T1), row(UNDO_HISTORY_MARKER, "Barmen omuz silker.", T2)]
        for receipts in ([],                                                                    # no receipt (or archived)
                         [receipt("a", T1, "A")],
                         [receipt("a", T1, "A"), receipt("f", T2, "Barmen omuz silker.")],      # its own ordinary turn
                         [receipt("a", T1, "A"), receipt("u", T3, UNDO_TEXT, undone="a")]):     # an undo of another row
            links = undo_links(rows, receipts)
            self.assertEqual(links, {})
            self.assertEqual(mark_undone(rows, links), rows)

    def test_an_ambiguous_link_marks_nothing(self):
        rows = [row("a", "Aynı.", T1), row("a", "Aynı.", T1), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T2)]
        receipts = [receipt("a1", T1, "Aynı."), receipt("a2", T1, "Aynı."), receipt("u", T2, UNDO_TEXT, undone="a2")]
        self.assertEqual(undo_links(rows, receipts), {2: None})      # the undo is proven, its turn is not
        # two undo receipts claiming one marker row: the row is not proven
        rows = [row("a", "A", T1), row("b", "B", T1), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T2)]
        receipts = [receipt("a", T1, "A"), receipt("b", T1, "B"),
                    receipt("u1", T2, UNDO_TEXT, undone="a"), receipt("u2", T2, UNDO_TEXT, undone="b")]
        self.assertEqual(undo_links(rows, receipts), {})

    def test_two_undos_of_one_turn_mark_nothing(self):
        # decision 38: a double target is never resolved by guess
        rows = [row("a", "A", T1), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T2), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T3)]
        receipts = [receipt("a", T1, "A"), receipt("u1", T2, UNDO_TEXT, undone="a"), receipt("u2", T3, UNDO_TEXT, undone="a")]
        links = undo_links(rows, receipts)
        self.assertEqual(links, {1: None, 2: None})
        self.assertEqual([x.get("undone", False) for x in mark_undone(rows, links)], [False, False, False])

    def test_a_turn_and_its_undo_in_the_same_second(self):
        rows = [row("a", "A", T1), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T1)]
        receipts = [receipt("a", T1, "A"), receipt("u", T1, UNDO_TEXT, undone="a")]
        self.assertEqual(undo_links(rows, receipts), {1: 0})

    def test_prepare_and_cancel_rows_between_are_not_the_undone_turn(self):
        rows = [row("/item shop_buy barman bira 1 0 4", "Bira aldın.", T1), row("Teklif hazırla", "Kart hazır.", T1),
                row("Teklifi geri çek", "Kart kapandı.", T2), row(UNDO_HISTORY_MARKER, UNDO_TEXT, T2)]
        receipts = [receipt("t", T1, "Bira aldın."), receipt("p", T1, "Kart hazır."), receipt("c", T2, "Kart kapandı."),
                    receipt("u", T2, UNDO_TEXT, undone="t")]
        self.assertEqual(undo_links(rows, receipts), {3: 0})


class UndoOverHttp(EconomicHttpFixture):
    async def test_the_flags_reach_detail_and_resume_but_never_the_save(self):
        campaign_id = self.campaign["campaign_id"]
        turn_id, played = await self.real_turn()
        await self.card(**TIP)                       # a prepare row lands between the turn and the undo
        undone = await self.undo(turn_id)
        self.assertEqual(undone.status_code, 200, undone.text)
        detail = await self.http.get(f"/api/game/campaigns/{campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        history = detail.json()["history"]
        turn_row = max(i for i, h in enumerate(history) if h["narration"] == played["narration"])
        self.assertEqual([i for i, h in enumerate(history) if h.get("undone")], [turn_row])
        self.assertEqual(history[-2]["player_message"], "Teklif hazırla")
        self.assertNotIn("undone", history[-2])      # the prepare row is not the undone turn
        self.assertEqual(history[-1]["player_message"], UNDO_HISTORY_MARKER)
        self.assertIs(history[-1]["undo_note"], True)
        self.assertNotIn("undone", history[-1])
        # resume (a fresh manager, as test_lr00_p7_undo.test_no_undo_after_restart) carries the same flags
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        app = create_app(session_manager=manager, ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["history"], history)
        # the save is untouched: same history columns, no flag in the stored payload
        with sqlite3.connect(self.store.path) as db:
            columns = {r[1] for r in db.execute("PRAGMA table_info(campaign_history)")}
            payload = db.execute("SELECT payload_json FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()[0]
        self.assertEqual(columns, {"campaign_id", "sequence", "player_message", "narration", "created_at"})
        self.assertNotIn('"undone"', payload)
        self.assertNotIn('"undo_note"', payload)
        self.assertNotIn('"undo_target_unknown"', payload)

    async def test_a_player_typing_the_marker_is_not_shown_as_an_undo(self):
        # decision 36, the forged-marker counter-test over the real write path (main.py records the message as typed)
        campaign_id = self.campaign["campaign_id"]
        await self.real_turn(UNDO_HISTORY_MARKER)
        history = (await self.http.get(f"/api/game/campaigns/{campaign_id}")).json()["history"]
        typed = [h for h in history if h["player_message"] == UNDO_HISTORY_MARKER]
        self.assertEqual(len(typed), 1, history)
        self.assertFalse({"undone", "undo_note", "undo_target_unknown"} & set(typed[0]), typed[0])
        self.assertEqual([h for h in history if h.get("undone") or h.get("undo_note")], [])

    async def test_a_second_undo_in_a_row_is_refused_and_writes_nothing(self):
        # decision 38: the engine undoes one step (main.py "One step only"); the second undo writes no row
        campaign_id = self.campaign["campaign_id"]
        url = f"/api/game/campaigns/{campaign_id}"
        first_id, _ = await self.real_turn()
        await asyncio.sleep(1.1)  # created_at has one-second resolution: keep the two turns apart
        second_id, second = await self.real_turn("Kapıya doğru bakıyorum.")
        self.assertEqual((await self.undo(second_id)).status_code, 200)
        before = (await self.http.get(url)).json()["history"]
        again = await self.undo(first_id)
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["detail"]["code"], "undo_unavailable")
        history = (await self.http.get(url)).json()["history"]
        self.assertEqual(history, before)
        self.assertEqual([h["player_message"] for h in history].count(UNDO_HISTORY_MARKER), 1)
        second_row = max(i for i, h in enumerate(history) if h["player_message"] == "Kapıya doğru bakıyorum.")
        self.assertEqual([i for i, h in enumerate(history) if h.get("undone")], [second_row])
        self.assertIs(history[-1]["undo_note"], True)
        self.assertNotIn("undo_target_unknown", history[-1])

    async def test_archiving_the_target_shows_the_undo_as_unverifiable(self):
        # decision 37: before and after the receipt archive (compact_receipts is called only by tests today)
        campaign_id = self.campaign["campaign_id"]
        url = f"/api/game/campaigns/{campaign_id}"
        turn_id, _ = await self.real_turn()
        self.assertEqual((await self.undo(turn_id)).status_code, 200)
        before = (await self.http.get(url)).json()["history"]
        self.assertEqual(sum(1 for h in before if h.get("undone")), 1)
        revision = self.store.get_campaign(campaign_id).metadata["revision"]
        self.store.compact_receipts(campaign_id, before_revision=revision + 1)  # keep_latest=1: the undo receipt stays
        kept = (await self.http.get(url)).json()["history"]
        self.assertEqual([h for h in kept if h.get("undone")], [])
        self.assertIs(kept[-1]["undo_note"], True)
        self.assertIs(kept[-1]["undo_target_unknown"], True)
        self.store.compact_receipts(campaign_id, before_revision=revision + 1, keep_latest=0)  # the undo receipt too
        bare = (await self.http.get(url)).json()["history"]
        self.assertEqual(bare[-1]["player_message"], UNDO_HISTORY_MARKER)
        self.assertFalse({"undone", "undo_note", "undo_target_unknown"} & set(bare[-1]), bare[-1])
        rows = lambda hs: [(h["player_message"], h["narration"], h["created_at"]) for h in hs]
        self.assertEqual(rows(bare), rows(before))  # the stored rows never change, only the read flags


if __name__ == "__main__":
    unittest.main()

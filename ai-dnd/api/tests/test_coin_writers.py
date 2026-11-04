"""Who may move coin: the full list of coin writers is pinned, and a turn of each open kind moves coin only by its own.

A new function that writes world['currency'], or calls pay() or give_coin(), fails the first test until it is
named here on purpose. Every coin a turn moves (a room, a gift, a tip, a bribe, a wage, an NPC's own give and the
counter sale) goes through the one owner, economic_actions.apply_resolution; talk only opens a card, and only its
confirmation pays. The word-match purchase, the speech give of a vendor and the coin put down with an order write
nothing. Counts come from the ledger and the purses, never from the length of the log.
"""
from __future__ import annotations

import ast
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bold_acts
import economic_actions as ea
import game
from api.core_resolution import resolution_action_scope
from money_owner import CoinDecision

ROOT = Path(__file__).resolve().parents[2]

# file:function for every coin writer in the product source; open paths stay open by the owner's scope.
WRITERS = frozenset({
    "equipment_economy.py:pay",                  # the one debit/credit primitive the owners call
    "equipment_economy.py:_apply",               # typed catalog buy, sell and item reward
    "bold_acts.py:settle_coin_labels",           # gold written in the pack becomes purse copper
    "bold_acts.py:_steal",                       # pickpocketed coin
    "bold_acts.py:_search_body",                 # coin found on a body
    "world_reactions.py:give_up",                # the fine on surrender
    "adventure/rewards.py:apply_plan",           # quest and delivery pay
    "incidents/rewards.py:_wallet_source",       # the incident's source purse
    "incidents/rewards.py:grant",                # incident coin reward
    "api/character_creation.py:configure_character",  # the starting purse
    "economic_actions.py:apply_resolution",      # the one owner of confirmed economic effects
})


def _writers() -> set[str]:
    found = set()
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in f"/{rel}" or rel.startswith(("legacy_debug/", "docs/")) or "__pycache__" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(ast.walk(node))
            wallets = {target.id for sub in body if isinstance(sub, ast.Assign) and "currency" in ast.unparse(sub.value)
                       for target in sub.targets if isinstance(target, ast.Name)}
            for sub in body:
                targets = (sub.targets if isinstance(sub, ast.Assign)
                           else [sub.target] if isinstance(sub, ast.AugAssign) else [])
                writes = any(isinstance(target, ast.Subscript) and (
                    "currency" in ast.unparse(target.value)
                    or isinstance(target.value, ast.Name) and target.value.id in wallets) for target in targets)
                call = isinstance(sub, ast.Call) and (
                    getattr(sub.func, "attr", None) or getattr(sub.func, "id", None)) in {"pay", "give_coin"}
                if writes or call:
                    found.add(f"{rel}:{node.name}")
                    break
    return found


class TheCoinWritersArePinned(unittest.TestCase):
    def test_every_coin_writer_is_named(self):
        self.assertEqual(sorted(_writers()), sorted(WRITERS))


class Watched(dict):
    """The purse map that notes which pinned writer touched it."""

    log: list = []

    def __setitem__(self, key, value):
        copying = sys._getframe(1).f_code.co_filename.endswith("copy.py")  # a candidate copy moves no coin
        if not copying and self.get(key) != value:
            Watched.log.append(_writer_on_stack())
        super().__setitem__(key, value)


def _writer_on_stack() -> str:
    frame = sys._getframe(2)
    while frame is not None:
        path = Path(frame.f_code.co_filename).resolve()
        if ROOT in path.parents and "tests" not in path.relative_to(ROOT).parts:
            name = f"{path.relative_to(ROOT).as_posix()}:{frame.f_code.co_name}"
            if name in WRITERS:
                return name
        frame = frame.f_back
    return "unknown"


class EachOpenPathMovesCoinOnlyByItsOwnWriter(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session()
        self.w = self.s.world_state
        self.w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.w["location"], "current_hp": 10},
            {"id": "guest", "name": "Oren", "role": "Yolcu", "location": self.w["location"], "current_hp": 10},
        ]
        self.w["currency"] = Watched({"player": 500, "barman": 100, "guest": 100})
        Watched.log = []
        self.chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        self.chat.start()
        self.addCleanup(self.chat.stop)

    def moved_by(self, *writers):
        self.assertEqual(set(Watched.log), set(writers), Watched.log)
        self.assertTrue(Watched.log if writers else True)

    def test_the_counter_trade(self):
        result = self.s.run_player_turn("/item shop_buy barman bira 1 0 4")
        self.assertTrue(result["action_result"]["success"], result["narration"])
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"]), (496, 104))
        self.moved_by("equipment_economy.py:pay")

    def offers(self):
        return self.w.get("flags", {}).get("economic_offers", {})

    def prepared(self):
        return [data for data in self.offers().values() if data["status"] == "prepared"]

    def operations(self):
        return self.w.get("flags", {}).get("economic_ledger", {}).get("operations", {})

    def confirm(self, data, action):
        with resolution_action_scope(action, "session"):
            return ea.confirm_offer(ea.EconomicState(world=self.w, character=self.s.character),
                                    offer_id=data["offer_id"], confirmation_digest=data["confirmation_digest"],
                                    operation_id=f"offer:{action}", check=lambda skill, dc: "BAŞARILI")

    def test_an_order_with_coin_put_down_moves_nothing(self):
        self.s._coin_paid = (100, self.w["npcs"][0], self.w["location"])
        result = self.s.run_player_turn("al şu bi altını, bi bira ver usta")
        self.assertEqual(result["action_result"]["action"], "shop_offer", result["narration"])
        self.assertEqual(self.w["flags"]["counter_offer_v1"]["tender_cp"], 100)
        self.moved_by()

    def gift_held_out(self, amount):
        """Coin held out to the guest with the money owner's gift decision, as the reading leaves them."""
        self.s._coin_decision = CoinDecision("gift", "guest", amount, 0, None, "model", self.w["location"])
        self.s._coin_paid = (amount, self.w["npcs"][1], self.w["location"])

    def test_a_coin_handed_with_no_order_is_a_gift(self):
        self.gift_held_out(5)
        self.s.run_player_turn("/item list")
        self.moved_by()  # the turn only opens the card
        [card] = self.prepared()
        self.assertEqual(self.confirm(card, "a-gift-confirm").status, "applied")
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guest"]), (495, 105))
        self.moved_by("equipment_economy.py:pay")

    def test_a_room(self):
        self.s.run_player_turn("bi oda tutayım usta")
        self.moved_by()  # the line opens the card; nothing is paid before it is confirmed
        [card] = self.prepared()
        self.assertEqual(self.confirm(card, "a-room-confirm").status, "applied")
        self.assertEqual(self.w["currency"]["player"], 500 - bold_acts._ROOM_PRICE)
        self.moved_by("economic_actions.py:apply_resolution")  # the room is a sink: nobody is paid, the total is kept

    def test_room_walk_has_one_economic_writer(self):
        self.s._economic_turn_key = "a-walk"
        walked = {"narration": "Hana giriyorsun.", "action_result": {"action": "move", "status": "completed",
                                                                     "state_changes": ["location"]}}
        game._sleep_after_walk(walked, "hana gidip bi oda tutayım", "the-street", None, session=self.s)
        self.moved_by()
        [card] = self.prepared()
        self.confirm(card, "a-walk-confirm")
        self.assertEqual(len(self.operations()), 1)
        self.assertEqual(self.w["currency"]["player"], 500 - bold_acts._ROOM_PRICE)
        self.assertEqual(self.w["currency"]["barman"], 100)
        self.moved_by("economic_actions.py:apply_resolution")

    def test_room_question_has_zero_writers(self):
        result = self.s.run_player_turn("bi gecelik oda ne kadar?")
        self.assertIn("5 gümüş", result["narration"])
        self.assertEqual(self.offers(), {})
        self.assertEqual(self.operations(), {})
        self.moved_by()

    def test_room_and_coin_offer_no_legacy_debit(self):
        self.s._coin_paid = (100, self.w["npcs"][0], self.w["location"])
        self.s.run_player_turn("hancıya 1 altın verip oda tutuyorum")
        self.moved_by()
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", 100))
        resolution = self.confirm(card, "a-room-coin-confirm")
        self.assertEqual((resolution.net_debit_cp, resolution.change_cp), (50, 50))
        self.assertEqual(len(self.operations()), 1)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"]), (450, 100))
        self.moved_by("economic_actions.py:apply_resolution")

    def test_unconfirmed_false_proposal_changes_no_relationship_or_clock(self):
        self.gift_held_out(5)
        before = (dict(self.w["currency"]), copy.deepcopy(self.w.get("relationships")),
                  copy.deepcopy(self.w.get("campaign_time")))
        self.s.run_player_turn("/item list")
        [card] = self.prepared()
        self.assertTrue(ea.cancel_offer(self.w, offer_id=card["offer_id"]))
        self.assertEqual((dict(self.w["currency"]), self.w.get("relationships"), self.w.get("campaign_time")), before)
        self.assertEqual(self.operations(), {})
        self.moved_by()

    def test_a_theft(self):
        with patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI", "skill": "Sleight of Hand",
                                                             "dc": 10, "roll": 20, "total": 20}), \
                patch("game._skill_result_category", return_value="success"):
            result = bold_acts._steal(self.s, "Oren'in kesesini aşırıyorum")
        self.assertEqual(result["action_result"]["status"], "stolen")
        self.moved_by("bold_acts.py:_steal")

    def test_a_spoken_give_from_someone_who_does_not_serve(self):
        import town_knowledge
        settled = town_knowledge.settle_reply(self.w, self.w["npcs"][1], "paramı ver hadi", {"kind": "give", "amount_cp": 5},
                                              "Al bakalım.", accept_job=lambda thread: None)
        self.assertEqual(settled["moved"], 5)
        self.moved_by("equipment_economy.py:pay")
        [(operation_id, entry)] = self.operations().items()
        self.assertEqual(entry["purpose"], "npc_gift")
        self.assertTrue(operation_id.startswith("unscoped:economic:npc_gift:"), operation_id)

    def test_a_spoken_give_from_whoever_serves_moves_nothing(self):
        import town_knowledge
        for raw in ({"kind": "give", "amount_cp": 96, "item": "Bira"}, {"kind": "give", "amount_cp": 30, "item": "Ekmek peynir"}):
            settled = town_knowledge.settle_reply(self.w, self.w["npcs"][0], "üstümü ver hadi", raw, "Al.",
                                                  accept_job=lambda thread: None)
            self.assertEqual(settled["moved"], 0)
        self.moved_by()

    def test_a_catalog_buy(self):
        self.w["npcs"][0]["inventory"] = ["Hançer"]
        self.w["shops"] = [{"id": "shop", "location": self.w["location"], "shopkeeper_id": "barman"}]
        self.s.run_player_turn("/item list")
        dagger = self.w["npcs"][0]["inventory"][0]["item_id"]
        self.w["shops"][0]["item_offers_cp"] = {dagger: 200}
        Watched.log = []
        self.assertTrue(self.s.run_player_turn(f"/item buy {dagger} shop")["action_result"]["success"])
        self.moved_by("equipment_economy.py:pay")


if __name__ == "__main__":
    unittest.main()

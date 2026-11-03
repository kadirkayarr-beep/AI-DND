"""Step 0: one long Turkish coin-ledger play, with the books checked after every single action.

Real FastAPI app, real SessionManager and a temporary SQLite campaign store; the model boundary is the project's fake
client (`PlayClient`, the scripted NPC speech client), so no real model is called. The play buys at the counter,
takes a room with a tip, walks to the inn and sleeps, tips and gives (confirm, cancel, double confirm), meets a
refused gift and a bribe under arrest, works a paid day, undoes a confirm and confirms again, meets a stale card
after a reprice, replays old action ids, gives a valuable and a plain item with `/item give`, and flees a fight.

After every action: the coin held by the player, every NPC wallet and every sink equals the starting total plus the
wage the engine paid (the only declared source); the player's purse equals the ledger this test keeps on its own;
no item instance exists twice; and a fresh SessionManager on the same database resumes the same purse and pack.
"""

from __future__ import annotations

import json
import re
import uuid
from unittest.mock import patch

import bold_acts
import equipment_economy
import living_world
import local_places
import shop_trade
import world_threads
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
from api.tests.test_three_plays import FIGHTER, PlayClient, ThreePlaysTests

HOUR = 3600
DAY = 86400
START_PURSE = 2400
_LABEL = re.compile(r"(\d+) (?:Altın|GP)")


def coin_in_labels(world):
    """Coin still written in a pack as "8 Altın": money the next spend turns into the purse."""
    total = 0
    for _owner, items in equipment_economy.containers(world):
        for item in items if isinstance(items, list) else []:
            name = item.get("name") if isinstance(item, dict) else item
            match = _LABEL.fullmatch(str(name))
            if match:
                total += int(match.group(1)) * 100
    return total


def pack(world):
    """Who holds which item, as plain data: the same after a reload, or the save lost something."""
    owners = {}
    for owner, items in equipment_economy.containers(world):
        listed = sorted(str(item.get("item_id") or item.get("name")) if isinstance(item, dict) else str(item)
                        for item in (items if isinstance(items, list) else []))
        if listed:
            owners[str(owner)] = listed
    return owners


class CoinLedgerPlay(ThreePlaysTests):
    async def asyncSetUp(self):
        await ThreePlaysTests.asyncSetUp(self)
        self.log = []          # (step, label, player, npcs, sinks, total, expected_total, expected_purse)
        self.expected_purse = START_PURSE
        self.minted = 0        # wage paid from the day's pool: the one declared source of new coin
        self.step_no = 0

    # --- the world --------------------------------------------------------------------------------------------

    @property
    def w(self):
        return self.session.world_state  # a turn may swap the dicts for committed copies; read it fresh

    def npc(self, npc_id):
        return next(npc for npc in self.w["npcs"] if npc["id"] == npc_id)

    async def build(self):
        await self.begin(FIGHTER)
        self.campaign_id = self.manager.get(self.session_id).campaign_id
        world = self.w
        world["npcs"].clear()
        self.city = world["location"]
        self.place = local_places.create_local_place(world, self.city, "smithy", name="Göl Sofrası Hanı")
        self.place.update(scene_kind="tavern", place_kind="tavern")
        bold_acts.settle_coin_labels(world)
        world["location"] = self.place["id"]
        self.add_person("Dorn", "Barmen", inventory=[], wares_v1={"bira": {"stock": 5}})
        self.add_person("Ilgin", "Çiftçi", inventory=[])
        self.add_person("Hale", "Muhafız", inventory=[])
        self.add_person("Kalila", "Kâhya", inventory=[])
        world["location"] = self.city
        world["currency"] = {"player": START_PURSE, "npc_dorn": 100, "npc_ilgin": 20, "npc_hale": 10,
                             "npc_kalila": 0}
        world["inventory"] = [*world.get("inventory", []),
                              {"item_id": "item_play_ring", "name": "Kırık halka"},
                              {"item_id": "item_play_wand", "name": "Asa", "magical": True}]
        equipment_economy.materialize(world)
        self.session.character.update(current_hp=5)
        self.save()
        self.start_total = self.coin_total()
        self.assertEqual(coin_in_labels(self.w), 0)

    def save(self):
        self.manager.save_campaign(self.campaign_id)

    def sinks(self):
        totals = (self.w.get("flags", {}).get("economic_ledger") or {}).get("sink_totals") or {}
        return sum(value for value in totals.values() if type(value) is int)

    def npc_coin(self):
        return sum(amount for owner, amount in (self.w.get("currency") or {}).items()
                   if owner != "player" and type(amount) is int)

    def purse(self):
        return self.w["currency"]["player"]

    def coin_total(self):
        return self.purse() + self.npc_coin() + self.sinks() + coin_in_labels(self.w)

    def offers(self):
        return self.w.get("flags", {}).get("economic_offers", {})

    def offer_status(self, offer_id):
        return self.offers().get(offer_id, {}).get("status")

    # --- the books after every action ------------------------------------------------------------------------

    def reloaded(self):
        """A new SessionManager on the same database: what a restart would give the player back."""
        fresh = SessionManager(campaign_store=self.store)
        _sid, record, *_ = fresh.resume_campaign(self.campaign_id, principal=TEST_PLAYER)
        return record.game_session.world_state

    def books(self, label, paid=0):
        """Checks the four promises after one action; `paid` is what this action took from the purse (+ gives)."""
        self.step_no += 1
        self.expected_purse -= paid
        world = self.w
        total = self.coin_total()
        expected_total = self.start_total + self.minted
        self.log.append((self.step_no, label, self.purse(), self.npc_coin(), self.sinks(), total, expected_total,
                         self.expected_purse))
        where = f"step {self.step_no} ({label})"
        self.assertEqual(total, expected_total, f"{where}: coin was made or lost")
        self.assertEqual(self.purse() + coin_in_labels(world), self.expected_purse, f"{where}: purse off the ledger")
        ids = [item.get("item_id") for _owner, items in equipment_economy.containers(world)
               for item in (items if isinstance(items, list) else []) if isinstance(item, dict) and item.get("item_id")]
        self.assertEqual(sorted(ids), sorted(set(ids)), f"{where}: an item exists twice")
        for tracked in ("item_play_ring", "item_play_wand"):
            self.assertEqual(ids.count(tracked), 1, f"{where}: {tracked} is not held exactly once")
        stored = self.reloaded()
        self.assertEqual(stored["currency"].get("player"), self.purse(), f"{where}: the save lost the purse")
        self.assertEqual(pack(stored), pack(world), f"{where}: the save lost the pack")

    # --- the HTTP actions ------------------------------------------------------------------------------------

    async def post(self, body, client=None):
        response = await self.post_scene_turn(self.url, client or PlayClient(), body)
        self.assertEqual(response.status_code, 200, f"{body.get('message')!r}: {response.text[:600]}")
        return response.json()

    async def line(self, message, client=None):
        body = {"message": message, "action_id": str(uuid.uuid4())}
        return await self.post(body, client), body

    async def prepare(self, **proposal):
        body = {"message": "Teklif hazırla", "action_id": str(uuid.uuid4()),
                "economic_action": {"kind": "prepare", "proposal": proposal}}
        return await self.post(body)

    async def card(self, **proposal):
        prepared = await self.prepare(**proposal)
        card = prepared["state"]["economic_offer"]
        self.assertIsNotNone(card, prepared["narration"])
        return card

    async def confirm(self, card, action_id=None):
        body = {"message": "Teklifi onayla", "action_id": action_id or str(uuid.uuid4()),
                "economic_action": {"kind": "confirm", "offer_id": card["offer_id"],
                                    "confirmation_digest": card["confirmation_digest"]}}
        answered = await self.post(body)
        return answered, answered["economic_resolution"], body

    async def cancel(self, card):
        body = {"message": "Teklifi iptal et", "action_id": str(uuid.uuid4()),
                "economic_action": {"kind": "cancel", "offer_id": card["offer_id"]}}
        return await self.post(body)

    async def undo(self, target):
        response = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                        json={"action_id": str(uuid.uuid4()), "target_action_id": target})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def assert_refused(self, resolution, reason):
        self.assertEqual((resolution["status"], resolution["reason_code"], resolution["net_debit_cp"]),
                         ("refused", reason, 0), resolution)

    # --- the play --------------------------------------------------------------------------------------------

    async def test_a_long_play_keeps_every_coin(self):
        await self.build()
        try:
            await self.play()
        finally:
            self.report()

    def report(self):
        print("\nSTEP0_LEDGER_PLAY step | action | player | npcs | sinks | total | expected_total | expected_purse")
        for row in self.log:
            print("STEP0_LEDGER_PLAY " + " | ".join(str(value) for value in row))

    async def play(self):
        # 1. Walk to the inn from the street.
        out, _ = await self.line("neyse hana gidiyorum")
        self.assertEqual(self.w["location"], self.place["id"], out["narration"])
        self.books("hana yürü")

        # 2. Buy a beer at the counter: 4 copper to the barman.
        seq = (self.w.get(shop_trade.KEY) or {}).get("seq", 0)
        out, buy_body = await self.line(f"/item shop_buy npc_dorn bira 1 {seq} 4")
        self.assertEqual(out["turn_outcome"]["status"], "resolved", out)
        self.books("tezgâhtan bira al", paid=4)
        self.assertIn("Bira", [equipment_economy.label(item) for item in self.w["inventory"]])
        bought = out

        # 3. Refresh: the same purchase action id answers with its receipt and buys nothing.
        replay = await self.post(buy_body)
        self.assertEqual(replay, bought)
        self.books("aynı satın alma kimliğini yenile")

        # 4-5. A room card, then the inn reprices before the confirm: the card is stale and costs nothing.
        stale = await self.card(purpose="room", recipient_id="npc_dorn")
        self.books("oda kartı hazırla")
        with patch("bold_acts._ROOM_PRICE", 60):
            _, resolution, _ = await self.confirm(stale)
        self.assert_refused(resolution, "stale")
        self.assertEqual(self.offer_status(stale["offer_id"]), "cancelled")
        self.books("fiyat değişti, eski oda kartını onayla")

        # 6-7. Room plus tip: 50 to the inn's sink, 5 to the barman.
        room = await self.card(purpose="room", recipient_id="npc_dorn", tip_cp=5)
        self.books("oda + bahşiş kartı hazırla")
        _, resolution, room_body = await self.confirm(room)
        self.assertEqual((resolution["status"], resolution["net_debit_cp"]), ("applied", 55), resolution)
        self.assertTrue(self.w["flags"].get("inn_room"))
        self.books("oda + bahşişi onayla", paid=55)

        # 8. The same card confirmed again by a new action: nothing is paid twice.
        _, resolution, _ = await self.confirm(room)
        self.assert_refused(resolution, "offer_not_prepared")
        self.books("oda kartını ikinci kez onayla")

        # 9. Sleep in the room already paid for.
        out, _ = await self.line("sabaha kadar uyuyorum")
        self.assertEqual(self.session.character["current_hp"], self.session.character["max_hp"], out["narration"])
        self.books("odada sabaha kadar uyu")

        # 10-11. A tip card and its confirm.
        tip = await self.card(purpose="tip", recipient_id="npc_dorn", amount_cp=4)
        self.books("bahşiş kartı hazırla")
        first, resolution, tip_body = await self.confirm(tip)
        self.assertEqual(resolution["status"], "applied", resolution)
        self.books("bahşişi onayla", paid=4)

        # 12. Undo the confirm: the purse comes back and the card is open again.
        undone = await self.undo(tip_body["action_id"])
        self.assertEqual(undone["state"]["economic_offer"]["offer_id"], tip["offer_id"])
        self.books("bahşiş onayını geri al", paid=-4)

        # 13. Confirm again with a new action: paid once, net.
        _, resolution, _ = await self.confirm(tip)
        self.assertEqual(resolution["status"], "applied", resolution)
        self.books("bahşişi yeniden onayla", paid=4)

        # 14. Refresh the undone confirm's old id: its historical answer, no second payment.
        replay = await self.post(tip_body)
        self.assertEqual(replay, first)
        self.books("geri alınan eski onay kimliğini yenile")

        # 15-17. A gift card, cancelled, then its stale id confirmed: nothing moves.
        gift = await self.card(purpose="gift", recipient_id="npc_ilgin", amount_cp=10)
        self.books("hediye kartı hazırla")
        cancelled = await self.cancel(gift)
        self.assertIsNone(cancelled["state"]["economic_offer"])
        self.books("hediye kartını iptal et")
        _, resolution, _ = await self.confirm(gift)
        self.assert_refused(resolution, "offer_not_prepared")
        self.books("iptal edilen hediyeyi onayla")

        # 18-20. A gift card confirmed, and confirmed a second time.
        gift = await self.card(purpose="gift", recipient_id="npc_ilgin", amount_cp=10)
        self.books("yeni hediye kartı hazırla")
        _, resolution, _ = await self.confirm(gift)
        self.assertEqual((resolution["status"], resolution["net_debit_cp"]), ("applied", 10), resolution)
        self.books("hediyeyi onayla", paid=10)
        _, resolution, _ = await self.confirm(gift)
        self.assert_refused(resolution, "offer_not_prepared")
        self.books("hediyeyi ikinci kez onayla")

        # 21. The guard who can tie the player to a theft refuses a gift: no card, no coin.
        deed = {"kind": "theft", "at": 120, "location": self.place["id"], "text": "Tezgâhtan kese çalındı",
                "described": ["npc_hale"], "witnesses": [], "told": [], "heard": [], "seen_near": [],
                "challenged": ["npc_hale"]}
        self.w.setdefault("flags", {}).setdefault("deeds", []).append(deed)
        self.save()
        refused = await self.prepare(purpose="gift", recipient_id="npc_hale", amount_cp=30)
        self.assertEqual(refused["turn_outcome"]["status"], "refused", refused["turn_outcome"])
        self.assertIsNone(refused["state"]["economic_offer"])
        self.books("muhafız hediyeyi reddeder")

        # 22. Under arrest, 30 copper held out to the guard opens a bribe card (an engine turn, no model).
        self.w["flags"]["deeds"][-1]["hold"] = {"guard": "npc_hale", "place": self.place["id"],
                                                "turn": self.w["flags"].get("turn_index", 0), "arrest": True}
        self.session._bribe_held_out = 30
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            self.session.run_player_turn("/item list")
        self.save()
        [bribe] = [data for data in self.offers().values() if data["status"] == "prepared"
                   and any(effect["kind"] == "bribe_accepted" for effect in data["on_accept"])]
        bribe = {"offer_id": bribe["offer_id"], "confirmation_digest": bribe["confirmation_digest"]}
        self.books("tutuklanırken muhafıza 30 bakır uzat")

        # 23. The bribe confirmed and the word holds: 30 copper to the guard, the hold released.
        with patch.object(bold_acts, "_check", side_effect=lambda *a, **k: {"result": "BAŞARILI"}):
            bribed, resolution, bribe_body = await self.confirm(bribe)
        self.assertEqual((resolution["status"], resolution["net_debit_cp"]), ("applied", 30), resolution)
        self.assertNotIn("hold", self.w["flags"]["deeds"][-1])
        self.books("rüşveti onayla", paid=30)

        # 24. Refresh the bribe's action id: the same answer, no second payment and no second roll.
        with patch.object(bold_acts, "_check", side_effect=AssertionError("no second roll")):
            replay = await self.post(bribe_body)
        self.assertEqual(replay, bribed)
        self.w["flags"]["deeds"].pop()  # the guard lets the matter go; the rest of the play is not about the law
        self.save()
        self.books("rüşvet onay kimliğini yenile")

        # 25. A paid day of work: the engine pays 40 copper from the day's pool, once.
        living_world.ensure_scene_state(self.w)
        owner = self.npc("npc_kalila")
        owner["place_role_of"] = self.place["id"]
        self.w["flags"].update(active_npc_id=owner["id"], last_npc_id=owner["id"], active_npc_until_turn=999)
        self.w.pop(world_threads.KEY, None)
        world_threads.ensure(self.w)
        state = world_threads.view(self.w)
        thread = state["threads"][0]
        thread.update(type="hiring", template_id="hand_wanted", status="offered", place_id=self.place["id"],
                      target_place_id=None, recipient_name=None, owner_name="Kalila",
                      expires_at=self.w["campaign_time"]["elapsed_seconds"] + 30 * DAY,
                      offered_at=self.w["campaign_time"]["elapsed_seconds"],
                      offered_turn=self.w["flags"].get("turn_index", 0),
                      offer_line="Günlüğü kırk bakır, iki gün. Yapar mısın?",
                      owner_line="Günlüğü kırk bakır, iki gün.",
                      terms={"pay": 40, "work_days": 2, "pay_basis": "daily", "pay_timing": "end_of_day",
                             "deadline_text": "iki gün içinde"})
        thread.pop("night_only", None)
        state["threads"] = [thread]
        thread_id = thread["thread_id"]
        self.w["npc_speech_log"] = {owner["id"]: [{"player": "iş var mı", "npc": thread["offer_line"]}]}
        world_threads.accept_hired(self.w, thread)
        self.save()
        self.minted += 40
        out, _ = await self.line("başlayalım", ScriptedNpcSpeechClient("Şimdilik sessiz bir gün."))
        self.assertEqual(world_threads.by_id(self.w, thread_id)["paid_cp"], 40, out["narration"])
        self.books("yevmiye günü çalış", paid=-40)

        # 26. A plain item given with /item give: it moves, no card, no coin.
        farmer = self.npc("npc_ilgin")
        farmer["item_consents"] = {"item_play_ring": {"operation": "give", "recipient": "npc_ilgin"},
                                   "item_play_wand": {"operation": "give", "recipient": "npc_ilgin"}}
        self.save()
        out, _ = await self.line("/item give item_play_ring npc_ilgin")
        self.assertIn("item_play_ring", pack(self.w).get("npc_ilgin", []), out["narration"])
        self.books("/item give sade halka")

        # 27-29. A valuable magic wand given with /item give opens a card; the confirm moves it, a second does not.
        out, _ = await self.line("/item give item_play_wand npc_ilgin")
        wand = out["state"]["economic_offer"]
        self.assertIsNotNone(wand, out["narration"])
        self.assertIn("item_play_wand", pack(self.w)["player"])
        self.books("/item give değerli büyülü asa (kart açılır)")
        _, resolution, _ = await self.confirm(wand)
        self.assertEqual((resolution["status"], resolution["net_debit_cp"]), ("applied", 0), resolution)
        self.assertIn("item_play_wand", pack(self.w)["npc_ilgin"])
        self.books("asa kartını onayla")
        _, resolution, _ = await self.confirm(wand)
        self.assert_refused(resolution, "offer_not_prepared")
        self.books("asa kartını ikinci kez onayla")

        # 30. A gift card left open before a fight.
        open_gift = await self.card(purpose="gift", recipient_id="npc_ilgin", amount_cp=5)
        self.books("kavgadan önce açık hediye kartı")

        # 31-32. A fight with a thug, and a flight out of the inn: the open card is cancelled, no coin moves.
        self.session.character.update(current_hp=300, max_hp=300)
        self.add_person("Brak", "Haydut", current_hp=500, max_hp=500, armor_class=1, inventory=[])
        self.save()
        out, _ = await self.line("hayduta saldırıyorum", PlayClient(intent="attack"))
        self.assertTrue(self.w["combat"]["active"], out["narration"])
        self.books("hayduta saldır")
        success = {"result": "BAŞARILI", "roll": 20, "total": 25, "dc": 12}
        with patch.object(self.session, "perform_skill_check", create=True, return_value=dict(success)):
            out, _ = await self.line("kapıdan dışarı kaçıyorum")
        self.assertEqual(out["turn_outcome"]["action"], "flee", out)
        self.assertNotEqual(self.w["location"], self.place["id"], out["narration"])
        self.assertFalse(self.w["combat"]["active"])
        self.assertEqual(self.offer_status(open_gift["offer_id"]), "cancelled")
        self.books("handan kaç")

        # 33. The card the flight cancelled is confirmed: nothing moves.
        _, resolution, _ = await self.confirm(open_gift)
        self.assert_refused(resolution, "offer_not_prepared")
        self.books("kaçışın iptal ettiği kartı onayla")

        # 34. A last look at the purse, a plain turn.
        out, _ = await self.line("/item list")
        self.books("çantaya bak")
        self.assertGreaterEqual(self.step_no, 30)
        self.assertEqual(self.purse(), START_PURSE - 4 - 55 - 4 - 10 - 30 + 40)
        self.assertEqual(json.loads(json.dumps(self.log, ensure_ascii=False))[-1][5], self.start_total + 40)

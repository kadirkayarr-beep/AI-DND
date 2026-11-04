"""Carius's fifth play, the turns that broke: the way out of town, the road on, coin, messengers, a punch, a fight's end.

Real app, real adapter, real engine; only the model client is scripted. The lines are the owner's own, as typed.
"""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

import bold_acts
import front_proposal
import local_places
import world_happenings
import world_threads
from api.tests import test_front_voice as voice
from api.tests.test_house_door import a_house
from api.tests.test_story_links import resident
from api.tests.test_world_keeps_its_word import FrontScene


class OnlyALineAboutLeavingLeavesTown(FrontScene):
    OUT = {"kind": "go_to", "place_id": front_proposal.WAY_OUT}

    def gate_road(self):
        return [record for record in self.world["locations"].values()
                if isinstance(record, dict) and local_places.PLACE_KINDS.get(record.get("place_kind"), {}).get("outdoors")]

    async def stays_in_town(self, line):
        await self.begin()
        self.client.front = self.OUT
        out = await self.line(line)
        self.assertEqual(self.gate_road(), [], out["narration"])
        self.assertNotIn("surların dışı", out["narration"])

    async def test_hills_someone_pointed_at_are_in_town(self):
        await self.stays_in_town("tamam sağol, gösterdiği tepelere doğru yürüyorum")

    async def test_a_tavern_is_in_town(self):
        await self.stays_in_town("meyhaneye gidiyorum")

    async def test_a_houses_outer_gate_is_in_town(self):
        await self.stays_in_town("hala salondayım galiba. salondan çıkıp avluya, dış kapıya gidiyorum")

    async def test_walking_someone_out_to_the_street_is_in_town(self):
        await self.stays_in_town(
            "yamalıya sakin ama sert: dışarı. kapıyı gösterip arkasından yürüyorum, sokağa çıkana kadar peşindeyim")

    async def test_a_line_that_leaves_town_still_leaves_it(self):
        await self.begin()
        self.client.front = self.OUT
        out = await self.line("ben şimdi şehirden çıkıp yola düşüyorum, civarı bi kolaçan edicem, ana yoldan kuzeye doğru")
        self.assertEqual([record["id"] for record in self.gate_road()], [self.world["location"]], out["narration"])

    async def test_other_words_for_the_town_its_roads_and_walls_leave_it_too(self):
        for line in ("kasabadan çıkıp yollara düşüyorum", "köyden çıkıp gidiyorum"):
            with self.subTest(line=line):
                await self.begin()
                self.client.front = self.OUT
                out = await self.line(line)
                self.assertEqual([record["id"] for record in self.gate_road()], [self.world["location"]], out["narration"])

    async def test_sending_a_letter_is_no_road(self):
        await self.stays_in_town("kardeşime bi mektup yolluyorum")

    async def test_over_there_is_no_wall(self):
        await self.stays_in_town("şurdan meyhaneye gidiyorum")

    async def test_the_list_does_not_call_a_door_the_way_out(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("etrafa bakıyorum")
        self.assertNotIn("kapı", self.world_label())

    def world_label(self):
        import grounded_action
        return grounded_action.way_out_label(self.session) or ""


class TheRoadOnIsNoWall(FrontScene):
    OUT = {"kind": "go_to", "place_id": front_proposal.WAY_OUT}

    async def test_told_why_not_once_the_player_can_still_walk_on_to_a_real_place(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("şehirden çıkıyorum, kuzey yoluna")
        stop = self.world["location"]
        first = await self.line("duraktan geçip kuzey yoluna devam ediyorum, şehirden uzaklaşıyorum")
        self.assertEqual(self.world["location"], stop, first["narration"])
        self.assertIn("“", first["narration"])
        clock = self.world["campaign_time"]["elapsed_seconds"]
        second = await self.line("günlerce gitmicem ki usta, yarım gün yürüyüp dönücem. yürüyorum ben")
        here = self.world["locations"][self.world["location"]]
        self.assertNotEqual(self.world["location"], stop, second["narration"])
        self.assertNotIn("sokaklarına", second["narration"])  # down the road, not back through the streets
        self.assertTrue(local_places.PLACE_KINDS[here["place_kind"]].get("outdoors"), here)
        self.assertGreater(self.world["campaign_time"]["elapsed_seconds"], clock)
        self.assertNotEqual(self.routes()[-1]["status"], "not_now")
        self.assertTrue([npc for npc in self.world["npcs"] if npc.get("location") == here["id"]])
        self.assertEqual(local_places.settlement_of(self.world, here["id"]), here["parent_location_id"])

    async def test_from_the_end_of_the_road_town_is_a_walk_back(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("şehirden çıkıyorum, kuzey yoluna")
        await self.line("kuzey yoluna devam ediyorum")
        await self.line("yürüyorum ben, yola devam")
        town = self.world["locations"][self.world["location"]]["parent_location_id"]
        self.client.front = {"kind": "go_to", "place_id": town}
        out = await self.line("şehre geri dönüyorum")
        self.assertEqual(self.world["location"], town, out["narration"])


class OneCoinOneTruth(FrontScene):
    async def at_the_bar(self):
        await self.begin()
        self.npc["role"] = "Barmen"
        self.world.setdefault("currency", {})["player"] = 2435

    def purse(self):
        return self.world["currency"]["player"]

    LABELS = {"gift": "Hediye", "tip": "Bahşiş"}

    def coin_card(self, out, purpose, amount):
        """The one card the line opened: a gift or a tip of exactly that coin to the barman, nothing paid yet."""
        cards = [data for data in self.world["flags"].get("economic_offers", {}).values()
                 if data["status"] == "prepared"]
        self.assertEqual(len(cards), 1, out["narration"])
        proposal = cards[0]["proposal"]
        self.assertEqual((proposal["purpose"], proposal["recipient_id"], proposal["amount_cp"]),
                         (purpose, self.npc["id"], amount), out["narration"])
        self.assertIsNone(proposal.get("tender_cp"))
        self.assertEqual(out["state"]["economic_offer"]["offer_id"], cards[0]["offer_id"])
        self.assertEqual([line["label"] for line in out["state"]["economic_offer"]["lines"]], [self.LABELS[purpose]])
        return out["state"]["economic_offer"]

    def coin_operations(self, purpose):
        operations = self.world["flags"].get("economic_ledger", {}).get("operations", {})
        return [op for op in operations.values() if op["purpose"] == purpose]

    async def confirm(self, card):
        response = await self.http.post(self.turn_url, json={
            "message": "Teklifi onayla", "action_id": str(uuid.uuid4()),
            "economic_action": {"kind": "confirm", "offer_id": card["offer_id"],
                                "confirmation_digest": card["confirmation_digest"]}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def confirm_pays_once(self, card, amount, *, purse, held, purpose):
        """Confirming over the API moves exactly that coin to the barman once; a second confirm moves nothing."""
        paid = await self.confirm(card)
        resolution = paid["economic_resolution"]
        self.assertEqual((resolution["status"], resolution["net_debit_cp"]), ("applied", amount), paid["narration"])
        self.assertEqual(self.purse(), purse - amount)
        self.assertEqual(self.world["currency"].get(self.npc["id"], 0), held + amount)
        self.assertNotEqual(paid["turn_outcome"]["action"], "purchase", paid["narration"])
        again = (await self.confirm(card))["economic_resolution"]
        self.assertEqual((again["status"], again["reason_code"], again["net_debit_cp"]),
                         ("refused", "offer_not_prepared", 0))
        self.assertEqual(self.purse(), purse - amount)
        self.assertEqual(self.world["currency"].get(self.npc["id"], 0), held + amount)
        self.assertEqual(len(self.coin_operations(purpose)), 1)

    async def test_the_price_the_barman_says_is_the_price_the_purse_pays(self):
        await self.at_the_bar()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        await self.line("barmene bi bira söylüyorum, kaç para?", "Bira dört bakır.")
        price = dict((stem, cp) for stem, _, cp in bold_acts._PRICES)["bira"]
        self.assertIn(f"bira {price} bakır", str(self.client.message_batches[-1]))

    async def test_a_gold_thrown_with_keep_the_change_pays_that_gold_and_buys_no_beer(self):
        await self.at_the_bar()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 100, "deal": "tip"}
        out = await self.line("bi altın atıyorum tezgaha, üstü kalsın, karşılığında biraz laf isterim. "
                              "mazduşa konağının sahibi kim biliyon mu", "Bilmem.")
        # Keep-the-change with no order is read as a tip of the whole gold: its Bahşiş card opens, the confirm pays it.
        self.assertEqual(self.purse(), 2435, out["narration"])
        self.assertEqual(self.world["currency"].get(self.npc["id"], 0), 0)
        self.assertNotEqual(out["turn_outcome"]["action"], "purchase", out["narration"])
        card = self.coin_card(out, "tip", 100)
        await self.confirm_pays_once(card, 100, purse=2435, held=0, purpose="tip")
        self.assertEqual(self.purse(), 2335)

    async def test_a_gold_put_down_with_a_beer_order_only_opens_the_counter(self):
        # The owner's call: coin and goods move only through the one counter trade, never with the words.
        await self.at_the_bar()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 100}
        out = await self.line("bi bira ver, al şu bi altını, üstü kalsın", "Sağ ol.")
        self.assertEqual(out["turn_outcome"]["action"], "shop_offer", out["narration"])
        self.assertEqual(self.purse(), 2435, out["narration"])
        self.assertEqual(self.world["currency"].get(self.npc["id"], 0), 0)

    async def test_a_gold_handed_on_the_line_after_the_order_stays_in_the_purse(self):
        # The owner's T13 line: the beer was ordered a line before, so the gold is for the open offer, not a gift.
        await self.at_the_bar()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        first = await self.line("bir bira alayım", "Buyur.")
        self.assertEqual(first["turn_outcome"]["action"], "shop_offer", first["narration"])
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 100}
        out = await self.line("bakırım yok, al şu bir altını, üstünü geri ver ama", "Al üstünü.")
        self.assertEqual(self.purse(), 2435, out["narration"])
        self.assertEqual(self.world["currency"].get(self.npc["id"], 0), 0)
        self.assertNotIn("kesenden çıkıyor", out["narration"])
        self.assertEqual(out["turn_outcome"]["action"], "shop_offer", out["narration"])
        self.assertIn("4 bakır", out["narration"])

    async def test_a_tip_after_the_beer_was_bought_still_pays(self):
        await self.at_the_bar()
        bought = await self.line(f"/item shop_buy {self.npc['id']} bira 1 0 4")
        self.assertEqual(self.purse(), 2431, bought["narration"])
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 10, "deal": "tip"}
        out = await self.line("al şu gümüşü de, üstü kalsın", "Sağ ol.")
        # The tip is its own Bahşiş card, not folded into the beer already bought; the confirm pays it.
        self.assertEqual(self.purse(), 2431, out["narration"])
        self.assertEqual(self.world["currency"][self.npc["id"]], 4)
        card = self.coin_card(out, "tip", 10)
        await self.confirm_pays_once(card, 10, purse=2431, held=4, purpose="tip")
        self.assertEqual(self.purse(), 2435 - 4 - 10)
        self.assertEqual(self.world["currency"][self.npc["id"]], 14)

    async def test_change_asked_back_is_not_left_on_the_counter(self):
        for line, coin in (("bi altın uzatıyorum, bir bira ver, üstünü geri ver", 100),
                           ("bi gümüş veriyorum, bi bira ver", 10)):
            with self.subTest(line=line):
                await self.at_the_bar()
                self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": coin}
                out = await self.line(line, "Al bakalım.")
                self.assertEqual(self.purse(), 2435, out["narration"])
                self.assertNotIn("tezgâhta kalıyor", out["narration"])
                self.assertNotIn("kesenden çıkıyor", out["narration"])

    async def test_a_coin_in_a_question_moves_no_coin(self):
        for line in ("bi altın versem, bira verir misin?", "bende bi altın var, nereye harcasam?"):
            with self.subTest(line=line):
                await self.at_the_bar()
                self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 100}
                out = await self.line(line, "Bakarız.")
                self.assertEqual(self.purse(), 2435, out["narration"])

    async def test_a_coin_handed_before_a_question_still_pays(self):
        await self.at_the_bar()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 100, "deal": "gift"}
        out = await self.line("bi altın atıyorum tezgaha, mazduşa konağının sahibi kim biliyon mu?", "Bilmem.")
        # The question does not swallow the coin: the gift card the reading names opens, and the confirm pays it.
        self.assertEqual(self.purse(), 2435, out["narration"])
        card = self.coin_card(out, "gift", 100)
        await self.confirm_pays_once(card, 100, purse=2435, held=0, purpose="gift")
        self.assertEqual(self.purse(), 2335)


class MessengersSayWhatHappened(unittest.TestCase):
    def house_link(self, owner=None, about=None):
        world, state, record, steward, room = a_house()
        link = world_happenings.tie(world, world_happenings.CALLER, "warned", owner or steward, record["id"], about=about)
        link.pop("fires_at")
        words = world_threads.job_lines("link", "caller")
        return world, state, record, steward, room, link, words

    def test_a_job_posting_is_not_spoken_as_the_matter(self):
        world, state, record, steward, room = a_house()
        thread = state["threads"][0]
        thread.pop("item_noun", None)
        thread["public_line"] = "Ulivem gece bekçisi arıyor, Mazduşa Konağı için."
        link = world_happenings.tie(world, world_happenings.CALLER, "warned", steward, record["id"],
                                    about=thread["thread_id"])
        link.pop("fires_at")
        message = world_happenings._message(world, link, world_threads.job_lines("link", "caller"))
        self.assertNotIn(thread["public_line"].rstrip(" ."), message)
        self.assertNotIn("meselesini unutmadı", message)

    def test_standing_in_the_house_the_messenger_points_to_the_room_not_the_house(self):
        world, state, record, steward, room, link, words = self.house_link()
        world["location"] = record["id"]
        message = world_happenings._message(world, link, words)
        self.assertNotIn(f"Seni {record['name']} içinde", message)
        self.assertIn(room["name"], message)
        world["location"] = room["id"]
        self.assertNotIn("görmek istiyor", world_happenings._message(world, link, words))

    def test_someone_who_is_not_the_house_sends_in_their_own_name(self):
        world, state, record, steward, room = a_house()
        struck = resident(world, record["id"], "yamali")
        struck.pop("place_role_of", None)
        link = world_happenings.tie(world, world_happenings.CALLER, "warned", struck, record["id"])
        self.assertNotIn("sahibi", world_happenings._link_owner(world, link))
        words = world_threads.job_lines("link", "caller")
        self.assertNotIn("görmek istiyor", world_happenings._message(world, link, words))

    def test_a_messenger_asked_something_answers_it_rather_than_repeat(self):
        world, state, record, steward, room, link, words = self.house_link()
        caller = resident(world, record["id"], "ulak")
        caller.update(caller_of=link["thread_id"], message="Bir dahakine lafla gelmem, dedi.")
        link["caller_id"] = caller["id"]
        note = world_happenings.link_note(world, caller)
        self.assertNotIn("aynen", note)
        self.assertIn("sorulan", note)


class Fists(FrontScene):
    assert_attacked = voice.AnyBlowIsAnAttack.assert_attacked

    async def begin(self, **kwargs):
        await FrontScene.begin(self, **kwargs)
        self.npc.update(armor_class=10, max_hp=12, current_hp=12)


class APunchIsAPunch(Fists):
    async def scoff_then_fist(self, mode):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "strike_to": self.npc["id"],
                             "thing_word": "yumruk"}
        reply = await self.line("itemez miyim? sıkıp yumruğumu suratına bi tane çakıyorum", "Dene bakalım.", mode=mode)
        self.assert_attacked(reply)

    async def test_a_scoff_then_a_fist_lands_in_the_ui_default_do_mode(self):
        await self.scoff_then_fist("do")  # the browser sends 'do' for typed text unless the player picks another

    async def test_a_scoff_then_a_fist_lands_with_no_mode(self):
        await self.scoff_then_fist(None)

    async def test_a_question_after_the_blow_is_still_only_a_question(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "strike_to": self.npc["id"]}
        reply = await self.line("ona bi tane çaksam ne olur?", "Denemeni tavsiye etmem.", mode="do")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])


class TheFightLeavesThePlayerTheirOwnHands(Fists):
    async def in_a_fight(self):
        await self.begin()
        self.npc.update(current_hp=200, max_hp=200)
        self.session.character.update(max_hp=300, current_hp=300)
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"], "thing_word": "yumruk"}
        await self.line("düşündüm. yumrukla vuruyorum")
        self.assertTrue(self.world["combat"]["active"])
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}

    async def test_stepping_back_and_telling_them_to_go_is_no_walk_off(self):
        await self.in_a_fight()
        out = await self.line("geri çekilip ellerimi indiriyorum. yeter, kan dökmeyelim. al pılını pırtını çık git konaktan",
                              "Peki.")
        self.assertNotEqual(out["turn_outcome"]["status"], "fight_refused", out["narration"])
        self.assertNotIn("yürüyüp gidemezsin", out["narration"])

    async def test_ending_the_fight_says_nothing_the_player_did_not_do(self):
        await self.in_a_fight()
        with patch.object(self.session, "perform_skill_check", return_value={"result": "BAŞARILI", "total": 20}):
            out = await self.line("ona bağırıyorum: bırak o silahı, teslim ol, seni kahyaya teslim edicem")
        self.assertNotIn("Kılıcını", out["narration"])

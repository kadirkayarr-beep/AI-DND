"""What the world says it does, it does: the things a long play found saying one thing and doing another.

Every line is the kind of thing the owner types. No real model is called.
"""
import json
import os
import unittest
import uuid
from unittest.mock import patch

import bold_acts
import campaign_time
import front_proposal
import interaction_adventure
import local_places
import pocket
import world_happenings
import world_reactions
import world_threads
from api.tests.test_front_proposal import FrontTable
from api.tests.test_lasting_consequences import OneTownScene
from api.tests.test_three_plays import PlayClient
from api.tests.town_seed import fixed_town
from api.tests.test_world_reactions import GuardsActOnWhatTheyKnow


class Stealing(OneTownScene):
    async def room(self):
        await self.town()
        self.world["location"] = "shop"
        self.world["flags"].pop("active_npc_id", None)

    async def steal(self, line, roll):
        with patch.object(self.session.rng, "randint", return_value=roll):
            return await self.say(line, PlayClient())

    async def test_an_empty_room_can_be_robbed_and_the_roll_is_shown(self):
        await self.room()
        before = self.world.get("currency", {}).get("player", 0)
        out = await self.steal("kimse yok. tezgahin arkasina gecip cekmeceden parayi yurutuyorum", 15)
        self.assertEqual(out["turn_outcome"]["status"], "stolen", out["narration"])
        self.assertGreater(self.world["currency"]["player"], before)
        self.assertEqual(out["skill_check_result"]["skill"], "Sleight of Hand")
        self.assertEqual(out["skill_check_result"]["dc"], 10)
        self.assertEqual(out["skill_check_result"]["d20"], 15)

    async def test_an_empty_street_has_no_till_and_the_roll_is_still_shown(self):
        await self.room()
        self.world["location"] = self.city
        before = self.world.get("currency", {}).get("player", 0)
        with patch.object(self.session, "active_npcs", return_value=[]):  # nobody passing in the street
            out = await self.steal("etrafta kimse yok, yerleri karistirip para caliyorum", 15)
        self.assertEqual(self.world.get("currency", {}).get("player", 0), before, out["narration"])
        self.assertEqual(out["skill_check_result"]["skill"], "Sleight of Hand")

    async def test_a_till_robbed_once_is_empty_the_same_day(self):
        await self.room()
        await self.steal("kimse yok. cekmeceden parayi yurutuyorum", 15)
        after_first = self.world["currency"]["player"]
        out = await self.steal("bi daha cekmeceden parayi yurutuyorum", 15)
        self.assertEqual(self.world["currency"]["player"], after_first, out["narration"])

    async def test_a_miss_in_an_empty_room_is_a_result_and_never_the_character_stopping(self):
        await self.room()
        before = self.world.get("currency", {}).get("player", 0)
        out = await self.steal("kimse yok, cekmeceyi yurutuyorum", 1)
        self.assertEqual(out["turn_outcome"]["status"], "failed", out["narration"])
        self.assertEqual(self.world.get("currency", {}).get("player", 0), before)
        self.assertNotIn("duraks", out["narration"])
        self.assertNotIn("fırsat", out["narration"])
        self.assertEqual(out["skill_check_result"]["outcome"], "failure")

    async def test_a_turned_back_is_the_easy_roll_and_a_face_watching_is_not(self):
        for line, dc in (("rahip mumlara donunce bagis kutusunu yurutuyorum", 10),
                         ("adam bakarken kesesini yurutuyorum", 10),
                         ("adamin kesesini yurutuyorum", 15)):
            with self.subTest(line=line):
                await self.room()
                self.add_person("Tariq", "Rahip", location="shop")
                out = await self.steal(line, 15)
                self.assertEqual(out["skill_check_result"]["dc"], dc, out["narration"])

    async def test_two_people_in_the_room_and_a_miss_is_a_caught_hand(self):
        await self.room()
        first = self.add_person("Tariq", "Rahip", location="shop")
        self.add_person("Bren", "Çırak", location="shop")
        out = await self.steal("kutuyu yurutuyorum", 1)
        self.assertEqual(out["turn_outcome"]["status"], "caught", out["narration"])
        self.assertEqual(self.world["flags"]["deeds"][-1]["victim_id"], first["id"])


class AnInnHasRooms(OneTownScene):
    async def inn(self):
        await self.town()
        self.world["location"] = "shop"
        self.world.setdefault("currency", {})["player"] = 1000
        return self.add_person("Veyra", "Barmen", location="shop")

    async def test_asking_the_price_of_a_room_gets_the_price_and_costs_nothing(self):
        for line in ("bi gecelik oda ne kadar?", "oda var mi", "barmene: oda kaç para?"):
            with self.subTest(line=line):
                await self.inn()
                out = await self.say(line, PlayClient(spoken="Oda kiralamıyorum."))
                self.assertIn("5 gümüş", out["narration"])
                self.assertEqual(self.world["currency"]["player"], 1000)
                self.assertIsNone(self.world["flags"].get("inn_room"))

    async def test_a_question_and_going_to_bed_in_one_line_opens_the_room_card_without_sleep(self):
        await self.inn()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        out = await self.say("barmene: bi gecelik oda ne kadar? yatıcam, sabaha kadar kimse uyandırmasın", PlayClient())
        self.assertIn("50 bakır", out["narration"])
        self.assertIsNone(self.world["flags"].get("inn_room"))
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock)
        self.assertEqual(self.world["currency"]["player"], 1000)
        cards = [data for data in self.world["flags"].get("economic_offers", {}).values()
                 if data["status"] == "prepared"]
        self.assertEqual([card["proposal"]["purpose"] for card in cards], ["room"])
        self.assertEqual(sum(line["total_cp"] for line in cards[0]["lines"]), 50)
        card = out["state"]["economic_offer"]
        confirm = {"message": "Teklifi onayla", "action_id": str(uuid.uuid4()),
                   "economic_action": {"kind": "confirm", "offer_id": card["offer_id"],
                                       "confirmation_digest": card["confirmation_digest"]}}
        confirmed = await self.post_scene_turn(self.url, PlayClient(), confirm)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["economic_resolution"]["status"], "applied")
        self.assertTrue(self.world["flags"].get("inn_room"))
        # The consuming confirm settles the gold written in the pack, then takes the room's 50.
        self.assertEqual(self.world["currency"]["player"], out["state"]["wallet"]["total_cp"] - 50)
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock)  # sleeping is a new line

    async def test_whoever_serves_knows_the_house_has_rooms_when_rooms_are_the_talk(self):
        barman = await self.inn()
        self.assertIn("5 gümüş", bold_acts.room_note(barman, "oda kiralamak gerek yarin"))
        self.assertEqual(bold_acts.room_note(barman, "en ucuz neyin var"), "")
        self.assertNotIn("5 gümüş", self.note(barman))

    async def test_coin_named_with_an_order_is_not_paid_by_the_words(self):
        # The counter trade (shop_trade.commit) takes the price once; the order line only opens the offer.
        await self.inn()
        before = self.purse_after_labels()
        # The reading says what the coin is for (plan Task 8: with coin held out, the decision opens the counter)
        client = ReadingClient({"kind": "speak_to", "person_id": "npc_veyra", "coin_cp": 4, "deal": "goods",
                                "deal_goods": "bira"})
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
            out = await self.say("al sana 4 bakır, bi bira ver", client)
        self.assertEqual(out["turn_outcome"]["action"], "shop_offer", out["narration"])
        self.assertEqual(self.world["currency"]["player"], before, out["narration"])

    def purse_after_labels(self):
        bold_acts.settle_coin_labels(self.world)
        return self.world["currency"]["player"]

    async def test_a_room_taken_is_not_haggled_over_afterwards(self):
        await self.inn()
        # With the reading on, the model's own `deal` says the room is the talk; room words alone are no longer read.
        client = ReadingClient({"kind": "speak_to", "person_id": "npc_veyra", "deal": "room",
                                "also_says": "kimse uyandirmasin"},
                               spoken="Gecelik beş gümüş, bırak tezgâha.")
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
            out = await self.say("bi gecelik oda ne kadar? yaticam, sabaha kadar kimse uyandirmasin", client)
        self.assertNotIn("bırak tezgâha", out["narration"])


class FrontScene(unittest.IsolatedAsyncioTestCase):
    asyncSetUp, asyncTearDown = FrontTable.asyncSetUp, FrontTable.asyncTearDown
    campaign_with_npc, open_job, line = FrontTable.campaign_with_npc, FrontTable.open_job, FrontTable.line
    begin, routes, front_calls = FrontTable.begin, FrontTable.routes, FrontTable.front_calls


class FrontLines(FrontScene):
    def purse(self):
        return self.world.setdefault("currency", {}).get("player", 0)

    def held_out(self):
        """(who, copper) of each open gift card: what the line held out, waiting for confirmation."""
        return [(data["proposal"]["recipient_id"], data["proposal"]["amount_cp"])
                for data in self.world.get("flags", {}).get("economic_offers", {}).values()
                if data["status"] == "prepared" and data["proposal"]["purpose"] == "gift"]

    async def confirm_card(self, out):
        """Confirms the card the line opened, over HTTP, with a fresh action; returns the response."""
        card = out["state"]["economic_offer"]
        confirmed = await self.http.post(self.turn_url, json={
            "message": "Teklifi onayla", "action_id": str(uuid.uuid4()),
            "economic_action": {"kind": "confirm", "offer_id": card["offer_id"],
                                "confirmation_digest": card["confirmation_digest"]}})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["economic_resolution"]["status"], "applied", confirmed.text)
        return confirmed

    async def test_hanging_about_moves_the_clock(self):
        await self.begin()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        self.client.front = {"kind": "wait"}
        out = await self.line("köşedeki masaya geçip akşama kadar takılıyorum, millet dolsun bakalım")
        self.assertGreater(self.world["campaign_time"]["elapsed_seconds"], clock + 1800, out["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:wait")
        self.assertEqual(self.routes()[-1]["owner"], "wait")

    async def test_a_length_in_the_line_is_time_spent_however_it_was_read(self):
        await self.begin()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        self.client.front = {"kind": "sit"}
        await self.line("köşedeki masaya geçip iki saat takılıyorum")
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock + 7200)
        self.assertEqual(self.routes()[-1]["route"], "front:wait")

    async def rest_scene(self):
        """A little hurt, no Long Rest on record. (Second Wind and Action Surge: the Fighter tests of the same path.)"""
        with fixed_town(self, 2731):
            await self.begin()
        self.session.character["current_hp"] = max(1, self.session.character["max_hp"] - 3)
        self.world.pop("last_long_rest_completed_at", None)

    async def test_a_long_rest_read_as_a_wait_is_a_long_rest(self):
        await self.rest_scene()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        self.client.front = {"kind": "wait"}
        out = await self.line("Sekiz saat uyuyarak uzun dinlenme yapıyorum")
        self.assertEqual(self.routes()[-1]["route"], "front:wait")
        self.assertEqual(self.session.character["current_hp"], self.session.character["max_hp"], out["narration"])
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock + 8 * 3600)
        self.assertEqual(self.world["last_long_rest_completed_at"], clock + 8 * 3600)

    async def test_a_short_rest_read_as_a_wait_is_a_short_rest(self):
        await self.rest_scene()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        self.client.front = {"kind": "wait"}
        out = await self.line("bir saat kısa dinleniyorum")
        self.assertEqual(self.routes()[-1]["route"], "front:wait")
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock + 3600, out["narration"])
        self.assertEqual(self.session.character["hit_dice"]["window_second"], clock + 3600, out["narration"])
        self.assertNotIn("last_long_rest_completed_at", self.world)

    async def test_a_second_long_rest_too_soon_read_as_a_wait_rests_nothing(self):
        await self.rest_scene()
        self.client.front = {"kind": "wait"}
        await self.line("Sekiz saat uyuyarak uzun dinlenme yapıyorum")
        rested_at = self.world["last_long_rest_completed_at"]
        self.session.character["current_hp"] = max(1, self.session.character["max_hp"] - 3)
        hurt = self.session.character["current_hp"]
        out = await self.line("Sekiz saat uyuyarak uzun dinlenme yapıyorum")
        self.assertIn("Daha yeni dinlenmiştin", out["narration"])
        self.assertEqual(self.world["last_long_rest_completed_at"], rested_at)
        self.assertEqual(self.session.character["current_hp"], hurt)

    async def test_a_rest_said_no_to_read_as_a_wait_is_only_the_wait(self):
        await self.rest_scene()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        hurt = self.session.character["current_hp"]
        self.client.front = {"kind": "wait"}
        out = await self.line("dinlenmek istemiyorum, iki saat bekliyorum")
        self.assertEqual(self.routes()[-1]["route"], "front:wait")
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock + 7200, out["narration"])
        self.assertIsNone((self.session.character.get("hit_dice") or {}).get("window_second"), out["narration"])
        self.assertNotIn("last_long_rest_completed_at", self.world)
        self.assertEqual(self.session.character["current_hp"], hurt)

    async def watch_without_rest(self, line):
        # Task 41 (owner vocabulary, 2026-11-10): 'dinlenmeden', 'dinlenmeksizin' are a rest said no to.
        await self.rest_scene()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        hurt = self.session.character["current_hp"]
        self.client.front = {"kind": "wait"}
        out = await self.line(line)
        self.assertEqual(self.routes()[-1]["route"], "front:wait")
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock + 7200, out["narration"])
        self.assertIsNone((self.session.character.get("hit_dice") or {}).get("window_second"), out["narration"])
        self.assertNotIn("last_long_rest_completed_at", self.world)
        self.assertEqual(self.session.character["current_hp"], hurt)

    async def test_a_watch_kept_without_resting_is_only_the_wait(self):
        await self.watch_without_rest("dinlenmeden iki saat nöbet tutuyorum")

    async def test_a_watch_kept_with_no_rest_at_all_is_only_the_wait(self):
        await self.watch_without_rest("dinlenmeksizin iki saat nöbet tutuyorum")

    async def wait_without_sleep(self, line):
        # Task 41: 'uyumadan', 'uyumaksızın' are a sleep said no to: eight hours pass, no Long Rest is recorded.
        await self.rest_scene()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        hurt = self.session.character["current_hp"]
        self.client.front = {"kind": "wait"}
        out = await self.line(line)
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock + 8 * 3600, out["narration"])
        self.assertNotIn("last_long_rest_completed_at", self.world)
        self.assertEqual(self.session.character["current_hp"], hurt)

    async def test_eight_hours_waited_without_sleeping_is_no_long_rest(self):
        await self.wait_without_sleep("uyumadan sekiz saat bekliyorum")

    async def test_eight_hours_waited_with_no_sleep_at_all_is_no_long_rest(self):
        await self.wait_without_sleep("uyumaksızın sekiz saat bekliyorum")

    async def test_a_rest_with_no_length_read_as_a_wait_asks_for_an_hour_and_passes_nothing(self):
        await self.rest_scene()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        self.client.front = {"kind": "wait"}
        out = await self.line("biraz dinleniyorum")
        self.assertEqual(self.routes()[-1]["route"], "front:wait")
        self.assertIn("Kısa dinlenme için en az bir saat gerekir.", out["narration"])
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], clock)
        self.assertIsNone((self.session.character.get("hit_dice") or {}).get("window_second"), out["narration"])

    async def test_hanging_about_with_no_length_is_a_while(self):
        await self.begin()
        clock = self.world["campaign_time"]["elapsed_seconds"]
        self.client.front = {"kind": "wait"}
        await self.line("biraz oyalaniyorum burda")
        passed = self.world["campaign_time"]["elapsed_seconds"] - clock
        self.assertTrue(600 <= passed <= 3600, passed)

    async def test_a_coin_given_leaves_the_purse_and_the_person_has_it(self):
        await self.begin()
        self.world.setdefault("currency", {})["player"] = 100
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 5, "deal": "gift"}
        out = await self.line("yasliya yarim gumus veriyorum sus diye")
        # A4: the coin held out as a gift opens a gift card for that person; only its confirmation moves it.
        self.assertEqual(self.purse(), 100, out["narration"])
        self.assertEqual(self.held_out(), [(self.npc["id"], 5)])
        self.assertIn("5 bakır", out["narration"])
        card = out["state"]["economic_offer"]
        confirmed = await self.http.post(self.turn_url, json={
            "message": "Teklifi onayla", "action_id": str(uuid.uuid4()),
            "economic_action": {"kind": "confirm", "offer_id": card["offer_id"],
                                "confirmation_digest": card["confirmation_digest"]}})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(self.purse(), 95)
        self.assertEqual(self.world["currency"][self.npc["id"]], 5)
        self.assertIn("5 bakır", confirmed.json()["narration"])

    async def test_words_about_coin_move_no_coin(self):
        for line in ("sana yarim gumus veririm ha", "yarim gumus eder mi?", "yarin bir gumus getiririm"):
            with self.subTest(line=line):
                await self.begin()
                self.world.setdefault("currency", {})["player"] = 100
                self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 5}
                await self.line(line)
                self.assertEqual(self.purse(), 100, line)

    async def test_a_figure_with_no_coin_in_the_line_moves_nothing(self):
        await self.begin()
        self.world.setdefault("currency", {})["player"] = 100
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 5}
        await self.line("sus artik bak")
        self.assertEqual(self.purse(), 100)

    async def test_the_figure_in_the_line_beats_the_figure_in_the_reading(self):
        for line, read, paid in (("barmene bir bakir birakiyorum", 100, 1), ("masaya 3 gumus birakiyorum", 5, 30),
                                 ("adama on bes bakir uzatiyorum", 500, 15), ("bi altin firlatiyorum masaya", 7, 100)):
            with self.subTest(line=line):
                await self.begin()
                self.world.setdefault("currency", {})["player"] = 320
                self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": read, "deal": "gift"}
                out = await self.line(line)
                self.assertEqual(self.purse(), 320, line)  # A4: held out, not paid, until the card is confirmed
                self.assertEqual(self.held_out(), [(self.npc["id"], paid)], line)
                await self.confirm_card(out)
                self.assertEqual(self.purse(), 320 - paid, line)  # the line's figure is what really moves
                self.assertEqual(self.world["currency"].get(self.npc["id"], 0), paid, line)

    async def test_coin_with_no_figure_is_a_small_hand_not_the_readings_number(self):
        await self.begin()
        self.world.setdefault("currency", {})["player"] = 320
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 300, "deal": "gift"}
        out = await self.line("eline biraz para sikistiriyorum")
        self.assertEqual(self.purse(), 320)  # A4: held out, not paid, until the card is confirmed
        self.assertEqual(self.held_out(), [(self.npc["id"], 10)])
        await self.confirm_card(out)
        self.assertEqual(self.purse(), 310)  # a small hand really moves, never the reading's number
        self.assertEqual(self.world["currency"].get(self.npc["id"], 0), 10)

    async def test_more_than_the_purse_holds_stays_in_the_purse(self):
        await self.begin()
        self.world.setdefault("currency", {})["player"] = 3
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 50}
        await self.line("al sana bes gumus veriyorum")
        self.assertEqual(self.purse(), 3)


class Messengers(FrontScene):
    def links(self):
        return world_happenings.links(world_threads.view(self.world))

    async def sent(self, tone="warned", assault=False):
        """Someone the player wronged has sent a person; the clock has just reached them."""
        await self.begin()
        self.world["flags"].pop("active_npc_id", None)
        if assault:
            bold_acts.remember(self.session, "assault", "biri üzerine yürüdü", victim_id=self.npc["id"])
        link = world_happenings.tie(self.world, world_happenings.CALLER, tone, self.npc, self.world["location"])
        campaign_time.advance(self.world, link["fires_at"] - world_threads._now(self.world) + 1, "rest", "test")
        self.client.front = {"kind": "look"}
        return link

    def caller(self, link):
        return next((npc for npc in self.world["npcs"] if npc.get("caller_of") == link["thread_id"]), None)

    async def test_a_messenger_says_who_sent_them_why_and_what_is_wanted(self):
        link = await self.sent(assault=True)
        out = await self.line("etrafa bi bakiyim")
        self.assertIn(world_threads.spoken_owner(self.world, {"owner_npc_id": self.npc["id"]}), out["narration"])
        self.assertIn("Üzerine yürüdüğünü", out["narration"])
        self.assertNotIn("Söylenen söz", out["narration"])
        self.assertIn(self.caller(link)["message"], out["narration"])

    async def test_asked_what_the_news_is_they_say_it_again_from_python_too(self):
        link = await self.sent(assault=True)
        await self.line("etrafa bi bakiyim")
        visitor = self.caller(link)
        said = interaction_adventure.immersive_unknown(visitor, "haber ne, lafi dolandirma?")
        self.assertIn(visitor["message"], said)

    async def test_they_say_it_and_go_and_are_not_in_the_room_hours_later(self):
        link = await self.sent()
        await self.line("etrafa bi bakiyim")
        visitor = self.caller(link)
        here = self.world["location"]
        self.assertEqual(visitor["location"], here)
        self.client.front = {"kind": "speak_to", "person_id": visitor["id"]}
        await self.line("ne istiyosun")
        self.assertEqual(visitor["location"], here)
        out = await self.line("sen kimsin ya")
        self.assertEqual(visitor["location"], link["place_id"] if link["place_id"] != here else here, out["narration"])
        self.assertIsNot(self.world["flags"].get("active_npc_id"), visitor["id"])

    async def test_walked_away_from_they_are_gone_when_the_player_comes_back(self):
        link = await self.sent()
        await self.line("etrafa bi bakiyim")
        visitor = self.caller(link)
        visitor["came_from"] = "elsewhere"
        self.world["location"], here = "other", self.world["location"]
        campaign_time.advance(self.world, 3600, "rest", "test")
        await self.line("etrafa bi bakiyim")
        self.assertEqual(visitor["location"], "elsewhere")

    async def test_the_same_visitor_line_does_not_come_twice_running(self):
        link = await self.sent()
        await self.line("etrafa bi bakiyim")
        first = self.caller(link)["message"], self.world["flags"].get("turn_index")
        words = world_threads.job_lines("link", "caller")
        self.assertGreaterEqual(len(words["warned"]), 3)
        self.assertGreaterEqual(len(words["messages"]["warned"]), 3)
        lines = {world_happenings._caller_line(self.world, {"thread_id": f"link_{n:03d}", "tone": "warned"}, words)
                 for n in range(1, 4)}
        self.assertEqual(len(lines), 3)
        self.assertTrue(first)

    async def test_a_second_caller_waits_until_the_first_has_gone(self):
        link = await self.sent()
        other = world_happenings.tie(self.world, world_happenings.CALLER, "opened", {"id": "npc_other"},
                                     self.world["location"])
        campaign_time.advance(self.world, other["fires_at"] - world_threads._now(self.world) + 1, "rest", "test")
        await self.line("etrafa bi bakiyim")
        callers = [npc for npc in self.world["npcs"] if npc.get("caller_of")]
        self.assertEqual(len(callers), 1, callers)
        self.assertTrue(link)


class ReadingClient(PlayClient):
    """A reading on top of the scripted person."""

    def __init__(self, front, **kwargs):
        super().__init__(**kwargs)
        self.front = front

    def chat(self, *args, **kwargs):
        properties = (kwargs.get("format") or {}).get("properties", {})
        if "front" not in properties:
            return super().chat(*args, **kwargs)
        filled = {"person_id": "none", "place_id": "none", "offer_id": "none", "thing_id": "none", "answer": "none",
                  "inside": False, **self.front}
        return {"message": {"content": json.dumps({"intent": "narrative", "action": "narrative", "target": {
            "type": "none", "reference": "", "npc_id": "", "evidence_quote": ""}, "completion": "unclear",
            "confidence": 1.0, "front": filled}, ensure_ascii=False)}}


class TheLawFindsTheKiller(unittest.IsolatedAsyncioTestCase):
    asyncSetUp, asyncTearDown = OneTownScene.asyncSetUp, OneTownScene.asyncTearDown
    post_scene_turn, begin, say = OneTownScene.post_scene_turn, OneTownScene.begin, OneTownScene.say
    add_person, town, killed_earlier, wait = (OneTownScene.add_person, OneTownScene.town,
                                              OneTownScene.killed_earlier, OneTownScene.wait)
    guard_told_by_witness = GuardsActOnWhatTheyKnow.guard_told_by_witness
    deed = GuardsActOnWhatTheyKnow.deed

    async def stopped(self):
        """A witness told a guard, the guard has walked up and asked: the player has the next word."""
        guard = await self.guard_told_by_witness()
        with patch.object(world_reactions, "_d20", return_value=20):
            out = await self.wait("iki saat bekliyorum")
        self.assertIn("Dur bakalım", out["narration"])
        return guard

    async def held(self):
        guard = await self.stopped()
        with patch.object(bold_acts, "_check", return_value={"result": "BAŞARISIZ"}):  # the answer did not convince
            out = await self.say("ben dun tapinakta calistim, rahibe sor", PlayClient(spoken="Dinliyorum."))
        self.assertIn("karakola", out["narration"].casefold())
        self.assertFalse(self.world["combat"]["active"])
        return guard

    async def test_an_answer_that_convinces_the_guard_ends_the_stop(self):
        guard = await self.stopped()
        with patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}) as check:
            out = await self.say("ben dun tapinakta calistim, rahibe sor", PlayClient(spoken="Dinliyorum."))
        check.assert_called()
        self.assertNotIn("karakola", out["narration"].casefold())
        self.assertNotIn("hold", self.deed())
        out = await self.say("iyi aksamlar o zaman", PlayClient(spoken="Hm."))
        self.assertFalse(self.world["combat"]["active"], out["narration"])
        self.assertIsNone(world_reactions.arrester(self.world))
        self.assertTrue(guard)

    async def test_saying_nothing_to_the_guard_is_an_arrest(self):
        await self.stopped()
        with patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}) as check:
            out = await self.wait("iki saat bekliyorum")
        check.assert_not_called()
        self.assertIn("karakola", out["narration"].casefold())

    async def test_the_question_is_followed_by_an_arrest_not_a_shrug(self):
        guard = await self.held()
        self.assertIn("tutukluyorsun", bold_acts.speech_note(self.world, guard))

    async def test_talking_on_ends_in_a_fight(self):
        guard = await self.held()
        await self.say("yanlis adam bu", PlayClient(spoken="Yürü."))
        out = await self.say("dur bir konusalim", PlayClient(spoken="Yeter."))
        self.assertTrue(self.world["combat"]["active"], out["narration"])
        self.assertTrue(guard["hostile"])

    async def test_a_blow_is_a_fight_through_the_normal_door(self):
        guard = await self.held()
        guard.update(current_hp=80, max_hp=80)
        out = await self.say(f"{guard['name'].lower()}a saldiriyorum", PlayClient())
        self.assertTrue(self.world["combat"]["active"], out["narration"])

    async def test_walking_off_is_flight_and_a_good_roll_gets_away(self):
        guard = await self.held()
        with patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            out = await self.say("tuz hanindan cikiyorum, sokaga", PlayClient())
        self.assertNotEqual(self.world["location"], "inn", out["narration"])
        self.assertFalse(self.world["combat"]["active"], out["narration"])
        self.assertNotIn("hold", self.deed())
        self.assertIn("izini", out["narration"])
        self.assertTrue(world_reactions._lost_sight(self.world, guard))

    async def test_a_bad_roll_and_the_guard_has_caught_up(self):
        guard = await self.held()
        with patch.object(bold_acts, "_check", return_value={"result": "BAŞARISIZ"}):
            out = await self.say("tuz hanindan cikiyorum, sokaga", PlayClient())
        self.assertEqual(guard["location"], self.world["location"], out["narration"])
        self.assertTrue(self.world["combat"]["active"], out["narration"])

    async def test_a_bribe_that_lands_costs_the_coin_and_ends_the_arrest(self):
        guard = await self.held()
        self.world.setdefault("currency", {})["player"] = 1000
        client = ReadingClient({"kind": "speak_to", "person_id": guard["id"], "coin_cp": 500}, spoken="Hm.")
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}), patch.object(
                bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            out = await self.say("avucuna bes altin birakiyorum, beni gormedin", client)
            # A4: the coin held out opens the bribe card; only its confirmation rolls the word and moves the coin.
            self.assertNotIn(guard["id"], self.world["currency"], out["narration"])
            self.assertIn("500 bakır", out["narration"])
            card = out["state"]["economic_offer"]
            confirmed = await self.post_scene_turn(self.url, PlayClient(), {
                "message": "Teklifi onayla", "action_id": str(uuid.uuid4()),
                "economic_action": {"kind": "confirm", "offer_id": card["offer_id"],
                                    "confirmation_digest": card["confirmation_digest"]}})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(self.world["currency"][guard["id"]], 500, confirmed.text)
        self.assertIn("500 bakır", confirmed.json()["narration"])
        self.assertNotIn("hold", self.deed())
        self.assertFalse(self.world["combat"]["active"])

    async def test_a_bribe_that_fails_stays_in_the_purse_and_the_arrest_stands(self):
        guard = await self.held()
        self.world.setdefault("currency", {})["player"] = 1000
        client = ReadingClient({"kind": "speak_to", "person_id": guard["id"], "coin_cp": 10}, spoken="Hm.")
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}), patch.object(
                bold_acts, "_check", return_value={"result": "BAŞARISIZ"}):
            out = await self.say("al sana bir gumus, unut gitsin", client)
        self.assertNotIn(guard["id"], self.world["currency"], out["narration"])
        self.assertIn("hold", self.deed())

    async def test_giving_up_is_a_night_held_and_a_fine_and_it_is_over(self):
        guard = await self.held()
        self.world.setdefault("currency", {})["player"] = 1000
        clock = self.world["campaign_time"]["elapsed_seconds"]
        client = ReadingClient({"kind": "attempt", "deed": "yield"})
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
            out = await self.say("tamam tamam kilici birakiyorum, teslim oluyorum", client)
        self.assertIn("500 bakır", out["narration"])
        self.assertGreaterEqual(self.world["campaign_time"]["elapsed_seconds"], clock + 8 * 3600)
        self.assertEqual(self.world["location"], "post", out["narration"])
        self.assertTrue(self.deed().get("settled"))
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(guard["location"], "post")

    async def test_a_neutral_line_the_reading_took_for_giving_up_gives_up_nothing(self):
        guard = await self.held()
        self.world.setdefault("currency", {})["player"] = 1000
        clock = self.world["campaign_time"]["elapsed_seconds"]
        client = ReadingClient({"kind": "attempt", "deed": "yield"})
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
            out = await self.say("kilicimi siki tutup ona bakiyorum", client)
        self.assertEqual(self.world["currency"]["player"], 1000, out["narration"])
        self.assertEqual(self.world["location"], "inn")
        self.assertFalse(self.deed().get("settled"))
        self.assertLess(self.world["campaign_time"]["elapsed_seconds"], clock + 8 * 3600)
        self.assertTrue(guard)

    async def test_refusing_to_give_up_is_no_giving_up_however_it_was_read(self):
        await self.held()
        client = ReadingClient({"kind": "attempt", "deed": "yield"})
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
            await self.say("teslim olmuyorum, kilicimi da birakmiyorum", client)
        self.assertFalse(self.deed().get("settled"))

    async def test_going_along_in_plain_words_is_giving_up(self):
        for line in ("peki karakola geliyorum", "ellerimi kaldiriyorum", "tamam, silahimi yere birakiyorum"):
            with self.subTest(line=line):
                await self.held()
                client = ReadingClient({"kind": "attempt", "deed": "yield"})
                with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
                    await self.say(line, client)
                self.assertTrue(self.deed().get("settled"), line)

    async def test_coin_held_out_on_a_turn_that_never_settled_is_not_carried_on(self):
        await self.held()
        self.world.setdefault("currency", {})["player"] = 1000
        self.session._bribe_held_out = 500
        client = ReadingClient({"kind": "look"}, spoken="Hm.")
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
            await self.say("etrafa bakiyorum", client)
        self.assertEqual(self.world["currency"]["player"], 1000)
        self.assertFalse([data for data in self.world["flags"].get("economic_offers", {}).values()
                          if any(effect["kind"] == "bribe_accepted" for effect in data["on_accept"])])

    async def test_a_killing_of_someone_who_came_at_the_player_brings_no_arrest(self):
        await self.town()
        self.add_person("Kalila", "Haydut", location="shop", combat_status="dead", current_hp=0, hostile=True)
        self.world["flags"]["deeds"] = [{"kind": "killing", "text": "Kalila öldürüldü", "location": "shop",
                                         "victim_id": "npc_kalila", "witnesses": [], "turn": 3, "at": 0,
                                         "heard": [], "told": []}]
        await self.wait("iki saat bekliyorum")
        self.assertNotIn("hold", self.deed())


class LeavingTown(FrontScene):
    OUT = {"kind": "go_to", "place_id": front_proposal.WAY_OUT}

    def outer(self):
        return next((record for record in self.world["locations"].values()
                     if isinstance(record, dict) and record.get("place_kind") == "waystation"), None)

    def clock(self):
        return self.world["campaign_time"]["elapsed_seconds"]

    async def test_the_way_out_of_town_is_on_the_list(self):
        await self.begin()
        await self.line("etrafa bakiyorum")
        kinds = self.front_calls()[0]["properties"]["front"]["properties"]
        self.assertIn(front_proposal.WAY_OUT, kinds["place_id"]["enum"])

    async def goes_out(self, line):
        await self.begin()
        self.client.front = self.OUT
        clock = self.clock()
        out = await self.line(line)
        place = self.outer()
        self.assertIsNotNone(place, out["narration"])
        self.assertEqual(self.world["location"], place["id"], out["narration"])
        self.assertGreaterEqual(self.clock(), clock + 1800)
        self.assertNotIn("içeri", out["narration"])
        people = [npc for npc in self.world["npcs"] if npc.get("location") == place["id"]]
        self.assertGreaterEqual(len(people), 2, people)
        self.assertEqual(self.routes()[-1]["owner"], "grounded_action")

    async def test_out_by_the_north_road(self):
        await self.goes_out("sehrin disina cikiyorum, kuzey yoluna")

    async def test_out_for_another_city(self):
        # A bare name Python has no record of could be a person or a house of this town; the road out has to be said.
        await self.goes_out("luskan'a gidiyorum, sehirden cikip kuzey yolundan")

    async def test_out_past_the_walls(self):
        await self.goes_out("surlarin disina gidiyorum")

    async def test_out_of_a_house_with_a_long_line(self):
        await self.goes_out("konaktan cikiyorum. kahyaya goz kirpip sokaga, sehrin kuzey kapisina dogru yuruyorum, surlarin disinda is var mi bakicam")

    async def test_the_road_on_is_a_person_saying_why_not_now_and_nothing_moves(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("sehrin disina cikiyorum")
        here, clock = self.world["location"], self.clock()
        out = await self.line("yola devam, bi gun yuruyorum kuzeye")
        self.assertEqual((self.world["location"], self.clock()), (here, clock), out["narration"])
        self.assertTrue(any(sign in out["narration"] for sign in ("“",)), out["narration"])
        self.assertEqual(self.routes()[-1]["owner"], "travel")
        self.assertEqual(self.routes()[-1]["status"], "not_now")

    async def test_the_road_on_read_as_an_attempt_is_still_no_journey(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("sehrin disina cikiyorum")
        here, clock = self.world["location"], self.clock()
        self.client.front = {"kind": "attempt"}
        out = await self.line("yola devam, bi gun yuruyorum kuzeye. luskan yonune")
        self.assertEqual((self.world["location"], self.clock()), (here, clock), out["narration"])
        self.assertEqual(self.routes()[-1]["status"], "not_now")

    async def test_a_far_city_read_as_the_street_stays_on_the_road(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("sehrin disina cikiyorum")
        here = self.world["location"]
        self.client.front = {"kind": "go_to", "place_id": self.outer()["parent_location_id"]}
        out = await self.line("luskan'a gidiyorum")
        self.assertEqual(self.world["location"], here, out["narration"])
        self.assertEqual(self.routes()[-1]["status"], "not_now")

    async def test_those_out_there_answer_and_the_house_left_behind_does_not(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("sehrin disina cikiyorum")
        person = local_places.resident_of(self.world, self.world["location"])
        self.client.front = {"kind": "speak_to", "person_id": person["id"]}
        out = await self.line("yolda kervan muhafizi arayan biri var mi, kervancilara soruyorum", "Burada iş az.")
        self.assertIn("Burada iş az.", out["narration"])

    async def test_a_question_about_the_gate_walks_nobody(self):
        await self.begin()
        where = self.world["location"]
        self.client.front = self.OUT
        out = await self.line("sehirden nasil cikilir?")
        self.assertEqual(self.world["location"], where, out["narration"])

    async def test_coming_back_takes_the_walk_too(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("sehrin disina cikiyorum")
        clock = self.clock()
        city = self.outer()["parent_location_id"]
        self.client.front = {"kind": "go_to", "place_id": city}
        out = await self.line("sehre geri donuyorum")
        self.assertEqual(self.world["location"], city, out["narration"])
        self.assertGreaterEqual(self.clock(), clock + 1800)

    async def test_news_and_callers_still_reach_the_gate_road(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("sehrin disina cikiyorum")
        self.assertEqual(local_places.settlement_of(self.world, self.world["location"]),
                         self.outer()["parent_location_id"])


class WhatTheScreenShows(FrontScene):
    DRAWER = ("Sağlam bir hamleyle çektiğinde sıkışan ahşap çekmece gıcırtıyla açılıyor ve içinde katlanmış "
              "eski bir parşömen parçası ile paslı demir bir anahtar ortaya çıkıyor.")

    def shown(self, text):
        self.session.messages.append({"role": "assistant", "content": text})

    def lying_here(self, *names):
        """A5 (C9): what the screen shows is taken only when it really lies here; the words alone make nothing."""
        ground = self.world.setdefault("ground_items_by_location", {}).setdefault(self.world["location"], [])
        ground.extend({"item_id": f"item_here_{index}", "name": name} for index, name in enumerate(names))

    def bag(self):
        return " ".join(str(item.get("name") if isinstance(item, dict) else item) for item in self.world["inventory"])

    async def test_two_things_in_one_line_both_reach_the_bag_and_the_screen_says_so(self):
        await self.begin()
        self.shown(self.DRAWER)
        self.lying_here("Parşömen", "Anahtar")
        self.client.front = {"kind": "take", "thing_word": "parşömen"}
        out = await self.line("parşömenle anahtarı alıyorum")
        self.assertIn("arşömen", self.bag())
        self.assertIn("nahtar", self.bag())
        self.assertIn("arşömen", out["narration"])
        self.assertIn("nahtar", out["narration"])
        self.assertNotIn("eline geçen", out["narration"])

    async def take_and(self, tail):
        await self.begin()
        name = self.npc["name"]
        self.shown(f"Masanın üstünde bir parşömen var; {name} kapının yanında duruyor.")
        self.lying_here("Parşömen")
        self.client.front = {"kind": "take", "thing_word": "parşömen"}
        out = await self.line("parşömeni alıp " + tail.format(name=name))
        self.assertIn("arşömen", self.bag(), out["narration"])
        self.assertNotIn("Kapı", self.bag(), out["narration"])
        self.assertNotIn(name, self.bag(), out["narration"])

    async def test_a_door_closed_in_the_same_line_stays_out_of_the_bag(self):
        await self.take_and("kapıyı kapatıyorum")

    async def test_a_person_called_in_the_same_line_stays_out_of_the_bag(self):
        await self.take_and("{name}'i çağırıyorum")

    async def test_a_person_called_over_in_the_same_line_stays_out_of_the_bag(self):
        await self.take_and("{name}i yanıma çağırıyorum")

    async def test_a_reading_that_names_two_things_in_its_one_word_takes_both(self):
        await self.begin()
        self.shown("Çekmecenin dibinden küçük bir çivi ile katlanmış bir mendil çıkıyor.")
        self.lying_here("Çivi", "Mendil")
        self.client.front = {"kind": "take", "thing_word": "çivi ve mendil"}
        out = await self.line("çiviyi alıyorum, mendili de cebe atıyorum")
        self.assertIn("Çivi", self.bag(), out["narration"])
        self.assertIn("Mendil", self.bag())

    async def test_a_key_the_screen_showed_can_be_taken(self):
        await self.begin()
        self.shown(self.DRAWER)
        self.lying_here("Anahtar")
        self.client.front = {"kind": "take", "thing_word": "anahtar"}
        out = await self.line("anahtari aliyorum")
        self.assertIn("nahtar", self.bag(), out["narration"])

    async def test_a_coin_the_screen_showed_still_comes_by_python_only(self):
        await self.begin()
        self.shown("Çekmecede üç altın duruyor.")
        before = self.bag()
        self.client.front = {"kind": "take", "thing_word": "altın"}
        await self.line("altinlari aliyorum")
        self.assertEqual(self.bag(), before)

    async def test_what_is_in_the_bag_is_not_cut_from_the_narration(self):
        await self.begin()
        self.world["inventory"].append("Eski parşömen")
        told = "Parşömeni alıyorsun."
        kept = pocket.without_the_taking(told, pocket.not_in_bag(self.world, ("parsomen", "yumurta")))
        self.assertEqual(kept, told)
        self.assertEqual(pocket.not_in_bag(self.world, ("parsomen", "yumurta")), ("yumurta",))

    async def test_a_key_stays_out_of_what_a_finding_may_say(self):
        await self.begin()
        self.session._front_found = ("Masanın altında paslı bir anahtar duruyor.", "masa")
        self.assertIsNone(self.session._inspection_findings("masanin altina bakiyorum", "success"))

    async def test_someone_on_the_screen_called_by_another_word_is_real(self):
        await self.begin()
        self.world["flags"].pop("active_npc_id", None)
        self.shown("Yaşlı adam uzatılan gümüşe bakıyor, kaşları çatık bir halde parmağını kırık çömlekten çekiyor.")
        self.client.front = {"kind": "speak_to", "person_word": "yaşlı adam"}
        out = await self.line("tamam dede de bakalim burda koruma arayan bi soylu var mi", "Vardır elbet.")
        self.assertIn("Vardır elbet.", out["narration"])
        made = next(npc for npc in self.world["npcs"] if npc.get("id") == self.world["flags"]["active_npc_id"])
        self.assertEqual(made["location"], self.world["location"])

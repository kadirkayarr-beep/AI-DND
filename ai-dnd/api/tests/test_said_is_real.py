"""What the screen says happened happened: items, hand-overs, work and blows are Python's to commit.

Real app, real engine; only the Ollama client is scripted. Lines are typed the way the owner types them.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import campaign_time
import equipment_economy
import front_proposal
import living_world
import world_threads
from api.tests import test_front_proposal as front_tests
from api.tests import test_experimental_npc_dialogue as speech
from api.tests import test_thread_errand as errand_tests
from api.tests import test_thread_gate as gate_tests


class Table(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    open_job = gate_tests.ThreadTable.open_job
    line = gate_tests.ThreadTable.line
    status = gate_tests.ThreadTable.status
    offer = gate_tests.ThreadTable.offer
    begin = front_tests.FrontTable.begin
    routes = front_tests.FrontTable.routes


class ClassifiedClient(front_tests.FrontClient):
    """A classifier that heard something else than the line says, as a small model does."""

    intent = None
    narrator_extra = {}
    speech_extra = {}

    def chat(self, *args, **kwargs):
        properties = (kwargs.get("format") or {}).get("properties") or {}
        if "narration" in properties and "intent" not in properties:
            self.chat_calls += 1
            self.schemas.append(kwargs.get("format"))
            self.message_batches.append(kwargs.get("messages", []))
            packet = {"narration": self.narration, "world_updates": {}, "lore_claims": []}
            return {"message": {"content": json.dumps({**packet, **self.narrator_extra}, ensure_ascii=False)}}
        reply = super().chat(*args, **kwargs)
        if self.speech_extra and "commitment" in properties:
            packet = json.loads(reply["message"]["content"])
            reply = {"message": {"content": json.dumps({**packet, **self.speech_extra}, ensure_ascii=False)}}
        if self.intent and "intent" in properties:
            packet = json.loads(reply["message"]["content"])
            packet.update(intent=self.intent, action=self.intent)
            reply = {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return reply


class BlowsThatRan(Table):
    async def fight(self):
        await self.begin()
        self.client = ClassifiedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.npc.update(armor_class=8, max_hp=40, current_hp=40)
        self.session.character.update(max_hp=300, current_hp=300)
        await self.line("marek'in suratina vuruyorum")
        self.assertTrue(self.world["combat"]["active"])

    async def test_a_blow_with_a_do_not_kill_beside_it_is_still_a_blow(self):
        await self.fight()
        reply = await self.line("bir daha kabzayla vuruyorum, bayilt onu, oldurme")
        self.assertEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_blow_said_with_i_am_not_killing_him_is_still_a_blow(self):
        await self.fight()
        reply = await self.line("vuruyorum yine ama oldurmuyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_line_that_refuses_every_blow_stays_no_blow(self):
        await self.fight()
        reply = await self.line("vurmuyorum, saldirmiyorum")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_fall_nothing_caused_leaves_the_line(self):
        await self.fight()
        self.client.intent = "attack"
        self.client.narration = ("Taş avluda rüzgâr esiyor. Marek geriye doğru sendeliyor, "
                                 "gözlerinde şaşkınlıkla yere yığılıyor.")
        reply = await self.line("kilici kaldirip tehditkar bir hamle yapiyorum")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack")
        self.assertNotIn("yığılıyor", reply["narration"])

    async def test_a_refused_blow_is_not_told_as_a_hit(self):
        await self.fight()
        self.client.intent = "attack"
        self.client.narration = "Marek bir darbe alır ve yere yığılıyor."
        reply = await self.line("onu oldurmuyorum")
        self.assertNotIn("darbe", reply["narration"])
        self.assertNotIn("yığılıyor", reply["narration"])


class ErrandBase(unittest.IsolatedAsyncioTestCase):
    """A real offered errand with the front reading on, its answer scripted turn by turn."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    job = errand_tests.ErrandTable.job
    line = errand_tests.ErrandTable.line
    status = errand_tests.ErrandTable.status
    row = errand_tests.ErrandTable.row
    wallet = errand_tests.ErrandTable.wallet
    parcel_owner = errand_tests.ErrandTable.parcel_owner
    recipient = errand_tests.ErrandTable.recipient
    go_to_recipient = errand_tests.ErrandTable.go_to_recipient

    routes = front_tests.FrontTable.routes

    async def errand(self, noun="buluşma notu", pay=10, front=True):
        await self.job(noun=noun, pay=pay)
        if front:
            self.directory = tempfile.TemporaryDirectory()
            self.addCleanup(self.directory.cleanup)
            self.route_file = Path(self.directory.name) / "routes.jsonl"
            self.enterContext(patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1",
                                                      "AI_DND_ROUTE_LOG": str(self.route_file)}))
        self.client = ClassifiedClient("Şimdilik sessiz bir gün.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))

    def parcel(self):
        return "parcel:" + world_threads.by_id(self.world, self.tid)["quest_id"]

    def bag(self):
        return [item.get("name") if isinstance(item, dict) else item for item in self.world.get("inventory", [])]


class SayingYes(ErrandBase):
    async def test_the_real_price_said_back_is_a_yes_not_a_bargain(self):
        await self.errand(front=False)
        await self.line("tamam o notu alirim, on bakir", "Peki, al öyleyse.")
        self.assertEqual(self.status(), "accepted")

    async def test_another_price_is_still_a_bargain(self):
        await self.errand(front=False)
        await self.line("tamam o notu alirim, on bes bakir", "Olmaz.")
        self.assertEqual(self.status(), "offered")

    async def test_a_yes_with_a_question_beside_it_is_a_yes(self):
        await self.errand(noun="yol kapanışı duyurusu", pay=25, front=False)
        await self.line("peki tamam alirim isi, nerden alacam duyuruyu", "Benden alacaksın.")
        self.assertEqual(self.status(), "accepted")

    async def test_the_front_yes_stands_on_the_real_price(self):
        await self.errand()
        self.client.front = {"kind": "offer_answer", "offer_id": self.tid, "answer": "accept"}
        await self.line("eh iyi madem, on bakira razi geldim", "Peki.")
        self.assertEqual(self.status(), "accepted")

    async def test_the_thing_offered_taken_is_the_job_and_the_real_paper_in_the_bag(self):
        await self.errand()
        self.client.front = {"kind": "take", "offer_id": self.tid}
        await self.line("hadi uzat su kagidi", "Peki, al öyleyse.")
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.client.front = {"kind": "unclear"}
        text = (await self.line("notu acip okuyorum gizlice"))["narration"]
        self.assertIn("Kâğıtta şunlar yazıyor", text)


class HandingOver(ErrandBase):
    async def carried(self):
        await self.errand(noun="yol kapanışı duyurusu", pay=25)
        self.client.front = {"kind": "take", "offer_id": self.tid}
        await self.line("ver bakalim su duyuruyu", "Al.")
        self.assertEqual(self.parcel_owner(), ["player"])
        return self.go_to_recipient()

    async def test_any_wording_of_a_hand_over_pays(self):
        for line in ("al sana duyuruyu veriyorum, iste bu", "duyuruyu lavunelin eline veriyorum",
                     "su kagidi masaya birakiyom buyur", "bak sana getirdigim sey bu"):
            await self.carried()
            person = self.recipient()
            self.client.front = {"kind": "hand_over", "person_id": person["id"], "item_id": self.parcel()}
            reply = await self.line(line)
            self.assertEqual(self.wallet(), 25, line)
            self.assertEqual(self.parcel_owner(), [person["id"]], line)
            self.assertEqual(reply["turn_outcome"]["action"], "item_transfer", line)

    async def test_one_person_here_needs_no_name(self):
        await self.carried()
        self.client.front = {"kind": "hand_over", "item_id": self.parcel()}
        await self.line("buyur iste bu")
        self.assertEqual(self.wallet(), 25)

    async def test_the_wrong_person_gets_nothing_and_answers(self):
        await self.carried()
        self.world["location"] = self.city
        self.world["flags"].update(active_npc_id=self.owner["id"], last_npc_id=self.owner["id"])
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"], "item_id": self.parcel()}
        reply = await self.line("sana veriyorum bunu, hadi al", "Bu bana gelmez.")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.assertEqual(self.wallet(), 0)
        self.assertIn("Bu bana gelmez", reply["narration"])

    async def test_a_question_about_handing_it_over_moves_nothing(self):
        await self.carried()
        person = self.recipient()
        self.client.front = {"kind": "hand_over", "person_id": person["id"], "item_id": self.parcel()}
        await self.line("sana mi vereyim bunu?", "Bana ver tabii.")
        self.assertEqual(self.parcel_owner(), ["player"])

    async def test_a_thing_of_the_bag_goes_to_the_person_for_real(self):
        await self.errand()
        equipment_economy.grant_plain(self.world, "Kırık halka")
        item = next(i for i in self.world["inventory"] if isinstance(i, dict) and i.get("name") == "Kırık halka")
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"], "item_id": item["item_id"]}
        reply = await self.line("sunu sana uzatiyorum usta, sakla", "Sağ ol, dursun bende.")
        self.assertNotIn("Kırık halka", self.bag())
        self.assertIn(item, self.owner["inventory"])
        self.assertIn("Sağ ol", reply["narration"])

    async def test_a_worn_blade_stays_off_the_list(self):
        await self.errand()
        held = set((self.world.get("equipment") or {}).values())
        listed = front_proposal.listing(self.session)
        self.assertFalse(held & {row["id"] for row in listed["bag"]})

    async def test_an_id_nobody_listed_moves_nothing(self):
        await self.carried()
        person = self.recipient()
        self.client.front = {"kind": "hand_over", "person_id": person["id"], "item_id": "item_999"}
        await self.line("hadi bakalim, senin icin getirdim", "Hm.")
        self.assertEqual(self.routes()[-1]["route"], "fallback:invalid")

    async def test_giving_what_is_not_there_is_told_as_it_is(self):
        await self.errand()
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"]}
        reply = await self.line("duyuruyu eline veriyorum", "Neyi?")
        self.assertIn("Neyi?", reply["narration"])
        self.assertEqual(self.wallet(), 0)


class TakingThings(ErrandBase):
    async def shown(self, words="Lavunel bakır defterine bir şeyler kaydediyor."):
        await self.errand()
        self.session.messages.append({"role": "assistant", "content": words})

    async def test_something_the_screen_showed_comes_into_the_bag_for_real(self):
        await self.shown()
        self.client.front = {"kind": "take", "thing_word": "defter"}
        reply = await self.line("defteri aliyorum elinden")
        self.assertIn("Defter", self.bag())
        self.assertEqual(reply["turn_outcome"]["action"], "pocket")
        self.client.front = {"kind": "unclear"}
        text = (await self.line("defteri okuyorum"))["narration"]
        self.assertNotIn("kitap yok", text)
        self.assertIn("Defter", text)

    async def test_the_job_parcel_in_the_owner_hands_is_listed_and_taken(self):
        await self.errand()
        await self.line("olur", "Tamam.")
        errand_tests.ErrandTable.owner_still_holds_it(self)
        self.client.front = {"kind": "take", "item_id": self.parcel()}
        await self.line("hadi uzat bakalim su seyi")
        self.assertEqual(self.parcel_owner(), ["player"])

    async def test_a_coin_purse_never_comes_this_way_and_the_line_drops_the_claim(self):
        await self.shown("Arşivci keseyi masaya bırakıyor.")
        self.client.front = {"kind": "take", "thing_word": "kese"}
        self.client.narration = "Masadaki keseyi kavrayıp ağırlığını tartıyorsun. Odada kısa bir sessizlik oluyor."
        reply = await self.line("keseyi aliyorum")
        self.assertNotIn("Kese", self.bag())
        self.assertNotIn("kavrayıp", reply["narration"])
        self.assertIn("sessizlik", reply["narration"])

    async def test_a_thing_nobody_showed_stays_out_of_the_bag_and_out_of_the_line(self):
        await self.shown()
        self.client.front = {"kind": "take", "thing_word": "yumurta"}
        self.client.narration = "Ejderha yumurtasını alıyorsun."
        reply = await self.line("ejderha yumurtasini aliyorum")
        self.assertNotIn("Yumurta", self.bag())
        self.assertNotIn("yumurtasını alıyorsun", reply["narration"])
        self.assertTrue(reply["narration"].strip())

    async def test_the_players_own_echo_shows_nothing(self):
        await self.shown("Sen: “defteri aliyorum”\n\nRüzgâr esiyor.")
        self.client.front = {"kind": "take", "thing_word": "defter"}
        await self.line("defteri aliyorum")
        self.assertNotIn("Defter", self.bag())

    async def test_taking_it_twice_makes_no_second_one(self):
        await self.shown()
        self.client.front = {"kind": "take", "thing_word": "defter"}
        await self.line("defteri aliyorum elinden")
        await self.line("defteri aliyorum elinden")
        self.assertEqual(self.bag().count("Defter"), 1)


class TheChannel(ErrandBase):
    async def test_a_person_handing_over_the_job_parcel_really_hands_it(self):
        await self.errand()
        await self.line("olur", "Tamam.")
        errand_tests.ErrandTable.owner_still_holds_it(self)
        self.client.front = {"kind": "speak_to", "person_id": self.owner["id"]}
        self.client.speech_extra = {"commitment": {"kind": "give", "item": self.parcel()}}
        await self.line("e nerde bu kagit simdi", "Al işte, burada.")
        self.assertEqual(self.parcel_owner(), ["player"])

    async def test_a_person_handing_over_a_plain_thing_really_hands_it(self):
        await self.errand()
        self.client.front = {"kind": "speak_to", "person_id": self.owner["id"]}
        self.client.speech_extra = {"commitment": {"kind": "give", "item": "elma"}}
        reply = await self.line("acim usta bi sey var mi", "Al şu elmayı, ye.")
        self.assertIn("Elma", self.bag())
        self.assertIn("elmayı", reply["narration"])

    async def test_a_purse_nobody_moved_leaves_the_speech(self):
        await self.errand()
        self.client.front = {"kind": "speak_to", "person_id": self.owner["id"]}
        self.client.speech_extra = {"commitment": {"kind": "give", "item": "kese"}}
        self.client.stage_direction = "Keseyi masaya bırakır."
        reply = await self.line("usta hakkimi ver", "Al şu keseyi. Hayırlı işler.")
        self.assertNotIn("keseyi", reply["narration"].casefold())
        self.assertIn("Hayırlı işler", reply["narration"])
        self.assertNotIn("Kese", self.bag())

    def alone(self):
        for npc in self.world["npcs"]:
            npc["location"] = "elsewhere"
        for key in ("active_npc_id", "last_npc_id"):
            self.world["flags"].pop(key, None)

    async def test_the_narrator_can_put_a_thing_in_the_bag_through_the_channel(self):
        await self.errand()
        self.alone()
        self.client.front = {"kind": "attempt"}
        self.client.narration = "Tezgâhın altından çıkan ipi eline alıyorsun."
        self.client.narrator_extra = {"item_claims": [{"item": "ip", "to": "player"}]}
        reply = await self.line("tezgahin altindaki ipi aliyorum")
        self.assertIn("Ip", self.bag())
        self.assertIn("ipi", reply["narration"])

    async def test_a_thing_told_as_given_away_that_never_moved_leaves_the_line(self):
        await self.errand()
        self.alone()
        self.client.front = {"kind": "attempt"}
        self.client.narration = "Halkayı ona veriyorsun. Rüzgâr esiyor."
        self.client.narrator_extra = {"item_claims": [{"item": "halka", "to": "person"}]}
        reply = await self.line("sessizce bekliyorum orda")
        self.assertNotIn("Halkayı", reply["narration"])

    async def test_the_prompts_know_what_is_really_in_the_bag(self):
        await self.errand()
        equipment_economy.grant_plain(self.world, "Kırık halka")
        self.client.front = {"kind": "speak_to", "person_id": self.owner["id"]}
        await self.line("usta bi sey soracam", "Sor.")
        self.assertIn("Kırık halka", str(self.client.message_batches[-1]))
        self.alone()
        self.client.front = {"kind": "attempt"}
        await self.line("biraz ortaligi kolacan ediyorum")
        self.assertIn("Kırık halka", str(self.client.message_batches[-1]))

    async def test_handing_over_what_is_not_there_keeps_no_taking_gesture(self):
        await self.errand()
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"]}
        self.client.stage_direction = "Kâğıdı alıp defterinin yanına çeker."
        reply = await self.line("duyuruyu eline veriyorum", "Bakalım.")
        self.assertNotIn("Kâğıdı", reply["narration"])


class Working(Table):
    async def hired(self):
        await self.begin()
        self.client = ClassifiedClient("Şimdilik sessiz bir gün.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.offer()
        await self.line("olur", "Güzel.")
        self.assertEqual(self.status(), "accepted")
        self.worked = {"kind": "work", "job_id": self.thread["thread_id"]}

    def clock(self):
        return campaign_time.public_time(self.world)

    def wallet(self):
        return self.world.get("currency", {}).get("player", 0)

    def job(self):
        return world_threads.by_id(self.world, self.thread["thread_id"])

    async def set_hour(self, hour):
        now = self.clock()
        self.session.advance_campaign_time(((hour - now["hour"]) % 24) * 3600 - now["minute"] * 60, "wait")

    async def test_natural_lines_start_the_work(self):
        await self.hired()
        self.client.front = self.worked
        start = self.world["campaign_time"]["elapsed_seconds"]
        reply = await self.line("raflara giriyorum, kayitlari ayiklamaya basliyorum, bir yandan da gravusa geceni okuyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "work")
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"] - start, 8 * 3600)
        self.assertEqual(self.wallet(), 10)

    async def test_until_the_evening_is_until_the_evening(self):
        await self.hired()
        await self.set_hour(15)
        self.client.front = self.worked
        reply = await self.line("aksama kadar calisiyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "work")
        self.assertEqual(self.clock()["hour"], 18)
        self.assertEqual(self.wallet(), 0)
        self.assertNotIn("gün boyu", reply["narration"])
        self.assertEqual(self.job()["shift_seconds"], 3 * 3600)

    async def test_two_days_of_work_are_two_days_of_pay(self):
        await self.hired()
        await self.set_hour(9)
        day = self.clock()["day_index"]
        self.client.front = self.worked
        reply = await self.line("isi yapiyorum iki gun boyunca burda")
        self.assertEqual(self.wallet(), 20)
        self.assertEqual(self.clock()["day_index"], day + 1)  # the evening of the second day
        self.assertEqual(self.clock()["hour"], 17)
        self.assertIn("20 bakır", reply["narration"])

    async def test_no_more_days_are_worked_than_the_job_has(self):
        await self.hired()
        await self.set_hour(9)
        day = self.clock()["day_index"]
        self.client.front = self.worked
        await self.line("bes gun boyunca calisiyorum burda")
        self.assertEqual(self.wallet(), 20)
        self.assertEqual(self.clock()["day_index"], day + 1)

    async def test_a_promise_of_work_is_no_shift(self):
        await self.hired()
        self.client.front = self.worked
        start = self.world["campaign_time"]["elapsed_seconds"]
        await self.line("yarin calisirim tamam mi", "Olur.")
        self.assertLess(self.world["campaign_time"]["elapsed_seconds"] - start, 3600)
        self.assertEqual(self.wallet(), 0)

    async def test_the_list_holds_only_work_really_in_hand(self):
        await self.begin()
        listed = front_proposal.listing(self.session)
        self.assertEqual(listed["jobs"], [])

    async def test_until_the_evening_needs_no_front_reading(self):
        await self.hired()
        await self.set_hour(15)
        self.client.front = {"kind": "unclear"}
        reply = await self.line("aksama kadar calisiyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "work")
        self.assertEqual(self.clock()["hour"], 18)

    async def test_days_of_work_said_after_a_paid_day_start_tomorrow(self):
        await self.hired()
        await self.set_hour(9)
        self.client.front = self.worked
        await self.line("calisiyorum")
        self.assertEqual(self.wallet(), 10)
        day = self.clock()["day_index"]
        await self.line("isi yapiyorum iki gun boyunca burda")
        self.assertEqual(self.wallet(), 20)
        self.assertEqual(self.clock()["day_index"], day + 1)

    async def test_the_last_day_said_as_days_after_a_paid_day_is_paid_tomorrow(self):
        await self.hired()
        await self.set_hour(9)
        self.client.front = self.worked
        await self.line("calisiyorum")
        await self.line("isi yapiyorum bes gun boyunca burda")
        self.assertEqual(self.wallet(), 20)

    async def test_the_prompt_says_work_is_at_hand_only_when_it_is(self):
        await self.begin()
        await self.line("etrafa sakin sakin bakiniyorum")
        self.assertNotIn("jobs listesi dolu", str(self.client.message_batches))
        self.offer()
        await self.line("olur", "Güzel.")
        await self.line("etrafa sakin sakin bakiniyorum")
        self.assertIn("jobs listesi dolu", str(self.client.message_batches))


class SmallModelSlips(ErrandBase):
    async def test_a_word_copied_with_its_ending_is_still_the_thing(self):
        await self.errand()
        self.session.messages.append({"role": "assistant", "content": "Marek bakır defterine yazıyor."})
        self.client.front = {"kind": "take", "thing_word": "defteri"}
        await self.line("defteri aliyorum elinden")
        self.assertIn("Defter", self.bag())

    async def test_a_purse_copied_with_its_ending_is_still_a_purse(self):
        await self.errand()
        self.session.messages.append({"role": "assistant", "content": "Marek keseyi masaya koyuyor."})
        self.client.front = {"kind": "take", "thing_word": "keseyi"}
        self.client.narration = "Keseyi kavrıyorsun. Odada kısa bir sessizlik oluyor."
        reply = await self.line("keseyi aliyorum")
        self.assertNotIn("Kese", self.bag())
        self.assertNotIn("Keseyi", " ".join(self.bag()))
        self.assertNotIn("kavrıyorsun", reply["narration"])

    async def test_a_taking_that_failed_is_told_to_the_narrator(self):
        await self.errand()
        self.client.front = {"kind": "take", "thing_word": "yumurta"}
        await self.line("ejderha yumurtasini aliyorum")
        self.assertIn("eline hiçbir şey geçmedi", str(self.client.message_batches[-1]))

    async def test_what_is_in_the_bag_is_answered_even_when_the_model_hears_a_look(self):
        await self.errand()
        self.client.front = {"kind": "look"}
        reply = await self.line("cantamda ne var")
        self.assertIn("Macera çantası", reply["narration"])
        self.assertEqual(self.client.chat_calls, 0)

    async def test_the_answer_wins_when_the_model_also_named_the_person(self):
        await self.errand()
        self.client.front = {"kind": "speak_to", "person_id": self.owner["id"], "offer_id": self.tid, "answer": "accept"}
        await self.line("eh iyi madem, hallederiz biz bu seyi", "Peki.")
        self.assertEqual(self.status(), "accepted")

    async def test_setting_to_the_offered_work_takes_it_and_works(self):
        await self.errand()
        thread = world_threads.by_id(self.world, self.tid)
        thread.update(type="hiring", terms={"pay": 20, "work_days": 2, "pay_basis": "total", "pay_timing": "end_of_day",
                                            "deadline_text": "iki gün içinde"})
        for key in ("target_place_id", "item_noun", "recipient_name"):
            thread.pop(key, None)
        self.client.front = {"kind": "work", "offer_id": self.tid}
        reply = await self.line("raflara giriyorum, isi yapmaya basliyorum, bir yandan da etrafa bakiyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "work")
        self.assertEqual(self.wallet(), 10)

    async def test_reading_the_note_still_in_the_owners_hand_brings_it_over(self):
        await self.errand()
        await self.line("olur", "Tamam.")
        errand_tests.ErrandTable.owner_still_holds_it(self)
        self.client.front = {"kind": "look"}
        reply = await self.line("notu acip okuyorum gizlice")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.assertIn("Kâğıtta şunlar yazıyor", reply["narration"])


    async def test_a_counter_never_goes_in_the_bag(self):
        await self.errand()
        feature = {"id": "feature_x", "name": "Çalışma tezgâhı"}
        self.session.messages.append({"role": "assistant", "content": "Burada çalışma tezgâhı var."})
        before = list(self.bag())
        self.client.front = {"kind": "unclear"}
        with patch.object(living_world, "visible_features", return_value=[feature]):
            await self.line("tezgahtaki seyi elime alip cebime atiyorum")
        self.assertEqual(self.bag(), before)

    async def test_a_condition_about_something_useful_is_no_shift(self):
        await self.errand()
        thread = world_threads.by_id(self.world, self.tid)
        thread.update(type="hiring", status="accepted", accepted_turn=0, terms={
            "pay": 20, "work_days": 2, "pay_basis": "total", "pay_timing": "end_of_day", "deadline_text": "iki gün içinde"})
        self.client.front = {"kind": "look"}
        start = self.world["campaign_time"]["elapsed_seconds"]
        await self.line("yerde bi sey var mi diye bakiniyorum, ise yarar bi sey bulursam aliyorum")
        self.assertLess(self.world["campaign_time"]["elapsed_seconds"] - start, 3600)

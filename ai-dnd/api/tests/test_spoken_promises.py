"""What a person says about work and pay reaches the engine, or leaves the line.

The lines are the owner's own from the failed play: money existed only in narration and
the sergeant denied, word for word, what he had said the day before.
"""

from __future__ import annotations

import json
import unittest
import uuid
from unittest.mock import patch

import game
import living_world
import npc_statements
import world_threads
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.town_seed import fixed_town

HOUR = 3600
DAY = 86400
ASK_ON_THE_SPOT = "elini uzat bakalım, sayıp alıyorum paraları keseye atıyorum"
ASK_NEXT_MORNING = "günaydın çavuş, bir gün geçti. dün dedin ya günlük ödenir diye, kağıtlar asılı duruyo. paramı ver"
ASK_AGAIN = "nasıl çıkmadı lan, 25 bakır 3 gün kabul ediyosan başla dedin. kağıtları da ben astım. şimdi ödeyecek misin"
DENIALS = ("hatırlardım", "ağzımdan çıkmadı", "anımsamıyorum", "sözüm yok", "yanlış kapıyı")


class PromiseClient(speech.ScriptedNpcSpeechClient):
    """The speech client, able to put the structured field in its reply."""

    commitment = None

    def chat(self, *args, **kwargs):
        reply = super().chat(*args, **kwargs)
        schema = kwargs.get("format") or {}
        if self.commitment is not None and "intent" not in schema.get("properties", {}):
            packet = json.loads(reply["message"]["content"])
            packet["commitment"] = self.commitment
            reply["message"]["content"] = json.dumps(packet, ensure_ascii=False)
        return reply


class Table(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def job(self, *, status="offered", pay=25, days=3, basis="total"):
        self.city, self.session_id, self.session, self.turn_url, self.npc = await self.campaign_with_npc()
        self.client = PromiseClient("Şimdilik sessiz bir gün.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world = self.session.world_state
        living_world.ensure_scene_state(self.world)
        self.world["flags"].update(active_npc_id=self.npc["id"], last_npc_id=self.npc["id"], active_npc_until_turn=999)
        self.world.pop(world_threads.KEY, None)
        world_threads.ensure(self.world)
        state = world_threads.view(self.world)
        self.npc["place_role_of"] = self.city
        self.thread = state["threads"][0]
        offer = "Doğrudur, duyuruları asacak yardımcı aranıyor. Ücret yirmi beş bakır, süre üç gün. Kabul ediyorsan başla."
        self.thread.update(type="hiring", template_id="hand_wanted", status="offered", place_id=self.city,
                           target_place_id=None, recipient_name=None, owner_name=self.npc["name"], expires_at=30 * DAY,
                           offered_at=0, offered_turn=self.world["flags"].get("turn_index", 0),
                           owner_npc_id=self.npc["id"], offer_line=offer, offer_line_turn=self.world["flags"].get("turn_index", 0),
                           owner_line="Duyuruları asacak yardımcı aranıyor. Ücret 25 bakır; süre 3 gün.",
                           terms={"pay": pay, "work_days": days, "pay_basis": basis, "pay_timing": "end_of_day",
                                  "deadline_text": "3 gün içinde"})
        self.thread.pop("night_only", None)
        state["threads"] = [self.thread]
        self.tid = self.thread["thread_id"]
        self.world["npc_speech_log"] = {self.npc["id"]: [{"player": "iş var mı", "npc": offer}]}
        npc_statements.record(self.world, self.npc, "iş var mı", offer, turn=None)
        if status == "accepted":
            world_threads.accept_hired(self.world, self.thread)

    async def line(self, message, reply=None, *, commitment=None, mode=None):
        if reply is not None:
            self.client.narration = reply
        self.client.commitment = commitment
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
            body["target_id"] = self.npc["id"]
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.world = self.session.world_state
        return response.json()

    def t(self):
        return world_threads.by_id(self.world, self.tid)

    def wallet(self):
        return self.world.get("currency", {}).get("player", 0)

    def pass_a_day(self):
        self.world["campaign_time"]["elapsed_seconds"] += DAY
        self.world["flags"]["turn_index"] = self.world["flags"].get("turn_index", 0) + 1
        self.t().update(expires_at=60 * DAY)

    def worked_a_while(self):
        self.world["flags"]["turn_index"] = self.world["flags"].get("turn_index", 0) + 3


class TheField(Table):
    async def test_the_reply_may_carry_the_field_and_need_not(self):
        await self.job()
        await self.line("selam", "Selam.")
        schema = self.client.schemas[-1]
        self.assertIn("commitment", schema["properties"])
        self.assertEqual(schema["required"], ["spoken_text", "stage_direction", "threat"])

    async def test_the_prompt_lists_the_jobs_by_id_and_his_own_words(self):
        await self.job(status="accepted")
        await self.line("selam", "Selam.", mode="say")
        prompt = str(self.client.message_batches)
        self.assertIn(self.tid, prompt)
        self.assertIn("Ücret yirmi beş bakır", prompt)

    async def test_a_firm_yes_with_more_around_it_takes_the_job_with_no_help(self):
        await self.job()
        await self.line("gör işte, ordu adamıyım. tamam kabul, bu gece kapıdayım", "Güzel.")
        self.assertEqual(self.t()["status"], "accepted")

    async def test_a_yes_that_goes_straight_on_to_the_work_takes_the_job_with_no_help(self):
        for line in ("iyi tamam. ver duyuruları, nereye asıcam bunları", "iyi tamam. ne yapıcam söyle, nereden başlıyım"):
            await self.job()
            await self.line(line, "Kapının yanındaki tahtaya as.")
            self.assertEqual(self.t()["status"], "accepted", line)

    async def test_a_softer_yes_reaches_the_person_who_says_what_came_of_it(self):
        await self.job()
        line = "tamam. duyuruları ver bakalım"
        await self.line(line, "Kapının yanındaki tahtaya as.", commitment={"kind": "job_accepted", "thread_id": self.tid})
        self.assertEqual(self.t()["status"], "accepted")

    async def test_the_field_takes_a_yes_once_the_offer_has_slipped_from_the_talk(self):
        await self.job()
        self.thread["offer_line_turn"] = -5
        self.world["npc_speech_log"][self.npc["id"]].append({"player": "hava güzel", "npc": "Güzel."})
        line = "iyi tamam. ver duyuruları, nereye asıcam bunları"
        await self.line(line, "Kapının yanındaki tahtaya as.", mode="say",
                        commitment={"kind": "job_accepted", "thread_id": self.tid})
        self.assertEqual(self.t()["status"], "accepted")

    async def test_taking_up_the_work_is_a_yes_the_person_can_point_at(self):
        await self.job()
        await self.line("dediğin işi yapıyorum, bitene kadar başından ayrılmıyorum", "Güzel, bakalım.", mode="say",
                        commitment={"kind": "job_accepted", "thread_id": self.tid})
        self.assertEqual(self.t()["status"], "accepted")

    async def test_the_model_still_cannot_say_yes_for_the_player(self):
        await self.job()
        await self.line("hmm", "Anlaştık o zaman, işe başladın.",
                        commitment={"kind": "job_accepted", "thread_id": self.tid})
        self.assertEqual(self.t()["status"], "offered")

    async def test_someone_elses_or_an_invented_id_records_nothing(self):
        await self.job()
        money = self.wallet()
        await self.line("iyi tamam. ver duyuruları", "Al.",
                        commitment={"kind": "job_accepted", "thread_id": "thread_999"})
        self.assertEqual(self.t()["status"], "offered")
        self.assertEqual(self.wallet(), money)

    async def test_a_promise_kind_goes_into_the_ledger(self):
        await self.job()
        await self.line("yarın kapıda olur musun", "Olurum, bekleyecek bir şeyim yok.",
                        commitment={"kind": "meet", "thread_id": "", "terms": "yarın kapıda"}, mode="say")
        open_ones = npc_statements.open_commitments(self.world, npc_id=self.npc["id"], kind="meet")
        self.assertTrue(open_ones)
        self.assertTrue(any("yarın kapıda" in " ".join(c.get("objects") or []) or c.get("terms") == "yarın kapıda"
                            for c in open_ones))

    async def test_a_promise_the_words_never_made_does_not_go_into_the_ledger(self):
        await self.job()
        await self.line("limana nerden gidilir", "Sağdan aşağı in.",
                        commitment={"kind": "escort", "thread_id": "", "terms": "limana kadar"}, mode="say")
        self.assertFalse(npc_statements.open_commitments(self.world, npc_id=self.npc["id"], kind="escort"))

    async def test_a_reply_with_a_broken_field_still_speaks(self):
        await self.job()
        text = (await self.line("selam", "Selam yabancı.", commitment={"kind": "pay", "amount_cp": "çok"}))["narration"]
        self.assertIn("Selam yabancı", text)


class Pay(Table):
    async def test_the_play_s_line_pays_a_real_job_through_the_wallet(self):
        await self.job(status="accepted")
        self.worked_a_while()
        money = self.wallet()
        reply = await self.line(ASK_ON_THE_SPOT, "Al bakalım, bugünkü hakkın.")
        self.assertEqual(self.wallet() - money, 8)
        self.assertEqual(self.t()["paid_cp"], 8)
        self.assertIn("8 bakır", reply["narration"])

    async def test_it_pays_on_the_fallback_too_when_no_model_answers(self):
        await self.job(status="accepted")
        self.worked_a_while()
        money = self.wallet()
        reply = await self.line(ASK_ON_THE_SPOT, "")  # a reply with nothing usable in it
        self.assertEqual(self.wallet() - money, 8)
        self.assertIn("8 bakır", reply["narration"])
        self.assertFalse(any(word in reply["narration"] for word in DENIALS), reply["narration"])

    async def test_the_field_alone_pays_a_way_of_asking_no_list_knows(self):
        await self.job(status="accepted")
        self.worked_a_while()
        money = self.wallet()
        reply = await self.line("hadi usta hesabı görelim artık", "Haklısın, al.", mode="say",
                                commitment={"kind": "pay", "thread_id": self.tid, "amount_cp": 25})
        self.assertEqual(self.wallet() - money, 8, "the day's share, whatever the model said")
        self.assertIn("8 bakır", reply["narration"])

    async def test_the_field_alone_pays_nothing_on_a_line_that_is_not_about_money(self):
        await self.job(status="accepted")
        self.worked_a_while()
        money = self.wallet()
        reply = await self.line("hava güzel bugün usta", "Al sana bugünkü hakkın, sekiz bakır.", mode="say",
                                commitment={"kind": "pay", "thread_id": self.tid, "amount_cp": 8})
        self.assertEqual(self.wallet(), money)
        self.assertEqual(self.t().get("paid_cp", 0), 0)
        self.assertNotIn("sekiz bakır", reply["narration"])

    async def test_words_that_refuse_what_was_just_paid_do_not_stand(self):
        await self.job(status="accepted")
        self.worked_a_while()
        reply = await self.line("paramı ver", "Hangi parayı, hiç anlamadım.")
        self.assertNotIn("anlamadım", reply["narration"])
        self.assertIn("8 bakır", reply["narration"])

    async def test_a_day_is_paid_once(self):
        await self.job(status="accepted")
        self.worked_a_while()
        await self.line(ASK_ON_THE_SPOT, "Al.")
        money = self.wallet()
        await self.line("kalanı da ver, paramı ver", "Bugünlük bu kadar.")
        self.assertEqual(self.wallet(), money)

    async def test_the_next_morning_pays_the_next_share_and_nobody_denies_anything(self):
        await self.job(status="accepted")
        self.worked_a_while()
        await self.line(ASK_ON_THE_SPOT, "Al.")
        self.pass_a_day()
        money = self.wallet()
        reply = await self.line(ASK_NEXT_MORNING, "Doğru, günlük ödenir dedim. Al.")
        self.assertEqual(self.wallet() - money, 8)
        self.assertIn("günlük ödenir", reply["narration"])

    async def test_the_last_day_takes_what_is_left_and_closes_the_job(self):
        await self.job(status="accepted")
        self.worked_a_while()
        money = self.wallet()
        for _ in range(3):
            await self.line("paramı ver", "Al.")
            if self.t()["status"] == "accepted":
                self.pass_a_day()
        self.assertEqual(self.wallet() - money, 25)
        self.assertEqual(self.t()["status"], "done")

    async def test_money_on_the_spot_after_a_handshake_is_not_owed(self):
        await self.job(status="accepted")
        money = self.wallet()
        await self.line("paramı ver", "Önce işi gör.")
        self.assertEqual(self.wallet(), money)
        self.assertIn("iş görmedi", str(self.client.message_batches))

    async def test_a_shift_already_paid_today_is_not_paid_again_by_asking(self):
        await self.job(status="accepted")
        self.worked_a_while()
        await self.line("başlayalım")
        money = self.wallet()
        await self.line("paramı ver", "Aldın ya bugünkünü.")
        self.assertEqual(self.wallet(), money)

    async def test_a_finished_job_is_not_paid_twice_and_the_person_knows_it(self):
        await self.job(status="accepted", days=1)
        self.worked_a_while()
        money = self.wallet()
        await self.line("paramı ver", "Al.")
        self.assertEqual(self.wallet() - money, 25)
        self.assertEqual(self.t()["status"], "done")
        await self.line(ASK_ON_THE_SPOT, "Aldın ya.")
        self.assertEqual(self.wallet() - money, 25)
        self.assertIn("parasını aldı", str(self.client.message_batches[-1]))

    async def test_the_person_is_told_last_that_the_coin_already_moved(self):
        await self.job(status="accepted")
        self.worked_a_while()
        await self.line("paramı ver", "Al.")
        note = self.client.message_batches[-1][-1]["content"]
        self.assertGreater(note.rindex("Oldu bitti"), note.rindex("commitment"))

    async def test_an_offer_nobody_took_pays_nothing(self):
        for line in ("önce paramı ver", ASK_ON_THE_SPOT):
            await self.job()
            money = self.wallet()
            reply = await self.line(line, "Peşin yok.")
            self.assertEqual(self.wallet(), money)
            self.assertEqual(self.t()["status"], "offered")
            self.assertIn("Peşin yok", reply["narration"], line)

    async def test_narration_cannot_pay_where_python_did_not(self):
        await self.job(status="accepted")
        money = self.wallet()
        reply = await self.line("paramı ver", "Al, yirmi beş bakır, say bakalım.", mode="say")
        self.assertEqual(self.wallet(), money)
        self.assertNotIn("yirmi beş bakır", reply["narration"])


class Repair(Table):
    async def test_a_wage_nobody_listed_leaves_the_line_and_the_rest_stays(self):
        await self.job()
        self.thread["status"] = "expired"
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        reply = await self.line("selam usta, ne var ne yok", "Hele bir düşüneyim. Sana kırk bakır veririm, akşama gel.", mode="say")
        self.assertNotIn("kırk bakır", reply["narration"])
        self.assertIn("Hele bir düşüneyim", reply["narration"])

    async def test_a_wrong_figure_for_a_real_job_gives_way_to_the_real_terms(self):
        await self.job()
        self.thread.update(status="open")
        self.thread.pop("offered_at", None)
        self.world.pop("npc_speech_log", None)
        reply = await self.line("iş var mı?", "Var. Sana kırk bakır veririm.", mode="say",
                                commitment={"kind": "job_offer", "thread_id": self.tid, "amount_cp": 40})
        self.assertNotIn("kırk bakır", reply["narration"])
        self.assertIn("25 bakır", reply["narration"])
        self.assertEqual(self.t()["status"], "offered")

    async def test_a_wary_person_who_names_the_real_terms_has_made_the_offer(self):
        await self.job()
        self.thread["status"] = "open"
        self.thread["thread_id"] = next(
            f"thread_{n:03d}" for n in range(1, 500)
            if world_threads._rank(living_world._campaign_seed(self.world), f"thread_{n:03d}", "wary") % 100
            < world_threads.WARY_PERCENT)
        self.tid = self.thread["thread_id"]
        self.world.pop("npc_speech_log", None)
        self.world.pop(npc_statements.KEY, None)
        await self.line("iş var mı?", "Yirmi beş bakır, üç gün. Kabul edersen başlarız.", mode="say")
        self.assertEqual(self.t()["status"], "offered")

    async def test_the_real_figures_from_the_owner_are_an_offer_whatever_the_line_was_read_as(self):
        await self.job()
        self.thread["status"] = "open"
        await self.line("ne verirsin bana", "Bir gün sürecek de değil, üç gün, ücreti yirmi beş bakır.", mode="say")
        self.assertEqual(self.t()["status"], "offered")

    async def test_pay_and_days_together_are_an_offer_with_no_promise_word(self):
        await self.job()
        self.thread["status"] = "open"
        await self.line("ne verirsin bana", "Nemli paketleri ayırma işi. Üç günlük, yirmi beş bakır.", mode="say")
        self.assertEqual(self.t()["status"], "offered")

    async def test_a_figure_with_no_promise_in_it_is_only_a_price(self):
        await self.job()
        reply = await self.line("bira ne kadar", "Bira iki bakır, sen de bilirsin.", mode="say")
        self.assertIn("iki bakır", reply["narration"])

    async def test_saying_there_is_not_a_copper_stays(self):
        await self.job()
        reply = await self.line("selam", "Cebimden çıkacak bir bakır bile yok.", mode="say")
        self.assertIn("bir bakır bile yok", reply["narration"])

    async def test_a_gift_of_coin_needs_coin_in_his_purse(self):
        await self.job()
        money = self.wallet()
        reply = await self.line("biraz para versene", "Al sana beş bakır, git başımdan.", mode="say",
                                commitment={"kind": "give", "thread_id": "", "amount_cp": 5})
        self.assertEqual(self.wallet(), money)
        self.assertNotIn("beş bakır", reply["narration"])
        self.world.setdefault("currency", {})[self.npc["id"]] = 7
        reply = await self.line("biraz para versene yahu", "Al sana beş bakır, git başımdan.", mode="say",
                                commitment={"kind": "give", "thread_id": "", "amount_cp": 5})
        self.assertEqual(self.wallet() - money, 5)
        self.assertEqual(self.world["currency"][self.npc["id"]], 2)
        self.assertIn("beş bakır", reply["narration"])


class Unasked(Table):
    async def test_a_gift_nobody_asked_about_moves_no_coin(self):
        await self.job()
        self.world.setdefault("currency", {})[self.npc["id"]] = 400
        money = self.wallet()
        reply = await self.line("selam", "Al sana yüz bakır, yolun açık olsun.", mode="say",
                                commitment={"kind": "give", "thread_id": "", "amount_cp": 100})
        self.assertEqual(self.wallet(), money)
        self.assertEqual(self.world["currency"][self.npc["id"]], 400)
        self.assertNotIn("yüz bakır", reply["narration"])


class Denial(Table):
    async def test_his_own_words_are_not_denied(self):
        await self.job(status="accepted")
        npc_statements.record(self.world, self.npc, "ne zaman ödersin",
                              "Üç günlük işin ücreti her günün sonunda ödenir, peşin avans vermem.", turn=None)
        reply = await self.line(ASK_NEXT_MORNING, "Evet, öyle dedim.")
        self.assertIn("öyle dedim", reply["narration"])
        self.assertFalse(any(word in reply["narration"] for word in DENIALS), reply["narration"])
        self.assertIn("her günün sonunda ödenir", str(self.client.message_batches))

    async def test_nor_with_the_offer_still_open_nor_after_it_closed(self):
        for closed in (False, True):
            await self.job()
            npc_statements.record(self.world, self.npc, "ne zaman ödersin",
                                  "Üç günlük işin ücreti her günün sonunda ödenir, peşin avans vermem.", turn=None)
            if closed:
                state = world_threads.view(self.world)
                self.thread["status"] = "expired"
                self.thread["closed_at"] = -3 * DAY
                state["history"].append(state["threads"].pop(0))
            for line in (ASK_NEXT_MORNING, ASK_AGAIN):
                reply = await self.line(line, "Hmm, bakalım.", mode="say")
                self.assertIn("bakalım", reply["narration"], (closed, line))

    async def test_a_claim_on_his_real_words_counts_as_supported(self):
        await self.job()
        npc_statements.record(self.world, self.npc, "ne zaman ödersin",
                              "Üç günlük işin ücreti her günün sonunda ödenir, peşin avans vermem.", turn=None)
        for line in (ASK_NEXT_MORNING, ASK_AGAIN):
            found = npc_statements.claim_support(self.world, self.npc, line)
            self.assertEqual(found["status"], "supported", line)

    async def test_a_claim_on_words_he_never_said_stays_unsupported(self):
        await self.job()
        found = npc_statements.claim_support(self.world, self.npc, "dedin ya bana kılıç hediye edecektin")
        self.assertNotEqual(found["status"], "supported")

    async def test_a_reply_the_safety_turned_down_does_not_become_a_denial_of_a_real_job(self):
        await self.job(status="accepted", days=1)
        self.worked_a_while()
        await self.line("paramı ver", "Al.")
        reply = await self.line("nasıl yani, kabul ediyosan başla dedin. şimdi ödeyecek misin",
                                "Parayı saydın da gittin; şimdi neyin ısrarı bu?")
        self.assertFalse(any(word in reply["narration"] for word in DENIALS), reply["narration"])

    async def test_a_job_that_never_was_gets_his_own_answer(self):
        await self.job()
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        self.world.pop("npc_speech_log", None)
        self.world.pop(npc_statements.KEY, None)
        reply = await self.line("dün iş verdin ya bana, paramı ver", "Ne parası? Seni ilk kez görüyorum.", mode="say")
        self.assertIn("Seni ilk kez görüyorum", reply["narration"])

    async def test_money_asked_of_a_stranger_gets_his_answer_in_the_default_mode(self):
        await self.job()
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        reply = await self.line("dün bana iş verdin ya, paramı ver", "Ne işi, ne parası?")
        self.assertIn("Ne işi, ne parası", reply["narration"])

    async def test_a_plain_no_in_his_own_words_stands_even_with_the_claim_quoted_in_it(self):
        await self.job()
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        reply = await self.line("dün kapıda söz verdin 20 bakır diye. ver paramı",
                                "Dün mü? Bana söz verdiğini hatırlamıyorum, beni birine benzetiyorsun.", mode="say")
        self.assertIn("birine benzetiyorsun", reply["narration"])

    async def test_a_question_about_what_he_said_is_not_a_claim_to_turn_down(self):
        await self.job()
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        reply = await self.line("ne dedin duymadım usta? iş var mı yok mu", "Duymadın mı? Şimdilik sana göre bir şey görmedim.")
        self.assertIn("sana göre bir şey görmedim", reply["narration"])

    async def test_the_last_resort_never_says_the_same_thing_twice(self):
        await self.job()
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        world = self.world
        with patch.object(game, "_session", return_value=self.session):
            first = game.historical_claim_denial(self.npc, "dün söz verdin")
            world["npc_speech_log"] = {self.npc["id"]: [{"player": "x", "npc": first.split("“")[-1].rstrip("”")}]}
            second = game.historical_claim_denial(self.npc, "dün söz verdin")
        self.assertNotEqual(first, second)


class Recognition(Table):
    """'Beni hatırlıyor musun?' asks after the meeting itself: the person's own recorded words are the memory (Task 28)."""

    RECOGNISE = "Beni hatırlıyor musun?"

    async def job(self, **kwargs):
        with fixed_town(self, 2811):
            await super().job(**kwargs)

    def never_met(self):
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        self.world.pop("npc_speech_log", None)
        self.world.pop(npc_statements.KEY, None)

    async def test_someone_who_spoke_with_you_remembers(self):
        for mode in (None, "say"):
            await self.job()
            self.never_met()  # no job to talk about: only the greeting they once said
            npc_statements.record(self.world, self.npc, "selam", "Selam yolcu, hoş geldin.", turn=None)
            found = npc_statements.claim_support(self.world, self.npc, self.RECOGNISE)
            self.assertEqual(found["status"], "supported")
            reply = await self.line(self.RECOGNISE, "Elbette, yüzünü unutmadım.", mode=mode)
            self.assertIn("yüzünü unutmadım", reply["narration"], mode)
            self.assertFalse(any(word in reply["narration"] for word in DENIALS), (mode, reply["narration"]))

    async def test_a_thing_or_someone_else_pointed_at_is_not_a_meeting_remembered(self):
        """Review I1: 'Bunu / Onu hatırlıyor musun?' asks after a thing or a third person, not the meeting."""
        for line in ("Bunu hatırlıyor musun?", "Onu hatırlıyor musun?"):
            with self.subTest(line=line):
                await self.job()
                self.never_met()  # they only ever greeted the player
                npc_statements.record(self.world, self.npc, "selam", "Hoş geldin yolcu, ekmek taze.", turn=None)
                self.assertNotEqual(npc_statements.claim_support(self.world, self.npc, line)["status"], "supported")
                reply = await self.line(line, "Evet, o yüzüğü sana ben satmıştım.", mode="say")
                self.assertNotIn("yüzüğü sana ben satmıştım", reply["narration"])

    def greeted_only(self, saying="Hoş geldin yolcu, ekmek taze."):
        self.never_met()
        npc_statements.record(self.world, self.npc, "selam", saying, turn=None)

    async def test_recognition_backs_i_remember_you_not_an_event_the_reply_adds(self):
        """Re-review R1: recognition backs 'I remember you'; an unbacked sale in the reply is cut."""
        ring = "o yüzüğü sana ben satmıştım"
        for line in ("Beni hatırlıyor musun?", "Beni hatırladın mı?", "Hatırlıyor musun?"):
            for mode in (None, "say"):
                with self.subTest(line=line, mode=mode):
                    await self.job()
                    self.greeted_only()
                    reply = await self.line(line, "Evet, o yüzüğü sana ben satmıştım.", mode=mode)
                    self.assertNotIn(ring, reply["narration"])
                    self.assertNotIn("satmıştım", reply["narration"])

    async def test_a_plain_recognition_still_stands(self):
        for answer in ("Evet, hatırlıyorum seni.", "Seni daha önce gördüm.", "Elbette, yüzünü unutmadım."):
            for mode in (None, "say"):
                with self.subTest(answer=answer, mode=mode):
                    await self.job()
                    self.greeted_only()
                    reply = await self.line("Beni hatırlıyor musun?", answer, mode=mode)
                    self.assertIn(answer.rstrip("."), reply["narration"])
                    self.assertFalse(any(word in reply["narration"] for word in DENIALS), reply["narration"])

    async def test_a_recorded_sale_may_still_be_said(self):
        await self.job()
        self.greeted_only("Bu yüzüğü sana geçen hafta otuz bakıra satmıştım.")
        reply = await self.line("Beni hatırlıyor musun?", "Evet, o yüzüğü sana ben satmıştım.", mode="say")
        self.assertIn("o yüzüğü sana ben satmıştım", reply["narration"])

    async def test_a_mixed_reply_keeps_the_recognition_and_loses_the_unbacked_event(self):
        for answer in ("Hatırlıyorum seni, sana yüzük satmıştım.", "Seni bana borç verirken gördüm."):
            with self.subTest(answer=answer):
                await self.job()
                self.greeted_only()
                reply = await self.line("Beni hatırlıyor musun?", answer, mode="say")
                self.assertNotIn("satmıştım", reply["narration"])
                self.assertNotIn("borç", reply["narration"])
                if answer.startswith("Hatırlıyorum"):
                    self.assertIn("Hatırlıyorum seni", reply["narration"])

    async def test_someone_never_met_does_not_remember(self):
        for mode in (None, "say"):
            await self.job()
            self.never_met()
            self.assertNotEqual(npc_statements.claim_support(self.world, self.npc, self.RECOGNISE)["status"], "supported")
            reply = await self.line(self.RECOGNISE, "Elbette, yüzünü unutmadım.", mode=mode)
            self.assertNotIn("yüzünü unutmadım", reply["narration"], mode)

    async def test_the_stage_direction_adds_no_unbacked_event_either(self):
        """Re-review RR2-1: the narration of their reply is cut like the speech; the invented sale is not shown."""
        for mode in (None, "say"):
            with self.subTest(mode=mode):
                await self.job()
                self.greeted_only()
                self.client.stage_direction = "Sana o yüzüğü sattığı günü hatırlayıp gülümser."
                reply = await self.line(self.RECOGNISE, "Evet, hatırlıyorum seni.", mode=mode)
                self.assertNotIn("sattığı", reply["narration"])
                self.assertNotIn("yüzüğü", reply["narration"])
                self.assertIn("hatırlıyorum seni", reply["narration"])
                self.assertFalse(any(word in reply["narration"] for word in DENIALS), reply["narration"])

    async def test_a_debt_or_payment_next_to_a_recognition_verb_does_not_stand(self):
        """Re-review RR2-2: 'something of yours' is only your face, voice, eyes or name; a payment word is not plain."""
        for answer, gone in (("Borcunu unutmadım.", "Borcunu"), ("Tabii, ödemeni unutmadım.", "ödemeni")):
            for mode in (None, "say"):
                with self.subTest(answer=answer, mode=mode):
                    await self.job()
                    self.greeted_only()
                    reply = await self.line(self.RECOGNISE, answer, mode=mode)
                    self.assertNotIn(gone, reply["narration"])


class RecognitionCut(unittest.TestCase):
    """only_what_recognition_backs alone, for someone who only ever greeted the player (re-review RR2-2)."""

    def setUp(self):
        self.world = {}
        self.npc = {"id": "npc_marek", "name": "Marek"}
        npc_statements.record(self.world, self.npc, "selam", "Hoş geldin yolcu, ekmek taze.", turn=0)

    def cut(self, reply):
        return npc_statements.only_what_recognition_backs(self.world, self.npc, "Beni hatırlıyor musun?", reply)

    def test_only_your_face_voice_eyes_or_name_sit_next_to_a_recognition_verb(self):
        for reply, gone in (("Borcunu unutmadım.", "Borcunu"), ("Tabii, ödemeni unutmadım.", "ödemeni"),
                            ("Sözünü unutmadım.", "Sözünü"), ("Kardeşini hatırlıyorum.", "Kardeşini"),
                            ("Seni ve kardeşini hatırlıyorum.", "kardeşini"), ("Görevini hatırlıyorum.", "Görevini"),
                            ("Ödeme sözünü unutmadım.", "sözünü"), ("Ödemeyi hatırlıyorum.", "Ödemeyi"),
                            ("Evet, sana verecektim.", "verecektim"), ("Seni sattığımı hatırlıyorum.", "sattığımı"),
                            ("Yüzünü ve borcunu unutmadım.", "borcunu")):
            with self.subTest(reply=reply):
                self.assertNotIn(gone, self.cut(reply))

    def test_a_plain_recognition_stands_whole(self):
        for reply in ("Elbette, yüzünü unutmadım.", "Seni daha önce gördüm.", "Evet, hatırlıyorum seni.",
                      "Sesini hatırlıyorum.", "Gözlerini unutmadım.", "Adını hatırlıyorum.", "İsmini unutmadım.",
                      "Hayır, hatırlamıyorum."):
            with self.subTest(reply=reply):
                self.assertEqual(self.cut(reply), reply)


class CheckIsNotSpeech(Table):
    """A check's result is the narrator's; when the reply cannot stand, the person answers in their own words (Task 34)."""

    async def job(self, **kwargs):
        with fixed_town(self, 2821):
            await super().job(**kwargs)

    async def test_a_turned_down_reply_after_a_check_is_not_the_check_in_their_mouth(self):
        await self.job()
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        # The reply makes up what the player did, so the safety turns it down after the Perception roll.
        said = "Marek, ses dinliyorum; sen de bir şey duyuyor musun?"
        reply = await self.line(said, "Elbette, dün buraya iş sormaya gelmiştin.", mode="say")
        self.assertEqual(self.session.last_narration_safety.get("handling"), "python_fallback", reply["narration"])
        # The safety's stand-in is the Perception check's own line ("İncelemen sonuç vermedi; ..."): it stays as the
        # narrator's line, outside any quote, and the person's own fallback follows it (review M3).
        at = reply["narration"].find(" " + living_world.public_npc_name(self.npc))
        self.assertGreater(at, 0, reply["narration"])
        check, person = reply["narration"][:at], reply["narration"][at + 1:]
        self.assertTrue(check.startswith("İncelemen"), reply["narration"])
        self.assertNotIn("“", check)
        self.assertNotIn("İncelemen", person)
        self.assertNotIn("gelmiştin", reply["narration"])
        with patch.object(game, "_session", return_value=self.session):
            own = game._person_fallback(self.world, self.npc, said)  # only the person's own fallback speaks for them
        self.assertIn(own, person)
        self.assertTrue(person.endswith("”") and "“" in person, person)  # the person's part is their quoted speech

    async def test_a_stock_check_line_swapped_for_their_words_is_not_said_twice(self):
        """Re-review R2: a generic check line is swapped by the stock rule; their fallback is shown once."""
        await self.job()
        world_threads.view(self.world)["threads"].clear()
        self.npc.pop("place_role_of")
        plain = "Yirmi beş bakır, üç gün; söz söz."  # a fallback that does not start with their name
        with patch.object(game, "_job_fallback", return_value=plain):
            reply = await self.line("Marek, seni ikna etmeye çalışıyorum, bana biraz yardım et",
                                    "Elbette, dün buraya iş sormaya gelmiştin.", mode="say")
        self.assertEqual(reply["narration"].count(plain), 1, reply["narration"])
        self.assertNotIn("gelmiştin", reply["narration"])


if __name__ == "__main__":
    unittest.main()

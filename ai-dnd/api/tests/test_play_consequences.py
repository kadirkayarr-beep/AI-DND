"""The 106-turn play: what the player did must stay done, and clear lines must get a real result.

Lines are the player's own loose Turkish. Real app, real engine; only the model is scripted.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import living_world
import relationships
import world_threads
from adventure import dialogue_jobs
from api.tests import test_experimental_npc_dialogue as speech
from api.tests import test_thread_gate as gate_tests
from api.tests.test_three_plays import FIGHTER, PlayClient, ThreePlaysTests


class OnTheJob(unittest.IsolatedAsyncioTestCase):
    """The job fixture without the job tests that come with it."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    open_job = gate_tests.ThreadTable.open_job
    line = gate_tests.ThreadTable.line
    status = gate_tests.ThreadTable.status
    offer = gate_tests.ThreadTable.offer


class Rope(ThreePlaysTests):
    async def worker(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        return self.add_person("Vesulir", "Liman işçisi", current_hp=12, max_hp=12, armor_class=10, inventory=[])

    async def test_cutting_a_crates_rope_is_no_blow_at_the_man_beside_it(self):
        npc = await self.worker()
        await self.say("işçi arkasını dönünce bağladığı sandığın ipini kesip içine bakıyorum", PlayClient(intent="attack"))
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(npc["current_hp"], 12)

    async def test_cutting_the_man_is_still_a_blow(self):
        npc = await self.worker()
        npc.update(current_hp=500, max_hp=500)  # one blow must not end the fight it starts
        await self.say("işçiyi kılıçla kesiyorum", PlayClient(intent="attack"))
        self.assertTrue(self.world["combat"]["active"])
        self.assertTrue(npc["id"] in self.world["combat"]["participants"])


class StandingDown(ThreePlaysTests):
    async def in_a_fight(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.session.character.update(current_hp=300, max_hp=300)
        self.npc = self.add_person("Vesulir", "Liman işçisi", current_hp=500, max_hp=500, armor_class=1, inventory=[])
        await self.say("işçiye yumrukla saldırıyorum", PlayClient(intent="attack"))
        self.assertTrue(self.world["combat"]["active"])

    def rolled(self, result):
        check = self.session.perform_skill_check
        return patch.object(self.session, "perform_skill_check",
                            lambda *args, **kwargs: {**check(*args, **kwargs), "result": result})

    async def test_an_apology_can_end_a_fight_with_someone_who_meant_no_harm(self):
        await self.in_a_fight()
        with self.rolled("BAŞARILI"):
            out = await self.say("dur dur ya ne vuruyom! kılıcı indiriyorum, tamam abi kusura bakma", PlayClient())
        self.assertFalse(self.world["combat"]["active"], out["narration"])
        self.assertEqual(out["turn_outcome"]["action"], "stand_down")
        self.assertLess(relationships.score(self.world, self.npc["id"]), 0)

    async def test_it_can_fail_and_then_the_fight_goes_on(self):
        await self.in_a_fight()
        with self.rolled("BAŞARISIZ"):
            out = await self.say("saldırmıyorum teslim ol diyorum ona, bırak halatı, kavga bitsin", PlayClient())
        self.assertTrue(self.world["combat"]["active"], out["narration"])
        self.assertEqual(out["turn_outcome"]["action"], "action_economy")

    async def test_a_blow_said_with_kind_words_is_still_a_blow(self):
        await self.in_a_fight()
        out = await self.say("kusura bakma ama öldürmicem bunu, kılıcın yan yüzüyle vurup bayıltıyorum",
                             PlayClient(intent="attack"))
        self.assertNotEqual(out["turn_outcome"]["action"], "stand_down")

    async def test_a_real_enemy_does_not_stop_for_an_apology(self):
        await self.in_a_fight()
        self.npc["hostile"] = True
        out = await self.say("kusura bakma kavga etmek istemiyorum", PlayClient())
        self.assertNotEqual(out["turn_outcome"]["action"], "stand_down")
        self.assertTrue(self.world["combat"]["active"])


class TheOneKnockedOut(ThreePlaysTests):
    async def out_cold(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.session.character.update(current_hp=300, max_hp=300)
        self.npc = self.add_person("Vesulir", "Liman işçisi", current_hp=500, max_hp=500, armor_class=1, inventory=[])
        await self.say("işçiye yumrukla saldırıyorum", PlayClient(intent="attack"))
        self.npc["current_hp"] = 1
        for record in self.world["combat"]["participant_records"]:
            if record["id"] == self.npc["id"]:
                record["current_hp"] = 1
        for _ in range(12):
            await self.say("yumrukla bayıltıyorum", PlayClient(intent="attack"))
            if self.npc["combat_status"] != "active":
                break
        self.assertEqual(self.npc["combat_status"], "unconscious")
        self.world["flags"].update(active_npc_id=self.npc["id"], last_npc_id=self.npc["id"], active_npc_until_turn=999)

    async def test_he_does_not_answer_while_he_lies_there(self):
        await self.out_cold()
        for line in ("adam baygın, nasıl konuşuyo? sallıyorum uyanıyo mu", "az önce kafana vurup bayılttım seni, hatırlamıyon mu?"):
            out = await self.say(line, PlayClient(narration="Kafama falan vurduğun yok."))
            self.assertNotIn("vurduğun yok", out["narration"], line)
            self.assertIn("baygın", out["narration"], line)

    async def test_when_he_wakes_he_remembers_who_put_him_down(self):
        await self.out_cold()
        await self.say("iki saat bekliyorum", PlayClient())
        await self.say("etrafa bakıyorum", PlayClient())
        self.assertEqual(self.npc["combat_status"], "active")
        import bold_acts
        note = bold_acts.speech_note(self.world, self.npc)
        self.assertIn("seni bayılttı", note)
        self.assertIn("inkâr etme", note)

    async def test_he_likes_the_player_less_for_it(self):
        await self.out_cold()
        self.assertLess(relationships.score(self.world, self.npc["id"]), 0)


class Work(OnTheJob):
    async def accepted(self):
        await self.open_job()
        self.offer()
        world_threads.accept_hired(self.world, self.thread)
        self.world["flags"]["turn_index"] += 3
        self.thread["accepted_at"] = -7200
        self.thread["starts_at"] = 0
        self.thread.pop("night_only", None)

    async def test_ordinary_ways_of_starting_the_work_start_it(self):
        for line in ("sabah oldu, hadi başlayalım. arabaya gidelim",
                     "tamam tamam, senin dediğin işini yapayım o zaman, işe başlıyorum",
                     "hadi başlayalım",
                     "tamam işe koyuluyorum"):
            await self.accepted()
            out = await self.line(line, "Hmm.")
            self.assertEqual(out["turn_outcome"]["action"], "work", line)

    async def test_saying_the_work_is_not_being_done_starts_nothing(self):
        await self.accepted()
        out = await self.line("işe başlamıyorum, canım istemiyor", "Sen bilirsin.")
        self.assertNotEqual(out["turn_outcome"]["action"], "work")


class Sealed(OnTheJob):
    async def carrying(self, *, template="sealed_letter", noun="mektup", pay=12):
        await self.open_job(kind="errand")
        self.client.narration = "Tamam."
        self.world["locations"]["place_x"] = {"id": "place_x", "name": "Kuzey Karakolu", "type": "building",
                                              "scene_kind": "building", "place_kind": "barracks",
                                              "parent_location_id": self.city, "exit_location_id": self.city,
                                              "hidden": False, "aliases": []}
        self.other = {"id": "npc_alici", "name": "Halvar", "role": "Muhafız", "location": "place_x", "status": "active",
                      "combat_status": "active", "current_hp": 8, "max_hp": 8, "memory": [], "knowledge": [],
                      "reality_layer": "PROCEDURAL_LOCAL_FICTION", "personal_profile": {}, "inventory": []}
        self.world["npcs"].append(self.other)
        self.thread.update(template_id=template, item_noun=noun, target_place_id="place_x",
                           recipient_name="Halvar", owner_name=self.npc["name"], recipient_npc_id=self.other["id"],
                           owner_line="Mektup alıcıya gidecek. Mührü açılmamış olmalı. Ücret 12 bakır." if template == "sealed_letter"
                           else "Not alıcıya gidecek. Ücret 12 bakır.",
                           terms={"pay": pay, "pay_basis": "total", "pay_timing": "on_delivery",
                                  "deadline_text": "bir gün içinde"})
        self.thread["owner_npc_id"] = self.npc["id"]
        self.offer()
        with patch("world_threads.recipient_of", return_value=self.other):
            self.assertTrue(dialogue_jobs.accept_thread_job(self.session, self.thread, self.npc))
        dialogue_jobs.hand_over(self.session, self.thread, self.npc)
        self.assertTrue(dialogue_jobs.holds_parcel(self.world, self.thread))

    async def test_a_letter_has_words_in_it(self):
        await self.carrying()
        out = await self.line("kimse bakmıyosa mührü kırıp mektubu okuyorum")
        self.assertIn("yazıyor", out["narration"])
        self.assertIn("“", out["narration"])
        self.assertIs(self.thread.get("seal_broken"), True)

    async def test_the_same_letter_says_the_same_thing_twice_and_the_seal_breaks_once(self):
        await self.carrying()
        first = (await self.line("mektubu açıp okuyorum"))["narration"]
        again = (await self.line("ee ne yazıyo mektupta, okuyorum işte"))["narration"]
        self.assertEqual(first.split("“")[1], again.split("“")[1])
        self.assertNotIn("kırıyorsun", again)

    async def test_a_note_can_be_read_too(self):
        await self.carrying(template="meeting_note", noun="not")
        out = await self.line("notu açıp okuyorum, ne yazıyo")
        self.assertIn("“", out["narration"])

    async def test_asking_someone_else_about_a_letter_reads_nothing(self):
        await self.carrying()
        await self.line("mektubu kimden aldın sen?")
        self.assertIsNone(self.thread.get("seal_broken"))

    async def test_a_broken_seal_costs_money_at_the_door(self):
        await self.carrying()
        await self.line("mührü kırıp mektubu okuyorum")
        money = self.world.get("currency", {}).get("player", 0)
        self.world["location"] = "place_x"
        self.world["flags"].update(active_npc_id=self.other["id"], last_npc_id=self.other["id"], active_npc_until_turn=999)
        out = await self.line("al sana mektup var, teslim ediyorum")
        paid = self.world.get("currency", {}).get("player", 0) - money
        self.assertEqual(paid, 6, out["narration"])
        self.assertIn("mührü", out["narration"].casefold())
        self.assertLess(relationships.score(self.world, self.other["id"]), 0)

    async def test_an_unopened_letter_pays_in_full(self):
        await self.carrying()
        money = self.world.get("currency", {}).get("player", 0)
        self.world["location"] = "place_x"
        self.world["flags"].update(active_npc_id=self.other["id"], last_npc_id=self.other["id"], active_npc_until_turn=999)
        await self.line("al sana mektup var, teslim ediyorum")
        self.assertEqual(self.world.get("currency", {}).get("player", 0) - money, 12)


class Pocket(ThreePlaysTests):
    async def shown(self, words):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.session.messages.append({"role": "assistant", "content": words})

    def names(self):
        return [item.get("name") if isinstance(item, dict) else item for item in self.world["inventory"]]

    async def test_what_was_just_shown_goes_into_the_bag(self):
        await self.shown("Kapağı kaldırıyorsun; içinde birkaç demir parça ve kalın bezler görünüyor.")
        out = await self.say("demir parçalardan iyilerini alıp çantaya atıyorum", PlayClient())
        self.assertIn("Demir parça", self.names())
        self.assertIn("emir parça", out["narration"])

    async def test_looking_in_the_bag_or_the_purse_shows_what_is_there(self):
        for line in ("çantama bakıyorum", "keseme bakıyorum, ne kadar param var"):
            await self.shown("Rıhtımda kalın halatlar yatıyor.")
            out = await self.say(line, PlayClient())
            self.assertEqual(out["turn_outcome"]["action"], "inventory", line)
            self.assertIn("Envanterinde", out["narration"], line)

    async def test_money_cannot_be_taken_out_of_a_description(self):
        await self.shown("Masanın üstünde bir kese altın duruyor.")
        before = self.names()
        await self.say("altınları alıp cebime atıyorum", PlayClient())
        self.assertEqual(self.names(), before)

    async def test_something_nobody_mentioned_is_not_there_to_take(self):
        await self.shown("Rıhtımda kalın halatlar yatıyor.")
        before = self.names()
        out = await self.say("kılıcı alıp çantama atıyorum", PlayClient())
        self.assertEqual(self.names(), before, out["narration"])

    async def test_a_thrown_thing_is_gone_from_the_bag(self):
        await self.shown("Rıhtımda dalgalar kayalara vuruyor.")
        self.world["inventory"].append({"item_id": "item_note_1", "name": "Pusula", "quantity": 1})
        await self.say("pusulayı buruşturup denize atıyorum", PlayClient(narration="Dalgalar onu alıp götürüyor."))
        self.assertNotIn("Pusula", self.names())

    async def test_a_thrown_parcel_cannot_be_handed_in_later(self):
        await self.shown("Rıhtımda dalgalar kayalara vuruyor.")
        self.world["inventory"].append({"item_id": "parcel:job:abc", "name": "Mektup", "quantity": 1})
        await self.say("mektubu denize atıyorum", PlayClient(narration="Kâğıt suya düşüyor."))
        self.assertNotIn("Mektup", self.names())

    async def test_the_sword_in_hand_is_not_thrown_by_a_line_about_something_else(self):
        await self.shown("Rıhtımda dalgalar kayalara vuruyor.")
        before = self.names()
        await self.say("taş alıp denize atıyorum", PlayClient(narration="Taş suya gömülüyor."))
        self.assertEqual(self.names(), before)


class OpeningACrate(ThreePlaysTests):
    async def test_a_crate_is_not_a_door(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        out = await self.say("sandığı açıyorum içine bakıcam", PlayClient())
        self.assertNotIn("kapı", out["narration"].casefold())


class Biri(OnTheJob):
    def expired_person(self, *aliases):
        state = living_world.ensure_scene_state(self.world)
        scene = state["scenes"].setdefault(self.world["location"], {"referents": []})
        scene.setdefault("referents", []).append(
            {"id": "ref_gone", "description": "biri", "lifecycle": "expired", "aliases": list(aliases),
             "expires_after_turn": 0})

    async def test_asking_the_one_before_you_about_someone_reaches_them(self):
        for line in ("rahip, biri geldi mi mektup için? kapıya dayanan oldu mu",
                     "kim gelecek kapıya, adını söyle. korktuğun kim"):
            await self.open_job()
            self.expired_person("biri", "kim")
            out = await self.line(line, "Kimse gelmedi henüz.")
            self.assertNotIn("ortalıkta yok", out["narration"], line)
            self.assertIn("Kimse gelmedi", out["narration"], line)

    async def test_someone_really_gone_is_still_gone_when_nobody_is_being_talked_to(self):
        await self.open_job()
        self.expired_person("kırmızı pelerinli adam", "biri")
        turn = self.world["flags"].get("turn_index", 0)
        found = living_world.resolve_scene_referent(self.world, "kırmızı pelerinli adam nereye gitti", turn)
        self.assertEqual(found["status"], "expired")
        self.assertEqual(living_world.resolve_scene_referent(self.world, "biri geldi mi", turn)["status"], "missing")


class Unrecognised(OnTheJob):
    async def test_a_reply_that_had_to_go_never_turns_into_asking_the_player_to_repeat(self):
        await self.open_job()
        out = await self.line("sandıktaki demirler nerde, kim açtı sandığı biliyo musun", "Bu altın senin, eline veriyorum.",
                              mode="say", target=True)
        for canned in ("kavrayamadım", "kestiremedim", "Tam anlayamadım", "biraz daha yavaş"):
            self.assertNotIn(canned, out["narration"])
        self.assertTrue(out["narration"].strip())

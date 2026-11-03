"""Roadmap step 5, second part: the front reading comes before the planner and the old word-list owners.

Real app, real adapter, real engine; only the Ollama client is scripted. The lines are the owner's own, as typed.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import equipment_economy
import fallen
import front_proposal
import grounded_action
from api.tests.test_front_proposal import FrontClient, FrontTable


class ReadsBeforeThePlanner(FrontTable):
    async def test_a_place_named_in_a_question_to_someone_does_not_walk_the_player(self):
        await self.begin()
        where = self.world["location"]
        place = self.world["locations"][self.a_place()]["name"]
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line(f"usta yirtik sayfalari soruyorum yine. biri bi kayit ariyormus, {place} tarafinda "
                                "son gorulmus. senin defterden mi gitti o sayfalar")
        self.assertEqual(self.world["location"], where)
        self.assertIn(self.client.narration, reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")

    async def test_a_threat_with_otur_in_it_is_said_not_sat(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("efendinle gorusmeden bunu vermiyorum. geceleri zifiri karanlikta otur istersen")
        self.assertIn(self.client.narration, reply["narration"])
        self.assertEqual(self.routes()[-1]["owner"], "dialogue")

    async def test_a_threat_read_as_an_attempt_is_not_sat_either(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        await self.line("efendinle gorusmeden bunu vermiyorum. geceleri zifiri karanlikta otur istersen")
        self.assertNotEqual(self.routes()[-1]["owner"], "sit")

    async def test_sitting_down_read_as_sitting_is_sat(self):
        await self.begin()
        self.client.front = {"kind": "sit"}
        await self.line("yorgunum, su banka oturuyorum")
        self.assertEqual(self.routes()[-1]["owner"], "sit")

    async def test_a_line_that_also_wants_a_proposal_is_read_once_and_the_reply_carries_it(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        await self.line("sana söz veriyorum, paketi yarın getiririm")
        self.assertEqual(len(self.front_calls()), 1)
        self.assertIn("interaction", self.front_calls()[0]["properties"])
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")
        self.assertLessEqual(self.client.chat_calls, 2)

    async def test_the_cap_counts_a_reading_taken_before_the_planner(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("usta bu kasabada kim kimle tanisir, sor bakalim sana sorayim")
        self.assertTrue(reply["narration"].strip())
        self.assertEqual(self.client.chat_calls, len(self.client.schemas))
        self.assertLessEqual(self.client.chat_calls, 2)


class ProposalClient(FrontClient):
    """The reading's reply also carries the interaction half, as the real schema asks."""

    interaction = None

    def chat(self, *args, **kwargs):
        reply = super().chat(*args, **kwargs)
        if self.interaction and "front" in ((kwargs.get("format") or {}).get("properties") or {}):
            packet = json.loads(reply["message"]["content"])
            packet["interaction"] = self.interaction
            reply = {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return reply


class TheReadingCarriesTheProposal(FrontTable):
    async def set_up(self):
        await self.begin()
        self.client = ProposalClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        for key in ("active_npc_id", "last_npc_id"):
            self.world["flags"].pop(key, None)
        self.name = self.npc["name"]
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}

    def proposal(self, operation, line, addressee):
        self.client.interaction = {
            "operation": operation, "quote": line, "privacy": "addressed",
            "conversation": {"addressee_id": addressee, "subject_phrase": "", "subject_role": "unknown",
                             "meaning": "unknown", "topic_relation": "new", "candidate_evidence_ids": []}}

    async def test_the_person_the_line_names_is_who_the_reading_is_built_for(self):
        await self.set_up()
        await self.line(f"{self.name}, sembol hakkinda ne biliyorsun")
        schema = self.front_calls()[0]
        self.assertIn(self.npc["id"], json.dumps(schema["$defs"]["ConversationProposal"]["properties"]["addressee_id"]))

    async def test_an_information_line_makes_the_reading_ask_for_the_conversation(self):
        await self.set_up()
        await self.line(f"{self.name}, sembol hakkinda ne biliyorsun")
        self.assertIn("conversation önerisini tüketecek", str(self.client.message_batches[0]))

    async def test_a_promise_to_the_named_person_is_recorded(self):
        await self.set_up()
        line = f"{self.name}, sana soz veriyorum, paketi yarin getiririm"
        self.proposal("promise", line, self.npc["id"])
        reply = await self.line(line)
        self.assertEqual(reply["turn_outcome"]["status"], "recorded")
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")

    async def test_a_reading_that_left_the_addressee_out_lets_the_person_answer(self):
        await self.set_up()
        line = f"{self.name}, sana soz veriyorum, paketi yarin getiririm"
        self.proposal("promise", line, None)
        reply = await self.line(line, "Görürüz bakalım.")
        self.assertIn("Görürüz bakalım", reply["narration"])
        self.assertNotEqual(reply["turn_outcome"]["status"], "recorded")


class ReadsBeforeTheOldOwners(FrontTable):
    async def test_lighting_a_lantern_is_no_arson(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        await self.line("kandil malzemesini acip sonuk fenere yag koyup yakiyorum")
        self.assertNotEqual(self.routes()[-1]["owner"], "arson")
        self.assertFalse(self.world["flags"].get("fires"))

    async def test_a_fire_the_model_read_is_still_a_fire(self):
        await self.begin()
        self.client.front = {"kind": "attempt", "deed": "burn"}
        await self.line("su dukkani bastan asagi tutusturuyorum")
        self.assertEqual(self.routes()[-1]["owner"], "arson")

    async def test_a_glance_at_a_purse_is_no_theft(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("adamin kesesine bi goz atiyorum, dolu mu diye")
        self.assertNotEqual(self.routes()[-1]["owner"], "theft")

    async def test_a_theft_the_word_list_never_heard_is_still_a_theft(self):
        await self.begin()
        self.client.front = {"kind": "attempt", "deed": "steal"}
        await self.line("kalabaligi firsat bilip adamin belindekini usulca kendime katiyorum")
        self.assertEqual(self.routes()[-1]["owner"], "theft")

    async def test_asking_about_a_theft_is_no_theft_whatever_the_reading_says(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "deed": "steal"}
        for line in ("su keseyi calsam fark eder mi?", "su keseyi calsam fark eder mi"):
            await self.line(line)
            self.assertNotEqual(self.routes()[-1]["owner"], "theft", line)
        self.assertFalse(self.world["flags"].get("deeds"))

    async def test_asking_about_a_fire_is_no_fire_whatever_the_reading_says(self):
        await self.begin()
        self.client.front = {"kind": "attempt", "deed": "burn"}
        for line in ("burayi yaksam ne olur?", "burayi yaksam ne olur"):
            await self.line(line)
            self.assertNotEqual(self.routes()[-1]["owner"], "arson", line)
        self.assertFalse(self.world["flags"].get("fires"))

    async def test_ringing_a_bell_is_no_theft_whatever_the_reading_says(self):
        await self.begin()
        self.client.front = {"kind": "attempt", "deed": "steal"}
        await self.line("zili caliyorum")
        self.assertNotEqual(self.routes()[-1]["owner"], "theft")

    async def test_with_no_reading_the_old_words_still_catch_a_fire(self):
        await self.begin()
        self.client.drop_front = True
        await self.line("dukkani atese veriyorum")
        self.assertEqual(self.routes()[-1]["owner"], "arson")

    async def test_what_is_in_my_bag_goes_by_the_reading_however_it_is_said(self):
        await self.begin()
        self.client.front = {"kind": "bag"}
        reply = await self.line("çantama koydum mu duyuruyu bi bakayim")
        self.assertIn("Envanterinde", reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:bag")
        self.assertLessEqual(self.client.chat_calls, 1)

    async def test_the_classifier_half_of_the_reply_can_name_the_bag_too(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        self.client.intent = "inventory"
        reply = await self.line("çantama koydum mu duyuruyu bi bakayim")
        self.assertIn("Envanterinde", reply["narration"])
        self.assertEqual(self.routes()[-1]["route"], "front:bag")

    async def test_dropping_the_sword_labelled_inventory_really_drops_it(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        self.client.intent = "inventory"
        reply = await self.line("kilici yere birakiyorum")
        self.assertNotIn("Envanterinde", reply["narration"])
        self.assertNotIn("Kılıç", equipment_economy.labels(self.world["inventory"]))

    async def test_putting_a_thing_away_labelled_inventory_really_puts_it_away(self):
        await self.begin()
        self.session.messages.append({"role": "assistant", "content": "Yolun kenarında yuvarlak bir çakıl duruyor."})
        self.world.setdefault("ground_items_by_location", {}).setdefault(self.world["location"], []).append(
            {"item_id": "item_cakil", "name": "Çakıl"})  # A5 (C9): the pebble really lies here
        self.client.front = {"kind": "attempt"}
        self.client.intent = "inventory"
        reply = await self.line("bu cakili cantama koyuyorum")
        self.assertNotIn("Envanterinde", reply["narration"])
        self.assertTrue([name for name in equipment_economy.labels(self.world["inventory"]) if "akıl" in name.casefold()])

    async def test_tossing_a_thing_labelled_inventory_really_tosses_it(self):
        await self.begin()
        equipment_economy.grant_plain(self.world, "Kâğıt")
        self.client.front = {"kind": "attempt"}
        self.client.intent = "inventory"
        reply = await self.line("kagidi yirtip atiyorum")
        self.assertNotIn("Envanterinde", reply["narration"])
        self.assertNotIn("Kâğıt", equipment_economy.labels(self.world["inventory"]))

    async def test_what_is_in_the_purse_goes_the_same_way(self):
        await self.begin()
        self.client.front = {"kind": "bag"}
        self.world.setdefault("currency", {})["player"] = 2412
        reply = await self.line("kese ne alemde, kac bakirim var")
        self.assertIn("24 altın 12 bakır", reply["narration"])


class SomeoneLiesOutCold(FrontTable):
    async def lay_out(self):
        await self.begin()
        for npc in self.world["npcs"]:
            if npc["id"] != self.npc["id"]:
                npc["location"] = "elsewhere"
            else:
                fallen.knock_out(self.session, npc)

    async def test_a_look_around_runs(self):
        await self.lay_out()
        self.client.front = {"kind": "look"}
        reply = await self.line("etrafa bakiyorum, gelen var mi, hizmetkarlar nobetciler ne yapiyor")
        self.assertNotIn("sesini duyacak durumda", reply["narration"])

    async def test_reading_what_was_taken_runs(self):
        await self.lay_out()
        self.client.front = {"kind": "attempt"}
        reply = await self.line("defterin son sayfalarinda ne yaziyor, kayit, muhur, okuyorum")
        self.assertNotIn("sesini duyacak durumda", reply["narration"])

    async def test_a_walk_runs(self):
        await self.lay_out()
        place = self.a_place()
        self.client.front = {"kind": "go_to", "place_id": place}
        name = self.world["locations"][place]["name"]
        reply = await self.line("su tarafa dogru yuruyorum, buradan cikalim")
        self.assertIn(name, reply["narration"], self.routes()[-1])

    async def test_only_words_said_to_them_meet_the_silence(self):
        await self.lay_out()
        self.client.front = {"kind": "speak_to"}
        reply = await self.line("hey, uyan lan, duyuyor musun")
        self.assertIn("sesini duyacak durumda", reply["narration"])


class TalkWithNobodyNamed(FrontTable):
    async def test_a_line_read_as_talk_with_nobody_named_walks_nowhere(self):
        await self.begin()
        for npc in self.world["npcs"]:
            npc["location"] = "elsewhere"
        where = self.world["location"]
        name = self.world["locations"][self.a_place()]["name"]
        self.client.front = {"kind": "speak_to"}
        reply = await self.line(f"usta yirtik sayfalari soruyorum, {name} tarafinda son gorulmus, senin defterden mi gitti")
        self.assertEqual(self.world["location"], where)
        self.assertEqual(self.routes()[-1]["route"], "front:talk_around")
        self.assertTrue(reply["narration"].strip())

    async def test_the_classifier_half_of_the_same_reply_cannot_walk_it_either(self):
        await self.begin()
        for npc in self.world["npcs"]:
            npc["location"] = "elsewhere"
        where = self.world["location"]
        name = self.world["locations"][self.a_place()]["name"]
        self.client.front = {"kind": "speak_to"}
        self.client.intent = "travel"
        self.client.target = {"type": "location", "reference": name}
        await self.line(f"usta yirtik sayfalari soruyorum, {name} tarafinda son gorulmus, senin defterden mi gitti")
        self.assertEqual(self.world["location"], where)


    async def test_a_known_place_and_a_walk_word_in_talk_do_not_turn_the_intent_into_a_walk(self):
        await self.begin()
        for npc in self.world["npcs"]:
            npc["location"] = "elsewhere"
        where = self.world["location"]
        name = self.world["locations"][self.a_place()]["name"]
        self.client.front = {"kind": "speak_to"}
        await self.line(f"{name} nerede usta, oraya nasil gidilir, senin defterden mi gitti o sayfalar")
        self.assertEqual(self.world["location"], where)

    async def test_the_old_walk_to_a_named_place_stays_out_of_it(self):
        await self.begin()
        for npc in self.world["npcs"]:
            npc["location"] = "elsewhere"
        self.client.front = {"kind": "speak_to"}
        name = self.world["locations"][self.a_place()]["name"]
        with patch("game._adventure_scene_turn") as old_walk, patch("timed_gameplay.start_travel") as old_journey:
            await self.line(f"usta biri bi kayit ariyormus, {name} tarafinda son gorulmus, senin defterden mi gitti")
        old_walk.assert_not_called()
        old_journey.assert_not_called()


class TheOldOwnersThatLostTheirTraffic(FrontTable):
    async def test_a_look_that_names_a_place_stays_a_look(self):
        await self.begin()
        where = self.world["location"]
        name = self.world["locations"][self.a_place()]["name"]
        self.client.front = {"kind": "look"}
        with patch("game._adventure_scene_turn") as old_walk, patch("game._local_place_turn") as old_place:
            await self.line(f"etrafa bakiyorum, {name} tarafinda ne var")
        old_walk.assert_not_called()
        old_place.assert_not_called()
        self.assertEqual(self.world["location"], where)

    async def test_reading_what_is_in_hand_is_not_answered_with_an_empty_bag(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        reply = await self.line("defteri okuyorum")
        self.assertNotIn("okuyabileceğin bir kitap yok", reply["narration"])

    async def test_with_no_reading_the_old_owners_still_answer(self):
        await self.begin()
        self.client.drop_front = True
        reply = await self.line("defteri okuyorum")
        self.assertIn("okuyabileceğin bir kitap yok", reply["narration"])

    async def test_a_reading_decides_who_hears_a_line_that_ends_in_dedim(self):
        await self.begin()
        self.client.front = {"kind": "attempt"}
        await self.line("masaya yumruk vurup sus artik dedim")
        self.assertNotEqual(self.routes()[-1]["owner"], "dialogue")


class SomeoneTheNarrationDescribed(FrontTable):
    def narrated(self, text):
        self.session.messages.append({"role": "assistant", "content": text})

    async def test_asking_a_guard_the_narration_described_reaches_a_real_guard(self):
        await self.begin()
        self.narrated("Kapının yanında uyuklayan bir nöbetçi mızrağına yaslanmış duruyor.")
        self.client.front = {"kind": "speak_to", "person_word": "nöbetçi"}
        reply = await self.line("off tamam. nobetciye gidiyorum, kapidakine soruyorum dun gece bi sey oldu mu diye")
        guard = next((npc for npc in self.world["npcs"] if "nöbetçi" in str(npc.get("role")).casefold()), None)
        self.assertIsNotNone(guard)
        self.assertEqual(guard["location"], self.world["location"])
        self.assertIn(self.client.narration, reply["narration"])
        self.assertEqual(self.world["flags"]["active_npc_id"], guard["id"])

    async def test_the_same_guard_is_not_made_twice(self):
        await self.begin()
        self.narrated("Kapının yanında uyuklayan bir nöbetçi mızrağına yaslanmış duruyor.")
        self.client.front = {"kind": "speak_to", "person_word": "nöbetçi"}
        await self.line("nobetciye soruyorum dun gece bi sey oldu mu")
        count = len(self.world["npcs"])
        self.narrated("Kapının yanında uyuklayan bir nöbetçi mızrağına yaslanmış duruyor.")
        await self.line("nobetci sen bi sey gordun mu")
        self.assertEqual(len(self.world["npcs"]), count)

    async def test_the_listed_person_the_model_named_stays_the_one_who_answers(self):
        await self.begin()
        count = len(self.world["npcs"])
        self.narrated("Kapının yanında uyuklayan bir nöbetçi mızrağına yaslanmış duruyor.")
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "person_word": "nöbetçi"}
        await self.line("nobetci ne zamandir orada")
        self.assertEqual(len(self.world["npcs"]), count)
        self.assertEqual(self.world["flags"]["active_npc_id"], self.npc["id"])

    async def test_a_person_the_screen_showed_is_reached_by_any_word_for_them(self):
        await self.begin()
        count = len(self.world["npcs"])
        self.narrated("Kapının yanında uyuklayan bir nöbetçi mızrağına yaslanmış duruyor.")
        self.client.front = {"kind": "speak_to", "person_word": "nöbetçi"}
        await self.line("oradaki adama soruyorum dun gece ne oldu")
        self.assertEqual(len(self.world["npcs"]), count + 1)

    async def test_a_thing_of_the_scene_is_nobody(self):
        await self.begin()
        count = len(self.world["npcs"])
        self.session.create_local_feature({"location": self.world["location"], "name": "Eski kuyu",
                                           "description": "Taşları yosun tutmuş bir kuyu.", "aliases": ["kuyu"]})
        self.narrated("Eski kuyu avlunun ortasında duruyor.")
        self.client.front = {"kind": "speak_to", "person_word": "kuyu"}
        await self.line("kuyuya sesleniyorum, kim var orda")
        self.assertEqual(len(self.world["npcs"]), count)

    async def test_the_players_own_question_describes_nobody(self):
        await self.begin()
        count = len(self.world["npcs"])
        self.narrated("Sen: “burada nobetci var mi”\n\nBarmen bardağı siliyor. “Nöbetçi mi? Bilmem.”")
        self.client.front = {"kind": "speak_to", "person_word": "nöbetçi"}
        await self.line("nobetciye sesleniyorum")
        self.assertEqual(len(self.world["npcs"]), count)

    async def test_a_narration_that_denies_someone_describes_nobody(self):
        await self.begin()
        count = len(self.world["npcs"])
        self.narrated("Kapıda nöbetçi yok.")
        self.client.front = {"kind": "speak_to", "person_word": "nöbetçi"}
        await self.line("nobetciye sesleniyorum")
        self.assertEqual(len(self.world["npcs"]), count)

    async def test_a_guard_nobody_described_is_not_conjured(self):
        await self.begin()
        count = len(self.world["npcs"])
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "person_word": "nöbetçi"}
        await self.line("nobetciye soruyorum dun gece bi sey oldu mu diye")
        self.assertEqual(len(self.world["npcs"]), count)
        self.assertEqual(self.routes()[-1]["route"], "front:speak_to")


class WhatAClarificationNames(FrontTable):
    def place(self, label, known=False):
        record = {"id": f"place_{label}", "name": label, "visited": known}
        self.world["locations"][record["id"]] = record
        return {"kind": "place", "id": record["id"], "label": label, "record": record}

    async def test_a_place_the_player_never_saw_or_heard_is_not_named(self):
        await self.begin()
        known, unknown = self.place("Tuz Kapısı", True), self.place("Gizli Mezarlık")
        self.assertEqual(grounded_action.worth_naming(self.session, "donuyorum", [unknown, known]), [known])

    async def test_a_place_the_narration_named_is_known(self):
        await self.begin()
        heard = self.place("Tuz Kapısı")
        self.session.messages.append({"role": "assistant", "content": "Tuz Kapısı tarafından bir araba geçiyor."})
        self.assertEqual(grounded_action.worth_naming(self.session, "donuyorum", [heard]), [heard])

    async def test_the_place_the_line_names_comes_first_even_unseen(self):
        await self.begin()
        known, inn = self.place("Tuz Kapısı", True), self.place("Ay Sofrası Hanı")
        options = grounded_action.worth_naming(self.session, "ay sofrasi hanina donuyorum", [known, inn])
        self.assertEqual(options, [inn, known])


class APassedCheckFindsSomething(FrontTable):
    FOUND = "Çamurda sağ ayağını sürüyen birinin izi var."

    def roll(self, line, outcome="success", word="izler"):
        self.session._front_found = (self.FOUND, word)
        return self.session._inspection_findings(line, outcome)

    def saved(self):
        return [row for row in self.world["features"] if row.get("description") == self.FOUND]

    async def test_a_pass_on_tracks_says_what_the_reading_proposed_and_keeps_it(self):
        await self.begin()
        found = self.roll("yerdeki izleri yakindan inceliyorum, ayak izi var mi")
        self.assertEqual(found["text"], self.FOUND)
        self.assertIs(found["found"], True)
        self.assertEqual(len(self.saved()), 1)

    async def test_a_pass_on_a_named_thing_says_it_too(self):
        await self.begin()
        self.session.create_local_feature({"location": self.world["location"], "name": "Eğri mezar taşı",
                                           "description": "Yana yatmış eski bir taş.", "aliases": ["mezar taşı"]})
        found = self.roll("egri mezar tasinin yazisini okumaya calisiyorum", word="yazı")
        self.assertEqual(found["text"], self.FOUND)

    async def test_a_pass_on_a_thing_no_list_held_says_it_too(self):
        await self.begin()
        found = self.roll("kirik muhurlu kavanozu acip icine bakiyorum", word="mühür")
        self.assertEqual(found["text"], self.FOUND)

    async def test_a_failed_roll_finds_nothing_and_saves_nothing(self):
        await self.begin()
        found = self.roll("yerdeki izleri yakindan inceliyorum, ayak izi var mi", "failure")
        self.assertNotIn(self.FOUND, found["text"])
        self.assertEqual(self.saved(), [])

    async def test_a_pass_with_nothing_proposed_stays_as_it_was(self):
        await self.begin()
        self.session._front_found = ("", "")
        self.assertIsNone(self.session._inspection_findings("kirik muhurlu kavanozu acip icine bakiyorum", "success"))

    async def test_the_same_sentence_again_is_no_new_finding(self):
        await self.begin()
        self.roll("yerdeki izleri inceliyorum", word="izler")
        self.assertIsNone(self.roll("kirik muhurlu kavanoza bakiyorum", word="mühür"))
        self.assertEqual(len(self.saved()), 1)

    async def test_a_proposal_that_only_says_the_line_back_is_no_finding(self):
        await self.begin()
        reply = {"front": {"found": "son sayfalarda ne yaziyor", "thing_word": "kagitlar"}}
        self.assertEqual(front_proposal.found_in(reply, "cebindeki kagitlari okuyorum, son sayfalarda ne yaziyor")[0], "")
        reply = {"front": {"found": "yerdeki izler", "thing_word": "izler"}}
        self.assertEqual(front_proposal.found_in(reply, "yerdeki izleri inceliyorum")[0], "")

    async def test_a_real_sentence_is_a_finding(self):
        await self.begin()
        reply = {"front": {"found": self.FOUND, "thing_word": "izler"}}
        self.assertEqual(front_proposal.found_in(reply, "yerdeki izleri inceliyorum")[0], self.FOUND)

    async def test_a_finding_carries_no_money_key_figure_or_new_name(self):
        await self.begin()
        for said in ("Masanın altında paslı bir anahtar duruyor.", "Köşede parlayan üç altın sikke duruyor.",
                     "Kâğıtta kâhyanın adı Umerişa diye yazılı duruyor.", "Kutunun dibinde kazınmış 12 sayısı görünüyor."):
            self.session._front_found = (said, "masa")
            self.assertIsNone(self.session._inspection_findings("masanin altina bakiyorum", "success"), said)
            self.assertFalse([row for row in self.world["features"] if row.get("description") == said], said)

    async def test_a_detail_under_something_is_still_a_finding(self):
        await self.begin()
        self.session._front_found = ("Masanın altında kurumuş bir çamur izi duruyor.", "masa")
        found = self.session._inspection_findings("masanin altina bakiyorum", "success")
        self.assertIs(found["found"], True)

    async def test_a_pass_with_nothing_proposed_shows_what_is_saved_of_a_named_thing(self):
        await self.begin()
        self.session.create_local_feature({"location": self.world["location"], "name": "Eğri taş",
                                           "description": "Yana yatmış eski bir taş.", "aliases": ["taş"]})
        self.session._front_found = ("", "yazı")
        found = self.session._inspection_findings("egri tasin altindaki yaziya bakiyorum", "success")
        self.assertIn("Yana yatmış eski bir taş", found["text"])
        self.assertNotIn("seçemiyorsun", found["text"])
        self.assertIs(found["found"], False)

    async def test_a_pass_on_tracks_with_nothing_proposed_keeps_python_s_line(self):
        await self.begin()
        self.session._front_found = ("", "izler")
        found = self.session._inspection_findings("yerdeki izleri inceliyorum", "success")
        self.assertIn("İzleri dikkatle inceliyorsun", found["text"])

    async def test_a_plain_look_with_no_roll_keeps_the_old_line_for_tracks(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        reply = await self.line("yerdeki izlere bakiyorum")
        self.assertIn("İzleri dikkatle inceliyorsun", str(self.client.message_batches[-1]) + reply["narration"])

    async def test_a_plain_look_with_no_roll_keeps_the_old_line_for_a_named_thing(self):
        await self.begin()
        self.session.create_local_feature({"location": self.world["location"], "name": "Eğri taş",
                                           "description": "Yana yatmış eski bir taş.", "aliases": ["taş"]})
        self.client.front = {"kind": "look"}
        reply = await self.line("egri tasin altindaki yaziya bakiyorum")
        self.assertIn("yeni bir ayrıntı seçemiyorsun", str(self.client.message_batches[-1]) + reply["narration"])

    async def test_a_plain_look_saves_nothing_the_reading_proposed(self):
        await self.begin()
        self.client.front = {"kind": "look", "found": self.FOUND, "thing_word": "izler"}
        await self.line("yerdeki izlere bakiyorum")
        self.assertEqual(self.saved(), [])

    async def test_a_look_leaves_the_reading_as_it_found_it(self):
        await self.begin()
        self.session._front_found = None
        self.session._inspection_findings("yerdeki izlere bakiyorum", "success", rolled=False)
        self.assertIsNone(self.session._front_found)

    async def test_a_second_look_finds_the_same_thing(self):
        await self.begin()
        self.roll("yerdeki izleri yakindan inceliyorum", word="ayak izi")
        self.session._front_found = ("", "")
        found = self.session._inspection_findings("ayak izi yine bakiyorum", "success")
        self.assertIn(self.FOUND, found["text"])

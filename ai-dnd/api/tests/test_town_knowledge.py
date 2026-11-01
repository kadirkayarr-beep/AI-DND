"""People know their town: limited, consistent, voiced by the model, never deciding state."""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import httpx

import game
import grounded_action
import local_dialogue
import local_places
import npc_statements
import relationships
import town_knowledge
import world_threads
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_world_threads import city


AuthenticatedOllamaAdapter = test_campaign_api.AuthenticatedOllamaAdapter
FakeOllamaClient = test_campaign_api.FakeOllamaClient
FixedAuthenticator = test_campaign_api.FixedAuthenticator
TEST_PLAYER = test_campaign_api.TEST_PLAYER


def person(npc_id, role="Kent sakini", **extra):
    return {"id": npc_id, "name": f"Kişi {npc_id}", "public_name": f"Kişi {npc_id}", "role": role,
            "location": "city", **extra}


def seeded(seed="know"):
    world = city(seed)
    world_threads.ensure(world)
    return world


class WhoKnowsWhat(unittest.TestCase):
    def test_the_same_person_always_knows_the_same_things(self):
        world = seeded()
        npc = person("npc_001", "Barmen")
        self.assertEqual(town_knowledge.public_knowledge(world, npc), town_knowledge.public_knowledge(world, npc))
        again = copy.deepcopy(world)
        self.assertEqual(town_knowledge.public_knowledge(again, npc), town_knowledge.public_knowledge(world, npc))

    def test_reading_what_someone_knows_writes_nothing(self):
        world = seeded()
        before = copy.deepcopy(world)
        town_knowledge.public_knowledge(world, person("npc_001", "Barmen"))
        town_knowledge.speech_note(world, person("npc_001", "Barmen"))
        self.assertEqual(world, before)

    def test_it_stays_inside_the_limits(self):
        for index in range(40):
            world = seeded(f"limit-{index}")
            known = town_knowledge.public_knowledge(world, person(f"npc_{index}", "Barmen"))
            self.assertLessEqual(len(known), town_knowledge.MAX_ITEMS)
            self.assertLessEqual(sum(len(i["text"].encode("utf-8")) for i in known), town_knowledge.MAX_BYTES)

    def test_a_barkeep_knows_more_work_than_a_traveller(self):
        keeper = traveller = 0
        for index in range(60):
            world = seeded(f"cover-{index}")
            for role, label in (("Barmen", "k"), ("Gezgin", "t")):
                known = town_knowledge.public_knowledge(world, person(f"npc_{index}{label}", role))
                count = sum(1 for item in known if item["kind"] == "thread")
                if label == "k":
                    keeper += count
                else:
                    traveller += count
        self.assertGreater(keeper, traveller * 2)

    def test_not_everyone_will_talk_and_that_stays_true(self):
        world = seeded()
        people = [person(f"npc_{index}", "Barmen") for index in range(60)]
        closed = [npc for npc in people if town_knowledge.is_closed_mouthed(world, npc)]
        self.assertTrue(closed)
        self.assertLess(len(closed), len(people) / 2)
        self.assertEqual(town_knowledge.public_knowledge(world, closed[0]), [])
        note = town_knowledge.speech_note(world, closed[0])
        self.assertIn("istemiyorsun", note)
        self.assertEqual(note, town_knowledge.speech_note(world, closed[0]))
        for thread in world_threads.active(world):
            self.assertNotIn(thread["public_line"], note)
            self.assertNotIn(thread["owner_line"], note)

    def test_someone_who_will_not_talk_still_sends_you_somewhere_real(self):
        # Real play: a lone closed-mouthed person on a street gave 13 turns of nothing.
        world = seeded()
        places = {world["locations"][t["place_id"]]["name"] for t in world_threads.active(world)}
        people = [person(f"npc_{index}", "Barmen") for index in range(60)]
        for npc in [npc for npc in people if town_knowledge.is_closed_mouthed(world, npc)]:
            note = town_knowledge.speech_note(world, npc)
            self.assertEqual(sum(place in note for place in places), 1, note)

    def test_a_place_a_closed_person_named_can_be_followed(self):
        world = seeded()
        npc = next(person(f"npc_{i}", "Barmen") for i in range(60)
                   if town_knowledge.is_closed_mouthed(world, person(f"npc_{i}", "Barmen")))
        world["npcs"].append(npc)
        name = town_knowledge._brush_off_place(world, npc)
        line = f"{name} tarafına sor, beni uğraştırma."
        npc_statements.record(world, npc, "İş var mı?", line, turn=None)
        town_knowledge.note_mention(world, npc, line)
        self.assertEqual(world["locations"][npc_statements.last_said_place(world)["location_id"]]["name"], name)

    def test_someone_in_most_towns_can_point_somewhere(self):
        pointed = 0
        for index in range(30):
            world = seeded(f"town-{index}")
            people = [person(f"npc_{n}", role) for n, role in enumerate(("Barmen", "Muhafız", "Kent sakini"))]
            pointed += any(item["kind"] == "thread" for npc in people
                           for item in town_knowledge.public_knowledge(world, npc))
        self.assertGreaterEqual(pointed, 27)

    def test_a_thread_owner_knows_their_own_matter_and_speaks_it(self):
        world = seeded()
        thread = world_threads.active(world)[0]
        owner = person("npc_009", "Demirci", location=thread["place_id"], place_role_of=thread["place_id"])
        relationships.note(world, owner["id"], 1, "knows the player")  # the seed may stand this at a house that wants a word first
        known = town_knowledge.public_knowledge(world, owner)
        self.assertIn(thread["thread_id"], [item["thread_id"] for item in known])
        self.assertIn(thread["owner_line"], town_knowledge.speech_note(world, owner))

    def test_only_the_owner_hears_the_terms(self):
        world = seeded()
        for thread in world_threads.active(world):
            for index in range(20):
                note = town_knowledge.speech_note(world, person(f"npc_{index}", "Barmen"))
                self.assertNotIn(thread["owner_line"], note)

    def test_nothing_private_or_mechanical_reaches_the_note(self):
        world = seeded()
        note = town_knowledge.speech_note(world, person("npc_001", "Barmen"))
        for word in ("thread_", "expires", "filled_by_other", "status", "location_0"):
            self.assertNotIn(word, note)

    def test_a_town_with_no_threads_adds_nothing(self):
        world = city("")
        self.assertEqual(town_knowledge.speech_note(world, person("npc_001")), "")
        self.assertIsNone(town_knowledge.fallback_line(world, person("npc_001")))


class WhatWasSaidIsTiedToTheRecord(unittest.TestCase):
    def setUp(self):
        self.world = seeded("bind")
        self.npc = next(person(f"npc_{i}", "Barmen") for i in range(50)
                        if any(item["kind"] == "thread"
                               for item in town_knowledge.public_knowledge(self.world, person(f"npc_{i}", "Barmen"))))
        self.world["npcs"].append(self.npc)
        self.item = next(i for i in town_knowledge.public_knowledge(self.world, self.npc) if i["kind"] == "thread")
        self.place = self.world["locations"][self.item["location_id"]]
        self.thread = next(t for t in world_threads.active(self.world) if t["thread_id"] == self.item["thread_id"])

    def say(self, line):
        npc_statements.record(self.world, self.npc, "İş var mı?", line, turn=None)
        town_knowledge.note_mention(self.world, self.npc, line)
        return npc_statements.last_said_place(self.world)

    def test_a_place_named_with_a_case_ending_is_that_place(self):
        said = self.say(f"Bence {self.place['name']}ne bir uğra.")
        self.assertEqual(said["location_id"], self.place["id"])
        self.assertEqual(self.thread["status"], "heard")

    def test_a_person_named_alone_leads_to_their_place(self):
        said = self.say(f"{self.thread['owner_name']} ile konuş, o bilir.")
        self.assertEqual(said["location_id"], self.place["id"])

    def test_a_plain_noun_only_one_listed_item_fits_is_that_item(self):
        stem = local_places.PLACE_KINDS[self.place["place_kind"]]["noun"]
        known = town_knowledge.public_knowledge(self.world, self.npc)
        same_kind = {self.world["locations"][i["location_id"]].get("place_kind") for i in known}
        if len(same_kind) != len({i["location_id"] for i in known}):
            self.skipTest("two listed places of one kind")
        said = self.say(f"Şu {stem} tarafına bak.")
        self.assertEqual(said["location_id"], self.place["id"])

    def test_a_place_name_is_never_also_a_persons_name(self):
        for index in range(40):
            world = seeded(f"names-{index}")
            first_words = {r["name"].split()[0] for r in world["locations"].values() if r.get("place_kind")}
            people = {t["owner_name"] for t in world_threads.active(world)}
            self.assertEqual(first_words & people, set())

    def test_a_reply_that_names_nothing_listed_changes_nothing(self):
        self.say("Burada öyle bir şey duymadım.")
        self.assertEqual(self.thread["status"], "open")

    def test_a_mention_never_reopens_a_closed_thread(self):
        self.thread["status"] = "expired"
        self.say(f"{self.place['name']} var.")
        self.assertEqual(self.thread["status"], "expired")

    def test_a_broken_mention_never_stops_a_turn(self):
        with patch.object(npc_statements, "bind_said_place", side_effect=RuntimeError("boom")):
            self.say(f"{self.place['name']} var.")


class ModelFailure(unittest.TestCase):
    def test_a_lead_survives_a_failed_model(self):
        world = seeded()
        npc = next(person(f"npc_{i}", "Barmen") for i in range(50)
                   if any(item["kind"] == "thread"
                          for item in town_knowledge.public_knowledge(world, person(f"npc_{i}", "Barmen"))))
        line = town_knowledge.fallback_line(world, npc)
        self.assertTrue(line.startswith("Duyduğuma göre "), line)


class ThroughTheRealTurn(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def start(self):
        self.city, self.session_id, self.session, self.turn_url, self.npc = await self.campaign_with_npc()
        self.client = speech.ScriptedNpcSpeechClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.session = self.manager.get(self.session_id).game_session
        world = self.session.world_state
        # Who knows what has its own tests; here this person simply knows.
        self.enterContext(patch.object(town_knowledge, "_coverage", return_value=100))
        self.enterContext(patch.object(town_knowledge, "is_closed_mouthed", return_value=False))
        world["flags"].update(active_npc_id=self.npc["id"], last_npc_id=self.npc["id"], active_npc_until_turn=99)
        self.npc = next(n for n in world["npcs"] if n["id"] == self.npc["id"])
        self.npc["role"] = "Barmen"

    async def say(self, message, line=None, mode="say"):
        if line is not None:
            self.client.narration = line
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body.update(interaction_mode=mode, target_id=self.npc["id"])
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["narration"]

    def prompt_text(self):
        return json.dumps(self.client.message_batches[-1], ensure_ascii=False, default=str)

    async def test_the_first_speech_seeds_the_town_and_the_model_gets_what_this_person_knows(self):
        await self.start()
        world = self.session.world_state
        self.assertNotIn(world_threads.KEY, world)
        await self.say("Burada nerede iş bulabilirim?", "Bir bakayım.")
        self.assertIn(world_threads.KEY, world)
        self.assertIn("Kentte", self.prompt_text())

    async def test_what_is_going_on_goes_to_the_model_when_the_town_has_something(self):
        await self.start()
        await self.say("Selam.", "Selam.")
        text = await self.say("Burada neler oluyor?", "Kentte bir şeyler dönüyor.", mode=None)
        self.assertNotIn("göze çarpan özel bir şey yok", text)

    async def test_a_failed_model_still_points_at_a_real_lead(self):
        await self.start()
        world = self.session.world_state
        await self.say("Selam.", "Selam.")
        self.client.narration = ""
        text = await self.say("Burada nerede iş bulabilirim?")
        self.assertIn("Duyduğuma göre", text)
        self.assertTrue(npc_statements.last_said_place(world)["location_id"])

    async def resume_in_a_new_process(self):
        campaign_id = self.manager.get(self.session_id).campaign_id
        store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        manager = SessionManager(campaign_store=store)
        app = create_app(session_manager=manager,
                         ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        return manager.get(resumed.json()["session_id"]).game_session.world_state

    async def test_threads_survive_save_and_resume(self):
        await self.start()
        await self.say("Burada nerede iş bulabilirim?", "Bir bakayım.")
        kept = copy.deepcopy(self.session.world_state[world_threads.KEY])
        world = await self.resume_in_a_new_process()
        self.assertEqual(world[world_threads.KEY], kept)

    async def test_a_save_from_before_threads_resumes_and_gains_them_on_its_first_talk(self):
        await self.start()
        self.assertNotIn(world_threads.KEY, self.session.world_state)
        world = await self.resume_in_a_new_process()
        self.assertNotIn(world_threads.KEY, world)
        world_threads.ensure(world)
        self.assertTrue(world_threads.active(world))

    async def test_nothing_of_a_thread_reaches_the_client(self):
        await self.start()
        self.npc["place_role_of"] = None
        response = await self.http.post(self.turn_url, json={
            "message": "Burada nerede iş bulabilirim?", "action_id": str(uuid.uuid4()),
            "interaction_mode": "say", "target_id": self.npc["id"]})
        text = response.text
        self.assertNotIn(world_threads.KEY, text)
        for thread in world_threads.active(self.session.world_state):
            self.assertNotIn(thread["owner_line"], text)
            self.assertNotIn(thread["thread_id"], text)

    async def test_a_failed_model_never_blocks_the_turn_when_the_town_breaks(self):
        await self.start()
        with patch.object(town_knowledge, "speech_note", side_effect=RuntimeError("boom")):
            text = await self.say("Burada nerede iş bulabilirim?", "Bilmem ki.")
        self.assertIn("Bilmem ki", text)

    async def test_asking_for_work_with_nobody_here_hears_a_real_lead(self):
        await self.start()
        world = self.session.world_state
        for npc in world["npcs"]:
            npc["location"] = "elsewhere"
        world["flags"].update(active_npc_id=None, last_npc_id=None, active_npc_until_turn=0)
        text = game._overheard_work(world)
        lines = [t["public_line"] for t in world_threads.active(world)]
        self.assertTrue(any(line in text for line in lines), text)
        self.assertIn(grounded_action.last_target_id(world), [t["place_id"] for t in world_threads.active(world)])


class PointingGoesSomewhere(ThroughTheRealTurn):
    """A named place is real and the player reaches it by saying so."""

    async def heard(self):
        await self.start()
        world = self.session.world_state
        await self.say("Selam.", "Selam.")
        known = town_knowledge.public_knowledge(world, self.npc)
        item = next(i for i in known if i["kind"] == "thread")
        self.thread = next(t for t in world_threads.active(world) if t["thread_id"] == item["thread_id"])
        self.place = world["locations"][self.thread["place_id"]]
        for door in world.get("doors", []):  # the hour may shut the drawn place; getting in has its own tests
            door.update(open=True, locked=False)
        return world

    async def go(self, message):
        self.client.narration = "Bir an durup çevrene kulak veriyorsun."
        response = await self.http.post(self.turn_url, json={"message": message, "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["narration"]

    async def test_going_there_after_a_person_named_it_arrives_and_meets_that_person(self):
        world = await self.heard()
        await self.say("Burada nerede iş bulabilirim?", f"{self.place['name']} tarafına bir uğra.")
        text = await self.go("Tamam, oraya gidiyorum.")
        self.assertEqual(world["location"], self.place["id"], text)
        resident = local_places.resident_of(world, self.place["id"])
        self.assertEqual(resident["name"], self.thread["owner_name"])

    async def test_thanks_before_going_there_still_goes(self):
        for line in ("sağol usta. tamam oraya gidiyorum o zaman",
                     "eyvallah abi, oraya gidiyorum",
                     "teşekkürler usta. tamam gidiyorum"):
            with self.subTest(line=line):
                world = await self.heard()
                self.npc["role"] = "Çizmeci ustası"  # "usta" is this person, and still not where the player goes
                await self.say("Burada nerede iş bulabilirim?", f"{self.place['name']} tarafına bir uğra.")
                text = await self.go(line)
                self.assertEqual(world["location"], self.place["id"], text)

    async def test_going_there_after_only_the_person_was_named_arrives_too(self):
        world = await self.heard()
        await self.say("Burada nerede iş bulabilirim?", f"{self.thread['owner_name']} ile konuş.")
        text = await self.go("Oraya gidiyorum.")
        self.assertEqual(world["location"], self.place["id"], text)

    async def test_going_to_a_person_by_name_goes_to_their_place(self):
        world = await self.heard()
        await self.say("Burada nerede iş bulabilirim?", "Bir bakayım.")
        text = await self.go(f"{self.thread['owner_name']} yanına gidiyorum.")
        self.assertEqual(world["location"], self.place["id"], text)

    async def test_the_place_name_with_a_case_ending_reaches_it(self):
        world = await self.heard()
        text = await self.go(f"{self.place['name']}ne gidiyorum.")
        self.assertEqual(world["location"], self.place["id"], text)

    async def test_two_places_of_one_kind_are_told_apart_by_name(self):
        world = await self.heard()
        other = local_places.create_local_place(world, self.city if isinstance(self.city, str) else
                                                local_places.settlement_of(world, world["location"]),
                                                self.place["place_kind"], name="Kuzgun " + self.place["name"].split()[-1])
        text = await self.go(f"{other['name']}ne gidiyorum.")
        self.assertEqual(world["location"], other["id"], text)

    async def test_calling_someone_who_is_elsewhere_says_where_they_are(self):
        world = await self.heard()
        text = await self.go(f"{self.thread['owner_name']}, burada mısın?")
        self.assertNotIn("adıyla tanıdığın biri görünmüyor", text)
        self.assertIn(self.place["name"], text)
        self.assertEqual(grounded_action.last_target_id(world), self.place["id"])

    async def test_a_place_spoken_outright_beats_the_person_in_the_same_line(self):
        # Real play: "Osric yükünü Tobin Karakolu tarafına götürecek" then "Oraya gidiyorum" went to Osric's shop.
        world = await self.heard()
        other = next(r for r in world["locations"].values()
                     if r.get("place_kind") and r["id"] != self.place["id"])
        await self.say("İş bilen var mı?", f"Duydum ki {self.thread['owner_name']}, {other['name']} tarafına gidecek birini arıyor.")
        text = await self.go("Oraya gidiyorum.")
        self.assertEqual(world["location"], other["id"], text)

    async def test_a_name_already_heard_is_the_name_shown_on_arrival(self):
        world = await self.heard()
        await self.say("İş bilen var mı?", f"{self.thread['owner_name']} ile konuş, {self.place['name']} tarafında.")
        text = await self.go("Oraya gidiyorum.")
        self.assertIn(self.thread["owner_name"], text)

    async def test_a_name_not_heard_stays_hidden_until_it_is_given(self):
        world = await self.heard()
        for thread in world_threads.active(world):
            thread["public_line"] = "Bir yerde iş varmış."
        await self.say("İş bilen var mı?", f"{self.place['name']} tarafına bak.")
        text = await self.go("Oraya gidiyorum.")
        self.assertNotIn(self.thread["owner_name"], text)

    async def test_walking_the_city_from_inside_a_building_goes_outside(self):
        world = await self.heard()
        await self.go(f"{self.place['name']}ne gidiyorum.")
        text = await self.go("Şehirde dolanıyorum, etrafı inceliyorum.")
        self.assertEqual(world["location"], self.place["parent_location_id"], text)
        self.assertNotIn("Tarif ettiğine uyan", text)
        self.assertNotIn("Bulunduğun yerde", text)

    async def test_looking_around_a_room_stays_in_the_room(self):
        world = await self.heard()
        await self.go(f"{self.place['name']}ne gidiyorum.")
        await self.go("Burada biraz dolaşıyorum.")
        self.assertEqual(world["location"], self.place["id"])

    async def test_turning_to_someone_else_changes_who_answers(self):
        # Real play: "Yandaki kişiye dönüyorum" got the same closed-mouthed person again.
        world = await self.heard()
        other = dict(self.npc, id="npc_other", name="Oren", public_name="Oren", place_role_of=None)
        world["npcs"].append(other)
        self.client.narration = "Bir bakayım."
        response = await self.http.post(self.turn_url, json={
            "message": "Yandaki kişiye dönüyorum. Buralarda iş bilen var mı?", "action_id": str(uuid.uuid4())})
        self.assertEqual(world["flags"].get("active_npc_id"), "npc_other", response.text[:300])

    def test_only_words_about_a_person_turn_away(self):
        self.assertTrue(game._turns_to_someone_else("Yandaki kişiye dönüyorum."))
        self.assertTrue(game._turns_to_someone_else("Başka birine soruyorum."))
        self.assertFalse(game._turns_to_someone_else("Başka iş var mı?"))
        self.assertFalse(game._turns_to_someone_else("Bu kişi kim?"))

    async def test_street_talk_never_brings_back_a_place_already_visited(self):
        world = await self.heard()
        await self.go(f"{self.place['name']}ne gidiyorum.")
        settlement = self.place["parent_location_id"]
        for _ in range(6):
            thread = world_threads.street_talk(world, settlement)
            if thread is None:
                break
            self.assertNotEqual(thread["place_id"], self.place["id"])

    async def test_street_talk_is_newer_than_what_someone_said_earlier(self):
        # Real play: "Selwyn Karakolu ..." overheard, then "Oraya gidiyorum" went back to the temple named before.
        world = await self.heard()
        await self.say("İş bilen var mı?", f"{self.place['name']} tarafına bak.")
        for npc in world["npcs"]:
            npc["location"] = "elsewhere"
        world["flags"].update(active_npc_id=None, last_npc_id=None, active_npc_until_turn=0)
        await self.go("Şehirde geziyorum.")
        talk = world_threads.view(world)["overheard"][-1]
        thread = next(t for t in world_threads.active(world) if t["thread_id"] == talk)
        await self.go("Şehirde geziyorum.")
        talk = world_threads.view(world)["overheard"][-1]
        thread = next(t for t in world_threads.active(world) if t["thread_id"] == talk)
        text = await self.go("Oraya gidiyorum.")
        self.assertEqual(world["location"], thread["place_id"], text)

    async def test_going_where_you_already_are_says_so(self):
        world = await self.heard()
        await self.go(f"{self.place['name']}ne gidiyorum.")
        resident = local_places.resident_of(world, self.place["id"])
        line = f"{self.place['name']} el arıyor."
        npc_statements.record(world, resident, "İş var mı?", line, turn=None)
        town_knowledge.note_mention(world, resident, line)
        text = await self.go("Oraya gidiyorum.")
        self.assertEqual(world["location"], self.place["id"], text)
        self.assertNotIn("yolu bulamıyorsun", text)
        self.assertIn(self.place["name"], text)

    async def test_wandering_the_city_turns_up_a_real_lead(self):
        await self.start()
        world = self.session.world_state
        world["location"] = local_places.settlement_of(world, world["location"]) or world["location"]
        self.npc["location"] = "elsewhere"
        world["flags"].update(active_npc_id=None, last_npc_id=None, active_npc_until_turn=0)
        text = await self.go("Şehirde geziyorum.")
        lines = [t["public_line"] for t in world_threads.active(world)]
        self.assertTrue(any(line in text for line in lines), text)
        again = await self.go("Şehirde geziyorum.")
        self.assertNotEqual(text, again)

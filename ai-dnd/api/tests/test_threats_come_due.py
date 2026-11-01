"""A word said aloud comes due on the clock: the model names what it is about from a list, Python says when.

Lines are typed the way the owner types them. Only the Ollama client is scripted.
"""
import copy
import unittest
from unittest.mock import patch

import campaign_time
import relationships
import town_knowledge
import world_happenings
import world_threads

from adventure import dialogue_jobs
from api.tests.test_story_links import Pocket, resident, town
from api.tests.test_said_is_real import ClassifiedClient, Table
from api.tests.test_world_threads import DAY, HOUR


def settle(world, npc, commitment, spoken="O zaman görürsün.", player="kim yakacak, sen mi"):
    return town_knowledge.settle_reply(world, npc, player, commitment, spoken, accept_job=lambda thread: None)


def someone(seed="seed-threat"):
    world, state = town(seed)
    thread = state["threads"][0]
    return world, state, thread, resident(world, thread["place_id"])


def links(world):
    return world_threads.view(world).get(world_happenings.LINKS, [])


class AThreatBecomesAMoment(unittest.TestCase):
    def test_one_said_about_a_listed_job_gets_a_moment_python_chose(self):
        world, state, thread, npc = someone()
        settle(world, npc, {"kind": "warn", "thread_id": thread["thread_id"], "terms": "üç saate kadar"})
        link = links(world)[0]
        self.assertEqual(link["about_thread_id"], thread["thread_id"])
        hours = (link["fires_at"] - world_threads._now(world)) / HOUR
        self.assertGreaterEqual(hours, world_happenings.LINK_HOURS[0])
        self.assertLessEqual(hours, world_happenings.LINK_HOURS[1])
        self.assertEqual(state["happenings"], [])

    def test_the_same_campaign_picks_the_same_moment(self):
        moments = set()
        for _ in range(2):
            world, _, thread, npc = someone()
            settle(world, npc, {"kind": "warn", "thread_id": thread["thread_id"]})
            moments.add(links(world)[0]["fires_at"])
        self.assertEqual(len(moments), 1)

    def test_an_id_the_list_never_had_falls_back_on_the_one_who_said_it(self):
        world, _, thread, npc = someone()
        settle(world, npc, {"kind": "warn", "thread_id": "thread_999", "person_id": "uydurma"})
        link = links(world)[0]
        self.assertIsNone(link["about_thread_id"])
        self.assertEqual(link["owner_npc_id"], npc["id"])
        self.assertEqual(link["place_id"], npc["location"])

    def test_a_listed_person_is_who_it_comes_from(self):
        world, state, thread, npc = someone()
        other = next(t for t in state["threads"] if t["place_id"] != thread["place_id"])
        sender = resident(world, other["place_id"], "gonderen")
        sender["location"] = npc["location"]
        self.assertIn("gonderen", town_knowledge.promise_note(world, npc))
        listed = world_happenings.who_can_be_named(world, npc)
        self.assertIn(sender["id"], [row["id"] for row in listed["people"]])
        settle(world, npc, {"kind": "warn", "person_id": sender["id"]})
        self.assertEqual(links(world)[0]["owner_npc_id"], sender["id"])

    def test_saying_it_twice_is_one_moment_and_the_town_keeps_a_few(self):
        world, state, thread, npc = someone()
        settle(world, npc, {"kind": "warn", "thread_id": thread["thread_id"]})
        settle(world, npc, {"kind": "warn", "thread_id": thread["thread_id"]}, spoken="Görürsün dedim.")
        self.assertEqual(len(links(world)), 1)
        for number in range(12):
            settle(world, resident(world, thread["place_id"], f"biri{number}"), {"kind": "warn"})
        self.assertLessEqual(len(links(world)), world_happenings.MAX_LINKS)
        world_threads.validate(world_threads.view(world))

    def test_an_old_save_has_none_and_a_damaged_one_is_refused(self):
        world, state, thread, npc = someone()
        world_threads.validate(state)
        settle(world, npc, {"kind": "warn", "thread_id": thread["thread_id"]})
        world_threads.validate(state)
        broken = copy.deepcopy(state)
        broken[world_happenings.LINKS][0]["fires_at"] = "yarın"
        with self.assertRaises(ValueError):
            world_threads.validate(broken)

    def test_nothing_comes_of_a_person_who_threatened_nobody(self):
        world, _, thread, npc = someone()
        settle(world, npc, {"kind": "meet", "terms": "akşam gel"})
        self.assertEqual(links(world), [])

    def test_the_prompt_lists_what_a_threat_can_name_and_the_field_exists(self):
        import game
        world, _, thread, npc = someone()
        note = town_knowledge.promise_note(world, npc)
        self.assertIn("warn", note)
        self.assertIn(thread["thread_id"], note)
        self.assertIn(npc["id"], note)
        fields = game._EXPERIMENTAL_NPC_SPEECH_SCHEMA["properties"]["commitment"]["properties"]
        self.assertIn("warn", fields["kind"]["enum"])
        self.assertIn("warned", fields["kind"]["enum"])
        self.assertIn("person_id", fields)


class ItComesDue(unittest.TestCase):
    def armed(self):
        world, state, thread, npc = someone()
        settle(world, npc, {"kind": "warn", "thread_id": thread["thread_id"]})
        return world, thread, npc, links(world)[0]

    def test_before_its_moment_nothing_has_happened(self):
        world, _, _, link = self.armed()
        world_threads.tick(world, link["fires_at"] - 1)
        self.assertEqual(world_threads.view(world)["happenings"], [])
        self.assertIn("fires_at", links(world)[0])

    def test_at_its_moment_the_ledger_has_it_and_no_deed_is_written(self):
        world, thread, _, link = self.armed()
        moment = link["fires_at"]
        world_threads.tick(world, moment)
        state = world_threads.view(world)
        rows = [row for row in state["happenings"] if row["thread_id"] == link["thread_id"]]
        self.assertEqual([(row["kind"], row["at"]) for row in rows], [("visit", moment)])
        self.assertIsNone(links(world)[0].get("fires_at"))
        self.assertNotIn("deeds", world["flags"])

    def test_the_one_who_said_it_knows_it_is_coming_in_words_not_a_figure(self):
        world, thread, npc, link = self.armed()
        note = town_knowledge.speech_note(world, npc)
        self.assertIn("tehdidin", note)
        self.assertNotRegex(note.split("tehdidin")[1][:90], r"\d")

    def test_a_wait_over_many_days_still_brings_it_once(self):
        world, _, _, link = self.armed()
        campaign_time.advance(world, 5 * DAY, "rest", "test")
        rows = [row for row in world_threads.view(world)["happenings"] if row["thread_id"] == link["thread_id"]]
        self.assertEqual(len(rows), 1)


class ThePlayerSaysIt(unittest.TestCase):
    def threatened(self):
        world, state, thread, npc = someone()
        settle(world, npc, {"kind": "warned"}, spoken="Beni tehdit mi ediyorsun?", player="kapina dayanirim bak")
        return world, thread, npc, links(world)[0]

    def test_the_threatened_person_gets_ready_by_the_clock(self):
        world, thread, npc, link = self.threatened()
        self.assertEqual(link["kind"], world_happenings.GUARDED)
        self.assertEqual(link["place_id"], npc["location"])
        world_threads.tick(world, link["fires_at"])
        rows = [row for row in world_threads.view(world)["happenings"] if row["thread_id"] == link["thread_id"]]
        self.assertEqual([row["kind"] for row in rows], ["closed"])

    def test_it_costs_the_player_with_that_person_at_once(self):
        world, _, npc, _ = self.threatened()
        self.assertEqual(relationships.score(world, npc["id"]), -1)

    def test_the_place_takes_nobody_on_for_a_while(self):
        world, thread, npc, link = self.threatened()
        world_threads.tick(world, link["fires_at"])
        self.assertTrue(world_happenings.barred(world_threads.view(world), npc["location"], "hiring", link["opened_at"] + DAY))

    def test_they_know_what_was_said_and_when_they_expect_trouble(self):
        world, thread, npc, link = self.threatened()
        self.assertIn("seni tehdit etti", town_knowledge.speech_note(world, npc))

    def test_standing_there_you_see_it(self):
        world, thread, npc, link = self.threatened()
        world["location"] = npc["location"]
        world_threads.tick(world, link["fires_at"])
        self.assertTrue(world["flags"].get("reaction_lines"))


def a_letter(seed="seed-seal"):
    world, state = town(seed)
    letter = state["threads"][0]
    other = next(t for t in state["threads"] if t is not letter)
    owner = resident(world, letter["place_id"], "kahya")
    letter.update(type="errand", status="accepted", item_noun="mektup", quest_id="q1", target_place_id=other["place_id"],
                  owner_line="Mühürlü mektup var, mührü bozulmasın.", owner_npc_id=owner["id"], offered_at=0,
                  terms={**letter["terms"], "pay": 6})
    world["inventory"] = [{"item_id": "parcel:q1", "name": "Mektup", "quantity": 1}]
    world["location"] = letter["place_id"]
    return world, state, letter, owner


def closed(world, thread, status):
    world_threads.transition(thread, status)
    thread["closed_at"] = world_threads._now(world)
    state = world_threads.view(world)
    state["threads"], gone = world_threads._split_closed(state["threads"])
    state["history"].extend(gone)
    world_threads._apply_effects(world, [(thread["thread_id"], status)])


class TheSealsOwner(unittest.TestCase):
    def test_breaking_the_seal_starts_a_clock_with_no_threat_said_by_anyone(self):
        world, _, letter, owner = a_letter()
        dialogue_jobs.read_parcel(Pocket(world), "kose basinda muhru kiriyorum ne yaziyor okuyorum")
        link = links(world)[0]
        self.assertEqual((link["tone"], link["about_thread_id"], link["owner_npc_id"]),
                         ("opened", letter["thread_id"], owner["id"]))
        self.assertGreater(link["fires_at"], world_threads._now(world))

    def test_a_reading_of_an_open_letter_ties_nothing_twice(self):
        world, _, letter, _ = a_letter()
        session = Pocket(world)
        dialogue_jobs.read_parcel(session, "mektubu okuyorum")
        dialogue_jobs.read_parcel(session, "mektubu bir daha okuyorum")
        self.assertEqual(len(links(world)), 1)

    def test_a_note_with_no_seal_starts_nothing(self):
        world, _, letter, _ = a_letter()
        letter["owner_line"] = "Bu mektubu götür."
        dialogue_jobs.read_parcel(Pocket(world), "mektubu okuyorum")
        self.assertEqual(links(world), [])

    def test_keeping_it_past_its_time_sends_someone_for_it(self):
        world, _, letter, owner = a_letter()
        closed(world, letter, "failed")
        self.assertEqual(links(world)[0]["tone"], "kept")

    def test_delivered_whole_the_owner_still_sends_word(self):
        world, _, letter, owner = a_letter()
        world["inventory"] = []
        closed(world, letter, "done")
        self.assertEqual(links(world)[0]["tone"], "delivered")

    def test_broken_and_delivered_is_one_visit_about_the_seal(self):
        world, _, letter, owner = a_letter()
        dialogue_jobs.read_parcel(Pocket(world), "mektubu okuyorum")
        world["inventory"] = []
        closed(world, letter, "done")
        self.assertEqual([link["tone"] for link in links(world)], ["opened"])

    def test_a_plain_errand_sends_nobody(self):
        world, _, letter, owner = a_letter()
        letter.update(item_noun="paket", owner_line="Şu paketi götür.")
        world["inventory"] = []
        closed(world, letter, "done")
        self.assertEqual(links(world), [])

    def test_the_owner_knows_it_is_coming_and_the_street_can_hear_of_it_after(self):
        world, _, letter, owner = a_letter()
        dialogue_jobs.read_parcel(Pocket(world), "mektubu okuyorum")
        self.assertIn("Mühür kırılmış", town_knowledge.speech_note(world, owner))
        moment = links(world)[0]["fires_at"]
        world_threads.tick(world, moment)
        self.assertRegex(world_threads.view(world)["happenings"][-1]["line"], "mühür|mührün")

    def test_the_one_sent_for_a_kept_letter_can_take_it_back(self):
        world, _, letter, owner = a_letter()
        closed(world, letter, "failed")
        link = links(world)[0]
        visitor = {"id": "ulak", "caller_of": link["thread_id"], "location": world["location"]}
        link["caller_id"] = "ulak"
        self.assertIn(letter, world_threads.late_parcels(world, visitor))

    def test_two_campaigns_differ_in_when(self):
        moments = set()
        for number in range(12):
            world, _, _, _ = a_letter(f"seed-seal-{number}")
            dialogue_jobs.read_parcel(Pocket(world), "mektubu okuyorum")
            moments.add(links(world)[0]["fires_at"] - links(world)[0]["opened_at"])
        self.assertGreater(len(moments), 1)


class AtTheTable(Table):
    async def threat(self):
        await self.begin()
        self.client = ClassifiedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        self.client.speech_extra = {"commitment": {"kind": "warn", "person_id": self.npc["id"]}}
        await self.line("ellerimi yakacakmis. kim yakacak sen mi",
                        "O mührün sahibi kapına dayandığında görürsün kimin eli yanıyormuş.")
        self.client.speech_extra = {}
        return links(self.world)[0]

    async def test_the_threat_at_the_table_ties_a_moment_and_somebody_really_comes(self):
        link = await self.threat()
        before = {npc["id"] for npc in self.world["npcs"]}
        campaign_time.advance(self.world, link["fires_at"] - world_threads._now(self.world) + 1, "rest", "test")
        self.client.front = {"kind": "look"}
        reply = await self.line("etrafa bi bakiyim, kim var kim yok")
        new = [npc for npc in self.world["npcs"] if npc["id"] not in before and npc.get("caller_of")]
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["location"], self.world["location"])
        self.assertIn(world_threads.spoken_owner(self.world, {"owner_npc_id": self.npc["id"]}), reply["narration"])

    async def test_the_visitor_comes_once_and_knows_why_they_came(self):
        link = await self.threat()
        campaign_time.advance(self.world, link["fires_at"] - world_threads._now(self.world) + 1, "rest", "test")
        self.client.front = {"kind": "look"}
        await self.line("etrafa bi bakiyim")
        visitor = world_threads._npc(self.world, links(self.world)[0]["caller_id"])
        await self.line("hmm bir daha bakiyim")
        self.assertEqual(sum(1 for npc in self.world["npcs"] if npc.get("caller_of")), 1)
        self.assertIn("gönderdi", town_knowledge.speech_note(self.world, visitor))

    async def test_a_player_away_from_town_meets_them_on_coming_back(self):
        link = await self.threat()
        campaign_time.advance(self.world, link["fires_at"] - world_threads._now(self.world) + 1, "rest", "test")
        links(self.world)[0]["settlement_id"] = "baska-kent"
        self.client.front = {"kind": "look"}
        await self.line("etrafa bi bakiyim")
        self.assertFalse(any(npc.get("caller_of") for npc in self.world["npcs"]))
        links(self.world)[0]["settlement_id"] = world_threads.view(self.world)["seeded"][0]
        await self.line("bi daha bakayim")
        self.assertTrue(any(npc.get("caller_of") for npc in self.world["npcs"]))

    async def test_the_owner_threatening_back_the_player_threat_needs_no_extra_call(self):
        await self.begin()
        self.client = ClassifiedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        self.client.speech_extra = {"commitment": {"kind": "warned"}}
        await self.line("bak sana diyim, gece kapina dayanirim haberin olsun", "Dene de görelim.")
        self.assertEqual(links(self.world)[0]["kind"], world_happenings.GUARDED)

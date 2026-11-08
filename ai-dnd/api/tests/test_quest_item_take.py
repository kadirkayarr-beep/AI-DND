"""A job's parcel has one owner: taking what is already in the bag makes nothing and says so (Dilim 2, Task 4)."""
from __future__ import annotations

import copy
from unittest.mock import patch

import front_proposal
import game
import pocket
import world_threads
from adventure import dialogue_jobs
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, _front_setting, apply_setup
from api.tests.journeys.schema import Step, load_scenario


class QuestItemTake(JourneyCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.setup = load_scenario(SCENARIO_DIR / "19_quest_item_no_duplicate.json").setup
        campaign = await self._journey_campaign(self.setup)
        apply_setup(self, campaign, self.setup)
        self.session_id = campaign["session_id"]
        self.last_session_id = self.session_id
        self.session = self.manager.get(self.session_id).game_session

    @property
    def world(self):
        return self.session.world_state

    async def turn(self, line, front=None):
        step = Step(say=line, command=None, economic_action=None, combat_action=None,
                    script={"front": front} if front else None, expect={}, known_broken=(), real_chain=False,
                    independent=True)
        with _front_setting(self.setup):
            return await self._play(self.session_id, step, ScriptedModel())

    async def accept(self):
        await self.turn("olur, götürürüm")
        self.assertEqual(self.bag_count(), 1)
        self.parcel_id = "parcel:" + self.accepted_threads()[0]["quest_id"]

    async def take(self, front, line="İade takımını alıyorum"):
        return await self.turn(line, front)

    def accepted_threads(self):
        return [t for t in world_threads.view(self.world)["threads"] if t.get("status") == "accepted"]

    def bag_count(self):
        return sum(i.get("quantity", 1) for i in self.world["inventory"])

    def narration(self):
        return self.last_narration

    def notes(self):
        return list(getattr(self.session, "_turn_notes", None) or [])

    async def accept_without_parcel(self):
        await self.accept()
        [thread] = self.accepted_threads()
        parcel = next(i for i in self.world["inventory"] if i["item_id"] == self.parcel_id)
        self.world["inventory"].remove(parcel)          # item_transfers.transfer_now refuses here (identity unresolved)
        next(n for n in self.world["npcs"] if n.get("id") == thread["owner_npc_id"]).setdefault(
            "inventory", []).append(parcel)
        giver = next(n for n in self.world["npcs"] if n.get("id") == thread["owner_npc_id"])
        giver["location"] = thread["target_place_id"]
        self.assertNotEqual(self.world["location"], giver["location"])

    def add_second_accepted_errand(self, item_noun):
        [first] = self.accepted_threads()
        second = copy.deepcopy(first)
        second.update(thread_id=first["thread_id"] + ":second", quest_id=first["quest_id"] + "2", item_noun=item_noun)
        world_threads.view(self.world)["threads"].append(second)
        quest = copy.deepcopy(next(q for q in self.world["quests"] if q.get("quest_id") == first["quest_id"]))
        quest["quest_id"] = second["quest_id"]
        self.world["quests"].append(quest)
        self.world["inventory"].append({"item_id": "parcel:" + second["quest_id"], "name": "İade takımı",
                                        "quantity": 1})

    async def test_taking_the_parcel_already_in_the_bag_makes_nothing(self):
        await self.accept()
        self.assertEqual(self.bag_count(), 1)
        for front in ({"kind": "take", "item_id": self.parcel_id}, {"kind": "take", "thing_word": "İade takımını"},
                      {"kind": "take", "thing_word": "takımını"}, {"kind": "take", "thing_word": "iade takımını"}):
            with self.subTest(front=front):
                await self.take(front)
                self.assertEqual(self.bag_count(), 1)
                self.assertEqual([i["item_id"] for i in self.world["inventory"]], [self.parcel_id])
                self.assertIn("zaten", self.narration())

    async def test_a_case_ending_still_finds_the_name_in_the_bag(self):
        await self.accept()
        self.assertTrue(pocket._named_in_bag(self.world, pocket._stem("takımını")))      # "takimini" starts with "takimi"
        self.assertTrue(pocket._named_in_bag(self.world, pocket._stem("İade takımı")))
        self.assertFalse(pocket._named_in_bag(self.world, pocket._stem("takım")))         # shorter word: today's answer
        self.assertFalse(pocket._named_in_bag(self.world, pocket._stem("kemer")))

    async def test_the_take_route_carries_a_bag_item_id(self):
        await self.accept()
        listed = front_proposal.listing(self.session)
        route = front_proposal.validate({"front": {"kind": "take", "item_id": self.parcel_id, "thing_word": "takımını"}}, listed)
        self.assertEqual(route, {"kind": "take", "item_id": self.parcel_id, "word": "takımını"})
        route = front_proposal.validate({"front": {"kind": "take", "item_id": "item:nope", "thing_word": "x"}}, listed)
        self.assertEqual(route, {"kind": "unclear"})                       # J-014 #2: an invalid id is no word fallback
        for absent in ("none", "", None):
            with self.subTest(item_id=absent):
                route = front_proposal.validate({"front": {"kind": "take", "item_id": absent, "thing_word": "x"}}, listed)
                self.assertEqual(route, {"kind": "take", "word": "x"})     # no id given: today's word route

    async def test_pickup_never_makes_an_item_from_a_jobs_name(self):
        # the job is accepted but the parcel is still with the giver, and the giver has walked to another place;
        # the narration of the last turn named "iade takımı" here
        await self.accept_without_parcel()
        self.session.recent_dm_narrations.append("Tezgâhın üstünde iade takımı duruyor.")
        for front in ({"kind": "take", "thing_word": "İade takımını"}, {"kind": "take", "thing_word": "takımını"}):
            with self.subTest(front=front):
                await self.take(front)
                self.assertEqual(self.bag_count(), 0)
                self.assertIn((None, "olmadı: İade takımı burada değil"), self.notes())

    async def test_taking_a_plain_thing_still_works(self):
        # Adım 0 ruling: a worthless thing the narration named is picked up; the job rule does not block it
        await self.accept()
        self.session.recent_dm_narrations.append("Masada kırık bir halka duruyor.")
        await self.take({"kind": "take", "thing_word": "kırık halka"}, line="kırık halkayı alıyorum")
        self.assertEqual(self.bag_count(), 2)
        self.assertIn("Kırık halka", [i["name"] for i in self.world["inventory"]])

    async def test_two_jobs_with_the_same_stem_pick_neither(self):
        await self.accept()
        self.add_second_accepted_errand(item_noun="iade takımı")
        self.assertEqual(dialogue_jobs.parcel_for_word(self.world, "takımını"), dialogue_jobs.WordMatch("many", None))

    async def test_parcel_for_word_tells_none_from_many(self):
        await self.accept()
        [job] = [t for t in self.accepted_threads()]
        self.assertEqual(dialogue_jobs.parcel_for_word(self.world, "takımını"), dialogue_jobs.WordMatch("one", job))
        self.assertEqual(dialogue_jobs.parcel_for_word(self.world, "kemer"), dialogue_jobs.WordMatch("none", None))
        self.add_second_accepted_errand(item_noun="iade takımı")
        self.assertEqual(dialogue_jobs.parcel_for_word(self.world, "takımını"), dialogue_jobs.WordMatch("many", None))
        self.assertEqual(dialogue_jobs.parcel_for_word(self.world, "kemer"), dialogue_jobs.WordMatch("none", None))

    async def test_the_four_take_states_end_to_end(self):
        # J-014 #2: field absent / invalid id / no match / ambiguous each have their own result (tasarım karar 55)
        await self.accept()
        self.add_second_accepted_errand(item_noun="iade takımı")                     # makes "takımını" ambiguous
        self.session.recent_dm_narrations.append("Masada kırık bir halka duruyor.")
        bag_before = copy.deepcopy(self.world["inventory"])
        with patch.object(pocket, "take_named", wraps=pocket.take_named) as pickup, \
             patch.object(dialogue_jobs, "hand_over", wraps=dialogue_jobs.hand_over) as handing, \
             patch.object(game, "_thread_gate", wraps=game._thread_gate) as word_reader, \
             patch.object(game, "_front_take", wraps=game._front_take) as front_take:
            # invalid id: unclear; nothing is taken, nothing falls to a word path
            await self.take({"kind": "take", "item_id": "item:nope", "thing_word": "takımını"}, line="takımını alıyorum")
            self.assertEqual((front_take.call_count, pickup.call_count, handing.call_count, word_reader.call_count),
                             (0, 0, 0, 0))
            self.assertEqual(self.world["inventory"], bag_before)
            # ambiguous: two jobs fit the word; nothing is taken and the narrator hears why
            await self.take({"kind": "take", "item_id": "none", "thing_word": "takımını"}, line="takımını alıyorum")
            self.assertEqual((pickup.call_count, handing.call_count), (0, 0))
            self.assertEqual(self.world["inventory"], bag_before)
            self.assertEqual([n for n in self.notes() if n[1].startswith("olmadı")],
                             [(None, "olmadı: hangi işin eşyasını kastettiğin belli değil")])
            # no match: a plain thing the narration named is picked up (Adım 0 ruling)
            await self.take({"kind": "take", "item_id": "none", "thing_word": "kırık halka"}, line="kırık halkayı alıyorum")
            self.assertEqual(pickup.call_count, 1)
            self.assertEqual(sorted(i["name"] for i in self.world["inventory"]),
                             sorted([*(i["name"] for i in bag_before), "Kırık halka"]))
            # field absent: today's pickup with an empty word
            await self.take({"kind": "take", "item_id": "none", "thing_word": ""}, line="onu alıyorum")
            self.assertEqual(pickup.call_count, 2)
            self.assertEqual(pickup.call_args.args[2], "")

    async def test_a_failed_take_leaves_a_turn_note(self):
        await self.accept_without_parcel()
        await self.take({"kind": "take", "thing_word": "İade takımını"})
        self.assertEqual(self.bag_count(), 0)
        self.assertEqual([note for note in self.notes() if note[1].startswith("olmadı")],
                         [(None, "olmadı: İade takımı burada değil")])

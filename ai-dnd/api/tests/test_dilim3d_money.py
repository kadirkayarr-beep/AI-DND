"""Dilim 3D Task 3 (#022, #032): English coin and English yes/no through the real HTTP turn.

#022: "I accept the room for 5 silver. I hand the bartender exactly five silver pieces..." names one sum twice; the
room card takes 50 copper once on confirm, and Undo gives it back. #032: "Of course, Father." answers a shown job
offer as its Turkish twin does.
"""
import copy
from dataclasses import replace

import world_threads
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems
from api.tests.journeys.schema import Step, load_scenario
from api.tests.test_front_money import Q022

TURKISH_022 = "5 gümüşe odayı alıyorum. Barmene beş gümüş veriyorum."
ROOM_READ = {"front": {"kind": "speak_to", "person_id": "barman", "coin_cp": 50, "economic_intent": "room"}}
HALL_LINE = "Salonu iki grup birden istiyor; aralarını bulursan yirmi bakır veririm."


def step(**fields) -> Step:
    base = dict(say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
                known_broken=(), real_chain=False, independent=False)
    base.update(fields)
    return Step(**base)


class EnglishCoinTurn(JourneyCase):
    def scenario(self, seed, steps, *, setup=None):
        source = load_scenario(SCENARIO_DIR / "18_room_phrase_not_job.json")
        base = {key: value for key, value in copy.deepcopy(source.setup).items() if key != "job"}
        base.update(campaign_seed=seed, **(setup or {}))
        return replace(source, id=f"dilim3d_money_{seed}", setup=base, steps=tuple(steps))

    async def play(self, seed, steps, *, setup=None):
        results = await self.run_scenario(self.scenario(seed, steps, setup=setup))
        self.assertEqual(describe_problems(results), [])
        return self.manager.get(self.last_session_id).game_session.world_state

    def pays_the_room(self, line):
        return [step(say=line, script=ROOM_READ,
                     expect={"kese": 100, "oda": False, "kart": {"max_total_cp": 50, "kalemler": ["Oda (bir gece)"]}}),
                step(economic_action={"kind": "confirm"}, expect={"kese": 50, "oda": True, "kart": None})]

    async def test_022_pays_the_room_once(self):
        world = await self.play(4521, self.pays_the_room(Q022))
        self.assertEqual(world["currency"]["player"], 50)

    async def test_022_turkish_twin_pays_the_room_once(self):
        world = await self.play(4522, self.pays_the_room(TURKISH_022))
        self.assertEqual(world["currency"]["player"], 50)

    async def test_undo_gives_the_coin_back(self):
        await self.play(4523, [*self.pays_the_room(Q022),
                              step(undo=True, expect={"kese": 100, "oda": False})])

    def tips_once(self, line):
        read = {"front": {"kind": "speak_to", "person_id": "barman", "coin_cp": 10, "economic_intent": "tip"}}
        # The card's sum is what a confirm may take at most (test_room_purpose_routing reads the tip card the same way).
        return [step(say=line, script=read, expect={"kese": 100, "kart": {"max_total_cp": 5, "kalemler": ["Bahşiş"]}})]

    async def test_a_tip_named_twice_is_given_once(self):
        # The sum on the card is the line's own: the same five copper said twice is five, not ten.
        await self.play(4528, self.tips_once("I leave five copper as a tip. I hand the bartender 5 copper."))

    async def test_a_turkish_tip_named_twice_is_given_once(self):
        await self.play(4529, self.tips_once("Bahşiş olarak beş bakır bırakıyorum. Barmene beş bakır veriyorum."))

    def hall_offer(self):
        return {"npcs": [{"id": "priest", "name": "Aldric", "role": "Rahip", "current_hp": 10}],
                "currency": {"player": 100, "priest": 0},
                "job": {"type": "hiring", "owner": "priest", "status": "offered", "pay": 20, "work_days": 1,
                        "line": HALL_LINE},
                "front_proposal": False}

    async def thread_after(self, seed, line):
        world = await self.play(seed, [step(say=line, expect={"kese": 100})], setup=self.hall_offer())
        threads = world[world_threads.KEY]["threads"]
        self.assertEqual(len(threads), 1)
        return threads[0]["status"]

    async def test_of_course_accepts_the_shown_offer(self):
        turkish = await self.thread_after(4524, "Tabii peder.")
        english = await self.thread_after(4525, "Of course, Father.")
        self.assertEqual(turkish, "accepted")
        self.assertEqual(english, turkish)

    async def test_no_declines_the_shown_offer(self):
        turkish = await self.thread_after(4526, "Hayır.")
        english = await self.thread_after(4527, "No.")
        self.assertEqual(turkish, "declined")
        self.assertEqual(english, turkish)

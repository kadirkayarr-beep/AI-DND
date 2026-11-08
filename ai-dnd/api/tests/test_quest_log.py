"""One quest log: the counter, the journal and the API's old quest fields come from one read-only view (Dilim 2, Task 6)."""
from __future__ import annotations

import copy
import json
from uuid import uuid4

import living_world
import quest_log
import world_threads
from api import serializers
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, _front_setting, apply_setup
from api.tests.journeys.schema import Step, load_scenario

_LEGACY = {"quest_id": "q_legacy", "title": "Eski görev", "description": "d", "status": "accepted",
           "giver_npc_id": None, "objectives": []}


class QuestLogCase(JourneyCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.setup = load_scenario(SCENARIO_DIR / "19_quest_item_no_duplicate.json").setup
        campaign = await self._journey_campaign(self.setup)
        apply_setup(self, campaign, self.setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = campaign["session_id"]
        self.last_session_id = self.session_id

    @property
    def session(self):
        return self.manager.get(self.session_id).game_session

    @property
    def world(self):
        return self.session.world_state

    async def say(self, line, front=None):
        step = Step(say=line, command=None, economic_action=None, combat_action=None,
                    script={"front": front} if front else None, expect={}, known_broken=(), real_chain=False,
                    independent=True)
        with _front_setting(self.setup), ScriptedModel().bind(self, step):
            response = await self.http.post(f"/api/game/sessions/{self.session_id}/turn",
                                            json={"action_id": str(uuid4()), "message": line})
        self.assertEqual(response.status_code, 200, response.text)

    async def world_with_town_errand(self):
        await self.say("olur, götürürüm")
        [thread] = [t for t in world_threads.view(self.world)["threads"] if t.get("status") == "accepted"]
        self.thread_id, self.quest_id = thread["thread_id"], thread["quest_id"]
        self.tuna = thread["recipient_npc_id"]
        return self.world

    def with_legacy_quest(self, world):
        world["quests"].append(copy.deepcopy(_LEGACY))
        return world

    async def world_delivered(self, seal_broken, item_noun="iade takımı"):
        world = await self.world_with_town_errand()
        thread = world_threads.by_id(world, self.thread_id)
        thread["item_noun"] = item_noun
        if seal_broken:
            thread["owner_line"] = "Mührü sakın bozma, mektubu götür."   # dialogue_jobs.sealed reads 'muhr' in the line
            thread["seal_broken"] = True
        world["location"] = thread["target_place_id"]
        await self.say("Tuna, getirdim, buyur", front={"kind": "hand_over", "person_id": self.tuna, "item_id": "none"})
        return self.world

    def state(self):
        return serializers.serialize_session_state(self.session)

    def giver(self, world):
        return next(n for n in world["npcs"] if n["id"] == world_threads.by_id(world, self.thread_id)["owner_npc_id"])

    def recipient(self, world):
        return next(n for n in world["npcs"] if n["id"] == self.tuna)

    def someone_else(self, world):
        if not any(n.get("id") == "stranger" for n in world["npcs"]):
            world["npcs"].append({"id": "stranger", "name": "Selin", "role": "Yolcu", "current_hp": 10,
                                  "location": world["location"]})
        return next(n for n in world["npcs"] if n["id"] == "stranger")


class OneView(QuestLogCase):
    async def test_counter_and_journal_read_one_view(self):
        view = quest_log.view(await self.world_with_town_errand())
        self.assertEqual(view["active_count"], len(view["active"]))
        self.assertEqual(view["active_count"], 1)          # the errand counts (today the counter reads quests.length: 0)

    async def test_the_api_fields_come_from_the_same_view(self):
        world = self.with_legacy_quest(await self.world_with_town_errand())
        state = self.state()
        log = state["quest_log"]
        self.assertEqual(log["active_count"], len(log["active"]))
        self.assertEqual(sorted(r["quest_id"] for r in log["active"]), sorted(["q_legacy", self.quest_id]))
        # old fields keep their membership and formats (karar 47): quests has no dynamic row, lowercase statuses
        self.assertEqual([(q["quest_id"], q["status"]) for q in state["quests"]], [("q_legacy", "accepted")])
        self.assertEqual(set(state["quests"][0]), {"quest_id", "title", "description", "status", "giver_npc_id", "objectives"})
        self.assertEqual([c["title"] for c in state["campaign_adventures"]["active"]],
                         [r["title"] for r in log["active"] if r["record_kind"] == "dynamic"])
        self.assertEqual({r["title"] for r in log["active"]},
                         {q["title"] for q in state["quests"] if q["status"] == "accepted"}
                         | {c["title"] for c in state["campaign_adventures"]["active"]})
        self.assertEqual(world["quests"][-1]["quest_id"], "q_legacy")

    async def test_only_public_names_appear(self):
        world = await self.world_with_town_errand()
        recipient = self.recipient(world)
        recipient["name_known_to_player"] = False                 # the field living_world.npc_name_known_to_player reads
        [row] = quest_log.view(world)["active"]
        self.assertEqual(row["recipient"], living_world.public_npc_name(recipient))
        self.assertNotIn(recipient["name"], json.dumps(quest_log.view(world), ensure_ascii=False))

    async def test_a_done_job_carries_the_engines_result(self):
        world = await self.world_delivered(seal_broken=False)          # scenario 19 + accept + deliver (pay 12)
        [row] = quest_log.view(world)["done"]
        self.assertEqual(row["result"], "12 bakır ödendi")
        self.assertEqual(quest_log.view(world)["active_count"], 0)

    async def test_a_sealed_job_opened_pays_half_and_says_so(self):
        world = await self.world_delivered(seal_broken=True, item_noun="mühürlü mektup")
        [row] = quest_log.view(world)["done"]
        self.assertEqual(row["result"], "mühür kırıktı: 6 bakır")

    async def test_card_lines_for_an_npc_show_only_their_jobs(self):
        world = await self.world_with_town_errand()
        giver, recipient, other = self.giver(world), self.recipient(world), self.someone_else(world)
        for npc in (giver, recipient):
            with self.subTest(npc=npc["id"]):
                [line] = quest_log.card_lines(world, npc=npc)
                self.assertTrue(line.startswith("görevlerin: "))
        self.assertEqual(quest_log.card_lines(world, npc=other), [])
        self.assertEqual(len(quest_log.card_lines(world)), 1)

    async def test_the_rows_carry_the_records_own_kind_and_status(self):
        world = self.with_legacy_quest(await self.world_with_town_errand())
        rows = {r["quest_id"]: r for r in quest_log.view(world)["active"]}
        self.assertEqual((rows["q_legacy"]["record_kind"], rows["q_legacy"]["raw_status"]), (None, "accepted"))
        self.assertEqual((rows[self.quest_id]["record_kind"], rows[self.quest_id]["raw_status"]), ("dynamic", "ACTIVE"))
        self.assertIsNone(rows[self.quest_id]["result"])

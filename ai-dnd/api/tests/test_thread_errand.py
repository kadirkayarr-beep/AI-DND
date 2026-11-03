"""A real errand: taken by word, carried, handed over, paid from the real wallet in the same reply."""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import equipment_economy
import item_transfers
import living_world
import local_places
import world_threads
from adventure import deadlines, dialogue_jobs, director, play, templates
from api.tests import test_experimental_npc_dialogue as speech

DAY = 86400


class ErrandTable(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def job(self, noun="mektup", pay=9):
        self.city, self.session_id, self.session, self.turn_url, self.owner = await self.campaign_with_npc()
        self.client = speech.ScriptedNpcSpeechClient("Şimdilik sessiz bir gün.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world = self.session.world_state
        living_world.ensure_scene_state(self.world)
        self.world["flags"].update(active_npc_id=self.owner["id"], last_npc_id=self.owner["id"], active_npc_until_turn=99)
        self.world.pop(world_threads.KEY, None)
        world_threads.ensure(self.world)
        state = world_threads.view(self.world)
        self.target = local_places.find_local_place(self.world, self.city, "temple") or local_places.create_local_place(
            self.world, self.city, "temple")
        self.target["resident_name"] = "Tariq"
        self.owner["place_role_of"] = self.city
        self.thread = state["threads"][0]
        self.thread.update(type="errand", template_id="courier", status="offered", place_id=self.city,
                           target_place_id=self.target["id"], recipient_name="Tariq", item_noun=noun,
                           owner_name="Kalila", expires_at=5 * DAY, offered_at=0,
                           offered_turn=self.world["flags"].get("turn_index", 0),
                           offer_line=f"{noun.capitalize()} Tariq eline. Dokuz bakır.",
                           owner_line=f"{noun.capitalize()} Tariq eline. Dokuz bakır.",
                           terms={"pay": pay, "work_days": None, "pay_basis": "per_trip", "pay_timing": "on_delivery",
                                  "deadline_text": "bir gün içinde"})
        state["threads"] = [self.thread]
        self.world["npc_speech_log"] = {self.owner["id"]: [{"player": "iş var mı", "npc": self.thread["offer_line"]}]}
        self.tid = self.thread["thread_id"]

    async def line(self, message, reply=None, *, mode=None, target=None):
        if reply is not None:
            self.client.narration = reply
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
        if target:
            body["target_id"] = target
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.world = self.session.world_state
        return response.json()

    def status(self):
        return world_threads.by_id(self.world, self.tid)["status"]

    def row(self):
        return next(q for q in self.world["quests"] if q.get("quest_id") == world_threads.by_id(self.world, self.tid)["quest_id"])

    def wallet(self):
        return self.world.get("currency", {}).get("player", 0)

    def parcel_owner(self):
        item_id = f"parcel:{world_threads.by_id(self.world, self.tid)['quest_id']}"
        return [owner for owner, items in equipment_economy.containers(self.world)
                for item in items if isinstance(item, dict) and item.get("item_id") == item_id]

    def recipient(self):
        return world_threads.recipient_of(self.world, world_threads.by_id(self.world, self.tid))

    def go_to_recipient(self):
        npc = self.recipient()
        self.world["location"] = self.target["id"]
        self.world["flags"].update(active_npc_id=npc["id"], last_npc_id=npc["id"], active_npc_until_turn=99)
        return npc

    def owner_still_holds_it(self):
        """An older save, or a hand-over that failed: the job is taken and the parcel has not moved."""
        item_id = f"parcel:{world_threads.by_id(self.world, self.tid)['quest_id']}"
        item = next(i for i in self.world["inventory"] if isinstance(i, dict) and i.get("item_id") == item_id)
        self.world["inventory"].remove(item)
        self.owner.setdefault("inventory", []).append(item)

    async def test_a_yes_makes_a_journal_row_and_puts_the_parcel_in_hand(self):
        await self.job()
        text = (await self.line("olur", "Tamam, al bakalım."))["narration"]
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.row()["status"], "ACTIVE")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.assertIn("Tamam, al bakalım.", text)
        self.assertIn("sende", text.replace("senin elinde", "sende"))
        self.assertEqual(self.recipient()["name"], "Tariq")
        self.assertEqual(director.active_count(self.world["quests"]), 0)
        event = next(e for e in self.world["scheduled_events"] if e["event_id"] == self.row()["deadline"])
        self.assertEqual(event["window_end"] - event["window_start"], DAY)

    async def test_the_town_job_does_not_stop_an_adventure_or_the_reverse(self):
        await self.job()
        adventure = templates.instantiate(
            "BOUNTY", quest_id="adv.x", turn=0, opportunity_key="opportunity:x", creation_evidence="x",
            bindings=templates.prepared_bindings(source_npc_id=self.owner["id"], target_npc_id=self.owner["id"],
                                                 location_ids=[self.city]), rumor="x")
        self.world.setdefault("quests", []).append(adventure)
        director.discover(self.world, "adv.x")
        director.accept_dynamic(self.world, "adv.x")
        await self.line("olur", "Tamam.")
        self.assertEqual(self.status(), "accepted")

    async def test_a_second_errand_stays_offered_and_the_owner_says_why(self):
        await self.job()
        await self.line("olur", "Tamam.")
        other = copy.deepcopy(self.thread)
        other.update(thread_id="thread_777", status="offered", quest_id=None, offer_line="İkinci iş, on bakır.")
        for name in ("accepted_at", "starts_at", "recipient_npc_id", "log"):
            other.pop(name, None)
        other["terms"]["pay"] = 10
        world_threads.view(self.world)["threads"].append(other)
        self.thread = world_threads.by_id(self.world, self.tid)
        self.world["npc_speech_log"][self.owner["id"]].append({"player": "x", "npc": "İkinci iş, on bakır."})
        await self.line("o işi yaparım", "Önce onu bitir.")
        self.assertEqual(world_threads.by_id(self.world, "thread_777")["status"], "offered")
        self.assertIn("başka bir teslimat", str(self.client.message_batches))

    async def test_taking_it_works_however_it_is_said(self):
        for line in ("mektubu alıyorum", "ver", "al bunu", "ver mektubu götüreyim", "tamam ver mektubu götürürüm"):
            await self.job()
            await self.line("olur", "Tamam.") if line in {"ver", "al bunu"} else None
            await self.line(line, "Al.")
            self.assertEqual(self.status(), "accepted", line)
            self.assertEqual(self.parcel_owner(), ["player"], line)

    async def test_an_accepting_word_and_a_walk_carry_it_along(self):
        await self.job()
        text = (await self.line("tamam, oraya gidiyorum"))["narration"]
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.assertEqual(self.world["location"], self.target["id"])
        self.assertIn("Mektup artık", text.replace("mektup", "Mektup"))

    async def test_with_the_parcel_in_hand_a_walk_is_just_a_walk(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        await self.line("tapınak nerede, oraya gidiyorum")
        self.assertEqual(self.world["location"], self.target["id"])

    async def test_asking_where_while_taking_it_gets_an_answer_and_the_parcel(self):
        await self.job()
        await self.line("iyi tamam ver mektubu götürürüm, ama Tariq kim nerde bulucam onu", "Tapınakta bulursun.")
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.assertEqual(self.client.chat_calls >= 1, True)

    async def test_money_talk_while_taking_it_keeps_the_offer_open(self):
        await self.job()
        await self.line("dokuz bakır mı? dalga mı geçiyosun. mektupta ne var ki, bir gümüş ver götüreyim", "Fiyat belli.")
        self.assertEqual(self.status(), "offered")
        self.assertNotIn(self.thread.get("quest_id"), {"x"})

    async def play_to_the_door(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        return self.go_to_recipient()

    async def test_handing_it_over_pays_once_in_the_same_reply(self):
        for line in ("mektubu getirdim", "işte", "teslim", "tariq sen misin? kalila usta mektubu gönderdi, buyur al, paramı ver",
                     "tariq sen misin? kalila usta mektup gönderdi, buyur mektubunu ver paramı",
                     "mektubu sunağın üstüne bırakıyorum. dokuz bakırımı kim verecek, sabah falan da değil akşam oluyor"):
            await self.play_to_the_door()
            start = self.wallet()
            reply = await self.line(line)
            self.assertEqual(self.wallet() - start, 9, line)
            self.assertEqual(self.status(), "done", line)
            self.assertEqual(self.row()["status"], "COMPLETED", line)
            self.assertEqual(reply["model_calls"] if "model_calls" in reply else 0, 0)
            self.assertEqual(self.parcel_owner(), [self.recipient()["id"]], line)
            self.assertIn("9 bakır", reply["narration"], line)

    async def test_paying_needs_no_money_in_anyone_s_purse(self):
        await self.play_to_the_door()
        self.world["currency"] = {key: value for key, value in self.world.get("currency", {}).items() if key == "player"}
        start = self.wallet()
        await self.line("mektubu getirdim")
        self.assertEqual(self.wallet() - start, 9)
        equipment_economy.validate_world(self.world)
        self.assertFalse([k for k in self.world["currency"] if k.startswith("adventure-pool")])

    async def test_a_job_pays_no_xp_and_opens_no_followup_adventure(self):
        await self.play_to_the_door()
        xp = self.session.character.get("xp")
        count = len(self.world["quests"])
        await self.line("mektubu getirdim")
        self.assertEqual(self.session.character.get("xp"), xp)
        self.assertEqual(len(self.world["quests"]), count)

    async def test_saying_the_money_is_due_after_delivery_never_pays_twice(self):
        await self.play_to_the_door()
        await self.line("mektubu getirdim")
        paid = self.wallet()
        self.world["location"] = self.city
        self.world["flags"].update(active_npc_id=self.owner["id"], last_npc_id=self.owner["id"], active_npc_until_turn=99)
        await self.line("kalila paketi tariqe verdim. dokuz bakırımı alayım, sözünün eri ol", "Aldın ya parayı.")
        self.assertEqual(self.wallet(), paid)
        self.assertIn("ücretini teslimde aldı", str(self.client.message_batches[-1]).replace("ücreti teslim yerinde ödendi", "ücretini teslimde aldı"))

    async def test_the_wrong_person_gets_no_parcel(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        await self.line("mektubu getirdim", "Ne getirdin?")
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.parcel_owner(), ["player"])

    async def test_a_recipient_with_no_parcel_in_hand_gets_a_plain_line(self):
        await self.job()
        await self.line("olur", "Tamam.")
        self.owner_still_holds_it()
        self.go_to_recipient()
        text = (await self.line("mektubu getirdim"))["narration"]
        self.assertIn("elinde değil", text)
        self.assertNotIn("görev", text.casefold())
        self.assertEqual(self.status(), "accepted")

    async def test_missing_the_day_fails_the_job_and_leaves_the_parcel_where_it_was(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        quest_id = world_threads.by_id(self.world, self.tid)["quest_id"]
        await self.line("iki gün bekliyorum")
        self.assertEqual(self.status(), "failed")
        row = next(q for q in self.world["quests"] if q["quest_id"] == quest_id)
        self.assertEqual(row["status"], "FAILED")
        self.assertIsNone(row["reward_application_id"])
        self.assertEqual(self.parcel_owner(), ["player"])

    async def missed_the_day(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        await self.line("iki gün bekliyorum")
        self.assertEqual(self.status(), "failed")

    async def test_the_recipient_knows_what_the_late_parcel_is(self):
        await self.missed_the_day()
        self.go_to_recipient()
        await self.line("selam", "Selam.", mode="say", target=self.recipient()["id"])
        prompt = str(self.client.message_batches[-1])
        self.assertIn("vakti geçti", prompt)
        self.assertNotIn("verecek bir işin yok", prompt)

    async def test_a_parcel_brought_too_late_is_taken_and_pays_nothing(self):
        await self.missed_the_day()
        npc = self.go_to_recipient()
        start = self.wallet()
        text = (await self.line("buyur, mektubunu getirdim"))["narration"]
        self.assertEqual(self.wallet(), start)
        self.assertEqual(self.parcel_owner(), [npc["id"]])
        self.assertEqual(self.status(), "failed")
        self.assertIn("para çıkmıyor", text)
        await self.line("selam", "Selam.", mode="say", target=npc["id"])
        self.assertIn("inkâr etme", str(self.client.message_batches[-1]))

    async def test_a_parcel_can_go_back_to_the_owner_after_the_job_failed(self):
        await self.missed_the_day()
        await self.line("selam", "Selam.", mode="say", target=self.owner["id"])
        self.assertIn("hâlâ onun elinde", str(self.client.message_batches[-1]))
        start = self.wallet()
        text = (await self.line("mektubu getirdim"))["narration"]
        self.assertEqual(self.parcel_owner(), [self.owner["id"]])
        self.assertEqual(self.wallet(), start)
        self.assertIn("para çıkmıyor", text)

    async def test_a_dead_recipient_leaves_the_parcel_for_the_owner_to_take_back(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        self.recipient().update(combat_status="dead", current_hp=0)
        await self.line("bir saat bekliyorum")
        self.assertEqual(self.status(), "expired")
        await self.line("mektubu getirdim")
        self.assertEqual(self.parcel_owner(), [self.owner["id"]])

    async def test_a_parcel_given_to_someone_else_after_the_day_stays_in_hand(self):
        await self.missed_the_day()
        self.world["npcs"].append({"id": "npc_other", "name": "Bren", "role": "Hamal", "location": self.city,
                                   "status": "alive", "personality": "", "appearance": "", "relationship": "neutral",
                                   "knowledge": [], "memory": []})
        self.world["flags"].update(active_npc_id="npc_other", last_npc_id="npc_other", active_npc_until_turn=99)
        await self.line("mektubu getirdim", "Ne mektubu?", mode="say", target="npc_other")
        self.assertEqual(self.parcel_owner(), ["player"])

    async def test_withdrawing_gives_the_parcel_back_and_cools_the_owner(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        await self.line("vazgeçtim", "Sen bilirsin.")
        self.assertEqual(self.status(), "abandoned")
        self.assertEqual(self.parcel_owner(), [self.owner["id"]])
        self.assertEqual(self.world["relationships"][self.owner["id"]]["score"], -1)

    async def test_quitting_and_walking_off_does_not_hand_over_the_parcel(self):
        for line in ("vazgeçtim, gidiyorum", "vazgeçtim gidiyorum"):
            await self.job()
            await self.line("olur", "Tamam.")
            await self.line(line, "Sen bilirsin.")
            self.assertEqual(self.status(), "abandoned", line)
            self.assertEqual(self.parcel_owner(), [self.owner["id"]], line)

    async def test_saying_no_and_walking_off_does_not_hand_over_the_parcel(self):
        for line in ("hayır, gidiyorum", "yok gidiyorum"):
            await self.job()
            await self.line("olur", "Tamam.")
            await self.line(line, "Peki.")
            self.assertEqual(self.status(), "accepted", line)
            self.assertEqual(self.parcel_owner(), ["player"], line)

    async def test_quitting_with_the_parcel_in_hand_gives_it_back_on_the_way_out(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        await self.line("vazgeçtim, gidiyorum", "Sen bilirsin.")
        self.assertEqual(self.status(), "abandoned")
        self.assertEqual(self.parcel_owner(), [self.owner["id"]])

    async def test_a_bare_word_about_something_else_makes_the_owner_ask(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        self.world["npc_speech_log"][self.owner["id"]].append({"player": "x", "npc": "Ekmeği alacak mısın?"})
        await self.line("vazgeçtim", "Neyden?")
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.assertIn("kastettiğini", str(self.client.message_batches[-1]))
        await self.line("vazgeçtim bu işten", "Sen bilirsin.")
        self.assertEqual(self.status(), "abandoned")

    async def test_what_the_owner_said_on_the_job_turn_is_about_the_job(self):
        await self.job()
        await self.line("olur", "Yolun açık olsun.")
        await self.line("vazgeçtim", "Sen bilirsin.")
        self.assertEqual(self.status(), "abandoned")

    async def test_small_talk_after_taking_it_changes_nothing(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.")
        await self.line("hayır", "Peki.")
        self.assertEqual(self.status(), "accepted")

    async def test_both_modes_take_and_deliver(self):
        await self.job()
        await self.line("mektubu alıyorum", "Al.", mode="say", target=self.owner["id"])
        self.assertEqual(self.parcel_owner(), ["player"])
        npc = self.go_to_recipient()
        start = self.wallet()
        await self.line("mektubu getirdim", mode="say", target=npc["id"])
        self.assertEqual(self.wallet() - start, 9)

    async def assert_untouched_after(self, target, line):
        watched = ("quests", "scheduled_events", "inventory", "currency", "world_threads_v1")
        before = {key: copy.deepcopy(self.world.get(key)) for key in watched}
        with patch.object(*target, side_effect=RuntimeError("boom")):
            await self.line(line, "Hmm.")
        for key in watched:
            self.assertEqual(self.world.get(key), before[key], key)

    async def test_a_failure_at_any_step_of_accepting_leaves_nothing(self):
        for target in ((deadlines, "arm"), (director, "discover"), (play, "accept"), (equipment_economy, "materialize"),
                       (world_threads, "accept_hired")):
            await self.job()
            await self.assert_untouched_after(target, "olur")

    async def test_a_failure_at_handing_over_leaves_nothing(self):
        await self.job()
        await self.line("olur", "Tamam.")
        self.owner_still_holds_it()
        # A5: the parcel moves by the one sourced transfer, so the failure is injected there.
        await self.assert_untouched_after((item_transfers, "transfer_existing_item"), "mektubu alıyorum")

    async def test_a_failure_at_delivery_leaves_nothing(self):
        for target in ((item_transfers, "transfer_existing_item"), (world_threads, "sync_from_quests")):
            await self.play_to_the_door()
            await self.assert_untouched_after(target, "mektubu getirdim")

    async def test_no_deadline_means_no_job(self):
        await self.job()
        with patch.object(deadlines, "arm", return_value=None):
            await self.line("olur", "Hmm.")
        self.assertEqual(self.status(), "offered")
        self.assertFalse(self.world.get("quests"))

    async def test_a_dead_recipient_means_no_job(self):
        await self.job()
        self.world["npcs"].append({"id": "npc_tariq", "name": "Tariq", "role": "Rahip", "location": self.target["id"],
                                   "place_role_of": self.target["id"], "combat_status": "dead", "current_hp": 0,
                                   "status": "dead", "personality": "", "appearance": "", "relationship": "neutral",
                                   "knowledge": [], "memory": []})
        await self.line("olur", "Hmm.")
        self.assertEqual(self.status(), "offered")
        self.assertFalse(self.world.get("quests"))

    async def test_a_closed_road_means_no_job(self):
        await self.job()
        self.world["blocked_travel_routes"] = {self.city: {self.target["id"]: True}}
        await self.line("olur", "Hmm.")
        self.assertEqual(self.status(), "offered")


if __name__ == "__main__":
    unittest.main()

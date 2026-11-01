"""A line about someone's work reaches Python first, in the UI's default mode and in say mode."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

import living_world
import town_knowledge
import world_threads
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_world_threads import city


class ThreadTable(unittest.IsolatedAsyncioTestCase):
    """A real session with one person who owns one real job, nobody else near."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def open_job(self, *, kind="hiring", wary=False):
        self.city, self.session_id, self.session, self.turn_url, self.npc = await self.campaign_with_npc()
        self.client = speech.ScriptedNpcSpeechClient("Şimdilik sessiz bir gün.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world = self.session.world_state
        self.seed = living_world.ensure_scene_state(self.world)["campaign_seed"]
        self.world.setdefault("scheduled_events", [])
        self.world["flags"].update(active_npc_id=self.npc["id"], last_npc_id=self.npc["id"], active_npc_until_turn=99)
        self.world.pop(world_threads.KEY, None)
        self.place_id = self.city
        world_threads.ensure(self.world)
        state = world_threads.view(self.world)
        self.assertIsNotNone(state)
        self.thread = state["threads"][0]
        self.thread.update(type=kind, status="open", place_id=self.place_id, expires_at=5 * 86400,
                           owner_line="Yirmi bakır, iki gün; günlüğü on bakır.",
                           terms={"pay": 20, "work_days": 2, "pay_basis": "total", "pay_timing": "end_of_day",
                                  "deadline_text": "iki gün içinde"})
        state["threads"] = [self.thread]
        self.npc["place_role_of"] = self.place_id
        if not wary:
            self.thread["thread_id"] = next(
                f"thread_{n:03d}" for n in range(1, 500)
                if world_threads._rank(self.seed, f"thread_{n:03d}", "wary") % 100 >= world_threads.WARY_PERCENT)
            state["next_number"] = max(state["next_number"], int(self.thread["thread_id"][-3:]) + 1)

    async def line(self, message, reply=None, *, mode=None, target=False):
        if reply is not None:
            self.client.narration = reply
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
        if target:
            body["target_id"] = self.npc["id"]
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def status(self):
        return world_threads.by_id(self.world, self.thread["thread_id"])["status"]

    def offer(self):
        turn = self.world["flags"].get("turn_index", 0)
        world_threads.mark_offered(self.world, self.thread, self.npc, "Yirmi bakır, iki gün.", turn)
        self.world["npc_speech_log"] = {self.npc["id"]: [{"player": "iş var mı", "npc": "Yirmi bakır, iki gün."}]}

    async def test_the_figures_on_screen_open_the_offer(self):
        await self.open_job()
        await self.line("iş var mı?", "İki gün için yirmi bakır veririm.", mode="say", target=True)
        self.assertEqual(self.status(), "offered")
        self.assertEqual(self.thread["offered_terms_shown"]["pay"], 20)

    async def test_a_reply_without_figures_gets_the_real_terms_added(self):
        await self.open_job()
        text = (await self.line("iş var mı?", "Var ama ağır.", mode="say", target=True))["narration"]
        self.assertIn("Yirmi bakır, iki gün", text)
        self.assertEqual(self.status(), "offered")

    async def test_work_asked_for_without_a_question_opens_it_too(self):
        for line in ("bana iş ver", "adam arıyormuşsun"):
            await self.open_job()
            text = (await self.line(line, "Hmm.", mode="say", target=True))["narration"]
            self.assertIn("Yirmi bakır", text, line)
            self.assertEqual(self.status(), "offered", line)

    async def test_small_talk_with_an_owner_opens_nothing(self):
        await self.open_job()
        text = (await self.line("selam", "Selam.", mode="say", target=True))["narration"]
        self.assertNotIn("Yirmi bakır", text)
        self.assertIn(self.status(), {"open", "heard"})

    async def test_a_yes_works_in_the_default_mode_with_no_target(self):
        await self.open_job()
        self.offer()
        await self.line("olur", "Güzel, başla bakalım.")
        self.assertEqual(self.status(), "accepted")

    async def test_a_yes_works_in_say_mode(self):
        await self.open_job()
        self.offer()
        await self.line("olur", "Güzel, başla bakalım.", mode="say", target=True)
        self.assertEqual(self.status(), "accepted")

    async def test_a_no_works_in_both_modes(self):
        for mode, target in ((None, False), ("say", True)):
            await self.open_job()
            self.offer()
            await self.line("yok ya", "Sen bilirsin.", mode=mode, target=target)
            self.assertEqual(self.status(), "declined", mode)

    async def test_an_offer_on_screen_takes_a_yes_on_the_very_next_turn(self):
        for mode, target in ((None, False), ("say", True)):
            await self.open_job()
            await self.line("iş var mı?", "Yirmi bakır, iki gün. Ne dersin?", mode="say", target=True)
            await self.line("olur", "Güzel.", mode=mode, target=target)
            self.assertEqual(self.status(), "accepted", mode)

    async def test_a_yes_to_a_later_subject_does_not_take_the_job(self):
        await self.open_job()
        self.offer()
        await self.line("ailen nasıl", "İyiler. Akşam bize yemeğe gel.")
        self.assertEqual(self.status(), "offered")
        await self.line("olur", "Sevindim.")
        self.assertEqual(self.status(), "offered")
        self.assertEqual(self.thread["offer_line"], "Yirmi bakır, iki gün.")

    async def test_a_yes_after_the_scene_moved_on_needs_to_name_the_job(self):
        await self.open_job()
        self.offer()
        await self.line("etrafa bakıyorum", "Oda boş, kapı aralık. Ne yaparsın?")
        await self.line("evet", "Hmm.")
        self.assertEqual(self.status(), "offered")
        await self.line("o işi yaparım", "Güzel.")
        self.assertEqual(self.status(), "accepted")

    async def test_being_asked_again_takes_the_yes(self):
        await self.open_job()
        self.offer()
        await self.line("hmm", "Ee, yapacak mısın?")
        await self.line("tamam", "Güzel.")
        self.assertEqual(self.status(), "accepted")

    async def test_the_model_cannot_answer_for_the_player(self):
        await self.open_job()
        self.offer()
        await self.line("hmm", "Anlaştık o zaman, işe başladın.")
        self.assertEqual(self.status(), "offered")

    async def test_the_prompt_tells_the_owner_what_was_decided_and_money_stays_put(self):
        await self.open_job()
        self.offer()
        before = dict(self.world.get("currency") or {})
        await self.line("önce parayı görelim", "Peşin yok, gün sonunda.")
        self.assertEqual(self.status(), "offered")
        prompt = str(self.client.message_batches)
        self.assertIn("Peşin ya da avans veremezsin", prompt)
        self.assertEqual(dict(self.world.get("currency") or {}), before)

    async def test_after_the_terms_are_argued_a_bare_yes_still_binds(self):
        await self.open_job()
        self.offer()
        await self.line("önce parayı görelim", "Peşin yok, gün sonunda.")
        await self.line("iyi tamam", "Güzel.")
        self.assertEqual(self.status(), "accepted")

    async def test_a_no_followed_by_a_changed_mind_takes_the_job(self):
        await self.open_job()
        self.offer()
        await self.line("yok ya", "Nasıl istersen.")
        self.assertEqual(self.status(), "declined")
        await self.line("yok ya... neyse olur, ne zaman başlıyorum?", "Yarın.")
        self.assertEqual(self.status(), "accepted")

    async def test_a_question_the_owner_asked_takes_the_bare_yes(self):
        await self.open_job()
        self.offer()
        self.world["npc_speech_log"][self.npc["id"]].append({"player": "sıcak", "npc": "Bir şey içer misin?"})
        await self.line("olur", "Al bakalım.")
        self.assertEqual(self.status(), "offered")

    async def test_a_physical_act_in_the_room_is_left_to_its_owner(self):
        await self.open_job()
        self.offer()
        await self.line("etrafa bakıyorum")
        self.assertEqual(self.status(), "offered")

    async def test_what_the_player_said_at_payment_goes_to_the_person_not_a_stock_denial(self):
        await self.open_job()
        self.offer()
        await self.line("olur", "Tamam.")
        reply = await self.line("sen söyledin yirmi bakır diye, paramı ver", "Gün bitince.")
        self.assertEqual(reply["narration"].count("Gün bitince"), 1)

    async def test_nothing_in_the_note_is_a_number_for_the_relationship(self):
        await self.open_job()
        self.world["relationships"] = {self.npc["id"]: {"score": -2, "events": ["x"]}}
        note = town_knowledge.speech_note(self.world, self.npc)
        self.assertIn("soğuk", note)
        self.assertNotIn("-2", note)

    async def test_someone_with_no_job_is_told_not_to_claim_one(self):
        await self.open_job()
        self.npc.pop("place_role_of")
        note = town_knowledge.speech_note(self.world, self.npc)
        self.assertIn("verecek bir işin yok", note)

    async def test_an_owner_sizing_up_a_stranger_gives_no_figure(self):
        await self.open_job(wary=True)
        self.thread["thread_id"] = next(
            f"thread_{n:03d}" for n in range(1, 500)
            if world_threads._rank(self.seed, f"thread_{n:03d}", "wary") % 100 < world_threads.WARY_PERCENT)
        self.world.pop("npc_speech_log", None)
        self.world.pop("npc_statements", None)
        text = (await self.line("iş var mı?", "Sen kimsin önce?", mode="say", target=True))["narration"]
        self.assertNotIn("Yirmi bakır", text)
        self.assertIn(self.status(), {"open", "heard"})
        text = (await self.line("iş var mı?", "Yirmi bakır, iki gün.", mode="say", target=True))["narration"]
        self.assertEqual(self.status(), "offered")

    async def test_someone_let_down_will_not_offer_again(self):
        await self.open_job()
        self.world["relationships"] = {self.npc["id"]: {"score": -1, "events": ["x"]}}
        world_threads.view(self.world)["history"].append(dict(self.thread, thread_id="thread_old", status="failed",
                                                              offered_at=0, closed_at=0))
        text = (await self.line("iş var mı?", "Sana iş yok.", mode="say", target=True))["narration"]
        self.assertNotIn("Yirmi bakır", text)
        self.assertIn(self.status(), {"open", "heard"})
        self.assertIn("iş vermek istemiyorsun", str(self.client.message_batches))


class NoteWording(unittest.TestCase):
    def test_a_trouble_owner_is_told_it_is_not_paid_work(self):
        world = city("trouble-note")
        world_threads.ensure(world)
        thread = world[world_threads.KEY]["threads"][0]
        thread["type"] = "trouble"
        npc = {"id": "n", "name": "Kalila", "role": "Usta", "location": "city", "place_role_of": thread["place_id"]}
        world["npcs"].append(npc)
        note = town_knowledge.speech_note(world, npc)
        self.assertIn("iş değil", note)
        self.assertIn("para", note)


if __name__ == "__main__":
    unittest.main()

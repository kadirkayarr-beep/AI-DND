"""One start, three choices, one day later: three different towns. Real HTTP, the model mocked."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

import living_world
import town_knowledge
import world_threads
from api.tests import test_experimental_npc_dialogue as speech

SEEDS = [f"branch-{number}" for number in range(20)]
MODES = (None, "say")


class Branches(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def town(self, seed):
        self.city, self.session_id, self.session, self.turn_url, self.owner = await self.campaign_with_npc()
        self.client = speech.ScriptedNpcSpeechClient("Hmm.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world = self.session.world_state
        living_world.ensure_scene_state(self.world)["campaign_seed"] = seed
        self.world["flags"].update(active_npc_id=self.owner["id"], last_npc_id=self.owner["id"], active_npc_until_turn=99)
        self.world.pop(world_threads.KEY, None)
        world_threads.ensure(self.world)
        state = world_threads.view(self.world)
        self.owner["place_role_of"] = self.city
        neighbour = next(t for t in state["threads"][1:] if t["place_id"] != self.city)
        self.neighbour = {"id": "npc_neighbour", "name": "Bren", "public_name": "Bren", "role": "Usta",
                          "location": neighbour["place_id"], "place_role_of": neighbour["place_id"],
                          "name_known_to_player": True, "personality": "", "appearance": "", "relationship": "neutral",
                          "knowledge": [], "memory": [], "combat_status": "active", "current_hp": 8, "status": "active"}
        self.world["npcs"].append(self.neighbour)
        self.thread = state["threads"][0]
        self.thread.update(type="hiring", template_id="hand_wanted", status="open", place_id=self.city, offered_at=None,
                           target_place_id=None, recipient_name=None, owner_name="Marek", expires_at=30 * 86400,
                           owner_line="Bir günlük iş; günlüğü on iki bakır.",
                           terms={"pay": 12, "work_days": 1, "pay_basis": "daily", "pay_timing": "end_of_day",
                                  "deadline_text": "bir gün içinde"})
        state["threads"] = [self.thread]
        self.world["campaign_time"]["start_second"] = 7 * 3600
        # someone sizing a stranger up is its own path; here everyone gets as far as the offer
        self.world["npc_speech_log"] = {self.owner["id"]: [{"player": "selam", "npc": "Selam."}]}
        self.tid = self.thread["thread_id"]

    async def line(self, message, reply=None, *, mode=None):
        if reply is not None:
            self.client.narration = reply
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
            body["target_id"] = self.owner["id"]
        before = self.client.chat_calls
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(self.client.chat_calls - before, 1, message)
        self.world = self.session.world_state
        return response.json()

    async def wait_a_day(self):
        await self.line("bir gün bekliyorum")

    def result(self):
        thread = world_threads.by_id(self.world, self.tid)
        note = town_knowledge.speech_note(self.world, self.owner)
        return {"status": thread["status"], "wallet": self.world.get("currency", {}).get("player", 0),
                "note": note.rsplit("uydurma.", 1)[-1], "who": thread.get("filled_by_name"),
                "log": len(thread.get("log", []))}

    async def start(self, seed, mode):
        await self.town(seed)
        await self.line("iş var mı?", "Bir günlük iş var, günlüğü on iki bakır.", mode=mode)
        self.assertEqual(world_threads.by_id(self.world, self.tid)["status"], "offered", seed)

    async def take_it(self, seed, mode):
        await self.start(seed, mode)
        await self.line("olur", "Güzel.", mode=mode)
        await self.line("başlayalım", mode=mode)
        await self.wait_a_day()
        return self.result()

    async def turn_it_down(self, seed, mode):
        await self.start(seed, mode)
        await self.line("yok ya", "Sen bilirsin.", mode=mode)
        await self.wait_a_day()
        return self.result()

    async def say_nothing(self, seed, mode):
        await self.start(seed, mode)
        await self.wait_a_day()
        return self.result()

    async def test_three_choices_make_three_towns_in_every_seed_and_both_modes(self):
        for seed in SEEDS:
            for mode in MODES:
                taken = await self.take_it(seed, mode)
                refused = await self.turn_it_down(seed, mode)
                silent = await self.say_nothing(seed, mode)
                self.assertEqual(taken["status"], "done", seed)
                self.assertEqual(silent["status"], "expired", seed)
                self.assertIn(refused["status"], {"filled_by_other", "expired"}, seed)
                self.assertEqual(taken["wallet"] - silent["wallet"], 12, seed)
                self.assertEqual(len({r["note"] for r in (taken, refused, silent)}), 3, (seed, mode))
                self.assertNotEqual(refused["log"], taken["log"])
                if refused["status"] == "filled_by_other":
                    self.assertTrue(refused["who"], seed)

    async def test_most_refused_work_goes_to_someone_with_a_name(self):
        filled = 0
        for seed in SEEDS:
            refused = await self.turn_it_down(seed, None)
            filled += refused["status"] == "filled_by_other"
            if refused["status"] == "filled_by_other":
                self.assertTrue(refused["who"])
        self.assertGreaterEqual(filled, 14)

    async def test_the_wage_is_the_only_money_that_moved(self):
        await self.start("wage", None)
        start = self.world.get("currency", {}).get("player", 0)
        await self.line("olur", "Güzel.")
        self.assertEqual(self.world.get("currency", {}).get("player", 0), start)
        await self.line("başlayalım")
        self.assertEqual(self.world.get("currency", {}).get("player", 0) - start, 12)

    async def test_a_refused_owner_is_not_offered_again_and_says_so_when_asked(self):
        await self.start("again", None)
        await self.line("yok ya", "Sen bilirsin.")
        await self.line("hâlâ iş var mı?", "O iş duruyor.")
        self.assertIn("yeniden sunma", str(self.client.message_batches[-1]))
        self.assertEqual(world_threads.by_id(self.world, self.tid)["status"], "declined")

    async def test_changing_your_mind_inside_the_window_takes_the_job(self):
        await self.start("mind", None)
        await self.line("yok ya", "Sen bilirsin.")
        await self.line("iki saat bekliyorum")
        self.world["flags"].update(active_npc_id=self.owner["id"], last_npc_id=self.owner["id"], active_npc_until_turn=99)
        await self.line("o işi yaparım", "Tamam.")
        self.assertEqual(world_threads.by_id(self.world, self.tid)["status"], "accepted")


class SaidButNeverRecorded(unittest.IsolatedAsyncioTestCase):
    """An appointment the model made up, with the speech switch off as it is in real play."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def begin(self):
        self.city, self.session_id, self.session, self.turn_url, self.npc = await self.campaign_with_npc(experimental=False)
        self.client = speech.ScriptedNpcSpeechClient("Yazmasına yazdım, etkinlik yarın sabah.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world = self.session.world_state
        self.world["flags"].update(active_npc_id=self.npc["id"], last_npc_id=self.npc["id"], active_npc_until_turn=99)

    async def line(self, message, reply=None, *, mode=None):
        if reply is not None:
            self.client.narration = reply
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
            body["target_id"] = self.npc["id"]
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["narration"]

    async def test_unrecorded_notebook_claim_is_not_verified_by_a_different_quote(self):
        await self.begin()
        import copy
        import npc_statements
        first = await self.line("yazdın mı peki? o etkinlik ne zaman, ne zaman geleyim", mode="say")
        self.assertIn("Yazmasına yazdım", first)
        claim = "dün beni deftere yazdın, yarın sabah gel dedin. bak deftere"
        self.assertEqual(npc_statements.claim_support(self.world, self.npc, claim)["status"], "unsupported")
        before_money = copy.deepcopy(self.world.get("currency"))
        before_commitments = copy.deepcopy(npc_statements.view(self.world)["commitments"])
        self.world["flags"].update(active_npc_id=None, active_npc_until_turn=-1)
        text = await self.line(claim, "Evet demiştim ama defter dolu.")
        self.assertNotIn("Evet demiştim", text)
        self.assertNotIn("defter dolu", text)
        self.assertEqual(self.world.get("currency"), before_money)
        self.assertEqual(npc_statements.view(self.world)["commitments"], before_commitments)

    async def test_a_displayed_recorded_quote_can_be_recalled_without_added_notebook_claims(self):
        await self.begin()
        first = await self.line("yazdın mı peki? o etkinlik ne zaman, ne zaman geleyim", mode="say")
        import npc_statements
        self.assertIn("Yazmasına yazdım", first)
        ledger = self.world.get(npc_statements.KEY)
        self.assertIsNotNone(ledger)
        self.assertIn("Yazmasına yazdım", str(ledger))
        self.assertEqual(npc_statements.claim_support(self.world, self.npc,
            "dün beni deftere yazdın, yarın sabah gel dedin. bak deftere")["status"], "unsupported")
        text = await self.line("etkinlik yarın sabah demiştin", "Etkinlik yarın sabah demiştim.")
        self.assertIn("Etkinlik yarın sabah demiştim", text, {"ledger": ledger, "reply": text})
    async def test_a_person_with_no_job_is_told_to_take_it_back(self):
        await self.begin()
        await self.line("yazdın mı peki? ne zaman geleyim", mode="say")
        self.assertIn("verecek bir işin yok", str(self.client.message_batches[-1]))


if __name__ == "__main__":
    unittest.main()

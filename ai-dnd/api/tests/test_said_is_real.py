"""What the screen says happened happened: items, hand-overs, work and blows are Python's to commit.

Real app, real engine; only the Ollama client is scripted. Lines are typed the way the owner types them.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import equipment_economy
import front_proposal
import world_threads
from api.tests import test_front_proposal as front_tests
from api.tests import test_experimental_npc_dialogue as speech
from api.tests import test_thread_errand as errand_tests
from api.tests import test_thread_gate as gate_tests


class Table(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    open_job = gate_tests.ThreadTable.open_job
    line = gate_tests.ThreadTable.line
    status = gate_tests.ThreadTable.status
    offer = gate_tests.ThreadTable.offer
    begin = front_tests.FrontTable.begin
    routes = front_tests.FrontTable.routes


class ClassifiedClient(front_tests.FrontClient):
    """A classifier that heard something else than the line says, as a small model does."""

    intent = None
    narrator_extra = {}

    def chat(self, *args, **kwargs):
        properties = (kwargs.get("format") or {}).get("properties") or {}
        if "narration" in properties and "intent" not in properties:
            self.chat_calls += 1
            self.schemas.append(kwargs.get("format"))
            self.message_batches.append(kwargs.get("messages", []))
            packet = {"narration": self.narration, "world_updates": {}, "lore_claims": []}
            return {"message": {"content": json.dumps({**packet, **self.narrator_extra}, ensure_ascii=False)}}
        reply = super().chat(*args, **kwargs)
        if self.intent and "intent" in properties:
            packet = json.loads(reply["message"]["content"])
            packet.update(intent=self.intent, action=self.intent)
            reply = {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return reply


class BlowsThatRan(Table):
    async def fight(self):
        await self.begin()
        self.client = ClassifiedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.npc.update(armor_class=8, max_hp=40, current_hp=40)
        self.session.character.update(max_hp=300, current_hp=300)
        await self.line("marek'in suratina vuruyorum")
        self.assertTrue(self.world["combat"]["active"])

    async def test_a_blow_with_a_do_not_kill_beside_it_is_still_a_blow(self):
        await self.fight()
        reply = await self.line("bir daha kabzayla vuruyorum, bayilt onu, oldurme")
        self.assertEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_blow_said_with_i_am_not_killing_him_is_still_a_blow(self):
        await self.fight()
        reply = await self.line("vuruyorum yine ama oldurmuyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_line_that_refuses_every_blow_stays_no_blow(self):
        await self.fight()
        reply = await self.line("vurmuyorum, saldirmiyorum")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_fall_nothing_caused_leaves_the_line(self):
        await self.fight()
        self.client.intent = "attack"
        self.client.narration = ("Taş avluda rüzgâr esiyor. Marek geriye doğru sendeliyor, "
                                 "gözlerinde şaşkınlıkla yere yığılıyor.")
        reply = await self.line("kilici kaldirip tehditkar bir hamle yapiyorum")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack")
        self.assertNotIn("yığılıyor", reply["narration"])

    async def test_a_refused_blow_is_not_told_as_a_hit(self):
        await self.fight()
        self.client.intent = "attack"
        self.client.narration = "Marek bir darbe alır ve yere yığılıyor."
        reply = await self.line("onu oldurmuyorum")
        self.assertNotIn("darbe", reply["narration"])
        self.assertNotIn("yığılıyor", reply["narration"])


class ErrandBase(unittest.IsolatedAsyncioTestCase):
    """A real offered errand with the front reading on, its answer scripted turn by turn."""

    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    job = errand_tests.ErrandTable.job
    line = errand_tests.ErrandTable.line
    status = errand_tests.ErrandTable.status
    row = errand_tests.ErrandTable.row
    wallet = errand_tests.ErrandTable.wallet
    parcel_owner = errand_tests.ErrandTable.parcel_owner
    recipient = errand_tests.ErrandTable.recipient
    go_to_recipient = errand_tests.ErrandTable.go_to_recipient

    routes = front_tests.FrontTable.routes

    async def errand(self, noun="buluşma notu", pay=10, front=True):
        await self.job(noun=noun, pay=pay)
        if front:
            self.directory = tempfile.TemporaryDirectory()
            self.addCleanup(self.directory.cleanup)
            self.route_file = Path(self.directory.name) / "routes.jsonl"
            self.enterContext(patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1",
                                                      "AI_DND_ROUTE_LOG": str(self.route_file)}))
        self.client = ClassifiedClient("Şimdilik sessiz bir gün.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))

    def parcel(self):
        return "parcel:" + world_threads.by_id(self.world, self.tid)["quest_id"]

    def bag(self):
        return [item.get("name") if isinstance(item, dict) else item for item in self.world.get("inventory", [])]


class SayingYes(ErrandBase):
    async def test_the_real_price_said_back_is_a_yes_not_a_bargain(self):
        await self.errand(front=False)
        await self.line("tamam o notu alirim, on bakir", "Peki, al öyleyse.")
        self.assertEqual(self.status(), "accepted")

    async def test_another_price_is_still_a_bargain(self):
        await self.errand(front=False)
        await self.line("tamam o notu alirim, on bes bakir", "Olmaz.")
        self.assertEqual(self.status(), "offered")

    async def test_a_yes_with_a_question_beside_it_is_a_yes(self):
        await self.errand(noun="yol kapanışı duyurusu", pay=25, front=False)
        await self.line("peki tamam alirim isi, nerden alacam duyuruyu", "Benden alacaksın.")
        self.assertEqual(self.status(), "accepted")

    async def test_the_front_yes_stands_on_the_real_price(self):
        await self.errand()
        self.client.front = {"kind": "offer_answer", "offer_id": self.tid, "answer": "accept"}
        await self.line("eh iyi madem, on bakira razi geldim", "Peki.")
        self.assertEqual(self.status(), "accepted")

    async def test_the_thing_offered_taken_is_the_job_and_the_real_paper_in_the_bag(self):
        await self.errand()
        self.client.front = {"kind": "take", "offer_id": self.tid}
        await self.line("hadi uzat su kagidi", "Peki, al öyleyse.")
        self.assertEqual(self.status(), "accepted")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.client.front = {"kind": "unclear"}
        text = (await self.line("notu acip okuyorum gizlice"))["narration"]
        self.assertIn("Kâğıtta şunlar yazıyor", text)


class HandingOver(ErrandBase):
    async def carried(self):
        await self.errand(noun="yol kapanışı duyurusu", pay=25)
        self.client.front = {"kind": "take", "offer_id": self.tid}
        await self.line("ver bakalim su duyuruyu", "Al.")
        self.assertEqual(self.parcel_owner(), ["player"])
        return self.go_to_recipient()

    async def test_any_wording_of_a_hand_over_pays(self):
        for line in ("al sana duyuruyu veriyorum, iste bu", "duyuruyu lavunelin eline veriyorum",
                     "su kagidi masaya birakiyom buyur", "bak sana getirdigim sey bu"):
            await self.carried()
            person = self.recipient()
            self.client.front = {"kind": "hand_over", "person_id": person["id"], "item_id": self.parcel()}
            reply = await self.line(line)
            self.assertEqual(self.wallet(), 25, line)
            self.assertEqual(self.parcel_owner(), [person["id"]], line)
            self.assertEqual(reply["turn_outcome"]["action"], "item_transfer", line)

    async def test_one_person_here_needs_no_name(self):
        await self.carried()
        self.client.front = {"kind": "hand_over", "item_id": self.parcel()}
        await self.line("buyur iste bu")
        self.assertEqual(self.wallet(), 25)

    async def test_the_wrong_person_gets_nothing_and_answers(self):
        await self.carried()
        self.world["location"] = self.city
        self.world["flags"].update(active_npc_id=self.owner["id"], last_npc_id=self.owner["id"])
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"], "item_id": self.parcel()}
        reply = await self.line("sana veriyorum bunu, hadi al", "Bu bana gelmez.")
        self.assertEqual(self.parcel_owner(), ["player"])
        self.assertEqual(self.wallet(), 0)
        self.assertIn("Bu bana gelmez", reply["narration"])

    async def test_a_question_about_handing_it_over_moves_nothing(self):
        await self.carried()
        person = self.recipient()
        self.client.front = {"kind": "hand_over", "person_id": person["id"], "item_id": self.parcel()}
        await self.line("sana mi vereyim bunu?", "Bana ver tabii.")
        self.assertEqual(self.parcel_owner(), ["player"])

    async def test_a_thing_of_the_bag_goes_to_the_person_for_real(self):
        await self.errand()
        equipment_economy.grant_plain(self.world, "Kırık halka")
        item = next(i for i in self.world["inventory"] if isinstance(i, dict) and i.get("name") == "Kırık halka")
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"], "item_id": item["item_id"]}
        reply = await self.line("sunu sana uzatiyorum usta, sakla", "Sağ ol, dursun bende.")
        self.assertNotIn("Kırık halka", self.bag())
        self.assertIn(item, self.owner["inventory"])
        self.assertIn("Sağ ol", reply["narration"])

    async def test_a_worn_blade_stays_off_the_list(self):
        await self.errand()
        held = set((self.world.get("equipment") or {}).values())
        listed = front_proposal.listing(self.session)
        self.assertFalse(held & {row["id"] for row in listed["bag"]})

    async def test_an_id_nobody_listed_moves_nothing(self):
        await self.carried()
        person = self.recipient()
        self.client.front = {"kind": "hand_over", "person_id": person["id"], "item_id": "item_999"}
        await self.line("hadi bakalim, senin icin getirdim", "Hm.")
        self.assertEqual(self.routes()[-1]["route"], "fallback:invalid")

    async def test_giving_what_is_not_there_is_told_as_it_is(self):
        await self.errand()
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"]}
        reply = await self.line("duyuruyu eline veriyorum", "Neyi?")
        self.assertIn("Neyi?", reply["narration"])
        self.assertEqual(self.wallet(), 0)

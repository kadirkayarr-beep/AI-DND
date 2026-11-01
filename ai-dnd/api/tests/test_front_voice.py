"""The line is understood and answered in the right voice: blows, stock lines, hands on people, bare walks, two parts.

Real app, real adapter, real engine; only the model client is scripted. The lines are the owner's own, as typed.
"""

from __future__ import annotations

import front_proposal
from api.tests.test_front_proposal import FrontTable


class AnyBlowIsAnAttack(FrontTable):
    async def begin(self, **kwargs):
        await super().begin(**kwargs)
        self.npc.update(armor_class=10, max_hp=12, current_hp=12)  # what a person of the town really carries

    async def blow(self, line, **front):
        await self.begin()
        self.client.front = {"kind": "strike", "person_id": self.npc["id"], **front}
        return await self.line(line, "Ne yapıyorsun sen?")

    def assert_attacked(self, reply):
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(reply["turn_outcome"]["target_name"], self.npc["name"])
        self.assertTrue(self.world["combat"]["active"] or reply["combat_result"]["combat_status"] == "ended")
        self.assertEqual(self.routes()[-1]["route"], "front:strike")

    def assert_no_blow(self, reply):
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertFalse(self.world["combat"]["active"])
        self.assertNotIn("Nereden bileyim", reply["narration"])

    async def test_a_fist_is_an_attack_and_a_bare_one(self):
        reply = await self.blow("güldüm. ona bi yumruk çakıyorum, kılıç yok daha", thing_word="yumruk")
        self.assert_attacked(reply)
        self.assertEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_a_mug_in_the_face_is_an_attack_with_no_sword_in_it(self):
        reply = await self.blow("suratına bira bardağını geçiriyorum", thing_word="bira bardağı")
        self.assert_attacked(reply)
        self.assertEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_a_thrown_mug_is_an_attack_too(self):
        reply = await self.blow("elimdeki bardağı adamın kafasına fırlatıyorum", thing_word="bardak")
        self.assert_attacked(reply)
        self.assertEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_a_swung_sword_is_an_attack_with_the_sword(self):
        reply = await self.blow("savuruyorum, omzuna")
        self.assert_attacked(reply)
        self.assertNotEqual(reply["combat_result"]["weapon"], "Unarmed Strike")

    async def test_a_reading_with_no_name_in_it_means_the_one_being_spoken_to(self):
        await self.begin()
        self.client.front = {"kind": "strike"}
        reply = await self.line("şuna bi tane patlatıyorum")
        self.assert_attacked(reply)

    async def test_a_question_about_a_blow_strikes_nobody(self):
        self.assert_no_blow(await self.blow("ona bi tane vursam ne olur?"))

    async def test_a_threat_strikes_nobody_and_is_said_to_them(self):
        reply = await self.blow("bi daha bana bakarsan suratını dağıtırım")
        self.assert_no_blow(reply)
        self.assertIn("Ne yapıyorsun sen?", reply["narration"])
        reply = await self.line("dişlerini sökerim senin")
        self.assert_no_blow(reply)

    async def test_a_refused_blow_strikes_nobody(self):
        self.assert_no_blow(await self.blow("hayır ona yumruk atmıyorum, gerek yok"))

    async def test_a_blow_only_quoted_strikes_nobody(self):
        self.assert_no_blow(await self.blow('"sana bi yumruk atıyorum" diyorum gülerek'))

    async def test_a_person_nobody_listed_is_struck_by_nobody(self):
        await self.begin()
        self.client.front = {"kind": "strike", "person_id": "npc_nobody"}
        reply = await self.line("şuna bi tane patlatıyorum")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack")

    async def test_the_reading_tells_the_model_what_a_blow_is(self):
        await self.begin()
        self.client.front = {"kind": "look"}
        await self.line("etrafa bakıyorum")
        self.assertIn("strike", self.front_calls()[0]["properties"]["front"]["properties"]["kind"]["enum"])
        self.assertIn("strike =", str(self.client.message_batches[0]))

    async def test_no_blow_is_left_behind_for_the_next_turn(self):
        await self.blow("ona bi yumruk çakıyorum, kılıç yok daha", thing_word="yumruk")
        self.assertFalse(getattr(self.session, "_front_strike", None))

"""Carius's fifth play, the turns that broke: the way out of town, the road on, coin, messengers, a punch, a fight's end.

Real app, real adapter, real engine; only the model client is scripted. The lines are the owner's own, as typed.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import bold_acts
import front_proposal
import local_places
import world_happenings
import world_threads
from api.tests import test_front_voice as voice
from api.tests.test_house_door import a_house
from api.tests.test_story_links import resident
from api.tests.test_world_keeps_its_word import FrontScene


class OneCoinOneTruth(FrontScene):
    async def at_the_bar(self):
        await self.begin()
        self.npc["role"] = "Barmen"
        self.world.setdefault("currency", {})["player"] = 2435

    def purse(self):
        return self.world["currency"]["player"]

    async def test_the_price_the_barman_says_is_the_price_the_purse_pays(self):
        await self.at_the_bar()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        await self.line("barmene bi bira söylüyorum, kaç para?", "Bira dört bakır.")
        price = dict((stem, cp) for stem, _, cp in bold_acts._PRICES)["bira"]
        self.assertIn(f"bira {price} bakır", str(self.client.message_batches[-1]))

    async def test_a_gold_thrown_with_keep_the_change_pays_that_gold_and_buys_no_beer(self):
        await self.at_the_bar()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 100}
        out = await self.line("bi altın atıyorum tezgaha, üstü kalsın, karşılığında biraz laf isterim. "
                              "mazduşa konağının sahibi kim biliyon mu", "Bilmem.")
        self.assertEqual(self.purse(), 2335, out["narration"])
        self.assertEqual(self.world["currency"][self.npc["id"]], 100)
        self.assertNotEqual(out["turn_outcome"]["action"], "purchase", out["narration"])

    async def test_a_beer_paid_with_a_gold_takes_the_gold_once(self):
        await self.at_the_bar()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 100}
        out = await self.line("bi bira ver, al şu bi altını, üstü kalsın", "Sağ ol.")
        self.assertEqual(self.purse(), 2335, out["narration"])
        self.assertIn("100", out["narration"])


class Fists(FrontScene):
    assert_attacked = voice.AnyBlowIsAnAttack.assert_attacked

    async def begin(self, **kwargs):
        await FrontScene.begin(self, **kwargs)
        self.npc.update(armor_class=10, max_hp=12, current_hp=12)


class APunchIsAPunch(Fists):
    async def scoff_then_fist(self, mode):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "strike_to": self.npc["id"],
                             "thing_word": "yumruk"}
        reply = await self.line("itemez miyim? sıkıp yumruğumu suratına bi tane çakıyorum", "Dene bakalım.", mode=mode)
        self.assert_attacked(reply)

    async def test_a_scoff_then_a_fist_lands_in_the_ui_default_do_mode(self):
        await self.scoff_then_fist("do")  # the browser sends 'do' for typed text unless the player picks another

    async def test_a_scoff_then_a_fist_lands_with_no_mode(self):
        await self.scoff_then_fist(None)

    async def test_a_question_after_the_blow_is_still_only_a_question(self):
        await self.begin()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "strike_to": self.npc["id"]}
        reply = await self.line("ona bi tane çaksam ne olur?", "Denemeni tavsiye etmem.", mode="do")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])


class TheFightLeavesThePlayerTheirOwnHands(Fists):
    async def in_a_fight(self):
        await self.begin()
        self.npc.update(current_hp=200, max_hp=200)
        self.session.character.update(max_hp=300, current_hp=300)
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"], "thing_word": "yumruk"}
        await self.line("düşündüm. yumrukla vuruyorum")
        self.assertTrue(self.world["combat"]["active"])
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}

    async def test_stepping_back_and_telling_them_to_go_is_no_walk_off(self):
        await self.in_a_fight()
        out = await self.line("geri çekilip ellerimi indiriyorum. yeter, kan dökmeyelim. al pılını pırtını çık git konaktan",
                              "Peki.")
        self.assertNotEqual(out["turn_outcome"]["status"], "fight_refused", out["narration"])
        self.assertNotIn("yürüyüp gidemezsin", out["narration"])

    async def test_ending_the_fight_says_nothing_the_player_did_not_do(self):
        await self.in_a_fight()
        with patch.object(self.session, "perform_skill_check", return_value={"result": "BAŞARILI", "total": 20}):
            out = await self.line("ona bağırıyorum: bırak o silahı, teslim ol, seni kahyaya teslim edicem")
        self.assertNotIn("Kılıcını", out["narration"])

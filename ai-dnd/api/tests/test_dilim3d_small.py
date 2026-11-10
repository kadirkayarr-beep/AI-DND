"""Dilim 3D Task 7: six small fixes from the 164-turn play (#15 #16 #14 #11 #9 #2d), each pinned."""

from __future__ import annotations

import unittest

import campaign_time
import game
import living_world
import local_dialogue
import npc_speech_boundary
import shop_trade
import truth_card
from api.serializers import serialize_session_state
from api.tests import test_front_proposal as front_tests
from api.tests.test_shop_counter import AtTheCounter
from api.tests.test_world_keeps_its_word import FrontScene
from api.tests.town_seed import fixed_town

Q137 = "I volunteer to lift a heavy crate from the floor onto the stall, carefully testing my Strength (Athletics) check."  # QA #137
Q046 = "I inspect the unfinished chest and the empty hook without touching them. I want to make an Investigation or Perception check."  # QA #046
Q004_SPEECH = ("“Benim adım yok, sadece bu kütüphanede çalışan biriyim. Kayıtları düzenleme işi mi? "
               "Evet, öyle bir ihtiyacım var.”")  # QA #004, from the speech
Q134 = ("I ask Mazduşa why his stall is piled with apples while his shop menu sells only beer, wine and cooked meals. "
        "Does he have any apples available to sell?")  # QA #134


class Table(FrontScene):
    """One real campaign on a pinned town (seed per class)."""
    SEED = 4561

    async def begin(self):
        with fixed_town(self, self.SEED):
            await front_tests.FrontTable.begin(self)


class EnglishFeatureText(Table):  # (a)
    SEED = 4561

    async def create(self, proposal):
        await self.begin()
        return self.session.create_local_feature({"location": self.world["location"], **proposal})

    async def test_english_feature_is_dropped(self):
        for proposal in ({"name": "Chest", "description": "An unfinished chest and an empty hook are on the workbench."},
                         {"name": "Notice", "description": "A sealed road-closure notice on the board."}):
            with self.subTest(name=proposal["name"]):
                self.assertIsNone(await self.create(proposal))

    async def test_turkish_feature_is_kept(self):
        self.assertIsNotNone(await self.create({"name": "Sandık", "description": "Tezgâhta yarım kalmış bir sandık."}))

    def test_reads_english_needs_no_turkish_letter_and_two_stop_words(self):
        self.assertTrue(game._reads_english("A chest on the bench"))
        self.assertFalse(game._reads_english("Tezgâhta the sandık"))
        self.assertFalse(game._reads_english("Masa"))
        self.assertFalse(game._reads_english("Meşe masa and"))


class StaleOpening(Table):  # (b)
    SEED = 4562

    def projection(self):
        return living_world.public_scene_projection(self.world, 0)

    async def opened(self):
        await self.begin()
        campaign_time.initialize(self.world)
        self.world["campaign_time"]["start_second"] = 9 * 3600
        living_world.set_scene_opening(self.world, self.world["location"], "Sabah güneşi sokağı ısıtıyor.", "calm",
                                       {"event_id": "e1", "variation_id": "v1"})

    async def test_opening_goes_when_the_period_changes(self):
        await self.opened()
        self.assertIsInstance(self.projection()["opening"], str)
        campaign_time.advance(self.world, 3600, "wait", "test")  # still the day period of the same day
        self.assertIsInstance(self.projection()["opening"], str)
        campaign_time.advance(self.world, 12 * 3600, "wait", "test")
        self.assertIsNone(self.projection()["opening"])

    async def test_opening_goes_with_the_next_day_in_the_same_period(self):
        await self.opened()
        campaign_time.advance(self.world, 24 * 3600, "wait", "test")
        self.assertIsNone(self.projection()["opening"])


class NamedSkill(unittest.TestCase):  # (c)
    def test_137_is_athletics(self):
        self.assertEqual(game.deterministic_check_for_action(Q137)["skill"], "Athletics")
        self.assertEqual(game.named_skill("Atletizm zarı atıyorum, sandığı kaldırıyorum"), "Athletics")

    def test_two_skills_or_no_check_word_is_no_override(self):
        self.assertIsNone(game.named_skill(Q046))
        self.assertIsNone(game.named_skill("I ask about the history of the town"))
        self.assertIsNone(game.named_skill("Athletics check mi gerekir?"))


class NoNameClaim(Table):  # (d)
    SEED = 4563

    def test_english_name_question(self):
        for line in ("What is your name?", "What's your name?", "Who are you?"):
            with self.subTest(line=line):
                self.assertEqual(local_dialogue.personal_question_kind(line), "npc_identity")

    def test_no_name_sentence_is_cut(self):
        out = npc_speech_boundary.without_no_name_claim(Q004_SPEECH)
        self.assertNotIn("adım yok", out)
        self.assertIn("Kayıtları düzenleme işi mi?", out)
        self.assertTrue(out.startswith("“") and out.endswith("”"), out)
        self.assertEqual(npc_speech_boundary.without_no_name_claim("“Adım Ovrak.”"), "“Adım Ovrak.”")
        self.assertEqual(npc_speech_boundary.without_no_name_claim("“Adım yok.”"), "")

    async def test_unknown_name_card_line(self):
        await self.begin()
        self.npc["name_known_to_player"] = False
        card = truth_card.npc_view(self.world, npc=self.npc)
        self.assertIn("Adını sorarlarsa söyleyebilir ya da kibarca geçebilirsin; adının olmadığını söyleme.", card)
        self.npc["name_known_to_player"] = True
        self.assertNotIn("adının olmadığını söyleme", truth_card.npc_view(self.world, npc=self.npc))


class SmallBundleTurns(AtTheCounter):  # (c)(e)(f)
    SEED = 4564

    async def begin(self):
        with fixed_town(self, self.SEED):
            await front_tests.FrontTable.begin(self)

    async def test_137_narration_says_athletics(self):
        await self.at_the_bar()
        narration = (await self.line(Q137))["narration"]
        self.assertNotIn("Akrobatik", narration)
        self.assertIn("Fiziksel çaban", narration)  # the Athletics line of the check result

    async def test_134_open_counter_is_not_closed(self):
        await self.at_the_bar()
        self.assertEqual(shop_trade.counter(self.world)["status"], "ready")
        narration = (await self.line(Q134))["narration"]
        self.assertNotIn("açık bir tezgâhı yok", narration)

    async def test_journal_lists_the_inn_counter_after_a_visit(self):
        await self.at_the_bar()
        place = self.world["location"]

        def counters():
            return [s for s in serialize_session_state(self.session)["shops"] if "counter" in s["tags"]]

        living_world.ensure_scene_state(self.world)["scenes"].get(place, {})["last_visit_turn"] = None
        self.assertEqual(counters(), [])
        living_world.record_scene_visit(self.world, place, 3)
        rows = counters()
        self.assertEqual([r["location"] for r in rows], [place])
        self.assertEqual(rows[0]["id"], f"counter:{place}")
        self.assertEqual(rows[0]["shopkeeper_id"], self.npc["id"])
        self.world.setdefault("shops", []).append({"id": "shop_x", "name": "Tezgâh", "location": place,
                                                   "description": "", "tags": [], "shopkeeper_id": self.npc["id"]})
        self.assertEqual(counters(), [])


if __name__ == "__main__":
    unittest.main()

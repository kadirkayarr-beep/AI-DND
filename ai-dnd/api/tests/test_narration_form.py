"""Dilim 3 Task 12: how a person's words, an open-air arrival, the world's gods and a recorded goal are told."""
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import game
import interaction_adventure as adventure
import campaign_time
import local_places
from api.tests import test_campaign_api as fixtures
from api.tests.test_interaction_adventure import envelope, npc as adventure_npc, session as adventure_session
from api.tests.town_seed import fixed_town

TOWN_SEED = 4201  # a new campaign's town comes from its id; pinned so the goal turn always meets the same town

WORLD_LINE = ("Faerûn'dasın: selam, dua ve yemin bu dünyanın tanrıları ve gelenekleriyle söylenir; "
              "gerçek dünyanın dinlerine ait sözler kullanılmaz.")


class SpeechForm(unittest.TestCase):
    def render(self, stage, spoken="Hoş geldin.", npc=None):
        payload = {"spoken_text": spoken, "stage_direction": stage}
        return game._render_experimental_npc_speech(payload, npc or {"id": "npc_kael", "name": "Kael"})

    def test_stage_reads_as_a_sentence_before_the_quote(self):
        self.assertEqual(self.render("çevresine bakıp gülümser", "Burada yaşamayı seviyorum."),
                         "Kael çevresine bakıp gülümser. “Burada yaşamayı seviyorum.”")

    def test_no_stage_keeps_the_colon_form(self):
        self.assertEqual(self.render(""), "Kael: “Hoş geldin.”")

    def test_stage_that_starts_with_the_name_loses_the_repeat(self):
        self.assertEqual(self.render("Kael, çevresine bakıp gülümser."), "Kael çevresine bakıp gülümser. “Hoş geldin.”")

    def test_another_actor_at_the_start_of_the_stage_stays_as_written(self):
        self.assertEqual(self.render("Rashid kapıya bakar."), "Kael Rashid kapıya bakar. “Hoş geldin.”")

    def test_unnamed_person_does_not_repeat_a_variant_of_the_label(self):
        npc = {"id": "n1", "name": "Zed", "name_known_to_player": False, "visible_trait": "mavi kuşaklı"}
        self.assertEqual(game.living_world.public_npc_name(npc), "Mavi kuşaklı biri")
        self.assertEqual(self.render("Mavi kuşaklı kişi, başını eğer", "Selam.", npc),
                         "Mavi kuşaklı biri başını eğer. “Selam.”")

    def test_unnamed_role_does_not_repeat_the_role_word(self):
        npc = {"id": "n2", "name": "Zed", "name_known_to_player": False, "role": "Muhafız"}
        self.assertEqual(game.living_world.public_npc_name(npc), "Bir muhafız")
        self.assertEqual(self.render("Muhafız kollarını göğsünde kavuşturup", "Aleykümselam.", npc),
                         "Bir muhafız kollarını göğsünde kavuşturup. “Aleykümselam.”")


def harbor_world():
    record = {"id": "p", "name": "Liman İskelesi", "place_kind": "harbor", "description": "Tuzlu rüzgâr."}
    return {"locations": {"p": record}, "npcs": [], "flags": {}}, record


def clocked(kind, name, hour):
    record = {"id": "p", "name": name, "place_kind": kind, "description": "Tarif."}
    world = {"locations": {"p": record}, "npcs": [], "flags": {}}
    campaign_time.initialize(world)
    world["campaign_time"]["start_second"] = hour * 3600
    return world, record


def back_after(world, record, seconds):
    local_places.arrival_text(world, record, None, None, first_visit=True)
    world["campaign_time"]["elapsed_seconds"] += seconds
    return local_places.arrival_text(world, record, None, None, first_visit=False)


class OpenAirClock(unittest.TestCase):
    def test_open_air_return_never_says_inside(self):
        for kind in ("harbor", "market", "graveyard"):
            for hour in (6, 12, 18, 22):
                with self.subTest(kind=kind, hour=hour):
                    world, record = clocked(kind, "Yer", hour)
                    text = back_after(world, record, 1800)
                    self.assertNotIn("içeri", text)
                    self.assertNotIn("içerisi", text)
                    self.assertTrue(text.startswith("Yeniden buradasın: Yer."), text)

    def test_open_air_return_line_is_the_period_line(self):
        world, record = clocked("harbor", "Yer", 22)
        self.assertIn("Gece olmuş; çevre karanlık ve sessiz.", back_after(world, record, 1800))

    def test_a_building_keeps_its_inside_period_line(self):
        world, record = clocked("smithy", "Demirhane", 22)
        self.assertIn("Gece olmuş; içerisi loş ve sessiz.", back_after(world, record, 1800))

    def test_first_visit_tells_the_period_after_the_description(self):
        world, record = clocked("graveyard", "Mezarlık", 18)
        text = local_places.arrival_text(world, record, None, None, first_visit=True)
        self.assertTrue(text.startswith("Mezarlık karşına çıkıyor. Tarif. Akşamın loşluğu çökmeye başlamış."), text)

    def test_first_visit_inside_a_building_uses_the_inside_line(self):
        world, record = clocked("smithy", "Demirhane", 6)
        self.assertIn("Tarif. Şafağın soluk ışığı içeri süzülüyor.",
                      local_places.arrival_text(world, record, None, None, first_visit=True))

    def test_short_return_and_outdoors_return_have_no_period_line(self):
        world, record = clocked("harbor", "Yer", 12)
        self.assertNotIn("Gün ışığı", back_after(world, record, 600))
        world, record = clocked("waystation", "Han Yolu", 12)
        self.assertNotIn("Gün ışığı", back_after(world, record, 7200))

    def test_no_clock_no_period_line(self):
        world, record = harbor_world()
        text = local_places.arrival_text(world, record, None, None, first_visit=True)
        self.assertEqual(text, "Liman İskelesi karşına çıkıyor. Tuzlu rüzgâr.")


class OpenAirArrival(unittest.TestCase):
    def test_open_air_kinds_are_the_three_the_owner_chose(self):
        flagged = {kind for kind, spec in local_places.PLACE_KINDS.items() if spec.get("open_air")}
        self.assertEqual(flagged, {"harbor", "market", "graveyard"})

    def test_first_visit_to_the_pier_is_reached_not_stepped_into(self):
        world, record = harbor_world()
        text = local_places.arrival_text(world, record, None, None, first_visit=True)
        self.assertTrue(text.startswith("Liman İskelesi karşına çıkıyor. Tuzlu rüzgâr."), text)
        self.assertNotIn("içeri adım atıyorsun", text)

    def test_second_visit_to_the_pier_is_not_inside_it(self):
        world, record = harbor_world()
        local_places.arrival_text(world, record, None, None, first_visit=True)
        text = local_places.arrival_text(world, record, None, None, first_visit=False)
        self.assertTrue(text.startswith("Yeniden buradasın: Liman İskelesi."), text)
        self.assertNotIn("içindesin", text)

    def test_a_building_keeps_its_inside_lines(self):
        record = {"id": "s", "name": "Demirhane", "place_kind": "smithy", "description": "İsli."}
        world = {"locations": {"s": record}, "npcs": [], "flags": {}}
        self.assertIn("içeri adım atıyorsun", local_places.arrival_text(world, record, None, None, first_visit=True))
        self.assertIn("Yeniden Demirhane içindesin",
                      local_places.arrival_text(world, record, None, None, first_visit=False))


class RecordedGoalLeavesTheTelling(unittest.TestCase):
    def test_goal_is_recorded_without_a_sentence_of_its_own(self):
        s = adventure_session()
        quote = "Hedefim bu sorunun peşine düşmek"
        result = adventure.resolve(s, quote, envelope("goal", quote), s.world_state["npcs"][0])
        self.assertEqual(result["status"], "recorded")
        self.assertIsNone(result["direct_response"])
        self.assertEqual(len(s.world_state[adventure.KEY]["threads"]), 1)
        self.assertEqual(s.world_state[adventure.KEY]["threads"][0]["title"], quote)


class GoalTurnStillTells(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    async def goal_turn(self, narration):
        with fixed_town(self, TOWN_SEED):
            campaign = await self.create_campaign()
        record = self.manager.get(campaign["session_id"])
        s = record.game_session
        s.world_state["locations"]["here"] = {"id": "here", "name": "Yerel oda", "type": "building",
                                            "reality_layer": "PROCEDURAL_LOCAL_FICTION"}
        s.world_state["location"] = "here"
        s.ensure_campaign_clock()
        s.world_state["npcs"] = [adventure_npc(location="here")]
        self.manager.save_campaign(campaign["campaign_id"])
        quote = "Hedefim bu gizemi çözmek"
        responses = [{"message": {"content": json.dumps({"intent": "dialogue",
                                                         "interaction": envelope("goal", quote)})}}]
        if narration is not None:
            responses.append({"message": {"content": json.dumps(narration)}})
        with patch("game.ollama.chat", side_effect=responses):
            response = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn",
                                            json={"message": quote, "target_id": "gromm", "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), s

    async def test_narrator_tells_a_recorded_goal(self):
        told = "Oda sessizleşiyor; gizemin ağırlığı havada asılı kalıyor."
        body, s = await self.goal_turn({"narration": told, "world_updates": {}, "lore_claims": []})
        self.assertEqual(body["narration"], told)
        self.assertEqual(len(s.world_state[adventure.KEY]["threads"]), 1)

    async def test_a_narrator_that_cannot_tell_it_still_leaves_a_line_and_the_record(self):
        body, s = await self.goal_turn({"narration": "The backend cannot access the canonical database.",
                                        "world_updates": {}, "lore_claims": []})
        self.assertTrue(body["narration"].strip())
        self.assertNotIn("backend", body["narration"])
        self.assertNotIn("peşini bırakmamaya", body["narration"])
        self.assertEqual(len(s.world_state[adventure.KEY]["threads"]), 1)


class WorldLineInPrompts(unittest.TestCase):
    def test_person_prompt_carries_the_world_line(self):
        self.assertIn(WORLD_LINE, game._SPEECH_ANSWER_RULES)

    def test_narrator_prompt_carries_the_world_line(self):
        self.assertIn(WORLD_LINE, game.NARRATOR_VOICE)


if __name__ == "__main__":
    unittest.main()

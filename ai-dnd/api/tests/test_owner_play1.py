"""The owner's first browser play (31 Oct 2026) pinned as regressions.

Every test replays the owner's own sentence, or the exact line the game showed.
The model is mocked, so these prove the deterministic path alone.
"""

from __future__ import annotations

import json
import unittest
import uuid
from unittest.mock import patch

import grounded_action
import living_world
import npc_statements
from api.tests import test_campaign_api
from api.tests import test_lr00_grounded_human as human
from api.tests.test_lr00_p1_intent import ProbeShapedClient
from api.tests.test_lr00_grounded_human import CITY, GARRICK, GARRICK_DOOR


class SpokenPlaceNames(unittest.TestCase):
    def names(self, line):
        return [item[0] for item in npc_statements._named_places(line)]

    def test_a_yes_before_the_name_is_not_part_of_the_name(self):
        self.assertEqual(self.names("Bir şey yok, sadece yolculuk. Evet, Veyra Hanı var."), ["Veyra Hanı"])

    def test_a_yes_without_a_comma_is_not_part_of_the_name(self):
        self.assertEqual(self.names("Evet Veyra Hanı var."), ["Veyra Hanı"])

    def test_two_places_in_a_list_stay_two_places(self):
        self.assertEqual(self.names("Kızıl Kule, Veyra Hanı ikisi de yakın."), ["Kızıl Kule", "Veyra Hanı"])

    def test_a_real_two_word_name_keeps_both_words(self):
        self.assertEqual(self.names("Tamam, Gümüş Kılıç Hanı burada."), ["Gümüş Kılıç Hanı"])


class OwnerPlayBase(unittest.IsolatedAsyncioTestCase):
    """The saved owner world, driven through the real HTTP turn with a mocked model."""

    asyncSetUp = human.HumanP6Regressions.asyncSetUp
    asyncTearDown = human.HumanP6Regressions.asyncTearDown
    world = human.HumanP6Regressions.world
    door = human.HumanP6Regressions.door
    turn = human.HumanP6Regressions.turn


class WanderingTheCity(OwnerPlayBase):
    def rumour(self, name):
        state = npc_statements.ensure(self.world)
        npc_statements._add_reference(
            self.world, state, npc_id="npc_001", name=name, noun="han", kind="tavern",
            claims=[], quote=f"{name} var.", turn=1, settlement=CITY,
        )

    async def test_wandering_after_leaving_does_not_walk_back_to_that_inn(self):
        self.world["location"] = GARRICK
        next(d for d in self.world["doors"] if d["id"] == GARRICK_DOOR).update(open=True, locked=False)
        state = npc_statements.ensure(self.world)
        state["references"].clear()
        self.rumour("Garrick Hanı")
        state["references"][-1].update(status="rumor", location_id=None)
        text, _ = await self.turn("handan çıkıyorum ve şehirde geziyorum")
        self.assertEqual(self.world["location"], CITY, text)
        self.assertNotIn("tabelasını", text)
        self.assertEqual(text.count("Garrick Hanı"), 1, text)  # only the leaving sentence
        self.assertNotEqual(grounded_action.near_door_id(self.world), GARRICK_DOOR, text)

    async def test_a_sign_seen_while_wandering_does_not_move_the_player_to_it(self):
        npc_statements.ensure(self.world)["statements"].clear()
        self.rumour("Mavi Kaz Hanı")
        text, _ = await self.turn("şehirde geziyorum")
        self.assertIn("Mavi Kaz Hanı tabelasını", text)
        self.assertNotIn("önüne geliyorsun", text)
        self.assertEqual(self.world["location"], CITY)
        self.assertIsNone(grounded_action.near_door_id(self.world), text)
        follow, _ = await self.turn("Oraya gidiyorum.")
        self.assertIn("Mavi Kaz Hanı", follow)

    async def test_a_new_place_found_wandering_is_named_once(self):
        npc_statements.ensure(self.world)["references"].clear()
        text, _ = await self.turn("şehirde geziyorum")
        self.assertNotIn("önüne çıkarıyor", text)
        self.assertEqual(text.count("önüne"), 1, text)


class AmbientEventsAreNotPeople(OwnerPlayBase):
    EVENT = "İki esnaf kısa bir tartışmaya tutuşur; biri avucunu tezgâha vurur."

    async def test_an_event_does_not_become_the_description_of_a_person(self):
        turn = self.world["flags"].get("turn_index", 0)
        scene = living_world.ensure_scene_record(self.world, CITY, turn)
        scene["materialized"] = True
        scene["referents"].clear()
        scene["last_beat"] = self.EVENT
        living_world.create_scene_referent(self.world, CITY, turn, description=self.EVENT, aliases=["esnaf"])
        await self.turn("Esnaf ile konuşmak istiyorum.")
        npc = next(n for n in self.world["npcs"] if n.get("role") == "Yolcu" and n.get("location") == CITY)
        self.assertNotIn("esnaf", npc.get("appearance", "").casefold())
        await self.turn("Konuşmayı bitiriyorum.")
        text, _ = await self.turn("etrafımı dikkatlice gözlemliyorum")
        self.assertLessEqual(text.count("İki esnaf"), 1, text)
        self.assertNotIn(": İki esnaf", text)

    async def test_a_feature_in_a_look_reads_as_a_sentence(self):
        scene_look = "Gözüne Ahşap masa çarpıyor"
        self.world["features"].append({"id": "f_table", "location": CITY, "name": "Ahşap masa", "kind": "furnishing"})
        text, _ = await self.turn("etrafımı dikkatlice gözlemliyorum")
        self.assertNotIn(scene_look, text)
        self.assertIn("Ahşap masa gözüne çarpıyor.", text)


class StrangersInTheBackground(OwnerPlayBase):
    async def test_the_narrator_is_told_a_background_event_belongs_to_strangers(self):
        scene = living_world.ensure_scene_record(self.world, CITY, 0)
        scene["materialized"] = True
        scene["last_beat"] = "Bir tüccar, müşterisiyle fiyat konusunda anlaşamıyor."
        context = json.loads(self.manager.get(self.session_id).game_session._living_world_prompt_context())
        self.assertEqual(context["recent_beat"], scene["last_beat"])
        self.assertIn("visible_npcs", context["recent_beat_actors"])

    async def test_a_quiet_scene_carries_no_such_note(self):
        scene = living_world.ensure_scene_record(self.world, CITY, 0)
        scene["materialized"] = True
        scene["last_beat"] = None
        context = json.loads(self.manager.get(self.session_id).game_session._living_world_prompt_context())
        self.assertNotIn("recent_beat_actors", context)


class EnteringAnAmbientEvent(OwnerPlayBase):
    EVENT = "İki esnaf kısa bir tartışmaya tutuşur; biri avucunu tezgâha vurur."

    def stage_event(self):
        turn = self.world["flags"].setdefault("turn_index", 0)
        self.instance = str(uuid.uuid4())
        scene = living_world.ensure_scene_record(self.world, CITY, turn)
        scene["materialized"] = True
        scene["referents"].clear()
        scene["last_beat"] = self.EVENT
        referent = living_world.create_scene_referent(
            self.world, CITY, turn, description=self.EVENT, aliases=["esnaf"], event_instance_id=self.instance,
        )
        scene["ambient_event"] = {
            "event_id": "city_small_argument", "instance_id": self.instance, "variation_id": "v1",
            "event_type": "BLUE", "repeat_group": "conversation", "count": 1, "referent_id": referent["id"],
        }

    async def act(self, action):
        url = self.turn_url.rsplit("/", 1)[0] + f"/ambient-events/{self.instance}/actions"
        response = await self.http.post(url, json={"action_id": str(uuid.uuid4()), "action": action})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["result"]

    async def test_joining_an_event_puts_the_player_in_front_of_someone_who_was_in_it(self):
        self.stage_event()
        result = await self.act("interact")
        self.assertEqual(result["status"], "APPLIED", result)
        npc = next(n for n in self.world["npcs"] if n["id"] == result["transition_id"])
        self.assertEqual(self.world["flags"].get("active_npc_id"), npc["id"])
        self.assertIn(self.EVENT, npc["personal_profile"]["current_activity"])
        text, _ = await self.turn("Yanlarına gidip ne olduğunu soruyorum.")
        self.assertNotIn("konuşabileceğin biri görünmüyor", text)
        self.assertTrue(text.strip())

    async def test_watching_an_event_tells_it_in_the_story(self):
        self.stage_event()
        await self.act("observe")
        text, _ = await self.turn("Bir süre durup çevremi gözlemliyorum.")
        self.assertIn("İki esnaf", text)


CARIUS = {
    "mode": "custom", "starting_level": 3,
    "level_choices": {"2": {}, "3": {"subclass_id": "champion"}},
    "name": "Carius", "species": "Human", "class": "Fighter", "background": "Soldier", "alignment": "True Neutral",
    "ability_score_method": "standard_array",
    "ability_scores": {"strength": 15, "constitution": 14, "dexterity": 13, "wisdom": 12, "intelligence": 10, "charisma": 8},
    "background_ability_bonuses": {"strength": 2, "constitution": 1},
    "proficient_skills": ["Athletics", "Intimidation", "Perception", "Insight", "History"],
    "species_bonus_skills": ["History"], "species_bonus_feat": "Tough",
    "fighting_style": "Defense", "equipment_package": "A", "background_equipment_option": "A",
    "languages": ["Common", "Dwarvish", "Giant"],
    "backstory": "Geç yirmili yaşlarda genç bir asker.",
}
START = {"character": CARIUS, "campaign_start": {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}}


class NewCampaign(unittest.IsolatedAsyncioTestCase):
    """A real new campaign, the way the owner started one."""

    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.client = ProbeShapedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        created = await self.http.post("/api/game/campaigns", json=START)
        self.assertEqual(created.status_code, 200, created.text)
        self.body = created.json()
        self.session_id = self.body["session_id"]

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    @property
    def world(self):
        return self.manager.get(self.session_id).game_session.world_state

    async def turn(self, message):
        self.client.message = message
        response = await self.http.post(
            f"/api/game/sessions/{self.session_id}/turn",
            json={"message": message, "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["narration"]

    async def test_who_is_here_on_the_first_turn_names_the_people_who_are_here(self):
        text = await self.turn("Burada kimler var?")
        self.assertNotIn("görünmüyor", text)
        people = [n for n in self.world["npcs"] if n.get("location") == self.world["location"]]
        self.assertTrue(people)

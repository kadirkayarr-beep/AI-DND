"""Campaign seeds vary the first scene; a saved scene keeps its people."""
import json
import unittest
import uuid
from unittest.mock import patch

import campaign_time
import game
import living_world
from api.tests import test_campaign_api as api
from api.tests.test_narration_evidence_acceptance import ask
from api.tests.test_stage10a_gameplay_repairs import city_session

CITY = "fr:city:neverwinter"
SEEDS = [f"tohum{index}" for index in range(16)]


def city_cast(seed):
    world = {"scene_state": {"campaign_seed": seed}}
    return living_world.scene_cast(world, CITY)


def cast_people(session):
    return [
        (npc["id"], npc["name"], npc["role"], npc["appearance"])
        for npc in session.world_state["npcs"] if npc.get("location") == CITY
    ]


class SeededCastTests(unittest.TestCase):
    def test_seeds_change_who_and_how_many(self):
        casts = [tuple(person[0] for person in city_cast(seed)) for seed in SEEDS]
        self.assertGreaterEqual(len(set(casts)), 8)
        self.assertEqual({1, 2, 3}, {len(cast) for cast in casts})
        self.assertGreater(len({role for cast in casts for role in cast}), 4)

    def test_the_same_seed_gives_the_same_cast(self):
        for seed in SEEDS:
            self.assertEqual(city_cast(seed), city_cast(seed))

    def test_no_seed_keeps_the_old_cast_for_saves_and_fixtures(self):
        self.assertEqual([person[0] for person in city_cast("")], ["Kent sakini", "Muhafız"])

    def test_tavern_keeper_is_not_always_warm(self):
        keepers = {living_world.tavern_keeper({"scene_state": {"campaign_seed": seed}}, "han")
                   for seed in SEEDS}
        self.assertGreaterEqual(len(keepers), 3)

    def test_observing_an_unchanged_scene_keeps_the_same_people(self):
        session = city_session()
        session.world_state.setdefault("scene_state", {})["campaign_seed"] = "tohum3"
        token = game._ACTIVE_SESSION.set(session)
        try:
            living_world.ensure_scene_state(session.world_state)["campaign_seed"] = "tohum3"
            materialize = lambda turn: living_world.materialize_scene(
                session.world_state, CITY, turn,
                create_npc=game.create_npc_from_ai, create_feature=game.create_local_feature,
            )
            materialize(0)
            first = cast_people(session)
            materialize(1)
            self.assertTrue(first)
            self.assertEqual(first, cast_people(session))
        finally:
            game._ACTIVE_SESSION.reset(token)


class SeededClockTests(unittest.TestCase):
    def test_first_hour_varies_and_stays_out_of_the_night(self):
        hours = set()
        for seed in SEEDS:
            world = {"locations": {CITY: {}}, "location": CITY}
            campaign_time.initialize(world)
            campaign_time.seed_start(world, seed)
            hours.add(campaign_time.public_time(world)["time_of_day"])
        self.assertEqual(hours, {"dawn", "day", "evening"})

    def test_a_running_or_anchored_clock_keeps_its_time(self):
        world = {"locations": {CITY: {}}, "location": CITY}
        campaign_time.initialize(world)
        world["campaign_time"]["elapsed_seconds"] = 60
        before = dict(world["campaign_time"])
        campaign_time.seed_start(world, "tohum1")
        self.assertEqual(world["campaign_time"], before)
        anchored = {"canonical_start_time": {"year": 1501, "month": "Kythorn", "day": 12, "hour": 18, "minute": 42}}
        campaign_time.initialize(anchored)
        before = dict(anchored["campaign_time"])
        campaign_time.seed_start(anchored, "tohum1")
        self.assertEqual(anchored["campaign_time"], before)


class NarrationNoteTests(unittest.TestCase):
    def test_prompt_names_the_last_opener_and_bars_invented_smells(self):
        session = city_session()
        session._living_world_prompt_context(player_input="Çevreme bakıyorum.")
        raw = {"narration": "Sokak sessiz.", "world_updates": {}, "lore_claims": []}
        previous = "Güneşin parlak ışıkları taş sokaklara vuruyor ve hava temiz."
        session.recent_dm_narrations = [previous]
        with patch("game.ollama.chat", return_value={"message": {"content": json.dumps(raw)}}) as chat:
            ask(session, [], "Çevreme bakıyorum.", narration_only=True, return_details=True,
                action_result={"action": "explore", "status": "observed", "success": True,
                               "direct_response": "Sokak görünür."})
        prompt = chat.call_args.kwargs["messages"][-1]["content"]
        self.assertIn("“Güneşin parlak ışıkları taş sokaklara”", prompt)
        self.assertIn("aynı kalıpla başlama", prompt)
        self.assertIn("koku", prompt)


class NewCampaignTests(unittest.IsolatedAsyncioTestCase):
    seeded_street = True
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown

    async def test_stored_metadata_and_opening_follow_the_seeded_hour(self):
        times = set()
        for _ in range(12):
            created = await self.http.post("/api/game/campaigns", json={"campaign_start": {
                "setting_id": "forgotten_realms",
                "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                "region_id": "fr:region:the_north",
                "starting_location_id": CITY,
            }})
            self.assertEqual(created.status_code, 200, created.text)
            session = self.manager.get(created.json()["session_id"]).game_session
            clock = campaign_time.public_time(session.world_state)
            self.assertEqual(session.world_metadata["time_of_day"], clock["time_of_day"])
            times.add(clock["time_of_day"])
        self.assertGreater(len(times), 1)

    async def test_first_look_shows_the_seeded_people_to_the_narrator(self):
        created = await self.http.post("/api/game/campaigns", json={"campaign_start": {
            "setting_id": "forgotten_realms",
            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
            "region_id": "fr:region:the_north",
            "starting_location_id": CITY,
        }})
        self.assertEqual(created.status_code, 200, created.text)
        sid = created.json()["session_id"]
        session = self.manager.get(sid).game_session
        client = api.CapturingConversationContextClient()
        with patch.object(self.app.state.ollama_adapter, "_client", client):
            turn = await self.http.post(f"/api/game/sessions/{sid}/turn", json={
                "message": "Çevremi gözlemliyorum.", "action_id": str(uuid.uuid4()),
            })
        self.assertEqual(turn.status_code, 200, turn.text)
        people = [npc for npc in session.world_state["npcs"] if npc.get("location") == CITY]
        self.assertTrue(people)
        roles = {person[0] for person in living_world.scene_cast(session.world_state, CITY)}
        self.assertEqual({npc["role"] for npc in people}, roles)
        self.assertIn(people[0]["appearance"], turn.json()["narration"])


class TurkishInitialTests(unittest.TestCase):
    def test_a_dotted_i_survives_in_a_label_and_in_prose(self):
        npc = {"id": "n", "role": "Kent sakini", "role_known_to_player": False,
               "name": "Nera", "name_known_to_player": False, "visible_trait": "iri yarı"}
        self.assertEqual(living_world.public_npc_descriptor(npc), "İri yarı biri")
        self.assertEqual(living_world.public_scene_people([npc]), "iri yarı biri")

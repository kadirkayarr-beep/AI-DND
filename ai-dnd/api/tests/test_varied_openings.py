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
from api.tests.test_natural_addressing import TownClient
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
    def test_first_hour_varies_and_finds_the_inn_open(self):
        # This pinned a dawn start, an hour before the inn opens at 07:00: the owner's first scene met a shut door.
        hours, periods = set(), set()
        for seed in SEEDS:
            world = {"locations": {CITY: {}}, "location": CITY}
            campaign_time.initialize(world)
            campaign_time.seed_start(world, seed)
            now = campaign_time.public_time(world)
            hours.add(now["hour"])
            periods.add(now["time_of_day"])
        self.assertGreaterEqual(min(hours), 7)
        self.assertGreaterEqual(len(hours), 4)
        self.assertEqual(periods, {"day", "evening"})

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
        self.assertTrue(any(people[0]["appearance"] in json.dumps(batch, ensure_ascii=False) for batch in client.message_batches))


    async def start(self):
        created = await self.http.post("/api/game/campaigns", json={"campaign_start": {
            "setting_id": "forgotten_realms",
            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
            "region_id": "fr:region:the_north",
            "starting_location_id": CITY,
        }})
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["session_id"], self.manager.get(created.json()["session_id"]).game_session

    async def post(self, sid, message):
        with patch.object(self.app.state.ollama_adapter, "_client", TownClient()):
            turn = await self.http.post(f"/api/game/sessions/{sid}/turn", json={
                "message": message, "action_id": str(uuid.uuid4()),
            })
        self.assertEqual(turn.status_code, 200, turn.text)
        return turn.json()["narration"]

    async def test_a_new_campaign_stores_a_seed_and_campaigns_differ_in_people_and_innkeeper(self):
        # The owner's first complaint: every game opening with the same two people. Compared across campaigns, not with the draw.
        casts, keepers = set(), set()
        for _ in range(12):
            sid, session = await self.start()
            await self.post(sid, "Çevremi gözlemliyorum.")
            world = session.world_state
            self.assertTrue(living_world.ensure_scene_state(world)["campaign_seed"])
            people = [npc for npc in world["npcs"] if npc.get("location") == CITY]
            self.assertTrue(1 <= len(people) <= 3, people)
            casts.add(frozenset(npc["role"] for npc in people))
            keepers.add(str(living_world.tavern_keeper(world, CITY)))
        self.assertGreaterEqual(len(casts), 2, casts)
        self.assertGreaterEqual(len(keepers), 2, keepers)

    async def lone_person(self):
        for _ in range(40):
            sid, session = await self.start()
            if len(living_world.scene_cast(session.world_state, CITY)) == 1:
                await self.post(sid, "Çevremi gözlemliyorum.")
                people = [npc for npc in session.world_state["npcs"] if npc.get("location") == CITY]
                self.assertEqual(len(people), 1)
                return sid, session, people[0]
        self.fail("no lone-person street in 40 draws")

    async def test_on_a_lone_person_street_a_typed_line_reaches_that_person(self):
        sid, session, person = await self.lone_person()
        shown = await self.post(sid, "Selam, buralarda yeni misin?")
        self.assertIn(TownClient.SPOKEN, shown)
        self.assertEqual(session.world_state["flags"]["active_npc_id"], person["id"])

    async def test_on_a_lone_person_street_the_inn_is_found_and_entered_through_its_door(self):
        sid, session, _ = await self.lone_person()
        shown = [
            await self.post(sid, message)
            for message in ("Bu çevrede bir han var mı?", "Tamam, oraya gidiyorum.", "Kapıyı açmaya çalışıyorum.")
        ]
        world = session.world_state
        inn = next(place for place in world["locations"].values() if place.get("scene_kind") == "tavern")
        self.assertIn(inn["name"], shown[0])
        self.assertEqual(world["location"], inn["id"], shown)


class TurkishInitialTests(unittest.TestCase):
    def test_a_dotted_i_survives_in_a_label_and_in_prose(self):
        npc = {"id": "n", "role": "Kent sakini", "role_known_to_player": False,
               "name": "Nera", "name_known_to_player": False, "visible_trait": "iri yarı"}
        self.assertEqual(living_world.public_npc_descriptor(npc), "İri yarı biri")
        self.assertEqual(living_world.public_scene_people([npc]), "iri yarı biri")

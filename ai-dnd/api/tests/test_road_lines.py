"""D-249 play fixes E4/E5/E6/E7: the road lines say what is true. A failed walk at the end of the road says the road
ends (and where the known settlement is); a front reading of go_to that names no listed place is a failed walk, never
a person to follow; leaving the caravan stop for the city's indoor places does not say "Dışarı"."""
import local_places
from api.tests.test_arrival_wiring import START, _ArrivalApi  # noqa: F401  (START re-exported for readers)

CITY = "fr:city:neverwinter"


class RoadLines(_ArrivalApi):
    TOWN_SEED = 4401  # a smithy is already in this town

    def make_road(self):
        world = self.session().world_state
        way = local_places.create_local_place(world, CITY, "waystation")
        grove = local_places.create_local_place(world, CITY, "grove")
        self.assertIsNotNone(way)
        self.assertIsNotNone(grove)
        return world, way, grove

    def stand_at(self, place_id):
        world = self.session().world_state
        world["location"] = place_id
        return world

    async def test_failed_travel_at_the_grove_says_the_road_ends(self):
        _world, _way, grove = self.make_road()
        self.stand_at(grove["id"])
        reply = await self.turn("Kasabaya git.", front={"kind": "go_to", "place_id": "fr:no:such:place"})
        self.assertEqual(reply.status_code, 200, reply.text)
        text = reply.json()["narration"]
        self.assertIn("Yol burada bitiyor", text)
        self.assertNotIn("sokak", text)
        self.assertNotIn("yolu bulamıyorsun", text)

    async def test_follow_the_road_is_travel_not_following_a_person(self):
        _world, _way, grove = self.make_road()
        self.stand_at(grove["id"])
        reply = await self.turn("Yolu takip ederek kasabanın meydanına gidiyorum.",
                                front={"kind": "go_to", "place_id": "fr:no:such:place"})
        self.assertEqual(reply.status_code, 200, reply.text)
        text = reply.json()["narration"]
        self.assertNotIn("izini kaybediyorsun", text)
        self.assertNotEqual(self.last_result()["action_result"].get("action"), "everyday")
        self.assertLessEqual(len(self.client.kinds), 2)

    async def test_from_the_caravan_stop_into_the_city_no_dışarı(self):
        world, way, _grove = self.make_road()
        smithy = self.place_of("smithy")
        self.stand_at(way["id"])
        reply = await self.turn(f"{world['locations'][smithy]['name']}ne yaklaşıyorum")
        self.assertEqual(reply.status_code, 200, reply.text)
        text = reply.json()["narration"]
        self.assertNotIn("Dışarı,", text)
        self.assertIn("sokaklarına giriyorsun", text)

    async def test_from_an_indoor_place_dışarı_stays(self):
        world, _way, _grove = self.make_road()
        smithy = self.place_of("smithy")
        second = local_places.create_local_place(world, CITY, "estate")
        self.assertIsNotNone(second)
        self.stand_at(smithy)
        reply = await self.turn(f"{second['name']}ne yaklaşıyorum")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertIn("Dışarı, Neverwinter sokaklarına çıkıyorsun.", reply.json()["narration"])

    async def test_failed_travel_inside_the_city_keeps_the_street_line(self):
        self.make_road()
        reply = await self.turn("Kasabaya git.", front={"kind": "go_to", "place_id": "fr:no:such:place"})
        self.assertEqual(reply.status_code, 200, reply.text)
        text = reply.json()["narration"]
        self.assertNotIn("Yol burada bitiyor", text)
        self.assertIn("Birkaç sokak dolaşıyorsun", text)

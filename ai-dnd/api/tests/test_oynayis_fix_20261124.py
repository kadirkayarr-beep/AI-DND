"""Play fixes of 2026-11-24 (six issues); every class pins the town (seed 4401: barracks, market, workshop, harbor, smithy)."""
from api.tests.test_arrival_wiring import _ArrivalApi

CITY = "fr:city:neverwinter"


class _Town(_ArrivalApi):
    TOWN_SEED = 4401

    def narration(self, reply):
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()["narration"]


class InnAgain(_Town):
    async def into_the_inn(self):
        world = self.session().world_state
        await self.turn("Köydeki tavernaya gidiyorum.", front={"kind": "go_to", "place_id": "kind:tavern"})
        inn = world["location"]
        self.assertNotEqual(inn, CITY)
        return inn

    async def test_a_walk_to_the_inn_in_the_inn_says_so(self):
        inn = await self.into_the_inn()
        world = self.session().world_state
        name = world["locations"][inn]["name"]
        reply = await self.turn("Hana gidiyorum.", front={"kind": "go_to", "place_id": "none"})
        text = self.narration(reply)
        self.assertIn(f"Zaten {name} içindesin.", text)
        self.assertEqual(world["location"], inn)

    async def test_the_list_of_known_places_keeps_every_place(self):
        world = self.session().world_state
        import grounded_places
        places = grounded_places._town_places(world)
        self.assertGreater(len(places), 4)
        text = grounded_places.known_places_question(self.session(), "Şuraya gidiyorum.")
        for rec in places.values():
            self.assertIn(rec["name"], text)

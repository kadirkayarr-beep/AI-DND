"""D-137 (YÜK-17): a fire that clears a room also carries the courtyard Yolcu's encounter outside.

The fire moved the living Yolcu out of the burning room, but the encounter record still named the room,
so the save check refused the turn and the whole wait (time, fire, news) was rolled back.
"""
import monster_sense
from api.tests.test_lasting_consequences import OneTownScene


class FireEvacuatesTheYolcu(OneTownScene):
    def light(self):
        import bold_acts
        from unittest.mock import patch
        with self.binding(), patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            bold_acts._burn(self.session)

    def live_world(self):
        return self.manager.get(self.session_id).game_session.world_state

    async def burning_room_with_the_yolcu(self):
        await self.town()
        self.world["location"] = "shop"
        begun = monster_sense.resolve_turn(self.session, "/encounter begin")
        self.assertTrue(begun["success"], begun)
        self.light()
        self.world["location"] = self.city

    async def test_the_wait_that_spreads_the_fire_is_kept(self):
        await self.burning_room_with_the_yolcu()
        out = await self.wait("yarım saat bekliyorum")
        world = self.live_world()
        fire = world["flags"]["fires"][0]
        self.assertEqual(fire["stage"], 1, out.get("narration"))
        yolcu = next(npc for npc in world["npcs"] if npc["id"] == monster_sense.NPC_ID)
        self.assertEqual(yolcu["location"], self.city)
        self.assertEqual(world[monster_sense.KEY]["location_id"], self.city)
        monster_sense.validate(world)

    async def test_outside_the_player_can_still_sense_the_yolcu(self):
        await self.burning_room_with_the_yolcu()
        await self.wait("yarım saat bekliyorum")
        session = self.manager.get(self.session_id).game_session
        view = monster_sense.resolve_turn(session, "/sense")
        self.assertTrue(view["success"], view)
        self.assertEqual(view["snapshot"]["targets"][0]["id"], monster_sense.NPC_ID)

    async def test_a_dead_yolcu_stays_where_it_fell(self):
        await self.burning_room_with_the_yolcu()
        yolcu = next(npc for npc in self.world["npcs"] if npc["id"] == monster_sense.NPC_ID)
        yolcu["combat_status"] = "dead"
        await self.wait("yarım saat bekliyorum")
        world = self.live_world()
        self.assertEqual(world["flags"]["fires"][0]["stage"], 1)
        self.assertEqual(world[monster_sense.KEY]["location_id"], "shop")
        monster_sense.validate(world)

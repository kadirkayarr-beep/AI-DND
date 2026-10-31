"""Doors and walking somewhere: what a plain line does, with no target and no special wording."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from api.tests.test_natural_addressing import TownCase
import campaign_time
import game
import grounded_action

HOUR = 3600


class DoorCase(TownCase):
    def set_hour(self, hour):
        clock = self.world["campaign_time"]
        clock["elapsed_seconds"] = (hour * HOUR - clock["start_second"]) % (24 * HOUR)
        self.assertEqual(campaign_time.public_time(self.world)["hour"], hour)

    async def find_inn(self):
        for npc in self.people:
            npc["location"] = "elsewhere"
        await self.say("Yakınlarda bir han arıyorum.")
        return next(r for r in self.world["locations"].values() if r.get("scene_kind") == "tavern")

    def door_of(self, place):
        return next(d for d in self.world["doors"] if d["id"] == f"venue-door:{place['id']}")


class AnInnIsNotALockedBox(DoorCase):
    async def test_the_first_inn_found_by_day_stands_open(self):
        door = self.door_of(await self.find_inn())
        self.assertTrue(door["open"])
        self.assertFalse(door["locked"])

    async def test_the_first_inn_found_at_the_morning_start_stands_open(self):
        self.set_hour(9)
        door = self.door_of(await self.find_inn())
        self.assertFalse(door["locked"])

    async def test_an_inn_named_by_a_person_stands_open_by_day(self):
        run = grounded_action._Run(self.session, "")
        record = grounded_action._create_venue(
            run, self.world["location"], name="Kızılhan", kind="tavern", provenance={"source": "test"},
        )
        door = self.door_of(record)
        self.assertTrue(door["open"])
        self.assertFalse(door["locked"])

    async def test_a_shop_found_in_its_hours_is_not_locked_by_chance(self):
        run = grounded_action._Run(self.session, "")
        for index in range(12):
            record = grounded_action._create_venue(
                run, self.world["location"], name=f"Dükkân {index}", kind="generic",
                noun="dukkan", provenance={"source": "test"},
            )
            self.assertFalse(self.door_of(record)["locked"])

    async def test_a_store_room_is_still_locked(self):
        run = grounded_action._Run(self.session, "")
        record = grounded_action._create_venue(
            run, self.world["location"], name="Eski Depo", kind="generic",
            noun="depo", provenance={"source": "test"},
        )
        self.assertTrue(self.door_of(record)["locked"])

    async def test_an_unreadable_clock_does_not_lock_the_inn(self):
        with patch.object(grounded_action, "_campaign_hour", return_value=None):
            state = grounded_action.public_door_state(self.world, "venue-door:x", "tavern")
        self.assertEqual(state, {"open": True, "locked": False})

    async def test_a_night_lock_lifts_when_the_inn_opens(self):
        self.set_hour(2)
        door = self.door_of(await self.find_inn())
        self.assertTrue(door["locked"])
        self.assertFalse(door["open"])
        self.set_hour(11)
        await self.say("Etrafa bakıyorum.")
        door = next(d for d in self.world["doors"] if d["id"] == door["id"])
        self.assertFalse(door["locked"])
        self.assertTrue(door["open"])

    async def test_a_lock_that_is_not_about_the_hours_stays(self):
        door = self.door_of(await self.find_inn())
        door.update(open=False, locked=True)
        self.set_hour(11)
        await self.say("Etrafa bakıyorum.")
        door = next(d for d in self.world["doors"] if d["id"] == door["id"])
        self.assertTrue(door["locked"])

    async def test_an_old_save_keeps_its_doors_when_opened(self):
        door = self.door_of(await self.find_inn())
        door.update(open=False, locked=True)
        self.world["grounded_actions"].pop("shut_for_hours", None)
        before = copy.deepcopy(self.world["doors"])
        grounded_action.reopen_public_doors(self.world)
        self.assertEqual(self.world["doors"], before)


class TryingADoorIsOpeningIt(DoorCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.inn = await self.find_inn()
        self.door = self.door_of(self.inn)
        grounded_action.note_near(self.world, self.door["id"])

    async def attempt(self, text="Kapıyı açmaya çalışıyorum."):
        rng_before = self.session.rng.getstate()
        data = await self.say(text)
        self.door = self.door_of(self.inn)
        return data, rng_before == self.session.rng.getstate()

    async def test_an_unlocked_door_opens_with_no_roll(self):
        self.door.update(open=False, locked=False)
        data, no_roll = await self.attempt()
        self.assertTrue(no_roll)
        self.assertTrue(self.door["open"])
        self.assertIn("açılıyor", data["narration"])

    async def test_a_locked_door_is_told_naturally_with_no_roll(self):
        self.door.update(open=False, locked=True)
        data, no_roll = await self.attempt()
        self.assertTrue(no_roll)
        self.assertFalse(self.door["open"])
        self.assertTrue(self.door["locked"])
        self.assertIn("kilitli", data["narration"])
        self.assertNotIn("deneyebilirsin", data["narration"])
        self.assertIn(self.door["id"], self.flags["known_locked_door_ids"])

    async def test_the_inn_door_by_its_noun_works_the_same(self):
        self.door.update(open=False, locked=False)
        await self.attempt("Hanın kapısını açmaya çalışıyorum.")
        self.assertTrue(self.door["open"])

    async def test_forcing_it_is_still_a_real_attempt(self):
        self.door.update(open=False, locked=True)
        _, no_roll = await self.attempt("Kapıyı zorlayarak açmaya çalışıyorum.")
        self.assertFalse(no_roll)


class TheDoorFromInside(DoorCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.inn = await self.find_inn()
        self.door = self.door_of(self.inn)
        await self.say("Hana giriyorum.")
        self.assertEqual(self.world["location"], self.inn["id"])

    async def test_opening_it_from_inside_finds_it(self):
        self.door_of(self.inn).update(open=False, locked=False)
        data = await self.say("Kapıyı açıyorum.")
        self.assertNotIn("görünmüyor", data["narration"])
        self.assertTrue(self.door_of(self.inn)["open"])

    async def test_trying_it_from_inside_finds_it(self):
        data = await self.say("Kapıyı açmaya çalışıyorum.")
        self.assertNotIn("görünmüyor", data["narration"])
        self.assertIn("açık", data["narration"])

    async def test_looking_at_it_from_inside_finds_it(self):
        data = await self.say("Kapıyı inceliyorum.")
        self.assertNotIn("göremiyorsun", data["narration"])

    async def test_a_remark_about_a_door_is_no_door_operation(self):
        data = await self.say("Kapı kilitliydi.")
        self.assertNotIn("açıp kapatabileceğin", data["narration"])


class AWalkDoesNotEndAtAClosedDoor(DoorCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.inn = await self.find_inn()
        self.door_of(self.inn).update(open=False, locked=False)

    async def test_going_to_the_inn_walks_in(self):
        data = await self.say("Tamam, hana gidiyorum.")
        self.assertEqual(self.world["location"], self.inn["id"])
        self.assertTrue(self.door_of(self.inn)["open"])
        self.assertNotIn("geçemezsin", data["narration"])

    async def test_going_by_name_walks_in(self):
        await self.say(f"{self.inn['name']}na gidiyorum.")
        self.assertEqual(self.world["location"], self.inn["id"])

    async def test_a_locked_door_stops_the_walk_in_plain_words(self):
        self.door_of(self.inn).update(open=False, locked=True)
        data = await self.say(f"{self.inn['name']}na gidiyorum.")
        self.assertNotEqual(self.world["location"], self.inn["id"])
        self.assertIn("kilitli", data["narration"])
        self.assertIn(self.door_of(self.inn)["id"], self.flags.get("known_locked_door_ids", []))

    async def test_timed_travel_to_a_closed_door_is_not_refused(self):
        self.assertIsNone(game._venue_entry_door(self.world, self.world["location"], self.inn["id"]))


class WhatAPersonSaidAboutAPlaceStands(DoorCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.say("Etrafa bakıyorum.")

    async def test_a_recommendation_is_not_rewritten(self):
        self.client.SPOKEN = "Kızılhan iyidir, meydanın hemen yanında."
        data = await self.say("Bana şehirde gidilecek başka bir yer öner.")
        self.assertIn("Kızılhan iyidir", data["narration"])
        self.assertNotIn("doğrula", data["narration"])
        references = self.world["npc_statements"]["references"]
        self.assertEqual([r["name"] for r in references], ["Kızılhan"])

    async def test_an_unnamed_recommendation_is_not_rewritten(self):
        self.client.SPOKEN = "Yakında bir han var, ucuzdur."
        data = await self.say("Bana şehirde gidilecek bir yer öner.")
        self.assertIn("ucuzdur", data["narration"])

    async def test_a_hidden_place_stays_out_of_the_mouth_without_system_words(self):
        self.world["locations"]["gizli"] = {
            "id": "gizli", "name": "Karanlıkhan", "type": "building", "hidden": True,
        }
        self.client.SPOKEN = "Karanlıkhan iyidir."
        data = await self.say("Bana şehirde gidilecek bir yer öner.")
        self.assertNotIn("Karanlıkhan", data["narration"])
        self.assertNotIn("doğrula", data["narration"])


if __name__ == "__main__":
    unittest.main()

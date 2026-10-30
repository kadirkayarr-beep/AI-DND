"""Doors and walking somewhere: what a plain line does, with no target and no special wording."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from api.tests.test_natural_addressing import TownCase
import campaign_time
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


if __name__ == "__main__":
    unittest.main()

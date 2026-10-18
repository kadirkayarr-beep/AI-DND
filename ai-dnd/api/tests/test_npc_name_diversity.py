"""NPC name diversity tests, written red-first.

Before the fix `living_world._stable_name` drew from a 16-name pool and ignored
the campaign seed, so different campaigns kept meeting the same NPC names.
The contract pinned here:

* no campaign seed -> byte-for-byte the legacy names (old saves and fixtures);
* a campaign seed -> deterministic per seed, but different across seeds, from a
  much larger pool;
* a name already used by a saved NPC is never reused, and saved NPCs are never
  renamed.
"""

from __future__ import annotations

import copy
import unittest

import living_world

LEGACY = {
    ("tavern", "Barmen", 1): "Elaris",
    ("tavern", "Barmen", 2): "Neris",
    ("tavern", "Barmen", 5): "Liora",
    ("tavern", "Kent sakini", 1): "Liora",
    ("fr:city:waterdeep", "Barmen", 1): "Elaris",
    ("fr:city:waterdeep", "Muhafız", 1): "Sylva",
    ("fr:city:neverwinter", "Kent sakini", 1): "Marek",
    ("fr:city:neverwinter", "Muhafız", 5): "Veyra",
}


def world(seed="", number=1, npcs=()):
    state = {"next_npc_number": number, "npcs": [dict(npc) for npc in npcs]}
    if seed is not None:
        state["scene_state"] = {"campaign_seed": seed}
    return state


class NpcNameDiversityTests(unittest.TestCase):
    def test_pool_is_large_unique_and_keeps_the_legacy_names_first(self):
        pool = living_world._LOCAL_NAMES
        self.assertGreaterEqual(len(pool), 80)
        self.assertEqual(len({name.casefold() for name in pool}), len(pool))
        self.assertEqual(
            pool[:16],
            ("Aldren", "Brynna", "Cael", "Darian", "Elaris", "Fenra", "Garrick",
             "Ilyra", "Kael", "Liora", "Marek", "Neris", "Orin", "Sylva",
             "Thalen", "Veyra"),
        )

    def test_without_a_campaign_seed_names_are_exactly_the_legacy_ones(self):
        for (location, role, number), expected in LEGACY.items():
            for seed_state in (world("", number), world(None, number)):
                self.assertEqual(
                    living_world._stable_name(seed_state, location, role),
                    expected,
                    (location, role, number),
                )

    def test_same_seed_gives_the_same_name(self):
        first = living_world._stable_name(world("a1b2c3"), "tavern", "Barmen")
        again = living_world._stable_name(world("a1b2c3"), "tavern", "Barmen")
        self.assertEqual(first, again)

    def test_different_campaign_seeds_do_not_keep_meeting_the_same_names(self):
        names = {
            living_world._stable_name(world(f"seed-{index:03d}"), "tavern", "Barmen")
            for index in range(60)
        }
        # A 16-name pool could never exceed 16 distinct values.
        self.assertGreater(len(names), 24, sorted(names))

    def test_seeded_names_are_not_all_inside_the_legacy_pool(self):
        legacy = set(living_world._LOCAL_NAMES[:16])
        names = {
            living_world._stable_name(world(f"seed-{index:03d}"), "tavern", "Barmen")
            for index in range(60)
        }
        self.assertTrue(names - legacy, "no new names are ever produced")

    def test_a_used_name_is_never_reused_and_saved_npcs_are_not_touched(self):
        npcs = [{"id": "npc_001", "name": "Elaris", "role": "Barmen"}]
        state = world("", 1, npcs)
        before = copy.deepcopy(state)
        name = living_world._stable_name(state, "tavern", "Barmen")
        self.assertNotEqual(name.casefold(), "elaris")
        self.assertEqual(state, before, "name selection must not mutate state")

        seeded = world("seed-007", 1, npcs)
        for _ in range(3):
            picked = living_world._stable_name(seeded, "tavern", "Barmen")
            self.assertNotEqual(picked.casefold(), "elaris")
            seeded["npcs"].append({"id": f"npc_{len(seeded['npcs']) + 1:03d}", "name": picked})

        all_names = [npc["name"].casefold() for npc in seeded["npcs"]]
        self.assertEqual(len(all_names), len(set(all_names)))

    def test_a_full_pool_still_returns_a_unique_numbered_name(self):
        state = world("seed-x")
        state["npcs"] = [
            {"name": name} for name in living_world._LOCAL_NAMES
        ]
        picked = living_world._stable_name(state, "tavern", "Barmen")
        self.assertNotIn(picked.casefold(), {n.casefold() for n in living_world._LOCAL_NAMES})

    def test_malformed_scene_state_falls_back_to_the_legacy_behaviour(self):
        for bad in (None, "x", [], {"campaign_seed": 5}, {"campaign_seed": None}):
            state = {"next_npc_number": 1, "npcs": [], "scene_state": bad}
            self.assertEqual(
                living_world._stable_name(state, "tavern", "Barmen"), "Elaris", bad
            )


if __name__ == "__main__":
    unittest.main()

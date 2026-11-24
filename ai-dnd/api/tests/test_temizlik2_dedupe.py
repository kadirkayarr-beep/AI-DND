"""Temizlik 2 G4: one shared turn reply, one shared level-3 subclass step, pay basis read only from the stored terms."""
from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import authored_dungeon
import bounded_encounter
import character_progression
import world_threads
from api.tests.test_world_threads import walled
from class_progression import fighter, monk, noncaster, rogue

BASES = {"daily", "total", "per_trip"}


class OneTurnReply(unittest.TestCase):
    def test_the_courtyard_and_the_dungeon_share_one_reply(self):
        self.assertIs(bounded_encounter._reply, authored_dungeon._reply)

    def test_the_reply_counts_one_turn_and_keeps_both_lines(self):
        session = SimpleNamespace(world_state={"flags": {"turn_index": 4}}, messages=[{"role": "user", "content": "önce"}])
        result = authored_dungeon._reply(session, "gir", "Girdin.", "dungeon_enter", room="hall")
        self.assertEqual(session.world_state["flags"]["turn_index"], 5)
        self.assertEqual(session.messages[1:], [{"role": "user", "content": "gir"}, {"role": "assistant", "content": "Girdin."}])
        self.assertEqual(result, {"messages": session.messages, "narration": "Girdin.", "model_calls": 0,
                                  "action_result": {"action": "dungeon_enter", "status": "resolved", "success": True,
                                                    "room": "hall"}})
        fresh = SimpleNamespace(world_state={"flags": {}}, messages=[])
        authored_dungeon._reply(fresh, "a", "b", "x")
        self.assertEqual(fresh.world_state["flags"]["turn_index"], 1)


class _Session:
    """Just the surface the level-3 step touches; the snapshot is a deep copy, as the real one restores whole state."""

    def __init__(self, character, combat_active=False):
        self.character = character
        self.world_state = {"inventory": [], "combat": {"active": combat_active}}
        self.synced = 0
        self.restored = False
        self.saved = 0

    def _capture_runtime_snapshot(self):
        return copy.deepcopy((self.character, self.world_state))

    def _restore_runtime_snapshot(self, snapshot):
        self.restored = True
        character, world = copy.deepcopy(snapshot)
        self.character.clear()
        self.character.update(character)
        self.world_state.clear()
        self.world_state.update(world)

    def _sync_combat_participant_records(self, combat):
        self.synced += 1

    def _player_state_for_save(self):
        self.saved += 1


def _character(cls):
    return {"class": cls, "level": 2, "progression_level": 2, "max_hp": 20, "current_hp": 15, "proficiency_bonus": 2}


def _preview(gain=7, already=False):
    return {"hit_points": {"gain": gain, "already_applied": already}, "effects_pending": ["later"]}


class OneSubclassStep(unittest.TestCase):
    def test_no_class_keeps_its_own_copy(self):
        for module in (fighter, monk, rogue):
            self.assertFalse(hasattr(module, "_apply_three"), module.__name__)

    def test_fighter_and_monk_apply_level_three_the_same_way(self):
        for module, cls in ((fighter, "Fighter"), (monk, "Monk")):
            session = _Session(_character(cls), combat_active=True)
            with patch.object(character_progression, "validate_saved") as validate:
                result = module.HANDLER.apply_level(session, {**_preview(), "to_level": 3}, {})
            validate.assert_called_once_with(session.character, session.world_state)
            self.assertEqual(result, {"status": "applied", "reason": None, "changes": [
                {"kind": "level", "from": 2, "to": 3}, {"kind": "hit_points", "gain": 7},
                {"kind": "subclass", "id": module.features.SUBCLASS}], "effects_pending": ["later"]})
            self.assertEqual((session.character["max_hp"], session.character["current_hp"]), (27, 22))
            self.assertEqual((session.character["level"], session.character["progression_level"]), (3, 3))
            self.assertEqual(session.character["subclass_id"], module.features.SUBCLASS)
            self.assertEqual((session.synced, session.saved, session.restored), (1, 1, False))

    def test_a_down_character_and_paid_hit_points_gain_nothing_now(self):
        session = _Session({**_character("Fighter"), "current_hp": 0})
        with patch.object(character_progression, "validate_saved"):
            result = fighter.HANDLER.apply_level(session, {**_preview(already=True), "to_level": 3}, {})
        self.assertEqual(result["changes"][1], {"kind": "hit_points", "gain": 0})
        self.assertEqual((session.character["max_hp"], session.character["current_hp"], session.synced), (20, 0, 0))

    def test_rogue_still_gets_its_tools_once(self):
        session = _Session({**_character("Rogue"), "proficient_tools": ["Thieves' Tools", "Disguise Kit"]})
        session.world_state["inventory"] = ["Disguise Kit"]
        with patch.object(character_progression, "validate_saved"):
            result = rogue.HANDLER.apply_level(session, {**_preview(), "to_level": 3}, {})
        self.assertEqual(result["status"], "applied")
        self.assertEqual(session.character["proficient_tools"], ["Thieves' Tools", "Disguise Kit", "Poisoner's Kit"])
        self.assertEqual(sorted(session.world_state["inventory"], key=str), ["Disguise Kit", "Poisoner's Kit"])

    def test_an_invalid_result_changes_nothing(self):
        for module, cls in ((fighter, "Fighter"), (monk, "Monk"), (rogue, "Rogue")):
            session = _Session(_character(cls))
            before = copy.deepcopy((session.character, session.world_state))
            with patch.object(character_progression, "validate_saved", side_effect=ValueError("bad")):
                result = module.HANDLER.apply_level(session, {**_preview(), "to_level": 3}, {})
            self.assertEqual(result, character_progression._reject("resulting_state_invalid"))
            self.assertTrue(session.restored)
            self.assertEqual((session.character, session.world_state), before, cls)

    def test_the_shared_step_lives_with_the_other_noncaster_steps(self):
        self.assertTrue(callable(noncaster.apply_subclass_step))


class PayBasisIsStored(unittest.TestCase):
    def test_every_new_job_thread_stores_how_it_pays(self):
        seen = set()
        for seed in ("seed-job", "seed-a", "seed-b", "seed-c"):
            for template in world_threads.catalog()["templates"]:
                if template["type"] not in {"errand", "hiring"}:
                    continue
                world, state = walled(seed)
                thread = world_threads._open_thread(world, state, template, "city", create=True, now=0)
                if thread is None:
                    continue
                expected = template.get("pay_basis") or {"errand": "per_trip", "hiring": "total"}[template["type"]]
                self.assertIn(thread["terms"]["pay_basis"], BASES, template["id"])
                self.assertEqual(thread["terms"]["pay_basis"], expected, template["id"])
                self.assertEqual(world_threads.pay_basis(thread), expected, template["id"])
                seen.add(template["id"])
        wanted = {t["id"] for t in world_threads.catalog()["templates"] if t["type"] in {"errand", "hiring"}}
        self.assertEqual(seen, wanted)

    def test_seeded_towns_store_it_on_every_paid_thread(self):
        for seed in ("seed-job", "seed-a", "seed-b", "seed-c", "seed-d"):
            _, state = walled(seed)
            for thread in state["threads"]:
                if thread["type"] in {"errand", "hiring"}:
                    self.assertIn(thread["terms"]["pay_basis"], BASES, thread["template_id"])

    def test_no_guess_from_the_kind_of_work(self):
        self.assertIsNone(world_threads.pay_basis({"type": "hiring", "template_id": "hand_wanted", "terms": {}}))
        self.assertIsNone(world_threads.pay_basis({"type": "errand", "terms": {}}))
        self.assertEqual(world_threads.pay_basis({"type": "hiring", "terms": {"pay_basis": "daily"}}), "daily")


if __name__ == "__main__":
    unittest.main()

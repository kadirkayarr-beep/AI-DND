"""P5T5-8: the travel branch of _narrate_resolved_turn commits a quest award through the forfeit boundary.

No other test drives travel -> GameSession.evaluate_quest_events -> _forfeit_unrecordable_xp through the narration
function (test_d060 calls evaluate_quest_events directly). This pins it before the function moves to its own part.
"""
from __future__ import annotations

import copy
import inspect
import unittest
from unittest.mock import patch

import game
import quest_catalog
from api.tests.test_d061_unrecorded_xp_line import _refuses_level_five
from api.tests.test_dilim4b_combat_xp import fighter

QUEST = {
    "quest_id": "quest.travel-xp",
    "title": "Road",
    "description": "Walk to the forest.",
    "objectives": [{"objective_id": "visit", "description": "Visit the forest",
                    "type": "visit_location", "target": "forest"}],
    "xp": 9000,
}


class TravelTurnForfeitPin(unittest.TestCase):
    def test_travel_turn_forfeits_a_refused_quest_award(self):
        with patch.object(quest_catalog, "CATALOG", (QUEST,)):
            session = game.create_session(seed=7101)
            fighter(session)
            session.character.update(level=4, xp=2700, max_hp=40, current_hp=40)
            session.world_state["locations"].setdefault("forest", {"name": "forest"})
            session.accept_quest("quest.travel-xp")
            before = copy.deepcopy(session.world_state)
            session.world_state["location"] = "forest"
            resolved = game.ResolvedTurn(
                action_result={"action": "travel", "status": "completed", "state_changes": []},
                fallback_response="Ormana vardın.", raw_result={},
                allow_new_locations=True, expected_location_change=True, quest_world_before=before,
            )
            packet = {"narration": "Ormana varırsın.", "valid_response": True, "world_updates": {}, "lore_claims": []}
            with patch.object(game, "ask_dungeon_master", return_value=packet), \
                    patch.object(game, "_validate_save_payload", _refuses_level_five):
                session._narrate_resolved_turn(resolved, "Ormana gidiyorum.", [], None)
        outcomes = resolved.action_result.get("quest_outcomes") or []
        self.assertEqual(outcomes[-1]["transition"], "completed")
        self.assertEqual((session.character["xp"], session.character["level"]), (2700, 4))
        self.assertNotIn("quest:quest.travel-xp", session.world_state["xp_awarded_event_ids"])
        self.assertEqual(len(session._take_xp_unrecorded()), 1)

    def test_narrate_resolved_turn_annotation_is_the_quoted_name(self):
        # Changed on purpose (Ruling T5 Step 2): game.py has no future import, so the
        # annotation was the class; it is now the quoted string. Introspection only.
        self.assertEqual(inspect.get_annotations(game._narrate_resolved_turn), {"resolved_turn": "ResolvedTurn"})


if __name__ == "__main__":
    unittest.main()

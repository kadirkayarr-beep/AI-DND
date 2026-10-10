"""E02 empty player projection and the save-load boundary."""

import copy
import unittest

import game
import incidents.projection as projection
from api.serializers import serialize_session_state
from api.tests.test_incident_models import _incident


def _public(session):
    state = serialize_session_state(session)
    return {key: state[key] for key in ("quests", "campaign_adventures")}


class IncidentProjectionTests(unittest.TestCase):
    def test_projection_is_empty_and_quest_surfaces_do_not_change(self):
        session = game.create_session(seed=7)
        before = _public(session)
        session.world_state["incidents"] = {"inc.one": _incident()}
        self.assertEqual(projection.scene_annotation(session.world_state), [])
        after = _public(session)
        self.assertEqual(after, before)
        self.assertNotIn("inc.one", repr(after))
        self.assertEqual(session.world_state["quests"], [])

    def test_engine_save_accepts_valid_and_refuses_corrupt_incidents(self):
        session = game.create_session(seed=8)
        session.world_state["incidents"] = {"inc.one": _incident()}
        payload = session.serialize_game_state()
        game._validate_save_payload(payload)
        for broken in ([], {"inc.one": _incident(lifecycle="PROPOSED")},
                       {"inc.x": _incident()}):
            corrupt = copy.deepcopy(payload)
            corrupt["world_state"]["incidents"] = broken
            with self.assertRaises(ValueError):
                game._validate_save_payload(corrupt)


if __name__ == "__main__":
    unittest.main()

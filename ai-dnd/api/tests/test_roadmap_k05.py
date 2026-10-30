"""K05: a reaction window is a durable pause that resumes exactly once.

Behaviour of the existing authoritative reaction owner (action_economy: Ready opportunity, react, decline_reaction) against
the plan's single-use conditions: nothing is spent before the player chooses, "use" spends once (a retry of the same window
is refused), "decline" spends nothing, a stale or invented window is refused without any state change, other actions stay
blocked while the window is open, a save/reload keeps the same window, and the pending projection exposes no hidden roll.
"""
from __future__ import annotations

import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import action_economy as ae
import game
from api.serializers import serialize_session_state
from api.tests.test_action_economy_reactions import interrupted
from api.tests.test_campaign_time import scene
from combat_lifecycle import CombatRequestError


def choose(session, kind, identity):
    return session.run_player_turn("Hamle.", combat_action={"steps": [{"kind": kind, "opportunity_id": identity}]})


class ReactionSingleUseTests(unittest.TestCase):
    def test_reaction_resume_is_single_use(self):
        session = scene()
        npcs, identity = interrupted(session, "attack")
        player = ae.ensure(session)["player"]
        spends = {"count": 0}
        real_attack = session.resolve_attack

        def counted(*args, **kwargs):
            if kwargs.get("origin") == "reaction":
                spends["count"] += 1
            return real_attack(*args, **kwargs)

        pending_projection = json.dumps(serialize_session_state(session), default=str)
        self.assertIn(identity, pending_projection, "control: the projection really contains the open window")
        obs = {"resource_spent_before_choice": int(player["reaction_spent"])}
        with patch.object(session, "resolve_attack", counted), patch("game.roll_d20", return_value=1), \
                patch("game.roll_damage", return_value=1):
            choose(session, "react", identity)
            with self.assertRaises(CombatRequestError):  # the retry of the SAME window
                choose(session, "react", identity)
        obs["used_choice_total_spend_after_retry"] = spends["count"]

        declined_session = scene()
        _, declined_id = interrupted(declined_session, "attack")
        declined_spends = {"count": 0}
        real_declined = declined_session.resolve_attack

        def counted_declined(*args, **kwargs):
            if kwargs.get("origin") == "reaction":
                declined_spends["count"] += 1
            return real_declined(*args, **kwargs)

        with patch.object(declined_session, "resolve_attack", counted_declined), patch("game.roll_d20", return_value=1), \
                patch("game.roll_damage", return_value=1):
            choose(declined_session, "decline_reaction", declined_id)
        obs["declined_choice_spend"] = declined_spends["count"]
        leak_pattern = r'"[a-z_]*(?:attack_total|attack_roll|total_roll|roll_total|raw_roll)[a-z_]*"'
        self.assertTrue(re.search(leak_pattern, '{"attack_total": 17}'), "control: the leak pattern can match")
        # weapon_sequence.attack_rolls is a per-turn count of attacks, not a roll value.
        without_attack_count = re.sub(r'"attack_rolls": \d+(?=[,}])', '', pending_projection)
        self.assertNotRegex(without_attack_count, r'"attack_rolls": "')
        obs["hidden_attack_total_disclosed"] = bool(re.search(leak_pattern, without_attack_count))

        self.assertEqual(obs["resource_spent_before_choice"], 0)
        self.assertEqual(obs["used_choice_total_spend_after_retry"], 1)
        self.assertEqual(obs["declined_choice_spend"], 0)
        self.assertIs(obs["hidden_attack_total_disclosed"], False)

    def test_a_stale_or_invented_window_is_refused_without_any_state_change(self):
        session = scene()
        npcs, identity = interrupted(session, "attack")
        before = copy.deepcopy(session.serialize_game_state())
        for kind in ("react", "decline_reaction"):
            with self.assertRaises(CombatRequestError):
                choose(session, kind, "not-the-open-window")
        self.assertEqual(session.serialize_game_state(), before)
        with patch("game.roll_d20", return_value=1), patch("game.roll_damage", return_value=1):
            choose(session, "decline_reaction", identity)
        with self.assertRaises(CombatRequestError):
            choose(session, "decline_reaction", identity)  # the closed window is stale

    def test_other_actions_stay_blocked_while_the_window_is_open_and_nothing_is_spent(self):
        session = scene()
        npcs, identity = interrupted(session, "attack")
        before = copy.deepcopy(session.serialize_game_state())
        with self.assertRaises(CombatRequestError) as caught:
            session.run_player_turn("Hamle.", combat_action={"steps": [{"kind": "move", "distance_ft": 5}]})
        self.assertEqual(caught.exception.code, "reaction_pending")
        self.assertEqual(session.serialize_game_state(), before)
        self.assertFalse(ae.ensure(session)["player"]["reaction_spent"])

    def test_an_interrupted_window_does_not_outlive_its_combat(self):
        # Interruption branch: when combat ends with a window still open, no stale window may stay in the saved truth.
        session = scene()
        npcs, identity = interrupted(session, "attack")
        session.end_combat("test_interruption")
        saved = json.dumps(session.serialize_game_state(), default=str)
        self.assertNotIn(identity, saved, "a closed combat must not keep its reaction window in the saved state")
        self.assertFalse(ae.pending_reaction(session))

    def test_the_same_window_survives_save_and_reload_and_is_still_single_use(self):
        session = scene()
        npcs, identity = interrupted(session, "attack")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            path.write_text(json.dumps(session.serialize_game_state(), ensure_ascii=False), encoding="utf-8")
            reloaded = scene()
            reloaded.load_game(str(path))
        reopened = ae.ensure(reloaded)["player"]["opportunity"]
        self.assertIsNotNone(reopened, "the reaction window is part of the saved truth")
        self.assertEqual(reopened["id"], identity)
        with patch("game.roll_d20", return_value=1), patch("game.roll_damage", return_value=1):
            choose(reloaded, "decline_reaction", identity)
        with self.assertRaises(CombatRequestError):
            choose(reloaded, "decline_reaction", identity)


if __name__ == "__main__":
    unittest.main()

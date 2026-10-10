"""Gate B: silence, commit, ignore, awareness, props, micro-locations, hook."""

import json
import unittest
from unittest.mock import patch

import game
from api import ollama_adapter
from api.serializers import serialize_session_state
from api.tests.test_incident_gate_a import PROFILE, _decisions, _envelope, _proposal, _world
from api.tests.test_incident_models import _incident
from incidents import awareness, commit, gate, hooks, projection, triggers
from incidents.attempts import MemoryAttemptStore

LIVE_PROFILE = {
    **PROFILE,
    "silence_rate": 0.0,
    "category_weights": (("disturbance", 1),),
    "reward_weights": (("none", 1),),
}
SILENT_PROFILE = {**LIVE_PROFILE, "silence_rate": 1.0}


def _propose(data):
    raw = json.dumps(_proposal(**data) if isinstance(data, dict) else data, ensure_ascii=False)
    return lambda packet: raw


class SilenceAndTriggerTests(unittest.TestCase):
    def test_ordinary_inn_can_return_no_incident(self):
        _, world = _world()
        world["campaign_id"] = "campaign.test"
        trigger = {"kind": "arrival", "location_id": "tavern"}
        self.assertIsNone(triggers.select(
            world, campaign_id="campaign.test", trigger=trigger, profile=SILENT_PROFILE))
        self.assertIsNone(triggers.select(
            world, campaign_id="campaign.test", trigger=trigger, profile=None))
        self.assertEqual(world.get("incidents", {}), {})

    def test_look_around_is_in_horizon_and_travel_is_arrival(self):
        _, world = _world()
        self.assertEqual(
            triggers.detect(world, action_result={"action": "travel", "success": True},
                            player_text="", location_changed=True)["kind"],
            "arrival",
        )
        self.assertEqual(
            triggers.detect(world, action_result={"action": "look"},
                            player_text="Etrafında neler oluyor?", location_changed=False)["kind"],
            "look_around",
        )
        self.assertIsNone(triggers.detect(
            world, action_result={"action": "wait"}, player_text="bekliyorum", location_changed=False))


class CommitAndLifecycleTests(unittest.TestCase):
    def test_commit_is_idempotent_and_not_a_quest(self):
        _, world = _world()
        world["campaign_id"] = "campaign.test"
        built = _envelope(world, reward="none")
        normalized = gate.evaluate(built, _proposal()).normalized
        first = commit.commit(world, built, normalized)
        second = commit.commit(world, built, normalized)
        self.assertEqual(first, second)
        self.assertEqual(len(world["incidents"]), 1)
        row = world["incidents"][first]
        self.assertEqual(row["lifecycle"], "PRESENT")
        self.assertEqual(row["trigger_id"], built["trigger_id"])
        self.assertEqual(world["quests"], [])
        self.assertTrue(awareness.noticed(world, first))
        self.assertIn("f.s1", awareness.known_fact_ids(world, first))
        self.assertNotIn("f.h1", awareness.known_fact_ids(world, first))

    def test_scene_exit_ignores_and_clock_expires(self):
        _, world = _world()
        world["campaign_id"] = "campaign.test"
        built = _envelope(world, reward="none")
        incident_id = commit.commit(world, built, gate.evaluate(built, _proposal()).normalized)
        world["location"] = "forest"
        changed = commit.advance(world, before_location="tavern")
        self.assertEqual(changed, [incident_id])
        self.assertEqual(world["incidents"][incident_id]["lifecycle"], "IGNORED")
        self.assertEqual(world["incidents"][incident_id]["details"]["props"], {})
        self.assertEqual(world["quests"], [])

        world["location"] = "tavern"
        still = _incident("inc.ttl", expiry_clock=0, location_id="tavern")
        world["incidents"][still["incident_id"]] = still
        expired = commit.advance(world, before_location="tavern")
        self.assertIn("inc.ttl", expired)
        self.assertEqual(world["incidents"]["inc.ttl"]["lifecycle"], "EXPIRED")


class AwarenessAndProjectionTests(unittest.TestCase):
    def test_hidden_fact_stays_off_player_surfaces_until_a_check(self):
        session, world = _world()
        row = _incident()
        world["incidents"] = {row["incident_id"]: row}
        world["location"] = "tavern"
        awareness.witness(world, row)
        shown = projection.scene_annotation(world)
        self.assertEqual(len(shown), 1)
        blob = json.dumps(shown, ensure_ascii=False)
        self.assertIn("A small leather purse", blob)
        self.assertNotIn("belongs to the cook", blob)
        self.assertNotIn("HIDDEN", blob)
        self.assertNotIn("PRESENT", blob)
        self.assertNotIn("fact.owner", blob)
        public = serialize_session_state(session)
        self.assertEqual(public["quests"], [])
        self.assertNotIn("belongs to the cook", json.dumps(public, ensure_ascii=False))
        self.assertEqual(public["scene_incidents"][0]["summary"], shown[0]["summary"])

        awareness.reveal(world, row, "fact.owner", evidence={"kind": "guess", "text": "Bu aşçının kesesi"})
        self.assertNotIn("fact.owner", awareness.known_fact_ids(world, row["incident_id"]))
        awareness.reveal_from_check(world, {
            "action": "skill_check", "success": True, "skill": "Investigation"})
        self.assertIn("fact.owner", awareness.known_fact_ids(world, row["incident_id"]))
        shown = projection.scene_annotation(world)
        self.assertIn("belongs to the cook", json.dumps(shown, ensure_ascii=False))

    def test_unnoticed_incident_is_absent_from_packet_and_state(self):
        session, world = _world()
        world["incidents"] = {"inc.one": _incident()}
        self.assertEqual(projection.scene_annotation(world), [])
        public = serialize_session_state(session)
        self.assertEqual(public["scene_incidents"], [])
        self.assertEqual(public["quests"], [])


class PropAndPlaceTests(unittest.TestCase):
    def test_props_and_subscenes_stay_ephemeral(self):
        _, world = _world()
        world["campaign_id"] = "campaign.test"
        built = _envelope(world, reward="none")
        data = _proposal(subscene={"label": "back alley", "kind": "alley",
                                   "description": "A narrow passage behind the inn."})
        incident_id = commit.commit(world, built, gate.evaluate(built, data).normalized)
        row = world["incidents"][incident_id]
        self.assertEqual(list(row["details"]["props"].values())[0]["state"], "scene")
        self.assertIsNone(list(row["details"]["props"].values())[0]["promoted_ref"])
        self.assertEqual(row["details"]["subscene"]["kind"], "alley")
        self.assertIsNone(row["details"]["subscene"]["promoted_location_id"])
        self.assertNotIn(row["details"]["subscene"]["label"], world["locations"])
        inventory = world.get("inventory", [])
        self.assertNotIn("crate", json.dumps(inventory, ensure_ascii=False))
        shown = projection.scene_annotation(world)[0]
        self.assertIn("İncele: crate", shown["affordances"])
        self.assertEqual(shown["place"], "back alley")


class HookTests(unittest.TestCase):
    def test_fake_proposal_commits_once_and_reject_stays_quiet(self):
        session, world = _world()
        world["campaign_id"] = "campaign.test"
        session.emergence_store = MemoryAttemptStore()
        calls = {"n": 0}

        def propose(_packet):
            calls["n"] += 1
            return json.dumps(_proposal(), ensure_ascii=False)

        with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls():
            with patch("incidents.profiles.resolve", return_value=LIVE_PROFILE):
                result = hooks.before_narration(
                    session, action_result={"action": "travel", "success": True},
                    player_text="tavernaya gidiyorum", location_changed=True, propose=propose,
                )
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(len(world["incidents"]), 1)
        self.assertEqual(world["quests"], [])

        with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls():
            with patch("incidents.profiles.resolve", return_value=LIVE_PROFILE):
                again = hooks.before_narration(
                    session, action_result={"action": "travel", "success": True},
                    player_text="tavernaya gidiyorum", location_changed=True, propose=propose,
                )
        self.assertIsNone(again["status"])
        self.assertEqual(calls["n"], 1)

        session2, world2 = _world()
        world2["campaign_id"] = "campaign.reject"
        session2.emergence_store = MemoryAttemptStore()
        bad = _proposal(category="not_a_category")
        with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls():
            with patch("incidents.profiles.resolve", return_value=LIVE_PROFILE):
                rejected = hooks.before_narration(
                    session2, action_result={"action": "travel", "success": True},
                    player_text="etrafıma bakıyorum", location_changed=True,
                    propose=_propose(bad),
                )
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(world2.get("incidents", {}), {})
        self.assertEqual(world2["quests"], [])

    def test_after_turn_reveals_from_a_real_check(self):
        session, world = _world()
        row = _incident()
        world["incidents"] = {row["incident_id"]: row}
        awareness.witness(world, row)
        hooks.after_turn(session, {"location": "tavern"}, {
            "action": "skill_check", "success": True, "skill": "perception"})
        self.assertIn("fact.owner", awareness.known_fact_ids(world, row["incident_id"]))


if __name__ == "__main__":
    unittest.main()

"""Neverwinter NPC continuity through the existing owners and SQLite."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import campaign_time
import game
import living_world
import relationships
from api import ollama_adapter
from api.lore_authority.campaign_state import EngineActionEvidence
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.test_incident_gate_a import _decisions, _proposal
from incidents import bridge, commit, envelope, gate, generator, hooks, horizon, possibilities, profiles, projection, rewards, rng, triggers

START = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}
SECRET = "The crate was kicked over on purpose."


class TriggerCoverageTests(unittest.TestCase):
    def test_arrival_and_look_fire_and_the_city_chatter_does_not(self):
        session = game.create_session(seed=3)
        world = session.world_state
        world["location"] = "fr:city:neverwinter"
        world.setdefault("locations", {})["fr:city:neverwinter"] = {
            "name": "Neverwinter", "type": "city",
        }
        arrival = triggers.detect(
            world, action_result={"action": "travel", "success": True},
            player_text="hana yürüdüm", location_changed=True,
        )
        look = triggers.detect(
            world, action_result={"action": "look", "success": True},
            player_text="etrafa bakıyorum", location_changed=False,
        )
        chatter = triggers.detect(
            world, action_result={"action": "narrative", "success": True},
            player_text="Etrafımda şu an ne görüyorum, kısaca anlat.",
            location_changed=False,
        )
        self.assertEqual(arrival["kind"], "arrival")
        self.assertEqual(look["kind"], "look_around")
        self.assertIsNone(chatter)
        self.assertTrue(horizon.in_horizon(world, arrival))
        self.assertTrue(horizon.in_horizon(world, look))
        self.assertEqual(profiles.resolve(world, "fr:city:neverwinter")["profile_id"], "neverwinter.v1")


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "campaigns.sqlite3"
        self.manager = SessionManager(campaign_store=CampaignStore(self.path))
        self.campaign_id, _, self.record, _ = self.manager.create_campaign(
            "Continuity", campaign_start=START,
        )
        self.session = self.record.game_session
        self.world = self.session.world_state
        self.location = self.world["location"]
        self.quests = copy.deepcopy(self.world.get("quests", []))

    def test_talk_promotes_once_and_the_same_npc_is_there_days_later(self):
        self.assertEqual(self.location, "fr:city:neverwinter")
        profile = profiles.resolve(self.world, self.location)
        self.assertEqual(profile["review_status"], "VERIFIED_PARTIAL")
        built = envelope.build(
            self.world, campaign_id=self.campaign_id,
            trigger_id=envelope.trigger_id_for(
                self.world, trigger_kind="arrival", location_id=self.location,
            ),
            trigger_kind="arrival", location_id=self.location, profile=profile,
            decisions=_decisions("none"),
            hidden_context={"fact.secret": SECRET},
            faction_ids=list(profile["faction_ids"]),
        )
        proposal = _proposal(
            people=[{
                "label": "telaşlı aşçı", "role": "cook", "name": "Mirel",
                "traits": ["anxious"], "backstory": "Gece vardiyasında çalışır.",
            }],
            hidden_facts=[SECRET],
            surface_facts=["Elmalar tahtalara yuvarlanmış."],
            existing_refs=[],
        )
        result = gate.evaluate(built, proposal)
        self.assertIn(result.outcome, (gate.ACCEPT, gate.NORMALIZE))
        incident_id = commit.commit(self.world, built, result.normalized)
        record = self.world["incidents"][incident_id]
        person_id = next(iter(record["details"]["people"]))
        self.assertEqual(record["details"]["people"][person_id]["state"], "passerby")
        self.assertNotIn(SECRET, json.dumps(projection.scene_annotation(self.world), ensure_ascii=False))

        ignored = {"action": "look", "success": True, "state_changes": []}
        hooks.before_narration(
            self.session, action_result=ignored, player_text="etrafa bakıyorum",
            location_changed=False, propose=lambda packet: self.fail("look called the model"),
        )
        hooks.after_turn(self.session, {"location": self.location}, ignored)
        self.assertEqual(record["details"]["people"][person_id]["state"], "passerby")

        talk = {"action": "narrative", "success": True, "state_changes": []}
        with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls() as calls:
            status = hooks.before_narration(
                self.session, action_result=talk, player_text="Konuş: telaşlı aşçı",
                location_changed=False, propose=lambda packet: self.fail("talk called the model"),
            )
            hooks.after_turn(self.session, {"location": self.location}, talk)
        self.assertEqual(status["model_calls"], 0)
        self.assertEqual(calls, [])
        self.assertEqual(record["details"]["people"][person_id]["state"], "promoted")
        npc_id = record["details"]["people"][person_id]["npc_id"]
        npc = next(row for row in self.world["npcs"] if row.get("id") == npc_id)
        self.assertEqual(npc["name"], "Mirel")
        self.assertIn("anxious", npc.get("personality", ""))
        self.assertEqual(relationships.score(self.world, npc_id), 1)
        self.assertEqual(npc.get("relationship"), "neutral")
        self.assertNotIn("Mirel", living_world.public_npc_name(npc))
        self.assertEqual(self.world.get("quests", []), self.quests)
        shown = json.dumps(projection.scene_annotation(self.world), ensure_ascii=False)
        self.assertNotIn(SECRET, shown)
        self.assertNotIn("talk:", shown)

        self.manager.save_campaign(self.campaign_id)
        with self.manager._registry_lock:
            session_id = self.manager._campaign_sessions.pop(self.campaign_id)
            del self.manager._sessions[session_id]
        _, resumed, _, _, _ = self.manager.resume_campaign(self.campaign_id)
        loaded = resumed.game_session.world_state
        loaded_npc = next(row for row in loaded["npcs"] if row.get("id") == npc_id)
        self.assertEqual(loaded_npc["name"], "Mirel")
        self.assertEqual(loaded_npc["location"], self.location)
        self.assertEqual(relationships.score(loaded, npc_id), 1)
        self.assertIn(f"talk:{incident_id}:{person_id}", loaded["relationships"][npc_id]["events"])
        self.assertEqual(loaded.get("quests", []), self.quests)

        before = campaign_time.public_time(loaded)["day_index"]
        moved = campaign_time.advance(loaded, 4 * campaign_time.DAY, "rest", "continuity")
        self.assertGreaterEqual(moved["elapsed_seconds"], 3 * campaign_time.DAY)
        self.assertGreaterEqual(campaign_time.public_time(loaded)["day_index"], before + 3)
        loaded["location"] = "fr:road:high"
        commit.advance(loaded, before_location=self.location)
        loaded["location"] = self.location
        again = next(row for row in loaded["npcs"] if row.get("id") == npc_id)
        self.assertEqual(again["location"], self.location)
        self.assertEqual(relationships.score(loaded, npc_id), 1)
        self.assertNotIn(SECRET, json.dumps(projection.scene_annotation(loaded), ensure_ascii=False))
        self.assertEqual(loaded.get("quests", []), self.quests)
        token = game._ACTIVE_SESSION.set(resumed.game_session)
        try:
            context = game.build_world_context()
        finally:
            game._ACTIVE_SESSION.reset(token)
        packet = json.dumps(context, ensure_ascii=False)
        self.assertIn("Elmalar tahtalara yuvarlanmış.", packet)
        self.assertNotIn("Mirel", packet)
        self.assertNotIn(SECRET, packet)
        self.assertNotIn("talk:", packet)
        for word in ("friend", "loyalty", "companion", "yoldaş", "sadık"):
            self.assertNotIn(word, packet.casefold())

    def test_player_look_and_rest_reach_the_incident_owner(self):
        self.world.setdefault("flags", {})["emergence_live"] = True
        proposals = []

        def propose(packet):
            envelope_packet = packet["envelope"]
            proposals.append(envelope_packet["trigger_kind"])
            body = _proposal(
                existing_refs=[],
                surface_facts=["Kasa kırılmış."],
                hidden_facts=[SECRET],
            )
            body["category"] = envelope_packet["decisions"]["category"]
            body["reward_class"] = envelope_packet["decisions"]["reward_class"]
            body["significance"] = envelope_packet["decisions"]["significance"]
            return json.dumps(body, ensure_ascii=False)

        real_decide = rng.decide

        def audible(campaign_id, trigger_id, **kwargs):
            decision = dict(real_decide(campaign_id, trigger_id, **kwargs))
            decision["silent"] = False
            return decision

        with patch.object(generator, "propose", propose), patch.object(rng, "decide", audible):
            with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls():
                rested = self.session.run_player_turn("bir saat dinleniyorum")
                looked = self.session.run_player_turn("etrafa bakıyorum")
        self.assertEqual(proposals, ["rest"])
        self.assertEqual(rested["action_result"]["action"], "rest")
        self.assertEqual(len(self.world.get("incidents", {})), 1)
        shown = projection.scene_annotation(self.world)
        packet = json.dumps(shown, ensure_ascii=False)
        self.assertIn("Kasa kırılmış.", packet)
        self.assertNotIn(SECRET, packet)
        self.assertNotIn("hidden_facts", packet)
        self.assertEqual(self.world.get("quests", []), self.quests)
        self.assertIn("direct_response", looked["action_result"])

    def test_player_look_reaches_the_incident_owner(self):
        self.world.setdefault("flags", {})["emergence_live"] = True
        proposals = []

        def propose(packet):
            envelope_packet = packet["envelope"]
            proposals.append(envelope_packet["trigger_kind"])
            body = _proposal(
                existing_refs=[],
                surface_facts=["Kasa kırılmış."],
                hidden_facts=[SECRET],
            )
            body["category"] = envelope_packet["decisions"]["category"]
            body["reward_class"] = envelope_packet["decisions"]["reward_class"]
            body["significance"] = envelope_packet["decisions"]["significance"]
            return json.dumps(body, ensure_ascii=False)

        real_decide = rng.decide

        def audible(campaign_id, trigger_id, **kwargs):
            decision = dict(real_decide(campaign_id, trigger_id, **kwargs))
            decision["silent"] = False
            return decision

        with patch.object(generator, "propose", propose), patch.object(rng, "decide", audible):
            with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls() as calls:
                looked = self.session.run_player_turn("etrafa bakıyorum")
        self.assertEqual(proposals, ["look_around"])
        self.assertEqual(calls, [])
        self.assertEqual(looked["action_result"]["action"], "explore")
        shown = json.dumps(projection.scene_annotation(self.world), ensure_ascii=False)
        self.assertIn("Kasa kırılmış.", shown)
        self.assertNotIn(SECRET, shown)
        self.assertEqual(self.world.get("quests", []), self.quests)

    def test_reward_pays_once_and_bridge_stays_quiet_until_it_is_eligible(self):
        profile = profiles.resolve(self.world, self.location)
        built = envelope.build(
            self.world, campaign_id=self.campaign_id,
            trigger_id=envelope.trigger_id_for(
                self.world, trigger_kind="arrival", location_id=self.location,
            ),
            trigger_kind="arrival", location_id=self.location, profile=profile,
            decisions=_decisions("coin_small"),
            hidden_context={"fact.secret": SECRET},
            faction_ids=list(profile["faction_ids"]),
        )
        proposal = _proposal(
            reward_class="coin_small",
            people=[
                {"label": "telaşlı aşçı", "role": "cook", "name": "Mirel",
                 "traits": ["anxious"], "backstory": "Gece vardiyasında çalışır."},
                {"label": "kapıdaki bekçi", "role": "guard", "name": "Sarn",
                 "traits": ["wary"], "backstory": None},
            ],
            hidden_facts=[SECRET],
            surface_facts=["Elmalar tahtalara yuvarlanmış."],
            existing_refs=[],
        )
        result = gate.evaluate(built, proposal)
        self.assertIn(result.outcome, (gate.ACCEPT, gate.NORMALIZE))
        incident_id = commit.commit(self.world, built, result.normalized)
        record = self.world["incidents"][incident_id]
        self.assertEqual(self.world.get("currency", {}).get("player", 0), 0)
        self.assertIsNone(bridge.bind(self.world, record, self.record.lore_authority, campaign_id=self.campaign_id))
        self.assertEqual(self.world.get("quests", []), self.quests)

        for label in ("telaşlı aşçı", "kapıdaki bekçi"):
            talk = {"action": "narrative", "success": True, "state_changes": []}
            hooks.before_narration(
                self.session, action_result=talk, player_text=f"Konuş: {label}", location_changed=False,
            )
            hooks.after_turn(self.session, {"location": self.location}, talk)
        promoted = [
            person.get("npc_id") for person in record["details"]["people"].values()
            if person.get("state") == "promoted"
        ]
        self.assertEqual(len(promoted), 2)

        solo = copy.deepcopy(self.world)
        solo["npcs"] = [npc for npc in solo["npcs"] if npc.get("id") == promoted[0]]
        evidence = EngineActionEvidence("act.hear", 1, "python_engine")
        heard = possibilities.offer(
            self.record.lore_authority, solo, record, authorized=True,
            evidence=evidence, source_action_id="act.hear", turn_index=1,
        )
        self.assertIsNone(bridge.bind(solo, record, heard, campaign_id=self.campaign_id))
        self.assertEqual(solo.get("quests", []), self.quests)

        heard = possibilities.offer(
            self.record.lore_authority, self.world, record, authorized=True,
            evidence=evidence, source_action_id="act.hear", turn_index=1,
        )
        self.record.lore_authority = heard
        created = bridge.bind(self.world, record, heard, campaign_id=self.campaign_id)
        self.assertIsNotNone(created)
        self.assertEqual(created["status"], "AVAILABLE")
        self.assertNotEqual(created["status"], "accepted")
        self.assertNotIn(SECRET, json.dumps(created, ensure_ascii=False))
        self.assertIsNone(bridge.bind(self.world, record, heard, campaign_id=self.campaign_id))
        self.assertEqual(sum(1 for item in self.world["quests"] if item.get("quest_id") == created["quest_id"]), 1)

        wallet = self.world.get("currency", {}).get("player", 0)
        claim = {"action": "claim_reward", "success": True, "incident_id": incident_id}
        hooks.after_turn(self.session, {"location": self.location}, claim)
        self.assertEqual(self.world["currency"]["player"], wallet + rewards.COIN_CP["coin_small"])
        hooks.after_turn(self.session, {"location": self.location}, claim)
        self.assertEqual(self.world["currency"]["player"], wallet + rewards.COIN_CP["coin_small"])
        narrated = {"action": "narrative", "success": True, "incident_id": incident_id}
        hooks.after_turn(self.session, {"location": self.location}, narrated)
        self.assertEqual(self.world["currency"]["player"], wallet + rewards.COIN_CP["coin_small"])
        self.assertEqual(
            [item.get("status") for item in self.world["quests"] if item.get("quest_id") == created["quest_id"]],
            ["AVAILABLE"],
        )

        self.manager.save_campaign(self.campaign_id)
        with self.manager._registry_lock:
            session_id = self.manager._campaign_sessions.pop(self.campaign_id)
            del self.manager._sessions[session_id]
        _, resumed, _, _, _ = self.manager.resume_campaign(self.campaign_id)
        loaded = resumed.game_session.world_state
        self.assertEqual(loaded["currency"]["player"], wallet + rewards.COIN_CP["coin_small"])
        self.assertEqual(
            next(item["status"] for item in loaded["quests"] if item.get("quest_id") == created["quest_id"]),
            "AVAILABLE",
        )
        self.assertEqual(relationships.score(loaded, promoted[0]), 1)


if __name__ == "__main__":
    unittest.main()

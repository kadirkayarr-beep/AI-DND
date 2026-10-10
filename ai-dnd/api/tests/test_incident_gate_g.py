"""Gate G: adventure possibility, director bind, aftermath seed, thread index."""

import unittest

from api.lore_authority.campaign_state import EngineActionEvidence
from api.lore_authority.models import CampaignLoreState, ClaimType
from api.lore_authority.player_knowledge import read_player_knowledge
from api.lore_authority.pack_loader import PRODUCTION_REGISTRY, load_pack_index
from api.tests.test_incident_gate_a import _envelope, _proposal, _world
from api.tests.test_incident_models import _incident
from adventure.director import MAX_OPEN
from incidents import bridge, commit, gate, possibilities, profiles, threads, triggers


def _bound_lore():
    return CampaignLoreState.from_mapping({
        "binding_status": "BOUND",
        "setting_profile": "forgotten_realms",
        "world_id": "fr:world:forgotten_realms",
        "epoch_id": "fr:epoch:1501_dr",
        "region_id": "fr:region:the_north",
        "current_location_entity_id": "fr:city:neverwinter",
        "starting_location_entity_id": "fr:city:neverwinter",
        "region_pack_id": "fr:pack:the_north:neverwinter:v1",
        "player_known_fact_ids": [],
        "npc_known_fact_ids": {},
        "campaign_overrides": [],
        "procedural_entity_refs": [],
        "lore_discoveries": [],
        "adventure_possibility_ids": [],
    })


def _evidence(action_id="act.incident", turn=3):
    return EngineActionEvidence(action_id=action_id, turn_index=turn, authority="python_engine")


class PossibilityTests(unittest.TestCase):
    def test_python_offer_is_not_a_quest_and_unauthorized_is_noop(self):
        _, world = _world()
        world["campaign_id"] = "campaign.test"
        incident_id = commit.commit(world, _envelope(world, reward="none"),
                                    gate.evaluate(_envelope(world, reward="none"), _proposal()).normalized)
        record = world["incidents"][incident_id]
        lore = _bound_lore()
        self.assertIs(possibilities.offer(
            lore, world, record, authorized=False, evidence=_evidence(),
            source_action_id="act.incident", turn_index=3,
        ), lore)
        updated = possibilities.offer(
            lore, world, record, authorized=True, evidence=_evidence(),
            source_action_id="act.incident", turn_index=3,
        )
        self.assertIn(possibilities.fact_id_for(incident_id), updated.adventure_possibility_ids)
        self.assertEqual(world["quests"], [])
        shown = read_player_knowledge(updated, world, PRODUCTION_REGISTRY)
        self.assertEqual(shown["adventure_possibilities"][0]["claim_type"], ClaimType.ADVENTURE_POSSIBILITY.value)
        self.assertEqual(shown["adventure_possibilities"][0]["text"], record["premise"])

    def test_director_bind_respects_max_open(self):
        _, world = _world()
        world["campaign_id"] = "campaign.test"
        world["npcs"].append({"id": "npc.cook", "name": "Mirel", "role": "cook", "location": "tavern"})
        built = _envelope(world, reward="none")
        incident_id = commit.commit(world, built, gate.evaluate(built, _proposal()).normalized)
        record = world["incidents"][incident_id]
        lore = possibilities.offer(
            _bound_lore(), world, record, authorized=True, evidence=_evidence(),
            source_action_id="act.incident", turn_index=3,
        )
        created = bridge.bind(world, record, lore, campaign_id="campaign.test")
        self.assertIsNotNone(created)
        self.assertEqual(created["record_kind"], "dynamic")
        self.assertNotEqual(created.get("quest_id"), incident_id)
        self.assertTrue(any(quest.get("quest_id") == created["quest_id"] for quest in world["quests"]))
        self.assertIn(incident_id, world["incidents"])

        world["quests"] = list(world["quests"])
        while len([q for q in world["quests"] if q.get("record_kind") == "dynamic"]) < MAX_OPEN:
            world["quests"].append({
                **created, "quest_id": f"adv.filler{len(world['quests'])}",
                "opportunity_key": f"opportunity:filler{len(world['quests'])}",
                "creation_evidence": f"other.{len(world['quests'])}",
            })
        second_id = "inc.other"
        world["incidents"][second_id] = _incident(second_id)
        lore2 = possibilities.offer(
            lore, world, world["incidents"][second_id], authorized=True,
            evidence=_evidence("act.2", 4), source_action_id="act.2", turn_index=4,
        )
        self.assertIsNone(bridge.bind(world, world["incidents"][second_id], lore2, campaign_id="campaign.test"))


class AftermathAndThreadTests(unittest.TestCase):
    def test_adventure_close_seeds_in_horizon_aftermath(self):
        _, world = _world()
        trigger = triggers.detect(
            world,
            action_result={"action": "adventure_completed", "quest_id": "adv.done"},
            player_text="",
            location_changed=False,
        )
        self.assertEqual(trigger["kind"], "aftermath")
        self.assertEqual(trigger["source_event_id"], "adv.done")
        from incidents import horizon
        self.assertTrue(horizon.in_horizon(world, trigger))

    def test_thread_depth_cap_starts_a_new_index(self):
        _, world = _world()
        first = threads.attach(world, "inc.a")
        parent = "inc.a"
        for index in range(2, threads.MAX_DEPTH + 1):
            parent_next = f"inc.{index}"
            self.assertEqual(threads.attach(world, parent_next, parent), first)
            parent = parent_next
        overflow = threads.attach(world, "inc.overflow", parent)
        self.assertNotEqual(overflow, first)
        self.assertEqual(max(row["depth"] for row in world["incident_threads"]), threads.MAX_DEPTH)
        threads.validate(world["incident_threads"])


class DraftCityPackTests(unittest.TestCase):
    def test_waterdeep_and_baldurs_gate_stay_incomplete_and_off(self):
        indexed = {row["pack_id"]: row["coverage_status"] for row in load_pack_index()}
        self.assertEqual(indexed["fr:pack:waterdeep:v1"], "INCOMPLETE")
        self.assertEqual(indexed["fr:pack:baldurs_gate:v1"], "INCOMPLETE")
        self.assertIsNone(profiles.load("waterdeep.v1"))
        self.assertIsNone(profiles.load("baldurs_gate.v1"))


class SaveThreadTests(unittest.TestCase):
    def test_thread_index_is_validated_on_save(self):
        import game
        session, world = _world()
        threads.attach(world, "inc.save")
        game._validate_save_payload(session.serialize_game_state())
        threads.validate(session.serialize_game_state()["world_state"]["incident_threads"])


if __name__ == "__main__":
    unittest.main()

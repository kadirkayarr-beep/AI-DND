"""Direct unit tests for incidents.envelope: built before any model call, stamped on the domains it read."""

import json
import unittest

from incidents import envelope
from incidents import state as emergence_state

PROFILE = {
    "profile_id": "test.tavern",
    "tier_ceiling": 9,
    "categories": ["lost_property", "disturbance"],
    "roles": ["cook", "guard"],
    "subscene_kinds": ["alley"],
    "faction_ids": ["fr:faction:a"],
    "faction_rank_ceiling": "member",
    "protected_names": ["Zed"],
}
DECISIONS = {"significance": "minor", "category": "disturbance", "reward_class": "none"}


def _world():
    return {
        "location": "tavern",
        "locations": {"tavern": {"parent_location_id": "town"}, "town": {}},
        "campaign_time": {"elapsed_seconds": 7200},
        "npcs": [
            {"id": "npc.keeper", "name": "Hesk", "role": "innkeeper", "location": "tavern"},
            {"id": "npc.dead", "name": "Old", "role": "farmer", "location": "tavern", "combat_status": "dead"},
            {"id": "npc.far", "name": "Ona", "role": "farmer", "location": "forest"},
        ],
        "incidents": {},
        "player_knowledge": [],
    }


def _build(world, **over):
    kwargs = dict(
        campaign_id="campaign.t",
        trigger_id="trg:1",
        trigger_kind="arrival",
        location_id="tavern",
        profile=PROFILE,
        decisions=DECISIONS,
    )
    kwargs.update(over)
    return envelope.build(world, **kwargs)


class ClockAndHashTests(unittest.TestCase):
    def test_clock_bucket_is_one_hour(self):
        self.assertEqual(envelope.clock_bucket(_world()), 2)
        self.assertEqual(envelope.clock_bucket({}), 0)

    def test_hash_ignores_key_order(self):
        self.assertEqual(envelope.envelope_hash({"a": 1, "b": 2}), envelope.envelope_hash({"b": 2, "a": 1}))
        self.assertNotEqual(envelope.envelope_hash({"a": 1}), envelope.envelope_hash({"a": 2}))


class KnownFactTests(unittest.TestCase):
    def test_only_facts_of_incidents_anchored_here(self):
        world = _world()
        world["incidents"] = {"inc.a": {"location_id": "tavern"}, "inc.b": {"location_id": "town"}}
        world["player_knowledge"] = ["incident:inc.a:fact.x", "incident:inc.b:fact.y", "incident:inc.a:fact.x", "other", 3]
        self.assertEqual(envelope.known_fact_ids(world, "tavern"), ["incident:inc.a:fact.x"])


class BuildTests(unittest.TestCase):
    def test_envelope_carries_the_profile_limits(self):
        built = _build(_world(), faction_ids=["fr:faction:a", "fr:faction:other"])
        self.assertEqual(built["tier_ceiling"], envelope.TIER_CEILING_MAX)
        self.assertEqual(built["allowed_faction_ids"], ["fr:faction:a"])
        self.assertEqual(built["allowed_entity_ids"], ["npc.keeper"])
        self.assertEqual(built["parent_location_id"], "town")
        self.assertEqual(built["protected_names"], ["Zed"])
        self.assertLessEqual(set(built), envelope.ENVELOPE_FIELDS)

    def test_unknown_location_or_reward_class_is_refused(self):
        with self.assertRaises(envelope.EnvelopeError):
            _build(_world(), location_id="nowhere")
        with self.assertRaises(envelope.EnvelopeError):
            _build(_world(), decisions={"reward_class": "dragon_hoard"})

    def test_too_large_envelope_is_refused(self):
        with self.assertRaises(envelope.EnvelopeError):
            _build(_world(), hidden_context={"fact": "x" * envelope.MAX_ENVELOPE_BYTES})

    def test_hidden_context_is_copied_not_shared(self):
        hidden = {"fact.a": "secret"}
        built = _build(_world(), hidden_context=hidden)
        hidden["fact.a"] = "changed"
        self.assertEqual(built["hidden_context"]["fact.a"], "secret")
        json.dumps(built)


class StampTests(unittest.TestCase):
    def test_unrelated_writes_keep_the_stamp(self):
        world = _world()
        built = _build(world)
        world["flags"] = {"anything": 1}
        world["npcs"][2]["role"] = "baker"
        self.assertFalse(envelope.is_stale(world, built))

    def test_cast_change_makes_the_envelope_stale(self):
        world = _world()
        built = _build(world)
        world["npcs"].append({"id": "npc.new", "name": "Ria", "role": "guard", "location": "tavern"})
        self.assertTrue(envelope.is_stale(world, built))

    def test_new_open_incident_here_makes_it_stale(self):
        world = _world()
        built = _build(world)
        world["incidents"]["inc.a"] = {"location_id": "tavern", "lifecycle": "PRESENT"}
        self.assertTrue(envelope.is_stale(world, built))

    def test_clock_bucket_change_gives_a_new_trigger_id(self):
        world = _world()
        before = envelope.trigger_id_for(world, trigger_kind="arrival", location_id="tavern")
        world["campaign_time"]["elapsed_seconds"] += envelope.CLOCK_BUCKET_SECONDS
        self.assertNotEqual(before, envelope.trigger_id_for(world, trigger_kind="arrival", location_id="tavern"))

    def test_reward_budget_only_counts_when_a_reward_is_possible(self):
        world = _world()
        no_reward = _build(world)
        rewarding = _build(world, decisions=dict(DECISIONS, reward_class="coin_small"))
        world[emergence_state.KEY] = {
            "budget": {"coin": 1}, "cooldowns": {}, "recent_categories": [], "paid_signatures": []
        }
        self.assertFalse(envelope.is_stale(world, no_reward))
        self.assertTrue(envelope.is_stale(world, rewarding))

    def test_trigger_id_is_stable_and_names_its_kind(self):
        world = _world()
        first = envelope.trigger_id_for(world, trigger_kind="arrival", location_id="tavern")
        self.assertEqual(first, envelope.trigger_id_for(world, trigger_kind="arrival", location_id="tavern"))
        self.assertTrue(first.startswith("trg:arrival:"))
        self.assertNotEqual(first, envelope.trigger_id_for(world, trigger_kind="rest", location_id="tavern"))


if __name__ == "__main__":
    unittest.main()

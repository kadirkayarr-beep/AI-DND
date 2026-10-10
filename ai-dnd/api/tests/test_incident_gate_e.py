"""Gate E: rewards, relationships, faction ceiling, knowledge, anti-farming."""

import unittest
from unittest.mock import patch

import equipment_economy
import relationships
from api.tests.test_incident_gate_a import _envelope, _proposal, _world
from incidents import budgets, commit, faction, gate, knowledge, rewards


def _paid(world, reward_class="coin_small", **overrides):
    world["campaign_id"] = "campaign.test"
    world.setdefault("currency", {})["player"] = world.get("currency", {}).get("player", 0)
    built = _envelope(world, reward=reward_class)
    data = _proposal(reward_class=reward_class, **overrides)
    incident_id = commit.commit(world, built, gate.evaluate(built, data).normalized)
    return incident_id, world["incidents"][incident_id]


class RewardTests(unittest.TestCase):
    def test_coin_pays_once_through_economy(self):
        _, world = _world()
        incident_id, record = _paid(world, "coin_small")
        before = world.get("currency", {}).get("player", 0)
        first = rewards.grant(world, record)
        self.assertEqual(first["kind"], "coin")
        self.assertEqual(world["currency"]["player"], before + 40)
        self.assertIsNone(rewards.grant(world, record))
        self.assertEqual(world["currency"]["player"], before + 40)
        self.assertEqual(world["quests"], [])

    def test_magic_catalog_is_rejected(self):
        _, world = _world()
        self.assertTrue(rewards.reject_magic(world, "no-such-vorpal"))
        magic = {
            "weapon_id": "vorpal_test", "name": "Vorpal", "magic_attack_bonus": 3,
            "magic_damage_bonus": 3,
        }
        with patch("equipment_economy.lookup", return_value=magic):
            self.assertTrue(rewards.reject_magic(world, "vorpal_test"))
        _, record = _paid(world, "rare_find")
        with patch("equipment_economy.lookup", return_value=magic):
            with self.assertRaises(rewards.RewardError):
                rewards.grant(world, record, catalog_id="vorpal_test")
        self.assertFalse(any(
            isinstance(item, dict) and "vorpal" in item.get("name", "").casefold()
            for item in world.get("inventory", [])
        ))

    def test_mundane_catalog_rare_find_pays(self):
        _, world = _world()
        _, record = _paid(world, "rare_find")
        paid = rewards.grant(world, record, catalog_id="club")
        self.assertEqual(paid["kind"], "catalog")
        self.assertTrue(any(item.get("item_id") == paid["item_id"] for item in world["inventory"]))


class FarmingTests(unittest.TestCase):
    def test_tavern_reentry_does_not_pay_again(self):
        _, world = _world()
        _, record = _paid(world, "coin_small")
        rewards.grant(world, record)
        self.assertFalse(budgets.allowed(
            world, location_id="tavern", reward_class="coin_small", trigger_kind="arrival"))
        world["location"] = "forest"
        world["location"] = "tavern"
        self.assertFalse(budgets.allowed(
            world, location_id="tavern", reward_class="coin_small", trigger_kind="arrival"))
        self.assertEqual(budgets.recent_weight(world, "coin_small"), 0)

    def test_second_rare_in_window_blocked(self):
        _, world = _world()
        _, record = _paid(world, "rare_find")
        rewards.grant(world, record, catalog_id="club")
        self.assertFalse(budgets.allowed(
            world, location_id="tavern", reward_class="rare_find", trigger_kind="look_around"))


class RelationshipAndKnowledgeTests(unittest.TestCase):
    def test_relationship_is_not_the_npc_string_and_is_idempotent(self):
        _, world = _world()
        world["npcs"][0]["relationship"] = "neutral"
        score = relationships.note(world, "npc.keeper", 2, "helped-crate")
        self.assertEqual(score, 2)
        self.assertEqual(relationships.note(world, "npc.keeper", 2, "helped-crate"), 2)
        self.assertEqual(relationships.note(world, "npc.keeper", 2, "helped-again"), 4)
        self.assertEqual(world["npcs"][0]["relationship"], "neutral")
        relationships.validate(world["relationships"])

    def test_rumor_is_knowledge_not_a_quest(self):
        _, world = _world()
        _, record = _paid(world, "none")
        knowledge.rumor(world, record, "The cook is missing a crate of apples.")
        self.assertTrue(any(item.startswith("incident:") and item.endswith(":rumor")
                            for item in world["player_knowledge"]))
        self.assertEqual(world["quests"], [])


class FactionTests(unittest.TestCase):
    def test_officer_rank_is_refused_and_unbound_is_unchanged(self):
        self.assertFalse(faction.rank_allowed("officer", "member"))
        self.assertTrue(faction.rank_allowed("associate", "member"))
        lore = object()
        self.assertIs(faction.apply(
            lore, faction_id="fr:faction:lords_alliance", rank="officer",
            source_action_id="act.1", turn_index=1, evidence=None,
        ), lore)


if __name__ == "__main__":
    unittest.main()

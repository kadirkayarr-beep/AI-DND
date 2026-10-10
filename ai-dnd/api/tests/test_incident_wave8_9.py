"""Wave 8 director/arcs and Gate I companions. Weighting is not canon."""

import unittest

import adventure.arcs as arcs
import adventure.director_v2 as director_v2
import adventure.templates as templates
import companions
import game
import relationships
from incidents import drift


def _world():
    session = game.create_session(seed=3)
    world = session.world_state
    world["location"] = "tavern"
    world["npcs"].append({"id": "npc.friend", "name": "Teren", "role": "traveler", "location": "tavern"})
    return session, world


class DirectorV2Tests(unittest.TestCase):
    def test_scores_are_not_written_to_the_world(self):
        _, world = _world()
        before = dict(world)
        table = director_v2.scores(world)
        self.assertIn("MISSING_PERSON", table)
        self.assertEqual(director_v2.style_signal(world), "cautious")
        self.assertEqual(world.keys(), before.keys())
        self.assertNotIn("director_v2", world)
        world["adventure_recent_categories"] = ["combat", "combat"]
        self.assertEqual(director_v2.style_signal(world), "direct")
        self.assertEqual(director_v2.choose(world), "BOUNTY")


class ArcAndDriftTests(unittest.TestCase):
    def test_sixth_link_is_refused_and_drift_does_not_rewrite(self):
        _, world = _world()
        for index in range(arcs.MAX_LINKS):
            self.assertIsNotNone(arcs.extend(world, "arc.one", f"adv.{index}"))
        self.assertIsNone(arcs.extend(world, "arc.one", "adv.too-many"))
        self.assertEqual(world["adventure_arcs"][0]["depth"], arcs.MAX_LINKS)
        premise = world.get("incidents")
        drift.flag(world, {"incident_id": "inc.x"}, "historical_override")
        self.assertEqual(world.get("incidents"), premise)
        self.assertIsNotNone(drift.profile_conflict(world, "waterdeep", "waterdeep.v1"))


class CompanionTests(unittest.TestCase):
    def test_narration_cannot_create_and_player_must_accept(self):
        _, world = _world()
        self.assertIsNone(companions.accept(
            world, "npc.friend", player_accepted=False, turn_index=2))
        self.assertEqual(world.get("companions", []), [])
        relationships.note(world, "npc.friend", 2, "helped-once")
        relationships.note(world, "npc.friend", 2, "helped-twice")
        self.assertTrue(companions.eligible(world, "npc.friend"))
        row = companions.accept(world, "npc.friend", player_accepted=True, turn_index=4)
        self.assertEqual(row["source"], "player_accepted")
        self.assertEqual(len(world["companions"]), 1)
        self.assertEqual(
            companions.accept(world, "npc.friend", player_accepted=True, turn_index=5)["npc_id"],
            "npc.friend",
        )
        world["npcs"].append({"id": "npc.other", "name": "Osa", "role": "guard", "location": "tavern"})
        relationships.note(world, "npc.other", 5, "bonded")
        self.assertIsNone(companions.accept(
            world, "npc.other", player_accepted=True, turn_index=6))

    def test_escort_graph_instantiates(self):
        _, world = _world()
        quest = templates.instantiate(
            "ESCORT",
            quest_id="adv.escort",
            turn=1,
            opportunity_key="opportunity:escort",
            creation_evidence="event:escort",
            bindings=templates.prepared_bindings(
                source_npc_id="npc.friend",
                target_npc_id="npc.friend",
                location_ids=["tavern"],
            ),
            rumor="Yolda refakat ister.",
        )
        self.assertEqual(quest["template_id"], "ESCORT")
        self.assertEqual(quest["record_kind"], "dynamic")


if __name__ == "__main__":
    unittest.main()

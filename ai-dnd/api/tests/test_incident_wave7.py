"""Wave 7: optional and secret objectives, fail-forward, RECOVERY and sibling graphs."""

import copy
import unittest

import adventure.completion as completion
import adventure.followup as followup
import adventure.projection as projection
import adventure.rewards as rewards
import adventure.templates as templates
import game


def _session():
    session = game.create_session(seed=8)
    place = "tavern"
    session.world_state["location"] = place
    session.world_state["npcs"].extend([
        {"id": "npc.source", "location": place, "current_hp": 12, "combat_status": "active"},
        {"id": "npc.missing", "location": place, "current_hp": 9, "combat_status": "active"},
    ])
    session.character["xp"] = 0
    return session, place


def _bindings(place):
    return templates.prepared_bindings(
        source_npc_id="npc.source",
        target_npc_id="npc.missing",
        location_ids=[place],
    )


def _make(template_id, session, place, quest_id="adv.one"):
    quest = templates.instantiate(
        template_id,
        quest_id=quest_id,
        turn=1,
        opportunity_key=f"opportunity:{template_id.lower()}",
        creation_evidence=f"event:{template_id.lower()}",
        bindings=_bindings(place),
        rumor="Yerel bir iş var.",
    )
    session.world_state["quests"].append(quest)
    return quest


class OptionalAndSecretTests(unittest.TestCase):
    def test_primary_success_ignores_optional_and_hides_secrets(self):
        session, place = _session()
        quest = _make("RECOVERY", session, place)
        required = {item["objective_id"] for item in completion.required(quest)}
        self.assertIn("item", required)
        self.assertNotIn("favor", required)
        for item in quest["objectives"]:
            if not item["optional"]:
                item["graph_state"] = "COMPLETE"
                item["status"] = "completed"
                item["visibility"] = "known"
        self.assertTrue(completion.primary_success(quest))
        favor = next(item for item in quest["objectives"] if item["objective_id"] == "favor")
        self.assertEqual(favor["graph_state"], "HIDDEN")
        card = projection.journal(session.world_state)
        blob = str(card)
        self.assertNotIn(favor["description"], blob)
        for secret in completion.secret_descriptions(quest):
            self.assertNotIn(secret, blob)

    def test_fail_forward_is_one_later_possibility(self):
        session, place = _session()
        quest = _make("DELIVERY", session, place, "adv.fail")
        quest["status"] = "FAILED"
        quest["outcome"] = "failed"
        created = followup.maybe_follow_up(
            session.world_state, quest,
            bindings=_bindings(place),
            rumor="İş yarım kaldı.",
            evidence_id="event:fail-forward",
            campaign_id="campaign.test",
        )
        self.assertIsNotNone(created)
        self.assertEqual(quest["follow_up_key"], created["opportunity_key"])
        self.assertIsNone(followup.maybe_follow_up(
            session.world_state, quest,
            bindings=_bindings(place),
            rumor="İkinci bir iş.",
            evidence_id="event:fail-forward-2",
            campaign_id="campaign.test",
        ))


class TemplateGraphTests(unittest.TestCase):
    def test_each_new_template_is_one_graph(self):
        session, place = _session()
        for template_id in (
            "RECOVERY", "DELIVERY", "MONSTER_HUNT", "FACTION_CONFLICT",
            "SOCIAL_INTRIGUE", "DUNGEON_DELVE", "URBAN_INVESTIGATION",
        ):
            with self.subTest(template_id=template_id):
                quest = templates.instantiate(
                    template_id,
                    quest_id=f"adv.{template_id.lower()}",
                    turn=1,
                    opportunity_key=f"opportunity:{template_id.lower()}",
                    creation_evidence=f"event:{template_id.lower()}",
                    bindings=_bindings(place),
                    rumor="Bir iş.",
                )
                self.assertEqual(quest["template_id"], template_id)
                self.assertEqual(quest["record_kind"], "dynamic")
                self.assertGreaterEqual(len(quest["objectives"]), 2)
                self.assertTrue(any(item["graph_state"] == "ACTIVE" for item in quest["objectives"]))

    def test_partial_success_pays_existing_reward_owner(self):
        session, place = _session()
        quest = _make("RECOVERY", session, place, "adv.reward")
        quest["status"] = "COMPLETED"
        quest["outcome"] = "partial_success"
        before = session.world_state.get("currency", {}).get("player", 0)
        paid = rewards.apply_plan(session.character, session.world_state, quest)
        self.assertFalse(paid["replayed"])
        self.assertGreater(session.world_state["currency"]["player"], before)
        again = rewards.apply_plan(session.character, session.world_state, quest)
        self.assertTrue(again["replayed"])


if __name__ == "__main__":
    unittest.main()

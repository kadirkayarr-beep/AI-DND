"""Durable reward rollback and faction follow-up on the API session path."""

from __future__ import annotations

import copy
import random
import unittest
from unittest.mock import patch
from uuid import uuid4

import adventure.play as play
import adventure.templates as templates
from api.tests import test_campaign_api as fixtures
from api.tests.test_phase7_package import bound_state


class _FixedRandom(random.Random):
    def randint(self, a, b):
        return b


def _daggers(world):
    return [
        item for item in world.get("inventory", [])
        if isinstance(item, dict) and item.get("weapon_id") == "dagger"
    ]


def _faction_quests(world):
    return [
        item for item in world.get("quests", [])
        if isinstance(item, dict) and str(item.get("creation_evidence", "")).startswith("faction:")
    ]


class AdventureReleaseTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    def _prepare(self, campaign):
        record = self.manager.get(campaign["session_id"])
        session = record.game_session
        world = session.world_state
        place = world.get("location")
        world["campaign_id"] = campaign["campaign_id"]
        if isinstance(place, str):
            world.setdefault("locations", {}).setdefault(place, {"name": place})
        world.setdefault("locations", {}).setdefault("forest", {"name": "Orman"})
        world["npcs"] = [
            {"id": "npc.source", "name": "Marek", "location": place, "current_hp": 12, "combat_status": "active"},
            {"id": "npc.missing", "name": "Elin", "location": place, "current_hp": 9, "combat_status": "active"},
        ]
        lore = bound_state()
        session.campaign_lore_state = lore
        record.lore_authority = lore
        session.rng = _FixedRandom(1)
        quest = templates.instantiate(
            "MISSING_PERSON",
            quest_id="adv.release",
            turn=1,
            opportunity_key="opportunity:release",
            creation_evidence="event:release",
            bindings=templates.prepared_bindings(
                source_npc_id="npc.source",
                target_npc_id="npc.missing",
                location_ids=[place] if isinstance(place, str) else [],
                faction_ids=["faction:watch"],
            ),
            rumor="Cael hakkında bir söylenti dolaşıyor.",
        )
        quest["reward_plan"]["success"]["faction"] = {"id": "faction:watch", "standing": 1}
        world.setdefault("quests", []).append(quest)
        play.hear(session, quest["quest_id"])
        session.accept_quest(quest["quest_id"])
        session.run_player_turn("izleri inceliyorum.")
        session.run_player_turn("izleri inceliyorum.")
        origin = world["location"]
        world["location"] = "forest"
        before = copy.deepcopy(world)
        world["location"] = origin
        world["flags"]["turn_index"] = world["flags"].get("turn_index", 0) + 1
        session.evaluate_quest_events(before, {"action": "travel", "success": True})
        session.run_player_turn("Saklı girişe giriyorum.")
        session.run_player_turn("Koridorda ilerliyorum.")
        session.run_player_turn("Odayı incele")
        session.run_player_turn("Gizli geçitten ilerliyorum.")
        session.run_player_turn("Tutsakların olduğu odaya giriyorum.")
        self.manager.save_campaign(campaign["campaign_id"])
        return record, quest

    def _reward_view(self, record):
        session = record.game_session
        world = session.world_state
        quest = next(item for item in world["quests"] if item.get("quest_id") == "adv.release")
        lore = getattr(record, "lore_authority", None) or session.campaign_lore_state
        standing = next(
            (row.standing for row in getattr(lore, "faction_standings", ()) if row.faction_id == "faction:watch"),
            None,
        )
        return {
            "xp": session.character.get("xp", 0),
            "gold": world.get("currency", {}).get("player", 0),
            "daggers": len(_daggers(world)),
            "standing": standing,
            "marker": quest.get("reward_application_id"),
            "status": quest.get("status"),
            "outcome": quest.get("outcome"),
            "faction_followups": [item["quest_id"] for item in _faction_quests(world)],
        }

    async def test_failed_save_rolls_back_the_reward_and_retry_pays_once(self):
        campaign = await self.create_campaign()
        record, _quest = self._prepare(campaign)
        before = self._reward_view(record)
        stored = self.store.get_campaign(campaign["campaign_id"])
        action_id = str(uuid4())
        command = {"message": "Onu ikna etmeye çalışıyorum.", "action_id": action_id}
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("fixture save failure")):
            failed = await self.http.post(
                f"/api/game/sessions/{campaign['session_id']}/turn",
                json=command,
            )
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertNotIn("karşılık", failed.text.casefold())
        self.assertEqual(self._reward_view(record), before)
        self.assertEqual(self.store.get_campaign(campaign["campaign_id"]), stored)
        self.assertIsNone(self.manager.get_turn_action(record, action_id))

        paid = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/turn",
            json=command,
        )
        self.assertEqual(paid.status_code, 200, paid.text)
        self.assertIn("karşılık", paid.json()["narration"].casefold())
        after = self._reward_view(record)
        self.assertEqual(after["xp"], before["xp"] + 80)
        self.assertEqual(after["gold"], before["gold"] + 50)
        self.assertEqual(after["daggers"], before["daggers"] + 1)
        self.assertEqual(after["standing"], 1)
        self.assertEqual(after["marker"], "quest:adv.release:success")
        self.assertEqual(after["status"], "COMPLETED")
        self.assertEqual(after["outcome"], "success")
        self.assertEqual(len(after["faction_followups"]), 1)

        replay = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/turn",
            json=command,
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(self._reward_view(record), after)

        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager

        resumed = SessionManager(campaign_store=CampaignStore(self.store.path))
        resumed_id, restored, *_rest = resumed.resume_campaign(campaign["campaign_id"])
        self.assertEqual(self._reward_view(restored), after)
        self.assertNotEqual(resumed_id, "")


if __name__ == "__main__":
    unittest.main()

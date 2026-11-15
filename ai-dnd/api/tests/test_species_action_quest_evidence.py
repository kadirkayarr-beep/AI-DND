"""D-105 (KRİT-04): a bounty target that falls to a species action's own damage closes the bounty.

The species-actions panel route is its own door: a combat Healing Hands ends the Aasimar's turn, and an active Inner
Radiance deals its end-of-turn Radiant damage (PHB 2024 PDF p.185) to each creature within 10 feet. When that damage
drops the bounty's target, the quest owner must see the before/after of this same command, as the play turn does;
the next turn's "before" already holds the fallen target and can no longer see the defeat.
"""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

import httpx

import adventure.templates as adventure_templates
import adventure.transitions as adventure_transitions
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.tests.auth_fixture import TEST_PLAYER, TestPlayerSessionManager
from api.tests.test_api import FakeOllamaClient
from api.tests.town_seed import fixed_town
from api.lore_authority.campaign_state import EngineActionEvidence, apply_faction_standing
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as campaign_fixtures
from api.tests.test_phase7_package import bound_state


def _stage_radiant_bounty(session, target_hp):
    """An Aasimar with Inner Radiance in combat beside a bounty whose only open step is the target's defeat."""
    session.character.update(species="Aasimar", race="Aasimar", level=3, proficiency_bonus=2,
                             current_hp=5, max_hp=20, charisma_mod=1)
    session.initialize_species_trait_state()
    session._species_trait_state().update(active_celestial_form="inner_radiance",
                                          celestial_revelation_turns_remaining=10)
    here = session.world_state["location"]
    giver = {"id": "npc.d105-giver", "name": "Ödül Veren", "role": "Guard", "location": here, "current_hp": 8,
             "max_hp": 8, "combat_status": "active", "distance_ft": 60}  # outside the 10 ft radiance
    foe = {"id": "npc.d105-target", "name": "Aranan Haydut", "role": "Bandit", "location": here,
           "current_hp": target_hp, "max_hp": target_hp, "armor_class": 10, "combat_status": "active",
           "dexterity_mod": 0, "hostile": True, "combat_side": "enemy", "distance_ft": 5,
           "attack_damage_type": "bludgeoning", "attack_bonus": 0, "damage_die": 6, "damage_dice": 1,
           "damage_modifier": 0}
    session.world_state["npcs"].extend([giver, foe])
    session.world_state.setdefault("monster_perception", {})[foe["id"]] = {"player": {"visible": True}}
    quest = adventure_templates.instantiate(
        "BOUNTY", quest_id="adv.d105-bounty", turn=1, opportunity_key="opportunity:d105",
        creation_evidence="event:d105",
        bindings=adventure_templates.prepared_bindings(source_npc_id=giver["id"], target_npc_id=foe["id"],
                                                       location_ids=[here]),
        rumor="Synthetic D-105 bounty fixture.",
    )
    quest = adventure_transitions.transition(quest, "DISCOVERED", 1)
    quest = adventure_transitions.transition(quest, "ACTIVE", 2)
    for objective in quest["objectives"]:  # notice and mark already done: only the defeat is left
        done = objective["objective_id"] != "resolve"
        objective.update(graph_state="COMPLETE" if done else "ACTIVE", status="completed" if done else "active",
                         visibility="known", progress=objective["required_count"] if done else 0)
    session.world_state["quests"].append(quest)
    with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
        session.start_combat(foe)
    return foe


class SpeciesActionQuestEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = TestPlayerSessionManager()
        self.adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(self.adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=self.adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")

    async def asyncTearDown(self):
        await self.http.aclose()

    async def radiant_aasimar_facing_the_bounty(self, target_hp):
        with fixed_town(self, 10501):
            created = await self.http.post("/api/game/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        session = self.manager.get(session_id).game_session
        return session_id, session, _stage_radiant_bounty(session, target_hp)

    def bounty(self, session):
        return next(q for q in session.world_state["quests"] if q.get("quest_id") == "adv.d105-bounty")

    async def test_radiance_defeat_of_the_bounty_target_completes_and_pays_the_bounty(self):
        session_id, session, foe = await self.radiant_aasimar_facing_the_bounty(target_hp=1)
        purse_before = session.world_state.get("currency", {}).get("player", 0)
        xp_before = session.character.get("xp", 0)
        with patch.object(session.rng, "randint", return_value=1):
            response = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                            json={"action": "healing_hands", "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        radiance = [e for e in response.json()["result"]["effects"]["turn_end"] if e.get("target_id") == foe["id"]]
        self.assertEqual([e["target_hp_after"] for e in radiance], [0], "Inner Radiance drops the bounty target")
        bounty = self.bounty(session)
        self.assertEqual((bounty["status"], bounty.get("outcome")), ("COMPLETED", "success"))
        self.assertIsNotNone(bounty.get("reward_application_id"), "the bounty's reward receipt is written")
        plan = bounty["reward_plan"]["success"]
        # D-104: the plan's gold is paid as gold, x 100 copper.
        self.assertEqual(session.world_state["currency"]["player"] - purse_before, plan["gold"] * 100)
        # 60 bounty XP plus the fallen foe's own 10 combat XP, each under its own once-only id.
        self.assertEqual(session.character["xp"] - xp_before, plan["xp"] + 10)
        self.assertEqual([i for i in session.world_state["xp_awarded_event_ids"] if i.startswith(("quest:", "combat:"))],
                         [f"combat:foe:{foe['id']}", "quest:adv.d105-bounty:success"])
        self.assertEqual(bounty["reward_application_id"], "quest:adv.d105-bounty:success")
        outcomes = response.json()["result"]["effects"].get("quest_outcomes")
        self.assertEqual([o["transition"] for o in outcomes], ["objective_completed", "completed"])

    async def test_replay_keeps_the_bounty_paid_exactly_once(self):
        session_id, session, foe = await self.radiant_aasimar_facing_the_bounty(target_hp=1)
        purse_before = session.world_state.get("currency", {}).get("player", 0)
        xp_before = session.character.get("xp", 0)
        url = f"/api/game/sessions/{session_id}/species-actions"
        action_id = "d1050000-0000-4000-8000-000000000105"
        with patch.object(session.rng, "randint", return_value=1):
            first = await self.http.post(url, json={"action": "healing_hands", "action_id": action_id})
        self.assertEqual(first.status_code, 200, first.text)
        paid_purse, paid_xp = session.world_state["currency"]["player"], session.character["xp"]
        replay = await self.http.post(url, json={"action": "healing_hands", "action_id": action_id})
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["result"], first.json()["result"])
        session = self.manager.get(session_id).game_session
        self.assertEqual((session.world_state["currency"]["player"], session.character["xp"]), (paid_purse, paid_xp))
        undone = await self.http.post(f"/api/game/sessions/{session_id}/undo",
                                      json={"action_id": "d1050000-0000-4000-8000-000000000106",
                                            "target_action_id": action_id})
        # A species command keeps no Undo checkpoint (only the turn, economic and ambient routes do); the refusal leaves the
        # paid bounty exactly as it was.
        self.assertEqual((undone.status_code, undone.json()["detail"]["code"]), (409, "undo_unavailable"))
        session = self.manager.get(session_id).game_session
        bounty = self.bounty(session)
        self.assertEqual((bounty["status"], bounty["reward_application_id"]), ("COMPLETED", "quest:adv.d105-bounty:success"))
        self.assertEqual(paid_purse - purse_before, bounty["reward_plan"]["success"]["gold"] * 100)
        self.assertEqual((session.world_state["currency"]["player"], session.character["xp"]), (paid_purse, paid_xp))
        self.assertEqual(paid_xp - xp_before, 70)

    async def test_a_target_left_standing_does_not_close_the_bounty(self):
        session_id, session, foe = await self.radiant_aasimar_facing_the_bounty(target_hp=30)
        purse_before = session.world_state.get("currency", {}).get("player", 0)
        with patch.object(session.rng, "randint", return_value=1):
            response = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                            json={"action": "healing_hands", "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        bounty = self.bounty(session)
        self.assertEqual(bounty["status"], "ACTIVE")
        self.assertIsNone(bounty.get("reward_application_id"))
        self.assertEqual(session.world_state.get("currency", {}).get("player", 0), purse_before)
        self.assertNotIn("quest_outcomes", response.json()["result"]["effects"])

    async def test_last_turns_ask_for_work_opens_no_offer_on_the_panel_command(self):
        # The panel command carries no player words: last turn's "iş var mı" must not make the player hear an offer here.
        session_id, session, _foe = await self.radiant_aasimar_facing_the_bounty(target_hp=30)
        here = session.world_state["location"]
        unheard = adventure_templates.instantiate(  # an offer still AVAILABLE: only asking for work makes it heard
            "BOUNTY", quest_id="adv.d105-unheard", turn=1, opportunity_key="opportunity:d105-unheard",
            creation_evidence="event:d105-unheard",
            bindings=adventure_templates.prepared_bindings(source_npc_id="npc.d105-giver",
                                                           target_npc_id="npc.d105-target", location_ids=[here]),
            rumor="Synthetic D-105 unheard offer fixture.",
        )
        self.assertEqual(unheard["status"], "AVAILABLE")
        session.world_state["quests"].append(unheard)
        session._adventure_player_text = "iş var mı, bir görev duydun mu?"
        quests_before = [(q.get("quest_id"), q.get("status")) for q in session.world_state["quests"]]
        with patch.object(session.rng, "randint", return_value=1):
            response = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                            json={"action": "healing_hands", "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([(q.get("quest_id"), q.get("status")) for q in session.world_state["quests"]], quests_before)


def _standings(lore, faction_id="faction:watch"):
    return [(row.standing, row.source_action_id) for row in getattr(lore, "faction_standings", ())
            if row.faction_id == faction_id]


class SpeciesActionFactionLoreTests(unittest.IsolatedAsyncioTestCase):
    """The bounty's standing reward from a species action lands on the saved lore and leaves with a rolled-back save."""

    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def faction_bounty(self, record_lore, session_lore):
        with fixed_town(self, 10511):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        record = self.manager.get(campaign["session_id"])
        session = record.game_session
        foe = _stage_radiant_bounty(session, target_hp=1)
        bounty = next(q for q in session.world_state["quests"] if q.get("quest_id") == "adv.d105-bounty")
        bounty["reward_plan"]["success"]["faction"] = {"id": "faction:watch", "standing": 1}
        record.lore_authority = record_lore
        if session_lore is not None:
            session.campaign_lore_state = session_lore
        return campaign, record, session, foe

    async def radiance(self, campaign, session, action_id=None):
        body = {"action": "healing_hands", "action_id": action_id or str(uuid.uuid4())}  # D-111: the id is required
        with patch.object(session.rng, "randint", return_value=1):
            return await self.http.post(f"/api/game/sessions/{campaign['session_id']}/species-actions", json=body)

    def resumed_lore(self, campaign):
        resumed = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _session_id, record, *_rest = resumed.resume_campaign(campaign["campaign_id"])
        return record.lore_authority

    async def test_bounty_standing_reaches_the_record_and_the_saved_campaign(self):
        lore = bound_state()
        campaign, record, session, _foe = await self.faction_bounty(lore, lore)
        response = await self.radiance(campaign, session)
        self.assertEqual(response.status_code, 200, response.text)
        marker = "quest:adv-d105-bounty:success"
        self.assertEqual(_standings(record.lore_authority), [(1, marker)])
        self.assertEqual(_standings(self.resumed_lore(campaign)), [(1, marker)], "the save holds the standing")

    async def test_a_session_without_a_lore_copy_pays_onto_the_record_lore(self):
        campaign, record, session, _foe = await self.faction_bounty(bound_state(), None)
        response = await self.radiance(campaign, session)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(_standings(record.lore_authority), [(1, "quest:adv-d105-bounty:success")])

    async def test_a_stale_session_lore_copy_does_not_drop_record_lore(self):
        stale = bound_state()
        earlier = apply_faction_standing(
            stale, faction_id="faction:guild", standing=-1, known_to_player=True, local_presence=True,
            evidence=EngineActionEvidence("turn-earlier", 0, "python_engine"),
            source_action_id="turn-earlier", turn_index=0,
        )
        campaign, record, session, _foe = await self.faction_bounty(earlier, stale)
        response = await self.radiance(campaign, session)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(_standings(record.lore_authority, "faction:guild"), [(-1, "turn-earlier")])
        self.assertEqual(_standings(record.lore_authority), [(1, "quest:adv-d105-bounty:success")])
        # The stale copy does not stay behind for the next quest command or play turn to read before the record.
        self.assertIs(session.campaign_lore_state, record.lore_authority)

    async def test_failed_save_takes_the_standing_out_of_the_live_session_too(self):
        lore = bound_state()
        campaign, record, session, _foe = await self.faction_bounty(lore, lore)
        action_id = "d1050000-0000-4000-8000-000000000201"
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("fixture save failure")), \
                self.assertRaises(RuntimeError):  # this route re-raises an unknown save error after the rollback
            await self.radiance(campaign, session, action_id)
        self.assertIsNone(self.manager.get_turn_action(record, action_id))
        session = self.manager.get(campaign["session_id"]).game_session
        self.assertIs(getattr(session, "campaign_lore_state", None), lore, "the live copy is put back as it was")
        self.assertIs(record.lore_authority, lore)
        paid = await self.radiance(campaign, session, action_id)
        self.assertEqual(paid.status_code, 200, paid.text)
        self.assertEqual(_standings(record.lore_authority), [(1, "quest:adv-d105-bounty:success")])
        self.assertEqual(_standings(self.resumed_lore(campaign)), [(1, "quest:adv-d105-bounty:success")])

    async def test_a_species_action_leaves_no_lore_copy_for_a_later_quest_command_to_restore(self):
        # A session without a lore copy (a fresh or resumed one) must stay without one: a later turn writes only the
        # record's lore, and a quest command would then put a copy left here back over the newer lore.
        campaign, record, session, _foe = await self.faction_bounty(bound_state(), None)
        bounty = next(q for q in session.world_state["quests"] if q.get("quest_id") == "adv.d105-bounty")
        target = next(n for n in session.world_state["npcs"] if n["id"] == "npc.d105-target")
        target.update(current_hp=30, max_hp=30)  # the target stays standing: no reward, nothing for the copy to carry
        response = await self.radiance(campaign, session)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(bounty["status"], "ACTIVE")
        self.assertIsNone(getattr(session, "campaign_lore_state", None), "the copy is put back as it was")
        # Stands in for what a later play turn writes: only the record's lore moves on.
        record.lore_authority = apply_faction_standing(
            record.lore_authority, faction_id="faction:guild", standing=2, known_to_player=True, local_presence=True,
            evidence=EngineActionEvidence("turn:9", 9, "python_engine"), source_action_id="turn:9", turn_index=9,
        )
        cancelled = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/quests/adv.d105-bounty/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(_standings(record.lore_authority, "faction:guild"), [(2, "turn:9")])
        self.assertEqual(_standings(self.resumed_lore(campaign), "faction:guild"), [(2, "turn:9")])

    async def test_a_filled_lore_copy_keeps_the_paid_standing_through_a_later_quest_command(self):
        # hear(), a paid reward, Undo and a rolled-back turn each leave a lore copy on the live session. After the
        # species action pays the bounty, the next quest command reads that copy: the paid standing must stay saved.
        lore = bound_state()
        campaign, record, session, _foe = await self.faction_bounty(lore, lore)
        here = session.world_state["location"]
        other = adventure_templates.instantiate(  # a second ACTIVE adventure the player cancels afterwards
            "BOUNTY", quest_id="adv.d105-other", turn=1, opportunity_key="opportunity:d105-other",
            creation_evidence="event:d105-other",
            bindings=adventure_templates.prepared_bindings(source_npc_id="npc.d105-giver",
                                                           target_npc_id="npc.d105-giver", location_ids=[here]),
            rumor="Synthetic D-105 second adventure fixture.",
        )
        other = adventure_transitions.transition(other, "DISCOVERED", 1)
        session.world_state["quests"].append(adventure_transitions.transition(other, "ACTIVE", 2))
        response = await self.radiance(campaign, session)
        self.assertEqual(response.status_code, 200, response.text)
        marker = "quest:adv-d105-bounty:success"
        self.assertEqual(_standings(record.lore_authority), [(1, marker)])
        # The next play turn stages its lore from this copy before the record's: it must be the paid lore itself.
        self.assertIs(session.campaign_lore_state, record.lore_authority)
        cancelled = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/quests/adv.d105-other/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(_standings(record.lore_authority), [(1, marker)], "the quest command keeps the paid standing")
        self.assertEqual(_standings(self.resumed_lore(campaign)), [(1, marker)], "the save keeps the paid standing")


if __name__ == "__main__":
    unittest.main()

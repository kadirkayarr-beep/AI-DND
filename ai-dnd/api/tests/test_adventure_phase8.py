"""Phase 8 adventure behavior beyond the state record."""

import copy
import unittest

import adventure.deadlines as deadlines
import adventure.director as director
import adventure.dungeon as dungeon
import adventure.encounters as encounters
import adventure.evidence as evidence
import adventure.followup as followup
import adventure.projection as projection
import adventure.rewards as rewards
import adventure.templates as templates
import game
from api.serializers import serialize_session_state
from api.tests.test_phase7_package import bound_state


def _session():
    session = game.create_session(seed=4)
    place = "tavern"
    session.world_state["location"] = place
    session.world_state["npcs"].extend([
        {"id": "npc.source", "location": place, "current_hp": 12, "combat_status": "active"},
        {"id": "npc.missing", "location": place, "current_hp": 9, "combat_status": "active"},
        {"id": "npc.bandit", "location": place, "current_hp": 8, "combat_status": "active"},
    ])
    return session, place


def _bindings(place):
    return templates.prepared_bindings(
        source_npc_id="npc.source",
        target_npc_id="npc.missing",
        location_ids=[place],
    )


class AdventurePhase8Tests(unittest.TestCase):
    def test_text_alone_does_not_complete_and_unrelated_evidence_misses(self):
        session, place = _session()
        quest = templates.instantiate(
            "MISSING_PERSON",
            quest_id="adv.missing",
            turn=1,
            opportunity_key="opportunity:missing",
            creation_evidence="event:rumor:1",
            bindings=_bindings(place),
            rumor="Bir muhafız kayıp.",
        )
        session.world_state["quests"].append(quest)
        before = copy.deepcopy(session.world_state)
        evidence.apply_dynamic_evidence(session.world_state, before, {"narration": "Rehineyi kurtardım."})
        self.assertEqual(quest["status"], "AVAILABLE")
        self.assertTrue(all(item["graph_state"] != "COMPLETE" for item in quest["objectives"]))

        discovered = adventure_transition(quest, "DISCOVERED", 2)
        quest.clear()
        quest.update(discovered)
        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = 3
        evidence.apply_dynamic_evidence(session.world_state, before, {
            "action": "skill_check",
            "success": True,
            "skill": "persuasion",
            "target": "npc.bandit",
            "action_id": "check:wrong",
        })
        hook = next(item for item in quest["objectives"] if item["objective_id"] == "hook")
        self.assertEqual(hook["graph_state"], "ACTIVE")

    def test_scoped_chain_partial_success_and_hidden_packet(self):
        session, place = _session()
        quest = templates.instantiate(
            "MISSING_PERSON",
            quest_id="adv.chain",
            turn=1,
            opportunity_key="opportunity:chain",
            creation_evidence="event:rumor:2",
            bindings=_bindings(place),
            rumor="Depoda bir ses duyulmuş.",
        )
        session.world_state["quests"].append(quest)
        session.campaign_lore_state = bound_state()
        session.world_state["flags"]["turn_index"] = 2
        import adventure.play as adventure_play
        adventure_play.hear(session, quest["quest_id"])
        packet = projection.model_packet(session.world_state, session.campaign_lore_state)
        self.assertNotIn("Tehdidi dağıt", str(packet))
        self.assertIn("Depoda bir ses duyulmuş.", packet["rumors"])
        self.assertNotIn("Tutsak odasına ulaş", str(packet))

        for state, turn in (("ACTIVE", 3),):
            updated = adventure_transition(quest, state, turn)
            quest.clear()
            quest.update(updated)
        self._advance(session, quest, {
            "action": "skill_check",
            "success": True,
            "skill": "persuasion",
            "target": "npc.source",
            "action_id": "check:hook",
        })
        self._advance(session, quest, {
            "action": "skill_check",
            "success": True,
            "skill": "investigation",
            "target": place,
            "action_id": "check:clue",
        })
        session.world_state["location"] = "forest"
        before = copy.deepcopy(session.world_state)
        session.world_state["location"] = place
        session.world_state["flags"]["turn_index"] = 6
        evidence.apply_dynamic_evidence(session.world_state, before, {})
        self._reach_cell(session, quest)
        evidence.fail_objective(quest, "threat")
        self._advance(session, quest, {
            "action": "skill_check",
            "success": True,
            "skill": "persuasion",
            "target": "npc.missing",
            "action_id": "check:rescue",
        })
        self.assertEqual(quest["outcome"], "partial_success")
        self.assertEqual(quest["status"], "COMPLETED")
        shown = projection.journal(session.world_state)
        self.assertTrue(shown["completed"])
        self.assertNotIn("objective_id", str(shown))

    def _reach_cell(self, session, quest):
        campaign_id = "campaign-a"
        session.world_state["campaign_id"] = campaign_id
        dungeon.ensure(session.world_state, campaign_id)
        dungeon.move(session.world_state, campaign_id, "fork")
        dungeon.reveal_hidden(session.world_state, campaign_id, "fork_hidden")
        dungeon.move(session.world_state, campaign_id, "hidden_route")
        before = copy.deepcopy(session.world_state)
        dungeon.move(session.world_state, campaign_id, "captive")
        session.world_state["flags"]["turn_index"] = session.world_state["flags"].get("turn_index", 0) + 1
        evidence.apply_dynamic_evidence(session.world_state, before, {})
        cell = next(item for item in quest["objectives"] if item["objective_id"] == "cell")
        self.assertEqual(cell["graph_state"], "COMPLETE")

    def _advance(self, session, quest, action):
        before = copy.deepcopy(session.world_state)
        turn = session.world_state["flags"].get("turn_index", 0)
        session.world_state["flags"]["turn_index"] = turn + 1
        evidence.apply_dynamic_evidence(session.world_state, before, action)

    def test_director_is_stable_capped_and_refuses_missing_entities(self):
        session, place = _session()
        bindings = _bindings(place)
        first = director.refresh(
            session.world_state,
            reason="ask_rumors",
            trigger="rumor",
            source_id="npc.source",
            bindings=bindings,
            rumor="Ormanda bir cadı varmış.",
            evidence_id="evidence:witch",
            campaign_id="campaign-a",
        )
        second = director.refresh(
            session.world_state,
            reason="ask_rumors",
            trigger="rumor",
            source_id="npc.source",
            bindings=bindings,
            rumor="Ormanda bir cadı varmış.",
            evidence_id="evidence:witch",
            campaign_id="campaign-a",
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(first["template_id"], "MISSING_PERSON")
        self.assertFalse(any(npc.get("id") == "npc.witch" for npc in session.world_state["npcs"]))
        invented = templates.prepared_bindings(
            source_npc_id="npc.nobody",
            target_npc_id="npc.missing",
            location_ids=[place],
        )
        self.assertIsNone(director.refresh(
            session.world_state,
            reason="ask_rumors",
            trigger="rumor",
            source_id="npc.nobody",
            bindings=invented,
            rumor="Kimse yok.",
            evidence_id="evidence:none",
            campaign_id="campaign-a",
        ))
        for index in range(3):
            director.refresh(
                session.world_state,
                reason="meaningful_discovery",
                trigger=f"extra-{index}",
                source_id="npc.source",
                bindings=bindings,
                rumor=f"Başka bir söylenti {index}",
                evidence_id=f"evidence:extra:{index}",
                campaign_id="campaign-a",
            )
        self.assertLessEqual(
            sum(item.get("status") in {"AVAILABLE", "DISCOVERED"} and item.get("record_kind") == "dynamic"
                for item in session.world_state["quests"]),
            3,
        )

    def test_reward_applies_once_and_rolls_back(self):
        session, place = _session()
        quest = templates.instantiate(
            "BOUNTY",
            quest_id="adv.bounty",
            turn=1,
            opportunity_key="opportunity:bounty",
            creation_evidence="event:bounty",
            bindings=_bindings(place),
            rumor="Bir haydut için ödül var.",
        )
        self.assertNotIn("rescue_person", {item["type"] for item in quest["objectives"]})
        quest["status"] = "COMPLETED"
        quest["outcome"] = "success"
        quest["accepted_turn"] = 1
        quest["reward_plan"] = {
            "success": {"xp": 50, "gold": 100, "faction": {"id": "faction:watch", "standing": 1}},
            "partial_success": {"xp": 25, "gold": 40},
            "failed": {},
        }
        before_xp = session.character.get("xp", 0)
        broken = copy.deepcopy(quest)
        with self.assertRaises(ValueError):
            rewards.apply_plan(session.character, session.world_state, broken, lore_state=None)
        self.assertEqual(session.character.get("xp", 0), before_xp)
        self.assertIsNone(broken["reward_application_id"])

        lore = bound_state()
        paid = rewards.apply_plan(session.character, session.world_state, quest, lore_state=lore)
        again = rewards.apply_plan(session.character, session.world_state, quest, lore_state=lore)
        self.assertFalse(paid["replayed"])
        self.assertTrue(again["replayed"])
        self.assertEqual(session.character["xp"], before_xp + 50)
        self.assertEqual(paid["lore_state"].faction_standings[0].standing, 1)
        self.assertEqual(quest["reward_application_id"], "quest:adv.bounty:success")

    def test_deadline_does_not_start_while_hidden_or_reveal_nodes(self):
        session, place = _session()
        quest = templates.instantiate(
            "MISSING_PERSON",
            quest_id="adv.time",
            turn=1,
            opportunity_key="opportunity:time",
            creation_evidence="event:time",
            bindings=_bindings(place),
            rumor="Zaman daralıyor.",
        )
        self.assertIsNone(deadlines.arm(session.world_state, quest))
        updated = adventure_transition(quest, "DISCOVERED", 2)
        quest.clear()
        quest.update(updated)
        self.assertIsNotNone(deadlines.arm(session.world_state, quest, duration_seconds=60))
        event = session.world_state["scheduled_events"][-1]
        event["encounter_status"] = "MISSED"
        hidden_before = [item["objective_id"] for item in quest["objectives"] if item["graph_state"] == "HIDDEN"]
        self.assertTrue(deadlines.close_missed(session.world_state, quest))
        self.assertEqual(quest["status"], "FAILED")
        self.assertEqual(quest["outcome"], "missed")
        self.assertEqual(
            [item["objective_id"] for item in quest["objectives"] if item["graph_state"] == "HIDDEN"],
            hidden_before,
        )

    def test_dungeon_discovery_stays_inside_one_campaign(self):
        first = game.create_session(seed=1)
        second = game.create_session(seed=2)
        dungeon.move(first.world_state, "campaign-a", "fork")
        dungeon.reveal_hidden(first.world_state, "campaign-a", "fork_hidden")
        dungeon.open_door(first.world_state, "campaign-a", "fork_guard")
        self.assertEqual(dungeon.ensure(second.world_state, "campaign-b")["node"], "entrance")
        self.assertEqual(dungeon.ensure(second.world_state, "campaign-b")["discovered_edges"], [])
        moved = dungeon.move(first.world_state, "campaign-a", "guarded")
        self.assertEqual(moved["node"], "guarded")
        titles = [item["title"] for item in dungeon.visible_exits(first.world_state, "campaign-a")]
        self.assertIn("Tutsak odası", titles)

    def test_recent_combat_changes_director_choice_without_becoming_canon(self):
        calm, place = _session()
        fought, _same = _session()
        bindings = _bindings(place)
        for _ in range(8):
            before = copy.deepcopy(fought.world_state)
            fought.evaluate_quest_events(before, {"action": "attack", "success": True})
        self.assertLessEqual(len(fought.world_state["adventure_recent_categories"]), 6)
        self.assertNotIn("pacing", fought.world_state)
        self.assertEqual(director.pacing_for(fought.world_state), "DANGER")
        self.assertEqual(director._choose_template(calm.world_state), "MISSING_PERSON")
        self.assertEqual(director._choose_template(fought.world_state), "BOUNTY")
        self.assertEqual(director._choose_template(fought.world_state), "BOUNTY")
        offered = director.refresh(
            fought.world_state, reason="aftermath", trigger="paced",
            source_id="npc.source", bindings=bindings, rumor="Sakin bir iz.",
            evidence_id="evidence:paced", campaign_id="campaign-a",
        )
        self.assertEqual(offered["template_id"], "BOUNTY")
        again = director.refresh(
            fought.world_state, reason="aftermath", trigger="paced",
            source_id="npc.source", bindings=bindings, rumor="Sakin bir iz.",
            evidence_id="evidence:paced", campaign_id="campaign-a",
        )
        self.assertIsNone(again)
        narrated = _session()[0]
        before = copy.deepcopy(narrated.world_state)
        narrated.evaluate_quest_events(before, {"narration": "Bu bir combat karşılaşmasıydı. Görev tamamlandı."})
        self.assertEqual(narrated.world_state.get("adventure_recent_categories", []), [])

    def test_encounter_weight_and_public_state_shape(self):
        recipe = encounters.select(1, ["combat", "combat"])
        self.assertEqual(recipe["recipe_id"], "wounded_traveler")
        session, _place = _session()
        state = serialize_session_state(session)
        self.assertIn("campaign_adventures", state)
        self.assertEqual(state["campaign_adventures"]["active"], [])
        self.assertEqual(director.pacing_for({"adventure_recent_categories": ["combat"]}), "DANGER")
        self.assertIn("beast_threat", encounters.families())
        self.assertNotEqual(encounters.select(1, [])["threat_band"], "high")

    def test_rumor_is_not_a_fact_until_heard_and_clue_is_labeled(self):
        from api.lore_authority.models import CampaignLoreState
        from api.lore_authority.player_knowledge import read_player_knowledge
        from api.lore_authority.registry import LoreRegistry

        session, place = _session()
        before_npcs = {npc["id"] for npc in session.world_state["npcs"]}
        created = director.refresh(
            session.world_state,
            reason="ask_rumors",
            trigger="rumor",
            source_id="npc.source",
            bindings=_bindings(place),
            rumor="Ormanda bir cadı varmış.",
            evidence_id="evidence:witch-label",
            campaign_id="campaign-a",
        )
        hidden = projection.model_packet(session.world_state)
        self.assertNotIn("Ormanda bir cadı varmış.", hidden["rumors"])
        session.campaign_lore_state = bound_state()
        session.world_state["flags"]["turn_index"] = max(2, created["updated_turn"])
        import adventure.play as adventure_play
        adventure_play.hear(session, created["quest_id"])
        heard = read_player_knowledge(
            session.campaign_lore_state,
            session.world_state,
            LoreRegistry.empty(),
        )
        self.assertEqual(heard["known_facts"], [])
        self.assertEqual(heard["adventure_possibilities"][0]["claim_type"], "ADVENTURE_POSSIBILITY")
        self.assertEqual(heard["adventure_possibilities"][0]["text"], "Ormanda bir cadı varmış.")
        self.assertEqual(session.campaign_lore_state.campaign_overrides, ())
        self.assertEqual({npc["id"] for npc in session.world_state["npcs"]}, before_npcs)
        quest = created
        quest.update(adventure_transition(dict(quest), "ACTIVE", 3))
        self._advance(session, quest, {
            "action": "skill_check", "success": True, "skill": "persuasion",
            "target": "npc.source", "action_id": "check:hook-label",
        })
        self._advance(session, quest, {
            "action": "skill_check", "success": True, "skill": "investigation",
            "target": place, "action_id": "check:clue-label",
        })
        labels = {item["label"] for item in projection.journal(session.world_state)["rumors"]}
        self.assertIn("İpucu", labels)

    def test_affordance_and_invented_reward_do_not_write_state(self):
        session, place = _session()
        quest = templates.instantiate(
            "MISSING_PERSON",
            quest_id="adv.button",
            turn=1,
            opportunity_key="opportunity:button",
            creation_evidence="event:button",
            bindings=_bindings(place),
            rumor="Kapıda bir iz var.",
        )
        session.world_state["quests"].append(quest)
        quest.update(adventure_transition(dict(quest), "DISCOVERED", 2))
        quest.update(adventure_transition(dict(quest), "ACTIVE", 3))
        label = projection.affordances(quest)[0]
        before = copy.deepcopy(session.world_state)
        session.world_state.setdefault("currency", {})["player"] = 0
        evidence.apply_dynamic_evidence(session.world_state, before, {"narration": label})
        evidence.apply_dynamic_evidence(session.world_state, before, {"narration": "100 altın kazandın. Görev tamamlandı."})
        hook = next(item for item in quest["objectives"] if item["objective_id"] == "hook")
        self.assertEqual(hook["graph_state"], "ACTIVE")
        self.assertEqual(session.world_state["currency"]["player"], 0)
        self.assertIsNone(quest["outcome"])

    def test_one_active_one_follow_up_and_one_faction_gate(self):
        session, place = _session()
        bindings = _bindings(place)
        first = director.refresh(
            session.world_state, reason="enter_settlement", trigger="gate",
            source_id="npc.source", bindings=bindings, rumor="İlk söylenti.",
            evidence_id="evidence:first", campaign_id="campaign-a",
        )
        second = director.refresh(
            session.world_state, reason="npc_conversation", trigger="gate-2",
            source_id="npc.source", bindings=bindings, rumor="İkinci söylenti.",
            evidence_id="evidence:second", campaign_id="campaign-a",
        )
        director.discover(session.world_state, first["quest_id"])
        director.discover(session.world_state, second["quest_id"])
        director.accept_dynamic(session.world_state, first["quest_id"])
        with self.assertRaises(director.TransitionError):
            director.accept_dynamic(session.world_state, second["quest_id"])
        first["status"] = "COMPLETED"
        first["outcome"] = "partial_success"
        first["accepted_turn"] = 2
        created = followup.maybe_follow_up(
            session.world_state, first, bindings=bindings,
            rumor="Takip izi.", evidence_id="evidence:follow", campaign_id="campaign-a",
        )
        self.assertIsNotNone(created)
        self.assertEqual(created["template_id"], "BOUNTY")
        self.assertIsNone(followup.maybe_follow_up(
            session.world_state, first, bindings=bindings,
            rumor="Takip izi.", evidence_id="evidence:follow-again", campaign_id="campaign-a",
        ))
        self.assertIsNone(followup.faction_gate(
            session.world_state, 0, threshold=1, bindings=bindings,
            rumor="Hizip.", evidence_id="evidence:faction", campaign_id="campaign-a",
        ))

    def test_combat_resolution_and_campaigns_stay_apart(self):
        session, place = _session()
        quest = templates.instantiate(
            "MISSING_PERSON",
            quest_id="adv.combat",
            turn=1,
            opportunity_key="opportunity:combat",
            creation_evidence="event:combat",
            bindings=_bindings(place),
            rumor="Kavga kapıda.",
        )
        session.world_state["quests"].append(quest)
        quest.update(adventure_transition(dict(quest), "DISCOVERED", 2))
        quest.update(adventure_transition(dict(quest), "ACTIVE", 3))
        self._advance(session, quest, {
            "action": "skill_check", "success": True, "skill": "persuasion",
            "target": "npc.source", "action_id": "check:combat-hook",
        })
        self._advance(session, quest, {
            "action": "skill_check", "success": True, "skill": "investigation",
            "target": place, "action_id": "check:combat-clue",
        })
        session.world_state["location"] = "forest"
        before = copy.deepcopy(session.world_state)
        session.world_state["location"] = place
        evidence.apply_dynamic_evidence(session.world_state, before, {})
        self._reach_cell(session, quest)
        target = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc.missing")
        target["current_hp"] = 0
        target["combat_status"] = "defeated"
        before = copy.deepcopy(session.world_state)
        before["npcs"] = [
            {**npc, "current_hp": 9, "combat_status": "active"} if npc["id"] == "npc.missing" else npc
            for npc in before["npcs"]
        ]
        evidence.apply_dynamic_evidence(session.world_state, before, {"action_id": "defeat:npc.missing"})
        self.assertEqual(quest["outcome"], "success")
        other = game.create_session(seed=9)
        self.assertEqual(other.world_state["quests"], [])
        partial = copy.deepcopy(quest)
        partial["outcome"] = "partial_success"
        partial["reward_application_id"] = None
        before_xp = session.character.get("xp", 0)
        paid = rewards.apply_plan(session.character, session.world_state, partial)
        self.assertEqual(paid["marker"], "quest:adv.combat:partial_success")
        self.assertEqual(session.character["xp"], before_xp + 40)

    def test_settlement_arrival_offers_once_and_stays_hidden(self):
        session, place = _session()
        session.world_state["location"] = "forest"
        before = copy.deepcopy(session.world_state)
        session.world_state["location"] = place
        session.evaluate_quest_events(before, {})
        dynamic = [item for item in session.world_state["quests"] if item.get("record_kind") == "dynamic"]
        self.assertEqual(len(dynamic), 1)
        self.assertEqual(dynamic[0]["status"], "AVAILABLE")
        self.assertEqual(projection.model_packet(session.world_state)["rumors"], [])
        before = copy.deepcopy(session.world_state)
        session.evaluate_quest_events(before, {})
        self.assertEqual(
            sum(item.get("record_kind") == "dynamic" for item in session.world_state["quests"]),
            1,
        )


def adventure_transition(quest, state, turn, outcome=None):
    import adventure
    return adventure.transition(quest, state, turn, outcome=outcome)


if __name__ == "__main__":
    unittest.main()

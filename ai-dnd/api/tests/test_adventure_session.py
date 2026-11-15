"""GameSession wiring for dynamic adventures. Package-only calls are not enough."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import adventure.dungeon as dungeon
import adventure.play as play
import adventure.templates as templates
import game
import quest_catalog
from api.lore_authority.models import CampaignLoreState
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.test_phase7_package import bound_state


from api.tests.auth_fixture import TEST_PLAYER
def _session():
    session = game.create_session(seed=11)
    session.world_state["location"] = "tavern"
    session.world_state["campaign_id"] = "campaign-session"
    session.world_state["npcs"].extend([
        {"id": "npc.source", "name": "Marek", "location": "tavern", "current_hp": 12, "combat_status": "active"},
        {"id": "npc.missing", "name": "Elin", "location": "tavern", "current_hp": 9, "combat_status": "active"},
        {"id": "npc.other", "name": "Cael", "location": "tavern", "current_hp": 8, "combat_status": "active"},
    ])
    session.campaign_lore_state = _lore()
    session.ensure_campaign_clock()
    return session


def _lore():
    state = bound_state()
    return CampaignLoreState.from_mapping({
        **state.to_dict(),
        "player_known_fact_ids": [],
        "lore_discoveries": [],
    })


def _offer(session, evidence_id, source="npc.source"):
    before = copy.deepcopy(session.world_state)
    session.world_state["flags"]["turn_index"] = session.world_state["flags"].get("turn_index", 0) + 1
    session.evaluate_quest_events(before, {
        "action": "dialogue",
        "success": True,
        "npc_id": source,
    })


class AdventureSessionTests(unittest.TestCase):
    def test_dynamic_accept_and_abandon_leave_a_valid_row(self):
        session = _session()
        _offer(session, "talk")
        quest = next(item for item in session.world_state["quests"] if item.get("record_kind") == "dynamic")
        self.assertEqual(quest["status"], "AVAILABLE")
        with self.assertRaises(ValueError):
            session.accept_quest(quest["quest_id"])
        self.assertEqual(quest["status"], "AVAILABLE")
        session._adventure_player_text = "Bu civarda iş var mı?"
        before = copy.deepcopy(session.world_state)
        session.evaluate_quest_events(before, {"action": "dialogue", "success": True, "npc_id": "npc.source"})
        self.assertEqual(quest["status"], "DISCOVERED")
        self.assertTrue(session.campaign_lore_state.adventure_possibility_ids)
        self.assertEqual(session.campaign_lore_state.campaign_overrides, ())
        accepted = session.accept_quest(quest["quest_id"])
        self.assertEqual(quest["status"], "ACTIVE")
        self.assertEqual(accepted["transition"]["transition"], "accepted")
        self.assertIsNotNone(quest["deadline"])
        left = session.cancel_quest(quest["quest_id"])
        self.assertEqual(quest["status"], "ABANDONED")
        self.assertEqual(quest["outcome"], "abandoned")
        self.assertNotEqual(quest["status"], "cancelled")
        self.assertEqual(left["transition"]["transition"], "cancelled")
        import adventure
        adventure.validate_dynamic_saved_quest(quest, set())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adventure.json"
            session.save_game(path)
            session.load_game(path)
        restored = next(item for item in session.world_state["quests"] if item["quest_id"] == quest["quest_id"])
        self.assertEqual(restored["status"], "ABANDONED")
        adventure.validate_dynamic_saved_quest(restored, set())

    def test_legacy_accept_and_cancel_stay_legacy(self):
        session = _session()
        previous = quest_catalog.CATALOG
        quest_catalog.CATALOG = ({
            "quest_id": "legacy.errand",
            "title": "Eski iş",
            "description": "Taverna yolunu yürü.",
            "objectives": [{
                "objective_id": "walk",
                "description": "Taverna yolunu yürü.",
                "type": "visit_location",
                "target": "tavern",
            }],
        },)
        try:
            accepted = session.accept_quest("legacy.errand")
            self.assertEqual(accepted["quest"]["status"], "accepted")
            self.assertNotIn("record_kind", accepted["quest"])
            cancelled = session.cancel_quest("legacy.errand")
            self.assertEqual(cancelled["quest"]["status"], "cancelled")
            self.assertEqual(set(cancelled["quest"]), adventure_fields())
        finally:
            quest_catalog.CATALOG = previous

    def test_refresh_is_idempotent_and_capped_on_the_session(self):
        session = _session()
        for source in ("npc.source", "npc.missing", "npc.other", "npc.source"):
            _offer(session, source, source)
        dynamic = [item for item in session.world_state["quests"] if item.get("record_kind") == "dynamic"]
        open_rows = [item for item in dynamic if item["status"] in {"AVAILABLE", "DISCOVERED"}]
        self.assertLessEqual(len(open_rows), 3)
        self.assertEqual(len(dynamic), len({item["opportunity_key"] for item in dynamic}))
        again = len(session.world_state["quests"])
        _offer(session, "npc.source", "npc.source")
        self.assertEqual(len(session.world_state["quests"]), again)

    def test_remote_deadline_closes_through_the_clock(self):
        session = _session()
        _offer(session, "talk")
        quest = next(item for item in session.world_state["quests"] if item.get("record_kind") == "dynamic")
        hidden = session.world_state["quests"]
        spare = templates.instantiate(
            "BOUNTY",
            quest_id="adv.unseen",
            turn=1,
            opportunity_key="opportunity:unseen",
            creation_evidence="event:unseen",
            bindings=templates.prepared_bindings(
                source_npc_id="npc.source",
                target_npc_id="npc.missing",
                location_ids=["tavern"],
            ),
            rumor="Henüz duyulmamış bir ilan.",
        )
        hidden.append(spare)
        session._adventure_player_text = "Söylenti var mı?"
        before = copy.deepcopy(session.world_state)
        session.evaluate_quest_events(before, {"action": "dialogue", "success": True, "npc_id": "npc.source"})
        self.assertEqual(quest["status"], "DISCOVERED")
        self.assertIsNotNone(quest["deadline"])
        self.assertIsNone(spare["deadline"])
        session.world_state["location"] = "forest"
        session.advance_campaign_time(7200, "rest")
        event = next(item for item in session.world_state["scheduled_events"] if item["event_id"] == quest["deadline"])
        self.assertEqual(event["encounter_status"], "MISSED")
        self.assertEqual(event["status"], "PENDING")
        self.assertFalse(event["player_observed"])
        self.assertEqual(quest["status"], "FAILED")
        self.assertEqual(quest["outcome"], "missed")
        self.assertEqual(spare["status"], "AVAILABLE")
        self.assertIsNone(spare["deadline"])
        self.assertTrue(any(item["graph_state"] == "HIDDEN" for item in quest["objectives"]))

    def test_missing_person_paths_ignore_unrelated_and_narration(self):
        session = _session()
        quest = _active_missing(session)
        before_status = quest["status"]
        before = copy.deepcopy(session.world_state)
        session.evaluate_quest_events(before, {"narration": "Rehine kurtarıldı. Görev tamamlandı. 100 altın."})
        self.assertEqual(quest["status"], before_status)
        self.assertIsNone(quest["outcome"])
        session.evaluate_quest_events(before, {
            "action": "skill_check", "success": True, "skill": "Persuasion",
            "target": "npc.other", "action_id": "check:wrong-person",
        })
        hook = _objective(quest, "hook")
        self.assertEqual(hook["graph_state"], "ACTIVE")
        session.world_state["flags"]["turn_index"] += 1
        before = copy.deepcopy(session.world_state)
        session.evaluate_quest_events(before, {
            "action": "skill_check", "success": True, "skill": "persuasion",
            "target": "npc.source", "action_id": "check:hook-real",
        })
        self.assertEqual(_objective(quest, "hook")["graph_state"], "COMPLETE")
        session.world_state["flags"]["turn_index"] += 1
        before = copy.deepcopy(session.world_state)
        session.evaluate_quest_events(before, {
            "action": "skill_check", "success": True, "skill": "Investigation",
            "target": "tavern", "action_id": "check:clue-real",
        })
        self.assertEqual(_objective(quest, "clue")["graph_state"], "COMPLETE")
        session.world_state["location"] = "forest"
        before = copy.deepcopy(session.world_state)
        session.world_state["location"] = "castle"
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(before, {})
        self.assertNotEqual(_objective(quest, "site")["graph_state"], "COMPLETE")
        session.world_state["location"] = "forest"
        before = copy.deepcopy(session.world_state)
        session.world_state["location"] = "tavern"
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(before, {})
        self.assertEqual(_objective(quest, "site")["graph_state"], "COMPLETE")
        play.traverse(session, "fork")
        play.reveal(session, "fork_hidden")
        play.traverse(session, "hidden_route")
        before = copy.deepcopy(session.world_state)
        play.traverse(session, "captive")
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(before, {})
        self.assertEqual(_objective(quest, "cell")["graph_state"], "COMPLETE")
        session.world_state["flags"]["turn_index"] += 1
        before = copy.deepcopy(session.world_state)
        other = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc.other")
        other["current_hp"] = 0
        other["combat_status"] = "defeated"
        session.evaluate_quest_events(before, {})
        self.assertNotEqual(quest["status"], "COMPLETED")
        session.world_state["flags"]["turn_index"] += 1
        before = copy.deepcopy(session.world_state)
        target = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc.missing")
        target["current_hp"] = 0
        target["combat_status"] = "defeated"
        session.evaluate_quest_events(before, {})
        # YENİDEN YAZIM (D-117 / YÜK-14 inceleme): the old test closed the quest as success on the
        # captive's defeat alone; a beaten captive is not rescued, so the rescue needs its own act.
        self.assertEqual(_objective(quest, "rescue")["graph_state"], "ACTIVE")
        self.assertIsNone(quest["outcome"])
        session.world_state["flags"]["turn_index"] += 1
        before = copy.deepcopy(session.world_state)
        session.evaluate_quest_events(before, {
            "action": "skill_check", "success": True, "skill": "Stealth",
            "target": "npc.missing", "action_id": "check:rescue-real",
        })
        self.assertEqual(quest["outcome"], "success")
        marker = "quest:adv.session-missing:success"
        self.assertEqual(quest["reward_application_id"], marker)
        self.assertIn(marker, session.world_state["xp_awarded_event_ids"])
        gold = session.world_state["currency"]["player"]
        self.assertGreater(gold, 0)
        session.evaluate_quest_events(copy.deepcopy(session.world_state), {})
        self.assertEqual(session.world_state["currency"]["player"], gold)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paid.json"
            session.save_game(path)
            session.world_state["currency"]["player"] = 0
            session.load_game(path)
        restored = next(item for item in session.world_state["quests"] if item["quest_id"] == quest["quest_id"])
        self.assertEqual(restored["reward_application_id"], marker)
        self.assertEqual(session.world_state["currency"]["player"], gold)
        self.assertIn(marker, session.world_state["xp_awarded_event_ids"])

    def test_partial_persuasion_pays_once(self):
        session = _session()
        quest = _active_missing(session)
        _finish_to_cell(session, quest)
        import adventure.evidence as evidence
        evidence.fail_objective(quest, "threat")
        before_xp = session.character.get("xp", 0)
        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(before, {
            "action": "skill_check", "success": True, "skill": "persuasion",
            "target": "npc.missing", "action_id": "check:rescue-real",
        })
        play.settle_session(session)
        self.assertEqual(quest["outcome"], "partial_success")
        self.assertEqual(session.character["xp"], before_xp + 40)
        marker = quest["reward_application_id"]
        followed = [
            item for item in session.world_state["quests"]
            if item.get("opportunity_key") == quest.get("follow_up_key")
        ]
        self.assertEqual(len(followed), 1)
        before_count = len(session.world_state["quests"])
        play.settle_session(session)
        self.assertEqual(quest["reward_application_id"], marker)
        self.assertEqual(len(session.world_state["quests"]), before_count)

    def test_bounty_uses_the_same_session_door(self):
        session = _session()
        _offer(session, "first")
        import adventure.director as director
        director.note_category(session.world_state, "combat")
        director.note_category(session.world_state, "combat")
        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(before, {
            "action": "dialogue", "success": True, "npc_id": "npc.missing",
        })
        bounty = next(item for item in session.world_state["quests"] if item.get("template_id") == "BOUNTY")
        play.hear(session, bounty["quest_id"])
        self.assertEqual(bounty["status"], "DISCOVERED")
        session.accept_quest(bounty["quest_id"])
        self.assertEqual(bounty["status"], "ACTIVE")
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(copy.deepcopy(session.world_state), {
            "action": "skill_check", "success": True, "skill": "investigation",
            "target": bounty["giver_npc_id"], "action_id": "check:bounty-notice",
        })
        session.world_state["location"] = "forest"
        before = copy.deepcopy(session.world_state)
        session.world_state["location"] = "tavern"
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(before, {})
        target = next(npc for npc in session.world_state["npcs"] if npc["id"] == bounty["bindings"]["target_npc_id"])
        before = copy.deepcopy(session.world_state)
        target["current_hp"] = 0
        target["combat_status"] = "defeated"
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(before, {})
        self.assertEqual(bounty["status"], "COMPLETED")
        self.assertEqual(bounty["outcome"], "success")

    def test_dungeon_resume_and_campaigns_do_not_share_discovery(self):
        session = _session()
        quest = _active_missing(session)
        _finish_to_site(session, quest)
        self.assertNotIn("fork_hidden", dungeon.ensure(session.world_state, "campaign-session")["discovered_edges"])
        play.traverse(session, "fork")
        play.reveal(session, "fork_hidden")
        play.traverse(session, "hidden_route")
        before = copy.deepcopy(session.world_state)
        play.traverse(session, "captive")
        session.world_state["flags"]["turn_index"] += 1
        session.evaluate_quest_events(before, {})
        self.assertEqual(_objective(quest, "cell")["graph_state"], "COMPLETE")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dungeon.json"
            session.save_game(path)
            session.world_state["dungeon_discovery"] = {}
            session.load_game(path)
        state = session.world_state["dungeon_discovery"][dungeon.HIDEOUT_ID]
        self.assertEqual(state["node"], "captive")
        self.assertIn("fork_hidden", state["discovered_edges"])
        other = game.create_session(seed=12)
        other.world_state["campaign_id"] = "campaign-other"
        fresh = dungeon.ensure(other.world_state, "campaign-other")
        self.assertEqual(fresh["discovered_nodes"], ["entrance"])
        self.assertEqual(fresh["node"], "entrance")

    def test_two_campaign_stores_do_not_share_adventures(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CampaignStore(Path(directory) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
            manager = SessionManager(campaign_store=store)
            first_id, _first_session, first, _meta = manager.create_campaign("Bir")
            second_id, _second_session, second, _meta = manager.create_campaign("İki")
            first.game_session.world_state["location"] = "tavern"
            first.game_session.world_state["npcs"].extend([
                {"id": "npc.source", "name": "Marek", "location": "tavern", "current_hp": 10, "combat_status": "active"},
                {"id": "npc.missing", "name": "Elin", "location": "tavern", "current_hp": 10, "combat_status": "active"},
            ])
            first.game_session.campaign_lore_state = _lore()
            first.lore_authority = first.game_session.campaign_lore_state
            _offer(first.game_session, "stored")
            first.game_session._adventure_player_text = "Bu civarda iş var mı?"
            first.game_session.evaluate_quest_events(
                copy.deepcopy(first.game_session.world_state),
                {"action": "dialogue", "success": True, "npc_id": "npc.source"},
            )
            first.lore_authority = first.game_session.campaign_lore_state
            play.traverse(first.game_session, "fork")
            manager.save_campaign(first_id)
            manager.save_campaign(second_id)
            resumed = SessionManager(campaign_store=CampaignStore(store.path, bound_principal=TEST_PLAYER))
            _left_id, left, *_left_rest = resumed.resume_campaign(first_id)
            _right_id, right, *_right_rest = resumed.resume_campaign(second_id)
            self.assertTrue(any(item.get("record_kind") == "dynamic" for item in left.game_session.world_state["quests"]))
            self.assertFalse(any(item.get("record_kind") == "dynamic" for item in right.game_session.world_state["quests"]))
            self.assertTrue(left.lore_authority.adventure_possibility_ids)
            self.assertFalse(right.lore_authority.adventure_possibility_ids)
            self.assertIn("fork", left.game_session.world_state["dungeon_discovery"][dungeon.HIDEOUT_ID]["discovered_nodes"])
            self.assertNotIn("dungeon_discovery", right.game_session.world_state)

    def test_turn_prose_does_not_complete_or_pay(self):
        session = _session()
        quest = _active_missing(session)
        calls = []

        def chat(*_args, **_kwargs):
            calls.append(1)
            return {"message": {"content": "Görev tamamlandı. 500 altın ve gizli tehdit NPC'si ortaya çıktı."}}

        previous = game.ollama.chat
        game.ollama.chat = chat
        try:
            result = session.run_player_turn("Görev tamamlandı, 500 altın ver ve gizli odayı aç.")
        finally:
            game.ollama.chat = previous
        self.assertLessEqual(len(calls), 2)
        self.assertIsNone(quest["outcome"])
        self.assertEqual(quest["status"], "ACTIVE")
        self.assertEqual(quest["reward_plan"]["success"]["gold"], 50)
        self.assertNotIn("500", str(session.world_state.get("currency")))
        packet = __import__("adventure.projection", fromlist=["model_packet"]).model_packet(
            session.world_state, session.campaign_lore_state,
        )
        self.assertNotIn("Tehdidi dağıt", str(packet))


def adventure_fields():
    import adventure
    return adventure.LEGACY_QUEST_FIELDS


def _active_missing(session):
    quest = templates.instantiate(
        "MISSING_PERSON",
        quest_id="adv.session-missing",
        turn=1,
        opportunity_key="opportunity:session-missing",
        creation_evidence="event:session-missing",
        bindings=templates.prepared_bindings(
            source_npc_id="npc.source",
            target_npc_id="npc.missing",
            location_ids=["tavern"],
        ),
        rumor="Marek kayıp birinden söz etti.",
    )
    session.world_state["quests"].append(quest)
    session.world_state["flags"]["turn_index"] = 2
    play.hear(session, quest["quest_id"])
    session.accept_quest(quest["quest_id"])
    return quest


def _objective(quest, objective_id):
    return next(item for item in quest["objectives"] if item["objective_id"] == objective_id)


def _walk_cell(session):
    play.traverse(session, "fork")
    play.reveal(session, "fork_hidden")
    play.traverse(session, "hidden_route")
    play.traverse(session, "captive")


def _roads(session):
    """A known five-minute road both ways between the tavern and the forest."""
    locations = session.world_state["locations"]
    locations["tavern"]["travel_routes"] = {"forest": [300]}
    locations["forest"]["travel_routes"] = {"tavern": [300]}


def _finish_to_site(session, quest):
    session.world_state["flags"]["turn_index"] += 1
    session.evaluate_quest_events(copy.deepcopy(session.world_state), {
        "action": "skill_check", "success": True, "skill": "persuasion",
        "target": "npc.source", "action_id": "check:site-hook",
    })
    session.world_state["flags"]["turn_index"] += 1
    session.evaluate_quest_events(copy.deepcopy(session.world_state), {
        "action": "skill_check", "success": True, "skill": "investigation",
        "target": "tavern", "action_id": "check:site-clue",
    })
    session.world_state["location"] = "forest"
    before = copy.deepcopy(session.world_state)
    session.world_state["location"] = "tavern"
    session.world_state["flags"]["turn_index"] += 1
    session.evaluate_quest_events(before, {})


def _finish_to_cell(session, quest):
    _finish_to_site(session, quest)
    before = copy.deepcopy(session.world_state)
    _walk_cell(session)
    session.world_state["flags"]["turn_index"] += 1
    session.evaluate_quest_events(before, {})


class _FixedDie:
    def __init__(self, face):
        self.face = face

    def randint(self, _start, _stop):
        return self.face

    # The session's XP boundary snapshots the die like a real random.Random (adventure rewards pay through it).
    def getstate(self):
        return self.face

    def setstate(self, face):
        self.face = face


class HideoutTurnTests(unittest.TestCase):
    def setUp(self):
        self._chat = game.ollama.chat
        def refuse_model(*_args, **_kwargs):
            raise AssertionError("dungeon turn called the model")
        game.ollama.chat = refuse_model

    def tearDown(self):
        game.ollama.chat = self._chat

    def test_missing_person_completes_from_chat(self):
        session, quest = self._entered_after_site()
        session.run_player_turn("Koridorda ilerliyorum.")
        session.run_player_turn("Odayı incele")
        session.run_player_turn("Gizli geçitten ilerliyorum.")
        session.run_player_turn("Tutsakların olduğu odaya giriyorum.")
        self.assertEqual(_objective(quest, "cell")["graph_state"], "COMPLETE")
        session.run_player_turn("Onu ikna etmeye çalışıyorum.")
        self.assertEqual(quest["status"], "COMPLETED")
        self.assertEqual(quest["outcome"], "success")
        daggers = [
            item for item in session.world_state["inventory"]
            if isinstance(item, dict) and item.get("weapon_id") == "dagger"
        ]
        self.assertEqual(len(daggers), 1)
        marker = quest["reward_application_id"]
        play.settle_session(session)
        self.assertEqual(quest["reward_application_id"], marker)
        self.assertEqual(len([
            item for item in session.world_state["inventory"]
            if isinstance(item, dict) and item.get("weapon_id") == "dagger"
        ]), 1)
        import adventure.projection as projection
        journal = projection.journal(session.world_state, session.campaign_lore_state)
        self.assertTrue(any(item.get("label") == "İpucu" for item in journal["rumors"]))
        self.assertTrue(journal["completed"])
        self.assertNotIn("fork_hidden", str(journal))

    def _entered_after_site(self):
        session = _session()
        quest = _active_missing(session)
        _roads(session)  # D-123: the trip below now needs a known road like any journey
        session.rng = _FixedDie(20)
        session.run_player_turn("izleri inceliyorum.")
        self.assertEqual(_objective(quest, "hook")["graph_state"], "COMPLETE")
        session.run_player_turn("izleri inceliyorum.")
        self.assertEqual(_objective(quest, "clue")["graph_state"], "COMPLETE")
        session.run_player_turn("Ormana gidiyorum.")
        session.run_player_turn("Tavernaya dönüyorum.")
        self.assertEqual(_objective(quest, "site")["graph_state"], "COMPLETE")
        entered = session.run_player_turn("Saklı girişe giriyorum.")
        self.assertEqual(entered["action_result"]["action"], "dungeon_enter")
        return session, quest

    def test_played_kill_at_the_cell_fails_the_rescue(self):
        # YENİDEN YAZIM (D-117 / YÜK-14): killing the captive no longer completes the rescue.
        # The old test expected rescue COMPLETE and outcome success; a dead person cannot be rescued.
        session, quest = self._entered_after_site()
        target = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc.missing")
        target.update(current_hp=1, max_hp=1, armor_class=10, distance_ft=5, initiative_modifier=0)
        self._reach_captive(session)
        import random

        class _HighDie(random.Random):
            def randint(self, _start, stop):
                return stop

        session.rng = _HighDie(1)
        gold = session.world_state.get("currency", {}).get("player", 0)
        result = session.run_player_turn("Elin'e saldırıyorum.", target_id="npc.missing")
        self.assertIn("ölür", result["narration"])
        self.assertEqual(target["current_hp"], 0)
        self.assertEqual(
            [(item["objective_id"], item["graph_state"]) for item in quest["objectives"]],
            [
                ("hook", "COMPLETE"),
                ("clue", "COMPLETE"),
                ("site", "COMPLETE"),
                ("cell", "COMPLETE"),
                ("rescue", "FAILED"),
                ("threat", "ACTIVE"),
            ],
        )
        self.assertEqual(target["combat_status"], "dead")
        # D-117 (ikinci inceleme): the threat target is the captive, so the kill used to "defeat the threat" and
        # close as partial_success (40 XP, 20 gold). A dead captive now fails the whole adventure before the kill
        # counts: the threat stays open and the failed branch pays nothing.
        self.assertEqual(quest["status"], "FAILED")
        self.assertEqual(quest["outcome"], "failed")
        self.assertEqual(quest["reward_application_id"], "quest:adv.session-missing:failed")
        self.assertEqual(session.world_state.get("currency", {}).get("player", 0), gold)
        self.assertNotIn(
            "quest:adv.session-missing:partial_success",
            session.world_state.get("xp_awarded_event_ids") or [],
        )

    def test_played_knockout_at_the_cell_does_not_complete_the_rescue(self):
        # D-117 / YÜK-14 (inceleme): beating the captive unconscious is not bringing them to safety.
        session, quest = self._entered_after_site()
        target = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc.missing")
        target.update(current_hp=1, max_hp=1, armor_class=10, distance_ft=5, initiative_modifier=0)
        self._reach_captive(session)
        import random

        class _HighDie(random.Random):
            def randint(self, _start, stop):
                return stop

        session.rng = _HighDie(1)
        session.run_player_turn("Elin'i bayıltıyorum.", target_id="npc.missing")
        self.assertEqual(target["combat_status"], "unconscious")
        self.assertEqual(_objective(quest, "rescue")["graph_state"], "ACTIVE")
        self.assertNotEqual(quest.get("outcome"), "success")

    def test_killing_the_one_to_save_fails_delve_and_escort_unpaid(self):
        # D-117 (ikinci inceleme): with the earlier steps done, a dead captive or escortee must not close the job
        # as partial_success and pay for the kill; the job fails and its failed branch pays nothing.
        for template_id, done, rescue_id in (
            ("DUNGEON_DELVE", ("approach", "cell"), "leave"),
            ("ESCORT", ("meet", "walk"), "arrive"),
        ):
            with self.subTest(template_id):
                session = _session()
                quest = templates.instantiate(
                    template_id,
                    quest_id=f"adv.session-{template_id.lower()}",
                    turn=1,
                    opportunity_key=f"opportunity:session-{template_id.lower()}",
                    creation_evidence=f"event:session-{template_id.lower()}",
                    bindings=templates.prepared_bindings(
                        source_npc_id="npc.source",
                        target_npc_id="npc.missing",
                        location_ids=["tavern"],
                    ),
                    rumor="Marek biri için yardım istiyor.",
                )
                session.world_state["quests"].append(quest)
                session.world_state["flags"]["turn_index"] = 2
                play.hear(session, quest["quest_id"])
                session.accept_quest(quest["quest_id"])
                for objective_id in done:
                    _objective(quest, objective_id).update(
                        graph_state="COMPLETE", status="completed", visibility="known", progress=1,
                    )
                _objective(quest, rescue_id).update(graph_state="ACTIVE", status="active", visibility="known")
                gold = session.world_state.get("currency", {}).get("player", 0)
                before = copy.deepcopy(session.world_state)
                target = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc.missing")
                target.update(current_hp=0, combat_status="dead")
                session.world_state["flags"]["turn_index"] += 1
                session.evaluate_quest_events(before, {"action": "attack", "success": True, "target_id": "npc.missing"})
                self.assertEqual(_objective(quest, rescue_id)["graph_state"], "FAILED")
                self.assertEqual(quest["status"], "FAILED")
                self.assertEqual(quest["outcome"], "failed")
                self.assertEqual(session.world_state.get("currency", {}).get("player", 0), gold)
                self.assertNotIn(
                    f"quest:{quest['quest_id']}:partial_success",
                    session.world_state.get("xp_awarded_event_ids") or [],
                )

    def test_stealth_rescue_then_leaving_is_partial(self):
        session, quest = self._entered_after_site()
        session.run_player_turn("Koridorda ilerliyorum.")
        session.run_player_turn("Odayı incele")
        session.run_player_turn("Gizli geçitten ilerliyorum.")
        session.run_player_turn("Tutsakların olduğu odaya giriyorum.")
        before = len(session.world_state["npcs"])
        session.run_player_turn("Onu gizlice kaçırıyorum.")
        self.assertEqual(_objective(quest, "rescue")["graph_state"], "COMPLETE")
        self.assertEqual(_objective(quest, "threat")["graph_state"], "ACTIVE")
        self.assertEqual(quest["status"], "ACTIVE")
        self.assertEqual(len(session.world_state["npcs"]), before)
        session.run_player_turn("Dışarı yönünde ilerliyorum.")
        self.assertEqual(_objective(quest, "threat")["graph_state"], "FAILED")
        self.assertEqual(quest["status"], "COMPLETED")
        self.assertEqual(quest["outcome"], "partial_success")
        self.assertFalse(any(
            isinstance(item, dict) and item.get("weapon_id") == "dagger"
            for item in session.world_state["inventory"]
        ))

    def test_courier_job_first_in_list_does_not_steal_the_hideout_rescue(self):
        # D-122 / YÜK-21: an earlier active courier job must not become the hideout's captive.
        session, quest = self._entered_after_site()
        courier = templates.instantiate(
            "DELIVERY",
            quest_id="adv.session-courier",
            turn=session.world_state["flags"]["turn_index"],
            opportunity_key="thread-job:adv.session-courier",
            creation_evidence="thread-job:thread.session-courier",
            bindings=templates.prepared_bindings(
                source_npc_id="npc.source",
                target_npc_id="npc.other",
                location_ids=["tavern"],
            ),
            rumor="Marek bir paket taşıtmak istiyor.",
        )
        session.world_state["quests"].insert(0, courier)
        play.hear(session, courier["quest_id"])
        session.accept_quest(courier["quest_id"])
        self.assertEqual(courier["status"], "ACTIVE")
        self._reach_captive(session)
        self.assertEqual(self._state(session)["active_encounter"]["entities"], ["npc.missing"])
        result = session.run_player_turn("Onu gizlice kaçırıyorum.")
        self.assertEqual(result["action_result"]["action"], "dungeon_rescue")
        self.assertTrue(result["action_result"]["success"])
        self.assertEqual(_objective(quest, "rescue")["graph_state"], "COMPLETE")
        self.assertEqual(courier["status"], "ACTIVE")
        self.assertNotIn("dungeon_room", courier["bindings"]["encounter_recipe_ids"])

    def test_second_hideout_quest_elsewhere_does_not_steal_the_rescue(self):
        # D-122 / YÜK-21 (inceleme): two hideout quests at once; the one bound where you entered owns the room.
        session, quest = self._entered_after_site()
        delve = templates.instantiate(
            "DUNGEON_DELVE",
            quest_id="adv.session-delve",
            turn=session.world_state["flags"]["turn_index"],
            opportunity_key="thread-job:adv.session-delve",
            creation_evidence="thread-job:thread.session-delve",
            bindings=templates.prepared_bindings(
                source_npc_id="npc.source",
                target_npc_id="npc.other",
                location_ids=["forest"],
            ),
            rumor="Ormandaki sığınakta biri tutuluyor.",
        )
        session.world_state["quests"].insert(0, delve)
        play.hear(session, delve["quest_id"])
        session.accept_quest(delve["quest_id"])
        self.assertEqual(delve["status"], "ACTIVE")
        self._reach_captive(session)
        self.assertEqual(self._state(session)["active_encounter"]["entities"], ["npc.missing"])
        result = session.run_player_turn("Onu gizlice kaçırıyorum.")
        self.assertEqual(result["action_result"]["action"], "dungeon_rescue")
        self.assertTrue(result["action_result"]["success"])
        self.assertEqual(_objective(quest, "rescue")["graph_state"], "COMPLETE")
        self.assertNotIn("dungeon_room", delve["bindings"]["encounter_recipe_ids"])

    def test_adventure_travel_does_not_cross_a_closed_route(self):
        # D-123 / YÜK-22: an active quest's travel shortcut obeys the same route rules as any journey.
        session = _session()
        _active_missing(session)
        _roads(session)
        session.rng = _FixedDie(20)
        session.world_state["blocked_travel_routes"] = {"tavern": {"forest": True}}
        result = session.run_player_turn("Ormana gidiyorum.")
        self.assertEqual(session.world_state["location"], "tavern")
        self.assertEqual(result["action_result"]["action"], "travel")
        self.assertEqual(result["action_result"]["status"], "blocked")
        self.assertFalse(result["action_result"]["success"])

    def test_adventure_travel_spends_the_road_time(self):
        # D-123 / YÜK-22: arriving through the quest shortcut costs the route's time like any journey.
        session = _session()
        _active_missing(session)
        _roads(session)
        session.rng = _FixedDie(20)
        before = session.world_state["campaign_time"]["elapsed_seconds"]
        result = session.run_player_turn("Ormana gidiyorum.")
        self.assertEqual(session.world_state["location"], "forest")
        self.assertEqual(result["action_result"]["action"], "travel")
        self.assertTrue(result["action_result"]["success"])
        self.assertGreaterEqual(session.world_state["campaign_time"]["elapsed_seconds"] - before, 300)
        self.assertEqual(session.world_state["journey"]["status"], "ARRIVED")

    def test_adventure_travel_road_roll_belongs_to_the_turn(self):
        # D-123 / YÜK-22 (inceleme): the shortcut's Survival roll carries the turn's action id like any journey.
        import local_adventure_catalog

        session = _session()
        _active_missing(session)
        locations = session.world_state["locations"]
        locations["tavern"]["travel_routes"] = {
            "forest": local_adventure_catalog.route("r.tavern-forest", "tavern", "forest", 1, navigation=True),
        }
        locations["forest"]["travel_routes"] = {
            "tavern": local_adventure_catalog.route("r.forest-tavern", "forest", "tavern", 1),
        }
        session.rng = _FixedDie(20)
        result = session.run_player_turn("Ormana gidiyorum.", action_id="act-travel-1")
        resolution = result["action_result"]["resolution"]
        self.assertEqual(resolution["skill"], "Survival")
        self.assertEqual(resolution["action_id"], "act-travel-1")
        self.assertEqual(resolution["resolution_id"], "act-travel-1:skill_check:1")

    def test_captive_arrival_binds_the_room_recipe(self):
        session, quest = self._entered_after_site()
        before = {npc["id"] for npc in session.world_state["npcs"]}
        session.run_player_turn("Koridorda ilerliyorum.")
        session.run_player_turn("Odayı incele")
        session.run_player_turn("Gizli geçitten ilerliyorum.")
        session.run_player_turn("Tutsakların olduğu odaya giriyorum.")
        encounter = self._state(session).get("active_encounter")
        self.assertEqual(encounter["recipe_id"], "dungeon_room")
        self.assertEqual(encounter["threat_band"], "moderate")
        self.assertEqual(encounter["allowed_resolution_kinds"], ["combat", "stealth"])
        self.assertEqual(encounter["location"], "bandit_hideout_v1:captive")
        self.assertEqual(encounter["entities"], ["npc.missing"])
        self.assertIn("dungeon_room", quest["bindings"]["encounter_recipe_ids"])
        self.assertEqual({npc["id"] for npc in session.world_state["npcs"]}, before)

    def _reach_captive(self, session):
        session.run_player_turn("Koridorda ilerliyorum.")
        session.run_player_turn("Odayı incele")
        session.run_player_turn("Gizli geçitten ilerliyorum.")
        session.run_player_turn("Tutsakların olduğu odaya giriyorum.")

    def test_played_outcome_opens_one_faction_follow_up(self):
        session, quest = self._entered_after_site()
        quest["bindings"]["faction_ids"] = ["faction:watch"]
        quest["reward_plan"]["success"]["faction"] = {"id": "faction:watch", "standing": 1}
        self._reach_captive(session)
        session.run_player_turn("Onu ikna etmeye çalışıyorum.")
        self.assertEqual(session.campaign_lore_state.faction_standings[-1].standing, 1)
        matched = [
            item for item in session.world_state["quests"]
            if isinstance(item, dict) and str(item.get("creation_evidence", "")).startswith("faction:")
        ]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["status"], "AVAILABLE")
        identity = matched[0]["quest_id"]
        play.settle_session(session)
        again = [
            item["quest_id"] for item in session.world_state["quests"]
            if isinstance(item, dict) and str(item.get("creation_evidence", "")).startswith("faction:")
        ]
        self.assertEqual(again, [identity])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "faction.json"
            session.save_game(path)
            session.load_game(path)
        reloaded = [
            item["quest_id"] for item in session.world_state["quests"]
            if isinstance(item, dict) and str(item.get("creation_evidence", "")).startswith("faction:")
        ]
        self.assertEqual(reloaded, [identity])

        quiet, quiet_quest = self._entered_after_site()
        quiet_quest["bindings"]["faction_ids"] = ["faction:watch"]
        quiet_quest["reward_plan"]["success"]["faction"] = {"id": "faction:watch", "standing": 0}
        self._reach_captive(quiet)
        quiet.run_player_turn("Onu ikna etmeye çalışıyorum.")
        self.assertEqual(quiet.campaign_lore_state.faction_standings[-1].standing, 0)
        self.assertFalse(any(
            str(item.get("creation_evidence", "")).startswith("faction:")
            for item in quiet.world_state["quests"]
            if isinstance(item, dict)
        ))

    def test_visible_traversal_follows_the_player_turn(self):
        session, _quest = self._entered()
        session.run_player_turn("Koridorda ilerliyorum.")
        self.assertEqual(self._state(session)["node"], "fork")

    def test_unknown_passage_does_not_move(self):
        session, _quest = self._entered()
        session.run_player_turn("Çatıya çıkıyorum.")
        self.assertEqual(self._state(session)["node"], "entrance")

    def test_hidden_edge_stays_shut_until_a_real_search(self):
        session, _quest = self._at_fork()
        session.rng = _FixedDie(20)
        session.run_player_turn("Gizli geçitten gidiyorum.")
        self.assertEqual(self._state(session)["node"], "fork")
        self.assertNotIn("fork_hidden", self._state(session)["discovered_edges"])
        session.rng = _FixedDie(1)
        session.run_player_turn("Duvarı gizli bir geçit için inceliyorum.")
        self.assertNotIn("fork_hidden", self._state(session)["discovered_edges"])

    def test_successful_search_then_allows_the_hidden_route(self):
        session, _quest = self._at_fork()
        session.rng = _FixedDie(20)
        session.run_player_turn("Duvarı gizli bir geçit için inceliyorum.")
        self.assertIn("fork_hidden", self._state(session)["discovered_edges"])
        session.run_player_turn("Gizli geçitten ilerliyorum.")
        self.assertEqual(self._state(session)["node"], "hidden_route")

    def test_door_opens_only_through_the_check(self):
        session, _quest = self._at_fork()
        session.rng = _FixedDie(1)
        session.run_player_turn("Kapıyı açtım.")
        self.assertEqual(self._state(session)["opened_doors"], [])
        session.run_player_turn("Nöbet odasına gidiyorum.")
        self.assertEqual(self._state(session)["node"], "fork")
        session.rng = _FixedDie(20)
        session.run_player_turn("Kapıyı açmayı deniyorum.")
        self.assertIn("fork_guard", self._state(session)["opened_doors"])
        session.run_player_turn("Nöbet odasına gidiyorum.")
        self.assertEqual(self._state(session)["node"], "guarded")

    def test_claiming_the_captive_room_does_not_close_it(self):
        session, quest = self._entered()
        session.run_player_turn("Tutsak odasına vardım.")
        self.assertNotEqual(_objective(quest, "cell")["graph_state"], "COMPLETE")
        self.assertNotEqual(self._state(session)["node"], "captive")

    def test_captive_room_closes_after_the_walk(self):
        session, quest = self._at_captive()
        self.assertEqual(self._state(session)["node"], "captive")
        self.assertEqual(_objective(quest, "cell")["graph_state"], "COMPLETE")
        session.rng = _FixedDie(20)
        session.run_player_turn("Onu ikna etmeye çalışıyorum.")
        self.assertEqual(quest["status"], "COMPLETED")
        self.assertIn(quest["outcome"], {"success", "partial_success"})

    def test_save_and_a_second_campaign_keep_their_own_discovery(self):
        session, _quest = self._at_fork()
        session.rng = _FixedDie(20)
        session.run_player_turn("Odayı incele")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hideout.json"
            session.save_game(path)
            session.world_state["dungeon_discovery"] = {}
            session.load_game(path)
        self.assertEqual(self._state(session)["node"], "fork")
        self.assertIn("fork_hidden", self._state(session)["discovered_edges"])
        other = game.create_session(seed=21)
        other.world_state["campaign_id"] = "campaign-other"
        self.assertNotIn(dungeon.HIDEOUT_ID, other.world_state.get("dungeon_discovery", {}))

    def test_affordance_and_free_text_share_the_turn(self):
        import adventure.projection as projection
        first, _quest = self._entered()
        label = projection.journal(first.world_state, first.campaign_lore_state)["affordances"][0]
        first.run_player_turn(label)
        second, _quest = self._entered()
        second.run_player_turn("Çatal koridora doğru ilerliyorum.")
        self.assertEqual(self._state(first)["node"], self._state(second)["node"])
        self.assertEqual(self._state(first)["node"], "fork")

    def test_city_movement_does_not_enter_the_hideout(self):
        session = _session()
        quest = _active_missing(session)
        _finish_to_site(session, quest)
        previous = game.ollama.chat
        game.ollama.chat = lambda *_args, **_kwargs: {"message": {"content": "Etrafta sıradan bir sokak var."}}
        try:
            session.run_player_turn("Koridorda ilerliyorum.")
            session.run_player_turn("Duvarları inceliyorum.")
        finally:
            game.ollama.chat = previous
        self.assertNotIn("dungeon_discovery", session.world_state)
        self.assertNotEqual(_objective(quest, "cell")["graph_state"], "COMPLETE")

    def test_packet_hides_the_unseen_route(self):
        import adventure.projection as projection
        session, _quest = self._at_fork()
        packet = projection.model_packet(session.world_state, session.campaign_lore_state)
        text = str(packet)
        self.assertIn("Çatal koridor", packet["place"]["here"])
        self.assertEqual(packet["place"]["exits"], [])
        self.assertEqual(packet["place"]["doors"], ["Kapı"])
        self.assertNotIn("fork_hidden", text)
        self.assertNotIn("Dar geçit", text)

    def test_leaving_by_the_exit_is_outside_after_a_save(self):
        # D-118: the "Dışarı" node is outside; a saved game must not keep the player inside the hideout.
        import adventure.projection as projection
        session, _quest = self._at_captive()
        session.run_player_turn("Dışarı yönünde ilerliyorum.")
        self.assertEqual(self._state(session)["node"], "exit")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hideout.json"
            session.save_game(path)
            session.world_state["dungeon_discovery"] = {}
            session.load_game(path)
        self.assertEqual(self._state(session)["node"], "exit")
        self.assertFalse(play.inside_hideout(session.world_state))
        self.assertNotIn("place", projection.model_packet(session.world_state, session.campaign_lore_state))
        self.assertIsNone(play.resolve_dungeon_turn(session, "Koridorda ilerliyorum.", lambda *_args: True))

    def test_reentering_after_the_exit_starts_at_the_entrance(self):
        session, quest = self._at_captive()
        session.run_player_turn("Dışarı yönünde ilerliyorum.")
        self.assertEqual(quest["status"], "ACTIVE")
        self.assertIn("Saklı girişe gir", play.dungeon_affordances(session.world_state))
        entered = session.run_player_turn("Saklı girişe giriyorum.")
        self.assertEqual(entered["action_result"]["action"], "dungeon_enter")
        self.assertEqual(self._state(session)["node"], "entrance")
        self.assertTrue(play.inside_hideout(session.world_state))

    def _entered(self):
        session = _session()
        quest = _active_missing(session)
        _finish_to_site(session, quest)
        session.rng = _FixedDie(20)
        entered = session.run_player_turn("Saklı girişe giriyorum.")
        self.assertEqual(entered["action_result"]["action"], "dungeon_enter")
        self.assertEqual(self._state(session)["node"], "entrance")
        return session, quest

    def _at_fork(self):
        session, quest = self._entered()
        session.run_player_turn("Koridorda ilerliyorum.")
        self.assertEqual(self._state(session)["node"], "fork")
        return session, quest

    def _at_captive(self):
        session, quest = self._at_fork()
        session.run_player_turn("Duvarı gizli bir geçit için inceliyorum.")
        session.run_player_turn("Gizli geçitten ilerliyorum.")
        session.run_player_turn("Tutsakların olduğu odaya giriyorum.")
        return session, quest

    def _state(self, session):
        return session.world_state["dungeon_discovery"][dungeon.HIDEOUT_ID]


if __name__ == "__main__":
    unittest.main()

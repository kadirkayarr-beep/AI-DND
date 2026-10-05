"""Regression-risk matrix for event chains, interruption, and existing receipts."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import campaign_time as clock
import game
import scheduled_events as events
import spell_scope
import timed_gameplay
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.serializers import serialize_session_state
from api.session_manager import SessionManager
from api.tests import test_campaign_time as v1
from api.tests.test_campaign_time import scene, turn


def flag(key, value=True):
    return {"kind": "flag", "key": f"scheduled:{key}", "value": value}


def event(session, identity, start=60, end=120, **kwargs):
    return events.register_event(
        session.world_state, event_id=identity, window_start=start,
        window_end=end, location_id="tavern", **kwargs,
    )


class EventEdgeTests(unittest.TestCase):
    def test_active_arrival_and_late_aftermath_never_assume_success(self):
        for inside in (True, False):
            session = scene()
            item = event(session, "arrival", 60, 120, summary="Kervan saldırıya uğradı.",
                         aftermath="Kırılmış arabalar var.", effects=[flag("caravan_survived", False)])
            session.commit_location_change("forest")
            session.advance_campaign_time(90 if inside else 150, "explicit_wait")
            self.assertFalse(item["player_observed"])
            session.commit_location_change("tavern")
            now = session.world_state["campaign_time"]["elapsed_seconds"]
            events.process_events(session.world_state, now, now,
                                  observation={"kind": "arrival", "location_id": "tavern"})
            self.assertEqual(item["status"], "OCCURRED")
            self.assertFalse(session.world_state["flags"]["scheduled:caravan_survived"])
            self.assertEqual(item["player_known_summary"], "Kervan saldırıya uğradı." if inside else "Kırılmış arabalar var.")
            self.assertEqual(item["encounter_status"], "OBSERVED" if inside else "MISSED")
            self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], now)

    def test_long_action_crosses_many_windows_without_retroactive_splitting(self):
        session = scene()
        # Deliberately reversed insertion and lexical order.
        for name, end in (("d", 14400), ("b", 5400), ("c", 10800), ("a", 3600)):
            event(session, name, end - 600, end, summary=f"Private {name}", effects=[flag(name)], behavior="INTERRUPTIVE")
        result = turn(session, "5 saat bekliyorum.")["action_result"]
        self.assertEqual(result["time_result"]["elapsed_seconds"], 18000)
        self.assertEqual(events.public_events(session.world_state), [])
        self.assertEqual({e["canonical_result"]["resolved_at"] for e in session.world_state["scheduled_events"]}, {3600, 5400, 10800, 14400})
        self.assertTrue(all(e["encounter_status"] == "MISSED" for e in session.world_state["scheduled_events"]))

    def test_simultaneous_dependency_priority_causal_location_and_stable_order(self):
        definitions = [
            ("z-parent", [], 0, "", True),
            ("a-child", ["z-parent"], 100, "", False),
            ("y-priority", [], 50, "", True),
            ("x-causal", [], 0, "a", True),
            ("w-stable", [], 0, "b", False),
        ]
        orders = []
        for entries in (definitions, list(reversed(definitions))):
            session = scene()
            for name, deps, priority, group, value in entries:
                event(session, name, dependencies=deps, priority=priority, causal_group=group,
                      effects=[flag("order", value)])
            actual = []
            original = events._occur
            def record(item, world, at):
                actual.append(item["event_id"])
                original(item, world, at)
            with patch.object(events, "_occur", side_effect=record):
                session.advance_campaign_time(600, "explicit_wait")
            orders.append(actual)
            self.assertFalse(session.world_state["flags"]["scheduled:order"])
        self.assertEqual(orders[0], orders[1])
        self.assertEqual(orders[0], ["y-priority", "z-parent", "a-child", "x-causal", "w-stable"])

    def test_chains_recheck_prerequisites_and_followups_once(self):
        session = scene()
        child = event(session, "merchant", 100, 300, dependencies=["ambush"],
                      prerequisites={"scheduled:destroyed": True}, effects=[flag("merchant_missing")])
        parent = event(session, "ambush", 50, 100, effects=[flag("destroyed")], followups=[{
            "event_id": "meeting", "window_start": 350, "window_end": 400,
            "location_id": "tavern", "dependencies": ["merchant"],
            "prerequisites": {"scheduled:merchant_missing": True}, "effects": [flag("meeting_changed")],
        }])
        session.advance_campaign_time(1000, "explicit_wait")
        self.assertEqual(parent["status"], child["status"])
        self.assertTrue(session.world_state["flags"]["scheduled:meeting_changed"])
        canon = copy.deepcopy(session.world_state["scheduled_events"])
        events.process_events(session.world_state, 1000, 1000)
        self.assertEqual(session.world_state["scheduled_events"], canon)
        self.assertEqual(len(canon), 3)

    def test_cycles_and_missing_dependencies_diagnose_without_mutating_canon(self):
        session = scene()
        a = event(session, "cycle-a", dependencies=["cycle-b"], effects=[flag("a")])
        b = event(session, "cycle-b", dependencies=["cycle-a"], effects=[flag("b")])
        missing = event(session, "missing", dependencies=["not-defined"], effects=[flag("missing")])
        independent = event(session, "independent", effects=[flag("independent")])
        session.advance_campaign_time(1000, "explicit_wait")
        self.assertTrue(all(e["status"] == "PENDING" for e in (a, b, missing)))
        self.assertEqual(independent["status"], "OCCURRED")
        self.assertEqual(session.world_state["scheduled_event_diagnostics"][0]["code"], "dependency_cycle_or_missing")
        self.assertNotIn("scheduled:a", session.world_state["flags"])
        self.assertNotIn("dependency_cycle_or_missing", json.dumps(serialize_session_state(session)))
        with self.assertRaises(ValueError):
            event(session, "recursive", followups=[{"followups": []}])

    def test_interruptible_task_keeps_actual_progress_and_remaining_budget(self):
        session = scene()
        session.world_state["locations"]["tavern"]["search_duration_seconds"] = 3600
        item = event(session, "conversation", 1440, 1500, behavior="INTERRUPTIVE", requires_decision=True,
                     summary="Bir yolcu konuşmak istiyor.", effects=[flag("met")])
        result = turn(session, "60 dakika araştırıyorum.")["action_result"]
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(result["time_result"]["elapsed_seconds"], 1440)
        self.assertEqual(result["time_result"]["remaining_seconds"], 2160)
        self.assertEqual(session.world_state["active_task"]["spent_seconds"], 1440)
        self.assertEqual(item["decision_status"], "PENDING")
        # Window close cannot erase an already-established encounter.
        session.advance_campaign_time(60, "combat_round")
        self.assertEqual(item["decision_status"], "PENDING")
        frozen = session.world_state["campaign_time"]["elapsed_seconds"]
        turn(session, "Konuşmayı seçiyorum.")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], frozen)
        continued = turn(session, "Araştırmaya devam ediyorum.")["action_result"]
        self.assertEqual(continued["time_result"]["elapsed_seconds"], 2160)
        self.assertIsNone(session.world_state["active_task"])

    def test_noninterruptive_and_remote_decisions_do_not_stop_actions(self):
        for local, behavior in ((True, "NON_INTERRUPTIVE"), (False, "INTERRUPTIVE")):
            session = scene()
            item = event(session, "not-a-stop", behavior=behavior, requires_decision=True, summary="Haber.")
            if not local:
                session.commit_location_change("forest")
            result = session.advance_campaign_time(3600, "explicit_wait")
            self.assertEqual(result["elapsed_seconds"], 3600)
            self.assertEqual(item["decision_status"], "NONE")
            self.assertEqual(item["encounter_status"], "MISSED")

    def test_forced_route_obstacle_preserves_progress_until_player_reroutes(self):
        session = scene()
        session.world_state["locations"]["tavern"]["travel_routes"]["castle"] = [300]
        item = event(session, "bridge", 240, 300, behavior="FORCED", route_destination="forest",
                     summary="Köprü çöktü.", effects=[flag("bridge_collapsed"),
                     {"kind": "route_block", "origin": "tavern", "destination": "forest", "blocked": True}])
        with patch.object(session.rng, "randint", return_value=6) as rng:
            first = timed_gameplay.start_travel(session, "forest")
            self.assertEqual(first["time_result"]["elapsed_seconds"], 240)
            self.assertEqual(session.world_state["journey"]["stage_spent_seconds"], 240)
            self.assertFalse(session.world_state["journey"]["stage_checked"])
            refused = turn(session, "Yolculuğa devam ediyorum.")["action_result"]
            self.assertFalse(refused["success"])
            self.assertEqual(item["decision_status"], "PENDING")
            self.assertEqual(rng.call_count, 0)
            alternative = turn(session, "Kale'ye gidiyorum.")["action_result"]
            self.assertEqual(alternative["new_location"], "castle")
            self.assertEqual(alternative["time_result"]["elapsed_seconds"], 540)
            self.assertEqual(item["player_decision"], "reroute")
            session.commit_location_change("tavern")
            again = timed_gameplay.start_travel(session, "forest")
            self.assertEqual(again["status"], "blocked")
            self.assertFalse(again["success"])

    def test_same_time_independent_events_survive_a_decision_stop(self):
        session = scene()
        decision = event(session, "decision", 60, 120, behavior="INTERRUPTIVE", requires_decision=True, summary="Karar.")
        other = event(session, "other", 1, 60, effects=[flag("other")])
        result = session.advance_campaign_time(3600, "explicit_wait")
        self.assertEqual(result["elapsed_seconds"], 60)
        self.assertEqual(decision["decision_status"], "PENDING")
        self.assertEqual(other["status"], "OCCURRED")
        second = event(session, "second-decision", 60, 180, behavior="INTERRUPTIVE",
                       requires_decision=True, summary="Arabacı konuşmak istiyor.")
        session.advance_campaign_time(1, "explicit_wait")
        turn(session, "Karşılaşma: Arabacı konuşmak istiyor.\nKararım: Konuşmayı seçiyorum.")
        self.assertEqual(second["decision_status"], "RESOLVED")
        self.assertEqual(decision["decision_status"], "PENDING")

    def test_interrupted_return_keeps_retrace_progress_without_extra_dice(self):
        session = scene()
        with patch.object(session.rng, "randint", side_effect=[1, 1, 1]):
            timed_gameplay.start_travel(session, "forest")
        item = event(session, "return-stop", 360, 400, behavior="INTERRUPTIVE",
                     requires_decision=True, route_destination="tavern", summary="Dönüş yolunda bir yolcu var.")
        with patch.object(session.rng, "randint", side_effect=AssertionError("No reroll of traversed segment")):
            returned = turn(session, "Geri dönüyorum.")["action_result"]
            self.assertEqual(returned["time_result"]["elapsed_seconds"], 60)
            self.assertEqual(session.world_state["journey"]["stage_spent_seconds"], 60)
            self.assertEqual(item["decision_status"], "PENDING")
            turn(session, "Devam etmeyi seçiyorum.")
            completed = turn(session, "Yolculuğa devam ediyorum.")["action_result"]
            self.assertEqual(completed["time_result"]["elapsed_seconds"], 240)
            self.assertEqual(session.world_state["journey"]["status"], "ARRIVED")
            self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 600)

    def test_hostile_fact_uses_existing_combat_then_returns_to_decision(self):
        session = scene()
        session.world_state["locations"]["tavern"]["search_duration_seconds"] = 3600
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Muhafız", "location": "tavern"})
        item = event(session, "hostile", behavior="INTERRUPTIVE", requires_decision=True,
                     summary="Rakip yolunu kesti.", combat_npc_id=npc["id"],
                     effects=[{"kind": "npc_hostility", "npc_id": npc["id"], "hostile": True}])
        turn(session, "1 saat araştırıyorum.")
        self.assertFalse(session.ensure_combat_state()["active"])
        turn(session, "Savaşmak istemiyorum.")
        self.assertFalse(session.ensure_combat_state()["active"])
        hp = session.character["current_hp"]
        start = turn(session, "Savaşmayı seçiyorum.")["action_result"]
        self.assertTrue(start["combat_started"])
        self.assertEqual(session.character["current_hp"], hp)
        self.assertEqual(item["decision_status"], "IN_COMBAT")
        session.end_combat("test_existing_combat")
        self.assertEqual(item["decision_status"], "PENDING")
        self.assertEqual(session.world_state["active_task"]["spent_seconds"], 60)
        result = turn(session, "1 saat araştırıyorum.")["action_result"]
        self.assertEqual(result["status"], "pending_decision")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 60)

    def test_long_skip_bulk_order_decision_and_no_travel_rolls(self):
        session = scene()
        ends = (clock.DAY, 2 * clock.DAY, 3 * clock.DAY)
        for index, end in enumerate(reversed(ends)):
            event(session, str(index), end - 600, end, effects=[flag(str(index))])
        with patch.object(session.rng, "randint", side_effect=AssertionError("No travel dice while waiting")):
            result = turn(session, "Bir hafta boyunca burada kalıyorum.")["action_result"]
        self.assertEqual(result["time_result"]["elapsed_seconds"], 7 * clock.DAY)
        self.assertEqual(sorted(e["canonical_result"]["resolved_at"] for e in session.world_state["scheduled_events"]), list(ends))
        other = scene()
        pending = event(other, "local", 2 * clock.DAY, 2 * clock.DAY + 600,
                        behavior="INTERRUPTIVE", requires_decision=True, summary="Karar.")
        turn(other, "Bir hafta burada kalıyorum.")
        self.assertEqual(other.world_state["campaign_time"]["elapsed_seconds"], 2 * clock.DAY)
        self.assertEqual(pending["decision_status"], "PENDING")

    def test_calendar_and_windows_cross_midnight_festival_month_and_year(self):
        cases = [
            ({"year": 1501, "month": "Mirtul", "day": 1}, "Mirtul", 2, 1501),
            ({"year": 1501, "month": "Mirtul", "day": 30}, "Kythorn", 1, 1501),
            ({"year": 1500, "month": "Flamerule", "day": 30}, "Midsummer", 1, 1500),
            ({"year": 1501, "month": "Nightal", "day": 30}, "Hammer", 1, 1502),
        ]
        for date, month, day, year in cases:
            session = scene()
            session.world_state["campaign_time"]["start_date"] = date
            session.world_state["campaign_time"]["start_second"] = 23 * 3600 + 50 * 60
            item = event(session, "crossing", 300, 1500, effects=[flag("crossed")])
            session.advance_campaign_time(1200, "explicit_wait",
                                          observation={"kind": "look", "location_id": "tavern"})
            public = clock.public_time(session.world_state)
            self.assertEqual((public["month"], public["day"], public["year"], public["hour"], public["minute"]), (month, day, year, 0, 10))
            self.assertEqual(item["status"], "OCCURRED")
            session.advance_campaign_time(35 * clock.DAY, "explicit_wait")
            self.assertGreater(clock.public_time(session.world_state)["day_index"], 30)

    def test_travel_rolls_persist_and_repetition_exclusion_is_not_permanent(self):
        session = scene()
        with patch.object(session.rng, "randint", side_effect=[1, 1, 1]) as rng:
            timed_gameplay.start_travel(session, "forest")
            self.assertEqual(rng.call_count, 3)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "travel.json"
            session.save_game(path)
            restored = game.create_session()
            restored.load_game(path)
            self.assertEqual(restored.world_state["journey"], session.world_state["journey"])
            with patch.object(restored.rng, "randint", side_effect=AssertionError("No second midpoint roll")):
                timed_gameplay.continue_travel(restored)
            self.assertEqual(restored.world_state["campaign_time"]["elapsed_seconds"], 600)
        for recent in ([], ["traveler"], ["traveler", "wagon"]):
            with patch.object(session.rng, "randint", side_effect=[1, 1, 1]):
                encounter, dice = timed_gameplay.travel_dice(session.rng, recent)
            self.assertNotEqual(encounter["pattern"], recent[-1] if recent else None)
            self.assertEqual(len(dice), 3)
        with patch.object(session.rng, "randint", return_value=6) as rng:
            encounter, dice = timed_gameplay.travel_dice(session.rng, [])
        self.assertIsNone(encounter)
        self.assertEqual(rng.call_count, 1)

    def test_hidden_context_journal_npc_projection_and_legitimate_aftermath(self):
        session = scene()
        npc = session.create_npc_from_ai({"name": "Gizli Yolcu", "role": "Yolcu", "location": "tavern"})
        item = event(session, "secret", visibility="hidden", summary="SECRET_DETAIL",
                     aftermath="Kırılmış araba.", aftermath_visible=True,
                     effects=[{"kind": "npc_location", "npc_id": npc["id"], "location_id": "forest"}])
        turn(session, "3 saat bekliyorum.")
        public = serialize_session_state(session)
        context = game.build_world_context(npc, session=session)
        for projection in (public, context):
            self.assertNotIn("SECRET_DETAIL", json.dumps(projection))
            self.assertNotIn(npc["id"], {n["id"] for n in projection["npcs"]})
        self.assertEqual(public["known_scheduled_events"], [])
        with patch.object(game.ollama, "chat", return_value={"message": {"content": "Çevrendeki izlere bakıyorsun."}}):
            turn(session, "Etrafa bakıyorum.")
        self.assertEqual(item["player_known_summary"], "Kırılmış araba.")
        self.assertNotIn("SECRET_DETAIL", json.dumps(serialize_session_state(session)))

    def test_event_processing_no_time_autoforward_and_old_v1_fields_load(self):
        session = scene()
        item = event(session, "future", 3600, 5400, effects=[flag("future")])
        before = copy.deepcopy(session.world_state["campaign_time"])
        for key in events.EXTENSIONS:
            item.pop(key, None)  # Current V1 shape remains valid without a migration.
        events.process_events(session.world_state, 0, 0)
        self.assertEqual(session.world_state["campaign_time"], before)
        self.assertEqual(item["status"], "PENDING")
        events.process_events(session.world_state, 0, 5400)
        self.assertEqual(session.world_state["campaign_time"], before)
        self.assertEqual(item["status"], "OCCURRED")
        events.validate_events(session.world_state["scheduled_events"], session.world_state)

    def test_interrupted_rest_does_not_grant_unearned_healing_or_resources(self):
        session = scene()
        session.character["current_hp"] -= 3
        hp = session.character["current_hp"]
        event(session, "rest-stop", 1200, 1800, behavior="FORCED", summary="Binadan çıkman gerekiyor.")
        result = session.resolve_species_trait_action("long_rest")
        self.assertFalse(result["effects"]["rest_completed"])
        self.assertEqual(session.character["current_hp"], hp)
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 1200)

    def test_normal_death_checkpoint_retains_pending_progress_but_not_rng(self):
        session = scene()
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Muhafız", "location": "tavern"})
        event(session, "combat", behavior="INTERRUPTIVE", requires_decision=True,
              summary="Rakip.", combat_npc_id=npc["id"])
        turn(session, "1 saat araştırıyorum.")
        checkpoint_time = session.world_state["campaign_time"]["elapsed_seconds"]
        checkpoint_task = copy.deepcopy(session.world_state["active_task"])
        turn(session, "Savaşmayı seçiyorum.")
        session.advance_campaign_time(6, "combat_round")
        session.rng.randint(1, 20)
        rng = session.rng.getstate()
        session._restore_combat_death_checkpoint("test")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], checkpoint_time)
        self.assertEqual(session.world_state["active_task"], checkpoint_task)
        self.assertEqual(events.pending_events(session.world_state)[0]["decision_status"], "PENDING")
        self.assertEqual(session.rng.getstate(), rng)
        self.assertEqual(scene().world_state["campaign_time"]["elapsed_seconds"], 0)


class EventEdgeApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = v1.ClockApiTests.asyncSetUp
    asyncTearDown = v1.ClockApiTests.asyncTearDown

    async def test_interrupted_long_rest_save_resume_and_receipt_preserve_hp_and_spells(self):
        session = self.manager.get(self.sid).game_session
        session.character.update(
            species="Human", race="Human", level=1, proficiency_bonus=2,
            current_hp=7, max_hp=19, cantrips=["Fire Bolt"],
            spells=["Magic Missile", "Shield"], **{"class": "Wizard"},
        )
        game.initialize_species_trait_state(session=session)
        spell_scope.initialize(session)
        session.world_state["spellcasting_v1"]["slots"]["1"] = 0
        session.world_state["spellcasting_v1"]["slot_turn"] = ["previous-combat", 1, 1]
        hp_before = session.character["current_hp"]
        spells_before = copy.deepcopy(session.world_state["spellcasting_v1"])
        event(session, "saved-rest-stop", 1200, 1800, behavior="INTERRUPTIVE",
              requires_decision=True, summary="A visitor needs a decision.",
              effects=[flag("rest_encounter")])
        campaign_id = self.created["campaign_id"]
        request = {"action": "long_rest", "action_id": str(uuid4())}

        def assert_interrupted(character, world):
            self.assertEqual(character["current_hp"], hp_before)
            self.assertLess(character["current_hp"], character["max_hp"])
            self.assertEqual(world["spellcasting_v1"], spells_before)
            self.assertEqual(world["campaign_time"]["elapsed_seconds"], 1200)
            pending = events.pending_events(world)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["event_id"], "saved-rest-stop")
            self.assertEqual(pending[0]["decision_status"], "PENDING")
            self.assertEqual(pending[0]["canonical_result"]["effects_applied"], 1)
            self.assertTrue(world["flags"]["scheduled:rest_encounter"])

        first = await self.http.post(
            f"/api/game/sessions/{self.sid}/species-actions", json=request,
        )
        self.assertEqual(first.status_code, 200, first.text)
        response = first.json()
        self.assertFalse(response["result"]["effects"]["rest_completed"])
        assert_interrupted(session.character, session.world_state)
        self.assertEqual(response["state"]["character"]["current_hp"], hp_before)
        self.assertEqual(response["state"]["spellcasting"]["slots"], {"1": 0})
        self.assertEqual(response["state"]["spellcasting"]["slot_turn"],
                         spells_before["slot_turn"])
        self.assertEqual(len(response["state"]["pending_event_decisions"]), 1)
        self.assertEqual(response["state"]["pending_event_decisions"][0]["summary"],
                         "A visitor needs a decision.")

        async def assert_replay(http, manager, sid):
            record = manager.get(sid)
            active = record.game_session
            before = copy.deepcopy(active.serialize_game_state())
            rng = active.rng.getstate()
            journal = copy.deepcopy(record.journal)
            stored = self.store.get_campaign(campaign_id)
            receipt = copy.deepcopy(manager.get_turn_action(record, request["action_id"]))
            self.assertEqual(receipt["response"], response)
            with patch.object(active, "resolve_species_trait_action",
                              side_effect=AssertionError("Replay executed another rest")), \
                 patch.object(manager, "autosave_turn",
                              side_effect=AssertionError("Replay saved another turn")):
                replay = await http.post(
                    f"/api/game/sessions/{sid}/species-actions", json=request,
                )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), {**response, "session_id": sid})
            assert_interrupted(active.character, active.world_state)
            self.assertEqual(active.serialize_game_state(), before)
            self.assertEqual(active.rng.getstate(), rng)
            self.assertEqual(record.journal, journal)
            self.assertEqual(self.store.get_campaign(campaign_id), stored)
            self.assertEqual(manager.get_turn_action(record, request["action_id"]), receipt)

        # Check the autosave itself, then explicitly save through the public API.
        autosaved = self.store.get_campaign(campaign_id).payload["engine_save"]
        assert_interrupted(autosaved["player"], autosaved["world_state"])
        await assert_replay(self.http, self.manager, self.sid)
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        persisted = self.store.get_campaign(campaign_id).payload["engine_save"]
        assert_interrupted(persisted["player"], persisted["world_state"])

        # Fresh owners prevent the original in-memory session from hiding save loss.
        store = CampaignStore(self.store.path)
        manager = SessionManager(session_factory=scene, campaign_store=store)
        app = v1.create_app(session_manager=manager,
                            ollama_adapter=v1.AuthenticatedOllamaAdapter(v1.NoModel()))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = manager.get(sid).game_session
            self.assertIsNot(restored, session)
            assert_interrupted(restored.character, restored.world_state)
            self.assertEqual(resumed.json()["state"]["character"]["current_hp"], hp_before)
            for key in ("spellcasting", "pending_event_decisions", "campaign_time"):
                self.assertEqual(resumed.json()["state"][key], response["state"][key])
            for key in ("spellcasting_v1", "scheduled_events", "campaign_time"):
                self.assertEqual(restored.world_state[key], persisted["world_state"][key])
            await assert_replay(http, manager, sid)

    async def prepare_return(self):
        """Persist an outward midpoint encounter and the upcoming return stop."""
        record = self.manager.get(self.sid)
        session = record.game_session
        session.world_state["flags"]["pending_destination"] = "forest"
        with patch.object(session.rng, "randint", side_effect=[1, 1, 1]) as dice:
            outward = await self.http.post(f"/api/game/sessions/{self.sid}/turn", json={
                "message": "Ormana gidiyorum.", "action_id": str(uuid4()),
            })
        self.assertEqual(outward.status_code, 200, outward.text)
        self.assertEqual(dice.call_count, 3)
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], 300)
        self.assertEqual(session.world_state["journey"]["status"], "INTERRUPTED")
        self.assertEqual(session.world_state["flags"]["pending_destination"], "forest")
        event(session, "saved-return-stop", 360, 400, behavior="INTERRUPTIVE",
              requires_decision=True, route_destination="tavern",
              summary="Dönüş yolunda bir yolcu var.", effects=[flag("saved-return-stop")])
        self.manager.save_campaign(self.created["campaign_id"])
        return record

    def assert_pending_return(self, session):
        world = session.world_state
        journey = world["journey"]
        self.assertTrue(journey["returning"])
        self.assertEqual(journey["destination"], "tavern")
        self.assertEqual(journey["status"], "INTERRUPTED")
        self.assertEqual(journey["stages"], [300])
        self.assertEqual(journey["stage_index"], 0)
        self.assertEqual(journey["stage_spent_seconds"], 60)
        self.assertEqual(sum(journey["stages"][journey["stage_index"]:]) -
                         journey["stage_spent_seconds"], 240)
        self.assertTrue(journey["stage_checked"])
        self.assertEqual(world["location"], "tavern")
        # The selected goal stays pending until arrival, even while retracing.
        self.assertEqual(world["flags"]["pending_destination"], "forest")
        self.assertEqual(world["campaign_time"]["elapsed_seconds"], 360)
        pending = events.pending_events(world)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["event_id"], "saved-return-stop")
        self.assertEqual(pending[0]["decision_status"], "PENDING")
        self.assertTrue(world["flags"]["scheduled:saved-return-stop"])
        self.assertEqual(pending[0]["canonical_result"]["effects_applied"], 1)

    async def assert_return_replay(self, http, manager, sid, request, response):
        """A replay may replace only the transport session ID after a restart."""
        record = manager.get(sid)
        session = record.game_session
        saved = copy.deepcopy(session.serialize_game_state())
        rng = session.rng.getstate()
        journal = copy.deepcopy(record.journal)
        stored = self.store.get_campaign(self.created["campaign_id"])
        receipt = copy.deepcopy(manager.get_turn_action(record, request["action_id"]))
        self.assertEqual(receipt["response"], response)
        with patch.object(session, "run_player_turn", side_effect=AssertionError("Replay ran the engine")), \
             patch.object(session.rng, "randint", side_effect=AssertionError("Replay rolled travel dice")), \
             patch.object(manager, "autosave_turn", side_effect=AssertionError("Replay saved another turn")):
            replay = await http.post(f"/api/game/sessions/{sid}/turn", json=request)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), {**response, "session_id": sid})
        self.assertEqual(session.serialize_game_state(), saved)
        self.assertEqual(session.rng.getstate(), rng)
        self.assertEqual(record.journal, journal)
        self.assertEqual(self.store.get_campaign(self.created["campaign_id"]), stored)
        self.assertEqual(manager.get_turn_action(record, request["action_id"]), receipt)

    async def assert_reloaded_return(self, request, response, saved_session):
        """Use a fresh store, manager and in-process API, never the live service."""
        store = CampaignStore(self.store.path)
        manager = SessionManager(session_factory=scene, campaign_store=store)
        app = v1.create_app(session_manager=manager,
                            ollama_adapter=v1.AuthenticatedOllamaAdapter(v1.NoModel()))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as http:
            resumed = await http.post(f"/api/game/campaigns/{self.created['campaign_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = manager.get(sid).game_session
            self.assertIsNot(restored, saved_session)
            self.assert_pending_return(restored)
            for key in ("journey", "campaign_time", "scheduled_events", "flags"):
                self.assertEqual(restored.world_state[key], saved_session.world_state[key])
            self.assertEqual(resumed.json()["state"]["journey"], response["state"]["journey"])
            self.assertEqual(resumed.json()["state"]["pending_event_decisions"],
                             response["state"]["pending_event_decisions"])
            await self.assert_return_replay(http, manager, sid, request, response)
            with patch.object(restored.rng, "randint", side_effect=AssertionError("Return rerolled traversed road")):
                decision = await http.post(f"/api/game/sessions/{sid}/turn", json={
                    "message": "Devam etmeyi seçiyorum.", "action_id": str(uuid4()),
                })
                self.assertEqual(decision.status_code, 200, decision.text)
                self.assertEqual(restored.world_state["campaign_time"]["elapsed_seconds"], 360)
                self.assertEqual(restored.world_state["journey"]["stage_spent_seconds"], 60)
                self.assertEqual(restored.world_state["scheduled_events"][0]["decision_status"], "RESOLVED")
                completed = await http.post(f"/api/game/sessions/{sid}/turn", json={
                    "message": "Yolculuğa devam ediyorum.", "action_id": str(uuid4()),
                })
                self.assertEqual(completed.status_code, 200, completed.text)
            self.assertEqual(restored.world_state["campaign_time"]["elapsed_seconds"], 600)
            self.assertEqual(restored.world_state["journey"]["status"], "ARRIVED")
            self.assertEqual(restored.world_state["location"], "tavern")
            self.assertIsNone(restored.world_state["flags"]["pending_destination"])
            self.assertIsNone(completed.json()["state"]["journey"])
            # Even an old return receipt after arrival must not restore its old state.
            await self.assert_return_replay(http, manager, sid, request, response)

    async def test_interrupted_return_save_resume_and_action_replay_charge_once(self):
        record = await self.prepare_return()
        session = record.game_session
        rng = session.rng.getstate()
        request = {"message": "Geri dönüyorum.", "action_id": str(uuid4())}
        with patch.object(session.rng, "randint", side_effect=AssertionError("Return must not roll travel dice")):
            first = await self.http.post(f"/api/game/sessions/{self.sid}/turn", json=request)
        self.assertEqual(first.status_code, 200, first.text)
        self.assert_pending_return(session)
        self.assertEqual(session.rng.getstate(), rng)
        await self.assert_return_replay(self.http, self.manager, self.sid, request, first.json())
        # An explicit save must preserve the autosaved response receipt.
        self.manager.save_campaign(self.created["campaign_id"])
        await self.assert_reloaded_return(request, first.json(), session)

    async def test_interrupted_return_failed_autosave_rolls_back_before_retry_and_reload(self):
        record = await self.prepare_return()
        session = record.game_session
        before = copy.deepcopy(session.serialize_game_state())
        rng = session.rng.getstate()
        messages = copy.deepcopy(session.messages)
        journal = copy.deepcopy(record.journal)
        memory = copy.deepcopy(record.narrative_memory)
        stored = self.store.get_campaign(self.created["campaign_id"])
        request = {"message": "Geri dönüyorum.", "action_id": str(uuid4())}

        def reject_interrupted_return(*args, **kwargs):
            # Prove the failure happens after the return advances, not at an early gate.
            self.assert_pending_return(session)
            self.assertEqual(kwargs["turn_action_receipt"]["action_id"], request["action_id"])
            raise CampaignStorageError("test return autosave failure")

        with patch.object(session.rng, "randint", side_effect=AssertionError("Return must not roll travel dice")), \
             patch.object(self.store, "save_campaign", side_effect=reject_interrupted_return) as save:
            failed = await self.http.post(f"/api/game/sessions/{self.sid}/turn", json=request)
        self.assertEqual(save.call_count, 1)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(session.serialize_game_state(), before)
        self.assertEqual(session.rng.getstate(), rng)
        self.assertEqual(session.messages, messages)
        self.assertEqual(record.journal, journal)
        self.assertEqual(record.narrative_memory, memory)
        self.assertEqual(self.store.get_campaign(self.created["campaign_id"]), stored)
        self.assertIsNone(self.manager.get_turn_action(record, request["action_id"]))
        with patch.object(session.rng, "randint", side_effect=AssertionError("Retry must not roll travel dice")):
            retried = await self.http.post(f"/api/game/sessions/{self.sid}/turn", json=request)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assert_pending_return(session)
        self.assertEqual(len(self.store.get_campaign(self.created["campaign_id"]).history),
                         len(stored.history) + 1)
        await self.assert_return_replay(self.http, self.manager, self.sid, request, retried.json())
        await self.assert_reloaded_return(request, retried.json(), session)

    async def test_event_combat_handoff_uses_public_combat_contract(self):
        session = self.manager.get(self.sid).game_session
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Muhafız", "location": "tavern"})
        event(session, "combat-handoff", behavior="INTERRUPTIVE", requires_decision=True,
              combat_npc_id=npc["id"], summary="Rakip karşılaşması.")
        path = f"/api/game/sessions/{self.sid}/turn"
        first = await self.http.post(path, json={"message": "1 saat araştırıyorum.", "action_id": str(uuid4())})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["state"]["pending_event_decisions"][0]["can_fight"])
        action = str(uuid4())
        command = {"message": "Savaşmayı seçiyorum.", "action_id": action}
        fight = await self.http.post(path, json=command)
        self.assertEqual(fight.status_code, 200, fight.text)
        self.assertTrue(fight.json()["state"]["combat"]["active"])
        replay = await self.http.post(path, json=command)
        self.assertEqual(replay.json(), fight.json())
        session.end_combat("test")
        self.assertFalse(events.public_pending(session.world_state)[0]["in_combat"])

    async def test_pending_task_receipt_lost_response_and_restart_are_atomic(self):
        session = self.manager.get(self.sid).game_session
        session.world_state["locations"]["tavern"]["search_duration_seconds"] = 3600
        event(session, "pending", 1440, 1500, behavior="INTERRUPTIVE", requires_decision=True,
              summary="Karar.", effects=[flag("pending")])
        action = str(uuid4())
        request = {"message": "1 saat araştırıyorum.", "action_id": action}
        path = f"/api/game/sessions/{self.sid}/turn"
        first = await self.http.post(path, json=request)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["state"]["campaign_time"]["minute"], 24)
        self.assertEqual(first.json()["state"]["pending_event_decisions"][0]["summary"], "Karar.")
        repeated = await self.http.post(path, json=request)
        self.assertEqual(first.json(), repeated.json())
        manager = SessionManager(session_factory=scene, campaign_store=CampaignStore(self.store.path))
        _, record, _, _, _ = manager.resume_campaign(self.created["campaign_id"])
        self.assertEqual(record.game_session.world_state["active_task"]["spent_seconds"], 1440)
        self.assertEqual(events.pending_events(record.game_session.world_state)[0]["decision_status"], "PENDING")
        self.assertEqual(manager.get_turn_action(record, action)["response"], first.json())
        conflict = await self.http.post(path, json={**request, "message": "2 saat araştırıyorum."})
        self.assertEqual(conflict.status_code, 409)

    async def test_failed_save_rolls_back_time_event_progress_rng_and_receipt(self):
        record = self.manager.get(self.sid)
        session = record.game_session
        event(session, "atomic", 120, 180, behavior="INTERRUPTIVE", requires_decision=True,
              summary="Karar.", effects=[flag("atomic")])
        before = copy.deepcopy(session.world_state)
        rng = session.rng.getstate()
        journal = copy.deepcopy(record.journal)
        action = str(uuid4())
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("test")):
            response = await self.http.post(f"/api/game/sessions/{self.sid}/turn",
                                           json={"message": "1 saat araştırıyorum.", "action_id": action})
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(session.world_state, before)
        self.assertEqual(session.rng.getstate(), rng)
        self.assertEqual(record.journal, journal)
        self.assertIsNone(self.manager.get_turn_action(record, action))
        response = await self.http.post(f"/api/game/sessions/{self.sid}/turn",
                                       json={"message": "1 saat araştırıyorum.", "action_id": action})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(session.world_state["active_task"]["spent_seconds"], 120)


if __name__ == "__main__":
    unittest.main()
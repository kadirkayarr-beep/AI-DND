"""Regression coverage for the stability repairs.

These tests stay deterministic. They do not raise fallback budgets or call Qwen.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

import game
import living_world
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignCorruptError
from api.persistence.campaign_validation import _validate_engine_save
from api.session_manager import SessionManager
from api.tests.live_playable_living_world_v1_1_smoke import (
    EXPECTED_LABELS,
    SmokeFailure,
    apply_smoke_summary,
)


def _intent_json(intent="unknown"):
    return {
        "message": {
            "content": (
                '{"intent":"%s","action":"none","target":{"type":"","reference":""},'
                '"completion":"unclear","confidence":0.1}'
            ) % intent
        }
    }


def _ruler_context():
    context = game._empty_lore_authority_context()
    context["sections"]["official_forgotten_realms_lore"] = [
        {
            "fact_id": "fr:fact:dagult_neverember_current_lord",
            "subject_id": "fr:city:neverwinter",
            "predicate": "current_lord_id",
            "object_id_or_value": "fr:person:dagult_neverember",
            "notes": "Dagult Neverember is the current Lord of Neverwinter.",
        }
    ]
    context["sections"]["verified_entities"] = [
        {
            "entity_id": "fr:city:neverwinter",
            "canonical_name": "Neverwinter",
            "aliases": [],
        },
        {
            "entity_id": "fr:person:dagult_neverember",
            "canonical_name": "Dagult Neverember",
            "aliases": ["Dagult"],
        },
    ]
    context["diagnostics"] = {"query_intents": ["rulership"]}
    return context


class FakeOllamaClient:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("stability API tests must not call a model")


class SmokeSummaryTests(unittest.TestCase):
    def test_failure_code_survives_evidence_gaps(self):
        rows = [{
            "turn": 1,
            "label": EXPECTED_LABELS[0],
            "proposal_trace_status": "validator_not_invoked",
            "proposal_validation_calls": 0,
            "proposal_decisions": [],
            "request_telemetry_context_seen": True,
            "action_result_capture_seen": True,
            "resolved_action": "explore",
            "action_result": {"action": "explore"},
            "safety": {
                "tier": "ordinary",
                "handling": "accepted",
                "reason_code": "NO_SAFETY_TRIGGER",
                "scope": "turn",
            },
            "token_usage": {"prompt_eval_count": 1, "eval_count": 1},
            "fallback_budget_counted": True,
            "safety_reason": "UNREGISTERED_NAMED_ENTITY",
        }]
        result = apply_smoke_summary(
            {},
            rows,
            1,
            SmokeFailure(f"{EXPECTED_LABELS[1]}: engine evidence is incomplete."),
        )
        self.assertIn("SmokeFailure", result["error"])
        self.assertIn(EXPECTED_LABELS[1], result["error"])
        self.assertEqual(result["error_turn_label"], EXPECTED_LABELS[1])
        self.assertIn("30-turn action sequence incomplete", result["evidence_incomplete"])
        self.assertNotEqual(result["error"], "; ".join(result["evidence_incomplete"]))
        self.assertEqual(
            result["validator_not_invoked"][0]["classification"],
            "intentional_skip",
        )
        marked = apply_smoke_summary(
            {},
            [{
                **rows[0],
                "proposal_decisions": [{
                    "kind": "proposal_summary",
                    "status": "validator_not_invoked",
                }],
            }],
            0,
            None,
        )
        self.assertEqual(
            marked["validator_not_invoked"][0]["classification"],
            "intentional_skip",
        )
        self.assertNotIn(
            "validator skip was not an intentional no-call",
            marked["evidence_incomplete"],
        )
        self.assertEqual(
            result["ordinary_fallback_reason_codes"],
            ["UNREGISTERED_NAMED_ENTITY"],
        )
        self.assertLessEqual(2, 2)

    def test_secret_text_is_not_copied_into_the_summary(self):
        result = apply_smoke_summary(
            {},
            [],
            0,
            SmokeFailure("bearer abc.def token=secret"),
        )
        self.assertNotIn("abc.def", result["error"])
        self.assertNotIn("secret", result["error"])


class TurnIntegrityTests(unittest.TestCase):
    def test_model_outage_keeps_deterministic_dialogue_mechanics_safe(self):
        session = game.create_session(seed=4)
        before_world = copy.deepcopy(session.world_state)
        before_character = copy.deepcopy(session.character)
        before_rng = session.rng.getstate()
        before_turn_index = before_world.get("flags", {}).get("turn_index", 0)

        with patch(
            "game.ollama.chat", side_effect=TimeoutError("timed out")
        ) as chat:
            result = session.run_player_turn("merhaba")

        action_result = result["action_result"]
        self.assertEqual(action_result["action"], "dialogue")
        self.assertEqual(action_result["status"], "resolved")
        self.assertIs(action_result["success"], True)

        narration = result.get("narration")
        self.assertIsInstance(narration, str)
        self.assertTrue(narration.strip())

        evidence = result.get("_engine_event_evidence", {})
        telemetry = evidence.get("telemetry", {})
        self.assertEqual(telemetry.get("intent_model_calls"), 1)
        self.assertEqual(telemetry.get("narration_model_calls"), 1)
        self.assertLessEqual(telemetry.get("total_model_calls", 3), 2)
        self.assertEqual(telemetry.get("narration_source"), "deterministic_fallback")
        self.assertEqual(telemetry.get("fallback_reason"), "MODEL_UNAVAILABLE")
        self.assertEqual(chat.call_count, 2)

        self.assertEqual(session.character, before_character)
        self.assertEqual(session.rng.getstate(), before_rng)
        self.assertEqual(
            session.world_state.get("flags", {}).get("turn_index"),
            before_turn_index + 1,
        )

        # A recognized dialogue may append NPC/player conversation memory.
        # It must not otherwise mutate canonical world state.
        after_world = copy.deepcopy(session.world_state)
        for world in (before_world, after_world):
            flags = world.get("flags")
            if isinstance(flags, dict):
                flags.pop("turn_index", None)
            for npc in world.get("npcs", []):
                if isinstance(npc, dict):
                    npc.pop("memory", None)
        self.assertEqual(after_world, before_world)

    def test_malformed_intent_json_is_not_an_unknown_success(self):
        session = game.create_session(seed=5)
        before = copy.deepcopy(session.world_state)
        with patch(
            "game.ollama.chat",
            return_value={"message": {"content": "this is not json at all"}},
        ):
            result = session.run_player_turn("merhaba")
        self.assertEqual(
            result["action_result"]["infrastructure_code"],
            "intent_json_invalid",
        )
        self.assertEqual(session.world_state, before)

    def test_explicit_unknown_intent_is_not_infrastructure(self):
        session = game.create_session(seed=6)
        with patch("game.ollama.chat", return_value=_intent_json("unknown")):
            result = session.run_player_turn("asdf qqq")
        self.assertNotEqual(
            result["action_result"].get("status"),
            "infrastructure_failure",
        )

    def test_model_timeout_on_unknown_input_does_not_apply_mechanics(self):
        session = game.create_session(seed=8)
        before_world = copy.deepcopy(session.world_state)
        before_character = copy.deepcopy(session.character)
        before_hp = session.character.get("current_hp")
        before_inventory = copy.deepcopy(session.character.get("inventory"))
        before_location = before_world.get("location")
        before_shops = copy.deepcopy(before_world.get("shops"))
        before_quests = {
            key: copy.deepcopy(value)
            for key, value in before_world.items()
            if "quest" in key.casefold()
        }
        before_rng = session.rng.getstate()
        before_turn_index = before_world.get("flags", {}).get("turn_index", 0)

        with patch(
            "game.ollama.chat", side_effect=TimeoutError("timed out")
        ) as chat:
            result = session.run_player_turn("asdf qqq")

        action_result = result["action_result"]
        self.assertEqual(action_result.get("action"), "unknown")
        self.assertIn(
            action_result.get("status"),
            {"resolved", "clarification", "no_effect"},
        )
        self.assertEqual(action_result.get("state_changes", []), [])
        for key in (
            "skill",
            "dice",
            "damage",
            "item_result",
            "quest_outcomes",
            "travel_outcome",
        ):
            self.assertNotIn(key, action_result)

        narration = result.get("narration")
        self.assertIsInstance(narration, str)
        self.assertTrue(narration.strip())
        telemetry = result.get("_engine_event_evidence", {}).get("telemetry", {})
        self.assertEqual(telemetry.get("intent_model_calls"), 1)
        self.assertEqual(telemetry.get("narration_model_calls"), 1)
        self.assertLessEqual(telemetry.get("total_model_calls", 3), 2)
        self.assertEqual(telemetry.get("narration_source"), "deterministic_fallback")
        self.assertEqual(telemetry.get("fallback_reason"), "MODEL_UNAVAILABLE")
        self.assertEqual(chat.call_count, 2)

        self.assertEqual(session.character, before_character)
        self.assertEqual(session.character.get("current_hp"), before_hp)
        self.assertEqual(session.character.get("inventory"), before_inventory)
        self.assertEqual(session.rng.getstate(), before_rng)
        self.assertEqual(session.world_state.get("location"), before_location)
        self.assertEqual(session.world_state.get("shops"), before_shops)
        self.assertEqual(
            {
                key: value
                for key, value in session.world_state.items()
                if "quest" in key.casefold()
            },
            before_quests,
        )
        self.assertEqual(
            session.world_state.get("flags", {}).get("turn_index"),
            before_turn_index + 1,
        )

        after_world = copy.deepcopy(session.world_state)
        for world in (before_world, after_world):
            flags = world.get("flags")
            if isinstance(flags, dict):
                flags.pop("turn_index", None)
        self.assertEqual(after_world, before_world)

    def test_narration_timeout_preserves_python_skill_check_result(self):
        session = game.create_session(seed=1)
        player_input = "I investigate signs that Neverwinter is rebuilding."
        intent_response = {
            "message": {
                "content": (
                    '{"intent":"investigation","action":"investigate",'
                    '"target":{"type":"none","reference":""},'
                    '"completion":"unclear","confidence":1.0,'
                    '"interaction":{"operation":"none","quote":'
                    '"I investigate signs that Neverwinter is rebuilding."}}'
                )
            }
        }
        session.initialize_species_trait_state()
        before_world = copy.deepcopy(session.world_state)
        before_character = copy.deepcopy(session.character)
        before_hp = session.character.get("current_hp")
        before_inventory = copy.deepcopy(session.character.get("inventory"))
        before_world_inventory = copy.deepcopy(session.world_state.get("inventory"))
        before_location = before_world.get("location")
        before_shops = copy.deepcopy(before_world.get("shops"))
        before_quests = {
            key: copy.deepcopy(value)
            for key, value in before_world.items()
            if "quest" in key.casefold()
        }
        before_turn_index = before_world.get("flags", {}).get("turn_index", 0)

        with patch(
            "game.ollama.chat",
            side_effect=[intent_response, TimeoutError("narration timeout")],
        ) as chat, patch("game.roll_d20", wraps=game.roll_d20) as roll_d20:
            result = session.run_player_turn(player_input)

        action_result = result["action_result"]
        self.assertEqual(action_result.get("action"), "skill_check")
        self.assertEqual(action_result.get("skill"), "Investigation")
        self.assertEqual(action_result.get("status"), "resolved")
        self.assertIn(action_result.get("outcome"), {"success", "failure"})
        self.assertIs(action_result.get("success"), action_result["outcome"] == "success")
        self.assertEqual(roll_d20.call_count, 1)
        self.assertIsInstance(action_result.get("dice"), int)
        self.assertGreaterEqual(action_result["dice"], 1)
        self.assertLessEqual(action_result["dice"], 20)
        self.assertEqual(
            action_result["dice"],
            action_result["resolution"]["selected_roll"],
        )
        self.assertEqual(
            action_result["outcome"],
            action_result["resolution"]["outcome"].casefold(),
        )

        narration = result.get("narration")
        self.assertIsInstance(narration, str)
        expected_outcome_text = (
            "başarılı" if action_result["outcome"] == "success" else "sonuç vermedi"
        )
        self.assertIn(expected_outcome_text, narration.casefold())

        telemetry = result.get("_engine_event_evidence", {}).get("telemetry", {})
        self.assertEqual(telemetry.get("intent_model_calls"), 1)
        self.assertEqual(telemetry.get("narration_model_calls"), 1)
        self.assertLessEqual(telemetry.get("total_model_calls", 3), 2)
        self.assertEqual(telemetry.get("narration_source"), "deterministic_fallback")
        self.assertEqual(telemetry.get("fallback_reason"), "MODEL_UNAVAILABLE")
        self.assertEqual(chat.call_count, 2)

        self.assertEqual(session.character, before_character)
        self.assertEqual(session.character.get("current_hp"), before_hp)
        self.assertEqual(session.character.get("inventory"), before_inventory)
        self.assertEqual(session.world_state.get("inventory"), before_world_inventory)
        self.assertEqual(session.world_state.get("location"), before_location)
        self.assertEqual(session.world_state.get("shops"), before_shops)
        self.assertEqual(
            {
                key: value
                for key, value in session.world_state.items()
                if "quest" in key.casefold()
            },
            before_quests,
        )
        self.assertEqual(
            session.world_state.get("flags", {}).get("turn_index"),
            before_turn_index + 1,
        )
        expected_world = copy.deepcopy(before_world)
        expected_world["flags"]["turn_index"] = before_turn_index + 1
        expected_categories = copy.deepcopy(
            expected_world.get("adventure_recent_categories", [])
        )
        self.assertIsInstance(expected_categories, list)
        expected_categories.append("investigation")
        expected_world["adventure_recent_categories"] = expected_categories[-6:]
        self.assertEqual(session.world_state, expected_world)

    def test_self_query_beats_active_npc_dialogue(self):
        session = game.create_session(seed=7)
        session.world_state["npcs"].append({
            "id": "npc_self",
            "name": "TestNPC",
            "role": "Barmen",
            "location": session.world_state["location"],
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "backstory": "",
        })
        before_memory = copy.deepcopy(session.world_state["npcs"][-1]["memory"])
        result = session.run_player_turn("benim adım ne?", target_id="npc_self")
        self.assertEqual(result["action_result"]["action"], "character_query")
        self.assertIn(session.character["name"], result["action_result"]["direct_response"])
        self.assertEqual(session.world_state["npcs"][-1]["memory"], before_memory)
        self.assertNotIn("npc_id", result["action_result"])

    def test_ruler_question_answers_from_lore_without_scene_writes(self):
        session = game.create_session(seed=8)
        session.lore_authority_context = _ruler_context()
        session.world_state["locations"]["local_tavern"] = {
            "id": "local_tavern",
            "name": "Ilyra Hanı",
            "type": "building",
            "aliases": ["han"],
        }
        session.world_state["location"] = "local_tavern"
        npc = {
            "id": "npc_ruler_route",
            "name": "Melis",
            "role": "Kent sakini",
            "location": session.world_state["location"],
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "memory": [],
        }
        session.world_state["npcs"].append(npc)
        before = copy.deepcopy(session.world_state)
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            targeted = session.run_player_turn(
                "Bu şehrin hükümdarı kim?",
                target_id=npc["id"],
            )
            untargeted = session.run_player_turn("Bu şehrin hükümdarı kim?")
        for result in (targeted, untargeted):
            self.assertEqual(result["action_result"]["status"], "answered_from_loaded_lore")
            self.assertNotIn("npc_id", result["action_result"])
            self.assertIn("Dagult Neverember", result["narration"])
            self.assertNotIn("Melis", result["narration"])
        self.assertEqual(session.world_state["location"], before["location"])
        self.assertEqual(
            [item.get("id") for item in session.world_state["npcs"]],
            [item.get("id") for item in before["npcs"]],
        )

    def test_route_question_does_not_expire_an_unrelated_referent(self):
        session = game.create_session(seed=9)
        world = session.world_state
        location = world["location"]
        turn_index = world.get("flags", {}).get("turn_index", 0)
        referent = living_world.create_scene_referent(
            world,
            location,
            turn_index,
            description="Kapıda bekleyen bir yolcu.",
            aliases=["yolcu", "ziyaretçi"],
        )
        referent["expires_after_turn"] = 0
        before = referent["lifecycle"]
        with patch("game.ollama.chat", return_value=_intent_json("query")):
            session.run_player_turn(
                "Taverna ile Kale arasındaki yol mesafesi kaç kilometre?"
            )
        self.assertEqual(before, "presented")
        self.assertEqual(referent["lifecycle"], "presented")

    def test_distance_forms_do_not_create_a_place(self):
        session = game.create_session(seed=10)
        before_ids = set(session.world_state["locations"])
        phrases = (
            "Taverna ile Kale arasındaki yol mesafesi kaç kilometre?",
            "Taverna ile Kale arasındaki mesafeyi söyle.",
            "Taverna ile Kale arasındaki mesafe nedir",
        )
        with patch("game.ollama.chat", return_value=_intent_json("query")):
            for phrase in phrases:
                session.run_player_turn(phrase)
        self.assertEqual(set(session.world_state["locations"]), before_ids)


class PersistenceTests(unittest.TestCase):
    def test_load_keeps_the_caller_world_dictionary(self):
        session = game.create_session(seed=11)
        held = session.world_state
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adventure.json"
            session.save_game(path)
            session.load_game(path)
        self.assertIs(session.world_state, held)

    def test_corrupt_engine_save_is_rejected_and_logged(self):
        with self.assertLogs("ai_dnd.persistence", level="WARNING") as logs:
            with self.assertRaises(CampaignCorruptError):
                _validate_engine_save({"format": "nope"}, CampaignCorruptError)
        self.assertTrue(any("Engine save rejected" in line for line in logs.output))
        with self.assertRaises(ValueError):
            game._validate_save_payload({
                "format": "ai-dnd-save",
                "version": 99,
                "player": {},
                "world_state": {},
            })


class NarrationAndCoreTests(unittest.TestCase):
    def test_texture_and_feature_names_are_not_people(self):
        session = game.create_session(seed=12)
        session.world_state["features"].append({
            "id": "feature_hidden_road",
            "name": "Gizli Yol",
            "location": session.world_state["location"],
            "description": "Dar bir patika.",
        })
        safe_place = session._narration_is_unsafe(
            "Gizli Yol durur.",
            "etrafa bak",
            None,
            {"action": "explore", "status": "observed"},
        )
        safe_texture = session._narration_is_unsafe(
            "Bardak durur.",
            "etrafa bak",
            None,
            {"action": "explore", "status": "observed"},
        )
        unsafe = session._narration_is_unsafe(
            "Elara durur.",
            "etrafa bak",
            None,
            {"action": "explore", "status": "observed"},
        )
        self.assertFalse(safe_place)
        self.assertFalse(safe_texture)
        self.assertTrue(unsafe)

    def test_second_sword_drop_does_not_duplicate(self):
        session = game.create_session(seed=13)
        first = session.update_inventory_from_player("Kılıcı yere bırakıyorum")
        second = session.update_inventory_from_player("Kılıcı yere bırakıyorum")
        ground = session.world_state["ground_items_by_location"][
            session.world_state["location"]
        ]
        self.assertIn("yere taşındı", first)
        self.assertIn("zaten yerde", second)
        self.assertEqual(ground.count("Kılıç"), 1)
        self.assertNotIn("Kılıç", session.world_state["inventory"])

    def test_unsupported_commands_repeat_without_mutation(self):
        session = game.create_session(seed=14)
        before = copy.deepcopy(session.world_state)
        hp = session.character["current_hp"]
        for _ in range(50):
            rest = session.execute_intent({"intent": "rest"}, "dinleniyorum")
            item = session.execute_intent({"intent": "use_item"}, "iksir içiyorum")
            self.assertEqual(rest["status"], "unsupported")
            self.assertEqual(item["status"], "unsupported")
        self.assertEqual(session.character["current_hp"], hp)
        self.assertEqual(session.world_state["inventory"], before["inventory"])
        self.assertEqual(session.world_state["quests"], [])

    def test_repeated_attacks_do_not_drop_hp_below_zero(self):
        session = game.create_session(seed=15)
        target = {
            "id": "npc_dummy",
            "name": "Hedef",
            "role": "Eğitim",
            "location": session.world_state["location"],
            "combat_status": "active",
            "armor_class": 1,
            "max_hp": 8,
            "current_hp": 8,
        }
        session.world_state["npcs"].append(target)
        weapon = next(iter(game.WEAPONS.values()))
        weapon_name = next(iter(game.WEAPONS))
        for _ in range(20):
            session.resolve_attack("saldır", weapon_name, weapon, target)
            self.assertGreaterEqual(target["current_hp"], 0)
            self.assertGreaterEqual(session.character["current_hp"], 0)

    def test_location_cap_is_explicit(self):
        session = game.create_session(seed=16)
        locations = session.world_state["locations"]
        index = 0
        while len(locations) < 80:
            created = session.create_location_from_proposal({
                "name": f"Geçit {index}",
                "type": "landmark",
                "description": "Dar bir taş geçit.",
                "aliases": [],
            })
            self.assertIsNotNone(created)
            index += 1
        blocked = session.create_location_from_proposal({
            "name": "Fazla Geçit",
            "type": "landmark",
            "description": "Sığmayan bir geçit.",
            "aliases": [],
        })
        self.assertIsNone(blocked)
        self.assertEqual(len(session.world_state["locations"]), 80)
        self.assertEqual(
            session.world_state["flags"].get("location_create_status"),
            "limit_reached",
        )
        self.assertNotIn(
            "Fazla Geçit",
            [item.get("name") for item in session.world_state["locations"].values()],
        )

    def test_seeded_trace_is_stable_across_two_runs(self):
        phrases = (
            ["benim adım ne?"] * 5
            + ["buranın adı ne?"] * 5
            + ["Kılıcı yere bırakıyorum", "Yerdeki kılıcı alıyorum"] * 5
            + ["Taverna ile Kale arasındaki yol mesafesi kaç kilometre?"] * 5
            + ["Bu şehrin hükümdarı kim?"] * 5
        )
        self.assertEqual(len(phrases), 30)

        def trace():
            session = game.create_session(seed=21)
            session.lore_authority_context = _ruler_context()
            rows = []
            with patch("game.ollama.chat", return_value=_intent_json("unknown")):
                for phrase in phrases:
                    result = session.run_player_turn(phrase)
                    action = result["action_result"]
                    rows.append((
                        action.get("action"),
                        action.get("status"),
                        session.world_state.get("location"),
                        session.character["current_hp"],
                        tuple(session.world_state["inventory"]),
                        len(session.world_state["quests"]),
                    ))
            return rows

        self.assertEqual(trace(), trace())


class CrossSessionTests(unittest.TestCase):
    def test_boundary_inputs_leave_hp_inventory_and_quests_alone(self):
        session = game.create_session(seed=31)
        before_location = session.world_state["location"]
        before_inventory = list(session.world_state["inventory"])
        hp = session.character["current_hp"]
        phrases = ("", "   ", "\u2603" * 12, "x" * 4000)
        with patch("game.ollama.chat", return_value=_intent_json("unknown")):
            for phrase in phrases:
                result = session.run_player_turn(phrase)
                self.assertIn("narration", result)
                self.assertNotEqual(
                    result["action_result"].get("status"),
                    "infrastructure_failure",
                )
        self.assertEqual(session.character["current_hp"], hp)
        self.assertEqual(session.world_state["location"], before_location)
        self.assertEqual(session.world_state["inventory"], before_inventory)
        self.assertEqual(session.world_state["quests"], [])

    def test_attack_lore_and_reload_do_not_cross_write(self):
        session = game.create_session(seed=32)
        session.lore_authority_context = _ruler_context()
        target = {
            "id": "npc_cross",
            "name": "Hedef",
            "role": "Eğitim",
            "location": session.world_state["location"],
            "combat_status": "active",
            "armor_class": 10,
            "max_hp": 12,
            "current_hp": 12,
            "memory": [],
        }
        session.world_state["npcs"].append(target)
        weapon_name = next(iter(game.WEAPONS))
        session.resolve_attack(
            "saldır",
            weapon_name,
            game.WEAPONS[weapon_name],
            target,
        )
        player_hp = session.character["current_hp"]
        target_hp = target["current_hp"]
        location = session.world_state["location"]
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            ruler = session.run_player_turn(
                "Bu şehrin hükümdarı kim?",
                target_id=target["id"],
            )
        self.assertEqual(ruler["action_result"]["status"], "answered_from_loaded_lore")
        self.assertNotIn("npc_id", ruler["action_result"])
        self.assertEqual(session.character["current_hp"], player_hp)
        self.assertEqual(target["current_hp"], target_hp)
        self.assertEqual(session.world_state["location"], location)
        self.assertEqual(session.world_state["quests"], [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cross.json"
            session.save_game(path)
            session.character["current_hp"] = 1
            session.load_game(path)
        self.assertEqual(session.character["current_hp"], player_hp)
        reloaded = next(
            npc for npc in session.world_state["npcs"] if npc.get("id") == "npc_cross"
        )
        self.assertEqual(reloaded["current_hp"], target_hp)

    def test_shop_price_question_does_not_mint_gold(self):
        session = game.create_session(seed=33)
        session.world_state.setdefault("shops", []).append({
            "id": "shop_cross",
            "name": "Tezgah",
            "location": session.world_state["location"],
        })
        before = list(session.world_state["inventory"])
        result = session.run_player_turn("fiyatları söyle")
        self.assertEqual(result["action_result"]["status"], "unsupported")
        self.assertEqual(session.world_state["inventory"], before)
        self.assertNotIn("altın", " ".join(session.world_state["inventory"]).casefold())

    def test_conversational_accept_does_not_invent_a_quest(self):
        session = game.create_session(seed=34)
        with patch("game.ollama.chat", return_value=_intent_json("unknown")):
            session.run_player_turn("işi kabul ediyorum")
        self.assertEqual(session.world_state["quests"], [])


class ApiRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = SessionManager()
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.http.aclose()

    async def test_health_names_this_process(self):
        response = await self.http.get("/api/game/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-ai-dnd-instance"], str(os.getpid()))

    async def test_failed_restore_closes_the_session_and_skips_save(self):
        created = await self.http.post("/api/sessions")
        session_id = created.json()["session_id"]
        with patch("api.main._restore_session", side_effect=RuntimeError("restore failed")):
            response = await self.http.post(
                f"/api/game/sessions/{session_id}/quests/missing/accept"
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "session_restore_failed")
        follow = await self.http.get(f"/api/sessions/{session_id}/state")
        self.assertEqual(follow.status_code, 409)
        self.assertFalse(self.manager.get(session_id).usable)

    async def test_generated_health_client_matches_fastapi(self):
        root = Path(__file__).resolve().parents[3]
        spec = (root / "lib" / "api-spec" / "openapi.yaml").read_text(encoding="utf-8")
        client = (root / "lib" / "api-client-react" / "src" / "generated" / "api.ts").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("/healthz", spec)
        self.assertIn("/game/health:", spec)
        self.assertIn("return `/api/game/health`", client)


if __name__ == "__main__":
    unittest.main()

"""Real API attack resolution plus production safety/finalize boundary integration."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"

import httpx
import game
import narration_claims
from api.tests.test_f04_frozen_faults import (
    Fixture,
    ScriptedProvider,
    narration,
    no_network,
)


class AttackNarrationApiIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_attack_narration_is_accepted_and_reward_claim_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="attack-narration-positive-api-") as temporary:
            provider = ScriptedProvider([])
            fixture = Fixture(Path(temporary) / "campaign.sqlite3", provider)
            with no_network() as network, fixture.adapter.engine_binding():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=fixture.build_app()),
                    base_url="http://testserver",
                    trust_env=False,
                ) as client:
                    await fixture.create(client)
                    fixture.tavern()
                    npc = {
                        "id": "npc_enemy",
                        "name": "Haydut",
                        "role": "Guard",
                        "location": "tavern",
                        "relationship": "hostile",
                        "hostile": True,
                        "memory": [],
                        "knowledge": [],
                        "current_hp": 100,
                        "max_hp": 100,
                        "armor_class": 10,
                        "combat_status": "active",
                        "distance_ft": 5,
                        "dexterity_mod": -5,
                        "attack_bonus": 0,
                        "damage_die": 4,
                        "damage_dice": 1,
                        "damage_modifier": 0,
                    }
                    fixture.session.world_state["npcs"] = [npc]
                    fixture.session.rng.seed(5)
                    game._living_world_prompt_context(session=fixture.session)
                    fixture.session.start_combat(npc)
                    fixture.session.rng.seed(5)
                    fixture.save()

                    combat = fixture.session.world_state["combat"]
                    response = await fixture.turn(
                        client,
                        "Kılıçla saldırıyorum.",
                        target_id=npc["id"],
                        interaction_mode="do",
                        combat_id=combat["combat_id"],
                        combat_round=combat["round"],
                        combat_turn_index=combat["current_turn_index"],
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    native_api_provider_calls = len(provider.calls)
                    self.assertEqual(provider.calls, [])
                    native = fixture.engine_results[-1]
                    action = native["action_result"]
                    self.assertEqual(action["action"], "attack")
                    self.assertEqual(action["outcome"], "critical_hit")
                    self.assertGreater(action["damage"], 0)
                    committed = fixture.snapshot()

                    def resolved_turn():
                        return game.ResolvedTurn(
                            action_result=copy.deepcopy(action),
                            fallback_response=native["narration"],
                            raw_result=copy.deepcopy(native),
                            messages=fixture.session.messages,
                            lore_context=game._empty_lore_authority_context(),
                        )

                    original_assess = narration_claims.assess
                    attack_assess_packets = []
                    attack_assess_results = []

                    def observe_assess(narration_text, packet):
                        attack_assess_packets.append(copy.deepcopy(packet))
                        verdict = original_assess(narration_text, packet)
                        attack_assess_results.append({
                            "narration": narration_text,
                            "verdict": verdict,
                        })
                        return verdict

                    positive_text = (
                        f'{npc["name"]}, kritik bir darbe alır: '
                        f'{action["damage"]} hasar. Rakibin savunmaya geçer.'
                    )
                    provider.scripts.append(narration(positive_text))
                    with patch.object(narration_claims, "assess", side_effect=observe_assess):
                        positive = game._narrate_resolved_turn(
                            resolved_turn(),
                            "Kılıçla saldırıyorum.",
                            fixture.session.messages,
                            npc["id"],
                        )
                    positive_telemetry = positive["_engine_event_evidence"]["telemetry"]
                    safety_decision = getattr(fixture.session, "last_narration_safety", {}) or {}
                    print("ATTACK_POSITIVE_CONTROL_DIAGNOSTIC " + json.dumps({
                        "synthetic_narration_text_at_boundary": positive_text,
                        "provider_implementation": "ScriptedProvider",
                        "real_model_calls": 0,
                        "network_attempts": len(network),
                        "returned_narration": positive["narration"],
                        "output_relation": (
                            "verbatim" if positive["narration"] == positive_text else "modified"
                        ),
                        "production_safety_decision": {
                            key: safety_decision.get(key)
                            for key in ("handling", "reason_code", "trigger_span", "scene_type")
                        },
                        "finalize_telemetry": positive_telemetry,
                        "authoritative_attack_result": action,
                        "attack_claim_packets_seen": attack_assess_packets,
                        "provider_calls": {
                            "native_api_attack": native_api_provider_calls,
                            "after_narration_boundary": len(provider.calls),
                        },
                    }, ensure_ascii=False, sort_keys=True, default=str))
                    self.assertEqual(len(provider.calls), 1)
                    self.assertEqual(positive["narration"], positive_text)
                    self.assertEqual(positive_telemetry["narration_source"], "qwen")
                    self.assertEqual(
                        positive_telemetry["narration_validation_result"], "accepted"
                    )
                    self.assertIsNone(positive_telemetry["fallback_reason"])
                    self.assertTrue(attack_assess_packets)
                    self.assertTrue(
                        all(packet.get("action") == "attack" for packet in attack_assess_packets)
                    )
                    after_positive = fixture.snapshot()
                    self.assertEqual(
                        after_positive["engine_save"]["world_state"],
                        committed["engine_save"]["world_state"],
                    )
                    self.assertEqual(
                        after_positive["engine_save"]["player"],
                        committed["engine_save"]["player"],
                    )
                    self.assertEqual(after_positive["rng"], committed["rng"])
                    self.assertEqual(after_positive["persisted"], committed["persisted"])
                    self.assertEqual(after_positive["sql_rows"], committed["sql_rows"])

                    unsupported_quest_claim = "Yeni görev tamamlandı."
                    negative_text = f"{positive_text} {unsupported_quest_claim}"
                    fixture.session.recent_dm_narrations.clear()
                    provider.scripts.append(narration(negative_text))
                    negative_packet_start = len(attack_assess_packets)
                    with patch.object(narration_claims, "assess", side_effect=observe_assess):
                        negative_result = game._narrate_resolved_turn(
                            resolved_turn(),
                            "Kılıçla saldırıyorum.",
                            fixture.session.messages,
                            npc["id"],
                        )
                    negative_telemetry = negative_result["_engine_event_evidence"]["telemetry"]
                    negative_packets = attack_assess_packets[negative_packet_start:]
                    safety_decision = getattr(fixture.session, "last_narration_safety", {}) or {}
                    after_negative = fixture.snapshot()
                    authoritative_state_unchanged = {
                        "world_state": (
                            after_negative["engine_save"]["world_state"]
                            == committed["engine_save"]["world_state"]
                        ),
                        "player": (
                            after_negative["engine_save"]["player"]
                            == committed["engine_save"]["player"]
                        ),
                        "rng": after_negative["rng"] == committed["rng"],
                        "persisted": after_negative["persisted"] == committed["persisted"],
                        "sql_rows": after_negative["sql_rows"] == committed["sql_rows"],
                    }
                    print("ATTACK_UNSUPPORTED_QUEST_DIAGNOSTIC " + json.dumps({
                        "synthetic_model_text": negative_text,
                        "returned_narration": negative_result["narration"],
                        "output_relation": (
                            "verbatim" if negative_result["narration"] == negative_text else "modified"
                        ),
                        "production_safety_decision": {
                            key: safety_decision.get(key)
                            for key in ("handling", "reason_code", "trigger_span", "scene_type")
                        },
                        "finalize_telemetry": negative_telemetry,
                        "authoritative_attack_result": action,
                        "attack_claim_packets_seen": negative_packets,
                        "authoritative_state_unchanged": authoritative_state_unchanged,
                        "provider_calls": {
                            "native_api_attack": native_api_provider_calls,
                            "after_positive_narration": 1,
                            "after_negative_narration": len(provider.calls),
                        },
                        "network_attempts": len(network),
                    }, ensure_ascii=False, sort_keys=True, default=str))
                    additional_claims = (
                        ("unnumbered_reward", "Sana ödül sözü verildi."),
                        ("unregistered_new_npc", "Arven içeri girer."),
                        ("unresolved_reaction", "Haydut tepki olarak sana karşı saldırır."),
                    )
                    additional_results = []
                    for index, (claim_kind, unsupported_claim) in enumerate(
                        additional_claims, start=3
                    ):
                        fixture.session.recent_dm_narrations.clear()
                        candidate_text = f"{positive_text} {unsupported_claim}"
                        provider.scripts.append(narration(candidate_text))
                        packet_start = len(attack_assess_packets)
                        assessment_start = len(attack_assess_results)
                        with patch.object(
                            narration_claims, "assess", side_effect=observe_assess
                        ):
                            candidate_result = game._narrate_resolved_turn(
                                resolved_turn(),
                                "Kılıçla saldırıyorum.",
                                fixture.session.messages,
                                npc["id"],
                            )
                        candidate_telemetry = candidate_result[
                            "_engine_event_evidence"
                        ]["telemetry"]
                        candidate_packets = attack_assess_packets[packet_start:]
                        candidate_state = fixture.snapshot()
                        candidate_state_unchanged = {
                            "world_state": (
                                candidate_state["engine_save"]["world_state"]
                                == committed["engine_save"]["world_state"]
                            ),
                            "player": (
                                candidate_state["engine_save"]["player"]
                                == committed["engine_save"]["player"]
                            ),
                            "rng": candidate_state["rng"] == committed["rng"],
                            "persisted": (
                                candidate_state["persisted"] == committed["persisted"]
                            ),
                            "sql_rows": candidate_state["sql_rows"]
                            == committed["sql_rows"],
                        }
                        safety_decision = (
                            getattr(fixture.session, "last_narration_safety", {}) or {}
                        )
                        print(
                            "ATTACK_BOUNDARY_NEGATIVE_DIAGNOSTIC "
                            + json.dumps(
                                {
                                    "case": claim_kind,
                                    "synthetic_model_text": candidate_text,
                                    "returned_narration": candidate_result["narration"],
                                    "output_relation": (
                                        "verbatim"
                                        if candidate_result["narration"] == candidate_text
                                        else "modified"
                                    ),
                                    "production_safety_decision": {
                                        key: safety_decision.get(key)
                                        for key in (
                                            "handling",
                                            "reason_code",
                                            "trigger_span",
                                            "scene_type",
                                        )
                                    },
                                    "finalize_telemetry": candidate_telemetry,
                                    "authoritative_attack_result": action,
                                    "attack_claim_packets_seen": candidate_packets,
                                    "authoritative_state_unchanged": candidate_state_unchanged,
                                    "provider_calls": {
                                        "native_api_attack": native_api_provider_calls,
                                        "after_boundary_call": len(provider.calls),
                                    },
                                    "network_attempts": len(network),
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            )
                        )
                        additional_results.append({
                            "claim": unsupported_claim,
                            "text": candidate_text,
                            "result": candidate_result,
                            "telemetry": candidate_telemetry,
                            "safety_decision": safety_decision,
                            "assessments": attack_assess_results[assessment_start:],
                            "packets": candidate_packets,
                            "state_unchanged": candidate_state_unchanged,
                            "kind": claim_kind,
                        })
                    self.assertEqual(len(provider.calls), 5)
                    self.assertTrue(all(authoritative_state_unchanged.values()))
                    self.assertNotIn(unsupported_quest_claim, negative_result["narration"])
                    self.assertEqual(negative_result["narration"], native["narration"])
                    self.assertEqual(
                        negative_telemetry["narration_source"], "deterministic_fallback"
                    )
                    self.assertEqual(
                        negative_telemetry["narration_validation_result"], "python_fallback"
                    )
                    self.assertTrue(negative_telemetry["fallback_reason"])
                    self.assertTrue(negative_packets)
                    self.assertTrue(all(packet.get("action") == "attack" for packet in negative_packets))
                    self.assertEqual(negative_result["action_result"], action)
                    for item in additional_results:
                        self.assertNotIn(item["claim"], item["result"]["narration"])
                        self.assertNotEqual(item["result"]["narration"], item["text"])
                        self.assertTrue(
                            all(item["state_unchanged"].values()),
                            f'{item["kind"]} narration changed authoritative state: '
                            f'{item["state_unchanged"]}',
                        )
                        self.assertEqual(item["result"]["action_result"], action)
                        self.assertTrue(item["packets"])
                        self.assertTrue(
                            all(packet.get("action") == "attack" for packet in item["packets"])
                        )
                        if item["kind"] == "unresolved_reaction":
                            self.assertTrue(
                                any(
                                    entry["verdict"].get("reject")
                                    and entry["verdict"].get("reason")
                                    == "COMBAT_RESULT_CONTRADICTION"
                                    for entry in item["assessments"]
                                ),
                                "unresolved incoming attack must fail the common claim check",
                            )
                    self.assertEqual(network, [])

    async def test_api_critical_vurus_damage_with_dodging_defender_is_accepted(self):
        with tempfile.TemporaryDirectory(prefix="attack-vurus-dodge-api-") as temporary:
            provider = ScriptedProvider([])
            fixture = Fixture(Path(temporary) / "campaign.sqlite3", provider)
            with no_network() as network, fixture.adapter.engine_binding():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=fixture.build_app()),
                    base_url="http://testserver",
                    trust_env=False,
                ) as client:
                    await fixture.create(client)
                    fixture.tavern()
                    npc = {
                        "id": "npc_enemy",
                        "name": "Haydut",
                        "role": "Guard",
                        "location": "tavern",
                        "relationship": "hostile",
                        "hostile": True,
                        "memory": [],
                        "knowledge": [],
                        "current_hp": 100,
                        "max_hp": 100,
                        "armor_class": 10,
                        "combat_status": "active",
                        "distance_ft": 5,
                        "dexterity_mod": -5,
                        "attack_bonus": 0,
                        "damage_die": 4,
                        "damage_dice": 1,
                        "damage_modifier": 0,
                    }
                    fixture.session.world_state["npcs"] = [npc]
                    fixture.session.rng.seed(5)
                    game._living_world_prompt_context(session=fixture.session)
                    fixture.session.start_combat(npc)
                    fixture.session.rng.seed(5)
                    fixture.save()
                    combat = fixture.session.world_state["combat"]
                    response = await fixture.turn(
                        client,
                        "Kılıçla saldırıyorum.",
                        target_id=npc["id"],
                        interaction_mode="do",
                        combat_id=combat["combat_id"],
                        combat_round=combat["round"],
                        combat_turn_index=combat["current_turn_index"],
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(provider.calls, [])
                    native = fixture.engine_results[-1]
                    action = native["action_result"]
                    self.assertEqual(action["action"], "attack")
                    self.assertEqual(action["outcome"], "critical_hit")
                    self.assertGreater(action["damage"], 0)
                    enemy_actions = action.get("enemy_actions") or [
                        action.get("enemy_action")
                    ]
                    self.assertTrue(any(
                        isinstance(enemy, dict) and enemy.get("outcome") == "dodge"
                        for enemy in enemy_actions
                    ), action)

                    text = (
                        f'{npc["name"]} kritik bir vuruş alır: '
                        f'{action["damage"]} hasar. Rakibin savunmaya geçer.'
                    )
                    provider.scripts.append(narration(text))
                    resolved = game.ResolvedTurn(
                        action_result=copy.deepcopy(action),
                        fallback_response=native["narration"],
                        raw_result=copy.deepcopy(native),
                        messages=fixture.session.messages,
                        lore_context=game._empty_lore_authority_context(),
                    )
                    result = game._narrate_resolved_turn(
                        resolved, "Kılıçla saldırıyorum.",
                        fixture.session.messages, npc["id"],
                    )
                    telemetry = result["_engine_event_evidence"]["telemetry"]
                    print("ATTACK_CRITICAL_VURUS_DIAGNOSTIC " + json.dumps({
                        "synthetic_narration_at_boundary": text,
                        "provider_implementation": "ScriptedProvider",
                        "real_model_calls": 0,
                        "authoritative_api_action_result": action,
                        "returned_narration": result["narration"],
                        "telemetry": telemetry,
                        "network_attempts": len(network),
                    }, ensure_ascii=False, sort_keys=True, default=str))
                    self.assertEqual(result["narration"], text)
                    self.assertEqual(telemetry["narration_validation_result"], "accepted")
                    self.assertIsNone(telemetry["fallback_reason"])
                    self.assertEqual(len(provider.calls), 1)
                    self.assertEqual(network, [])

    async def test_api_canonical_damage_phrase_with_dodging_defender_is_accepted(self):
        with tempfile.TemporaryDirectory(prefix="attack-hasar-alir-dodge-api-") as temporary:
            provider = ScriptedProvider([])
            fixture = Fixture(Path(temporary) / "campaign.sqlite3", provider)
            with no_network() as network, fixture.adapter.engine_binding():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=fixture.build_app()),
                    base_url="http://testserver",
                    trust_env=False,
                ) as client:
                    await fixture.create(client)
                    fixture.tavern()
                    npc = {
                        "id": "npc_enemy",
                        "name": "Haydut",
                        "role": "Guard",
                        "location": "tavern",
                        "relationship": "hostile",
                        "hostile": True,
                        "memory": [],
                        "knowledge": [],
                        "current_hp": 100,
                        "max_hp": 100,
                        "armor_class": 10,
                        "combat_status": "active",
                        "distance_ft": 5,
                        "dexterity_mod": -5,
                        "attack_bonus": 0,
                        "damage_die": 4,
                        "damage_dice": 1,
                        "damage_modifier": 0,
                    }
                    fixture.session.world_state["npcs"] = [npc]
                    fixture.session.rng.seed(5)
                    game._living_world_prompt_context(session=fixture.session)
                    fixture.session.start_combat(npc)
                    fixture.session.rng.seed(5)
                    fixture.save()
                    combat = fixture.session.world_state["combat"]
                    response = await fixture.turn(
                        client,
                        "Kılıçla saldırıyorum.",
                        target_id=npc["id"],
                        interaction_mode="do",
                        combat_id=combat["combat_id"],
                        combat_round=combat["round"],
                        combat_turn_index=combat["current_turn_index"],
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(provider.calls, [])
                    native = fixture.engine_results[-1]
                    action = native["action_result"]
                    self.assertEqual(action["action"], "attack")
                    self.assertEqual(action["outcome"], "critical_hit")
                    self.assertGreater(action["damage"], 0)
                    enemy_actions = action.get("enemy_actions") or [
                        action.get("enemy_action")
                    ]
                    self.assertTrue(any(
                        isinstance(enemy, dict) and enemy.get("outcome") == "dodge"
                        for enemy in enemy_actions
                    ), action)

                    text = (
                        f'{npc["name"]}, kritik bir darbe alır ve '
                        f'{action["damage"]} hasar alır. Rakibin savunmaya geçer.'
                    )
                    provider.scripts.append(narration(text))
                    resolved = game.ResolvedTurn(
                        action_result=copy.deepcopy(action),
                        fallback_response=native["narration"],
                        raw_result=copy.deepcopy(native),
                        messages=fixture.session.messages,
                        lore_context=game._empty_lore_authority_context(),
                    )
                    result = game._narrate_resolved_turn(
                        resolved, "Kılıçla saldırıyorum.",
                        fixture.session.messages, npc["id"],
                    )
                    telemetry = result["_engine_event_evidence"]["telemetry"]
                    fallback_safety = (
                        getattr(fixture.session, "last_narration_safety", {}) or {}
                    )
                    print("ATTACK_CANONICAL_DAMAGE_DIAGNOSTIC " + json.dumps({
                        "synthetic_narration_at_boundary": text,
                        "provider_implementation": "ScriptedProvider",
                        "real_model_calls": 0,
                        "authoritative_api_action_result": action,
                        "returned_narration": result["narration"],
                        "candidate_safety_rejection": {
                            "reason_code": telemetry["fallback_reason"],
                            "validation_result": telemetry["narration_validation_result"],
                        },
                        "returned_fallback_safety": {
                            key: fallback_safety.get(key)
                            for key in ("handling", "reason_code", "trigger_span", "scene_type")
                        },
                        "telemetry": telemetry,
                        "network_attempts": len(network),
                    }, ensure_ascii=False, sort_keys=True, default=str))
                    self.assertEqual(result["narration"], text)
                    self.assertEqual(telemetry["narration_validation_result"], "accepted")
                    self.assertIsNone(telemetry["fallback_reason"])
                    self.assertEqual(len(provider.calls), 1)
                    self.assertEqual(network, [])

    async def test_api_rejects_unbound_extra_damage_claim_even_when_number_matches(self):
        with tempfile.TemporaryDirectory(prefix="attack-extra-damage-api-") as temporary:
            provider = ScriptedProvider([])
            fixture = Fixture(Path(temporary) / "campaign.sqlite3", provider)
            with no_network() as network, fixture.adapter.engine_binding():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=fixture.build_app()),
                    base_url="http://testserver",
                    trust_env=False,
                ) as client:
                    await fixture.create(client)
                    fixture.tavern()
                    npc = {
                        "id": "npc_enemy",
                        "name": "Haydut",
                        "role": "Guard",
                        "location": "tavern",
                        "relationship": "hostile",
                        "hostile": True,
                        "memory": [],
                        "knowledge": [],
                        "current_hp": 100,
                        "max_hp": 100,
                        "armor_class": 10,
                        "combat_status": "active",
                        "distance_ft": 5,
                        "dexterity_mod": -5,
                        "attack_bonus": 0,
                        "damage_die": 4,
                        "damage_dice": 1,
                        "damage_modifier": 0,
                    }
                    fixture.session.world_state["npcs"] = [npc]
                    fixture.session.rng.seed(5)
                    game._living_world_prompt_context(session=fixture.session)
                    fixture.session.start_combat(npc)
                    fixture.session.rng.seed(5)
                    fixture.save()
                    combat = fixture.session.world_state["combat"]
                    response = await fixture.turn(
                        client,
                        "Kılıçla saldırıyorum.",
                        target_id=npc["id"],
                        interaction_mode="do",
                        combat_id=combat["combat_id"],
                        combat_round=combat["round"],
                        combat_turn_index=combat["current_turn_index"],
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(provider.calls, [])
                    native = fixture.engine_results[-1]
                    action = native["action_result"]
                    self.assertEqual(action["action"], "attack")
                    self.assertEqual(action["outcome"], "critical_hit")
                    self.assertGreater(action["damage"], 0)
                    enemy_actions = action.get("enemy_actions") or [
                        action.get("enemy_action")
                    ]
                    self.assertTrue(any(
                        isinstance(enemy, dict) and enemy.get("outcome") == "dodge"
                        for enemy in enemy_actions
                    ), action)

                    valid_text = (
                        f'{npc["name"]}, kritik bir darbe alır ve '
                        f'{action["damage"]} hasar alır. Rakibin savunmaya geçer.'
                    )
                    text = f'{valid_text} Ben {action["damage"]} hasar alırım.'
                    provider.scripts.append(narration(text))
                    resolved = game.ResolvedTurn(
                        action_result=copy.deepcopy(action),
                        fallback_response=native["narration"],
                        raw_result=copy.deepcopy(native),
                        messages=fixture.session.messages,
                        lore_context=game._empty_lore_authority_context(),
                    )
                    # Bind this direct safety-boundary call to its fixture;
                    # the API request's active-session context has ended.
                    # Clear only this fixture's prior API-turn narration so
                    # repeat detection cannot mask the candidate safety result.
                    fixture.session.recent_dm_narrations.clear()
                    token = game._ACTIVE_SESSION.set(fixture.session)
                    try:
                        result = game._narrate_resolved_turn(
                            resolved, "Kılıçla saldırıyorum.",
                            fixture.session.messages, npc["id"],
                        )
                    finally:
                        game._ACTIVE_SESSION.reset(token)
                    telemetry = result["_engine_event_evidence"]["telemetry"]
                    safety_decision = (
                        getattr(fixture.session, "last_narration_safety", {}) or {}
                    )
                    print("ATTACK_UNBOUND_EXTRA_DAMAGE_DIAGNOSTIC " + json.dumps({
                        "synthetic_narration_at_boundary": text,
                        "provider_implementation": "ScriptedProvider",
                        "real_model_calls": 0,
                        "authoritative_api_action_result": action,
                        "returned_narration": result["narration"],
                        "production_safety_decision": {
                            key: safety_decision.get(key)
                            for key in ("handling", "reason_code", "trigger_span", "scene_type")
                        },
                        "telemetry": telemetry,
                        "network_attempts": len(network),
                    }, ensure_ascii=False, sort_keys=True, default=str))
                    self.assertNotEqual(result["narration"], text)
                    self.assertEqual(
                        telemetry["fallback_reason"],
                        "CANONICAL_DAMAGE_CONTRADICTION",
                    )
                    self.assertEqual(telemetry["narration_validation_result"], "python_fallback")
                    self.assertEqual(len(provider.calls), 1)
                    self.assertEqual(network, [])

    async def test_attack_fallback_matches_api_result_for_hit_miss_critical_and_dead_name(self):
        async def resolve_attack_case(folder, *, name, hp, armor_class, seed):
            provider = ScriptedProvider([])
            fixture = Fixture(folder, provider)
            npc = {
                "id": "npc_enemy",
                "name": name,
                "role": "Guard",
                "location": "tavern",
                "relationship": "hostile",
                "hostile": True,
                "memory": [],
                "knowledge": [],
                "current_hp": hp,
                "max_hp": hp,
                "armor_class": armor_class,
                "combat_status": "active",
                "distance_ft": 5,
                "dexterity_mod": -5,
                "attack_bonus": 0,
                "damage_die": 4,
                "damage_dice": 1,
                "damage_modifier": 0,
            }
            with fixture.adapter.engine_binding():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=fixture.build_app()),
                    base_url="http://testserver",
                    trust_env=False,
                ) as client:
                    await fixture.create(client)
                    fixture.tavern()
                    fixture.session.world_state["npcs"] = [npc]
                    fixture.session.rng.seed(seed)
                    game._living_world_prompt_context(session=fixture.session)
                    fixture.session.start_combat(npc)
                    fixture.session.rng.seed(seed)
                    fixture.save()
                    combat = fixture.session.world_state["combat"]
                    response = await fixture.turn(
                        client,
                        "Kılıçla saldırıyorum.",
                        target_id=npc["id"],
                        interaction_mode="do",
                        combat_id=combat["combat_id"],
                        combat_round=combat["round"],
                        combat_turn_index=combat["current_turn_index"],
                    )
                    self.assertEqual(response.status_code, 200, response.text)
            return fixture, provider, npc, fixture.engine_results[-1]

        cases = (
            ("normal_hit", "Haydut", 100, 10, 0, "hit"),
            ("miss", "Haydut", 100, 100, 0, "miss"),
            ("critical", "Haydut", 100, 10, 5, "critical_hit"),
            ("multiword_dead_target", "Kızıl Sis Haydudu", 1, 10, 5, "critical_hit"),
        )
        with tempfile.TemporaryDirectory(prefix="attack-fallback-matrix-") as temporary:
            with no_network() as network:
                for label, target_name, hp, armor_class, seed, expected_outcome in cases:
                    fixture, provider, npc, native = await resolve_attack_case(
                        Path(temporary) / f"{label}.sqlite3",
                        name=target_name,
                        hp=hp,
                        armor_class=armor_class,
                        seed=seed,
                    )
                    action = native["action_result"]
                    self.assertEqual(action["outcome"], expected_outcome)
                    if label == "multiword_dead_target":
                        target_after = next(
                            item for item in fixture.session.world_state["npcs"]
                            if item.get("id") == npc["id"]
                        )
                        self.assertEqual(target_after.get("combat_status"), "dead")
                        self.assertEqual(target_after.get("current_hp"), 0)
                    committed = fixture.snapshot()
                    unresolved_text = f"{target_name} hiç yara almaz."
                    provider.scripts.append(narration(unresolved_text))
                    with fixture.adapter.engine_binding(), patch.object(
                        narration_claims,
                        "assess",
                        wraps=narration_claims.assess,
                    ):
                        fallback = game._narrate_resolved_turn(
                            game.ResolvedTurn(
                                action_result=copy.deepcopy(action),
                                fallback_response=native["narration"],
                                raw_result=copy.deepcopy(native),
                                messages=fixture.session.messages,
                                lore_context=game._empty_lore_authority_context(),
                            ),
                            "Kılıçla saldırıyorum.",
                            fixture.session.messages,
                            npc["id"],
                        )
                    telemetry = fallback["_engine_event_evidence"]["telemetry"]
                    safety_decision = getattr(
                        fixture.session, "last_narration_safety", {}
                    ) or {}
                    after = fixture.snapshot()
                    state_unchanged = (
                        after["engine_save"]["world_state"]
                        == committed["engine_save"]["world_state"]
                        and after["engine_save"]["player"]
                        == committed["engine_save"]["player"]
                        and after["rng"] == committed["rng"]
                        and after["persisted"] == committed["persisted"]
                        and after["sql_rows"] == committed["sql_rows"]
                    )
                    print("ATTACK_FALLBACK_CASE_DIAGNOSTIC " + json.dumps({
                        "case": label,
                        "action_result": action,
                        "synthetic_model_text": unresolved_text,
                        "native_api_narration": native["narration"],
                        "returned_narration": fallback["narration"],
                        "production_safety_decision": {
                            key: safety_decision.get(key)
                            for key in ("handling", "reason_code", "trigger_span", "scene_type")
                        },
                        "finalize_telemetry": telemetry,
                        "provider_calls": {
                            "native_api_attack": 0,
                            "narration_boundary": len(provider.calls),
                        },
                        "authoritative_state_unchanged": state_unchanged,
                        "network_attempts": len(network),
                    }, ensure_ascii=False, sort_keys=True, default=str))
                    self.assertEqual(len(provider.calls), 1)
                    self.assertEqual(fallback["narration"], native["narration"])
                    self.assertEqual(telemetry["narration_source"], "deterministic_fallback")
                    self.assertEqual(
                        telemetry["narration_validation_result"], "python_fallback"
                    )
                    self.assertTrue(telemetry["fallback_reason"])
                    self.assertTrue(state_unchanged)
                    if label == "multiword_dead_target":
                        self.assertIn(target_name, fallback["narration"])
            self.assertEqual(network, [])

    async def test_resolved_attack_rejects_unsupported_reward_without_changing_facts(self):
        with tempfile.TemporaryDirectory(prefix="attack-narration-api-") as temporary:
            provider = ScriptedProvider([])
            fixture = Fixture(Path(temporary) / "campaign.sqlite3", provider)
            with no_network() as network, fixture.adapter.engine_binding():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=fixture.build_app()),
                    base_url="http://testserver",
                    trust_env=False,
                ) as client:
                    await fixture.create(client)
                    fixture.tavern()
                    npc = {
                        "id": "npc_enemy",
                        "name": "Haydut",
                        "role": "Guard",
                        "location": "tavern",
                        "relationship": "hostile",
                        "hostile": True,
                        "memory": [],
                        "knowledge": [],
                        "current_hp": 100,
                        "max_hp": 100,
                        "armor_class": 10,
                        "combat_status": "active",
                        "distance_ft": 5,
                        "dexterity_mod": -5,
                        "attack_bonus": 0,
                        "damage_die": 4,
                        "damage_dice": 1,
                        "damage_modifier": 0,
                    }
                    fixture.session.world_state["npcs"] = [npc]
                    fixture.session.rng.seed(5)
                    game._living_world_prompt_context(session=fixture.session)
                    fixture.session.start_combat(npc)
                    fixture.session.rng.seed(5)
                    fixture.save()

                    combat = fixture.session.world_state["combat"]
                    response = await fixture.turn(
                        client,
                        "Kılıçla saldırıyorum.",
                        target_id=npc["id"],
                        interaction_mode="do",
                        combat_id=combat["combat_id"],
                        combat_round=combat["round"],
                        combat_turn_index=combat["current_turn_index"],
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(provider.calls, [])

                    native = fixture.engine_results[-1]
                    action = native["action_result"]
                    self.assertEqual(action["action"], "attack")
                    self.assertEqual(action["outcome"], "critical_hit")
                    self.assertGreater(action["damage"], 0)
                    self.assertEqual(npc["current_hp"], 100 - action["damage"])
                    committed = fixture.snapshot()

                    unsupported_reward = "50 altın kazanırsın."
                    provider.scripts.append(
                        narration(f'{native["narration"]} {unsupported_reward}')
                    )
                    resolved = game.ResolvedTurn(
                        action_result=copy.deepcopy(action),
                        fallback_response=native["narration"],
                        raw_result=copy.deepcopy(native),
                        messages=fixture.session.messages,
                        lore_context=game._empty_lore_authority_context(),
                    )
                    result = game._narrate_resolved_turn(
                        resolved,
                        "Kılıçla saldırıyorum.",
                        fixture.session.messages,
                        npc["id"],
                    )

                    self.assertEqual(len(provider.calls), 1)
                    self.assertNotIn(unsupported_reward, result["narration"])
                    self.assertEqual(result["narration"], native["narration"])
                    self.assertEqual(result["action_result"], action)
                    after = fixture.snapshot()
                    self.assertEqual(
                        after["engine_save"]["world_state"],
                        committed["engine_save"]["world_state"],
                    )
                    self.assertEqual(
                        after["engine_save"]["player"],
                        committed["engine_save"]["player"],
                    )
                    self.assertEqual(after["rng"], committed["rng"])
                    self.assertEqual(after["persisted"], committed["persisted"])
                    self.assertEqual(after["sql_rows"], committed["sql_rows"])
                    self.assertEqual(network, [])

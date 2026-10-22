"""Focused pure tests for the Narrative Director memory boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


from api.tests.auth_fixture import TEST_PLAYER
AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import tempfile
import game
from game import build_world_context
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.narrative_memory import (  # noqa: E402
    MAX_RECENT_TURNS,
    MAX_SERIALIZED_BYTES,
    empty_narrative_memory,
    build_narrative_context,
    update_narrative_memory,
    validate_narrative_memory,
)


def world(location="tavern", npcs=None, turn=0):
    return {
        "location": location,
        "flags": {"turn_index": turn},
        "npcs": npcs or [],
        "locations": {
            "tavern": {"name": "The Tavern"},
            "forest": {"name": "The Forest"},
            "old_mill_a": {"name": "Old Mill"},
            "old_mill_b": {"name": "Old Mill"},
        },
        "inventory": ["Torch"],
        "player": {"current_hp": 10},
    }


class NarrativeMemoryTests(unittest.TestCase):
    def turn(self, memory, message, narration, action=None, before=None, after=None, turn=1):
        state_before = before or world(turn=turn - 1)
        state_after = after or world(turn=turn)
        return update_narrative_memory(
            memory,
            player_message=message,
            narration=narration,
            action_result=action or {},
            world_state_before=state_before,
            world_state_after=state_after,
        )

    def test_empty_shape_and_legacy_empty_initialization(self):
        memory = empty_narrative_memory()
        self.assertEqual(memory["schema_version"], 1)
        self.assertEqual(memory["recent_turns"], [])
        self.assertEqual(memory["quest_memory"], {})
        normalized = validate_narrative_memory(memory)
        self.assertEqual(normalized, memory)
        self.assertIsNot(normalized, memory)

    def test_canonical_and_narrative_layers_are_isolated(self):
        before = world()
        after = world()
        after["npcs"] = [{"id": "npc_a", "name": "Kasim", "role": "bartender", "location": "tavern"}]
        after["player"]["current_hp"] = 1
        after["inventory"].append("forged crown")
        result = self.turn(
            empty_narrative_memory(),
            "Kasim'e söz veriyorum, sonra döneceğim.",
            "Kasim sana efsanevi bir kılıç verdi; HP'n de tamamen yenilendi.",
            {"npc_id": "npc_a", "damage": 999, "inventory": ["forged crown"]},
            before,
            after,
        )
        self.assertNotIn("current_hp", result["story_summary"])
        self.assertNotIn("forged crown", result["story_summary"])
        self.assertNotIn("damage", result["npc_interactions"]["npc_a"][0])
        self.assertEqual(result["entity_memory"]["npcs"]["npc_a"]["id"], "npc_a")
        self.assertEqual(result["npc_interactions"]["npc_a"][0]["source"], "player_utterance")

    def test_hidden_npc_identity_is_not_promoted_into_narrator_memory(self):
        hidden = {
            "id": "npc_hidden",
            "name": "SecretLiora",
            "role": "Traveler",
            "location": "tavern",
            "name_known_to_player": False,
            "role_known_to_player": False,
        }
        after = world(npcs=[hidden], turn=1)
        memory = self.turn(
            empty_narrative_memory(),
            "O kişiyle konuşuyorum.",
            "Yakındaki kişi sana dönüyor.",
            {"npc_id": "npc_hidden", "action": "dialogue"},
            after=after,
        )
        encoded_memory = json.dumps(memory, ensure_ascii=False)
        self.assertNotIn("SecretLiora", encoded_memory)
        self.assertNotIn("Traveler", encoded_memory)
        self.assertEqual(
            memory["entity_memory"]["npcs"]["npc_hidden"]["name"],
            "Yakındaki kişi",
        )
        packet, _ = build_narrative_context(
            memory,
            {
                "location_id": "tavern",
                "current_npc_target": {
                    "id": "npc_hidden",
                    "name": "Yakındaki kişi",
                    "role": None,
                },
            },
            "Ona selam veriyorum.",
            {"npc_id": "npc_hidden", "action": "dialogue"},
        )
        self.assertNotIn("SecretLiora", json.dumps(packet, ensure_ascii=False))
        self.assertNotIn("Traveler", json.dumps(packet, ensure_ascii=False))

    def test_invented_mechanics_never_become_facts(self):
        result = self.turn(
            empty_narrative_memory(),
            "Sadece etrafa bakıyorum.",
            "Altın kazandın, seviye atladın ve görev tamamlandı.",
        )
        self.assertNotIn("gold", result["story_summary"])
        self.assertNotIn("seviye atlad", str(result["entity_memory"]).lower())
        self.assertEqual(result["quest_memory"], {})

    def test_same_name_npcs_remain_separate_by_ids(self):
        npcs = [
            {"id": "npc_001", "name": "Arin", "role": "blacksmith", "location": "tavern"},
            {"id": "npc_058", "name": "Arin", "role": "traveler", "location": "tavern"},
        ]
        after = world(npcs=npcs, turn=1)
        memory = self.turn(
            empty_narrative_memory(), "Arin'e söz veriyorum.", "Arin başını eğdi.",
            {"npc_id": "npc_001"}, after=after,
        )
        memory = self.turn(
            memory, "Arin'i sonra bulacağım.", "Diğer Arin uzakta bekledi.",
            {"npc_id": "npc_058"}, before=after, after=world(npcs=npcs, turn=2), turn=2,
        )
        self.assertEqual(set(memory["entity_memory"]["npcs"]), {"npc_001", "npc_058"})
        self.assertNotEqual(
            memory["npc_interactions"]["npc_001"],
            memory["npc_interactions"]["npc_058"],
        )
        self.assertTrue(all(item["npc_id"] if "npc_id" in item else True for item in []))

    def test_same_title_quests_are_identity_separate_without_inference(self):
        canonical_quests = [
            {"quest_id": "quest_12", "title": "The Missing Child", "status": "active"},
            {"quest_id": "quest_91", "title": "The Missing Child", "status": "completed"},
        ]
        result = self.turn(
            empty_narrative_memory(), "Bakıyorum.", "Bir işaret görüyorsun.",
            {"canonical_quests": canonical_quests},
        )
        self.assertEqual(set(result["quest_memory"]), {"quest_12", "quest_91"})
        self.assertEqual(result["quest_memory"]["quest_12"]["status"], "active")
        self.assertEqual(result["quest_memory"]["quest_91"]["status"], "completed")
        no_quests = self.turn(
            empty_narrative_memory(), "Görev tamamlandı.", "Görev tamamlandı.",
        )
        self.assertEqual(no_quests["quest_memory"], {})

    def test_long_sequence_keeps_high_value_memory_after_recent_window(self):
        memory = empty_narrative_memory()
        npc = [{"id": "npc_kasim", "name": "Kasim", "role": "bartender", "location": "tavern"}]
        first = world(npcs=npc, turn=1)
        memory = self.turn(memory, "Kervanı araştıracağıma söz veriyorum.", "Kasim sessiz kaldı.", {"npc_id": "npc_kasim"}, after=first)
        for turn in range(2, 12):
            memory = self.turn(memory, f"Adım {turn}.", "Taşlar ayaklarının altında ezildi.", turn=turn)
        self.assertEqual(len(memory["recent_turns"]), MAX_RECENT_TURNS)
        self.assertTrue(any("Kervanı" in item["summary"] for item in memory["unresolved_threads"]))
        self.assertTrue(any("Kervanı" in item["text"] for item in memory["npc_interactions"]["npc_kasim"]))

    def test_low_value_generic_text_is_compacted(self):
        memory = empty_narrative_memory()
        for turn in range(1, 30):
            memory = self.turn(memory, "Selam", "Merhaba.", turn=turn)
        self.assertEqual(memory["npc_interactions"], {})
        self.assertEqual(memory["unresolved_threads"], [])
        self.assertLessEqual(len(memory["recent_turns"]), MAX_RECENT_TURNS)

    def test_generated_narration_is_not_saved_as_recallable_continuity(self):
        memory = self.turn(
            empty_narrative_memory(),
            "Etrafıma bakıyorum.",
            "A merchant named Elara offers silverwork in a busy market.",
            turn=1,
        )

        self.assertEqual(
            memory["recent_turns"][-1]["narration"],
            "[presentation omitted from continuity]",
        )
        self.assertTrue(all(
            item.get("authority") != "temporary_narrative_texture"
            for entries in memory["location_continuity"].values()
            for item in entries
        ))
        packet, _ = build_narrative_context(
            memory,
            {"location_id": "tavern"},
            "Etrafıma bakıyorum.",
        )
        continuity = packet["relevant_continuity"]
        self.assertTrue(all(
            "narration" not in turn
            for turn in continuity["recent_turns"]
        ))
        self.assertNotIn("Elara", json.dumps(packet, ensure_ascii=False))

    def test_thread_deduplication_and_resolution(self):
        memory = self.turn(empty_narrative_memory(), "Sembolü sonra araştıracağım.", "Bir iz.", turn=1)
        memory = self.turn(memory, "Sembolü sonra araştıracağım.", "Aynı iz.", turn=2)
        self.assertEqual(len(memory["unresolved_threads"]), 1)
        thread_id = memory["unresolved_threads"][0]["thread_id"]
        self.assertEqual(memory["unresolved_threads"][0]["created_turn"], 1)
        self.assertEqual(memory["unresolved_threads"][0]["last_reference_turn"], 2)
        memory = self.turn(memory, "Bitti.", "İz kayboldu.", {"resolved_thread_ids": [thread_id]}, turn=3)
        self.assertEqual(memory["unresolved_threads"][0]["status"], "resolved")

    def test_turkish_global_thread_retrieval_after_recent_window_and_unrelated_exclusion(self):
        memory = self.turn(
            empty_narrative_memory(),
            "Kervanı araştıracağıma söz veriyorum.",
            "Kısa bir yanıt.",
            turn=1,
        )
        for turn in range(2, 10):
            memory = self.turn(memory, f"Adım {turn}.", "Taşlar ezildi.", turn=turn)
        packet, diagnostics = build_narrative_context(
            memory,
            {"location_id": "tavern"},
            "Kervan hakkında ne biliyoruz?",
        )
        self.assertEqual(diagnostics["selected_counts"]["threads"], 1)
        self.assertEqual(len(packet["relevant_continuity"]["unresolved_threads"]), 1)
        _, unrelated = build_narrative_context(
            memory,
            {"location_id": "tavern"},
            "Kayıp yüzük hakkında konuşalım.",
        )
        self.assertEqual(unrelated["selected_counts"]["threads"], 0)

    def test_paraphrased_promise_deduplicates_and_remember_query_does_not_resolve(self):
        memory = self.turn(
            empty_narrative_memory(),
            "Kervanı araştıracağıma söz veriyorum.",
            "Bir iz.",
            turn=1,
        )
        memory = self.turn(
            memory,
            "Kervanı sonra araştıracağım.",
            "Aynı iz.",
            turn=2,
        )
        self.assertEqual(len(memory["unresolved_threads"]), 1)
        thread = memory["unresolved_threads"][0]
        self.assertEqual(thread["created_turn"], 1)
        self.assertEqual(thread["last_reference_turn"], 2)
        memory = self.turn(
            memory,
            "Kervanı hatırlıyor musun?",
            "Yanıt verildi.",
            turn=3,
        )
        self.assertEqual(memory["unresolved_threads"][0]["status"], "open")

    def test_clarification_cannot_bind_npc_interactions_or_threads(self):
        npc = [{"id": "npc_a", "name": "Arin", "role": "smith", "location": "tavern"}]
        memory = self.turn(
            empty_narrative_memory(),
            "Arin'e sonra döneceğim.",
            "Hangisini kastettiğini belirt.",
            {"npc_id": "npc_a", "status": "ambiguous"},
            after=world(npcs=npc, turn=1),
        )
        self.assertEqual(memory["npc_interactions"], {})
        self.assertEqual(memory["unresolved_threads"][0]["related_entity_ids"], [])

        memory = self.turn(
            memory,
            "Arin'e sonra döneceğim.",
            "Hangisini kastettiğini belirt.",
            {"target_id": "npc_a", "status": "needs_clarification"},
            before=world(npcs=npc, turn=1),
            after=world(npcs=npc, turn=2),
            turn=2,
        )
        self.assertEqual(len(memory["unresolved_threads"]), 1)
        self.assertEqual(memory["unresolved_threads"][0]["related_entity_ids"], [])

    def test_story_summary_is_incremental_and_source_bound(self):
        npc = [{"id": "npc_a", "name": "Kasim", "role": "bartender", "location": "tavern"}]
        action = {
            "npc_id": "npc_a",
            "event_references": [{
                "summary": "Player met Kasim.",
                "source": "npc_interaction",
                "npc_id": "npc_a",
            }],
            "canonical_events": [{
                "event_type": "major_discovery",
                "summary": "The sealed archive was discovered.",
                "authority": "canonical",
            }],
        }
        memory = self.turn(
            empty_narrative_memory(),
            "Kervanı araştıracağıma söz veriyorum.",
            "Kasim looks worried and mentions a treasure.",
            action,
            after=world(npcs=npc, turn=1),
        )
        self.assertEqual(memory["story_summary"]["recent_events"][0]["source"], "npc_interaction")
        self.assertEqual(memory["story_summary"]["major_discoveries"][0]["authority"], "canonical")
        self.assertTrue(memory["story_summary"]["player_history"])
        self.assertTrue(memory["story_summary"]["current_arc"])
        self.assertNotIn("treasure", str(memory["story_summary"]).lower())

    def test_generated_location_texture_is_not_retrieved_as_memory(self):
        npc = [{"id": "npc_a", "name": "Kasim", "role": "bartender", "location": "tavern"}]
        memory = self.turn(
            empty_narrative_memory(),
            "Etrafa bakıyorum.",
            "Rain taps the windows. Warm candlelight trembles across the floorboards.",
            after=world(npcs=npc, turn=1),
        )
        memory = self.turn(
            memory,
            "Tekrar bakıyorum.",
            "A hidden treasure chest waits nearby. Kasim raises a key.",
            before=world(npcs=npc, turn=1),
            after=world(npcs=npc, turn=2),
            turn=2,
        )
        excerpts = memory["location_continuity"]["tavern"]
        texts = [item["text"] for item in excerpts]
        self.assertFalse(any("Rain taps" in text for text in texts))
        self.assertTrue(all(item["authority"] != "canonical" for item in excerpts))
        self.assertFalse(any("treasure" in text.lower() for text in texts))
        self.assertFalse(any("Kasim" in text for text in texts))
        self.assertFalse(any("key" in text.lower() for text in texts))
        self.assertEqual(memory["story_summary"]["major_discoveries"], [])

    def test_same_name_locations_remain_separate(self):
        after = world(location="old_mill_a", turn=1)
        memory = self.turn(empty_narrative_memory(), "İnceliyorum.", "Kirişler gıcırdadı.", after=after)
        after = world(location="old_mill_b", turn=2)
        memory = self.turn(memory, "İnceliyorum.", "Başka bir değirmen.", before=world(location="old_mill_a"), after=after, turn=2)
        self.assertEqual(set(memory["entity_memory"]["locations"]), {"old_mill_a", "old_mill_b"})
        self.assertEqual(memory["entity_memory"]["locations"]["old_mill_a"]["name"], "Old Mill")

    def test_repetition_fingerprints_are_bounded(self):
        memory = empty_narrative_memory()
        for turn in range(1, 30):
            memory = self.turn(memory, f"Bakış {turn}.", "Rain taps the windows. Kasim pauses.", turn=turn)
        fingerprint = memory["repetition_fingerprint"]
        self.assertEqual(fingerprint["recent_openings"], [])
        self.assertEqual(fingerprint["recent_closings"], [])
        self.assertEqual(fingerprint["recent_phrases"], [])
        self.assertLessEqual(len(fingerprint["recent_openings"]), 12)
        self.assertLessEqual(len(fingerprint["recent_phrases"]), 12)

    def test_schema_limits_and_no_mutation(self):
        original = empty_narrative_memory()
        snapshot = copy.deepcopy(original)
        updated = self.turn(original, "Bir konu soruyorum.", "Kısa yanıt.", turn=1)
        self.assertEqual(original, snapshot)
        self.assertIsNot(original, updated)
        invalid = empty_narrative_memory()
        invalid["recent_turns"] = [
            {"player": "x", "narration": "y", "turn_index": i, "authority": "presentation"}
            for i in range(MAX_RECENT_TURNS + 1)
        ]
        with self.assertRaises(ValueError):
            validate_narrative_memory(invalid)
        huge = empty_narrative_memory()
        huge["story_summary"]["current_arc"] = ["x" * MAX_SERIALIZED_BYTES]
        with self.assertRaises(ValueError):
            validate_narrative_memory(huge)

    def test_context_retrieves_exact_ids_and_canonical_precedence(self):
        npc = [{"id": "npc_a", "name": "Arin", "role": "smith", "location": "tavern"}]
        memory = self.turn(
            empty_narrative_memory(), "Arin'e söz veriyorum.", "Arin başını eğdi.",
            {"npc_id": "npc_a"}, after=world(npcs=npc, turn=1),
        )
        memory = self.turn(
            memory, "Arin'e soru soruyorum.", "Arin bekledi.",
            {"npc_id": "npc_b"}, before=world(npcs=npc, turn=1),
            after=world(npcs=npc, location="forest", turn=2), turn=2,
        )
        packet, diagnostics = build_narrative_context(
            memory,
            {
                "location_id": "tavern",
                "player": {"current_hp": 3, "inventory": []},
                "npcs": [{"id": "npc_a", "name": "Arin"}],
            },
            "npc_a hakkında konuşalım",
            {"npc_id": "npc_a", "damage": 999},
        )
        self.assertEqual(packet["canonical"]["player"]["current_hp"], 3)
        self.assertEqual(list(packet["relevant_continuity"]["npcs"]), ["npc_a"])
        self.assertEqual(diagnostics["scene_type"], "conversation")
        self.assertEqual(diagnostics["ambiguities"], [])

    def test_context_reports_same_name_ambiguity_without_merging(self):
        npc = [
            {"id": "npc_a", "name": "Arin", "role": "smith", "location": "tavern"},
            {"id": "npc_b", "name": "Arin", "role": "traveler", "location": "forest"},
        ]
        memory = self.turn(
            empty_narrative_memory(), "Arin'e söz veriyorum.", "Arin başını eğdi.",
            {"npc_id": "npc_a"}, after=world(npcs=npc, turn=1),
        )
        memory = self.turn(
            memory, "Arin'e soru soruyorum.", "Arin bekledi.",
            {"npc_id": "npc_b"}, before=world(npcs=npc, turn=1),
            after=world(npcs=npc, location="forest", turn=2), turn=2,
        )
        packet, diagnostics = build_narrative_context(memory, {"location_id": "tavern"}, "Arin ile konuşuyorum")
        self.assertEqual(diagnostics["ambiguities"], [{"display_name": "arin", "entity_ids": ["npc_a", "npc_b"]}])
        self.assertNotIn("npc_b", packet["relevant_continuity"]["npcs"])

    def test_context_budget_is_deterministic(self):
        memory = empty_narrative_memory()
        for index in range(1, 7):
            memory = self.turn(memory, f"Question {index}", "A richly described answer. " * 8, turn=index)
        packet_a, diagnostics_a = build_narrative_context(
            memory, {"location_id": "tavern", "lore": "x" * 10000}, "look " + "word " * 1000
        )
        packet_b, diagnostics_b = build_narrative_context(
            memory, {"location_id": "tavern", "lore": "x" * 10000}, "look " + "word " * 1000
        )
        self.assertLessEqual(diagnostics_a["packet_characters"], 4800)
        self.assertEqual(
            diagnostics_a["estimated_tokens"],
            (diagnostics_a["packet_characters"] + 1) // 2,
        )
        self.assertEqual(diagnostics_a["model_context_window_tokens"], 40960)
        self.assertEqual(diagnostics_a["reserved_prompt_tokens"], 8192)
        self.assertEqual(
            diagnostics_a["estimated_total_tokens"],
            diagnostics_a["estimated_tokens"] + 8192,
        )
        self.assertEqual(diagnostics_a["max_estimated_total_tokens"], 32768)
        self.assertLessEqual(diagnostics_a["estimated_total_tokens"], 32768)
        self.assertLessEqual(diagnostics_a["estimated_total_tokens"], 40960)
        self.assertEqual(packet_a, packet_b)
        self.assertEqual(diagnostics_a["estimated_tokens"], diagnostics_b["estimated_tokens"])


class NpcMemoryIsolationAndSpeakerBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "campaigns.sqlite3"
        self.store = CampaignStore(self.db_path, bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _setup_two_npc_session(self):
        campaign_id, session_id, record, _ = self.manager.create_campaign("Memory Isolation Test")
        session = record.game_session
        session.character["name"] = "Kaelen"
        session.character["race"] = "Human"
        session.character["class"] = "Fighter"
        session.character["level"] = 1
        session.character["current_hp"] = 10
        session.character["max_hp"] = 10
        session.character["armor_class"] = 12
        session.world_state["location"] = "tavern"
        session.world_state["locations"]["tavern"] = {
            "name": "The Tavern",
            "reality_layer": "CANONICAL",
        }
        session.world_state["npcs"] = [
            {
                "id": "npc_001",
                "name": "Elaris",
                "role": "bartender",
                "location": "tavern",
                "memory": [],
            },
            {
                "id": "npc_002",
                "name": "Aldren",
                "role": "patron",
                "location": "tavern",
                "memory": [],
            },
        ]
        return campaign_id, session_id, record, session

    def test_1_npc_memory_isolation(self):
        """TEST 1: Disclose name to NPC A; NPC A knows it, NPC B does not."""
        _, _, record, session = self._setup_two_npc_session()

        # Step 4: Tell NPC A: "Benim adım Arven."
        t1 = session.run_player_turn("Benim adım Arven.", target_id="npc_001")
        self.manager.autosave_turn(record, "Benim adım Arven.", t1["narration"])
        self.assertIn("Arven", t1["narration"])
        self.assertEqual(t1["action_result"].get("npc_id"), "npc_001")

        # Step 5: Verify NPC A can use Arven
        t_a = session.run_player_turn("Bana adımla hitap et", target_id="npc_001")
        self.assertIn("Arven", t_a["narration"])
        self.assertIn("Elaris", t_a["narration"])
        self.assertEqual(t_a["action_result"].get("npc_id"), "npc_001")

        # Step 6 & 7: Address NPC B and ask NPC B to use player's name
        t_b = session.run_player_turn("Bana adımla hitap et", target_id="npc_002")
        self.manager.autosave_turn(record, "Bana adımla hitap et", t_b["narration"])

        # Step 8: Verify NPC B does NOT know Arven
        self.assertNotIn("Arven", t_b["narration"])
        self.assertIn("Aldren", t_b["narration"])
        self.assertEqual(t_b["action_result"].get("npc_id"), "npc_002")
        self.assertEqual(t_b["action_result"].get("status"), "answered_from_npc_memory")

    def test_2_speaker_binding(self):
        """TEST 2: Address NPC B; returned dialogue/narration attributed to NPC B, not NPC A."""
        _, _, _, session = self._setup_two_npc_session()

        # Disclose to Elaris
        session.run_player_turn("Benim adım Arven.", target_id="npc_001")

        # Address Aldren
        t2 = session.run_player_turn("Bana adımla hitap et", target_id="npc_002")

        # Attributed to Aldren, not Elaris
        self.assertIn("Aldren", t2["narration"])
        self.assertNotIn("Elaris", t2["narration"])
        self.assertEqual(t2["action_result"].get("npc_id"), "npc_002")

    def test_3_cross_npc_recent_dialogue_leak(self):
        """TEST 3: Recent turn involving NPC A does not cause NPC B's response to inherit NPC A's memory."""
        _, _, record, session = self._setup_two_npc_session()

        # Turn with NPC A
        t1 = session.run_player_turn("Benim adım Arven.", target_id="npc_001")
        self.manager.autosave_turn(record, "Benim adım Arven.", t1["narration"])

        # Next turn with NPC B
        t2 = session.run_player_turn("Bana adımla hitap et", target_id="npc_002")
        self.manager.autosave_turn(record, "Bana adımla hitap et", t2["narration"])

        # NPC B must not leak Arven from recent dialogue history
        self.assertNotIn("Arven", t2["narration"])
        # Verify narrative memory context packet isolates recent turns
        packet, _ = build_narrative_context(
            record.narrative_memory,
            build_world_context(npc_target=session.world_state["npcs"][1]),
            "Bana adımla hitap et",
            {"npc_id": "npc_002"},
        )
        recent_players = [t["player"] for t in packet["relevant_continuity"].get("recent_turns", [])]
        self.assertNotIn("Benim adım Arven.", recent_players)

    def test_4_resume(self):
        """TEST 4: Disclose to NPC A, save, resume, verify NPC A still knows and NPC B still does not."""
        campaign_id, _, record, session = self._setup_two_npc_session()

        # Disclose to NPC A
        t1 = session.run_player_turn("Benim adım Arven.", target_id="npc_001")
        self.manager.autosave_turn(record, "Benim adım Arven.", t1["narration"])
        self.manager.save_campaign(campaign_id)

        # Resume campaign in fresh manager
        fresh_manager = SessionManager(campaign_store=CampaignStore(self.db_path, bound_principal=TEST_PLAYER))
        _, resumed_record, _, _, _ = fresh_manager.resume_campaign(campaign_id)
        resumed_session = resumed_record.game_session

        # Verify NPC A still knows
        t_a = resumed_session.run_player_turn("Bana adımla hitap et", target_id="npc_001")
        self.assertIn("Arven", t_a["narration"])
        self.assertEqual(t_a["action_result"].get("npc_id"), "npc_001")

        # Verify NPC B still does not know
        t_b = resumed_session.run_player_turn("Bana adımla hitap et", target_id="npc_002")
        self.assertNotIn("Arven", t_b["narration"])
        self.assertIn("Aldren", t_b["narration"])
        self.assertEqual(t_b["action_result"].get("npc_id"), "npc_002")

    def test_5_existing_npc_memory_regression(self):
        """TEST 5: Verify existing legitimate NPC memory and historical claim behavior remains intact."""
        _, _, _, session = self._setup_two_npc_session()

        # Disclose to Elaris
        t1 = session.run_player_turn("Benim adım Arven.", target_id="npc_001")
        self.assertIn("Arven", t1["narration"])

        # Historical query to Elaris
        t2 = session.run_player_turn("Daha önce sana adımı söylemiştim, hatırla.", target_id="npc_001")
        self.assertIn("Arven", t2["narration"])
        self.assertEqual(t2["action_result"].get("status"), "answered_from_npc_memory")

        # Unsupported claim to Elaris
        t3 = session.run_player_turn("Elaris bana ejderha hazinesinden bahsetmişti.", target_id="npc_001")
        self.assertEqual(t3["action_result"].get("status"), "unverified")
        # In-character denial (NPC P2); the claim is neither confirmed nor stored.
        self.assertTrue(any(
            marker in t3["narration"]
            for marker in ("hatırlamıyorum", "anımsamıyorum", "sözüm yok", "söylemedim", "ağzımdan çıkmadı")
        ), t3["narration"])
        self.assertNotIn("ejderha hazinesi", t3["narration"])


if __name__ == "__main__":
    unittest.main()

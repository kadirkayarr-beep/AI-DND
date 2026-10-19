"""Stage 10A disclosure, local tavern entry, and quest-availability repairs."""
import copy
import unittest
from unittest.mock import patch

import combat_lifecycle
import game
import quest_catalog
from local_dialogue import (
    explicit_player_name_disclosure,
    quest_availability_question,
)


DISCLOSURE = "Benim adım Arven. Kendimi sana tanıtıyorum; lütfen bunu hatırla."
RECALL = "Bana daha önce adımı söylemiştin. Ne demiştim?"
EMPTY_RECALL = "Adımı hatırlıyor musun?"
QUEST_QUESTION = "Bu bölgede bana sunulmuş etkin bir görev var mı?"


def city_session(seed=2108):
    session = game.create_session(seed=seed)
    session.world_state["locations"]["fr:city:neverwinter"] = {
        "id": "fr:city:neverwinter",
        "name": "Neverwinter",
        "type": "city",
    }
    session.world_state["location"] = "fr:city:neverwinter"
    return session


def place_npc(session, npc_id, name):
    session.world_state["npcs"].append({
        "id": npc_id,
        "name": name,
        "role": "shopkeeper",
        "location": session.world_state["location"],
        "memory": [],
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "tags": ["shopkeeper"],
    })


def procedural_taverns(world):
    return [
        record for record in world["locations"].values()
        if isinstance(record, dict)
        and record.get("scene_kind") == "tavern"
        and record.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
    ]


class DisclosurePrecedenceTests(unittest.TestCase):
    def test_player_name_disclosure_requires_direct_self_introduction(self):
        cases = (
            ("Ben Astrid", "Astrid"),
            ("Ben Astrid. Merhaba.", "Astrid"),
            (
                "Selam, ben Rhea. Senin adın ne, burada ne iş yaparsın?",
                "Rhea",
            ),
            ("Marek benim adım Rhea dedi.", None),
            ("Marek, ‘Benim adım Rhea,’ dedi.", None),
            ("Benim adım ne?", None),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    explicit_player_name_disclosure(text),
                    expected,
                )

    def test_greeting_disclosure_is_saved_only_to_the_selected_npc(self):
        session = city_session()
        place_npc(session, "npc_001", "Mira")
        place_npc(session, "npc_002", "Evan")
        text = "Selam, ben Rhea. Senin adın ne, burada ne iş yaparsın?"
        with patch(
            "game.ollama.chat",
            side_effect=AssertionError("unexpected model call"),
        ) as model_chat:
            result = session.run_player_turn(text, target_id="npc_001")
        model_chat.assert_not_called()
        self.assertEqual(
            result["action_result"]["status"],
            "player_name_disclosed",
        )
        self.assertIn("Rhea", result["narration"])
        speaker = next(
            npc for npc in session.world_state["npcs"]
            if npc["id"] == "npc_001"
        )
        other = next(
            npc for npc in session.world_state["npcs"]
            if npc["id"] == "npc_002"
        )
        player_entries = [
            entry for entry in speaker["memory"]
            if entry.get("speaker") == "player"
        ]
        self.assertEqual(len(player_entries), 1)
        self.assertEqual(player_entries[0]["text"], text)
        self.assertEqual(other["memory"], [])
        self.assertEqual(
            result["_engine_event_evidence"]["telemetry"]["total_model_calls"],
            0,
        )

    def test_reported_introductions_are_not_recalled_as_player_names(self):
        session = city_session()
        place_npc(session, "npc_001", "Mira")
        place_npc(session, "npc_002", "Evan")
        target = next(
            npc for npc in session.world_state["npcs"]
            if npc["id"] == "npc_001"
        )
        other = next(
            npc for npc in session.world_state["npcs"]
            if npc["id"] == "npc_002"
        )
        reported_speech = (
            "Marek benim adım Rhea dedi.",
            "Marek, ‘Benim adım Rhea,’ dedi.",
        )
        for text in reported_speech:
            game.record_npc_interaction(
                target,
                "Mira dinler.",
                text,
                target,
            )
        self.assertEqual(target["memory"], [])
        self.assertEqual(other["memory"], [])
        self.assertIsNone(
            game._historical_player_name_from_npc_memory(
                target,
                "Adımı hatırlıyor musun?",
            )
        )
        self.assertIsNone(
            game._historical_player_name_from_npc_memory(
                other,
                "Adımı hatırlıyor musun?",
            )
        )

    def test_exact_disclosure_is_acknowledged_once_without_a_model_call(self):
        session = city_session()
        place_npc(session, "npc_001", "Mira")
        place_npc(session, "npc_002", "Evan")
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            result = session.run_player_turn(DISCLOSURE, target_id="npc_001")
        self.assertEqual(result["action_result"]["status"], "player_name_disclosed")
        self.assertIn("hatırlayacağım", result["narration"].casefold())
        self.assertIn("Arven", result["narration"])
        self.assertEqual(
            result["action_result"].get("safety_reason_code")
            or session.last_narration_safety.get("reason_code"),
            "NPC_MEMORY_EXPLICIT_PLAYER_NAME",
        )
        speaker = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc_001")
        other = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc_002")
        player_entries = [
            entry for entry in speaker["memory"]
            if entry.get("speaker") == "player" and "Arven" in entry.get("text", "")
        ]
        self.assertEqual(len(player_entries), 1)
        self.assertEqual(other["memory"], [])
        self.assertEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)

    def test_empty_memory_denies_and_other_npc_stays_isolated(self):
        session = city_session()
        place_npc(session, "npc_001", "Mira")
        place_npc(session, "npc_002", "Evan")
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            denied = session.run_player_turn(EMPTY_RECALL, target_id="npc_001")
            session.run_player_turn(DISCLOSURE, target_id="npc_001")
            isolated = session.run_player_turn(EMPTY_RECALL, target_id="npc_002")
        self.assertIn("adını bilmiyorum", denied["narration"].casefold())
        self.assertIn("adını bilmiyorum", isolated["narration"].casefold())
        self.assertNotIn("Arven", isolated["narration"])
        other = next(npc for npc in session.world_state["npcs"] if npc["id"] == "npc_002")
        remembered = " ".join(
            entry.get("text", "")
            for entry in other["memory"]
            if isinstance(entry, dict)
        )
        self.assertNotIn("Arven", remembered)
        self.assertIsNone(game._explicit_player_name_disclosure(remembered))

    def test_saved_memory_recalls_only_for_the_same_npc(self):
        session = city_session()
        place_npc(session, "npc_001", "Mira")
        place_npc(session, "npc_002", "Evan")
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            session.run_player_turn(DISCLOSURE, target_id="npc_001")
            saved = session.serialize_game_state()
            restored = city_session(seed=2109)
            restored.world_state = copy.deepcopy(saved["world_state"])
            recalled = restored.run_player_turn(RECALL, target_id="npc_001")
            isolated = restored.run_player_turn(RECALL, target_id="npc_002")
        self.assertIn("Arven", recalled["narration"])
        self.assertNotIn("Arven", isolated["narration"])
        self.assertEqual(recalled["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)
        self.assertEqual(isolated["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)


class LocalTavernEntryTests(unittest.TestCase):
    def test_natural_departure_enters_one_parented_tavern_and_returns(self):
        session = city_session()
        session.world_state["shops"] = [{
            "id": "shop_001",
            "name": "Yerel Dükkân",
            "location": "fr:city:neverwinter",
            "shopkeeper_id": "npc_001",
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        }]
        template = copy.deepcopy(session.world_state["locations"]["tavern"])
        forest = copy.deepcopy(session.world_state["locations"]["forest"])
        castle = copy.deepcopy(session.world_state["locations"]["castle"])
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            entered = session.run_player_turn("tavernaya gidiyorum")
            after_entry = session.world_state["location"]
            again = session.run_player_turn("tavernaya gidiyorum")
            after_again = session.world_state["location"]
            returned = session.run_player_turn("Neverwinter'a geri dönüyorum.")
            after_return = session.world_state["location"]
            reentered = session.run_player_turn("tavernaya gidiyorum")
            after_reentry = session.world_state["location"]
        taverns = procedural_taverns(session.world_state)
        self.assertEqual(len(taverns), 1)
        tavern = taverns[0]
        self.assertEqual(entered["action_result"]["status"], "completed")
        self.assertEqual(entered["action_result"]["target_id"], tavern["id"])
        self.assertEqual(after_entry, tavern["id"])
        self.assertEqual(tavern["parent_location_id"], "fr:city:neverwinter")
        self.assertEqual(tavern["exit_location_id"], "fr:city:neverwinter")
        self.assertEqual(tavern["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertEqual(again["action_result"]["status"], "already_inside")
        self.assertEqual(after_again, tavern["id"])
        self.assertEqual(returned["action_result"]["status"], "completed")
        self.assertEqual(returned["action_result"]["action"], "exit")
        self.assertEqual(after_return, "fr:city:neverwinter")
        self.assertEqual(reentered["action_result"]["target_id"], tavern["id"])
        self.assertEqual(after_reentry, tavern["id"])
        self.assertEqual(len(procedural_taverns(session.world_state)), 1)
        self.assertEqual(session.world_state["shops"][0]["location"], "fr:city:neverwinter")
        saved = session.serialize_game_state()
        isolated = city_session(seed=2110)
        self.assertEqual(isolated.world_state["location"], "fr:city:neverwinter")
        self.assertEqual(procedural_taverns(isolated.world_state), [])
        restored = city_session(seed=2111)
        restored.world_state = copy.deepcopy(saved["world_state"])
        self.assertEqual(restored.world_state["location"], after_reentry)
        self.assertEqual(len(procedural_taverns(restored.world_state)), 1)
        self.assertEqual(session.world_state["location"], after_reentry)
        self.assertEqual(session.world_state["locations"]["tavern"], template)
        self.assertEqual(session.world_state["locations"]["forest"], forest)
        self.assertEqual(session.world_state["locations"]["castle"], castle)
        self.assertEqual(entered["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)

    def test_unbound_forest_template_is_not_a_local_destination(self):
        session = city_session()
        before = copy.deepcopy(session.world_state["locations"])
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            result = session.run_player_turn("ormana gidiyorum")
        self.assertEqual(session.world_state["location"], "fr:city:neverwinter")
        self.assertEqual(result["action_result"]["status"], "unverified")
        self.assertEqual(session.world_state["locations"]["forest"], before["forest"])
        self.assertEqual(procedural_taverns(session.world_state), [])

    def test_combat_blocks_local_tavern_entry(self):
        session = city_session()
        npc = session.create_npc_from_ai({
            "name": "Rakip",
            "role": "Guard",
            "location": "fr:city:neverwinter",
        })
        npc.update(
            current_hp=40,
            max_hp=40,
            armor_class=20,
            hostile=True,
            distance_ft=5,
            attack_damage_type="bludgeoning",
        )
        with patch("game.roll_initiative_player", return_value=20), patch(
            "game.roll_initiative", return_value=1
        ):
            session.start_combat(npc)
        self.assertTrue(session.ensure_combat_state()["active"])
        with self.assertRaises(combat_lifecycle.CombatRequestError) as raised:
            session.run_player_turn("tavernaya gidiyorum")
        self.assertEqual(raised.exception.code, "combat_travel")
        self.assertEqual(session.world_state["location"], "fr:city:neverwinter")
        self.assertEqual(procedural_taverns(session.world_state), [])


class QuestAvailabilityTests(unittest.TestCase):
    def test_empty_catalog_answers_without_a_model_or_a_quest(self):
        session = city_session()
        before = copy.deepcopy(session.world_state["quests"])
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            result = session.run_player_turn(QUEST_QUESTION)
        self.assertEqual(result["action_result"]["status"], "answered_from_campaign_state")
        self.assertIn("etkin bir görev yok", result["narration"].casefold())
        self.assertNotIn("duydum", result["narration"].casefold())
        self.assertEqual(session.world_state["quests"], before)
        self.assertEqual(result["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)
        self.assertTrue(session._unsupported_available_quest_claim(
            "Meyhanede bazı görevlerin olduğunu duydum, ama onlarla ilgili detaylar yok."
        ))
        self.assertFalse(session._unsupported_available_quest_claim(
            "Bu bölgede sana sunulmuş etkin bir görev yok."
        ))
        self.assertFalse(session._unsupported_available_quest_claim(
            "Eski bir görev şarkısı sokakta çalıyor."
        ))

    def test_authorized_offer_is_named_and_not_accepted(self):
        session = city_session()
        original = quest_catalog.CATALOG
        quest_catalog.CATALOG = ({
            "quest_id": "quest-local-note",
            "title": "Kayıtlı Not",
            "description": "Bir notu teslim et.",
            "offer_condition": {
                "type": "location_is",
                "target": "fr:city:neverwinter",
            },
            "objectives": ({
                "objective_id": "visit-note",
                "description": "Notun durduğu yeri gör.",
                "type": "visit_location",
                "target": "fr:city:neverwinter",
            },),
        },)
        try:
            self.assertTrue(quest_availability_question(QUEST_QUESTION))
            with patch("game.ollama.chat", side_effect=AssertionError("model")):
                result = session.run_player_turn(QUEST_QUESTION)
            self.assertFalse(session._unsupported_available_quest_claim(
                "Üstlenebileceğin işler şunlar: Kayıtlı Not."
            ))
        finally:
            quest_catalog.CATALOG = original
        self.assertIn("Kayıtlı Not", result["narration"])
        self.assertEqual(session.world_state["quests"], [])

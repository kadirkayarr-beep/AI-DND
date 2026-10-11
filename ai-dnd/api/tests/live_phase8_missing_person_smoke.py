"""In-process MISSING_PERSON proof, plus a narration check when Ollama is up.

Mechanical completion does not count as a narration review.
"""

from __future__ import annotations

import copy
import json
import os
import unittest

import adventure
import adventure.evidence as evidence
import adventure.projection as projection
import adventure.templates as templates
import game


def _open_story():
    session = game.create_session(seed=8)
    session.world_state["location"] = "tavern"
    place = "tavern"
    session.world_state["npcs"].extend([
        {"id": "npc.source", "location": place, "current_hp": 12, "combat_status": "active", "name": "Marek"},
        {"id": "npc.missing", "location": place, "current_hp": 9, "combat_status": "active", "name": "Kayıp"},
    ])
    quest = templates.instantiate(
        "MISSING_PERSON",
        quest_id="adv.live",
        turn=1,
        opportunity_key="opportunity:live",
        creation_evidence="event:live",
        bindings=templates.prepared_bindings(
            source_npc_id="npc.source",
            target_npc_id="npc.missing",
            location_ids=[place],
        ),
        rumor="Marek kayıp bir muhafızdan söz etti.",
    )
    session.world_state["quests"].append(quest)
    quest.update(adventure.transition(dict(quest), "DISCOVERED", 2))
    quest.update(adventure.transition(dict(quest), "ACTIVE", 3))
    packet = projection.model_packet(session.world_state)
    return session, place, quest, packet


def _story_until_hidden():
    session, _place, _quest, packet = _open_story()
    assert "Tehdidi dağıt" not in json.dumps(packet, ensure_ascii=False)
    return session, packet


def _story():
    session, place, quest, packet = _open_story()
    assert "Tehdidi dağıt" not in json.dumps(packet, ensure_ascii=False)

    def advance(action):
        before = copy.deepcopy(session.world_state)
        session.world_state["flags"]["turn_index"] = session.world_state["flags"].get("turn_index", 0) + 1
        evidence.apply_dynamic_evidence(session.world_state, before, action)

    advance({
        "action": "skill_check", "success": True, "skill": "persuasion",
        "target": "npc.source", "action_id": "check:hook",
    })
    advance({
        "action": "skill_check", "success": True, "skill": "investigation",
        "target": place, "action_id": "check:clue",
    })
    session.world_state["location"] = "forest"
    before = copy.deepcopy(session.world_state)
    session.world_state["location"] = place
    evidence.apply_dynamic_evidence(session.world_state, before, {})
    import adventure.dungeon as dungeon
    campaign_id = "campaign-live"
    session.world_state["campaign_id"] = campaign_id
    dungeon.ensure(session.world_state, campaign_id)
    dungeon.move(session.world_state, campaign_id, "fork")
    dungeon.reveal_hidden(session.world_state, campaign_id, "fork_hidden")
    dungeon.move(session.world_state, campaign_id, "hidden_route")
    before = copy.deepcopy(session.world_state)
    dungeon.move(session.world_state, campaign_id, "captive")
    evidence.apply_dynamic_evidence(session.world_state, before, {})
    advance({
        "action": "skill_check", "success": True, "skill": "persuasion",
        "target": "npc.missing", "action_id": "check:rescue",
    })
    evidence.fail_objective(quest, "threat")
    assert quest["outcome"] == "partial_success"
    assert quest["template_version"] == 1
    shown = projection.journal(session.world_state)
    assert shown["completed"]
    assert "fact_id" not in json.dumps(shown, ensure_ascii=False)
    return session, packet


class MissingPersonSmokeTests(unittest.TestCase):
    def test_mechanical_story_keeps_bindings_and_hides_the_threat(self):
        session, packet = _story()
        quest = session.world_state["quests"][0]
        self.assertEqual(quest["bindings"]["source_npc_id"], "npc.source")
        shown = projection.journal(session.world_state)
        self.assertEqual(shown["completed"][0]["label"], "Doğrulandı")

    def test_narration_uses_one_call_and_does_not_write_the_world(self):
        import ollama

        session, packet = _story_until_hidden()
        quest = session.world_state["quests"][0]
        before = copy.deepcopy(quest)
        prompt = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn("Tehdidi dağıt", prompt)
        self.assertNotIn("template_version", prompt)
        self.assertNotIn("opportunity:", prompt)
        client = ollama.Client(host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"), timeout=90)
        response = client.chat(
            model="qwen3:8b",
            messages=[{
                "role": "user",
                "content": (
                    "Aşağıdaki doğrulanmış oyuncu bilgisiyle tek bir kısa anlatım yaz. "
                    "Yeni kişi, ödül veya görev uydurma.\n" + prompt
                ),
            }],
        )
        text = response["message"]["content"]
        self.assertTrue(isinstance(text, str) and text.strip())
        self.assertEqual(quest["status"], before["status"])
        self.assertEqual(quest["outcome"], before["outcome"])
        self.assertEqual(
            [item["graph_state"] for item in quest["objectives"]],
            [item["graph_state"] for item in before["objectives"]],
        )
        self.assertNotIn("npc.invented", {npc.get("id") for npc in session.world_state["npcs"]})


if __name__ == "__main__":
    unittest.main()

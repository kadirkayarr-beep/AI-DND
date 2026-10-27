"""W01: knowledge layers stay separate — world fact, NPC belief, player knowledge.

A rumour, a manual note or an attributed claim never becomes a canonical fact; an NPC who did not witness an event does not
learn it; a name the player does not know appears in no player-facing projection (UI state, narrative memory/context for the
model, public interaction view) and never under a debug label such as UNKNOWN FACTS; no mind-reading mechanic exists, so no
thought is disclosed (a secret perspective entry stays out of every projection).
"""
from __future__ import annotations

import copy
import json
import pathlib
import unittest

import game
import interaction_adventure as interaction
from api.campaign_journal import empty_campaign_journal, update_campaign_journal
from api.narrative_memory import build_narrative_context, update_narrative_memory
from api.serializers import serialize_session_state
from api.tests.test_campaign_time import scene

HIDDEN_NAME = "Kara Vexmoor"
HIDDEN_ROLE = "Gölge Tüccarı"
SECRET_TEXT = "Kara Vexmoor gerçekte krallığın casusudur."


def npc(world, npc_id, name, **facts):
    record = {"id": npc_id, "name": name, "role": "Yolcu", "location": world["location"], "combat_status": "active",
              "current_hp": 10, "max_hp": 10, "armor_class": 10}
    record.update(facts)
    world["npcs"].append(record)
    return record


def hidden_session():
    session = scene()
    npc(session.world_state, "npc_hidden", HIDDEN_NAME, role=HIDDEN_ROLE, name_known_to_player=False, role_known_to_player=False)
    return session


class KnowledgeLayerTests(unittest.TestCase):
    def test_knowledge_layers_never_promote_note_to_fact(self):
        session = hidden_session()
        world = session.world_state
        # --- an unknown name appears in NO player-facing projection --------------------------------------------------
        action = {"action": "talk", "npc_id": "npc_hidden", "status": "resolved"}
        memory = update_narrative_memory(
            None, player_message="Selam.", narration="Bir yabancı sana bakıyor.", action_result=action,
            world_state_before=copy.deepcopy(world), world_state_after=copy.deepcopy(world))
        packet, _meta = build_narrative_context(memory, {"location_id": world["location"]}, "Yabancıya tekrar sesleniyorum.", action)
        public = serialize_session_state(session)
        before_state = session.serialize_game_state()
        projections = {
            "ui_state": public,
            "narrative_memory": memory,
            "narrative_context": packet,
            "interaction_public": interaction.public(world),
            "journal": update_campaign_journal(empty_campaign_journal(), before_state, session.serialize_game_state(),
                                               action, public["world"]),
            "world_context": game.build_world_context(world["npcs"][-1], session=session),
        }
        # Control: once the player learns the name, the same projections DO carry it (the check can see a leak).
        world["npcs"][-1]["name_known_to_player"] = True
        self.assertIn(HIDDEN_NAME, json.dumps(serialize_session_state(session), ensure_ascii=False, default=str))
        world["npcs"][-1]["name_known_to_player"] = False
        secret_labels = sorted(
            name for name, value in projections.items()
            if HIDDEN_NAME in json.dumps(value, ensure_ascii=False, default=str)
            or HIDDEN_ROLE in json.dumps(value, ensure_ascii=False, default=str)
            or "UNKNOWN FACTS" in json.dumps(value, ensure_ascii=False, default=str))
        # --- an attributed claim stays a claim; it is never evidence or a canonical fact -----------------------------
        state = interaction.get(world)
        before_knowledge = copy.deepcopy(world.get("player_knowledge"))
        claim_event = interaction._remember_claim(world, state, "Kral dün gece öldü.", world["npcs"][-1], "addressed")
        claims = [entry for entry in state["perspectives"].get("npc_hidden", []) if entry["source_id"] == claim_event["event_id"]]
        manual_note_promoted = (
            any(entry["kind"] != "player_claim" for entry in claims)
            or claim_event["event_id"] in interaction.known_evidence({**world, interaction.KEY: state})
            or world.get("player_knowledge") != before_knowledge)
        # --- a witness fact for an NPC that was not a listener is refused ----------------------------------------------
        accepted = interaction._event(world, state, "witnessed_fact", "Köprüde bir kavga oldu.", world["npcs"][-1])
        world[interaction.KEY] = state
        bystander = npc(world, "npc_far", "Uzaktaki Kişi")
        try:
            interaction.record_witness(world, accepted["event_id"], "Köprüde bir kavga oldu.", [bystander["id"]])
            unwitnessed_learned = True
        except ValueError:
            unwitnessed_learned = bool(interaction.get(world)["perspectives"].get("npc_far"))
        obs = {
            "manual_note_promoted_to_fact": manual_note_promoted,
            "unwitnessed_npc_learned_event": unwitnessed_learned,
            "secret_labels_in_player_payload": secret_labels,
            "mind_reading_disclosures": [],
            "rule_permitted_disclosures": [],
        }
        self.assertIs(obs["manual_note_promoted_to_fact"], False)
        self.assertIs(obs["unwitnessed_npc_learned_event"], False)
        self.assertEqual(obs["secret_labels_in_player_payload"], [])
        self.assertEqual(obs["mind_reading_disclosures"], obs["rule_permitted_disclosures"])

    def test_a_removed_npc_does_not_fall_back_to_its_raw_name_in_a_combat_projection(self):
        # Reviewer-found path: the combat projection fell back to the raw name when the NPC id was no longer in the world.
        from api.serializers import serialize_combat_result
        session = hidden_session()
        gone = {"action": "attack", "outcome": "hit", "combat_started": True, "target_id": "npc_gone", "target_name": HIDDEN_NAME,
                "enemy_actions": [{"actor": "npc_gone", "actor_name": HIDDEN_NAME, "outcome": "miss", "damage": 0}]}
        control = {**gone, "target_id": "npc_hidden", "enemy_actions": [dict(gone["enemy_actions"][0], actor="npc_hidden")]}
        projected = json.dumps(serialize_combat_result(gone, session), ensure_ascii=False, default=str)
        guarded = json.dumps(serialize_combat_result(control, session), ensure_ascii=False, default=str)
        self.assertNotIn(HIDDEN_NAME, guarded, "control: a present unknown-named NPC is already guarded")
        self.assertNotIn(HIDDEN_NAME, projected, "a removed NPC id must not reopen the raw-name fallback")

    def test_a_secret_perspective_entry_stays_out_of_every_projection(self):
        session = hidden_session()
        world = session.world_state
        state = interaction.get(world)
        state["perspectives"]["npc_hidden"] = [interaction.PerspectiveEntry(
            entry_id="perspective:secret", kind="belief", text=SECRET_TEXT, source_id="belief:1", secret=True).model_dump()]
        world[interaction.KEY] = state
        view = interaction.perspective(world, world["npcs"][-1])
        self.assertEqual(view["entries"], [], "a secret entry is not a disclosable perspective")
        rendered = json.dumps({"public": interaction.public(world), "ui": serialize_session_state(session)},
                              ensure_ascii=False, default=str)
        self.assertNotIn(SECRET_TEXT, rendered)

    def test_no_mind_reading_mechanic_discloses_thoughts_today(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        for name in ("game.py", "interaction_adventure.py", "npc_statements.py"):
            text = (root / name).read_text(encoding="utf-8").casefold()
            self.assertNotIn("detect thoughts", text, f"{name}: a mind-reading rule would need a permitted-scope test")


if __name__ == "__main__":
    unittest.main()

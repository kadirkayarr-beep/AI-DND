import unittest
from unittest.mock import patch

from api.narrative_director import (
    install_narrative_context_adapter,
    narrative_turn_context,
)
from api.narrative_memory import (
    empty_narrative_memory,
    update_narrative_memory,
)


class _FakeGame:
    def __init__(self):
        self.original_context = {
            "location": {"id": "loc-1", "name": "Old Mill"},
            "npcs": [{"id": "npc-1", "name": "Mira"}],
        }
        self.finalize_calls = []

    def build_world_context(self, npc_target=None):
        return self.original_context

    def ask_dungeon_master(self, **kwargs):
        return self.build_world_context(kwargs.get("npc_target"))

    def finalize_narration(self, *args, **kwargs):
        self.finalize_calls.append({"args": args, "kwargs": dict(kwargs)})
        return args[0] if args else ""


class NarrativeDirectorAdapterTests(unittest.TestCase):
    def test_context_is_request_scoped_and_does_not_mutate_engine_context(self):
        engine = _FakeGame()
        install_narrative_context_adapter(engine)
        memory = update_narrative_memory(
            empty_narrative_memory(),
            player_message="Mira, tell me about the old caravan.",
            narration="The room is quiet.",
            action_result={
                "action": "dialogue",
                "status": "success",
                "npc_id": "npc-1",
            },
            world_state_before={},
            world_state_after={
                "location": "loc-1",
                "npcs": [
                    {
                        "id": "npc-1",
                        "name": "Mira",
                        "role": "merchant",
                        "location": "loc-1",
                    }
                ],
            },
        )

        with narrative_turn_context(
            memory,
            "Mira, tell me about the old caravan.",
        ) as frame:
            enriched = engine.ask_dungeon_master(
                action_result={"action": "dialogue", "npc_id": "npc-1"}
            )
            engine.finalize_narration("Mira answers.", "Mira, tell me about it.")

        self.assertIn("narrative_continuity", enriched)
        self.assertIn("authority_boundary", enriched["narrative_continuity"])
        self.assertEqual(frame.diagnostics["selected_counts"]["npcs"], 1)
        self.assertEqual(
            engine.finalize_calls[-1]["kwargs"]["supported_player_claims"],
            [{
                "npc_id": "npc-1",
                "text": "Mira, tell me about the old caravan.",
            }],
        )
        self.assertNotIn("narrative_continuity", engine.original_context)
        self.assertNotIn("narrative_continuity", engine.build_world_context())
        engine.finalize_narration("Outside the request.", "Look around.")
        self.assertNotIn(
            "supported_player_claims", engine.finalize_calls[-1]["kwargs"]
        )

    def test_adapter_exports_only_fitted_player_utterances(self):
        engine = _FakeGame()
        install_narrative_context_adapter(engine)
        packet = {
            "relevant_continuity": {
                "npc_interactions": {
                    "npc-1": [
                        {
                            "text": "Mira, my name is Rowan.",
                            "source": "player_utterance",
                            "authority": "narrative_continuity",
                        },
                        {
                            "text": "The room was quiet.",
                            "source": "model_narration",
                            "authority": "narrative_continuity",
                        },
                        {
                            "text": "Mira remembers Rowan.",
                            "source": "player_utterance",
                            "authority": "model_generated",
                        },
                    ]
                }
            }
        }
        diagnostics = {"selected_counts": {"npcs": 1}}
        with patch(
            "api.narrative_director.build_narrative_context",
            return_value=(packet, diagnostics),
        ):
            with narrative_turn_context(
                empty_narrative_memory(), "Mira, what is my name?"
            ):
                engine.ask_dungeon_master(
                    action_result={"action": "dialogue", "npc_id": "npc-1"}
                )
                engine.finalize_narration("Answer.", "Mira, what is my name?")

        self.assertEqual(
            engine.finalize_calls[-1]["kwargs"]["supported_player_claims"],
            [{"npc_id": "npc-1", "text": "Mira, my name is Rowan."}],
        )

        # When the fitted packet omits interaction memory, do not read it back
        # from the unbounded request memory.
        with patch(
            "api.narrative_director.build_narrative_context",
            return_value=({"relevant_continuity": {}}, diagnostics),
        ):
            with narrative_turn_context(
                empty_narrative_memory(), "Mira, what is my name?"
            ):
                engine.ask_dungeon_master(
                    action_result={"action": "dialogue", "npc_id": "npc-1"}
                )
                engine.finalize_narration("Answer.", "Mira, what is my name?")
        self.assertEqual(
            engine.finalize_calls[-1]["kwargs"]["supported_player_claims"], []
        )

    def test_context_is_cleared_after_exception(self):
        engine = _FakeGame()
        install_narrative_context_adapter(engine)
        with self.assertRaisesRegex(RuntimeError, "test"):
            with narrative_turn_context(
                empty_narrative_memory(),
                "Look around.",
            ):
                raise RuntimeError("test")

        result = engine.build_world_context()
        self.assertIs(result, engine.original_context)
        engine.finalize_narration("After exception.", "Look around.")
        self.assertNotIn(
            "supported_player_claims", engine.finalize_calls[-1]["kwargs"]
        )

    def test_install_is_idempotent(self):
        engine = _FakeGame()
        install_narrative_context_adapter(engine)
        wrapped = engine.build_world_context
        finalize_wrapped = engine.finalize_narration
        install_narrative_context_adapter(engine)
        self.assertIs(engine.build_world_context, wrapped)
        self.assertIs(engine.finalize_narration, finalize_wrapped)


if __name__ == "__main__":
    unittest.main()
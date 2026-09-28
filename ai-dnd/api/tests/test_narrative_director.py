import unittest

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

    def build_world_context(self, npc_target=None):
        return self.original_context

    def ask_dungeon_master(self, **kwargs):
        return self.build_world_context(kwargs.get("npc_target"))


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

        self.assertIn("narrative_continuity", enriched)
        self.assertIn("authority_boundary", enriched["narrative_continuity"])
        self.assertEqual(frame.diagnostics["selected_counts"]["npcs"], 1)
        self.assertNotIn("narrative_continuity", engine.original_context)
        self.assertNotIn("narrative_continuity", engine.build_world_context())

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

    def test_install_is_idempotent(self):
        engine = _FakeGame()
        install_narrative_context_adapter(engine)
        wrapped = engine.build_world_context
        install_narrative_context_adapter(engine)
        self.assertIs(engine.build_world_context, wrapped)


if __name__ == "__main__":
    unittest.main()
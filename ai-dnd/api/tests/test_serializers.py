"""Direct tests for the small projection and redaction helpers in api.serializers."""
import os
import unittest
from unittest.mock import patch

from api import serializers


class RedactionTests(unittest.TestCase):
    def test_configured_secrets_are_redacted_in_keys_values_and_lists(self):
        env = {"OLLAMA_HOST": "http://10.0.0.5:11434", "OLLAMA_PROXY_TOKEN": "tok-123"}
        with patch.dict(os.environ, env):
            out = serializers.redact_sensitive_values({
                "detail": "host http://10.0.0.5:11434 refused tok-123",
                "tok-123": ("a", "tok-123"),
                "count": 3,
            })
        self.assertEqual(out, {
            "detail": "host [redacted] refused [redacted]",
            "[redacted]": ["a", "[redacted]"],
            "count": 3,
        })

    def test_nothing_changes_without_configured_secrets(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(serializers.redact_sensitive_values({"a": "b"}), {"a": "b"})


class ProjectionTests(unittest.TestCase):
    def test_project_fields_copies_only_the_allowlisted_fields(self):
        source = {"id": "n1", "inventory": [{"item_id": "x"}], "secret": "hidden"}
        projected = serializers._project_fields(source, ("id", "inventory"))
        self.assertEqual(projected, {"id": "n1", "inventory": [{"item_id": "x"}]})
        projected["inventory"].append("changed")
        self.assertEqual(source["inventory"], [{"item_id": "x"}], "the projection is a detached copy")

    def test_project_fields_of_a_non_mapping_is_empty(self):
        self.assertEqual(serializers._project_fields(["id"], ("id",)), {})

    def test_project_list_drops_items_with_no_allowlisted_field(self):
        rows = [{"id": "a"}, {"other": 1}, "text", {"id": "b", "x": 2}]
        self.assertEqual(serializers._project_list(rows, ("id",)), [{"id": "a"}, {"id": "b"}])
        self.assertEqual(serializers._project_list("not a list", ("id",)), [])


class CombatNameTests(unittest.TestCase):
    def test_player_and_non_text_identities_keep_the_fallback(self):
        self.assertEqual(serializers._public_combat_name("player", "Carius", {}), "Carius")
        self.assertEqual(serializers._public_combat_name(None, "Biri", {"npcs": []}), "Biri")

    def test_identity_missing_from_the_world_fails_closed(self):
        world = {"npcs": [{"id": "npc_a", "name": "Marek"}]}
        self.assertEqual(serializers._public_combat_name("npc_gone", "Marek", world),
                         serializers._UNKNOWN_COMBATANT_NAME)


if __name__ == "__main__":
    unittest.main()

"""D-143: every NPC the state shows carries every key the GameNpc contract requires.

The courtyard Yolcu (monster_sense._begin) has no appearance and no relationship. The serializer dropped the
missing keys, while GameNpc (openapi.yaml, and the Zod schema generated from it) requires both keys and only
lets their values be null, so the server's own state failed its own contract.
"""
import unittest
from pathlib import Path

import yaml

import game
import monster_sense
from api.serializers import serialize_session_state

SPEC = Path(__file__).resolve().parents[3] / "lib" / "api-spec" / "openapi.yaml"
_JSON_TYPES = {"string": str, "integer": int, "array": list}


def _game_npc_schema():
    with SPEC.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)["components"]["schemas"]["GameNpc"]


def _contract_errors(npc, schema):
    """What in one serialized NPC the GameNpc schema rejects (keys, extra keys, value types)."""
    errors = [f"missing {key}" for key in schema["required"] if key not in npc]
    for key, value in npc.items():
        prop = schema["properties"].get(key)
        if prop is None:
            errors.append(f"extra {key}")
            continue
        types = prop["type"] if isinstance(prop["type"], list) else [prop["type"]]
        if value is None:
            if "null" not in types:
                errors.append(f"{key} is null but not nullable")
        elif not any(isinstance(value, _JSON_TYPES[t]) and not isinstance(value, bool)
                     for t in types if t != "null"):
            errors.append(f"{key} has type {type(value).__name__}, contract {types}")
    return errors


class YolcuMatchesTheNpcContractTests(unittest.TestCase):
    def setUp(self):
        self.schema = _game_npc_schema()
        self.session = game.create_session(seed=4)
        world = self.session.world_state
        world["location"] = "courtyard"
        world.setdefault("locations", {})["courtyard"] = {"id": "courtyard", "name": "Avlu"}
        self.assertTrue(monster_sense.resolve_turn(self.session, "/encounter begin")["success"])

    def _yolcu(self):
        npcs = serialize_session_state(self.session)["npcs"]
        return next(npc for npc in npcs if npc["id"] == monster_sense.NPC_ID)

    def test_the_visible_yolcu_passes_the_game_npc_contract(self):
        self.assertEqual(_contract_errors(self._yolcu(), self.schema), [])

    def test_the_missing_appearance_and_relationship_are_sent_as_null(self):
        yolcu = self._yolcu()
        self.assertIn("appearance", yolcu)
        self.assertIsNone(yolcu["appearance"])
        self.assertIn("relationship", yolcu)
        self.assertIsNone(yolcu["relationship"])

    def test_the_engine_npc_itself_is_left_unchanged(self):
        self._yolcu()
        engine_npc = next(npc for npc in self.session.world_state["npcs"] if npc["id"] == monster_sense.NPC_ID)
        self.assertNotIn("appearance", engine_npc)
        self.assertNotIn("relationship", engine_npc)

    def test_known_values_are_kept_as_they_are(self):
        engine_npc = next(npc for npc in self.session.world_state["npcs"] if npc["id"] == monster_sense.NPC_ID)
        engine_npc["appearance"] = "Tozlu pelerinli, sıska biri."
        engine_npc["relationship"] = "hostile"
        yolcu = self._yolcu()
        self.assertEqual(yolcu["appearance"], "Tozlu pelerinli, sıska biri.")
        self.assertEqual(yolcu["relationship"], "hostile")
        self.assertEqual(_contract_errors(yolcu, self.schema), [])

    def test_the_null_filled_keys_are_exactly_the_contract_required_nullable_keys(self):
        from api.serializers import _NPC_NULLABLE_REQUIRED_FIELDS
        nullable_required = {
            key for key in self.schema["required"]
            if "null" in (self.schema["properties"][key]["type"]
                          if isinstance(self.schema["properties"][key]["type"], list) else [])
        }
        self.assertEqual(set(_NPC_NULLABLE_REQUIRED_FIELDS), nullable_required)


if __name__ == "__main__":
    unittest.main()

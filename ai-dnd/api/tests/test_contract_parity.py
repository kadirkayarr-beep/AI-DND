"""Contract checks between the published OpenAPI file and the FastAPI app."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.campaign_journal import (
    JOURNAL_SCHEMA_VERSION,
    MAX_EVENTS,
    MAX_LOCATIONS,
    MAX_NPCS,
    MAX_OBJECTIVES_PER_QUEST,
    MAX_QUESTS,
    _ENVIRONMENTS as JOURNAL_ENVIRONMENTS,
    _EVENT_TYPES,
    _OBJECTIVE_STATUSES,
    _QUEST_STATUSES,
    empty_campaign_journal,
    validate_campaign_journal,
)
from api.main import app
from api.schemas import (
    CampaignCreateRequest,
    CampaignDetailResponse,
    CampaignHistoryEntry,
    CampaignSessionResponse,
    CampaignSummary,
    CharacterCreateInput,
    CharacterCreationOptions,
    HealthResponse,
    SessionResponse,
    TurnRequest,
    TurnResponse,
)
from api.serializers import (
    _COMBAT_ATTACK_FIELDS,
    _COMBAT_TURN_FIELDS,
    _LOCATION_FIELDS,
    _PLAYER_FIELDS,
    serialize_combat_result,
    serialize_session_state,
)
from api.world_metadata import (
    DEFAULT_TIME_OF_DAY,
    DEFAULT_WEATHER,
    ENVIRONMENTS,
    TIMES_OF_DAY,
    WEATHER_TYPES,
    world_metadata_for_state,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = WORKSPACE_ROOT / "lib" / "api-spec" / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
SPEC_TEXT = OPENAPI_PATH.read_text(encoding="utf-8")


def _route_inventory(spec_text: str) -> set[tuple[str, str]]:
    """Read the small, stable paths/methods subset without adding a YAML dependency."""
    lines = spec_text.splitlines()
    base_path = ""
    in_servers = False
    for line in lines:
        if line == "servers:":
            in_servers = True
            continue
        if in_servers and line and not line[0].isspace():
            break
        if in_servers:
            match = re.match(r"\s+- url:\s*([^\s#]+)", line)
            if match:
                base_path = match.group(1).rstrip("/")
                break

    routes: set[tuple[str, str]] = set()
    in_paths = False
    current_path: str | None = None
    for line in lines:
        if line == "paths:":
            in_paths = True
            continue
        if in_paths and line and not line[0].isspace():
            break
        if not in_paths:
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 2 and stripped.startswith("/") and stripped.endswith(":"):
            current_path = stripped[:-1]
        elif (
            current_path is not None
            and indent == 4
            and stripped.endswith(":")
            and stripped[:-1].lower() in HTTP_METHODS
        ):
            routes.add(
                (stripped[:-1].upper(), f"{base_path}{current_path}")
            )
    return routes


def _schema_block(name: str) -> str:
    components_text = SPEC_TEXT.split("\ncomponents:\n", 1)[1]
    schemas_text = re.split(
        r"(?m)^  responses:\s*$",
        components_text,
        maxsplit=1,
    )[0]
    lines = schemas_text.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line == f"    {name}:"
        ),
        None,
    )
    if start is None:
        raise AssertionError(f"OpenAPI schema {name!r} was not found")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.fullmatch(r"    [A-Za-z0-9_]+:", lines[index])
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _property_names(schema_name: str) -> set[str]:
    lines = _schema_block(schema_name).splitlines()
    properties_line = next(
        (
            index
            for index, line in enumerate(lines)
            if line == "      properties:"
        ),
        None,
    )
    if properties_line is None:
        return set()
    names: set[str] = set()
    for line in lines[properties_line + 1 :]:
        indent = len(line) - len(line.lstrip())
        if line.strip() and indent <= 6:
            break
        if indent == 8 and line.strip().endswith(":"):
            names.add(line.strip()[:-1])
    return names


def _property_block(schema_name: str, property_name: str) -> str:
    lines = _schema_block(schema_name).splitlines()
    properties_line = next(
        index for index, line in enumerate(lines) if line == "      properties:"
    )
    start = next(
        (
            index
            for index in range(properties_line + 1, len(lines))
            if lines[index] == f"        {property_name}:"
        ),
        None,
    )
    if start is None:
        raise AssertionError(
            f"OpenAPI property {schema_name}.{property_name} was not found"
        )
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].strip()
            and len(lines[index]) - len(lines[index].lstrip()) <= 8
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _enum_values(schema_name: str, property_name: str) -> set[Any]:
    lines = _property_block(schema_name, property_name).splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)enum:\s*(.*)$", line)
        if not match:
            continue
        indent = len(match.group(1))
        inline = match.group(2).strip()
        if inline.startswith("[") and inline.endswith("]"):
            raw_values = inline[1:-1].split(",")
        else:
            raw_values = []
            for candidate in lines[index + 1 :]:
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate.strip() and candidate_indent <= indent:
                    break
                item = re.match(r"^\s*-\s*(.*?)\s*$", candidate)
                if item:
                    raw_values.append(item.group(1))
        parsed: set[Any] = set()
        for value in raw_values:
            value = value.strip().strip("'\"")
            parsed.add(int(value) if value.isdigit() else value)
        return parsed
    return set()


def _runtime_field_names(model: Any) -> set[str]:
    return {
        field.alias or name
        for name, field in model.model_fields.items()
    }


class ContractParityTests(unittest.TestCase):
    def test_documented_routes_match_fastapi_and_preserve_both_alias_families(self):
        methods = {
            method
            for method in HTTP_METHODS
        }
        runtime_routes = {
            (method, route.path)
            for route in app.routes
            if route.path.startswith("/api/")
            for method in (route.methods or set())
            if method.lower() in methods
        }
        documented_routes = _route_inventory(SPEC_TEXT)
        self.assertEqual(runtime_routes, documented_routes)
        self.assertEqual(len(documented_routes), 24)

        alias_pairs = (
            ("GET", "/api/game/health", "/api/health"),
            ("GET", "/api/game/character-options", "/api/character-options"),
            ("POST", "/api/game/sessions", "/api/sessions"),
            ("GET", "/api/game/sessions/{session_id}/state", "/api/sessions/{session_id}/state"),
            ("POST", "/api/game/sessions/{session_id}/turn", "/api/sessions/{session_id}/turn"),
            ("GET", "/api/game/campaigns", "/api/campaigns"),
            ("POST", "/api/game/campaigns", "/api/campaigns"),
            ("GET", "/api/game/campaigns/{campaign_id}", "/api/campaigns/{campaign_id}"),
            ("POST", "/api/game/campaigns/{campaign_id}/resume", "/api/campaigns/{campaign_id}/resume"),
            ("POST", "/api/game/campaigns/{campaign_id}/save", "/api/campaigns/{campaign_id}/save"),
        )
        for method, canonical, alias in alias_pairs:
            with self.subTest(method=method, canonical=canonical):
                self.assertIn((method, canonical), documented_routes)
                self.assertIn((method, alias), documented_routes)

    def test_operation_ids_are_unique_and_error_statuses_are_documented(self):
        path_text = SPEC_TEXT.split("paths:\n", 1)[1].split("\ncomponents:\n", 1)[0]
        operation_ids = re.findall(
            r"(?m)^      operationId:\s*([A-Za-z0-9_]+)\s*$",
            path_text,
        )
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

        status_expectations = {
            ("/game/sessions/{session_id}/state", "get"): {"200", "404", "422"},
            ("/game/sessions/{session_id}/turn", "post"): {
                "200", "404", "422", "500", "503"
            },
            ("/game/campaigns", "post"): {"200", "422", "500", "503"},
            ("/game/campaigns/{campaign_id}", "get"): {
                "200", "404", "409", "422", "500", "503"
            },
        }
        for (path, method), expected in status_expectations.items():
            with self.subTest(path=path, method=method):
                operation = _operation_block(path, method)
                actual = set(
                    re.findall(r'(?m)^        "(\d{3})":\s*$', operation)
                )
                self.assertEqual(actual, expected)

    def test_health_and_request_schemas_match_runtime_models(self):
        self.assertEqual(
            _property_names("HealthResponse"),
            _runtime_field_names(HealthResponse),
        )
        self.assertEqual(
            _enum_values("HealthResponse", "status"),
            {HealthResponse().status},
        )
        self.assertEqual(
            _enum_values("HealthResponse", "engine"),
            {HealthResponse().engine},
        )
        self.assertEqual(
            _enum_values("HealthResponse", "model"),
            {HealthResponse().model},
        )

        self.assertEqual(
            _property_names("GameTurnInput"),
            _runtime_field_names(TurnRequest),
        )
        turn_input = _schema_block("GameTurnInput")
        self.assertIn("additionalProperties: false", turn_input)
        message_schema = _property_block("GameTurnInput", "message")
        self.assertIn("minLength: 1", message_schema)
        self.assertIn("maxLength: 4000", message_schema)
        with self.assertRaises(ValidationError):
            TurnRequest(message="   ")
        with self.assertRaises(ValidationError):
            TurnRequest.model_validate({"message": "look", "current_hp": 99})

    def test_campaign_and_session_schema_fields_match_fastapi_models(self):
        response_models = {
            "GameSession": SessionResponse,
            "CharacterCreationOptions": CharacterCreationOptions,
            "CampaignSummary": CampaignSummary,
            "CampaignHistoryEntry": CampaignHistoryEntry,
            "CampaignDetail": CampaignDetailResponse,
            "CampaignSession": CampaignSessionResponse,
            "GameTurnResult": TurnResponse,
        }
        for schema_name, model in response_models.items():
            with self.subTest(schema=schema_name):
                self.assertEqual(_property_names(schema_name), _runtime_field_names(model))

        self.assertEqual(
            _property_names("CampaignCreateInput"),
            _runtime_field_names(CampaignCreateRequest),
        )
        self.assertIn("additionalProperties: false", _schema_block("CampaignCreateInput"))
        self.assertIn('"null"', _property_block("CampaignCreateInput", "name"))
        character_schema = _schema_block("CharacterCreateInput")
        self.assertEqual(
            _property_names("CharacterCreateInput"),
            _runtime_field_names(CharacterCreateInput),
        )
        self.assertIn("additionalProperties: false", character_schema)
        self.assertEqual(
            _enum_values("CharacterCreateInput", "mode"),
            {"custom", "random"},
        )
        for field_name in ("name", "race", "class"):
            with self.subTest(character_field=field_name):
                self.assertIn(
                    '"null"',
                    _property_block("CharacterCreateInput", field_name),
                )
        CharacterCreateInput.model_validate(
            {"mode": "custom", "name": "Ari", "race": "Elf", "class": "Wizard"}
        )
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate({"mode": "custom"})
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate({"mode": "random", "name": "Ari"})

    def test_public_state_world_and_combat_shapes_match_serializers(self):
        class SerializableSession:
            world_metadata = None

            def quest_offers(self):
                return []

            def serialize_game_state(self):
                return {
                    "player": {field: None for field in _PLAYER_FIELDS},
                    "world_state": {
                        "location": "tavern",
                        "locations": {
                            "tavern": {field: "Tavern" for field in _LOCATION_FIELDS}
                        },
                        "flags": {"turn_index": 2},
                        "inventory": [],
                        "npcs": [],
                        "features": [],
                        "doors": [],
                        "combat": {
                            "active": False,
                            "round": 0,
                            "initiative_order": [],
                            "current_turn_index": 0,
                            "participants": [],
                            "target_id": None,
                        },
                        "player_combat_status": "active",
                    },
                }

        public_state = serialize_session_state(SerializableSession())
        self.assertEqual(set(public_state), _property_names("GameState"))
        self.assertEqual(set(public_state["character"]), _property_names("GameCharacter"))
        self.assertEqual(set(public_state["combat"]), _property_names("GameCombat"))
        self.assertEqual(
            set(public_state["world"]),
            _property_names("GameWorldMetadata"),
        )
        self.assertEqual(set(public_state["journal"]), _property_names("CampaignJournal"))
        self.assertEqual(public_state["journal"], empty_campaign_journal())
        validate_campaign_journal(public_state["journal"])

        self.assertEqual(
            _enum_values("GameWorldMetadata", "environment"),
            set(ENVIRONMENTS),
        )
        self.assertEqual(
            _enum_values("GameWorldMetadata", "time_of_day"),
            set(TIMES_OF_DAY),
        )
        self.assertEqual(
            _enum_values("GameWorldMetadata", "weather"),
            set(WEATHER_TYPES),
        )
        self.assertIn("default: day", _property_block("GameWorldMetadata", "time_of_day"))
        self.assertIn("default: clear", _property_block("GameWorldMetadata", "weather"))
        self.assertEqual(
            world_metadata_for_state({}),
            {
                "environment": "unknown",
                "time_of_day": DEFAULT_TIME_OF_DAY,
                "weather": DEFAULT_WEATHER,
            },
        )
        self.assertIn(
            "items:\n            type: string",
            _property_block("GameCombat", "participants"),
        )

    def test_journal_fields_enums_and_limits_match_python_validator(self):
        journal = _schema_block("CampaignJournal")
        self.assertIn(f"enum: [{JOURNAL_SCHEMA_VERSION}]", journal)
        limits = {
            "discovered_locations": MAX_LOCATIONS,
            "known_npcs": MAX_NPCS,
            "notable_events": MAX_EVENTS,
            "quests": MAX_QUESTS,
        }
        for field_name, maximum in limits.items():
            with self.subTest(journal_field=field_name):
                self.assertIn(
                    f"maxItems: {maximum}",
                    _property_block("CampaignJournal", field_name),
                )

        self.assertEqual(
            _enum_values("JournalLocation", "environment"),
            set(JOURNAL_ENVIRONMENTS),
        )
        self.assertEqual(
            _enum_values("JournalEvent", "event_type"),
            set(_EVENT_TYPES),
        )
        self.assertEqual(
            _enum_values("CampaignQuest", "status"),
            set(_QUEST_STATUSES),
        )
        self.assertEqual(
            _enum_values("CampaignQuestObjective", "status"),
            set(_OBJECTIVE_STATUSES),
        )
        self.assertIn(
            f"maxItems: {MAX_OBJECTIVES_PER_QUEST}",
            _property_block("CampaignQuest", "objectives"),
        )
        expected_fields = {
            "JournalLocation": {
                "location_id", "name", "environment", "first_discovered_at",
                "last_visited_at", "first_discovered_turn", "last_visited_turn",
                "visit_count",
            },
            "JournalNpc": {
                "npc_id", "name", "role", "first_met_at", "last_seen_at",
                "first_met_turn", "last_seen_turn", "last_known_location_id",
                "last_known_location",
            },
            "JournalEvent": {
                "event_id", "event_type", "created_at", "turn_index", "summary",
                "location_id", "location_name", "related_npc_id", "related_item",
            },
            "CampaignQuest": {
                "quest_id", "title", "description", "status", "giver_npc_id",
                "objectives", "created_at", "updated_at", "completed_at",
            },
            "CampaignQuestObjective": {"objective_id", "description", "status"},
        }
        for schema_name, fields in expected_fields.items():
            with self.subTest(journal_schema=schema_name):
                self.assertEqual(_property_names(schema_name), fields)

    def test_combat_result_is_the_serializer_allowlist_and_nullable(self):
        self.assertEqual(
            _property_names("CombatAttackResult"),
            set(_COMBAT_ATTACK_FIELDS),
        )
        self.assertEqual(
            _property_names("CombatTurnResult"),
            set(_COMBAT_TURN_FIELDS) | {"enemy_action", "enemy_actions"},
        )
        for schema_name in ("CombatAttackResult", "CombatTurnResult"):
            optional_nested = {"enemy_action", "enemy_actions"}
            for field_name in _property_names(schema_name) - optional_nested:
                with self.subTest(schema=schema_name, field=field_name):
                    self.assertIn(
                        '"null"',
                        _property_block(schema_name, field_name),
                    )
        self.assertIn(
            'type: "null"',
            _property_block("CombatTurnResult", "enemy_action"),
        )
        self.assertIn(
            '"null"',
            _property_block("CombatTurnResult", "enemy_actions"),
        )

        projected = serialize_combat_result(
            {
                "action": "attack",
                "status": "hit",
                "attack_roll": 17,
                "combat_started": True,
                "secret_prompt": "must not be returned",
                "enemy_action": {
                    "action": "attack",
                    "attack_roll": 8,
                    "private_state": "must not be returned",
                },
                "enemy_actions": [
                    {
                        "action": "attack",
                        "actor": "npc_guard",
                        "actor_name": "Guard",
                        "attack_roll": 9,
                        "private_state": "must not be returned",
                    }
                ],
            }
        )
        self.assertIsNotNone(projected)
        self.assertEqual(
            set(projected or {}),
            {
                "action", "status", "attack_roll", "combat_started",
                "enemy_action", "enemy_actions",
            },
        )
        self.assertEqual(
            set((projected or {})["enemy_action"]),
            {"action", "attack_roll"},
        )
        self.assertEqual(
            set((projected or {})["enemy_actions"][0]),
            {"action", "actor", "actor_name", "attack_roll"},
        )

    def test_error_schemas_and_runtime_error_envelopes_match(self):
        self.assertEqual(_property_names("ApiErrorResponse"), {"detail"})
        self.assertEqual(_property_names("ApiErrorDetail"), {"code", "message"})
        self.assertEqual(
            _property_names("RequestValidationError"),
            {"detail"},
        )
        self.assertEqual(
            _property_names("RequestValidationIssue"),
            {"loc", "msg", "type"},
        )
        self.assertEqual(
            _enum_values("ApiErrorDetail", "code"),
            {
                "campaign_not_found", "campaign_unavailable", "campaign_not_active",
                "campaign_storage_unavailable", "campaign_error",
                "invalid_character", "unknown_session", "ollama_unavailable",
                "model_unavailable", "engine_error", "journal_error",
            },
        )

        client = TestClient(app)
        validation = client.post(
            "/api/game/sessions/not-a-uuid/turn",
            json={"message": "   "},
        )
        self.assertEqual(validation.status_code, 422)
        validation_body = validation.json()
        self.assertEqual(set(validation_body), {"detail"})
        self.assertTrue(validation_body["detail"])
        self.assertEqual(
            set(validation_body["detail"][0]),
            {"loc", "msg", "type"},
        )
        self.assertNotIn("input", validation_body["detail"][0])

        missing = client.get("/api/game/sessions/not-a-session/state")
        self.assertEqual(missing.status_code, 404)
        missing_body = missing.json()
        self.assertEqual(set(missing_body), {"detail"})
        self.assertEqual(
            set(missing_body["detail"]),
            _property_names("ApiErrorDetail"),
        )
        self.assertEqual(missing_body["detail"]["code"], "unknown_session")


def _operation_block(path: str, method: str) -> str:
    lines = SPEC_TEXT.splitlines()
    path_index = next(
        index for index, line in enumerate(lines) if line == f"  {path}:"
    )
    operation_index = next(
        index
        for index in range(path_index + 1, len(lines))
        if lines[index] == f"    {method}:"
    )
    end = next(
        (
            index
            for index in range(operation_index + 1, len(lines))
            if re.fullmatch(r"    (get|post|put|patch|delete):", lines[index])
            or re.fullmatch(r"  /.+:", lines[index])
            or lines[index] == "components:"
        ),
        len(lines),
    )
    return "\n".join(lines[operation_index:end])


if __name__ == "__main__":
    unittest.main()
"""Contract checks between the published OpenAPI file and the FastAPI app."""

from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
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
    CharacterCreationCatalogResponse,
    CombatAttackResult,
    CombatTurnResult,
    DeathResolutionResult,
    DeathSaveResult,
    DeathStateProjection,
    HealthResponse,
    SessionResponse,
    SpeciesTraitActionRequest,
    SpeciesTraitActionResult,
    SpeciesTraitCommandResult,
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


class _ContractLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently hiding contract declarations."""

    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(keys) != len(set(keys)):
            raise AssertionError("OpenAPI contains duplicate mapping keys")
        return super().construct_mapping(node, deep=deep)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError(f"OpenAPI {label} must be a mapping")
    return value


def _load_spec(spec_text: str) -> dict[str, Any]:
    try:
        return _mapping(yaml.load(spec_text, Loader=_ContractLoader), "document")
    except yaml.YAMLError as exc:
        raise AssertionError(f"Malformed OpenAPI YAML: {exc}") from exc


SPEC = _load_spec(SPEC_TEXT)


def _route_inventory(spec: dict[str, Any]) -> set[tuple[str, str]]:
    base_path = spec["servers"][0]["url"].rstrip("/")
    return {
        (method.upper(), f"{base_path}{path}")
        for path, item in _mapping(spec["paths"], "paths").items()
        for method in _mapping(item, f"path {path}")
        if method in HTTP_METHODS
    }


def _schema(name: str) -> dict[str, Any]:
    schemas = _mapping(SPEC["components"]["schemas"], "schemas")
    if name not in schemas:
        raise AssertionError(f"OpenAPI schema {name!r} was not found")
    return _mapping(schemas[name], f"schema {name}")


def _properties(schema_name: str) -> dict[str, Any]:
    return _mapping(_schema(schema_name).get("properties"), f"{schema_name}.properties")


def _property_names(schema_name: str) -> set[str]:
    return set(_properties(schema_name))


def _property(schema_name: str, property_name: str) -> dict[str, Any]:
    properties = _properties(schema_name)
    if property_name not in properties:
        raise AssertionError(
            f"OpenAPI property {schema_name}.{property_name} was not found"
        )
    return _mapping(properties[property_name], f"property {schema_name}.{property_name}")


def _enum_values(schema_name: str, property_name: str) -> set[Any]:
    values = _property(schema_name, property_name).get("enum", [])
    if not isinstance(values, list):
        raise AssertionError(f"OpenAPI enum {schema_name}.{property_name} must be a list")
    return set(values)


def _is_nullable(schema: dict[str, Any]) -> bool:
    types = schema.get("type", [])
    return (
        types == "null"
        or isinstance(types, list) and "null" in types
        or any(_is_nullable(branch) for branch in schema.get("anyOf", []))
    )


def _operation(path: str, method: str) -> dict[str, Any]:
    return _mapping(SPEC["paths"][path][method], f"operation {method} {path}")


def _operation_ids() -> list[str]:
    ids = [
        operation["operationId"]
        for item in SPEC["paths"].values()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]
    if not all(isinstance(value, str) and value for value in ids):
        raise AssertionError("OpenAPI operation IDs must be nonempty strings")
    return ids


def _runtime_field_names(model: Any) -> set[str]:
    return {
        field.alias or name
        for name, field in model.model_fields.items()
    }


def _schema_types(schema: dict[str, Any]) -> set[str]:
    """Normalize OpenAPI type arrays and Pydantic's anyOf representation."""
    if "$ref" in schema:
        return {"object"}
    types = schema.get("type", [])
    result = {types} if isinstance(types, str) else set(types)
    for branch in schema.get("anyOf", []):
        result.update(_schema_types(branch))
    return result


def _schema_references(schema: dict[str, Any]) -> set[str]:
    """Keep nested reference targets distinct from their shared object type."""
    references = {schema["$ref"]} if "$ref" in schema else set()
    for branch in schema.get("anyOf", []):
        references.update(_schema_references(branch))
    return references


DEATH_REFERENCE_FIELDS = (
    (CombatAttackResult, "death_save"),
    (CombatAttackResult, "death_resolution"),
    (CombatTurnResult, "death_save"),
    (CombatTurnResult, "death_resolution"),
    (DeathSaveResult, "death_resolution"),
    (DeathStateProjection, "last_death_save"),
    (DeathStateProjection, "last_resolution"),
)

TURN_REFERENCE_FIELDS = (
    "combat_result",
    "combat_history_entry",
    "skill_check_result",
)


def _schema_enum(schema: dict[str, Any]) -> set[Any] | None:
    """Keep nullable enum membership distinct from nullable field types."""
    if "enum" in schema:
        values = schema["enum"]
        if not isinstance(values, list):
            raise AssertionError("Schema enum must be a list")
        return set(values)
    branches = schema.get("anyOf", [])
    enums = [_schema_enum(branch) for branch in branches]
    if not any(values is not None for values in enums):
        return None
    result = set()
    for branch, values in zip(branches, enums):
        if values is not None:
            result.update(values)
        elif branch.get("type") == "null":
            result.add(None)
    return result


class ContractParityTests(unittest.TestCase):
    def test_turn_result_references_match_runtime_models(self):
        runtime_properties = TurnResponse.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["properties"]
        for field_name in TURN_REFERENCE_FIELDS:
            with self.subTest(field=field_name):
                runtime = runtime_properties[field_name]
                published = _property("GameTurnResult", field_name)
                expected = _schema_references(runtime)
                self.assertTrue(expected, "Runtime turn field must reference a model")
                self.assertEqual(
                    _schema_references(published), expected,
                    f"GameTurnResult.{field_name} reference target",
                )
                self.assertEqual(_schema_types(published), _schema_types(runtime))
                self.assertEqual(_is_nullable(published), _is_nullable(runtime))

    def test_enemy_result_references_match_runtime_models(self):
        runtime_properties = CombatTurnResult.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["properties"]
        for field_name in ("enemy_action", "enemy_actions"):
            with self.subTest(field=field_name):
                runtime = runtime_properties[field_name]
                published = _property("CombatTurnResult", field_name)
                self.assertEqual(_schema_types(published), _schema_types(runtime))
                self.assertEqual(_is_nullable(published), _is_nullable(runtime))
                if field_name == "enemy_actions":
                    runtime = next(
                        branch for branch in runtime["anyOf"] if "items" in branch
                    )["items"]
                    published = _mapping(
                        published.get("items"), "CombatTurnResult.enemy_actions.items"
                    )
                expected = _schema_references(runtime)
                self.assertEqual(
                    expected, {f"#/components/schemas/{CombatAttackResult.__name__}"},
                    f"Runtime {field_name} must reference CombatAttackResult",
                )
                self.assertEqual(
                    _schema_references(published), expected,
                    f"CombatTurnResult.{field_name} reference target",
                )

    def test_nested_death_references_match_runtime_models(self):
        for model, field_name in DEATH_REFERENCE_FIELDS:
            with self.subTest(schema=model.__name__, field=field_name):
                runtime = model.model_json_schema(
                    ref_template="#/components/schemas/{model}"
                )["properties"][field_name]
                published = _property(model.__name__, field_name)
                expected = _schema_references(runtime)
                self.assertTrue(expected, "Runtime death field must reference a model")
                self.assertEqual(
                    _schema_references(published), expected,
                    f"{model.__name__}.{field_name} reference target",
                )
                self.assertEqual(_is_nullable(published), _is_nullable(runtime))

        # Session state is a dict in Python; the serializer validates this
        # projection explicitly rather than exposing a GameState model.
        published = _property("GameState", "death_state")
        self.assertEqual(
            _schema_references(published),
            {f"#/components/schemas/{DeathStateProjection.__name__}"},
            "GameState.death_state reference target",
        )
        self.assertFalse(_is_nullable(published))

    def test_nested_death_schemas_match_runtime_models(self):
        for model in (DeathSaveResult, DeathResolutionResult, DeathStateProjection):
            schema_name = model.__name__
            runtime = model.model_json_schema()
            with self.subTest(schema=schema_name):
                self.assertEqual(_property_names(schema_name), _runtime_field_names(model))
                self.assertEqual(
                    set(_schema(schema_name).get("required", [])),
                    set(runtime.get("required", [])),
                )
                self.assertEqual(
                    _schema(schema_name).get("additionalProperties"),
                    runtime.get("additionalProperties"),
                )
            for field_name, runtime_property in runtime["properties"].items():
                with self.subTest(schema=schema_name, field=field_name):
                    published = _property(schema_name, field_name)
                    self.assertEqual(
                        _enum_values(schema_name, field_name),
                        set(runtime_property.get("enum", [])),
                    )
                    self.assertEqual(_is_nullable(published), _is_nullable(runtime_property))
                    for constraint in (
                        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                    ):
                        self.assertEqual(
                            published.get(constraint),
                            runtime_property.get(constraint),
                            f"{schema_name}.{field_name}.{constraint}",
                        )
                    if "enum" in runtime_property or "minimum" in runtime_property:
                        self.assertEqual(published.get("type"), runtime_property.get("type"))

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
        documented_routes = _route_inventory(SPEC)
        self.assertEqual(runtime_routes, documented_routes)
        self.assertEqual(len(documented_routes), 31)

        alias_pairs = (
            ("GET", "/api/game/health", "/api/health"),
            ("GET", "/api/game/character-options", "/api/character-options"),
            ("GET", "/api/game/character-creation-catalog", "/api/character-creation-catalog"),
            ("POST", "/api/game/sessions", "/api/sessions"),
            ("GET", "/api/game/sessions/{session_id}/state", "/api/sessions/{session_id}/state"),
            ("POST", "/api/game/sessions/{session_id}/turn", "/api/sessions/{session_id}/turn"),
            ("POST", "/api/game/sessions/{session_id}/species-actions", "/api/sessions/{session_id}/species-actions"),
            ("GET", "/api/game/campaigns", "/api/campaigns"),
            ("POST", "/api/game/campaigns", "/api/campaigns"),
            ("GET", "/api/game/campaigns/{campaign_id}", "/api/campaigns/{campaign_id}"),
            ("DELETE", "/api/game/campaigns/{campaign_id}", "/api/campaigns/{campaign_id}"),
            ("POST", "/api/game/campaigns/{campaign_id}/resume", "/api/campaigns/{campaign_id}/resume"),
            ("POST", "/api/game/campaigns/{campaign_id}/save", "/api/campaigns/{campaign_id}/save"),
        )
        for method, canonical, alias in alias_pairs:
            with self.subTest(method=method, canonical=canonical):
                self.assertIn((method, canonical), documented_routes)
                self.assertIn((method, alias), documented_routes)

    def test_operation_ids_are_unique_and_error_statuses_are_documented(self):
        operation_ids = _operation_ids()
        self.assertEqual(len(operation_ids), len(_route_inventory(SPEC)))
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

        status_expectations = {
            ("/game/sessions/{session_id}/state", "get"): {"200", "404", "422"},
            ("/game/sessions/{session_id}/turn", "post"): {
                "200", "404", "409", "422", "500", "503"
            },
            ("/game/campaigns", "post"): {"200", "422", "500", "503"},
            ("/game/campaigns/{campaign_id}", "get"): {
                "200", "404", "409", "422", "500", "503"
            },
            ("/game/campaigns/{campaign_id}", "delete"): {"200", "503"},
            ("/campaigns/{campaign_id}", "delete"): {"200", "503"},
        }
        for (path, method), expected in status_expectations.items():
            with self.subTest(path=path, method=method):
                operation = _operation(path, method)
                actual = {str(status) for status in operation["responses"]}
                self.assertEqual(actual, expected)

    def test_campaign_deletion_aliases_share_the_response_contract(self):
        self.assertEqual(
            _property_names("CampaignDeleteResult"),
            {"campaign_id", "deleted"},
        )
        self.assertEqual(_schema("CampaignDeleteResult")["required"], ["campaign_id", "deleted"])
        for path in ("/game/campaigns/{campaign_id}", "/campaigns/{campaign_id}"):
            with self.subTest(path=path):
                responses = _operation(path, "delete")["responses"]
                self.assertEqual(
                    responses["200"]["content"]["application/json"]["schema"]["$ref"],
                    "#/components/schemas/CampaignDeleteResult",
                )
                self.assertEqual(responses["503"]["$ref"], "#/components/responses/ApiError")

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
        self.assertIs(_schema("GameTurnInput")["additionalProperties"], False)
        message_schema = _property("GameTurnInput", "message")
        self.assertEqual(message_schema["minLength"], 1)
        self.assertEqual(message_schema["maxLength"], 4000)
        with self.assertRaises(ValidationError):
            TurnRequest(message="   ")
        with self.assertRaises(ValidationError):
            TurnRequest.model_validate({"message": "look", "current_hp": 99})

    def test_campaign_and_session_schema_fields_match_fastapi_models(self):
        response_models = {
            "GameSession": SessionResponse,
            "CharacterCreationOptions": CharacterCreationOptions,
            "CharacterCreationCatalogResponse": CharacterCreationCatalogResponse,
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
        self.assertIs(_schema("CampaignCreateInput")["additionalProperties"], False)
        self.assertTrue(_is_nullable(_property("CampaignCreateInput", "name")))
        character_schema = _schema("CharacterCreateInput")
        self.assertEqual(
            _property_names("CharacterCreateInput"),
            _runtime_field_names(CharacterCreateInput),
        )
        self.assertIs(character_schema["additionalProperties"], False)
        self.assertEqual(
            _enum_values("CharacterCreateInput", "mode"),
            {"custom", "random"},
        )
        for field_name in (
            "name",
            "race",
            "class",
            "species",
            "background",
            "alignment",
            "ability_score_method",
            "ability_scores",
            "background_ability_bonuses",
            "proficient_skills",
            "proficient_tools",
            "origin_feat",
            "species_bonus_feat",
            "species_bonus_skills",
            "fighting_style",
            "equipment_package",
            "equipment_choices",
            "cantrips",
            "spells",
            "languages",
            "background_equipment_option",
            "appearance",
            "personality",
            "backstory",
        ):
            with self.subTest(character_field=field_name):
                self.assertTrue(_is_nullable(_property("CharacterCreateInput", field_name)))
        CharacterCreateInput.model_validate(
            {"mode": "custom", "name": "Ari", "race": "Elf", "class": "Wizard"}
        )
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate({"mode": "custom"})
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate({"mode": "random", "name": "Ari"})

    def test_species_action_schemas_match_runtime_models(self):
        models = {
            "SpeciesTraitActionInput": SpeciesTraitActionRequest,
            "SpeciesTraitActionResult": SpeciesTraitActionResult,
            "SpeciesTraitCommandResult": SpeciesTraitCommandResult,
        }
        for schema_name, model in models.items():
            published = _schema(schema_name)
            runtime = model.model_json_schema()
            with self.subTest(schema=schema_name):
                self.assertEqual(_property_names(schema_name), _runtime_field_names(model))
                self.assertEqual(
                    set(published.get("required", [])),
                    set(runtime.get("required", [])),
                )
                self.assertIs(published.get("additionalProperties"), False)
                self.assertEqual(
                    published.get("additionalProperties"),
                    runtime.get("additionalProperties"),
                )
            for field_name, runtime_field in runtime["properties"].items():
                with self.subTest(schema=schema_name, field=field_name):
                    published_field = _property(schema_name, field_name)
                    self.assertEqual(
                        _schema_types(published_field), _schema_types(runtime_field)
                    )
                    self.assertEqual(
                        _is_nullable(published_field), _is_nullable(runtime_field)
                    )
                    self.assertEqual(
                        _schema_enum(published_field), _schema_enum(runtime_field)
                    )
                    for constraint in ("minLength", "maxLength", "additionalProperties"):
                        if (
                            schema_name == "SpeciesTraitCommandResult"
                            and field_name == "state"
                            and constraint == "additionalProperties"
                        ):
                            # The public GameState reference intentionally narrows this dict.
                            continue
                        self.assertEqual(
                            published_field.get(constraint),
                            runtime_field.get(constraint),
                            f"{schema_name}.{field_name}.{constraint}",
                        )
        # Python uses a broad state dict; the public contract narrows it to GameState.
        self.assertEqual(
            _property("SpeciesTraitCommandResult", "state").get("$ref"),
            "#/components/schemas/GameState",
        )
        self.assertEqual(
            _property("SpeciesTraitCommandResult", "result").get("$ref"),
            "#/components/schemas/SpeciesTraitActionResult",
        )

    def test_session_creation_and_campaign_resume_route_bindings_match_fastapi(self):
        runtime_spec = app.openapi()
        base_path = SPEC["servers"][0]["url"].rstrip("/")
        # Client-facing session names intentionally differ from Python's models.
        runtime_to_published_refs = {
            "#/components/schemas/SessionResponse": "#/components/schemas/GameSession",
            "#/components/schemas/CampaignSessionResponse": "#/components/schemas/CampaignSession",
            "#/components/schemas/CampaignCreateRequest": "#/components/schemas/CampaignCreateInput",
        }
        for path in (
            "/game/sessions",
            "/sessions",
            "/game/campaigns/{campaign_id}/resume",
            "/campaigns/{campaign_id}/resume",
        ):
            published = _operation(path, "post")
            runtime = runtime_spec["paths"][f"{base_path}{path}"]["post"]
            with self.subTest(path=path, binding="requestBody"):
                # These operations currently have no body. An added client body
                # is contract drift even when it points at a valid schema.
                self.assertEqual("requestBody" in published, "requestBody" in runtime)
                if "requestBody" in runtime:
                    runtime_body = runtime["requestBody"]
                    published_body = published["requestBody"]
                    runtime_schema = runtime_body["content"]["application/json"]["schema"]
                    self.assertEqual(
                        published_body["content"]["application/json"]["schema"],
                        {"$ref": runtime_to_published_refs.get(
                            runtime_schema["$ref"], runtime_schema["$ref"],
                        )},
                    )
                    self.assertEqual(
                        published_body.get("required", False),
                        runtime_body.get("required", False),
                    )
            published_successes = {
                str(status): response
                for status, response in published["responses"].items()
                if str(status).startswith("2")
            }
            runtime_successes = {
                str(status): response
                for status, response in runtime["responses"].items()
                if str(status).startswith("2")
            }
            with self.subTest(path=path, binding="success statuses"):
                self.assertEqual(set(published_successes), set(runtime_successes))
            for status, response in runtime_successes.items():
                with self.subTest(path=path, binding="response", status=status):
                    runtime_schema = response["content"]["application/json"]["schema"]
                    self.assertEqual(
                        published_successes[status]["content"]["application/json"]["schema"],
                        {"$ref": runtime_to_published_refs.get(
                            runtime_schema["$ref"], runtime_schema["$ref"],
                        )},
                    )

    def test_turn_route_bindings_match_fastapi(self):
        runtime_spec = app.openapi()
        base_path = SPEC["servers"][0]["url"].rstrip("/")
        # Public turn models intentionally use different names from Python.
        runtime_to_published_refs = {
            "#/components/schemas/TurnRequest": "#/components/schemas/GameTurnInput",
            "#/components/schemas/TurnResponse": "#/components/schemas/GameTurnResult",
        }
        for path in (
            "/game/sessions/{session_id}/turn",
            "/sessions/{session_id}/turn",
        ):
            published = _operation(path, "post")
            runtime = runtime_spec["paths"][f"{base_path}{path}"]["post"]
            with self.subTest(path=path, binding="requestBody"):
                runtime_schema = runtime["requestBody"]["content"]["application/json"]["schema"]
                self.assertEqual(
                    published["requestBody"]["content"]["application/json"]["schema"],
                    {"$ref": runtime_to_published_refs.get(
                        runtime_schema["$ref"], runtime_schema["$ref"],
                    )},
                )
                self.assertEqual(
                    published["requestBody"].get("required", False),
                    runtime["requestBody"].get("required", False),
                )
            published_successes = {
                str(status): response
                for status, response in published["responses"].items()
                if str(status).startswith("2")
            }
            runtime_successes = {
                str(status): response
                for status, response in runtime["responses"].items()
                if str(status).startswith("2")
            }
            with self.subTest(path=path, binding="success statuses"):
                self.assertEqual(set(published_successes), set(runtime_successes))
            for status, response in runtime_successes.items():
                with self.subTest(path=path, binding="response", status=status):
                    runtime_schema = response["content"]["application/json"]["schema"]
                    self.assertEqual(
                        published_successes[status]["content"]["application/json"]["schema"],
                        {"$ref": runtime_to_published_refs.get(
                            runtime_schema["$ref"], runtime_schema["$ref"],
                        )},
                    )

    def test_species_action_route_bindings_match_fastapi(self):
        runtime_spec = app.openapi()
        base_path = SPEC["servers"][0]["url"].rstrip("/")
        # The published input has a client-facing name distinct from Python's model.
        runtime_to_published_refs = {
            "#/components/schemas/SpeciesTraitActionRequest":
                "#/components/schemas/SpeciesTraitActionInput",
        }
        for path in (
            "/game/sessions/{session_id}/species-actions",
            "/sessions/{session_id}/species-actions",
        ):
            published = _operation(path, "post")
            runtime = runtime_spec["paths"][f"{base_path}{path}"]["post"]
            with self.subTest(path=path, binding="requestBody"):
                runtime_schema = runtime["requestBody"]["content"]["application/json"]["schema"]
                self.assertEqual(
                    published["requestBody"]["content"]["application/json"]["schema"],
                    {"$ref": runtime_to_published_refs.get(
                        runtime_schema["$ref"], runtime_schema["$ref"],
                    )},
                )
                self.assertEqual(
                    published["requestBody"].get("required", False),
                    runtime["requestBody"].get("required", False),
                )
            published_successes = {
                str(status): response
                for status, response in published["responses"].items()
                if str(status).startswith("2")
            }
            runtime_successes = {
                str(status): response
                for status, response in runtime["responses"].items()
                if str(status).startswith("2")
            }
            with self.subTest(path=path, binding="success statuses"):
                self.assertEqual(set(published_successes), set(runtime_successes))
            for status in runtime_successes:
                with self.subTest(path=path, binding="response", status=status):
                    self.assertEqual(
                        published_successes[status]["content"]["application/json"]["schema"],
                        runtime_successes[status]["content"]["application/json"]["schema"],
                    )

    def test_species_action_runtime_acceptance_and_rejection_boundaries(self):
        request_schema = SpeciesTraitActionRequest.model_json_schema()["properties"]
        for action in _schema_enum(request_schema["action"]):
            payload = {"action": action}
            if action == "celestial_revelation":
                payload["form"] = "heavenly_wings"
            elif action == "choose_giant_ancestry":
                payload["ancestry"] = "cloud"
            with self.subTest(action=action):
                self.assertEqual(SpeciesTraitActionRequest.model_validate(payload).action, action)
        for field, action in (
            ("form", "celestial_revelation"),
            ("ancestry", "choose_giant_ancestry"),
        ):
            for value in _schema_enum(request_schema[field]) - {None}:
                with self.subTest(field=field, value=value):
                    SpeciesTraitActionRequest.model_validate({"action": action, field: value})
        SpeciesTraitActionRequest(
            action="healing_hands", form=None, ancestry=None, armed=None, action_id=None
        )
        SpeciesTraitActionRequest(action="arm_giant_ancestry", armed=False)
        SpeciesTraitActionRequest(action="arm_giant_ancestry", armed=True)
        for payload in (
            {},
            {"action": None},
            {"action": "unknown"},
            {"action": "celestial_revelation", "form": "unknown"},
            {"action": "choose_giant_ancestry", "ancestry": "unknown"},
            {"action": "healing_hands", "unexpected": True},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                SpeciesTraitActionRequest.model_validate(payload)

        result = {"action": "healing_hands", "message": "ok", "effects": {"healed": 1}}
        command = {"session_id": "session", "state": {}, "result": result}
        SpeciesTraitCommandResult.model_validate(command)
        SpeciesTraitCommandResult.model_validate({**command, "action_id": None})
        for length in (1, 500):
            SpeciesTraitActionResult.model_validate({**result, "message": "x" * length})
        for length in (0, 501):
            with self.subTest(length=length), self.assertRaises(ValidationError):
                SpeciesTraitActionResult.model_validate({**result, "message": "x" * length})
        for model, payload in (
            (SpeciesTraitActionResult, {**result, "unexpected": True}),
            (SpeciesTraitCommandResult, {**command, "unexpected": True}),
            (SpeciesTraitCommandResult, {**command, "result": {**result, "unexpected": True}}),
        ):
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model.model_validate(payload)

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
                        "scene_state": {
                            "schema_version": 1,
                            "next_referent_number": 1,
                            "next_feature_number": 1,
                            "active_referent_id": None,
                            "player_position": {
                                "location_id": "tavern",
                                "kind": "standing",
                                "target_id": None,
                            },
                            "proposal_references": [],
                            "scenes": {
                                "tavern": {
                                    "id": "scene:tavern",
                                    "location_id": "tavern",
                                    "parent_location_id": None,
                                    "kind": "tavern",
                                    "materialized": True,
                                    "visit_revision": 1,
                                    "activity_revision": 0,
                                    "first_seen_turn": 1,
                                    "last_visit_turn": 1,
                                    "last_activity_turn": 1,
                                    "last_beat": None,
                                    "referents": [],
                                }
                            },
                        },
                        "inventory": [],
                        "npcs": [],
                        "shops": [],
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
        self.assertEqual(public_state["scene"]["id"], "scene:tavern")
        self.assertEqual(public_state["scene"]["location_id"], "tavern")
        self.assertEqual(
            public_state["scene"]["player_position"]["kind"],
            "standing",
        )
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
        self.assertEqual(_property("GameWorldMetadata", "time_of_day")["default"], "day")
        self.assertEqual(_property("GameWorldMetadata", "weather")["default"], "clear")
        self.assertEqual(
            world_metadata_for_state({}),
            {
                "environment": "unknown",
                "time_of_day": DEFAULT_TIME_OF_DAY,
                "weather": DEFAULT_WEATHER,
            },
        )
        self.assertEqual(_property("GameCombat", "participants")["items"]["type"], "string")

    def test_journal_fields_enums_and_limits_match_python_validator(self):
        self.assertEqual(_enum_values("CampaignJournal", "schema_version"), {JOURNAL_SCHEMA_VERSION})
        limits = {
            "discovered_locations": MAX_LOCATIONS,
            "known_npcs": MAX_NPCS,
            "notable_events": MAX_EVENTS,
            "quests": MAX_QUESTS,
        }
        for field_name, maximum in limits.items():
            with self.subTest(journal_field=field_name):
                self.assertEqual(_property("CampaignJournal", field_name)["maxItems"], maximum)

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
        self.assertEqual(_property("CampaignQuest", "objectives")["maxItems"], MAX_OBJECTIVES_PER_QUEST)
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
                "event_result",
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
                    self.assertTrue(_is_nullable(_property(schema_name, field_name)))
        self.assertTrue(_is_nullable(_property("CombatTurnResult", "enemy_action")))
        self.assertTrue(_is_nullable(_property("CombatTurnResult", "enemy_actions")))

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


class ContractYamlReaderTests(unittest.TestCase):
    BLOCK_FIXTURE = """
servers:
  - url: /api
paths:
  /example:
    get:
      operationId: readExample
      responses:
        "200":
          description: Success
components:
  schemas:
    Example:
      type: object
      required:
        - combat_id
      additionalProperties: false
      properties:
        combat_id:
          type:
            - string
            - "null"
        result:
          anyOf:
            - type: object
            - type: "null"
        message:
          type: string
          minLength: 1
          maxLength: 4000
          enum:
            - "hit, critical"
            - "1"
            - 1
"""
    COMPACT_FIXTURE = """
servers: [{url: /api}]
paths: {/example: {get: {operationId: readExample, responses: {"200": {description: Success}}}}}
components: {schemas: {Example: {type: object, required: [combat_id], additionalProperties: false, properties: {combat_id: {type: [string, "null"]}, result: {anyOf: [{type: object}, {type: "null"}]}, message: {type: string, minLength: 1, maxLength: 4000, enum: ["hit, critical", "1", 1]}}}}}
"""

    def test_species_action_wrong_route_bindings_fail_in_both_formats(self):
        for path in (
            "/game/sessions/{session_id}/species-actions",
            "/sessions/{session_id}/species-actions",
        ):
            for binding in ("requestBody", "response"):
                for flow_style in (False, True):
                    with self.subTest(path=path, binding=binding, compact=flow_style):
                        spec = deepcopy(SPEC)
                        operation = spec["paths"][path]["post"]
                        if binding == "requestBody":
                            schema = operation["requestBody"]["content"]["application/json"]["schema"]
                            wrong_ref = "#/components/schemas/GameTurnInput"
                        else:
                            schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
                            wrong_ref = "#/components/schemas/SpeciesTraitActionResult"
                        schema["$ref"] = wrong_ref
                        text = yaml.safe_dump(spec, default_flow_style=flow_style)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=_load_spec(text)):
                            # The existing inventory and model checks cannot see this drift.
                            for test_name in (
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                                "test_species_action_schemas_match_runtime_models",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(unchanged.wasSuccessful(), unchanged.errors)
                            ContractParityTests(
                                "test_species_action_route_bindings_match_fastapi"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertTrue(
                            result.failures,
                            f"Undetected species-action binding drift: {path} {binding}",
                        )

    def _parity_result(self, spec):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContractParityTests)
        result = unittest.TestResult()
        with patch.dict(globals(), SPEC=spec):
            suite.run(result)
        return result

    def test_block_and_compact_fixtures_have_identical_reader_results(self):
        block = _load_spec(self.BLOCK_FIXTURE)
        compact = _load_spec(self.COMPACT_FIXTURE)
        self.assertEqual(block, compact)
        for spec in (block, compact):
            with self.subTest(spec=spec), patch.dict(globals(), SPEC=spec):
                self.assertEqual(_route_inventory(spec), {("GET", "/api/example")})
                self.assertEqual(_operation_ids(), ["readExample"])
                self.assertEqual(set(_operation("/example", "get")["responses"]), {"200"})
                self.assertEqual(_schema("Example")["required"], ["combat_id"])
                self.assertIs(_schema("Example")["additionalProperties"], False)
                self.assertEqual(_property_names("Example"), {"combat_id", "result", "message"})
                self.assertTrue(_is_nullable(_property("Example", "combat_id")))
                self.assertTrue(_is_nullable(_property("Example", "result")))
                self.assertEqual(_property("Example", "message")["minLength"], 1)
                self.assertEqual(_property("Example", "message")["maxLength"], 4000)
                self.assertEqual(_enum_values("Example", "message"), {"hit, critical", "1", 1})

    def test_entire_contract_passes_with_block_and_compact_yaml(self):
        results = []
        for flow_style in (False, True):
            with self.subTest(compact=flow_style):
                text = yaml.safe_dump(SPEC, default_flow_style=flow_style, sort_keys=False)
                spec = _load_spec(text)
                self.assertEqual(spec, SPEC)
                result = self._parity_result(spec)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
                results.append(result.testsRun)
        self.assertEqual(results[0], results[1])
        self.assertGreater(results[0], 0)

    def test_malformed_yaml_and_duplicate_declarations_fail_explicitly(self):
        for text in (
            "components: {schemas: [",
            "components:\n  schemas: {}\n  schemas: {}",
            "{paths: {}, paths: {}}",
            "[]",
            "",
            "!!python/object:builtins.object {}",
        ):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                _load_spec(text)

    def test_missing_and_malformed_schema_fields_fail_explicitly(self):
        for properties in (None, [], "combat_id"):
            spec = _load_spec(self.BLOCK_FIXTURE)
            spec["components"]["schemas"]["Example"]["properties"] = properties
            with self.subTest(properties=properties), patch.dict(globals(), SPEC=spec):
                with self.assertRaisesRegex(AssertionError, "properties must be a mapping"):
                    _property_names("Example")
        spec = _load_spec(self.BLOCK_FIXTURE)
        with patch.dict(globals(), SPEC=spec):
            with self.assertRaisesRegex(AssertionError, "schema 'Missing' was not found"):
                _property_names("Missing")
            with self.assertRaisesRegex(AssertionError, "Example.missing was not found"):
                _property("Example", "missing")
            spec["components"]["schemas"]["Example"]["properties"]["combat_id"] = None
            with self.assertRaisesRegex(AssertionError, "must be a mapping"):
                _property("Example", "combat_id")
            spec["components"]["schemas"]["Example"]["properties"]["message"]["enum"] = "hit"
            with self.assertRaisesRegex(AssertionError, "enum Example.message must be a list"):
                _enum_values("Example", "message")

    def test_real_contract_regressions_still_fail_in_both_formats(self):
        def missing_field(spec):
            del spec["components"]["schemas"]["CombatTurnResult"]["properties"]["combat_id"]

        def nonnullable_field(spec):
            spec["components"]["schemas"]["CombatTurnResult"]["properties"]["combat_id"] = {
                "type": "string", "description": 'The word "null" is not nullability',
            }

        def wrong_enum(spec):
            spec["components"]["schemas"]["HealthResponse"]["properties"]["status"]["enum"] = ["wrong"]

        def wrong_constraint(spec):
            spec["components"]["schemas"]["GameTurnInput"]["properties"]["message"]["maxLength"] = 400

        def missing_alias(spec):
            del spec["paths"]["/health"]

        def duplicate_operation_id(spec):
            spec["paths"]["/health"]["get"]["operationId"] = (
                spec["paths"]["/game/health"]["get"]["operationId"]
            )

        def missing_operation_id(spec):
            del spec["paths"]["/health"]["get"]["operationId"]

        def missing_status(spec):
            del spec["paths"]["/game/sessions/{session_id}/turn"]["post"]["responses"]["409"]

        def wrong_delete_reference(spec):
            spec["paths"]["/campaigns/{campaign_id}"]["delete"]["responses"]["200"][
                "content"
            ]["application/json"]["schema"]["$ref"] = "#/components/schemas/GameSession"

        for mutate in (
            missing_field, nonnullable_field, wrong_enum, wrong_constraint,
            missing_alias, duplicate_operation_id, missing_operation_id,
            missing_status, wrong_delete_reference,
        ):
            for flow_style in (False, True):
                with self.subTest(mutation=mutate.__name__, compact=flow_style):
                    spec = deepcopy(SPEC)
                    mutate(spec)
                    text = yaml.safe_dump(spec, default_flow_style=flow_style)
                    result = self._parity_result(_load_spec(text))
                    self.assertFalse(result.wasSuccessful())
                    self.assertTrue(result.failures or result.errors)

    def test_species_action_contract_drift_is_detected_in_both_formats(self):
        mutations = []
        for schema_name in (
            "SpeciesTraitActionInput", "SpeciesTraitActionResult", "SpeciesTraitCommandResult"
        ):
            schema_path = ("components", "schemas", schema_name)
            published = _schema(schema_name)
            mutations.extend([
                (schema_path + ("additionalProperties",), True),
                (schema_path + ("additionalProperties",), None),
                (schema_path + ("required",), []),
                (schema_path + ("properties", "unexpected"), {"type": "string"}),
            ])
            for field_name, field_schema in published["properties"].items():
                field_path = schema_path + ("properties", field_name)
                # Missing fields and incompatible types, including nested result refs.
                mutations.append((field_path, None))
                mutations.append((field_path, {"type": "integer"}))
                if _is_nullable(field_schema):
                    nonnullable = deepcopy(field_schema)
                    nonnullable["type"] = [
                        value for value in field_schema["type"] if value != "null"
                    ]
                    mutations.append((field_path, nonnullable))
                    mutations.append((
                        schema_path + ("required",),
                        [*published["required"], field_name],
                    ))
                else:
                    mutations.append((field_path, {
                        "anyOf": [deepcopy(field_schema), {"type": "null"}],
                    }))
            # Each required field must remain required, not just the whole set.
            for required_field in published["required"]:
                mutations.append((
                    schema_path + ("required",),
                    [value for value in published["required"] if value != required_field],
                ))
        input_path = ("components", "schemas", "SpeciesTraitActionInput", "properties")
        for field_name in ("action", "form", "ancestry"):
            values = _enum_values("SpeciesTraitActionInput", field_name)
            mutations.append((input_path + (field_name, "enum"), [*values, "unsupported"]))
            mutations.append((input_path + (field_name, "enum"), None))
            for value in values:
                mutations.append((
                    input_path + (field_name, "enum"),
                    [item for item in values if item != value],
                ))
        result_path = ("components", "schemas", "SpeciesTraitActionResult", "properties")
        for constraint, wrong_value in (("minLength", 0), ("maxLength", 501)):
            mutations.append((result_path + ("message", constraint), wrong_value))
            mutations.append((result_path + ("message", constraint), None))
        mutations.append((result_path + ("effects", "additionalProperties"), False))
        mutations.append((result_path + ("effects", "additionalProperties"), None))
        command_path = ("components", "schemas", "SpeciesTraitCommandResult", "properties")
        for field_name in ("state", "result"):
            mutations.append((
                command_path + (field_name, "$ref"),
                "#/components/schemas/GameSession",
            ))

        for path, value in mutations:
            for flow_style in (False, True):
                with self.subTest(path=path, value=value, compact=flow_style):
                    spec = deepcopy(SPEC)
                    target = spec
                    for key in path[:-1]:
                        target = target[key]
                    if value is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = value
                    text = yaml.safe_dump(spec, default_flow_style=flow_style)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=_load_spec(text)):
                        ContractParityTests(
                            "test_species_action_schemas_match_runtime_models"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertTrue(result.failures, f"Undetected species-action drift: {path}")

    def test_nested_death_contract_mutations_fail_in_both_formats(self):
        # Each case changes only a deep-copied published schema. The same
        # parity test used for the real contract must reject every mutation.
        mutations = []
        for schema_name in (
            "DeathSaveResult", "DeathResolutionResult", "DeathStateProjection",
        ):
            mutations.extend([
                (schema_name, ("properties", _schema(schema_name)["required"][0]),
                 None, "delete"),
                (schema_name, ("properties", "unexpected"), {"type": "boolean"}, "set"),
                (schema_name, ("required",), [], "set"),
                (schema_name, ("additionalProperties",), True, "set"),
            ])
        enum_fields = {
            "DeathSaveResult": ("outcome",),
            "DeathResolutionResult": ("mode", "outcome", "cause"),
            "DeathStateProjection": ("mode", "status"),
        }
        for schema_name, fields in enum_fields.items():
            for field_name in fields:
                enum = _property(schema_name, field_name)["enum"]
                for replacement in (enum[:-1], enum + ["unexpected"], None):
                    mutations.append((
                        schema_name, ("properties", field_name, "enum"),
                        replacement, "delete" if replacement is None else "set",
                    ))
        bounded_fields = {
            "DeathSaveResult": ("roll", "successes", "failures"),
            "DeathStateProjection": ("successes", "failures"),
        }
        for schema_name, fields in bounded_fields.items():
            for field_name in fields:
                for bound in ("minimum", "maximum"):
                    value = _property(schema_name, field_name)[bound]
                    for replacement in (value - 1, value + 1, None):
                        mutations.append((
                            schema_name, ("properties", field_name, bound),
                            replacement, "delete" if replacement is None else "set",
                        ))
                mutations.append((
                    schema_name, ("properties", field_name, "type"), "number", "set",
                ))
        for schema_name, field_name in (
            ("DeathSaveResult", "action_id"),
            ("DeathSaveResult", "resolution_id"),
            ("DeathSaveResult", "death_resolution"),
            ("DeathStateProjection", "last_death_save"),
            ("DeathStateProjection", "last_resolution"),
        ):
            mutations.extend([
                (schema_name, ("properties", field_name), None, "delete"),
                (schema_name, ("required",),
                 _schema(schema_name)["required"] + [field_name], "set"),
                (schema_name, ("properties", field_name),
                 {"type": "string"}, "set"),
            ])

        for schema_name, path, replacement, operation in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    schema=schema_name, path=path, replacement=replacement,
                    operation=operation, compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if operation == "delete":
                        del target[path[-1]]
                    else:
                        target[path[-1]] = replacement
                    text = yaml.safe_dump(spec, default_flow_style=flow_style)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=_load_spec(text)):
                        ContractParityTests(
                            "test_nested_death_schemas_match_runtime_models"
                        ).run(result)
                    self.assertTrue(result.failures, result.errors)
                    self.assertFalse(result.errors, result.errors)

    def test_turn_result_reference_mutations_fail_in_both_formats(self):
        for field_name in TURN_REFERENCE_FIELDS:
            original = _property("GameTurnResult", field_name)
            wrong_nested_ref = (
                "#/components/schemas/SkillCheckResult"
                if field_name == "combat_result"
                else "#/components/schemas/CombatTurnResult"
            )
            for replacement in (
                "#/components/schemas/GameSession",
                wrong_nested_ref,
            ):
                for flow_style in (False, True):
                    with self.subTest(
                        field=field_name, replacement=replacement, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        field = spec["components"]["schemas"]["GameTurnResult"][
                            "properties"
                        ][field_name]
                        target = next(
                            branch for branch in field["anyOf"] if "$ref" in branch
                        )
                        target["$ref"] = replacement
                        self.assertEqual(_schema_types(field), _schema_types(original))
                        self.assertEqual(_is_nullable(field), _is_nullable(original))
                        text = yaml.safe_dump(spec, default_flow_style=flow_style)
                        with patch.dict(globals(), SPEC=_load_spec(text)):
                            unchanged = unittest.TestResult()
                            ContractParityTests(
                                "test_campaign_and_session_schema_fields_match_fastapi_models"
                            ).run(unchanged)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_turn_result_references_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertTrue(
                            result.failures,
                            f"Undetected turn result reference drift: {field_name}",
                        )
                        self.assertTrue(
                            all(
                                f"GameTurnResult.{field_name} reference target" in failure
                                for _, failure in result.failures
                            ),
                            result.failures,
                        )

    def test_enemy_result_reference_mutations_fail_in_both_formats(self):
        for field_name in ("enemy_action", "enemy_actions"):
            original = _property("CombatTurnResult", field_name)
            for replacement in (
                "#/components/schemas/GameSession",
                "#/components/schemas/CombatTurnResult",
            ):
                for flow_style in (False, True):
                    with self.subTest(
                        field=field_name, replacement=replacement, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        field = spec["components"]["schemas"]["CombatTurnResult"][
                            "properties"
                        ][field_name]
                        target = field["items"] if field_name == "enemy_actions" else next(
                            branch for branch in field["anyOf"] if "$ref" in branch
                        )
                        target["$ref"] = replacement
                        self.assertEqual(_schema_types(field), _schema_types(original))
                        self.assertEqual(_is_nullable(field), _is_nullable(original))
                        if field_name == "enemy_actions":
                            self.assertEqual(
                                _schema_types(target), _schema_types(original["items"])
                            )
                            self.assertEqual(
                                _is_nullable(target), _is_nullable(original["items"])
                            )
                        text = yaml.safe_dump(spec, default_flow_style=flow_style)
                        with patch.dict(globals(), SPEC=_load_spec(text)):
                            unchanged = unittest.TestResult()
                            ContractParityTests(
                                "test_combat_result_is_the_serializer_allowlist_and_nullable"
                            ).run(unchanged)
                            self.assertTrue(
                                unchanged.wasSuccessful(), unchanged.failures + unchanged.errors
                            )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_enemy_result_references_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertTrue(
                            result.failures,
                            f"Undetected enemy result reference drift: {field_name}",
                        )
                        self.assertTrue(
                            all(
                                f"CombatTurnResult.{field_name} reference target" in failure
                                for _, failure in result.failures
                            ),
                            result.failures,
                        )

    def test_death_reference_mutations_fail_in_both_formats(self):
        fields = [
            (model.__name__, field_name)
            for model, field_name in DEATH_REFERENCE_FIELDS
        ] + [("GameState", "death_state")]
        for schema_name, field_name in fields:
            original = _property(schema_name, field_name)
            references = _schema_references(original)
            wrong_death_model = (
                "DeathSaveResult"
                if "#/components/schemas/DeathSaveResult" not in references
                else "DeathResolutionResult"
            )
            for replacement in (
                f"#/components/schemas/{wrong_death_model}",
                "#/components/schemas/GameSession",
                None,
            ):
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, field=field_name,
                        replacement=replacement, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        field = spec["components"]["schemas"][schema_name][
                            "properties"
                        ][field_name]
                        target = field if "$ref" in field else next(
                            branch for branch in field["anyOf"] if "$ref" in branch
                        )
                        if replacement is None:
                            del target["$ref"]
                            target["type"] = "object"
                        else:
                            target["$ref"] = replacement
                        # Wrong targets still have the same object/null type.
                        self.assertEqual(_schema_types(field), _schema_types(original))
                        self.assertEqual(_is_nullable(field), _is_nullable(original))
                        text = yaml.safe_dump(spec, default_flow_style=flow_style)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=_load_spec(text)):
                            ContractParityTests(
                                "test_nested_death_references_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertTrue(
                            result.failures,
                            f"Undetected reference drift: {schema_name}.{field_name}",
                        )

    def test_session_creation_and_campaign_resume_wrong_bindings_fail_in_both_formats(self):
        for path in (
            "/game/sessions",
            "/sessions",
            "/game/campaigns/{campaign_id}/resume",
            "/campaigns/{campaign_id}/resume",
        ):
            for binding in ("requestBody", "response"):
                for flow_style in (False, True):
                    with self.subTest(path=path, binding=binding, compact=flow_style):
                        spec = deepcopy(SPEC)
                        operation = spec["paths"][path]["post"]
                        if binding == "requestBody":
                            self.assertNotIn("requestBody", operation)
                            operation["requestBody"] = {
                                "required": True,
                                "content": {"application/json": {"schema": {
                                    "$ref": "#/components/schemas/CampaignCreateInput",
                                }}},
                            }
                        else:
                            schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
                            # Both targets remain valid components; only the
                            # operation's binding to the component is wrong.
                            schema["$ref"] = (
                                "#/components/schemas/CampaignSession"
                                if path.endswith("/sessions")
                                else "#/components/schemas/GameSession"
                            )
                        self.assertEqual(spec["components"], SPEC["components"])
                        text = yaml.safe_dump(spec, default_flow_style=flow_style)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=_load_spec(text)):
                            for test_name in (
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                                "test_operation_ids_are_unique_and_error_statuses_are_documented",
                                "test_health_and_request_schemas_match_runtime_models",
                                "test_campaign_and_session_schema_fields_match_fastapi_models",
                                "test_turn_route_bindings_match_fastapi",
                                "test_species_action_route_bindings_match_fastapi",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            ContractParityTests(
                                "test_session_creation_and_campaign_resume_route_bindings_match_fastapi"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(f"path='{path}'", result.failures[0][0].id())
                        self.assertIn(f"binding='{binding}'", result.failures[0][0].id())

    def test_turn_wrong_route_bindings_fail_in_both_formats(self):
        for path in (
            "/game/sessions/{session_id}/turn",
            "/sessions/{session_id}/turn",
        ):
            for binding in ("requestBody", "response"):
                for flow_style in (False, True):
                    with self.subTest(path=path, binding=binding, compact=flow_style):
                        spec = deepcopy(SPEC)
                        operation = spec["paths"][path]["post"]
                        if binding == "requestBody":
                            schema = operation["requestBody"]["content"]["application/json"]["schema"]
                            wrong_ref = "#/components/schemas/SpeciesTraitActionInput"
                        else:
                            schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
                            wrong_ref = "#/components/schemas/SpeciesTraitCommandResult"
                        schema["$ref"] = wrong_ref
                        text = yaml.safe_dump(spec, default_flow_style=flow_style)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=_load_spec(text)):
                            # Only a binding changes; inventory, statuses and models stay valid.
                            for test_name in (
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                                "test_operation_ids_are_unique_and_error_statuses_are_documented",
                                "test_health_and_request_schemas_match_runtime_models",
                                "test_campaign_and_session_schema_fields_match_fastapi_models",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            ContractParityTests(
                                "test_turn_route_bindings_match_fastapi"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(f"path='{path}'", result.failures[0][0].id())
                        self.assertIn(f"binding='{binding}'", result.failures[0][0].id())


if __name__ == "__main__":
    unittest.main()

"""Contract checks between the published OpenAPI file and the FastAPI app."""

from __future__ import annotations

import re
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
    CampaignStartLocationOption,
    CampaignStartOptionsResponse,
    CampaignStartRegionOption,
    CampaignStartSettingOption,
    CampaignSummary,
    CharacterCreateInput,
    CharacterCreationOptions,
    CharacterCreationCatalogResponse,
    CombatActionInput,
    CombatAttackResult,
    CombatHistoryEntry,
    CombatTurnResult,
    DeathResolutionResult,
    DeathSaveResult,
    DeathStateProjection,
    EconomyStepInput,
    HealthResponse,
    QuestCommandResult,
    QuestObjectiveOffer,
    QuestObjectiveState,
    QuestOffer,
    QuestOutcome,
    QuestState,
    ReadyResponseInput,
    ReadyTriggerInput,
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


_SAFE_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_SAFE_DUMPER = getattr(yaml, "CSafeDumper", yaml.SafeDumper)


class _ContractLoader(_DuplicateKeyLoaderMixin, _SAFE_LOADER):
    """Use LibYAML when installed, without relaxing safe-loader checks."""


def _dump_spec(spec, *, default_flow_style, sort_keys=True):
    """Serialize each independent mutation with a safe, optionally C-backed dumper."""
    return yaml.dump(
        spec, Dumper=_SAFE_DUMPER,
        default_flow_style=default_flow_style, sort_keys=sort_keys,
    )
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


def _nested_schema_objects(schema: Any, label: str):
    """Walk schema keywords only, never examples or arbitrary metadata."""
    schema = _mapping(schema, label)
    yield label, schema
    for name, child in _mapping(schema.get("properties", {}), f"{label}.properties").items():
        yield from _nested_schema_objects(child, f"{label}.properties.{name}")
    if "items" in schema:
        yield from _nested_schema_objects(schema["items"], f"{label}.items")
    # Boolean additionalProperties permits/forbids unknown keys; only its
    # schema-valued form can declare required fields for dictionary values.
    if isinstance(schema.get("additionalProperties"), dict):
        yield from _nested_schema_objects(
            schema["additionalProperties"], f"{label}.additionalProperties",
        )
    for keyword in ("anyOf", "allOf", "oneOf"):
        for index, child in enumerate(schema.get(keyword, [])):
            yield from _nested_schema_objects(child, f"{label}.{keyword}[{index}]")

def _parameter_schema_objects(parameters: list[dict[str, Any]], label: str):
    for index, parameter in enumerate(parameters):
        if "schema" in parameter:
            yield from _nested_schema_objects(
                parameter["schema"], f"{label}[{index}].schema",
            )
        for media_type, media in parameter.get("content", {}).items():
            if "schema" in media:
                yield from _nested_schema_objects(
                    media["schema"], f"{label}[{index}].content.{media_type}.schema",
                )
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

QUEST_OBJECTIVE_LIST_MODELS = (
    (QuestState, QuestObjectiveState, "QuestObjective"),
    (QuestOffer, QuestObjectiveOffer, "QuestObjectiveOffer"),
)

# Published objective strings intentionally omit the runtime minLength=1.
# Keep exceptions field-specific rather than ignoring all string constraints.
QUEST_OBJECTIVE_MIN_LENGTH_EXCEPTIONS = {
    ("QuestObjective", "objective_id"),
    ("QuestObjective", "description"),
    ("QuestObjectiveOffer", "objective_id"),
    ("QuestObjectiveOffer", "description"),
    ("QuestObjectiveOffer", "target"),
}

# Parent quest strings have the same intentional published minLength omission.
QUEST_PARENT_MIN_LENGTH_EXCEPTIONS = {
    (schema_name, field_name)
    for schema_name in ("QuestOffer", "QuestState")
    for field_name in ("quest_id", "title", "description")
}

QUEST_COMMAND_PATHS = (
    "/game/sessions/{session_id}/quests/{quest_id}/accept",
    "/game/sessions/{session_id}/quests/{quest_id}/cancel",
)

CAMPAIGN_START_ARRAY_FIELDS = (
    (CampaignStartOptionsResponse, "settings", CampaignStartSettingOption),
    (CampaignStartSettingOption, "regions", CampaignStartRegionOption),
    (CampaignStartRegionOption, "starting_locations", CampaignStartLocationOption),
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
    def test_campaign_start_schemas_match_runtime_models(self):
        for model in (
            CampaignStartOptionsResponse,
            CampaignStartSettingOption,
            CampaignStartRegionOption,
            CampaignStartLocationOption,
        ):
            schema_name = model.__name__
            runtime = model.model_json_schema()
            published_schema = _schema(schema_name)
            with self.subTest(schema=schema_name, contract="type"):
                self.assertEqual(
                    _schema_types(published_schema), _schema_types(runtime),
                    f"{schema_name} type",
                )
            with self.subTest(schema=schema_name, contract="nullable"):
                self.assertEqual(
                    _is_nullable(published_schema), _is_nullable(runtime),
                    f"{schema_name} nullable",
                )
            with self.subTest(schema=schema_name):
                self.assertEqual(_property_names(schema_name), _runtime_field_names(model))
                self.assertEqual(
                    set(_schema(schema_name).get("required", [])),
                    set(runtime.get("required", [])),
                    f"{schema_name}.required",
                )
                self.assertEqual(
                    _schema(schema_name).get("additionalProperties"),
                    runtime.get("additionalProperties"),
                    f"{schema_name}.additionalProperties",
                )
            for field_name, runtime_field in runtime["properties"].items():
                with self.subTest(schema=schema_name, field=field_name):
                    published = _property(schema_name, field_name)
                    self.assertEqual(
                        _schema_types(published), _schema_types(runtime_field),
                        f"{schema_name}.{field_name} type",
                    )
                    self.assertEqual(
                        _is_nullable(published), _is_nullable(runtime_field),
                        f"{schema_name}.{field_name} nullable",
                    )

    def test_campaign_start_item_references_match_runtime_models(self):
        for model, field_name, item_model in CAMPAIGN_START_ARRAY_FIELDS:
            schema_name = model.__name__
            label = f"{schema_name}.{field_name}.items"
            with self.subTest(schema=schema_name, field=field_name):
                runtime = model.model_json_schema(
                    ref_template="#/components/schemas/{model}"
                )["properties"][field_name]
                published = _property(schema_name, field_name)
                self.assertEqual(_schema_types(runtime), {"array"})
                self.assertEqual(_schema_types(published), _schema_types(runtime))
                self.assertEqual(_is_nullable(published), _is_nullable(runtime))
                runtime_items = _mapping(runtime.get("items"), label)
                published_items = _mapping(published.get("items"), label)
                expected = _schema_references(runtime_items)
                self.assertEqual(
                    expected, {f"#/components/schemas/{item_model.__name__}"},
                    f"Runtime {label} must reference {item_model.__name__}",
                )
                self.assertEqual(
                    _schema_references(published_items), expected,
                    f"{label} reference target",
                )
                self.assertEqual(_schema_types(published_items), _schema_types(runtime_items))
                self.assertEqual(_is_nullable(published_items), _is_nullable(runtime_items))

    def test_quest_objective_item_references_match_runtime_models(self):
        for model, item_model, published_item_name in QUEST_OBJECTIVE_LIST_MODELS:
            with self.subTest(schema=model.__name__):
                runtime = model.model_json_schema(
                    ref_template="#/components/schemas/{model}"
                )["properties"]["objectives"]
                published = _property(model.__name__, "objectives")
                self.assertEqual(_schema_types(runtime), {"array"})
                self.assertEqual(_schema_types(published), _schema_types(runtime))
                self.assertEqual(_is_nullable(published), _is_nullable(runtime))
                runtime_items = _mapping(
                    runtime.get("items"), f"{model.__name__}.objectives.items"
                )
                published_items = _mapping(
                    published.get("items"), f"{model.__name__}.objectives.items"
                )
                runtime_ref = f"#/components/schemas/{item_model.__name__}"
                self.assertEqual(
                    _schema_references(runtime_items), {runtime_ref},
                    f"Runtime {model.__name__}.objectives items must reference "
                    f"{item_model.__name__}",
                )
                # QuestObjectiveState is intentionally published as QuestObjective;
                # QuestObjectiveOffer retains its runtime name.
                runtime_to_published_refs = {
                    runtime_ref: f"#/components/schemas/{published_item_name}"
                }
                expected = {
                    runtime_to_published_refs[ref]
                    for ref in _schema_references(runtime_items)
                }
                self.assertEqual(
                    _schema_references(published_items), expected,
                    f"{model.__name__}.objectives.items reference target",
                )
                self.assertEqual(
                    _schema_types(published_items), _schema_types(runtime_items)
                )
                self.assertEqual(
                    _is_nullable(published_items), _is_nullable(runtime_items)
                )

    def test_quest_parent_schemas_match_runtime_models(self):
        for model in (QuestOffer, QuestState):
            schema_name = model.__name__
            runtime = model.model_json_schema()
            published_schema = _schema(schema_name)
            with self.subTest(schema=schema_name):
                self.assertEqual(
                    _property_names(schema_name), _runtime_field_names(model),
                    f"{schema_name}.properties",
                )
                # The response always emits the nullable giver, although the
                # runtime constructor permits omission and defaults it to None.
                self.assertNotIn("giver_npc_id", runtime.get("required", []))
                self.assertIn("default", runtime["properties"]["giver_npc_id"])
                self.assertIsNone(runtime["properties"]["giver_npc_id"]["default"])
                self.assertEqual(
                    set(published_schema.get("required", [])),
                    set(runtime.get("required", [])) | {"giver_npc_id"},
                    f"{schema_name}.required",
                )
                self.assertEqual(
                    _schema_types(published_schema), _schema_types(runtime),
                    f"{schema_name} type",
                )
                self.assertEqual(
                    published_schema.get("additionalProperties"),
                    runtime.get("additionalProperties"),
                    f"{schema_name}.additionalProperties",
                )
            for field_name, runtime_field in runtime["properties"].items():
                with self.subTest(schema=schema_name, field=field_name):
                    label = f"{schema_name}.{field_name}"
                    published = _property(schema_name, field_name)
                    self.assertEqual(
                        _schema_types(published), _schema_types(runtime_field),
                        f"{label} type",
                    )
                    self.assertEqual(
                        _is_nullable(published), _is_nullable(runtime_field),
                        f"{label} nullable",
                    )
                    self.assertEqual(
                        _schema_enum(published), _schema_enum(runtime_field),
                        f"{label} enum",
                    )
                    # No published defaults: in particular, the runtime giver
                    # default must not make the required response key optional.
                    self.assertNotIn("default", published, f"{label} default")
                    runtime_string = runtime_field
                    if field_name == "giver_npc_id":
                        runtime_string = next(
                            branch for branch in runtime_field["anyOf"]
                            if branch.get("type") == "string"
                        )
                    for constraint in ("minLength", "maxLength"):
                        expected = runtime_string.get(constraint)
                        if (
                            constraint == "minLength"
                            and (schema_name, field_name)
                            in QUEST_PARENT_MIN_LENGTH_EXCEPTIONS
                        ):
                            self.assertEqual(expected, 1, f"Runtime {label}.minLength")
                            expected = None
                        self.assertEqual(
                            published.get(constraint), expected,
                            f"{label}.{constraint}",
                        )

    def test_quest_objective_schemas_match_runtime_models(self):
        # Reuse the explicit QuestObjectiveState -> QuestObjective alias; these
        # checks inspect the referenced components, not just the list bindings.
        for _, model, schema_name in QUEST_OBJECTIVE_LIST_MODELS:
            runtime = model.model_json_schema()
            with self.subTest(schema=schema_name):
                self.assertEqual(
                    _property_names(schema_name), _runtime_field_names(model),
                    f"{schema_name}.properties",
                )
                self.assertEqual(
                    set(_schema(schema_name).get("required", [])),
                    set(runtime.get("required", [])),
                    f"{schema_name}.required",
                )
                self.assertEqual(
                    _schema_types(_schema(schema_name)), _schema_types(runtime),
                    f"{schema_name} type",
                )
                self.assertEqual(
                    _schema(schema_name).get("additionalProperties"),
                    runtime.get("additionalProperties"),
                    f"{schema_name}.additionalProperties",
                )
            for field_name, runtime_field in runtime["properties"].items():
                with self.subTest(schema=schema_name, field=field_name):
                    label = f"{schema_name}.{field_name}"
                    published = _property(schema_name, field_name)
                    self.assertEqual(
                        _schema_types(published), _schema_types(runtime_field),
                        f"{label} type",
                    )
                    self.assertEqual(
                        _is_nullable(published), _is_nullable(runtime_field),
                        f"{label} nullable",
                    )
                    self.assertEqual(
                        _schema_enum(published), _schema_enum(runtime_field),
                        f"{label} enum",
                    )
                    for constraint in (
                        "minimum", "maximum", "exclusiveMinimum",
                        "exclusiveMaximum", "multipleOf", "minLength", "maxLength",
                    ):
                        expected = runtime_field.get(constraint)
                        if (
                            constraint == "minLength"
                            and (schema_name, field_name)
                            in QUEST_OBJECTIVE_MIN_LENGTH_EXCEPTIONS
                        ):
                            self.assertEqual(expected, 1, f"Runtime {label}.minLength")
                            expected = None
                        self.assertEqual(
                            published.get(constraint), expected,
                            f"{label}.{constraint}",
                        )

    def test_quest_outcome_schema_matches_runtime_model(self):
        schema_name = "QuestOutcome"
        runtime = QuestOutcome.model_json_schema()
        published_schema = _schema(schema_name)
        # Responses emit objective_id even when callers omit it at construction.
        # Do not turn this response guarantee into a runtime required-field rule.
        self.assertNotIn("objective_id", runtime.get("required", []))
        self.assertIsNone(runtime["properties"]["objective_id"]["default"])
        self.assertEqual(
            _property_names(schema_name), _runtime_field_names(QuestOutcome),
            f"{schema_name}.properties",
        )
        self.assertEqual(
            set(published_schema.get("required", [])),
            set(runtime.get("required", [])) | {"objective_id"},
            f"{schema_name}.required",
        )
        self.assertEqual(
            _schema_types(published_schema), _schema_types(runtime),
            f"{schema_name} type",
        )
        self.assertEqual(
            _is_nullable(published_schema), _is_nullable(runtime),
            f"{schema_name} nullable",
        )
        self.assertEqual(
            published_schema.get("additionalProperties"),
            runtime.get("additionalProperties"),
            f"{schema_name}.additionalProperties",
        )
        # These exact published bounds are intentional, not runtime bounds.
        published_string_limits = {
            "event_id": 300, "quest_id": 120,
            "objective_id": 120, "source_event_id": 300,
        }
        for field_name, runtime_field in runtime["properties"].items():
            with self.subTest(field=field_name):
                label = f"{schema_name}.{field_name}"
                published = _property(schema_name, field_name)
                self.assertEqual(
                    _schema_types(published), _schema_types(runtime_field),
                    f"{label} type",
                )
                self.assertEqual(
                    _is_nullable(published), _is_nullable(runtime_field),
                    f"{label} nullable",
                )
                self.assertEqual(
                    _schema_enum(published), _schema_enum(runtime_field),
                    f"{label} enum",
                )
                # Only objective_id has a runtime default; the public response
                # declares presence instead and intentionally has no default.
                self.assertEqual(
                    "default" in runtime_field, field_name == "objective_id",
                    f"Runtime {label}.default",
                )
                self.assertNotIn("default", published, f"{label}.default")
                for constraint in (
                    "minimum", "maximum", "exclusiveMinimum",
                    "exclusiveMaximum", "multipleOf", "minLength", "maxLength",
                ):
                    expected = runtime_field.get(constraint)
                    if constraint == "maxLength" and field_name in published_string_limits:
                        self.assertIsNone(expected, f"Runtime {label}.maxLength")
                        expected = published_string_limits[field_name]
                    self.assertEqual(
                        published.get(constraint), expected,
                        f"{label}.{constraint}",
                    )

    def test_turn_quest_outcome_item_references_match_runtime_model(self):
        runtime = TurnResponse.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["properties"]["quest_outcomes"]
        published = _property("GameTurnResult", "quest_outcomes")
        self.assertEqual(_schema_types(runtime), {"array"})
        self.assertEqual(_schema_types(published), _schema_types(runtime))
        self.assertEqual(_is_nullable(published), _is_nullable(runtime))
        runtime_items = _mapping(
            runtime.get("items"), "TurnResponse.quest_outcomes.items"
        )
        published_items = _mapping(
            published.get("items"), "GameTurnResult.quest_outcomes.items"
        )
        expected = _schema_references(runtime_items)
        self.assertEqual(
            expected, {f"#/components/schemas/{QuestOutcome.__name__}"},
            "Runtime quest_outcomes items must reference QuestOutcome",
        )
        self.assertEqual(
            _schema_references(published_items), expected,
            "GameTurnResult.quest_outcomes.items reference target",
        )
        self.assertEqual(_schema_types(published_items), _schema_types(runtime_items))
        self.assertEqual(_is_nullable(published_items), _is_nullable(runtime_items))

    def test_turn_input_combat_action_reference_matches_runtime_model(self):
        runtime = TurnRequest.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["properties"]["combat_action"]
        published = _property("GameTurnInput", "combat_action")
        expected = _schema_references(runtime)
        self.assertEqual(
            expected, {"#/components/schemas/CombatActionInput"},
            "Runtime combat_action must reference the published CombatActionInput",
        )
        self.assertEqual(
            _schema_references(published), expected,
            "GameTurnInput.combat_action reference target",
        )
        self.assertEqual(_schema_types(published), _schema_types(runtime))
        self.assertEqual(_is_nullable(published), _is_nullable(runtime))

    def test_combat_step_item_reference_matches_runtime_model(self):
        runtime = CombatActionInput.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["properties"]["steps"]
        published = _property("CombatActionInput", "steps")
        self.assertEqual(_schema_types(published), _schema_types(runtime))
        self.assertEqual(_is_nullable(published), _is_nullable(runtime))
        runtime_items = _mapping(runtime.get("items"), "CombatActionInput.steps.items")
        published_items = _mapping(
            published.get("items"), "CombatActionInput.steps.items"
        )
        expected = _schema_references(runtime_items)
        self.assertEqual(
            expected, {f"#/components/schemas/{EconomyStepInput.__name__}"},
            "Runtime steps items must reference EconomyStepInput",
        )
        self.assertEqual(
            _schema_references(published_items), expected,
            "CombatActionInput.steps.items reference target",
        )
        self.assertEqual(_schema_types(published_items), _schema_types(runtime_items))
        self.assertEqual(_is_nullable(published_items), _is_nullable(runtime_items))

    def test_combat_ready_references_match_runtime_models(self):
        runtime_properties = EconomyStepInput.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["properties"]
        for field_name, target_model, published_target in (
            ("trigger", ReadyTriggerInput, "ReadyTriggerInput"),
            ("response", ReadyResponseInput, "ReadyResponseInput"),
        ):
            with self.subTest(field=field_name):
                runtime = runtime_properties[field_name]
                published = _property("EconomyStepInput", field_name)
                runtime_ref = f"#/components/schemas/{target_model.__name__}"
                self.assertEqual(
                    _schema_references(runtime), {runtime_ref},
                    f"Runtime EconomyStepInput.{field_name} reference target",
                )
                expected = {
                    ref.replace(runtime_ref, f"#/components/schemas/{published_target}")
                    for ref in _schema_references(runtime)
                }
                self.assertEqual(
                    _schema_references(published), expected,
                    f"EconomyStepInput.{field_name} reference target",
                )
                self.assertEqual(_schema_types(published), _schema_types(runtime))
                self.assertEqual(_is_nullable(published), _is_nullable(runtime))

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

    def test_health_route_bindings_match_fastapi(self):
        runtime_spec = app.openapi()
        base_path = SPEC["servers"][0]["url"].rstrip("/")
        for path in ("/game/health", "/health"):
            published = _operation(path, "get")
            runtime = runtime_spec["paths"][f"{base_path}{path}"]["get"]
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
            for status in runtime_successes.keys() & published_successes.keys():
                with self.subTest(path=path, binding="response", status=status):
                    self.assertEqual(
                        published_successes[status]["content"]["application/json"]["schema"],
                        runtime_successes[status]["content"]["application/json"]["schema"],
                    )

    def test_turn_action_id_pattern_matches_uuid4_validator(self):
        # Pydantic publishes generic UUID format; the custom field validator
        # supplies the version restriction that must remain in our contract.
        pattern = _property("GameTurnInput", "action_id").get("pattern")
        self.assertEqual(
            pattern,
            "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            "GameTurnInput.action_id.pattern",
        )
        for variant in "89ab":
            action_id = f"12345678-9abc-4def-{variant}123-456789abcdef"
            with self.subTest(accepted=action_id):
                validated = TurnRequest(message="wait", action_id=action_id)
                self.assertEqual(str(validated.action_id), action_id)
                self.assertIsNotNone(re.fullmatch(pattern, action_id))
        for version in "01235678":
            action_id = f"12345678-9abc-{version}def-8123-456789abcdef"
            with self.subTest(rejected=action_id):
                with self.assertRaisesRegex(ValidationError, "Action ID must be a UUIDv4"):
                    TurnRequest(message="wait", action_id=action_id)
                self.assertIsNone(re.fullmatch(pattern, action_id))
        for variant in "07cf":
            action_id = f"12345678-9abc-4def-{variant}123-456789abcdef"
            with self.subTest(rejected_variant=action_id):
                with self.assertRaisesRegex(ValidationError, "Action ID must be a UUIDv4"):
                    TurnRequest(message="wait", action_id=action_id)
                self.assertIsNone(re.fullmatch(pattern, action_id))

    def test_health_and_request_schemas_match_runtime_models(self):
        runtime_health = HealthResponse.model_json_schema(mode="serialization")
        self.assertEqual(
            _property_names("HealthResponse"),
            _runtime_field_names(HealthResponse),
        )
        self.assertEqual(
            set(_schema("HealthResponse").get("required", [])),
            # Defaults make construction optional, not the fields emitted by
            # this response model (the health route does not exclude defaults).
            set(HealthResponse().model_dump(mode="json")),
            "HealthResponse.required",
        )
        for field_name, runtime_property in runtime_health["properties"].items():
            with self.subTest(schema="HealthResponse", field=field_name):
                self.assertEqual(
                    _schema_types(_property("HealthResponse", field_name)),
                    _schema_types(runtime_property),
                    f"HealthResponse.{field_name}.type",
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
        runtime = TurnRequest.model_json_schema()
        required = _schema("GameTurnInput").get("required", [])
        self.assertIsInstance(required, list, "GameTurnInput.required must be a list")
        self.assertEqual(
            set(required), set(runtime.get("required", [])),
            "GameTurnInput.required",
        )
        for field_name, runtime_property in runtime["properties"].items():
            with self.subTest(turn_request_field=field_name):
                published = _property("GameTurnInput", field_name)
                self.assertEqual(
                    _schema_types(published), _schema_types(runtime_property),
                    f"GameTurnInput.{field_name}.type",
                )
                self.assertEqual(
                    _is_nullable(published), _is_nullable(runtime_property),
                    f"GameTurnInput.{field_name}.nullable",
                )
                constraints = {
                    "target_id": ("minLength", "maxLength"),
                    "combat_id": ("minLength", "maxLength"),
                    "action_id": ("format",),
                    "combat_round": ("minimum",),
                    "combat_turn_index": ("minimum",),
                }.get(field_name, ())
                if constraints:
                    runtime_value = next(
                        branch for branch in runtime_property["anyOf"]
                        if branch.get("type") != "null"
                    )
                    for constraint in constraints:
                        self.assertEqual(
                            published.get(constraint), runtime_value[constraint],
                            f"GameTurnInput.{field_name}.{constraint}",
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
            "CombatHistoryEntry": CombatHistoryEntry,
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

    def test_character_creation_component_types_match_runtime_models(self):
        for model in (CharacterCreationOptions, CharacterCreationCatalogResponse):
            schema_name = model.__name__
            published = _schema(schema_name)
            runtime = model.model_json_schema()
            with self.subTest(schema=schema_name, contract="type"):
                self.assertEqual(
                    _schema_types(published), _schema_types(runtime),
                    f"{schema_name}.type",
                )
            with self.subTest(schema=schema_name, contract="nullable"):
                self.assertEqual(
                    _is_nullable(published), _is_nullable(runtime),
                    f"{schema_name}.nullable",
                )

    def test_campaign_summary_scalar_fields_match_runtime_model(self):
        schema_name = "CampaignSummary"
        published = _schema(schema_name)
        runtime = CampaignSummary.model_json_schema()
        self.assertEqual(
            set(published.get("required", [])),
            set(runtime.get("required", [])),
            f"{schema_name}.required",
        )
        for field_name, runtime_field in runtime["properties"].items():
            with self.subTest(field=field_name):
                published_field = _property(schema_name, field_name)
                self.assertEqual(
                    _schema_types(published_field) - {"null"},
                    _schema_types(runtime_field) - {"null"},
                    f"{schema_name}.{field_name}.type",
                )
                self.assertEqual(
                    _is_nullable(published_field),
                    _is_nullable(runtime_field),
                    f"{schema_name}.{field_name}.nullable",
                )

    def test_campaign_session_scalar_fields_match_runtime_model(self):
        schema_name = "CampaignSession"
        runtime = CampaignSessionResponse.model_json_schema()
        required = _schema(schema_name).get("required", [])
        self.assertIsInstance(required, list, f"{schema_name}.required must be a list")
        # Compare only these scalars; saved-history requirements have their
        # own parity checks and must not determine this test's result.
        for field_name in ("campaign_id", "session_id", "name"):
            with self.subTest(field=field_name):
                published_field = _property(schema_name, field_name)
                runtime_field = runtime["properties"][field_name]
                self.assertEqual(
                    _schema_types(published_field) - {"null"},
                    _schema_types(runtime_field) - {"null"},
                    f"{schema_name}.{field_name}.type",
                )
                self.assertEqual(
                    _is_nullable(published_field), _is_nullable(runtime_field),
                    f"{schema_name}.{field_name}.nullable",
                )
                self.assertEqual(
                    field_name in required,
                    field_name in runtime.get("required", []),
                    f"{schema_name}.{field_name}.required",
                )

    def test_campaign_detail_summary_reference_matches_runtime_model(self):
        runtime = CampaignDetailResponse.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["properties"]["campaign"]
        published = _property("CampaignDetail", "campaign")
        self.assertEqual(_schema_types(published), _schema_types(runtime))
        self.assertEqual(_is_nullable(published), _is_nullable(runtime))
        expected = _schema_references(runtime)
        self.assertEqual(
            expected, {"#/components/schemas/CampaignSummary"},
            "Runtime CampaignDetail.campaign must reference CampaignSummary",
        )
        self.assertEqual(
            _schema_references(published), expected,
            "CampaignDetail.campaign reference target",
        )

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

    def test_character_setup_route_bindings_match_fastapi(self):
        runtime_spec = app.openapi()
        base_path = SPEC["servers"][0]["url"].rstrip("/")
        # These setup models intentionally share their public and Python names;
        # unlike campaign/session replies, they need no reference renaming.
        for path in (
            "/game/character-options",
            "/character-options",
            "/game/character-creation-catalog",
            "/character-creation-catalog",
            "/game/campaign-start-options",
            "/campaign-start-options",
        ):
            published = _operation(path, "get")
            runtime = runtime_spec["paths"][f"{base_path}{path}"]["get"]
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
                        {"$ref": runtime_schema["$ref"]},
                    )

    def test_campaign_read_route_bindings_match_fastapi(self):
        runtime_spec = app.openapi()
        base_path = SPEC["servers"][0]["url"].rstrip("/")
        # CampaignSummary is shared; the detail model has a public-facing name.
        runtime_to_published_refs = {
            "#/components/schemas/CampaignDetailResponse": "#/components/schemas/CampaignDetail",
        }
        for path in (
            "/game/campaigns",
            "/campaigns",
            "/game/campaigns/{campaign_id}",
            "/campaigns/{campaign_id}",
        ):
            published = _operation(path, "get")
            runtime = runtime_spec["paths"][f"{base_path}{path}"]["get"]
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
                    if runtime_schema.get("type") == "array":
                        runtime_ref = runtime_schema["items"]["$ref"]
                        expected_schema = {
                            "type": "array",
                            "items": {"$ref": runtime_to_published_refs.get(
                                runtime_ref, runtime_ref,
                            )},
                        }
                    else:
                        runtime_ref = runtime_schema["$ref"]
                        expected_schema = {"$ref": runtime_to_published_refs.get(
                            runtime_ref, runtime_ref,
                        )}
                    # FastAPI's generated titles are documentation, not bindings.
                    self.assertEqual(
                        published_successes[status]["content"]["application/json"]["schema"],
                        expected_schema,
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

    def test_campaign_creation_and_save_route_bindings_match_fastapi(self):
        runtime_spec = app.openapi()
        base_path = SPEC["servers"][0]["url"].rstrip("/")
        # Creation has public model names; saves reuse Python's summary name.
        runtime_to_published_refs = {
            "#/components/schemas/CampaignCreateRequest": "#/components/schemas/CampaignCreateInput",
            "#/components/schemas/CampaignSessionResponse": "#/components/schemas/CampaignSession",
        }
        for path in (
            "/game/campaigns",
            "/campaigns",
            "/game/campaigns/{campaign_id}/save",
            "/campaigns/{campaign_id}/save",
        ):
            published = _operation(path, "post")
            runtime = runtime_spec["paths"][f"{base_path}{path}"]["post"]
            with self.subTest(path=path, binding="requestBody"):
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
            # Missing statuses are already reported above, not as a KeyError.
            for status in runtime_successes.keys() & published_successes.keys():
                with self.subTest(path=path, binding="response", status=status):
                    runtime_schema = runtime_successes[status]["content"]["application/json"]["schema"]
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

    def test_saved_story_history_constraints_match_runtime_model(self):
        schema_name = "CampaignHistoryEntry"
        runtime = CampaignHistoryEntry.model_json_schema()
        published = _schema(schema_name)
        self.assertEqual(
            set(published.get("required", [])),
            set(runtime.get("required", [])),
            f"{schema_name}.required",
        )
        for field_name in ("player_message", "narration", "created_at"):
            with self.subTest(field=field_name):
                self.assertEqual(
                    _schema_types(_property(schema_name, field_name)),
                    _schema_types(runtime["properties"][field_name]),
                    f"{schema_name}.{field_name}.type",
                )

    def test_saved_combat_history_constraints_match_runtime_model(self):
        schema_name = "CombatHistoryEntry"
        runtime = CombatHistoryEntry.model_json_schema()
        published = _schema(schema_name)
        self.assertEqual(
            set(published.get("required", [])),
            set(runtime.get("required", [])),
            f"{schema_name}.required",
        )
        self.assertEqual(
            published.get("additionalProperties"),
            runtime.get("additionalProperties"),
            f"{schema_name}.additionalProperties",
        )
        for field_name, constraints in (
            ("event_id", ("type", "pattern")),
            ("turn_index", ("type", "minimum")),
        ):
            for constraint in constraints:
                with self.subTest(field=field_name, constraint=constraint):
                    published_value = _property(schema_name, field_name).get(constraint)
                    if constraint == "minimum":
                        # bool subclasses int, so False == 0 must not hide drift.
                        self.assertNotIsInstance(
                            published_value, bool,
                            f"{schema_name}.{field_name}.{constraint} must be numeric, not boolean",
                        )
                    self.assertEqual(
                        published_value,
                        runtime["properties"][field_name].get(constraint),
                        f"{schema_name}.{field_name}.{constraint}",
                    )

    def test_campaign_history_required_fields_match_runtime_models(self):
        for schema_name, model in (
            ("CampaignDetail", CampaignDetailResponse),
            ("CampaignSession", CampaignSessionResponse),
        ):
            runtime_required = set(model.model_json_schema().get("required", []))
            published_required = set(_schema(schema_name).get("required", []))
            for field_name in ("history", "combat_history"):
                with self.subTest(schema=schema_name, field=field_name):
                    self.assertEqual(
                        field_name in published_required,
                        field_name in runtime_required,
                        f"{schema_name}.{field_name}.required",
                    )

    def test_campaign_history_item_references_match_runtime_models(self):
        for schema_name, model in (
            ("CampaignDetail", CampaignDetailResponse),
            ("CampaignSession", CampaignSessionResponse),
        ):
            runtime_properties = model.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )["properties"]
            for field_name, entry_model in (
                ("history", CampaignHistoryEntry),
                ("combat_history", CombatHistoryEntry),
            ):
                with self.subTest(schema=schema_name, field=field_name):
                    runtime = runtime_properties[field_name]
                    published = _property(schema_name, field_name)
                    self.assertEqual(
                        _schema_types(published), _schema_types(runtime),
                        f"{schema_name}.{field_name}.type",
                    )
                    self.assertEqual(
                        _is_nullable(published), _is_nullable(runtime),
                        f"{schema_name}.{field_name}.nullable",
                    )
                    published_items = _mapping(
                        published.get("items"), f"{schema_name}.{field_name}.items"
                    )
                    runtime_items = runtime["items"]
                    self.assertEqual(
                        _schema_types(published_items), _schema_types(runtime_items)
                    )
                    self.assertEqual(
                        _is_nullable(published_items), _is_nullable(runtime_items)
                    )
                    expected = _schema_references(runtime_items)
                    self.assertEqual(
                        expected, {f"#/components/schemas/{entry_model.__name__}"},
                        f"Runtime {schema_name}.{field_name} items must reference "
                        f"{entry_model.__name__}",
                    )
                    self.assertEqual(
                        _schema_references(published_items), expected,
                        f"{schema_name}.{field_name}.items reference target",
                    )

    def test_saved_combat_history_references_match_runtime_models(self):
        fields = (
            ("CombatHistoryEntry", CombatHistoryEntry, "result", CombatTurnResult),
            ("CampaignDetail", CampaignDetailResponse, "combat_history", CombatHistoryEntry),
            ("CampaignSession", CampaignSessionResponse, "combat_history", CombatHistoryEntry),
        )
        for schema_name, model, field_name, result_model in fields:
            with self.subTest(schema=schema_name, field=field_name):
                runtime = model.model_json_schema(
                    ref_template="#/components/schemas/{model}"
                )["properties"][field_name]
                published = _property(schema_name, field_name)
                self.assertEqual(_schema_types(published), _schema_types(runtime))
                self.assertEqual(_is_nullable(published), _is_nullable(runtime))
                if field_name == "combat_history":
                    runtime = runtime["items"]
                    published = _mapping(
                        published.get("items"), f"{schema_name}.{field_name}.items"
                    )
                    self.assertEqual(_schema_types(published), _schema_types(runtime))
                    self.assertEqual(_is_nullable(published), _is_nullable(runtime))
                expected = _schema_references(runtime)
                self.assertEqual(
                    expected, {f"#/components/schemas/{result_model.__name__}"},
                    f"Runtime {schema_name}.{field_name} must reference {result_model.__name__}",
                )
                self.assertEqual(
                    _schema_references(published), expected,
                    f"{schema_name}.{field_name} reference target",
                )

    def test_schema_required_declarations_are_lists_of_unique_strings(self):
        # Validate structure separately: set-based parity intentionally ignores
        # ordering, but also hides duplicate names and accepts mapping keys.
        for schema_path, schema in _published_schema_objects():
            with self.subTest(schema=schema_path):
                required = schema.get("required", [])
                label = f"{schema_path}.required"
                self.assertIsInstance(required, list, f"{label} must be a list")
                self.assertTrue(
                    all(isinstance(name, str) for name in required),
                    f"{label} must contain only strings",
                )
                self.assertEqual(
                    len(required), len(set(required)),
                    f"{label} must contain unique strings",
                )

    def test_quest_command_result_shape_matches_runtime_model(self):
        schema_name = "QuestCommandResult"
        runtime = QuestCommandResult.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        published = _schema(schema_name)
        self.assertEqual(
            _property_names(schema_name), _runtime_field_names(QuestCommandResult),
            f"{schema_name}.properties",
        )
        with self.subTest(contract="required inventory"):
            self.assertEqual(
                set(published.get("required", [])), set(runtime.get("required", [])),
                f"{schema_name}.required",
            )
        self.assertEqual(
            published.get("additionalProperties"), runtime.get("additionalProperties"),
            f"{schema_name}.additionalProperties",
        )
        self.assertEqual(
            _schema_types(published) - {"null"}, _schema_types(runtime) - {"null"},
            f"{schema_name}.type",
        )
        self.assertEqual(
            _is_nullable(published), _is_nullable(runtime), f"{schema_name}.nullable",
        )
        for field_name, runtime_field in runtime["properties"].items():
            label = f"{schema_name}.{field_name}"
            with self.subTest(field=field_name, contract="required"):
                self.assertEqual(
                    field_name in published.get("required", []),
                    field_name in runtime.get("required", []),
                    f"{label}.required",
                )
            with self.subTest(field=field_name, contract="type"):
                self.assertEqual(
                    _schema_types(_property(schema_name, field_name)) - {"null"},
                    _schema_types(runtime_field) - {"null"},
                    f"{label}.type",
                )
            with self.subTest(field=field_name, contract="nullable"):
                self.assertEqual(
                    _is_nullable(_property(schema_name, field_name)),
                    _is_nullable(runtime_field),
                    f"{label}.nullable",
                )
        # The public state is deliberately narrower than dict[str, Any].
        # Compare its outer object type/nullability above, not dictionary contents.
        self.assertEqual(
            _schema_references(_property(schema_name, "state")),
            {"#/components/schemas/GameState"},
            f"{schema_name}.state reference target",
        )

    def test_quest_command_result_references_match_runtime_model(self):
        runtime_properties = QuestCommandResult.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["properties"]
        for field_name, field_model in (("quest", QuestState), ("outcome", QuestOutcome)):
            with self.subTest(schema="QuestCommandResult", field=field_name):
                runtime = runtime_properties[field_name]
                published = _property("QuestCommandResult", field_name)
                expected = _schema_references(runtime)
                self.assertEqual(
                    expected, {f"#/components/schemas/{field_model.__name__}"},
                    f"Runtime QuestCommandResult.{field_name} reference target",
                )
                self.assertEqual(
                    _schema_references(published), expected,
                    f"QuestCommandResult.{field_name} reference target",
                )
                self.assertEqual(_schema_types(published), _schema_types(runtime))
                self.assertEqual(_is_nullable(published), _is_nullable(runtime))

    def test_quest_command_route_bindings_match_fastapi(self):
        runtime_spec = app.openapi()
        base_path = SPEC["servers"][0]["url"].rstrip("/")
        # Both POST routes in api.main publish QuestCommandResult directly.
        for path in QUEST_COMMAND_PATHS:
            published = _operation(path, "post")
            runtime = runtime_spec["paths"][f"{base_path}{path}"]["post"]
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
                        runtime_schema,
                        {"$ref": f"#/components/schemas/{QuestCommandResult.__name__}"},
                        f"Runtime {path} successful response binding",
                    )
                    self.assertEqual(
                        published_successes[status]["content"]["application/json"]["schema"],
                        runtime_schema,
                        f"{path} successful response binding",
                    )


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

    def test_campaign_start_component_type_drift_fails_in_both_formats(self):
        for model in (
            CampaignStartOptionsResponse,
            CampaignStartSettingOption,
            CampaignStartRegionOption,
            CampaignStartLocationOption,
        ):
            schema_name = model.__name__
            original = _schema(schema_name)
            runtime = model.model_json_schema()
            self.assertEqual(_schema_types(original), {"object"})
            self.assertEqual(_schema_types(runtime), {"object"})
            self.assertFalse(_is_nullable(original))
            self.assertFalse(_is_nullable(runtime))
            for replacement in ("string", "array", ["object", "null"]):
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, replacement=replacement,
                        compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        spec["components"]["schemas"][schema_name]["type"] = replacement
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["components"]["schemas"][schema_name]
                        nullable = isinstance(replacement, list)
                        self.assertEqual(
                            _schema_types(mutated),
                            {"object", "null"} if nullable else {replacement},
                        )
                        self.assertEqual(_is_nullable(mutated), nullable)
                        for key in ("properties", "required", "additionalProperties"):
                            self.assertEqual(mutated[key], original[key], key)
                        # Restoring only the component type must recover the whole
                        # spec, including collection types, item refs and routes.
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name]["type"] = (
                            original["type"]
                        )
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            for test_name in (
                                "test_campaign_start_item_references_match_runtime_models",
                                "test_character_setup_route_bindings_match_fastapi",
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_campaign_start_schemas_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(
                            len(result.failures), 2 if nullable else 1,
                            result.failures,
                        )
                        self.assertIn(f"{schema_name} type", result.failures[0][1])
                        if nullable:
                            self.assertIn(
                                f"{schema_name} nullable", result.failures[1][1],
                            )

    def test_character_creation_component_type_drift_fails_in_both_formats(self):
        for model in (CharacterCreationOptions, CharacterCreationCatalogResponse):
            schema_name = model.__name__
            original = _schema(schema_name)
            runtime = model.model_json_schema()
            self.assertEqual(_schema_types(original), {"object"})
            self.assertEqual(_schema_types(runtime), {"object"})
            self.assertFalse(_is_nullable(original))
            self.assertFalse(_is_nullable(runtime))
            for replacement in (
                "string", "array", "integer", "number", "boolean", "null",
                ["object", "null"],
            ):
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, replacement=replacement,
                        compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        spec["components"]["schemas"][schema_name]["type"] = replacement
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["components"]["schemas"][schema_name]
                        nullable = replacement == "null" or isinstance(replacement, list)
                        self.assertEqual(
                            _schema_types(mutated),
                            set(replacement) if isinstance(replacement, list) else {replacement},
                        )
                        self.assertEqual(_is_nullable(mutated), nullable)
                        # Preserve all non-type declarations, including required
                        # fields, extra-field policy and nested property references.
                        self.assertEqual(
                            {key: value for key, value in mutated.items() if key != "type"},
                            {key: value for key, value in original.items() if key != "type"},
                        )
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name]["type"] = (
                            original["type"]
                        )
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            for test_name in (
                                "test_campaign_and_session_schema_fields_match_fastapi_models",
                                "test_character_setup_route_bindings_match_fastapi",
                                "test_campaign_start_schemas_match_runtime_models",
                                "test_campaign_start_item_references_match_runtime_models",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_character_creation_component_types_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(
                            len(result.failures), 2 if nullable else 1,
                            result.failures,
                        )
                        for index, contract in enumerate(
                            ("type", "nullable") if nullable else ("type",)
                        ):
                            failed_test, failure = result.failures[index]
                            self.assertIn(f"schema='{schema_name}'", failed_test.id())
                            self.assertIn(f"contract='{contract}'", failed_test.id())
                            self.assertIn(f"{schema_name}.{contract}", failure)

    def test_campaign_start_scalar_type_drift_fails_in_both_formats(self):
        for model, field_names in (
            (CampaignStartLocationOption, ("entity_id", "name")),
            (
                CampaignStartRegionOption,
                ("region_pack_id", "region_id", "name", "epoch_id", "coverage_status"),
            ),
            (CampaignStartSettingOption, ("setting_id", "name")),
        ):
            schema_name = model.__name__
            for field_name in field_names:
                original = _property(schema_name, field_name)
                self.assertEqual(_schema_types(original), {"string"})
                self.assertFalse(_is_nullable(original))
                for replacement in ("integer", ["string", "null"]):
                    for flow_style in (False, True):
                        with self.subTest(
                            schema=schema_name, field=field_name,
                            replacement=replacement, compact=flow_style,
                        ):
                            spec = deepcopy(SPEC)
                            spec["components"]["schemas"][schema_name]["properties"][
                                field_name
                            ]["type"] = replacement
                            parsed = _load_spec(
                                _dump_spec(spec, default_flow_style=flow_style)
                            )
                            self.assertEqual(parsed, spec)
                            mutated = parsed["components"]["schemas"][schema_name][
                                "properties"
                            ][field_name]
                            self.assertEqual(
                                _schema_types(mutated),
                                {"integer"} if replacement == "integer"
                                else {"string", "null"},
                            )
                            self.assertEqual(
                                _is_nullable(mutated), replacement != "integer",
                            )
                            # Restoring only this scalar type proves that routes,
                            # required lists, and nested item refs did not change.
                            restored = deepcopy(parsed)
                            restored["components"]["schemas"][schema_name]["properties"][
                                field_name
                            ]["type"] = original["type"]
                            self.assertEqual(restored, SPEC)
                            with patch.dict(globals(), SPEC=parsed):
                                for test_name in (
                                    "test_campaign_start_item_references_match_runtime_models",
                                    "test_character_setup_route_bindings_match_fastapi",
                                    "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                                ):
                                    unchanged = unittest.TestResult()
                                    ContractParityTests(test_name).run(unchanged)
                                    self.assertTrue(
                                        unchanged.wasSuccessful(),
                                        unchanged.failures + unchanged.errors,
                                    )
                                result = unittest.TestResult()
                                ContractParityTests(
                                    "test_campaign_start_schemas_match_runtime_models"
                                ).run(result)
                            self.assertEqual(result.testsRun, 1)
                            self.assertEqual(result.errors, [], result.errors)
                            self.assertEqual(len(result.failures), 1, result.failures)
                            self.assertIn(
                                f"{schema_name}.{field_name} type",
                                result.failures[0][1],
                            )

    def test_campaign_start_collection_type_drift_fails_in_both_formats(self):
        for model, field_name, item_model in CAMPAIGN_START_ARRAY_FIELDS:
            schema_name = model.__name__
            original = _property(schema_name, field_name)
            self.assertEqual(_schema_types(original), {"array"})
            self.assertFalse(_is_nullable(original))
            self.assertEqual(
                original["items"]["$ref"],
                f"#/components/schemas/{item_model.__name__}",
            )
            for replacement in ("object", "string", ["array", "null"]):
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, field=field_name,
                        replacement=replacement, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        spec["components"]["schemas"][schema_name]["properties"][
                            field_name
                        ]["type"] = replacement
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["components"]["schemas"][schema_name][
                            "properties"
                        ][field_name]
                        self.assertEqual(
                            _schema_types(mutated),
                            {replacement} if isinstance(replacement, str)
                            else {"array", "null"},
                        )
                        self.assertEqual(
                            _is_nullable(mutated), isinstance(replacement, list),
                        )
                        self.assertEqual(mutated["items"], original["items"])
                        self.assertEqual(
                            parsed["components"]["schemas"][schema_name]["required"],
                            _schema(schema_name)["required"],
                        )
                        # Restoring only the collection type must recover the
                        # whole spec, including routes and nested item references.
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name]["properties"][
                            field_name
                        ]["type"] = original["type"]
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            for test_name in (
                                "test_character_setup_route_bindings_match_fastapi",
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_campaign_start_schemas_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(
                            f"{schema_name}.{field_name} type",
                            result.failures[0][1],
                        )

    def test_campaign_start_wrong_item_references_fail_in_both_formats(self):
        for model, field_name, item_model in CAMPAIGN_START_ARRAY_FIELDS:
            schema_name = model.__name__
            original = _property(schema_name, field_name)
            # These are existing object components, not dangling references.
            for wrong_model in (
                CampaignStartSettingOption,
                CampaignStartRegionOption,
                CampaignStartLocationOption,
            ):
                if wrong_model is item_model:
                    continue
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, field=field_name,
                        replacement=wrong_model.__name__, compact=flow_style,
                    ):
                        self.assertIn(wrong_model.__name__, SPEC["components"]["schemas"])
                        spec = deepcopy(SPEC)
                        spec["components"]["schemas"][schema_name]["properties"][
                            field_name
                        ]["items"]["$ref"] = f"#/components/schemas/{wrong_model.__name__}"
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["components"]["schemas"][schema_name][
                            "properties"
                        ][field_name]
                        for before, after in (
                            (original, mutated),
                            (original["items"], mutated["items"]),
                        ):
                            self.assertEqual(_schema_types(after), _schema_types(before))
                            self.assertEqual(_is_nullable(after), _is_nullable(before))
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name]["properties"][
                            field_name
                        ]["items"]["$ref"] = original["items"]["$ref"]
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            for test_name in (
                                "test_campaign_start_schemas_match_runtime_models",
                                "test_character_setup_route_bindings_match_fastapi",
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_campaign_start_item_references_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(
                            f"{schema_name}.{field_name}.items reference target",
                            result.failures[0][1],
                        )

    def test_campaign_start_extra_field_policy_drift_fails_in_both_formats(self):
        for model in (
            CampaignStartOptionsResponse,
            CampaignStartSettingOption,
            CampaignStartRegionOption,
            CampaignStartLocationOption,
        ):
            schema_name = model.__name__
            original = _schema(schema_name)
            self.assertIs(original["additionalProperties"], False)
            self.assertIs(model.model_json_schema()["additionalProperties"], False)
            for operation in ("remove", "allow"):
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, operation=operation, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        target = spec["components"]["schemas"][schema_name]
                        if operation == "remove":
                            del target["additionalProperties"]
                        else:
                            target["additionalProperties"] = True
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["components"]["schemas"][schema_name]
                        if operation == "remove":
                            self.assertNotIn("additionalProperties", mutated)
                        else:
                            self.assertIs(mutated["additionalProperties"], True)
                        # Restoring only the extra-field policy proves scalar
                        # fields, required lists, item refs, and routes are intact.
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name][
                            "additionalProperties"
                        ] = original["additionalProperties"]
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            for test_name in (
                                "test_campaign_start_item_references_match_runtime_models",
                                "test_character_setup_route_bindings_match_fastapi",
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_campaign_start_schemas_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(
                            f"{schema_name}.additionalProperties",
                            result.failures[0][1],
                        )

    def test_campaign_start_missing_properties_fail_in_both_formats(self):
        for model in (
            CampaignStartOptionsResponse,
            CampaignStartSettingOption,
            CampaignStartRegionOption,
            CampaignStartLocationOption,
        ):
            schema_name = model.__name__
            original = _schema(schema_name)
            self.assertEqual(set(original["properties"]), _runtime_field_names(model))
            for field_name in original["properties"]:
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, field=field_name, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        del spec["components"]["schemas"][schema_name]["properties"][
                            field_name
                        ]
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["components"]["schemas"][schema_name]
                        self.assertEqual(
                            mutated["properties"],
                            {
                                name: declaration
                                for name, declaration in original["properties"].items()
                                if name != field_name
                            },
                        )
                        self.assertEqual(mutated["required"], original["required"])
                        self.assertEqual(parsed["paths"], SPEC["paths"])
                        # Restoring just the removed property proves every other
                        # declaration, required list and route binding is intact.
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name]["properties"][
                            field_name
                        ] = deepcopy(original["properties"][field_name])
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            for test_name in (
                                "test_character_setup_route_bindings_match_fastapi",
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertEqual(unchanged.testsRun, 1)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_campaign_start_schemas_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        # The name-set comparison must fail independently of
                        # the subsequent lookup of the missing declaration.
                        self.assertEqual(len(result.failures), 2, result.failures)
                        comparison, lookup = result.failures
                        self.assertIn(f"schema='{schema_name}'", comparison[0].id())
                        self.assertNotIn("field=", comparison[0].id())
                        self.assertIn(
                            "self.assertEqual(_property_names(schema_name), _runtime_field_names(model))",
                            comparison[1],
                        )
                        self.assertIn(
                            "Items in the second set but not the first:", comparison[1],
                        )
                        self.assertIn(repr(field_name), comparison[1])
                        self.assertIn(f"field='{field_name}'", lookup[0].id())
                        self.assertIn(
                            f"OpenAPI property {schema_name}.{field_name} was not found",
                            lookup[1],
                        )

    def test_campaign_start_unexpected_properties_fail_in_both_formats(self):
        field_name = "unexpected"
        declaration = {"type": "string"}
        for model in (
            CampaignStartOptionsResponse,
            CampaignStartSettingOption,
            CampaignStartRegionOption,
            CampaignStartLocationOption,
        ):
            schema_name = model.__name__
            original = _schema(schema_name)
            self.assertEqual(set(original["properties"]), _runtime_field_names(model))
            self.assertNotIn(field_name, original["properties"])
            self.assertNotIn(field_name, original["required"])
            for flow_style in (False, True):
                with self.subTest(schema=schema_name, compact=flow_style):
                    spec = deepcopy(SPEC)
                    spec["components"]["schemas"][schema_name]["properties"][
                        field_name
                    ] = deepcopy(declaration)
                    parsed = _load_spec(
                        _dump_spec(spec, default_flow_style=flow_style)
                    )
                    self.assertEqual(parsed, spec)
                    mutated = parsed["components"]["schemas"][schema_name]
                    self.assertEqual(
                        mutated["properties"],
                        {**original["properties"], field_name: declaration},
                    )
                    self.assertEqual(mutated["required"], original["required"])
                    self.assertNotIn(field_name, mutated["required"])
                    self.assertEqual(
                        mutated["additionalProperties"], original["additionalProperties"],
                    )
                    self.assertEqual(parsed["paths"], SPEC["paths"])
                    # Removing only the extra declaration proves all original
                    # properties, required lists, policies and routes are intact.
                    restored = deepcopy(parsed)
                    del restored["components"]["schemas"][schema_name]["properties"][
                        field_name
                    ]
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=parsed):
                        for test_name in (
                            "test_campaign_start_item_references_match_runtime_models",
                            "test_character_setup_route_bindings_match_fastapi",
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                        ):
                            unchanged = unittest.TestResult()
                            ContractParityTests(test_name).run(unchanged)
                            self.assertEqual(unchanged.testsRun, 1)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                        result = unittest.TestResult()
                        ContractParityTests(
                            "test_campaign_start_schemas_match_runtime_models"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    comparison, failure = result.failures[0]
                    self.assertIn(f"schema='{schema_name}'", comparison.id())
                    self.assertNotIn("field=", comparison.id())
                    self.assertIn(
                        "self.assertEqual(_property_names(schema_name), _runtime_field_names(model))",
                        failure,
                    )
                    self.assertIn("Items in the first set but not the second:", failure)
                    self.assertIn(repr(field_name), failure)

    def test_campaign_start_required_field_drift_fails_in_both_formats(self):
        for model in (
            CampaignStartOptionsResponse,
            CampaignStartSettingOption,
            CampaignStartRegionOption,
            CampaignStartLocationOption,
        ):
            schema_name = model.__name__
            original = _schema(schema_name)
            replacements = [None, original["required"] + ["unexpected"]]
            replacements.extend(
                [field for field in original["required"] if field != removed]
                for removed in original["required"]
            )
            for replacement in replacements:
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, required=replacement, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        target = spec["components"]["schemas"][schema_name]
                        if replacement is None:
                            del target["required"]
                        else:
                            target["required"] = replacement
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name]["required"] = (
                            original["required"]
                        )
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_campaign_start_schemas_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(f"{schema_name}.required", result.failures[0][1])

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
                        text = _dump_spec(spec, default_flow_style=flow_style)
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
                text = _dump_spec(SPEC, default_flow_style=flow_style, sort_keys=False)
                spec = _load_spec(text)
                self.assertEqual(spec, SPEC)
                result = self._parity_result(spec)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
                results.append(result.testsRun)
        self.assertEqual(results[0], results[1])
        self.assertGreater(results[0], 0)

    def test_safe_yaml_backends_preserve_full_contract_and_scalar_types(self):
        backends = [(yaml.SafeLoader, yaml.SafeDumper)]
        if hasattr(yaml, "CSafeLoader") and hasattr(yaml, "CSafeDumper"):
            backends.append((yaml.CSafeLoader, yaml.CSafeDumper))
        for loader, dumper in backends:
            class ContractLoader(_DuplicateKeyLoaderMixin, loader):
                pass

            for flow_style in (False, True):
                with self.subTest(backend=loader.__name__, compact=flow_style):
                    spec = deepcopy(SPEC)
                    with patch.dict(
                        globals(), _ContractLoader=ContractLoader, _SAFE_DUMPER=dumper,
                    ):
                        text = _dump_spec(spec, default_flow_style=flow_style)
                        parsed = _load_spec(text)
                        fixture = _load_spec(self.COMPACT_FIXTURE)
                    self.assertEqual(parsed, spec)
                    self.assertEqual(fixture, _load_spec(self.BLOCK_FIXTURE))
                    values = fixture["components"]["schemas"]["Example"]["properties"]
                    self.assertIs(values["message"]["enum"][1].__class__, str)
                    self.assertIs(values["message"]["enum"][2].__class__, int)
                    self.assertIs(
                        fixture["components"]["schemas"]["Example"]["additionalProperties"],
                        False,
                    )
                    # Neither the dumper nor loader may share mutable contract data.
                    parsed["components"]["schemas"].clear()
                    self.assertEqual(spec, SPEC)

    def test_safe_yaml_backends_reject_duplicates_malformed_and_unsafe_tags(self):
        loaders = [yaml.SafeLoader]
        if hasattr(yaml, "CSafeLoader"):
            loaders.append(yaml.CSafeLoader)
        for loader in loaders:
            class ContractLoader(_DuplicateKeyLoaderMixin, loader):
                pass

            for text, diagnostic in (
                ("{paths: {}, paths: {}}", "duplicate mapping keys"),
                ("components:\n  schemas: {}\n  schemas: {}", "duplicate mapping keys"),
                ("components: {schemas: [", "Malformed OpenAPI YAML"),
                ("!!python/object/apply:builtins.dict []", "Malformed OpenAPI YAML"),
                ("[]", "document must be a mapping"),
                ("", "document must be a mapping"),
            ):
                with self.subTest(backend=loader.__name__, text=text):
                    with patch.dict(globals(), _ContractLoader=ContractLoader):
                        with self.assertRaisesRegex(AssertionError, diagnostic):
                            _load_spec(text)
        dumpers = [yaml.SafeDumper]
        if hasattr(yaml, "CSafeDumper"):
            dumpers.append(yaml.CSafeDumper)
        for dumper in dumpers:
            with self.subTest(backend=dumper.__name__):
                with patch.dict(globals(), _SAFE_DUMPER=dumper):
                    with self.assertRaises(yaml.representer.RepresenterError):
                        _dump_spec({"unsafe": object()}, default_flow_style=False)

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
                    text = _dump_spec(spec, default_flow_style=flow_style)
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
                    text = _dump_spec(spec, default_flow_style=flow_style)
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
                    text = _dump_spec(spec, default_flow_style=flow_style)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=_load_spec(text)):
                        ContractParityTests(
                            "test_nested_death_schemas_match_runtime_models"
                        ).run(result)
                    self.assertTrue(result.failures, result.errors)
                    self.assertFalse(result.errors, result.errors)

    def test_quest_objective_field_mutations_fail_in_both_formats(self):
        mutations = []
        for _, model, schema_name in QUEST_OBJECTIVE_LIST_MODELS:
            runtime = model.model_json_schema()
            required = _schema(schema_name)["required"]
            mutations.extend([
                (schema_name, ("required",), None, f"{schema_name}.required"),
                (schema_name, ("properties", "unexpected"), {"type": "boolean"},
                 f"{schema_name}.properties"),
                (schema_name, ("additionalProperties",), True,
                 f"{schema_name}.additionalProperties"),
            ])
            for field_name, runtime_field in runtime["properties"].items():
                label = f"{schema_name}.{field_name}"
                field_path = ("properties", field_name)
                mutations.extend([
                    (schema_name, ("required",),
                     [name for name in required if name != field_name],
                     f"{schema_name}.required"),
                    (schema_name, field_path, None, f"{schema_name}.properties"),
                    (schema_name, field_path + ("type",), "boolean", f"{label} type"),
                    (schema_name, field_path + ("type",),
                     [runtime_field["type"], "null"], f"{label} type"),
                ])
                if runtime_field["type"] == "integer":
                    mutations.append((
                        schema_name, field_path + ("type",), "number", f"{label} type",
                    ))
                enum = runtime_field.get("enum")
                if enum is not None:
                    for replacement in (None, enum[:-1], enum + ["unexpected"]):
                        mutations.append((
                            schema_name, field_path + ("enum",),
                            replacement, f"{label} enum",
                        ))
                for constraint in ("minimum", "maximum", "maxLength"):
                    if constraint in runtime_field:
                        for replacement in (None, runtime_field[constraint] + 1):
                            mutations.append((
                                schema_name, field_path + (constraint,),
                                replacement, f"{label}.{constraint}",
                            ))
                if (schema_name, field_name) in QUEST_OBJECTIVE_MIN_LENGTH_EXCEPTIONS:
                    mutations.append((
                        schema_name, field_path + ("minLength",), 1,
                        f"{label}.minLength",
                    ))

        for schema_name, path, replacement, diagnostic in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    schema=schema_name, path=path, replacement=replacement,
                    compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = replacement
                    text = _dump_spec(spec, default_flow_style=flow_style)
                    parsed = _load_spec(text)
                    self.assertEqual(parsed, spec)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        # Item-reference coverage cannot detect component drift.
                        unchanged = unittest.TestResult()
                        ContractParityTests(
                            "test_quest_objective_item_references_match_runtime_models"
                        ).run(unchanged)
                        self.assertTrue(
                            unchanged.wasSuccessful(), unchanged.failures + unchanged.errors
                        )
                        ContractParityTests(
                            "test_quest_objective_schemas_match_runtime_models"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertTrue(result.failures, f"Undetected drift: {diagnostic}")
                    self.assertIn(
                        diagnostic, "\n".join(failure for _, failure in result.failures)
                    )

    def test_quest_parent_field_drift_fails_in_both_formats(self):
        mutations = []
        for model in (QuestOffer, QuestState):
            schema_name = model.__name__
            required = _schema(schema_name)["required"]
            mutations.extend([
                (schema_name, ("required",), None, f"{schema_name}.required"),
                (schema_name, ("required",), required + ["unexpected"],
                 f"{schema_name}.required"),
                (schema_name, ("properties", "unexpected"), {"type": "boolean"},
                 f"{schema_name}.properties"),
                (schema_name, ("type",), "array", f"{schema_name} type"),
                (schema_name, ("additionalProperties",), True,
                 f"{schema_name}.additionalProperties"),
                (schema_name, ("additionalProperties",), None,
                 f"{schema_name}.additionalProperties"),
            ])
            for field_name in model.model_fields:
                label = f"{schema_name}.{field_name}"
                field_path = ("properties", field_name)
                published = _property(schema_name, field_name)
                mutations.extend([
                    (schema_name, ("required",),
                     [name for name in required if name != field_name],
                     f"{schema_name}.required"),
                    (schema_name, field_path, None, f"{schema_name}.properties"),
                    (schema_name, field_path + ("type",), "integer", f"{label} type"),
                    (schema_name, field_path + ("default",), "unexpected",
                     f"{label} default"),
                ])
                wrong_nullable_type = (
                    "string" if field_name == "giver_npc_id"
                    else [published["type"], "null"]
                )
                mutations.append((
                    schema_name, field_path + ("type",), wrong_nullable_type,
                    f"{label} type",
                ))
                for constraint in ("minLength", "maxLength"):
                    original = published.get(constraint)
                    replacements = (1,) if original is None else (None, original + 1)
                    for replacement in replacements:
                        mutations.append((
                            schema_name, field_path + (constraint,), replacement,
                            f"{label}.{constraint}",
                        ))
                enum = published.get("enum")
                replacements = (
                    [None, enum[:-1], enum + ["offered"]]
                    if enum is not None else [["unexpected"]]
                )
                for replacement in replacements:
                    mutations.append((
                        schema_name, field_path + ("enum",), replacement,
                        f"{label} enum",
                    ))
        for schema_name, path, replacement, diagnostic in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    schema=schema_name, path=path, replacement=replacement,
                    compact=flow_style,
                ):
                    # Each mutation starts from the real unmodified contract.
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        target.pop(path[-1], None)
                    else:
                        target[path[-1]] = deepcopy(replacement)
                    loaded = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style, sort_keys=False,
                    ))
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=loaded):
                        ContractParityTests(
                            "test_quest_parent_schemas_match_runtime_models"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertTrue(result.failures, f"Undetected drift: {diagnostic}")
                    self.assertIn(
                        diagnostic, "\n".join(failure for _, failure in result.failures)
                    )

    def test_quest_objective_wrong_item_references_fail_in_both_formats(self):
        for model, _, published_item_name in QUEST_OBJECTIVE_LIST_MODELS:
            schema_name = model.__name__
            original = _property(schema_name, "objectives")
            wrong_models = (
                "QuestObjectiveOffer" if published_item_name == "QuestObjective"
                else "QuestObjective",
                "QuestOutcome",
                "GameSession",
            )
            for wrong_model in wrong_models:
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, replacement=wrong_model,
                        compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        field = spec["components"]["schemas"][schema_name][
                            "properties"
                        ]["objectives"]
                        field["items"]["$ref"] = f"#/components/schemas/{wrong_model}"
                        text = _dump_spec(spec, default_flow_style=flow_style)
                        parsed = _load_spec(text)
                        self.assertEqual(parsed, spec)
                        parsed_field = parsed["components"]["schemas"][schema_name][
                            "properties"
                        ]["objectives"]
                        self.assertEqual(_schema_types(parsed_field), {"array"})
                        self.assertEqual(
                            _schema_types(parsed_field), _schema_types(original)
                        )
                        self.assertEqual(
                            _is_nullable(parsed_field), _is_nullable(original)
                        )
                        self.assertEqual(
                            _schema_types(parsed_field["items"]),
                            _schema_types(original["items"]),
                        )
                        self.assertEqual(
                            _is_nullable(parsed_field["items"]),
                            _is_nullable(original["items"]),
                        )
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name][
                            "properties"
                        ]["objectives"]["items"]["$ref"] = original["items"]["$ref"]
                        self.assertEqual(restored, SPEC)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=parsed):
                            ContractParityTests(
                                "test_quest_objective_item_references_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        failed_test, failure = result.failures[0]
                        self.assertIn(f"schema='{schema_name}'", failed_test.id())
                        self.assertIn(
                            f"{schema_name}.objectives.items reference target", failure
                        )

    def test_required_declaration_structure_drift_fails_in_both_formats(self):
        schema_name = "QuestCommandResult"
        original = deepcopy(_schema(schema_name)["required"])
        structure_test = "test_schema_required_declarations_are_lists_of_unique_strings"
        shape_test = "test_quest_command_result_shape_matches_runtime_model"
        mutations = (
            ("duplicate", original + [original[0]], "must contain unique strings", True),
            ("mapping", dict.fromkeys(original), "must be a list", True),
            ("scalar", original[0], "must be a list", False),
            ("null", None, "must be a list", False),
            ("integer", original + [1], "must contain only strings", False),
            ("boolean", original + [True], "must contain only strings", False),
            ("null item", original + [None], "must contain only strings", False),
            ("mapping item", original + [{}], "must contain only strings", False),
            ("list item", original + [[]], "must contain only strings", False),
        )
        for mutation, replacement, diagnostic, same_membership in mutations:
            for flow_style in (False, True):
                with self.subTest(mutation=mutation, compact=flow_style):
                    spec = deepcopy(SPEC)
                    spec["components"]["schemas"][schema_name]["required"] = (
                        deepcopy(replacement)
                    )
                    parsed = _load_spec(
                        _dump_spec(spec, default_flow_style=flow_style)
                    )
                    self.assertEqual(parsed, spec)
                    # Restoring only required proves properties, references,
                    # routes, and all other declarations remain unchanged.
                    restored = deepcopy(parsed)
                    restored["components"]["schemas"][schema_name]["required"] = (
                        deepcopy(original)
                    )
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=restored):
                        baseline = unittest.TestResult()
                        ContractParityTests(structure_test).run(baseline)
                        ContractParityTests(shape_test).run(baseline)
                    self.assertEqual(baseline.testsRun, 2)
                    self.assertTrue(
                        baseline.wasSuccessful(), baseline.failures + baseline.errors,
                    )
                    with patch.dict(globals(), SPEC=parsed):
                        result = unittest.TestResult()
                        ContractParityTests(structure_test).run(result)
                        if same_membership:
                            # These are the regressions that normalization
                            # previously hid; membership parity still passes.
                            inventory = unittest.TestResult()
                            ContractParityTests(shape_test).run(inventory)
                            self.assertTrue(
                                inventory.wasSuccessful(),
                                inventory.failures + inventory.errors,
                            )
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    self.assertIn(
                        f"{schema_name}.required {diagnostic}", result.failures[0][1],
                    )
        self.assertEqual(_schema(schema_name)["required"], original)

    def test_unique_required_lists_accept_reordering_in_both_formats(self):
        for flow_style in (False, True):
            with self.subTest(compact=flow_style):
                spec = deepcopy(SPEC)
                spec["components"]["schemas"]["QuestCommandResult"]["required"].reverse()
                parsed = _load_spec(
                    _dump_spec(spec, default_flow_style=flow_style)
                )
                self.assertEqual(parsed, spec)
                result = unittest.TestResult()
                with patch.dict(globals(), SPEC=parsed):
                    ContractParityTests(
                        "test_schema_required_declarations_are_lists_of_unique_strings"
                    ).run(result)
                    ContractParityTests(
                        "test_quest_command_result_shape_matches_runtime_model"
                    ).run(result)
                self.assertEqual(result.testsRun, 2)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)

    def _nested_required_fixture(self):
        spec = deepcopy(SPEC)
        object_schema = {
            "type": "object",
            "properties": {"first": {"type": "string"}, "second": {"type": "string"}},
            "required": ["first", "second"],
        }
        component_path = ("components", "schemas", "NestedRequiredFixture")
        spec["components"]["schemas"]["NestedRequiredFixture"] = {
            "type": "object",
            "properties": {
                "object": deepcopy(object_schema),
                "array": {"type": "array", "items": deepcopy(object_schema)},
                "dictionary": {
                    "type": "object", "additionalProperties": deepcopy(object_schema),
                },
                "free_dictionary": {"type": "object", "additionalProperties": True},
                "closed_dictionary": {"type": "object", "additionalProperties": False},
                "combined": {
                    keyword: [deepcopy(object_schema)]
                    for keyword in ("anyOf", "allOf", "oneOf")
                },
                "deep": {
                    "type": "array",
                    "items": {"anyOf": [{
                        "allOf": [{"oneOf": [{
                            "type": "object",
                            "properties": {"child": deepcopy(object_schema)},
                        }]}],
                    }]},
                },
            },
        }
        spec["paths"]["/nested-required-fixture"] = {
            "parameters": [{
                "name": "path-filter", "in": "query", "schema": deepcopy(object_schema),
            }],
            "post": {
                "parameters": [{
                    "name": "operation-filter", "in": "query",
                    "schema": deepcopy(object_schema),
                }, {
                    "name": "content-filter", "in": "query",
                    "content": {"application/json": {"schema": deepcopy(object_schema)}},
                }],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": deepcopy(object_schema)}},
                },
                "responses": {
                    "200": {
                        "description": "Fixture only",
                        "content": {"application/json": {
                            "schema": {"type": "array", "items": deepcopy(object_schema)},
                        }},
                    },
                },
            },
        }
        targets = [
            (component_path + ("properties", "object"),
             "NestedRequiredFixture.properties.object"),
            (component_path + ("properties", "array", "items"),
             "NestedRequiredFixture.properties.array.items"),
            (component_path + ("properties", "dictionary", "additionalProperties"),
             "NestedRequiredFixture.properties.dictionary.additionalProperties"),
            (("paths", "/nested-required-fixture", "parameters", 0, "schema"),
             "paths./nested-required-fixture.parameters[0].schema"),
            (("paths", "/nested-required-fixture", "post", "parameters", 0, "schema"),
             "paths./nested-required-fixture.post.parameters[0].schema"),
            (("paths", "/nested-required-fixture", "post", "parameters", 1,
              "content", "application/json", "schema"),
             "paths./nested-required-fixture.post.parameters[1].content"
             ".application/json.schema"),
        ]
        targets.extend(
            (component_path + ("properties", "combined", keyword, 0),
             f"NestedRequiredFixture.properties.combined.{keyword}[0]")
            for keyword in ("anyOf", "allOf", "oneOf")
        )
        targets.extend([
            (component_path + (
                "properties", "deep", "items", "anyOf", 0, "allOf", 0,
                "oneOf", 0, "properties", "child",
            ), "NestedRequiredFixture.properties.deep.items.anyOf[0].allOf[0]"
               ".oneOf[0].properties.child"),
            (("paths", "/nested-required-fixture", "post", "requestBody", "content",
              "application/json", "schema"),
             "paths./nested-required-fixture.post.requestBody.content.application/json.schema"),
            (("paths", "/nested-required-fixture", "post", "responses", "200", "content",
              "application/json", "schema", "items"),
             "paths./nested-required-fixture.post.responses.200.content.application/json"
             ".schema.items"),
        ])
        return spec, targets

    def test_nested_required_structure_drift_fails_in_both_formats(self):
        baseline, targets = self._nested_required_fixture()
        mutations = (
            ("duplicate", ["first", "second", "first"], "must contain unique strings"),
            ("same-key mapping", {"first": None, "second": None}, "must be a list"),
            ("scalar", "first", "must be a list"),
            ("null", None, "must be a list"),
            ("integer", ["first", "second", 1], "must contain only strings"),
            ("boolean", ["first", "second", True], "must contain only strings"),
            ("null item", ["first", "second", None], "must contain only strings"),
            ("mapping item", ["first", "second", {}], "must contain only strings"),
            ("list item", ["first", "second", []], "must contain only strings"),
        )
        for path, label in targets:
            for mutation, replacement, diagnostic in mutations:
                for flow_style in (False, True):
                    with self.subTest(path=label, mutation=mutation, compact=flow_style):
                        spec = deepcopy(baseline)
                        target = spec
                        for key in path:
                            target = target[key]
                        target["required"] = deepcopy(replacement)
                        parsed = _load_spec(yaml.safe_dump(
                            spec, default_flow_style=flow_style,
                        ))
                        self.assertEqual(parsed, spec)
                        restored = deepcopy(parsed)
                        restored_target = restored
                        for key in path:
                            restored_target = restored_target[key]
                        restored_target["required"] = ["first", "second"]
                        self.assertEqual(restored, baseline)
                        if mutation in ("duplicate", "same-key mapping"):
                            # Both corruptions preserve membership; only the
                            # structural check should reject them.
                            self.assertEqual(set(replacement), {"first", "second"})
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=parsed):
                            ContractParityTests(
                                "test_schema_required_declarations_are_lists_of_unique_strings"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(
                            f"{label}.required {diagnostic}", result.failures[0][1],
                        )

    def test_nested_required_omission_and_reordering_are_valid_in_both_formats(self):
        baseline, targets = self._nested_required_fixture()
        for mutation in ("omitted", "reordered"):
            for flow_style in (False, True):
                with self.subTest(mutation=mutation, compact=flow_style):
                    spec = deepcopy(baseline)
                    for path, _ in targets:
                        target = spec
                        for key in path:
                            target = target[key]
                        if mutation == "omitted":
                            del target["required"]
                        else:
                            target["required"].reverse()
                    parsed = _load_spec(yaml.safe_dump(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(parsed, spec)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        ContractParityTests(
                            "test_schema_required_declarations_are_lists_of_unique_strings"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertTrue(result.wasSuccessful(), result.failures + result.errors)

    def test_required_structure_ignores_examples_and_metadata_in_both_formats(self):
        baseline, targets = self._nested_required_fixture()
        decoy = {
            "required": ["first", "first"],
            "properties": {"child": {"required": {"first": None}}},
            "items": {"required": [False]},
            "anyOf": [{"required": None}],
            "allOf": [{"required": [{}]}],
            "oneOf": [{"required": [[]]}],
        }
        for flow_style in (False, True):
            with self.subTest(compact=flow_style):
                spec = deepcopy(baseline)
                for path, _ in targets:
                    target = spec
                    for key in path:
                        target = target[key]
                    for keyword in ("example", "examples", "default", "x-metadata"):
                        target[keyword] = deepcopy(decoy)
                operation = spec["paths"]["/nested-required-fixture"]["post"]
                operation["x-metadata"] = deepcopy(decoy)
                for parameter in (
                    *spec["paths"]["/nested-required-fixture"]["parameters"],
                    *operation["parameters"],
                ):
                    parameter["example"] = deepcopy(decoy)
                    parameter["examples"] = {"payload": {"value": deepcopy(decoy)}}
                    parameter["required"] = False
                operation["requestBody"]["content"]["application/json"]["example"] = (
                    deepcopy(decoy)
                )
                operation["responses"]["200"]["content"]["application/json"]["examples"] = {
                    "payload": {"value": deepcopy(decoy)},
                }
                spec["info"]["x-metadata"] = deepcopy(decoy)
                parsed = _load_spec(yaml.safe_dump(spec, default_flow_style=flow_style))
                self.assertEqual(parsed, spec)
                result = unittest.TestResult()
                with patch.dict(globals(), SPEC=parsed):
                    ContractParityTests(
                        "test_schema_required_declarations_are_lists_of_unique_strings"
                    ).run(result)
                self.assertEqual(result.testsRun, 1)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)

    def test_quest_command_result_shape_mutations_fail_in_both_formats(self):
        schema_name = "QuestCommandResult"
        original = _schema(schema_name)
        mutations = [
            (("required",), None, f"{schema_name}.required"),
            (("properties", "unexpected"), {"type": "boolean"},
             f"{schema_name}.properties"),
            (("additionalProperties",), None, f"{schema_name}.additionalProperties"),
            (("additionalProperties",), True, f"{schema_name}.additionalProperties"),
            (("type",), "array", f"{schema_name}.type"),
            (("type",), ["object", "null"], f"{schema_name}.nullable"),
            (("properties", "state", "$ref"), "#/components/schemas/QuestState",
             f"{schema_name}.state reference target"),
        ]
        for field_name, original_field in original["properties"].items():
            label = f"{schema_name}.{field_name}"
            # Preserve references and metadata when changing only nullability.
            nullable_field = (
                deepcopy(original_field["anyOf"][0])
                if _is_nullable(original_field)
                else {"anyOf": [deepcopy(original_field), {"type": "null"}]}
            )
            mutations.extend([
                (("properties", field_name), None, f"{schema_name}.properties"),
                (("required",),
                 [name for name in original["required"] if name != field_name],
                 f"{label}.required"),
                (("properties", field_name), {"type": "boolean"}, f"{label}.type"),
                (("properties", field_name), nullable_field, f"{label}.nullable"),
            ])

        for path, replacement, diagnostic in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    path=path, replacement=replacement, compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = deepcopy(replacement)
                    parsed = _load_spec(
                        _dump_spec(spec, default_flow_style=flow_style)
                    )
                    self.assertEqual(parsed, spec)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        ContractParityTests(
                            "test_quest_command_result_shape_matches_runtime_model"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertTrue(result.failures, f"Undetected drift: {diagnostic}")
                    self.assertIn(
                        diagnostic, "\n".join(failure for _, failure in result.failures)
                    )
        self.assertEqual(_schema(schema_name), original)

    def test_quest_command_wrong_response_bindings_fail_in_both_formats(self):
        for path in QUEST_COMMAND_PATHS:
            original = _operation(path, "post")["responses"]["200"][
                "content"
            ]["application/json"]["schema"]
            for wrong_model in ("QuestState", "SpeciesTraitCommandResult"):
                for flow_style in (False, True):
                    with self.subTest(
                        path=path, replacement=wrong_model, compact=flow_style,
                    ):
                        self.assertIn(wrong_model, SPEC["components"]["schemas"])
                        spec = deepcopy(SPEC)
                        schema = spec["paths"][path]["post"]["responses"]["200"][
                            "content"
                        ]["application/json"]["schema"]
                        schema["$ref"] = f"#/components/schemas/{wrong_model}"
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["paths"][path]["post"]["responses"]["200"][
                            "content"
                        ]["application/json"]["schema"]
                        self.assertEqual(_schema_types(mutated), _schema_types(original))
                        self.assertEqual(_is_nullable(mutated), _is_nullable(original))
                        # Restoring only the reference recovers all inventories,
                        # component definitions, statuses and operation details.
                        restored = deepcopy(parsed)
                        restored["paths"][path]["post"]["responses"]["200"][
                            "content"
                        ]["application/json"]["schema"]["$ref"] = original["$ref"]
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            unchanged = unittest.TestResult()
                            ContractParityTests(
                                "test_quest_command_result_references_match_runtime_model"
                            ).run(unchanged)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_quest_command_route_bindings_match_fastapi"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        failed_test, failure = result.failures[0]
                        self.assertIn(f"path='{path}'", failed_test.id())
                        self.assertIn("binding='response'", failed_test.id())
                        self.assertIn(f"{path} successful response binding", failure)

    def test_quest_command_wrong_result_references_fail_in_both_formats(self):
        for field_name, wrong_models in (
            ("quest", ("QuestOffer", "QuestOutcome")),
            ("outcome", ("QuestState", "QuestOffer")),
        ):
            original = _property("QuestCommandResult", field_name)
            original_target = (
                original if field_name == "quest" else original["anyOf"][0]
            )
            for wrong_model in wrong_models:
                for flow_style in (False, True):
                    with self.subTest(
                        field=field_name, replacement=wrong_model, compact=flow_style,
                    ):
                        self.assertIn(wrong_model, SPEC["components"]["schemas"])
                        spec = deepcopy(SPEC)
                        field = spec["components"]["schemas"]["QuestCommandResult"][
                            "properties"
                        ][field_name]
                        target = field if field_name == "quest" else field["anyOf"][0]
                        target["$ref"] = f"#/components/schemas/{wrong_model}"
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["components"]["schemas"]["QuestCommandResult"][
                            "properties"
                        ][field_name]
                        self.assertEqual(_schema_types(mutated), _schema_types(original))
                        self.assertEqual(_is_nullable(mutated), _is_nullable(original))
                        # In particular, outcome's null branch stays intact.
                        restored = deepcopy(parsed)
                        restored_field = restored["components"]["schemas"][
                            "QuestCommandResult"
                        ]["properties"][field_name]
                        restored_target = (
                            restored_field if field_name == "quest"
                            else restored_field["anyOf"][0]
                        )
                        restored_target["$ref"] = original_target["$ref"]
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            unchanged = unittest.TestResult()
                            ContractParityTests(
                                "test_quest_command_route_bindings_match_fastapi"
                            ).run(unchanged)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_quest_command_result_references_match_runtime_model"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        failed_test, failure = result.failures[0]
                        self.assertIn(f"field='{field_name}'", failed_test.id())
                        self.assertIn(
                            f"QuestCommandResult.{field_name} reference target", failure,
                        )

    def test_quest_outcome_component_mutations_fail_in_both_formats(self):
        original = _schema("QuestOutcome")
        mutations = [
            (("type",), "string", "QuestOutcome type"),
            (("type",), ["object", "null"], "QuestOutcome type"),
            (("additionalProperties",), True, "QuestOutcome.additionalProperties"),
            (("properties", "unexpected"), {"type": "string"}, "QuestOutcome.properties"),
            (("properties", "transition", "enum"),
             ["accepted", "objective_progress", "objective_completed", "completed"],
             "QuestOutcome.transition enum"),
            (("properties", "transition", "enum"),
             original["properties"]["transition"]["enum"] + ["failed"],
             "QuestOutcome.transition enum"),
            (("properties", "objective_id", "type"), "string", "QuestOutcome.objective_id type"),
            (("properties", "objective_id", "type"), ["integer", "null"],
             "QuestOutcome.objective_id type"),
            (("properties", "objective_id", "default"), None, "QuestOutcome.objective_id.default"),
        ]
        for field_name, field_schema in original["properties"].items():
            mutations.extend([
                (("required",),
                 [name for name in original["required"] if name != field_name],
                 "QuestOutcome.required"),
                (("properties", field_name), None, "QuestOutcome.properties"),
                (("properties", field_name, "type"),
                 "string" if field_name == "turn_index" else "integer",
                 f"QuestOutcome.{field_name} type"),
            ])
            if field_name != "objective_id":
                mutations.append((
                    ("properties", field_name, "type"),
                    [field_schema["type"], "null"], f"QuestOutcome.{field_name} type",
                ))
            if "maxLength" in field_schema:
                for replacement in (None, field_schema["maxLength"] + 1):
                    mutations.append((
                        ("properties", field_name, "maxLength"),
                        replacement, f"QuestOutcome.{field_name}.maxLength",
                    ))
        for replacement in (None, -1, 1):
            mutations.append((
                ("properties", "turn_index", "minimum"),
                replacement, "QuestOutcome.turn_index.minimum",
            ))
        mutations.extend([
            (("properties", "transition", "enum"), None, "QuestOutcome.transition enum"),
            (("properties", "event_id", "minLength"), 1, "QuestOutcome.event_id.minLength"),
            (("properties", "turn_index", "default"), 0, "QuestOutcome.turn_index.default"),
        ])
        for path, replacement, label in mutations:
            for flow_style in (False, True):
                with self.subTest(path=path, replacement=replacement, compact=flow_style):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"]["QuestOutcome"]
                    for key in path[:-1]:
                        target = target[key]
                    # None removes a declaration except for the explicit
                    # default:null mutation, which must preserve the key.
                    if replacement is None and path[-1] != "default":
                        target.pop(path[-1])
                    else:
                        target[path[-1]] = deepcopy(replacement)
                    parsed = _load_spec(_dump_spec(spec, default_flow_style=flow_style))
                    self.assertEqual(parsed, spec)
                    restored = deepcopy(parsed)
                    restored["components"]["schemas"]["QuestOutcome"] = deepcopy(original)
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=parsed):
                        result = unittest.TestResult()
                        ContractParityTests(
                            "test_quest_outcome_schema_matches_runtime_model"
                        ).run(result)
                        # Component changes do not alter collection targets or
                        # command route bindings; their checks stay independent.
                        unchanged = unittest.TestResult()
                        for test_name in (
                            "test_turn_quest_outcome_item_references_match_runtime_model",
                            "test_quest_command_result_references_match_runtime_model",
                            "test_quest_command_route_bindings_match_fastapi",
                        ):
                            ContractParityTests(test_name).run(unchanged)
                    self.assertTrue(
                        unchanged.wasSuccessful(), unchanged.failures + unchanged.errors,
                    )
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertTrue(result.failures, f"Mutation was not detected: {path}")
                    self.assertTrue(
                        any(label in failure for _, failure in result.failures),
                        result.failures,
                    )

    def test_turn_quest_outcome_wrong_item_references_fail_in_both_formats(self):
        original = _property("GameTurnResult", "quest_outcomes")
        for wrong_model in ("GameSession", "CombatTurnResult", "QuestObjective"):
            for flow_style in (False, True):
                with self.subTest(replacement=wrong_model, compact=flow_style):
                    spec = deepcopy(SPEC)
                    field = spec["components"]["schemas"]["GameTurnResult"][
                        "properties"
                    ]["quest_outcomes"]
                    field["items"]["$ref"] = f"#/components/schemas/{wrong_model}"
                    self.assertEqual(_schema_types(field), _schema_types(original))
                    self.assertEqual(_is_nullable(field), _is_nullable(original))
                    self.assertEqual(
                        _schema_types(field["items"]), _schema_types(original["items"])
                    )
                    self.assertEqual(
                        _is_nullable(field["items"]), _is_nullable(original["items"])
                    )
                    text = _dump_spec(spec, default_flow_style=flow_style)
                    parsed = _load_spec(text)
                    self.assertEqual(parsed, spec)
                    # Only the item target changed; restoring it restores all
                    # field inventories, types, nullability and route bindings.
                    restored = deepcopy(parsed)
                    restored["components"]["schemas"]["GameTurnResult"][
                        "properties"
                    ]["quest_outcomes"]["items"]["$ref"] = original["items"]["$ref"]
                    self.assertEqual(restored, SPEC)
                    result = self._parity_result(parsed)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    failed_test, failure = result.failures[0]
                    self.assertIn(
                        "test_turn_quest_outcome_item_references_match_runtime_model",
                        failed_test.id(),
                    )
                    self.assertIn(
                        "GameTurnResult.quest_outcomes.items reference target", failure,
                    )

    def test_turn_input_wrong_combat_action_reference_fails_in_both_formats(self):
        original = _property("GameTurnInput", "combat_action")
        replacement = "#/components/schemas/GameSession"
        self.assertEqual(_schema_types(_schema("GameSession")), {"object"})
        self.assertNotIn(replacement, _schema_references(original))
        for flow_style in (False, True):
            with self.subTest(compact=flow_style):
                spec = deepcopy(SPEC)
                field = spec["components"]["schemas"]["GameTurnInput"][
                    "properties"
                ]["combat_action"]
                target = next(
                    branch for branch in field["anyOf"] if "$ref" in branch
                )
                original_reference = target["$ref"]
                target["$ref"] = replacement
                parsed = _load_spec(_dump_spec(
                    spec, default_flow_style=flow_style,
                ))
                self.assertEqual(parsed, spec)
                mutated = parsed["components"]["schemas"]["GameTurnInput"][
                    "properties"
                ]["combat_action"]
                self.assertEqual(_schema_types(mutated), _schema_types(original))
                self.assertEqual(_is_nullable(mutated), _is_nullable(original))
                self.assertEqual(parsed["paths"], SPEC["paths"])
                # Restoring only the nested target must recover the entire
                # document, including required fields, routes and statuses.
                restored = deepcopy(parsed)
                restored_field = restored["components"]["schemas"]["GameTurnInput"][
                    "properties"
                ]["combat_action"]
                next(
                    branch for branch in restored_field["anyOf"] if "$ref" in branch
                )["$ref"] = original_reference
                self.assertEqual(restored, SPEC)
                with patch.dict(globals(), SPEC=parsed):
                    unchanged = unittest.TestResult()
                    for method in (
                        "test_health_and_request_schemas_match_runtime_models",
                        "test_turn_route_bindings_match_fastapi",
                    ):
                        ContractParityTests(method).run(unchanged)
                    self.assertTrue(
                        unchanged.wasSuccessful(),
                        unchanged.failures + unchanged.errors,
                    )
                    result = unittest.TestResult()
                    ContractParityTests(
                        "test_turn_input_combat_action_reference_matches_runtime_model"
                    ).run(result)
                self.assertEqual(result.testsRun, 1)
                self.assertEqual(result.errors, [], result.errors)
                self.assertEqual(len(result.failures), 1, result.failures)
                self.assertIn(
                    "GameTurnInput.combat_action reference target",
                    result.failures[0][1],
                )

    def test_nested_combat_request_wrong_references_fail_in_both_formats(self):
        cases = (
            ("CombatActionInput", "steps", ("items",), "ReadyResponseInput",
             "test_combat_step_item_reference_matches_runtime_model"),
            ("EconomyStepInput", "trigger", ("anyOf", 0), "ReadyResponseInput",
             "test_combat_ready_references_match_runtime_models"),
            ("EconomyStepInput", "response", ("anyOf", 0), "ReadyTriggerInput",
             "test_combat_ready_references_match_runtime_models"),
        )
        for schema_name, field_name, target_path, wrong_model, parity_method in cases:
            original = _property(schema_name, field_name)
            original_target = original
            for key in target_path:
                original_target = original_target[key]
            replacement = f"#/components/schemas/{wrong_model}"
            self.assertEqual(_schema_types(_schema(wrong_model)), {"object"})
            self.assertNotIn(replacement, _schema_references(original_target))
            label = f"{schema_name}.{field_name}"
            if field_name == "steps":
                label += ".items"
            for flow_style in (False, True):
                with self.subTest(field=label, compact=flow_style):
                    spec = deepcopy(SPEC)
                    field = spec["components"]["schemas"][schema_name]["properties"][
                        field_name
                    ]
                    target = field
                    for key in target_path:
                        target = target[key]
                    target["$ref"] = replacement
                    parsed = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(parsed, spec)
                    mutated = parsed["components"]["schemas"][schema_name][
                        "properties"
                    ][field_name]
                    self.assertEqual(_schema_types(mutated), _schema_types(original))
                    self.assertEqual(_is_nullable(mutated), _is_nullable(original))
                    mutated_target = mutated
                    for key in target_path:
                        mutated_target = mutated_target[key]
                    self.assertEqual(
                        _schema_types(mutated_target), _schema_types(original_target)
                    )
                    self.assertEqual(
                        _is_nullable(mutated_target), _is_nullable(original_target)
                    )
                    self.assertEqual(parsed["paths"], SPEC["paths"])
                    # Restoring just the target restores every other declaration,
                    # including required fields, bounds, routes and statuses.
                    restored = deepcopy(parsed)
                    restored_target = restored["components"]["schemas"][schema_name][
                        "properties"
                    ][field_name]
                    for key in target_path:
                        restored_target = restored_target[key]
                    restored_target["$ref"] = original_target["$ref"]
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=parsed):
                        unchanged = unittest.TestResult()
                        for method in (
                            "test_health_and_request_schemas_match_runtime_models",
                            "test_turn_route_bindings_match_fastapi",
                            "test_turn_input_combat_action_reference_matches_runtime_model",
                        ):
                            ContractParityTests(method).run(unchanged)
                        self.assertTrue(
                            unchanged.wasSuccessful(),
                            unchanged.failures + unchanged.errors,
                        )
                        result = unittest.TestResult()
                        ContractParityTests(parity_method).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    self.assertIn(
                        f"{label} reference target", result.failures[0][1],
                    )

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
                        text = _dump_spec(spec, default_flow_style=flow_style)
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
                        text = _dump_spec(spec, default_flow_style=flow_style)
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
                        text = _dump_spec(spec, default_flow_style=flow_style)
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

    def test_health_error_responses_pass_in_both_formats(self):
        for path in ("/game/health", "/health"):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    responses = spec["paths"][path]["get"]["responses"]
                    self.assertNotIn("503", responses)
                    self.assertIn("ApiError", spec["components"]["responses"])
                    responses["503"] = {
                        "$ref": "#/components/responses/ApiError",
                    }
                    loaded = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(loaded, spec)
                    self.assertEqual(loaded["components"], SPEC["components"])
                    self.assertEqual(_route_inventory(loaded), _route_inventory(SPEC))
                    # Removing only the error proves the success responses,
                    # other alias and all remaining declarations are unchanged.
                    restored = deepcopy(loaded)
                    del restored["paths"][path]["get"]["responses"]["503"]
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=loaded):
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_operation_ids_are_unique_and_error_statuses_are_documented",
                            "test_health_and_request_schemas_match_runtime_models",
                            "test_health_route_bindings_match_fastapi",
                        ):
                            result = unittest.TestResult()
                            ContractParityTests(test_name).run(result)
                            self.assertEqual(result.testsRun, 1)
                            self.assertTrue(
                                result.wasSuccessful(),
                                result.failures + result.errors,
                            )

    def test_health_default_error_responses_pass_in_both_formats(self):
        for path in ("/game/health", "/health"):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    responses = spec["paths"][path]["get"]["responses"]
                    self.assertNotIn("default", responses)
                    self.assertIn("ApiError", spec["components"]["responses"])
                    responses["default"] = {
                        "$ref": "#/components/responses/ApiError",
                    }
                    loaded = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(loaded, spec)
                    self.assertEqual(loaded["components"], SPEC["components"])
                    self.assertEqual(_route_inventory(loaded), _route_inventory(SPEC))
                    # Only the default error is added; successful bindings,
                    # the other alias and every component remain unchanged.
                    restored = deepcopy(loaded)
                    del restored["paths"][path]["get"]["responses"]["default"]
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=loaded):
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_operation_ids_are_unique_and_error_statuses_are_documented",
                            "test_health_and_request_schemas_match_runtime_models",
                            "test_health_route_bindings_match_fastapi",
                        ):
                            result = unittest.TestResult()
                            ContractParityTests(test_name).run(result)
                            self.assertEqual(result.testsRun, 1)
                            self.assertTrue(
                                result.wasSuccessful(),
                                result.failures + result.errors,
                            )

    def test_health_success_status_drift_fails_in_both_formats(self):
        for path in ("/game/health", "/health"):
            for mutation in ("missing success", "extra success"):
                for flow_style in (False, True):
                    with self.subTest(path=path, mutation=mutation, compact=flow_style):
                        spec = deepcopy(SPEC)
                        responses = spec["paths"][path]["get"]["responses"]
                        if mutation == "missing success":
                            del responses["200"]
                            changed_status = "200"
                        else:
                            self.assertNotIn("201", responses)
                            responses["201"] = deepcopy(responses["200"])
                            changed_status = "201"
                        text = _dump_spec(spec, default_flow_style=flow_style)
                        loaded = _load_spec(text)
                        self.assertEqual(loaded, spec)
                        self.assertEqual(loaded["components"], SPEC["components"])
                        self.assertEqual(_route_inventory(loaded), _route_inventory(SPEC))
                        # Restore only the mutated response inventory to prove
                        # every other operation and definition stayed intact.
                        restored = deepcopy(loaded)
                        restored["paths"][path]["get"]["responses"] = deepcopy(
                            SPEC["paths"][path]["get"]["responses"]
                        )
                        self.assertEqual(restored, SPEC)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=loaded):
                            for test_name in (
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                                "test_operation_ids_are_unique_and_error_statuses_are_documented",
                                "test_health_and_request_schemas_match_runtime_models",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            ContractParityTests(
                                "test_health_route_bindings_match_fastapi"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        failure, traceback = result.failures[0]
                        self.assertIn(f"path='{path}'", failure.id())
                        self.assertIn("binding='success statuses'", failure.id())
                        self.assertIn("AssertionError", traceback)
                        self.assertIn(f"'{changed_status}'", traceback)

    def test_health_missing_success_with_default_error_fails_in_both_formats(self):
        for path in ("/game/health", "/health"):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    responses = spec["paths"][path]["get"]["responses"]
                    self.assertNotIn("default", responses)
                    self.assertIn("ApiError", spec["components"]["responses"])
                    responses["default"] = {
                        "$ref": "#/components/responses/ApiError",
                    }
                    del responses["200"]
                    loaded = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(loaded, spec)
                    self.assertEqual(loaded["components"], SPEC["components"])
                    self.assertEqual(_route_inventory(loaded), _route_inventory(SPEC))
                    self.assertEqual(
                        loaded["paths"][path]["get"]["responses"],
                        {"default": {"$ref": "#/components/responses/ApiError"}},
                    )
                    # Undo only the two response changes to prove the other
                    # alias and every remaining declaration stayed intact.
                    restored = deepcopy(loaded)
                    restored_responses = restored["paths"][path]["get"]["responses"]
                    del restored_responses["default"]
                    restored_responses["200"] = deepcopy(
                        SPEC["paths"][path]["get"]["responses"]["200"]
                    )
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=loaded):
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_operation_ids_are_unique_and_error_statuses_are_documented",
                            "test_health_and_request_schemas_match_runtime_models",
                        ):
                            unchanged = unittest.TestResult()
                            ContractParityTests(test_name).run(unchanged)
                            self.assertEqual(unchanged.testsRun, 1)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                        ContractParityTests(
                            "test_health_route_bindings_match_fastapi"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    failure, traceback = result.failures[0]
                    self.assertIn(f"path='{path}'", failure.id())
                    self.assertIn("binding='success statuses'", failure.id())
                    self.assertIn("AssertionError", traceback)
                    self.assertIn("'200'", traceback)

    def test_health_component_constraint_drift_fails_in_both_formats(self):
        schema_name = "HealthResponse"
        original = _schema(schema_name)
        mutations = [
            (("required",), None),
            (("required",), []),
            (("required",), [*original["required"], "unexpected"]),
        ]
        mutations.extend(
            (("required",), [
                field for field in original["required"] if field != removed
            ])
            for removed in original["required"]
        )
        for field_name in original["properties"]:
            mutations.extend(
                (("properties", field_name, "type"), replacement)
                for replacement in (
                    None, "integer", "number", "boolean", "object", "array",
                    ["string", "null"],
                )
            )
        for path, replacement in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    path=path, replacement=replacement, compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = deepcopy(replacement)
                    parsed = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    # References, statuses, names and enums remain untouched.
                    self.assertEqual(parsed["paths"], SPEC["paths"])
                    restored = deepcopy(parsed)
                    restored["components"]["schemas"][schema_name] = deepcopy(original)
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=parsed):
                        self.assertEqual(
                            _property_names(schema_name), set(original["properties"]),
                        )
                        for field_name in original["properties"]:
                            self.assertEqual(
                                _enum_values(schema_name, field_name),
                                set(original["properties"][field_name]["enum"]),
                            )
                        unchanged = unittest.TestResult()
                        ContractParityTests(
                            "test_health_route_bindings_match_fastapi"
                        ).run(unchanged)
                        self.assertTrue(
                            unchanged.wasSuccessful(),
                            unchanged.failures + unchanged.errors,
                        )
                        result = unittest.TestResult()
                        ContractParityTests(
                            "test_health_and_request_schemas_match_runtime_models"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    expected_label = (
                        "HealthResponse.required" if path == ("required",)
                        else f"HealthResponse.{path[1]}.type"
                    )
                    self.assertIn(expected_label, result.failures[0][1])

    def test_health_wrong_references_fail_in_both_formats(self):
        for path in ("/game/health", "/health"):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    schema = spec["paths"][path]["get"]["responses"]["200"][
                        "content"
                    ]["application/json"]["schema"]
                    wrong_model = "CampaignSummary"
                    self.assertIn(wrong_model, spec["components"]["schemas"])
                    schema["$ref"] = f"#/components/schemas/{wrong_model}"
                    self.assertEqual(spec["components"], SPEC["components"])
                    text = _dump_spec(spec, default_flow_style=flow_style)
                    parsed = _load_spec(text)
                    self.assertEqual(parsed, spec)
                    # Restoring only the response target recovers the whole
                    # contract, including the other alias and component fields.
                    restored = deepcopy(parsed)
                    restored["paths"][path]["get"]["responses"]["200"][
                        "content"
                    ]["application/json"]["schema"] = deepcopy(
                        SPEC["paths"][path]["get"]["responses"]["200"][
                            "content"
                        ]["application/json"]["schema"]
                    )
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
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
                            "test_health_route_bindings_match_fastapi"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    self.assertIn(f"path='{path}'", result.failures[0][0].id())
                    self.assertIn("binding='response'", result.failures[0][0].id())
                    self.assertIn("status='200'", result.failures[0][0].id())

    def test_campaign_read_wrong_references_fail_in_both_formats(self):
        for path in (
            "/game/campaigns",
            "/campaigns",
            "/game/campaigns/{campaign_id}",
            "/campaigns/{campaign_id}",
        ):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    schema = spec["paths"][path]["get"]["responses"]["200"][
                        "content"
                    ]["application/json"]["schema"]
                    if path.endswith("/campaigns"):
                        # Keep the array intact and swap only its item target.
                        schema["items"]["$ref"] = "#/components/schemas/CampaignDetail"
                    else:
                        schema["$ref"] = "#/components/schemas/CampaignSummary"
                    self.assertEqual(spec["components"], SPEC["components"])
                    text = _dump_spec(spec, default_flow_style=flow_style)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=_load_spec(text)):
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_operation_ids_are_unique_and_error_statuses_are_documented",
                            "test_health_and_request_schemas_match_runtime_models",
                            "test_campaign_and_session_schema_fields_match_fastapi_models",
                            "test_session_creation_and_campaign_resume_route_bindings_match_fastapi",
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
                            "test_campaign_read_route_bindings_match_fastapi"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    self.assertIn(f"path='{path}'", result.failures[0][0].id())
                    self.assertIn("binding='response'", result.failures[0][0].id())
                    self.assertIn("status='200'", result.failures[0][0].id())

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
                        text = _dump_spec(spec, default_flow_style=flow_style)
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

    def test_campaign_creation_and_save_wrong_bindings_fail_in_both_formats(self):
        for path in (
            "/game/campaigns",
            "/campaigns",
            "/game/campaigns/{campaign_id}/save",
            "/campaigns/{campaign_id}/save",
        ):
            for binding in ("requestBody", "response"):
                for flow_style in (False, True):
                    with self.subTest(path=path, binding=binding, compact=flow_style):
                        spec = deepcopy(SPEC)
                        operation = spec["paths"][path]["post"]
                        if binding == "requestBody":
                            if path.endswith("/save"):
                                self.assertNotIn("requestBody", operation)
                                operation["requestBody"] = {
                                    "required": True,
                                    "content": {"application/json": {"schema": {
                                        "$ref": "#/components/schemas/CampaignCreateInput",
                                    }}},
                                }
                            else:
                                operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] = (
                                    "#/components/schemas/GameTurnInput"
                                )
                        else:
                            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] = (
                                "#/components/schemas/CampaignSession"
                                if path.endswith("/save")
                                else "#/components/schemas/CampaignSummary"
                            )
                        # Only this operation changes; every component stays valid.
                        self.assertEqual(spec["components"], SPEC["components"])
                        text = _dump_spec(spec, default_flow_style=flow_style)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=_load_spec(text)):
                            for test_name in (
                                "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                                "test_operation_ids_are_unique_and_error_statuses_are_documented",
                                "test_health_and_request_schemas_match_runtime_models",
                                "test_campaign_and_session_schema_fields_match_fastapi_models",
                                "test_session_creation_and_campaign_resume_route_bindings_match_fastapi",
                                "test_turn_route_bindings_match_fastapi",
                                "test_species_action_route_bindings_match_fastapi",
                                "test_nested_death_schemas_match_runtime_models",
                                "test_nested_death_references_match_runtime_models",
                                "test_enemy_result_references_match_runtime_models",
                            ):
                                unchanged = unittest.TestResult()
                                ContractParityTests(test_name).run(unchanged)
                                self.assertTrue(
                                    unchanged.wasSuccessful(),
                                    unchanged.failures + unchanged.errors,
                                )
                            ContractParityTests(
                                "test_campaign_creation_and_save_route_bindings_match_fastapi"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(f"path='{path}'", result.failures[0][0].id())
                        self.assertIn(f"binding='{binding}'", result.failures[0][0].id())

    def test_campaign_creation_and_save_body_and_status_drift_fail_in_both_formats(self):
        for path in (
            "/game/campaigns",
            "/campaigns",
            "/game/campaigns/{campaign_id}/save",
            "/campaigns/{campaign_id}/save",
        ):
            mutations = ["missing success", "extra success", "changed success"]
            if not path.endswith("/save"):
                mutations.extend(["missing body", "optional body", "omitted required"])
            for mutation in mutations:
                binding = "requestBody" if mutation.endswith(("body", "required")) else "success statuses"
                for flow_style in (False, True):
                    with self.subTest(path=path, mutation=mutation, compact=flow_style):
                        spec = deepcopy(SPEC)
                        operation = spec["paths"][path]["post"]
                        if mutation == "missing body":
                            del operation["requestBody"]
                        elif mutation == "optional body":
                            operation["requestBody"]["required"] = False
                        elif mutation == "omitted required":
                            del operation["requestBody"]["required"]
                        elif mutation == "missing success":
                            del operation["responses"]["200"]
                        elif mutation == "extra success":
                            operation["responses"]["201"] = deepcopy(operation["responses"]["200"])
                        else:
                            operation["responses"]["201"] = operation["responses"].pop("200")
                        self.assertEqual(spec["components"], SPEC["components"])
                        text = _dump_spec(spec, default_flow_style=flow_style)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=_load_spec(text)):
                            ContractParityTests(
                                "test_campaign_creation_and_save_route_bindings_match_fastapi"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(f"path='{path}'", result.failures[0][0].id())
                        self.assertIn(f"binding='{binding}'", result.failures[0][0].id())

    def test_campaign_creation_and_save_default_error_responses_pass_in_both_formats(self):
        for path in (
            "/game/campaigns",
            "/campaigns",
            "/game/campaigns/{campaign_id}/save",
            "/campaigns/{campaign_id}/save",
        ):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    responses = spec["paths"][path]["post"]["responses"]
                    self.assertIn("200", responses)
                    self.assertNotIn("default", responses)
                    self.assertIn("ApiError", spec["components"]["responses"])
                    responses["default"] = {
                        "$ref": "#/components/responses/ApiError",
                    }
                    loaded = _load_spec(yaml.safe_dump(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(loaded, spec)
                    self.assertEqual(loaded["components"], SPEC["components"])
                    self.assertEqual(_route_inventory(loaded), _route_inventory(SPEC))
                    self.assertEqual(
                        loaded["paths"][path]["post"]["responses"]["200"],
                        SPEC["paths"][path]["post"]["responses"]["200"],
                    )
                    self.assertEqual(
                        loaded["paths"][path]["post"]["responses"]["default"],
                        {"$ref": "#/components/responses/ApiError"},
                    )
                    # Removing only the added fallback proves request bodies,
                    # untouched aliases and all other declarations are preserved.
                    restored = deepcopy(loaded)
                    del restored["paths"][path]["post"]["responses"]["default"]
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=loaded):
                        # The general status inventory deliberately fixes the
                        # canonical creation status set, so do not run it here.
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_health_and_request_schemas_match_runtime_models",
                            "test_campaign_and_session_schema_fields_match_fastapi_models",
                            "test_campaign_creation_and_save_route_bindings_match_fastapi",
                        ):
                            result = unittest.TestResult()
                            ContractParityTests(test_name).run(result)
                            self.assertEqual(result.testsRun, 1)
                            self.assertTrue(
                                result.wasSuccessful(),
                                result.failures + result.errors,
                            )

    def test_campaign_creation_and_save_missing_success_with_default_error_fails_in_both_formats(self):
        for path in (
            "/game/campaigns",
            "/campaigns",
            "/game/campaigns/{campaign_id}/save",
            "/campaigns/{campaign_id}/save",
        ):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    responses = spec["paths"][path]["post"]["responses"]
                    self.assertNotIn("default", responses)
                    self.assertIn("ApiError", spec["components"]["responses"])
                    responses["default"] = {
                        "$ref": "#/components/responses/ApiError",
                    }
                    del responses["200"]
                    loaded = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(loaded, spec)
                    self.assertEqual(loaded["components"], SPEC["components"])
                    self.assertEqual(_route_inventory(loaded), _route_inventory(SPEC))
                    self.assertNotIn("200", loaded["paths"][path]["post"]["responses"])
                    self.assertEqual(
                        loaded["paths"][path]["post"]["responses"]["default"],
                        {"$ref": "#/components/responses/ApiError"},
                    )
                    # Undo only the two response changes to prove request bodies,
                    # other aliases and every remaining declaration stayed intact.
                    restored = deepcopy(loaded)
                    restored_responses = restored["paths"][path]["post"]["responses"]
                    del restored_responses["default"]
                    restored_responses["200"] = deepcopy(
                        SPEC["paths"][path]["post"]["responses"]["200"]
                    )
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=loaded):
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_health_and_request_schemas_match_runtime_models",
                            "test_campaign_and_session_schema_fields_match_fastapi_models",
                        ):
                            unchanged = unittest.TestResult()
                            ContractParityTests(test_name).run(unchanged)
                            self.assertEqual(unchanged.testsRun, 1)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                        ContractParityTests(
                            "test_campaign_creation_and_save_route_bindings_match_fastapi"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    failure, traceback = result.failures[0]
                    self.assertIn(f"path='{path}'", failure.id())
                    self.assertIn("binding='success statuses'", failure.id())
                    self.assertIn("AssertionError", traceback)
                    self.assertIn("'200'", traceback)

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
                        text = _dump_spec(spec, default_flow_style=flow_style)
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

    def test_saved_story_history_constraint_drift_fails_in_both_formats(self):
        schema_name = "CampaignHistoryEntry"
        original = _schema(schema_name)
        mutations = [(("required",), None)]
        for field_name in ("player_message", "narration", "created_at"):
            mutations.append((
                ("required",),
                [field for field in original["required"] if field != field_name],
            ))
            mutations.extend(
                (("properties", field_name, "type"), replacement)
                for replacement in (
                    None, "integer", "number", "boolean", "object", "array",
                    ["string", "null"],
                )
            )
        for path, replacement in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    path=path, replacement=replacement, compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = replacement
                    parsed = _load_spec(
                        _dump_spec(spec, default_flow_style=flow_style)
                    )
                    self.assertEqual(parsed, spec)
                    # Restoring only the mutated entry declaration must recover
                    # the entire contract, including unchanged history item refs.
                    restored = deepcopy(parsed)
                    target = restored["components"]["schemas"][schema_name]
                    source = original
                    for key in path[:-1]:
                        target = target[key]
                        source = source[key]
                    target[path[-1]] = deepcopy(source[path[-1]])
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        for test_name in (
                            "test_saved_story_history_constraints_match_runtime_model",
                            "test_campaign_and_session_schema_fields_match_fastapi_models",
                        ):
                            ContractParityTests(test_name).run(result)
                    self.assertEqual(result.testsRun, 2)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    failed_test, failure = result.failures[0]
                    self.assertIn(
                        "test_saved_story_history_constraints_match_runtime_model",
                        failed_test.id(),
                    )
                    self.assertIn(
                        f"{schema_name}.{'.'.join(path).removeprefix('properties.')}",
                        failure,
                    )

    def test_saved_combat_history_constraint_drift_fails_in_both_formats(self):
        original = _schema("CombatHistoryEntry")
        mutations = [
            (("required",), None),
            (("required",), original["required"] + ["unexpected"]),
            (("additionalProperties",), None),
            (("additionalProperties",), True),
            (("properties", "event_id", "pattern"), None),
            (("properties", "event_id", "pattern"), "^[0-9a-f-]+$"),
            (("properties", "turn_index", "type"), None),
            (("properties", "turn_index", "type"), "number"),
            (("properties", "turn_index", "type"), "string"),
            (("properties", "turn_index", "type"), "boolean"),
            (("properties", "turn_index", "type"), "object"),
            (("properties", "turn_index", "type"), "array"),
            (("properties", "turn_index", "type"), "null"),
            (("properties", "turn_index", "type"), ["integer", "null"]),
            (("properties", "turn_index", "minimum"), None),
            (("properties", "turn_index", "minimum"), False),
            (("properties", "turn_index", "minimum"), -1),
            (("properties", "turn_index", "minimum"), 1),
        ]
        mutations.extend(
            (("properties", "event_id", "type"), replacement)
            for replacement in (
                None, "integer", "number", "boolean", "object", "array", "null",
                ["string", "null"],
            )
        )
        mutations.extend(
            (("required",), [
                field for field in original["required"] if field != removed
            ])
            for removed in original["required"]
        )
        for path, replacement in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    path=path, replacement=replacement, compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"]["CombatHistoryEntry"]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = replacement
                    parsed = _load_spec(
                        _dump_spec(spec, default_flow_style=flow_style)
                    )
                    self.assertEqual(parsed, spec)
                    # Only one entry constraint changes; references, routes and
                    # schema/field inventories remain the published contract.
                    if (
                        path == ("properties", "turn_index", "minimum")
                        and replacement is False
                    ):
                        self.assertIs(
                            parsed["components"]["schemas"]["CombatHistoryEntry"][
                                "properties"
                            ]["turn_index"]["minimum"],
                            False,
                        )
                    restored = deepcopy(parsed)
                    target = restored["components"]["schemas"]["CombatHistoryEntry"]
                    source = original
                    for key in path[:-1]:
                        target = target[key]
                        source = source[key]
                    target[path[-1]] = deepcopy(source[path[-1]])
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        for test_name in (
                            "test_saved_combat_history_constraints_match_runtime_model",
                            "test_saved_combat_history_references_match_runtime_models",
                            "test_campaign_and_session_schema_fields_match_fastapi_models",
                        ):
                            ContractParityTests(test_name).run(result)
                    self.assertEqual(result.testsRun, 3)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    failed_test, failure = result.failures[0]
                    self.assertIn(
                        "test_saved_combat_history_constraints_match_runtime_model",
                        failed_test.id(),
                    )
                    self.assertIn(
                        f"CombatHistoryEntry.{'.'.join(path).removeprefix('properties.')}",
                        failure,
                    )

    def test_campaign_history_optional_fields_fail_in_both_formats(self):
        for schema_name in ("CampaignDetail", "CampaignSession"):
            original = _schema(schema_name)
            for field_name in ("history", "combat_history"):
                self.assertIn(field_name, original["required"])
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, field=field_name, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        spec["components"]["schemas"][schema_name]["required"].remove(
                            field_name
                        )
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        self.assertEqual(parsed, spec)
                        mutated = parsed["components"]["schemas"][schema_name]
                        self.assertEqual(
                            mutated["properties"], original["properties"]
                        )
                        self.assertEqual(
                            set(mutated["required"]),
                            set(original["required"]) - {field_name},
                        )
                        # Restoring only required proves that properties, item
                        # targets, entry constraints and route bindings survived.
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name]["required"] = (
                            deepcopy(original["required"])
                        )
                        self.assertEqual(restored, SPEC)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=parsed):
                            for test_name in (
                                "test_campaign_history_required_fields_match_runtime_models",
                                "test_campaign_and_session_schema_fields_match_fastapi_models",
                                "test_campaign_history_item_references_match_runtime_models",
                            ):
                                ContractParityTests(test_name).run(result)
                        self.assertEqual(result.testsRun, 3)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        failed_test, failure = result.failures[0]
                        self.assertIn(
                            "test_campaign_history_required_fields_match_runtime_models",
                            failed_test.id(),
                        )
                        self.assertIn(
                            f"{schema_name}.{field_name}.required", failure
                        )

    def test_campaign_history_collection_shapes_fail_in_both_formats(self):
        for schema_name in ("CampaignDetail", "CampaignSession"):
            original_schema = _schema(schema_name)
            for field_name, entry_model in (
                ("history", CampaignHistoryEntry),
                ("combat_history", CombatHistoryEntry),
            ):
                original = _property(schema_name, field_name)
                self.assertIn(field_name, original_schema["required"])
                self.assertEqual(_schema_types(original), {"array"})
                self.assertFalse(_is_nullable(original))
                for mutation in (
                    "missing_type", "string", "object",
                    "nullable_type_array", "nullable_any_of",
                ):
                    for flow_style in (False, True):
                        with self.subTest(
                            schema=schema_name, field=field_name,
                            mutation=mutation, compact=flow_style,
                        ):
                            spec = deepcopy(SPEC)
                            field = spec["components"]["schemas"][schema_name][
                                "properties"
                            ][field_name]
                            if mutation == "missing_type":
                                del field["type"]
                            elif mutation == "nullable_type_array":
                                field["type"] = ["array", "null"]
                            elif mutation == "nullable_any_of":
                                del field["type"]
                                field["anyOf"] = [
                                    {"type": "array"}, {"type": "null"},
                                ]
                            else:
                                field["type"] = mutation
                            parsed = _load_spec(
                                _dump_spec(spec, default_flow_style=flow_style)
                            )
                            self.assertEqual(parsed, spec)
                            mutated_schema = parsed["components"]["schemas"][schema_name]
                            mutated = mutated_schema["properties"][field_name]
                            self.assertEqual(
                                mutated_schema["required"], original_schema["required"]
                            )
                            self.assertEqual(mutated["items"], original["items"])
                            self.assertEqual(
                                _schema_references(mutated["items"]),
                                {f"#/components/schemas/{entry_model.__name__}"},
                            )
                            self.assertNotEqual(
                                _schema_types(mutated), _schema_types(original)
                            )
                            self.assertEqual(
                                _is_nullable(mutated), mutation.startswith("nullable_")
                            )
                            # Only collection declarations changed; restoring
                            # them preserves item targets and all other contracts.
                            restored = deepcopy(parsed)
                            restored_field = restored["components"]["schemas"][
                                schema_name
                            ]["properties"][field_name]
                            restored_field.pop("anyOf", None)
                            restored_field["type"] = original["type"]
                            self.assertEqual(restored, SPEC)
                            result = unittest.TestResult()
                            with patch.dict(globals(), SPEC=parsed):
                                for test_name in (
                                    "test_campaign_history_required_fields_match_runtime_models",
                                    "test_campaign_and_session_schema_fields_match_fastapi_models",
                                    "test_campaign_history_item_references_match_runtime_models",
                                ):
                                    ContractParityTests(test_name).run(result)
                            self.assertEqual(result.testsRun, 3)
                            self.assertEqual(result.errors, [], result.errors)
                            self.assertEqual(len(result.failures), 1, result.failures)
                            failed_test, failure = result.failures[0]
                            self.assertIn(
                                "test_campaign_history_item_references_match_runtime_models",
                                failed_test.id(),
                            )
                            self.assertIn(f"{schema_name}.{field_name}.type", failure)

    def test_campaign_history_wrong_item_references_fail_in_both_formats(self):
        for schema_name in ("CampaignDetail", "CampaignSession"):
            for field_name, wrong_models in (
                ("history", ("CombatHistoryEntry", "CampaignSummary")),
                ("combat_history", ("CampaignHistoryEntry", "CombatTurnResult")),
            ):
                original = _property(schema_name, field_name)
                for wrong_model in wrong_models:
                    for flow_style in (False, True):
                        with self.subTest(
                            schema=schema_name, field=field_name,
                            replacement=wrong_model, compact=flow_style,
                        ):
                            self.assertIn(wrong_model, SPEC["components"]["schemas"])
                            spec = deepcopy(SPEC)
                            field = spec["components"]["schemas"][schema_name][
                                "properties"
                            ][field_name]
                            field["items"]["$ref"] = f"#/components/schemas/{wrong_model}"
                            text = _dump_spec(spec, default_flow_style=flow_style)
                            parsed = _load_spec(text)
                            self.assertEqual(parsed, spec)
                            mutated = parsed["components"]["schemas"][schema_name][
                                "properties"
                            ][field_name]
                            for before, after in (
                                (original, mutated),
                                (original["items"], mutated["items"]),
                            ):
                                self.assertEqual(_schema_types(after), _schema_types(before))
                                self.assertEqual(_is_nullable(after), _is_nullable(before))
                            # Only the item target changed, not the surrounding
                            # schema, field inventory or route bindings.
                            restored = deepcopy(parsed)
                            restored["components"]["schemas"][schema_name]["properties"][
                                field_name
                            ]["items"]["$ref"] = original["items"]["$ref"]
                            self.assertEqual(restored, SPEC)
                            with patch.dict(globals(), SPEC=parsed):
                                inventory = unittest.TestResult()
                                ContractParityTests(
                                    "test_campaign_and_session_schema_fields_match_fastapi_models"
                                ).run(inventory)
                                self.assertTrue(
                                    inventory.wasSuccessful(),
                                    inventory.failures + inventory.errors,
                                )
                                result = unittest.TestResult()
                                ContractParityTests(
                                    "test_campaign_history_item_references_match_runtime_models"
                                ).run(result)
                            self.assertEqual(result.testsRun, 1)
                            self.assertEqual(result.errors, [], result.errors)
                            self.assertEqual(len(result.failures), 1, result.failures)
                            self.assertIn(
                                f"{schema_name}.{field_name}.items reference target",
                                result.failures[0][1],
                            )

    def test_saved_combat_history_wrong_references_fail_in_both_formats(self):
        fields = (
            ("CombatHistoryEntry", "result", ("CombatAttackResult", "GameSession")),
            ("CampaignDetail", "combat_history", ("CampaignHistoryEntry", "CombatTurnResult")),
            ("CampaignSession", "combat_history", ("CampaignHistoryEntry", "CombatTurnResult")),
        )
        for schema_name, field_name, wrong_models in fields:
            original = _property(schema_name, field_name)
            original_target = (
                original["items"] if field_name == "combat_history" else original
            )
            for wrong_model in wrong_models:
                for flow_style in (False, True):
                    with self.subTest(
                        schema=schema_name, field=field_name,
                        replacement=wrong_model, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        field = spec["components"]["schemas"][schema_name][
                            "properties"
                        ][field_name]
                        target = field["items"] if field_name == "combat_history" else field
                        target["$ref"] = f"#/components/schemas/{wrong_model}"
                        self.assertEqual(_schema_types(field), _schema_types(original))
                        self.assertEqual(_is_nullable(field), _is_nullable(original))
                        self.assertEqual(_schema_types(target), _schema_types(original_target))
                        self.assertEqual(_is_nullable(target), _is_nullable(original_target))
                        text = _dump_spec(spec, default_flow_style=flow_style)
                        parsed = _load_spec(text)
                        self.assertEqual(parsed, spec)
                        # Restoring only the target recovers the entire original
                        # contract: routes, operations and schema/field inventories
                        # (including required fields) were never changed.
                        restored = deepcopy(parsed)
                        restored_field = restored["components"]["schemas"][schema_name][
                            "properties"
                        ][field_name]
                        restored_target = (
                            restored_field["items"]
                            if field_name == "combat_history" else restored_field
                        )
                        restored_target["$ref"] = original_target["$ref"]
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_saved_combat_history_references_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        failed_test, failure = result.failures[0]
                        self.assertIn(
                            "test_saved_combat_history_references_match_runtime_models",
                            failed_test.id(),
                        )
                        self.assertIn(
                            f"{schema_name}.{field_name} reference target", failure,
                        )

    def test_character_setup_wrong_references_fail_in_both_formats(self):
        for path in (
            "/game/character-options",
            "/character-options",
            "/game/character-creation-catalog",
            "/character-creation-catalog",
            "/game/campaign-start-options",
            "/campaign-start-options",
        ):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    schema = spec["paths"][path]["get"]["responses"]["200"][
                        "content"
                    ]["application/json"]["schema"]
                    original_ref = schema["$ref"]
                    replacement = (
                        "CharacterCreationCatalogResponse"
                        if path.endswith("/character-options")
                        else "CharacterCreationOptions"
                    )
                    self.assertIn(replacement, spec["components"]["schemas"])
                    schema["$ref"] = f"#/components/schemas/{replacement}"
                    self.assertNotEqual(schema["$ref"], original_ref)
                    parsed = _load_spec(_dump_spec(spec, default_flow_style=flow_style))
                    self.assertEqual(parsed["components"], SPEC["components"])
                    restored = deepcopy(parsed)
                    restored["paths"][path]["get"]["responses"]["200"]["content"][
                        "application/json"
                    ]["schema"]["$ref"] = original_ref
                    # Only one operation's reference changed, not its component.
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_operation_ids_are_unique_and_error_statuses_are_documented",
                            "test_health_and_request_schemas_match_runtime_models",
                            "test_campaign_and_session_schema_fields_match_fastapi_models",
                            "test_campaign_read_route_bindings_match_fastapi",
                            "test_session_creation_and_campaign_resume_route_bindings_match_fastapi",
                            "test_campaign_creation_and_save_route_bindings_match_fastapi",
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
                            "test_character_setup_route_bindings_match_fastapi"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    self.assertIn(f"path='{path}'", result.failures[0][0].id())
                    self.assertIn("binding='response'", result.failures[0][0].id())
                    self.assertIn("status='200'", result.failures[0][0].id())

    def test_character_setup_success_status_mutations_fail_in_both_formats(self):
        for path in (
            "/game/character-options",
            "/character-options",
            "/game/character-creation-catalog",
            "/character-creation-catalog",
            "/game/campaign-start-options",
            "/campaign-start-options",
        ):
            for mutation in ("missing", "extra", "changed"):
                for flow_style in (False, True):
                    with self.subTest(path=path, mutation=mutation, compact=flow_style):
                        spec = deepcopy(SPEC)
                        responses = spec["paths"][path]["get"]["responses"]
                        if mutation == "missing":
                            del responses["200"]
                        elif mutation == "extra":
                            responses["201"] = deepcopy(responses["200"])
                        else:
                            responses["201"] = responses.pop("200")
                        parsed = _load_spec(
                            _dump_spec(spec, default_flow_style=flow_style)
                        )
                        restored = deepcopy(parsed)
                        restored["paths"][path]["get"]["responses"] = deepcopy(
                            SPEC["paths"][path]["get"]["responses"]
                        )
                        self.assertEqual(restored, SPEC)
                        result = unittest.TestResult()
                        with patch.dict(globals(), SPEC=parsed):
                            ContractParityTests(
                                "test_character_setup_route_bindings_match_fastapi"
                            ).run(result)
                        # A missing success may also raise during schema lookup;
                        # the status assertion must still fail for this exact route.
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(f"path='{path}'", result.failures[0][0].id())
                        self.assertIn(
                            "binding='success statuses'", result.failures[0][0].id()
                        )
                        if mutation == "extra":
                            self.assertEqual(result.errors, [], result.errors)
                        else:
                            self.assertEqual(len(result.errors), 1, result.errors)
                            self.assertIn(f"path='{path}'", result.errors[0][0].id())
                            self.assertIn("binding='response'", result.errors[0][0].id())

    def test_character_setup_missing_success_with_default_error_fails_in_both_formats(self):
        for path in (
            "/game/character-options",
            "/character-options",
            "/game/character-creation-catalog",
            "/character-creation-catalog",
            "/game/campaign-start-options",
            "/campaign-start-options",
        ):
            for flow_style in (False, True):
                with self.subTest(path=path, compact=flow_style):
                    spec = deepcopy(SPEC)
                    responses = spec["paths"][path]["get"]["responses"]
                    self.assertNotIn("default", responses)
                    self.assertIn("ApiError", spec["components"]["responses"])
                    responses["default"] = {
                        "$ref": "#/components/responses/ApiError",
                    }
                    del responses["200"]
                    loaded = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(loaded, spec)
                    self.assertEqual(loaded["components"], SPEC["components"])
                    self.assertEqual(_route_inventory(loaded), _route_inventory(SPEC))
                    self.assertNotIn("200", loaded["paths"][path]["get"]["responses"])
                    self.assertEqual(
                        loaded["paths"][path]["get"]["responses"]["default"],
                        {"$ref": "#/components/responses/ApiError"},
                    )
                    # Undo only the two response changes to prove the other
                    # aliases, errors and every component stayed intact.
                    restored = deepcopy(loaded)
                    restored_responses = restored["paths"][path]["get"]["responses"]
                    del restored_responses["default"]
                    restored_responses["200"] = deepcopy(
                        SPEC["paths"][path]["get"]["responses"]["200"]
                    )
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=loaded):
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_operation_ids_are_unique_and_error_statuses_are_documented",
                            "test_health_and_request_schemas_match_runtime_models",
                        ):
                            unchanged = unittest.TestResult()
                            ContractParityTests(test_name).run(unchanged)
                            self.assertEqual(unchanged.testsRun, 1)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                        ContractParityTests(
                            "test_character_setup_route_bindings_match_fastapi"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    failure, traceback = result.failures[0]
                    self.assertIn(
                        "test_character_setup_route_bindings_match_fastapi", failure.id(),
                    )
                    self.assertIn(f"path='{path}'", failure.id())
                    self.assertIn("binding='success statuses'", failure.id())
                    self.assertIn("AssertionError", traceback)
                    self.assertIn("'200'", traceback)
                    # The existing response lookup also reports the missing
                    # success; it must not obscure the route's status failure.
                    self.assertEqual(len(result.errors), 1, result.errors)
                    error, traceback = result.errors[0]
                    self.assertIn(f"path='{path}'", error.id())
                    self.assertIn("binding='response'", error.id())
                    self.assertIn("status='200'", error.id())
                    self.assertIn("KeyError: '200'", traceback)

    def test_campaign_summary_and_detail_unexpected_properties_fail_in_both_formats(self):
        field_name = "unexpected"
        declaration = {"type": "string"}
        for schema_name, model in (
            ("CampaignSummary", CampaignSummary),
            ("CampaignDetail", CampaignDetailResponse),
        ):
            original = deepcopy(_schema(schema_name))
            self.assertEqual(set(original["properties"]), _runtime_field_names(model))
            self.assertNotIn(field_name, original["properties"])
            self.assertNotIn(field_name, original["required"])
            for flow_style in (False, True):
                with self.subTest(schema=schema_name, compact=flow_style):
                    spec = deepcopy(SPEC)
                    spec["components"]["schemas"][schema_name]["properties"][
                        field_name
                    ] = deepcopy(declaration)
                    parsed = _load_spec(
                        yaml.safe_dump(spec, default_flow_style=flow_style)
                    )
                    self.assertEqual(parsed, spec)
                    mutated = parsed["components"]["schemas"][schema_name]
                    self.assertEqual(
                        mutated["properties"],
                        {**original["properties"], field_name: declaration},
                    )
                    self.assertEqual(mutated["required"], original["required"])
                    self.assertNotIn(field_name, mutated["required"])
                    self.assertEqual(
                        mutated["additionalProperties"], original["additionalProperties"],
                    )
                    self.assertEqual(parsed["paths"], SPEC["paths"])
                    # Removing just the optional declaration restores every
                    # original property, required list, policy and route.
                    restored = deepcopy(parsed)
                    del restored["components"]["schemas"][schema_name]["properties"][
                        field_name
                    ]
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=parsed):
                        for test_name in (
                            "test_campaign_summary_scalar_fields_match_runtime_model",
                            "test_campaign_detail_summary_reference_matches_runtime_model",
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_health_route_bindings_match_fastapi",
                            "test_character_setup_route_bindings_match_fastapi",
                            "test_campaign_read_route_bindings_match_fastapi",
                            "test_session_creation_and_campaign_resume_route_bindings_match_fastapi",
                            "test_campaign_creation_and_save_route_bindings_match_fastapi",
                            "test_turn_route_bindings_match_fastapi",
                            "test_species_action_route_bindings_match_fastapi",
                        ):
                            unchanged = unittest.TestResult()
                            ContractParityTests(test_name).run(unchanged)
                            self.assertEqual(unchanged.testsRun, 1)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                        result = unittest.TestResult()
                        ContractParityTests(
                            "test_campaign_and_session_schema_fields_match_fastapi_models"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    comparison, failure = result.failures[0]
                    self.assertIn(f"schema='{schema_name}'", comparison.id())
                    self.assertNotIn("field=", comparison.id())
                    self.assertIn(
                        "self.assertEqual(_property_names(schema_name), _runtime_field_names(model))",
                        failure,
                    )
                    self.assertIn("Items in the first set but not the second:", failure)
                    self.assertIn(repr(field_name), failure)
            self.assertEqual(_schema(schema_name), original)

    def test_campaign_detail_summary_wrong_references_fail_in_both_formats(self):
        original = _property("CampaignDetail", "campaign")
        for wrong_model in ("GameSession", "CampaignHistoryEntry"):
            for flow_style in (False, True):
                with self.subTest(model=wrong_model, compact=flow_style):
                    spec = deepcopy(SPEC)
                    self.assertIn(wrong_model, spec["components"]["schemas"])
                    field = spec["components"]["schemas"]["CampaignDetail"][
                        "properties"
                    ]["campaign"]
                    field["$ref"] = f"#/components/schemas/{wrong_model}"
                    self.assertEqual(_schema_types(field), _schema_types(original))
                    self.assertEqual(_is_nullable(field), _is_nullable(original))
                    # Restoring only the reference must recover the entire
                    # contract, including inventories and all route bindings.
                    restored = deepcopy(spec)
                    restored["components"]["schemas"]["CampaignDetail"][
                        "properties"
                    ]["campaign"]["$ref"] = original["$ref"]
                    self.assertEqual(restored, SPEC)
                    self.assertEqual(spec["paths"], SPEC["paths"])
                    text = _dump_spec(spec, default_flow_style=flow_style)
                    parsed = _load_spec(text)
                    self.assertEqual(parsed, spec)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_campaign_and_session_schema_fields_match_fastapi_models",
                            "test_campaign_read_route_bindings_match_fastapi",
                        ):
                            unchanged = unittest.TestResult()
                            ContractParityTests(test_name).run(unchanged)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                        ContractParityTests(
                            "test_campaign_detail_summary_reference_matches_runtime_model"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    self.assertIn(
                        "CampaignDetail.campaign reference target",
                        result.failures[0][1],
                    )
        self.assertEqual(_property("CampaignDetail", "campaign"), original)

    def test_turn_action_id_pattern_drift_fails_in_both_formats(self):
        original = _property("GameTurnInput", "action_id")
        mutations = (
            None,
            ".*",
            "^[0-9a-f-]+$",
            # Generic UUID shape no longer restricts the version nibble.
            original["pattern"].replace("4[0-9a-f]{3}", "[0-9a-f]{4}"),
            # Retain version 4 but accept non-RFC UUID variants.
            original["pattern"].replace("[89ab]", "[0-9a-f]"),
            original["pattern"].removeprefix("^").removesuffix("$"),
        )
        for replacement in mutations:
            for flow_style in (False, True):
                with self.subTest(replacement=replacement, compact=flow_style):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"]["GameTurnInput"][
                        "properties"
                    ]["action_id"]
                    if replacement is None:
                        del target["pattern"]
                    else:
                        target["pattern"] = replacement
                    parsed = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(parsed, spec)
                    self.assertEqual(parsed["paths"], SPEC["paths"])
                    restored = deepcopy(parsed)
                    restored["components"]["schemas"]["GameTurnInput"][
                        "properties"
                    ]["action_id"] = deepcopy(original)
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=parsed):
                        unchanged = unittest.TestResult()
                        for test_name in (
                            "test_documented_routes_match_fastapi_and_preserve_both_alias_families",
                            "test_turn_route_bindings_match_fastapi",
                            "test_health_and_request_schemas_match_runtime_models",
                        ):
                            ContractParityTests(test_name).run(unchanged)
                        self.assertTrue(
                            unchanged.wasSuccessful(),
                            unchanged.failures + unchanged.errors,
                        )
                        result = unittest.TestResult()
                        ContractParityTests(
                            "test_turn_action_id_pattern_matches_uuid4_validator"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    self.assertIn(
                        "GameTurnInput.action_id.pattern", result.failures[0][1],
                    )
        self.assertEqual(_property("GameTurnInput", "action_id"), original)

    def test_turn_input_constraint_drift_fails_in_both_formats(self):
        schema_name = "GameTurnInput"
        constraints = (
            ("target_id", "minLength"),
            ("target_id", "maxLength"),
            ("combat_id", "minLength"),
            ("combat_id", "maxLength"),
            ("action_id", "format"),
            ("combat_round", "minimum"),
            ("combat_turn_index", "minimum"),
        )
        for field_name, constraint in constraints:
            original = _property(schema_name, field_name)
            expected = original[constraint]
            replacements = (
                (None, "date-time", "uri") if constraint == "format"
                else (None, expected - 1, expected + 1)
            )
            for replacement in replacements:
                for flow_style in (False, True):
                    with self.subTest(
                        field=field_name, constraint=constraint,
                        replacement=replacement, compact=flow_style,
                    ):
                        spec = deepcopy(SPEC)
                        target = spec["components"]["schemas"][schema_name][
                            "properties"
                        ][field_name]
                        if replacement is None:
                            del target[constraint]
                        else:
                            target[constraint] = replacement
                        parsed = _load_spec(_dump_spec(
                            spec, default_flow_style=flow_style,
                        ))
                        self.assertEqual(parsed, spec)
                        self.assertEqual(parsed["paths"], SPEC["paths"])
                        restored = deepcopy(parsed)
                        restored["components"]["schemas"][schema_name][
                            "properties"
                        ][field_name] = deepcopy(original)
                        self.assertEqual(restored, SPEC)
                        with patch.dict(globals(), SPEC=parsed):
                            unchanged = unittest.TestResult()
                            ContractParityTests(
                                "test_turn_route_bindings_match_fastapi"
                            ).run(unchanged)
                            self.assertTrue(
                                unchanged.wasSuccessful(),
                                unchanged.failures + unchanged.errors,
                            )
                            result = unittest.TestResult()
                            ContractParityTests(
                                "test_health_and_request_schemas_match_runtime_models"
                            ).run(result)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [], result.errors)
                        self.assertEqual(len(result.failures), 1, result.failures)
                        self.assertIn(
                            f"{schema_name}.{field_name}.{constraint}",
                            result.failures[0][1],
                        )

    def test_turn_input_required_and_type_drift_fails_in_both_formats(self):
        schema_name = "GameTurnInput"
        original = _schema(schema_name)
        mutations = [
            (("required",), None),
            (("required",), []),
            (("required",), [*original["required"], "unexpected"]),
        ]
        mutations.extend(
            (("required",), [*original["required"], field_name])
            for field_name in original["properties"]
            if field_name not in original["required"]
        )
        for field_name, property_schema in original["properties"].items():
            expected_types = _schema_types(property_schema)
            if "anyOf" in property_schema:
                branches = property_schema["anyOf"]
                mutations.extend([
                    (("properties", field_name, "anyOf"), None),
                    (("properties", field_name, "anyOf"), [
                        branch for branch in branches if branch.get("type") != "null"
                    ]),
                    (("properties", field_name, "anyOf"), [
                        *branches, {"type": "string"},
                    ]),
                ])
            else:
                replacements = [
                    None,
                    *(value for value in (
                        "string", "integer", "number", "boolean", "object", "array",
                    ) if value not in expected_types),
                    sorted(expected_types ^ {"null"}),
                ]
                mutations.extend(
                    (("properties", field_name, "type"), replacement)
                    for replacement in replacements
                )
        for path, replacement in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    path=path, replacement=replacement, compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = deepcopy(replacement)
                    parsed = _load_spec(_dump_spec(
                        spec, default_flow_style=flow_style,
                    ))
                    self.assertEqual(parsed, spec)
                    # Only the input declaration changes: route bindings,
                    # statuses, field names and all other components stay intact.
                    self.assertEqual(parsed["paths"], SPEC["paths"])
                    restored = deepcopy(parsed)
                    restored["components"]["schemas"][schema_name] = deepcopy(original)
                    self.assertEqual(restored, SPEC)
                    with patch.dict(globals(), SPEC=parsed):
                        self.assertEqual(
                            _property_names(schema_name), set(original["properties"]),
                        )
                        unchanged = unittest.TestResult()
                        ContractParityTests(
                            "test_turn_route_bindings_match_fastapi"
                        ).run(unchanged)
                        self.assertTrue(
                            unchanged.wasSuccessful(),
                            unchanged.failures + unchanged.errors,
                        )
                        result = unittest.TestResult()
                        ContractParityTests(
                            "test_health_and_request_schemas_match_runtime_models"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    expected_label = (
                        f"{schema_name}.required" if path == ("required",)
                        else f"{schema_name}.{path[1]}.type"
                    )
                    self.assertIn(expected_label, result.failures[0][1])

    def test_campaign_session_scalar_drift_fails_in_both_formats(self):
        schema_name = "CampaignSession"
        original = deepcopy(_schema(schema_name))
        mutations = []
        for field_name in ("campaign_id", "session_id", "name"):
            field = original["properties"][field_name]
            for replacement in (None, "integer", "boolean", "object", "array"):
                mutations.append((
                    ("properties", field_name, "type"), replacement,
                    f"{field_name}.type",
                ))
            mutations.append((
                ("properties", field_name, "type"), ["string", "null"],
                f"{field_name}.nullable",
            ))
            nullable_field = deepcopy(field)
            del nullable_field["type"]
            nullable_field["anyOf"] = [{"type": "string"}, {"type": "null"}]
            mutations.append((
                ("properties", field_name), nullable_field,
                f"{field_name}.nullable",
            ))
            mutations.append((
                ("required",),
                [name for name in original["required"] if name != field_name],
                f"{field_name}.required",
            ))
        for path, replacement, diagnostic in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    path=path, replacement=replacement, compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = deepcopy(replacement)
                    parsed = _load_spec(
                        _dump_spec(spec, default_flow_style=flow_style)
                    )
                    self.assertEqual(parsed, spec)
                    self.assertEqual(parsed["paths"], SPEC["paths"])
                    self.assertEqual(
                        set(parsed["components"]["schemas"][schema_name]["properties"]),
                        set(original["properties"]),
                    )
                    # Restoring the sole mutated declaration recovers the
                    # complete contract, including route and field inventories.
                    restored = deepcopy(parsed)
                    target = restored["components"]["schemas"][schema_name]
                    source = original
                    for key in path[:-1]:
                        target = target[key]
                        source = source[key]
                    target[path[-1]] = deepcopy(source[path[-1]])
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        ContractParityTests(
                            "test_campaign_session_scalar_fields_match_runtime_model"
                        ).run(result)
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    failed_test, failure = result.failures[0]
                    self.assertIn(
                        "test_campaign_session_scalar_fields_match_runtime_model",
                        failed_test.id(),
                    )
                    self.assertIn(f"{schema_name}.{diagnostic}", failure)

    def test_campaign_summary_scalar_drift_fails_in_both_formats(self):
        schema_name = "CampaignSummary"
        original = deepcopy(_schema(schema_name))
        mutations = [
            (("required",), None, "required"),
            (("required",), [], "required"),
            (("required",), [*original["required"], "unexpected"], "required"),
        ]
        mutations.extend(
            (("required",), [
                field for field in original["required"] if field != removed
            ], "required")
            for removed in original["required"]
        )
        for field_name, field in original["properties"].items():
            for replacement in (None, "string" if field["type"] == "integer" else "integer"):
                mutations.append((
                    ("properties", field_name, "type"), replacement, f"{field_name}.type",
                ))
            mutations.append((
                ("properties", field_name, "type"),
                [field["type"], "null"], f"{field_name}.nullable",
            ))
            nullable_field = deepcopy(field)
            del nullable_field["type"]
            nullable_field["anyOf"] = [
                {"type": field["type"]}, {"type": "null"},
            ]
            mutations.append((
                ("properties", field_name), nullable_field, f"{field_name}.nullable",
            ))
        for path, replacement, diagnostic in mutations:
            for flow_style in (False, True):
                with self.subTest(
                    path=path, replacement=replacement, compact=flow_style,
                ):
                    spec = deepcopy(SPEC)
                    target = spec["components"]["schemas"][schema_name]
                    for key in path[:-1]:
                        target = target[key]
                    if replacement is None:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = deepcopy(replacement)
                    parsed = _load_spec(
                        _dump_spec(spec, default_flow_style=flow_style)
                    )
                    self.assertEqual(parsed, spec)
                    self.assertEqual(parsed["paths"], SPEC["paths"])
                    self.assertEqual(
                        set(parsed["components"]["schemas"][schema_name]["properties"]),
                        set(original["properties"]),
                    )
                    # Restoring only the changed declaration recovers all
                    # inventories, route bindings and unrelated contract details.
                    restored = deepcopy(parsed)
                    target = restored["components"]["schemas"][schema_name]
                    source = original
                    for key in path[:-1]:
                        target = target[key]
                        source = source[key]
                    target[path[-1]] = deepcopy(source[path[-1]])
                    self.assertEqual(restored, SPEC)
                    result = unittest.TestResult()
                    with patch.dict(globals(), SPEC=parsed):
                        for test_name in (
                            "test_campaign_summary_scalar_fields_match_runtime_model",
                            "test_campaign_and_session_schema_fields_match_fastapi_models",
                            "test_campaign_detail_summary_reference_matches_runtime_model",
                            "test_campaign_read_route_bindings_match_fastapi",
                        ):
                            ContractParityTests(test_name).run(result)
                    self.assertEqual(result.testsRun, 4)
                    self.assertEqual(result.errors, [], result.errors)
                    self.assertEqual(len(result.failures), 1, result.failures)
                    failed_test, failure = result.failures[0]
                    self.assertIn(
                        "test_campaign_summary_scalar_fields_match_runtime_model",
                        failed_test.id(),
                    )
                    self.assertIn(f"{schema_name}.{diagnostic}", failure)
        self.assertEqual(_schema(schema_name), original)
class _DuplicateKeyLoaderMixin:
    """Reject duplicate keys instead of silently hiding contract declarations."""

    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(keys) != len(set(keys)):
            raise AssertionError("OpenAPI contains duplicate mapping keys")
        return super().construct_mapping(node, deep=deep)
def _published_schema_objects():
    for name in SPEC["components"]["schemas"]:
        yield from _nested_schema_objects(_schema(name), name)
    for path, item in SPEC["paths"].items():
        yield from _parameter_schema_objects(
            item.get("parameters", []), f"paths.{path}.parameters",
        )
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            label = f"paths.{path}.{method}"
            yield from _parameter_schema_objects(
                operation.get("parameters", []), f"{label}.parameters",
            )
            bodies = []
            if "requestBody" in operation:
                bodies.append((f"{label}.requestBody", operation["requestBody"]))
            bodies.extend(
                (f"{label}.responses.{status}", response)
                for status, response in operation.get("responses", {}).items()
            )
            for body_label, body in bodies:
                for media_type, media in body.get("content", {}).items():
                    if "schema" in media:
                        yield from _nested_schema_objects(
                            media["schema"], f"{body_label}.content.{media_type}.schema",
                        )

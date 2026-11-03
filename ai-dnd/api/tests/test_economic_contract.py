"""S1b: the published contract against what a real game session actually serializes.

A fake `SerializableSession` cannot prove the contract: the wallet, the open economic card, the economic
receipt and the bounded courtyard projection are only written for a real `game.GameSession`. Every example here
comes from a real session driven through the HTTP API (no model call on these paths), and is checked against the
OpenAPI components with a small validator over the JSON Schema keywords the contract uses.
"""

from __future__ import annotations

import json
import re
from typing import Any

import bounded_encounter
from api.serializers import serialize_session_state
from api.tests.test_bounded_encounter import NativeBase
from api.tests.test_contract_parity import SPEC
from api.tests.test_economic_action_http import ROOM, TIP, EconomicHttpFixture

NPC_BALANCE_CP = 98765

_JSON_TYPES = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: type(value) is int,
    "number": lambda value: type(value) in (int, float),
    "boolean": lambda value: type(value) is bool,
    "null": lambda value: value is None,
}


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        name = schema["$ref"].removeprefix("#/components/schemas/")
        schema = SPEC["components"]["schemas"][name]
    return schema


def contract_validation_errors(value: Any, schema: dict[str, Any] | str, path: str = "$") -> list[str]:
    """Every place `value` breaks the OpenAPI schema; an empty list means it matches."""
    if isinstance(schema, str):
        schema = SPEC["components"]["schemas"][schema]
    schema = _resolve(schema)
    if value is None and schema.get("nullable") is True:
        return []
    for keyword in ("anyOf", "oneOf"):
        if keyword in schema:
            branch_errors = [contract_validation_errors(value, branch, path) for branch in schema[keyword]]
            matches = sum(not errors for errors in branch_errors)
            if matches == 0:
                return [f"{path}: no {keyword} branch matches", *min(branch_errors, key=len)]
            if keyword == "oneOf" and matches > 1:
                return [f"{path}: {matches} oneOf branches match"]
    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: {value!r} is not const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']!r}")
    declared = schema.get("type")
    if declared is not None:
        types = declared if isinstance(declared, list) else [declared]
        if not any(_JSON_TYPES[name](value) for name in types):
            return [*errors, f"{path}: {type(value).__name__} is not {declared}"]
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required {name!r}")
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in properties:
                errors.extend(contract_validation_errors(item, properties[name], f"{path}.{name}"))
            elif extra is False:
                errors.append(f"{path}: unexpected property {name!r}")
            elif isinstance(extra, dict):
                errors.extend(contract_validation_errors(item, extra, f"{path}.{name}"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(contract_validation_errors(item, schema["items"], f"{path}[{index}]"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: does not match {schema['pattern']!r}")
    if type(value) in (int, float):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: not above {schema['exclusiveMinimum']}")
    return errors


class RealEconomicSession(EconomicHttpFixture):
    """The A3 card fixture with its NPCs written as whole records, the way a campaign stores them."""

    maxDiff = None

    async def asyncSetUp(self):
        await super().asyncSetUp()
        for npc in self.world["npcs"]:
            npc.update({"appearance": None, "relationship": "neutral", "max_hp": npc["current_hp"],
                        "armor_class": 10, "combat_status": "active", "tags": []})
        self.world["currency"]["barman"] = NPC_BALANCE_CP
        self.save()


class ValidatorCatchesDrift(RealEconomicSession):
    """The validator itself must fail on the drifts these checks rely on, or a green run proves nothing."""

    async def test_validator_rejects_extra_missing_and_mistyped_fields(self):
        state = (await self.http.get(f'/api/game/sessions/{self.campaign["session_id"]}/state')).json()
        self.assertEqual(contract_validation_errors(state, "GameState"), [])
        self.assertTrue(contract_validation_errors({**state, "private_npc_balances": {}}, "GameState"))
        self.assertTrue(contract_validation_errors({**state, "wallet": {"total_cp": "100"}}, "GameState"))
        self.assertTrue(contract_validation_errors({**state, "wallet": {}}, "GameState"))
        self.assertTrue(contract_validation_errors({**state, "economic_offer": {"offer_id": "x"}}, "GameState"))
        missing = dict(state)
        missing.pop("turn_index")
        self.assertTrue(contract_validation_errors(missing, "GameState"))


class RealSessionContract(RealEconomicSession):
    def state_url(self):
        return f'/api/game/sessions/{self.campaign["session_id"]}/state'

    def authoritative_player_cp(self):
        coins = [item for item in self.world.get("inventory", []) if "Altın" in str(item) or "Gümüş" in str(item)
                 or "Bakır" in str(item)]
        self.assertEqual(coins, [], "the authoritative purse here is the currency entry alone")
        return self.world["currency"]["player"]

    def assert_public_state(self, public_state):
        self.assertEqual(contract_validation_errors(public_state, "GameState"), [])
        self.assertEqual(public_state["wallet"]["total_cp"], self.authoritative_player_cp())
        self.assertNotIn("private_npc_balances", public_state)

    async def test_real_state_matches_public_schema(self):
        response = await self.http.get(self.state_url())
        self.assertEqual(response.status_code, 200, response.text)
        public_state = response.json()
        self.assert_public_state(public_state)
        self.assertEqual(public_state, json.loads(json.dumps(serialize_session_state(self.record.game_session))))
        self.assertIn("wallet", public_state)
        self.assertIn("economic_offer", public_state)
        self.assertIsNone(public_state["economic_offer"])
        self.assertNotIn("bounded_encounter", public_state)

    async def test_economic_prepare_confirm_refused_examples_match_schema(self):
        prepare_body = {"message": "Teklif hazırla", "action_id": "", "economic_action": {"kind": "prepare",
                                                                                       "proposal": TIP}}
        with self.subTest("prepare"):
            response, body = await self.act({"kind": "prepare", "proposal": TIP}, "Teklif hazırla")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(contract_validation_errors(body, "GameTurnInput"), [])
            prepared = response.json()
            self.assertEqual(contract_validation_errors(prepared, "GameTurnResult"), [])
            card = prepared["state"]["economic_offer"]
            self.assertIsNotNone(card)
            self.assertEqual(contract_validation_errors(card, "PublicEconomicOffer"), [])
            self.assert_public_state(prepared["state"])
        with self.subTest("confirm applied"):
            applied, body = await self.confirm(card)
            self.assertEqual(contract_validation_errors(body, "GameTurnInput"), [])
            self.assertEqual(applied["economic_resolution"]["status"], "applied")
            self.assertEqual(contract_validation_errors(applied, "GameTurnResult"), [])
            self.assertEqual(contract_validation_errors(applied["economic_resolution"], "PublicEconomicResolution"), [])
            self.assertIsNone(applied["state"]["economic_offer"])
            self.assert_public_state(applied["state"])
            self.assertEqual(applied["state"]["wallet"]["total_cp"], 96)
        with self.subTest("confirm refused"):
            card = await self.card(**ROOM)
            self.world["currency"]["player"] = 40
            refused, body = await self.confirm(card)
            resolution = refused["economic_resolution"]
            self.assertEqual((resolution["status"], resolution["reason_code"]), ("refused", "no_money"))
            self.assertEqual(contract_validation_errors(refused, "GameTurnResult"), [])
            self.assertEqual(contract_validation_errors(resolution, "PublicEconomicResolution"), [])
            self.assert_public_state(refused["state"])
            self.assertEqual(refused["state"]["wallet"]["total_cp"], 40)
        with self.subTest("cancel"):
            card = await self.card(**TIP)
            cancelled = await self.cancel(card["offer_id"])
            self.assertEqual(contract_validation_errors(cancelled, "GameTurnResult"), [])
            self.assertIsNone(cancelled["state"]["economic_offer"])
            self.assert_public_state(cancelled["state"])
        self.assertTrue(contract_validation_errors(prepare_body, "GameTurnInput"), "an empty action id is not valid")

    async def test_public_state_has_no_private_npc_balances(self):
        card = await self.card(purpose="gift", recipient_id="barman", amount_cp=10)
        public_state = (await self.http.get(self.state_url())).json()
        self.assertEqual(public_state["economic_offer"]["offer_id"], card["offer_id"])
        self.assert_public_state(public_state)
        text = json.dumps(public_state, ensure_ascii=False)
        self.assertNotIn(str(NPC_BALANCE_CP), text)
        self.assertNotIn("currency", text)
        self.assertNotIn("acceptance", text)
        for npc in public_state["npcs"]:
            self.assertNotIn("currency", npc)
            self.assertNotIn("balance_cp", npc)
        self.assertEqual(self.world["currency"]["barman"], NPC_BALANCE_CP)


class BoundedEncounterContract(NativeBase):
    maxDiff = None
    def public_state(self):
        response = self.client.get(f"/api/sessions/{self.sid}/state")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_bounded_encounter_present_and_absent_match_schema(self):
        with self.subTest("absent before entry: no key, never null"):
            before = self.public_state()
            self.assertNotIn("bounded_encounter", before)
            self.assertEqual(contract_validation_errors(before, "GameState"), [])
        with self.subTest("present after entry"):
            self.enter()
            entered = self.public_state()
            self.assertIn("bounded_encounter", entered)
            projection = entered["bounded_encounter"]
            self.assertEqual(projection, bounded_encounter.public_projection(self.session))
            self.assertEqual(projection["player_node_id"], "courtyard_entry")
            self.assertEqual(contract_validation_errors(entered, "GameState"), [])
        with self.subTest("opponent visible during contact"):
            result = self.walk_to_contact()
            self.assertEqual(contract_validation_errors(result, "GameTurnResult"), [])
            seen = self.public_state()
            self.assertIsNotNone(seen["bounded_encounter"]["visible_opponent"])
            self.assertEqual(contract_validation_errors(seen, "GameState"), [])
        with self.subTest("authored nodes are the published node enum"):
            schemas = SPEC["components"]["schemas"]
            for enum in (schemas["BoundedEncounterOpponent"]["properties"]["node_id"]["enum"],
                         schemas["GameScenePlayerPosition"]["properties"]["bounded_node_id"]["enum"],
                         schemas["BoundedEncounterProjection"]["properties"]["player_node_id"]["anyOf"][0]["enum"]):
                self.assertEqual(set(enum), set(bounded_encounter.NODES))
        with self.subTest("the schema refuses null and unknown fields"):
            self.assertTrue(contract_validation_errors({**seen, "bounded_encounter": None}, "GameState"))
            self.assertTrue(contract_validation_errors(
                {**seen, "bounded_encounter": {**seen["bounded_encounter"], "npc_ai": {}}}, "GameState"))

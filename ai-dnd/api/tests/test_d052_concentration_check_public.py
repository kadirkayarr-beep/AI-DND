"""D-052: the engine's Concentration save after an enemy's damage is a field of the public combat result
(`concentration_check` on the enemy action), not only a narration line, so the combat event strip can show it.

The field is what `spell_concentration.after_damage` returned for that damage instance: the Constitution save
({"spell_id", "dc", "roll", "total", "kept"}, plus "bless_roll" when Bless added its d4) or the outright end
({"spell_id", "kept": False, "reason"}). It is absent when nothing was held. The combat history entry carries the same
result, and Geri Al takes the turn back with the Concentration it broke.

Before the fix the free-text attack's counterattack (top-level `enemy_action`/`enemy_actions`) dropped the field in
`serialize_combat_result`; the economy path's `economy_steps` already carried it (guarded below).

Harness: the Bless-over-HTTP fight of test_dilim4c_spell_resolvers_http (fixed town, level-1 Cleric, one guard)."""
from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from api.tests import test_dilim4c_spell_resolvers_http as bless_http

KEY = "spell_concentration_v1"
SAVE_FIELDS = {"spell_id", "dc", "roll", "total", "kept"}


class ConcentrationCheckPublic(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = bless_http.SpellResolversHttp.asyncSetUp
    asyncTearDown = bless_http.SpellResolversHttp.asyncTearDown
    fight = bless_http.SpellResolversHttp.fight
    post = bless_http.SpellResolversHttp.post

    async def counterattack(self, seed, rolls, *, held=True):
        """The player swings and misses (free-text attack); the guard's counterattack hits for 1."""
        campaign, record = await self.fight(seed)
        s = record.game_session
        next(n for n in s.world_state["npcs"] if n.get("hostile"))["distance_ft"] = 5
        if held:
            combat = s.world_state["combat"]
            s.world_state[KEY] = {"spell_id": "Bless", "combat_id": combat["combat_id"],
                                  "started_round": combat["round"], "slot_level": 1, "targets": ["player"]}
        body = {"message": "Ona saldırıyorum", "action_id": str(uuid4())}
        rolls = iter(rolls)
        with patch("game.roll_d20", side_effect=lambda *a, **k: next(rolls)), patch.object(s.rng, "randint", return_value=1):
            sent = await self.post(campaign, body)
        self.assertEqual(sent.status_code, 200, sent.text)
        result = sent.json()["combat_result"]
        self.assertEqual((result["action"], result["outcome"]), ("attack", "miss"))
        self.assertEqual([a["outcome"] for a in result["enemy_actions"]], ["hit"])
        return campaign, s, body, sent.json()

    async def test_a_failed_save_is_in_the_combat_result_and_its_history_entry(self):
        campaign, s, body, sent = await self.counterattack(7311, [2, 19] + [2] * 20)  # the save fails
        self.assertIsNone(s.world_state[KEY])
        result = sent["combat_result"]
        check = result["enemy_actions"][0]["concentration_check"]
        self.assertEqual(set(check), SAVE_FIELDS | {"bless_roll"})
        self.assertEqual({k: check[k] for k in ("spell_id", "dc", "roll", "kept", "bless_roll")},
                         {"spell_id": "Bless", "dc": 10, "roll": 2, "kept": False, "bless_roll": 1})
        self.assertLess(check["total"], check["dc"])
        self.assertEqual(result["enemy_action"]["concentration_check"], check)
        self.assertEqual(sent["combat_history_entry"]["result"]["enemy_actions"][0]["concentration_check"], check)
        undone = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/undo",
                                      json={"action_id": str(uuid4()), "target_action_id": body["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertIsNotNone(s.world_state[KEY])  # Geri Al gives the Concentration back
        self.assertEqual(undone.json()["state"]["concentration"]["spell_id"], "Bless")

    async def test_a_kept_save_is_in_the_combat_result(self):
        _, s, _, sent = await self.counterattack(7312, [2, 19] + [18] * 20)  # the save holds
        self.assertIsNotNone(s.world_state[KEY])
        check = sent["combat_result"]["enemy_actions"][0]["concentration_check"]
        self.assertEqual({k: check[k] for k in ("spell_id", "dc", "roll", "kept")},
                         {"spell_id": "Bless", "dc": 10, "roll": 18, "kept": True})
        self.assertGreaterEqual(check["total"], check["dc"])

    async def test_no_field_when_nothing_was_held(self):
        _, _, _, sent = await self.counterattack(7313, [2, 19] + [2] * 20, held=False)
        self.assertNotIn("concentration_check", sent["combat_result"]["enemy_actions"][0])
        self.assertNotIn("concentration_check", sent["combat_result"]["enemy_action"])

    async def test_the_economy_path_keeps_carrying_it(self):
        """Guard: the end-turn path already carried the save inside `economy_steps` before D-052's fix."""
        campaign, record = await self.fight(7315)
        s = record.game_session
        next(n for n in s.world_state["npcs"] if n.get("hostile"))["distance_ft"] = 5
        cast = await self.post(campaign, {"message": "Hamle.", "action_id": str(uuid4()), "combat_action": {
            "steps": [{"kind": "magic", "ability": "Bless", "target_id": "player"}]}})
        self.assertEqual(cast.status_code, 200, cast.text)
        rolls = iter([19] + [2] * 20)
        with patch("game.roll_d20", side_effect=lambda *a, **k: next(rolls)), patch.object(s.rng, "randint", return_value=1):
            ended = await self.post(campaign, {"message": "Hamle.", "action_id": str(uuid4()),
                                               "combat_action": {"steps": [{"kind": "end_turn"}]}})
        self.assertEqual(ended.status_code, 200, ended.text)
        checks = [a["concentration_check"] for step in ended.json()["combat_result"]["economy_steps"]
                  for a in step.get("enemy_actions") or [] if "concentration_check" in a]
        self.assertEqual([{k: c[k] for k in ("spell_id", "dc", "kept")} for c in checks],
                         [{"spell_id": "Bless", "dc": 10, "kept": False}])


class ConcentrationCheckContract(unittest.TestCase):
    """openapi.yaml publishes the same ConcentrationCheckResult the serializer validates against."""

    def test_schema_matches_the_runtime_model(self):
        from api.schemas import CombatAttackResult, CombatTurnResult, ConcentrationCheckResult
        from api.tests import test_contract_parity as parity
        runtime = ConcentrationCheckResult.model_json_schema()
        name = "ConcentrationCheckResult"
        self.assertEqual(parity._property_names(name), set(runtime["properties"]))
        self.assertEqual(set(parity._schema(name)["required"]), set(runtime["required"]))
        self.assertIs(parity._schema(name)["additionalProperties"], False)
        for field, prop in runtime["properties"].items():
            with self.subTest(field=field):
                published = parity._property(name, field)
                self.assertEqual(parity._is_nullable(published), parity._is_nullable(prop))
                branches = [prop, *prop.get("anyOf", [])]
                for bound in ("minimum", "maximum"):
                    self.assertEqual(published.get(bound), next((b[bound] for b in branches if bound in b), None))
                enum = {v for b in branches for v in b.get("enum", [])}
                self.assertEqual(parity._enum_values(name, field) - {None}, enum)
        for model in (CombatAttackResult, CombatTurnResult):
            with self.subTest(model=model.__name__):
                field = model.model_json_schema(ref_template="#/components/schemas/{model}")["properties"][
                    "concentration_check"]
                published = parity._property(model.__name__, "concentration_check")
                self.assertEqual(parity._schema_references(published), {f"#/components/schemas/{name}"})
                self.assertEqual(parity._schema_references(field), {f"#/components/schemas/{name}"})
                self.assertTrue(parity._is_nullable(published))


if __name__ == "__main__":
    unittest.main()

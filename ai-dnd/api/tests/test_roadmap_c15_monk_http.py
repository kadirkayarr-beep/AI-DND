"""Public Monk 1-5: catalog fail-closed per row, creation, earned level-up and the typed commands through the real ASGI app.

Synthetic SQLite campaigns; a refusal is pinned by status and by the absence of any change.
"""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import character_progression as cp
import xp
from pydantic import ValidationError
from api.dnd_2024_rules import get_character_creation_catalog
from api.schemas import CharacterCreateInput, CharacterCreationCatalogResponse, EconomyStepInput, LevelUpApplyRequest
from api.tests import test_roadmap_c14_fighter_http as fighter_http
from api.tests.test_roadmap_c15_monk import CHOICES, THRESHOLDS, bundle, spec


def request(level):
    value = spec()
    value["class"] = value.pop("character_class")
    value.update(mode="custom", starting_level=level, level_choices=bundle(level) if level > 1 else None)
    return value


class Catalog(unittest.TestCase):
    def options(self, mutate=None):
        real = cp.table

        def patched(name):
            table = copy.deepcopy(real(name))
            if name == "Monk" and mutate:
                mutate(table)
            return table
        with patch.object(cp, "table", side_effect=patched):
            return cp.monk_starting_creation_options()

    def test_the_verified_catalog_offers_one_to_five(self):
        options = get_character_creation_catalog()["monk_starting_creation"]
        self.assertEqual(options["supported_starting_levels"], [1, 2, 3, 4, 5])
        self.assertEqual(options["level_3"]["subclass_options"], [{"id": "open_hand", "name": "Warrior of the Open Hand"}])
        self.assertEqual(len(options["level_4"]["supported_asi_choices"]), 15)
        self.assertIn("Stunning Strike", " ".join(options["level_5"]["effects_supported"]))
        self.assertIn("Higher-start equipment", " ".join(options["level_5"]["effects_pending"]))
        CharacterCreationCatalogResponse.model_validate(get_character_creation_catalog())

    def test_a_bad_row_hides_that_level_and_everything_above(self):
        cases = [("1", 1), ("2", 1), ("3", 2), ("4", 3), ("5", 4)]
        faults = [lambda row: row.update(features=["Fake"]), lambda row: row.update(martial_arts_die=True),
                  lambda row: row.update(martial_arts_die=12), lambda row: row.update(focus_points=9),
                  lambda row: row.update(unarmored_movement_ft=30), lambda row: row.update(proficiency_bonus=7),
                  lambda row: row.update(slots={"1": 2}), lambda row: row.pop("focus_points")]
        for key, reachable in cases:
            for index, fault in enumerate(faults):
                with self.subTest(row=key, fault=index):
                    options = self.options(lambda table: fault(table["levels"][key]))
                    if reachable == 1:
                        self.assertIsNone(options)
                    else:
                        self.assertEqual(options["supported_starting_levels"], list(range(1, reachable + 1)))
                        self.assertNotIn(f"level_{reachable + 1}", options)

    def test_a_missing_subclass_source_hides_level_three_and_above(self):
        self.assertEqual(self.options(lambda table: table.pop("subclass_options"))["supported_starting_levels"], [1, 2])


class CreationSchema(unittest.TestCase):
    def test_exact_bundles_parse(self):
        for level in range(2, 6):
            CharacterCreateInput.model_validate(request(level))

    def test_a_bundle_of_the_wrong_class_or_length_is_refused(self):
        bad = [{**request(3), "level_choices": {"2": {}, "3": {"subclass_id": "champion"}}},
               {**request(3), "level_choices": {"2": {}, "3": {"subclass_id": "berserker", "primal_knowledge_skill": "Nature"}}},
               {**request(3), "level_choices": {"2": {}}}, {**request(2), "level_choices": None},
               {**request(4), "level_choices": {"2": {}, "3": {"subclass_id": "open_hand"}}},
               {**request(5), "level_choices": {"2": {}, "3": {"subclass_id": "open_hand"}, "4": CHOICES["4"], "5": {"x": 1}}}]
        for value in bad:
            with self.subTest(value["level_choices"]), self.assertRaises(ValidationError):
                CharacterCreateInput.model_validate(value)

    def test_the_level_three_body_reaches_the_level_up_request(self):
        body = {"action_id": str(uuid4()), "campaign_id": str(uuid4()), "expected_revision": 1, "target_level": 3, "choices": {"subclass_id": "open_hand"}}
        self.assertEqual(LevelUpApplyRequest.model_validate(body).choices.subclass_id, "open_hand")


class StepSchema(unittest.TestCase):
    def test_monk_fields_stay_on_their_steps(self):
        for step in ({"kind": "patient_defense", "target_id": "x", "stunning_strike": True}, {"kind": "move", "distance_ft": 5, "spend_focus": True},
                     {"kind": "attack", "open_hand_technique": "push"}, {"kind": "attack", "deflect_mode": "off"},
                     {"kind": "set_deflect_attacks"}, {"kind": "set_deflect_attacks", "deflect_mode": "always"},
                     {"kind": "flurry_of_blows"}, {"kind": "flurry_of_blows", "target_id": "x", "open_hand_technique": "addle"},
                     {"kind": "step_of_the_wind", "spend_focus": 1}, {"kind": "patient_defense", "spend_focus": "true"}):
            with self.subTest(step), self.assertRaises(ValidationError):
                EconomyStepInput.model_validate(step)

    def test_the_good_shapes_parse(self):
        for step in ({"kind": "flurry_of_blows", "target_id": "x", "open_hand_technique": "topple", "stunning_strike": True},
                     {"kind": "attack", "target_id": "x", "stunning_strike": True}, {"kind": "patient_defense", "spend_focus": True},
                     {"kind": "step_of_the_wind"}, {"kind": "set_deflect_attacks", "deflect_mode": "off"}, {"kind": "uncanny_metabolism"}):
            EconomyStepInput.model_validate(step)


class MonkRoutes(unittest.IsolatedAsyncioTestCase):
    """The Fighter fixture's campaign helpers with a Monk request."""
    asyncSetUp = fighter_http.FighterHttp.asyncSetUp
    asyncTearDown = fighter_http.FighterHttp.asyncTearDown
    reopen = fighter_http.FighterHttp.reopen
    snapshot = fighter_http.FighterHttp.snapshot
    url = fighter_http.FighterHttp.url
    preview = fighter_http.FighterHttp.preview
    command = fighter_http.FighterHttp.command
    post = fighter_http.FighterHttp.post
    encounter = fighter_http.FighterHttp.encounter

    async def create(self, level=1):
        response = await self.http.post("/api/game/campaigns", json={"character": request(level)})
        self.assertEqual(response.status_code, 200, response.text)
        campaign = response.json()
        return campaign, self.manager.get(campaign["session_id"])

    def award(self, campaign, record, level):
        session = record.game_session
        gained = THRESHOLDS[level] - session.character["xp"]
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, f"quest:synthetic-monk-{level}")
        self.manager.save_campaign(campaign["campaign_id"])

    async def step(self, campaign, step, label="Monk"):
        return await self.post(campaign, {"message": label, "action_id": str(uuid4()), "combat_action": {"steps": [step]}})

    async def fight(self, level):
        campaign, record = await self.encounter(level)
        npc = next(n for n in record.game_session.world_state["npcs"] if n.get("name") == "Rakip")
        return campaign, record, npc

    async def test_every_start_is_created_stored_and_projected(self):
        for level in range(1, 6):
            campaign, record = await self.create(level)
            character = campaign["state"]["character"]
            self.assertEqual(character["monk"]["martial_arts_die"], 8 if level == 5 else 6, level)
            self.assertEqual(character["monk"]["focus"] is None, level == 1)
            self.assertEqual(character["armor_class"], 15)
            self.assertIn("Slow Fall" if level >= 4 else "Martial Arts", " ".join(character["progression_effects_pending"]))

    async def test_earned_steps_one_to_five_through_the_public_route(self):
        campaign, record = await self.create()
        for level in range(2, 6):
            self.award(campaign, record, level)
            preview = await self.preview(campaign)
            self.assertEqual((preview["status"], preview["target_level"], preview["class_name"]), ("ready", level, "Monk"), preview)
            body = self.command(campaign, copy.deepcopy(CHOICES[str(level)]), preview)
            response = await self.http.post(self.url(campaign), json=body)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(record.game_session.character["progression_level"], level)
            before = self.snapshot(record)
            with patch("character_progression.apply_level_choices", side_effect=AssertionError("old receipt reapplied")):
                replay = await self.http.post(self.url(campaign), json=body)
            self.assertEqual(replay.json(), response.json())
            self.assertEqual(self.snapshot(record), before)
        final = await self.preview(campaign)
        self.assertEqual((final["status"], final["reason"]), ("blocked", "target_not_above_applied_level"))

    async def test_a_wrong_class_level_three_body_is_refused(self):
        campaign, record = await self.create(2)
        self.award(campaign, record, 3)
        preview = await self.preview(campaign)
        before = self.snapshot(record)
        response = await self.http.post(self.url(campaign), json=self.command(campaign, {"subclass_id": "champion"}, preview))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "level_up_choice_class_mismatch")
        self.assertEqual(self.snapshot(record), before)

    async def test_flurry_is_receipted_replayed_and_finished_by_its_second_strike(self):
        campaign, record, npc = await self.fight(2)
        body = {"message": "Flurry", "action_id": str(uuid4()), "combat_action": {"steps": [{"kind": "flurry_of_blows", "target_id": npc["id"]}]}}
        with patch("game.roll_attack", return_value=1):
            response = await self.post(campaign, body)
        self.assertEqual(response.status_code, 200, response.text)
        monk = response.json()["state"]["character"]["monk"]
        self.assertEqual((monk["focus"]["points_remaining"], monk["flurry_strikes_remaining"]), (1, 1))
        before = self.snapshot(record)
        with patch("monk_features.run_step", side_effect=AssertionError("replayed")):
            replay = await self.post(campaign, body)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(self.snapshot(record), before)
        with patch("game.roll_attack", return_value=1):
            second = await self.step(campaign, {"kind": "flurry_strike", "target_id": npc["id"]})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["state"]["character"]["monk"]["flurry_strikes_remaining"], 0)

    async def test_a_refused_step_changes_nothing_and_says_why(self):
        campaign, record, npc = await self.fight(1)
        before = self.snapshot(record)
        response = await self.step(campaign, {"kind": "patient_defense", "spend_focus": True})
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (400, "focus_not_available"))
        self.assertEqual(self.snapshot(record), before)

    async def test_step_of_the_wind_and_the_settings_reach_the_public_state(self):
        campaign, record, npc = await self.fight(3)
        response = await self.step(campaign, {"kind": "step_of_the_wind", "spend_focus": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"]["character"]["monk"]["focus"]["points_remaining"], 2)
        response = await self.step(campaign, {"kind": "set_deflect_attacks", "deflect_mode": "redirect"})
        self.assertEqual(response.json()["state"]["character"]["monk"]["deflect_mode"], "redirect")

    async def test_a_stunning_strike_flag_reaches_the_attack_owner(self):
        campaign, record, npc = await self.fight(5)
        npc["armor_class"] = 5
        with patch("game.roll_attack", return_value=15), patch("game.roll_d20", return_value=1):
            response = await self.step(campaign, {"kind": "attack", "target_id": npc["id"], "stunning_strike": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"]["character"]["monk"]["focus"]["points_remaining"], 4)
        self.assertIn("stunned", npc["conditions"])

    async def test_fresh_resume_keeps_the_applied_state(self):
        campaign, record = await self.create(3)
        record.game_session.character["monk_state"] = {"focus_spent": 1, "metabolism_spent": True, "deflect": "redirect"}
        self.manager.save_campaign(campaign["campaign_id"])
        body, manager = await self.reopen(campaign)
        fresh = manager.get(body["session_id"]).game_session.character
        self.assertEqual(fresh["monk_state"], {"focus_spent": 1, "metabolism_spent": True, "deflect": "redirect"})
        self.assertEqual(fresh["subclass_id"], "open_hand")
        self.assertEqual(body["state"]["character"]["monk"]["focus"]["points_remaining"], 2)


if __name__ == "__main__":
    unittest.main()

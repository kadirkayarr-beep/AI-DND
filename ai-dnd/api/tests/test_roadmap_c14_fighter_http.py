"""Public Fighter 1-5: catalog fail-closed per row, creation, earned level-up and the two typed commands through the real ASGI app.

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
from api.schemas import CharacterCreateInput, CharacterCreationCatalogResponse, LevelUpApplyRequest
from api.tests import test_campaign_api as campaigns
from api.tests import test_roadmap_c06_level4_http as prior
from api.tests import test_roadmap_c10_berserker_http as berserker
from api.tests import test_roadmap_c19_quickened_http as quickened
from api.tests.test_roadmap_c14_fighter import CHOICES, THRESHOLDS, bundle, spec


def request(level, style="Defense"):
    value = spec(style)
    value["class"] = value.pop("character_class")
    value.update(mode="custom", starting_level=level, level_choices=bundle(level) if level > 1 else None)
    return value


class Catalog(unittest.TestCase):
    def options(self, mutate=None):
        real = cp.table

        def patched(name):
            table = copy.deepcopy(real(name))
            if name == "Fighter" and mutate:
                mutate(table)
            return table
        with patch.object(cp, "table", side_effect=patched):
            return cp.fighter_starting_creation_options()

    def test_the_verified_catalog_offers_one_to_five(self):
        options = get_character_creation_catalog()["fighter_starting_creation"]
        self.assertEqual(options["supported_starting_levels"], [1, 2, 3, 4, 5])
        self.assertEqual(options["level_2"]["choices"], {})
        self.assertEqual(options["level_3"]["subclass_options"], [{"id": "champion", "name": "Champion"}])
        self.assertEqual(len(options["level_4"]["supported_asi_choices"]), 21)
        self.assertIn("Tactical Shift", " ".join(options["level_5"]["effects_supported"]))
        self.assertIn("Higher-start equipment", " ".join(options["level_5"]["effects_pending"]))
        CharacterCreationCatalogResponse.model_validate(get_character_creation_catalog())

    def test_a_bad_row_hides_that_level_and_everything_above(self):
        cases = [("1", 1), ("2", 1), ("3", 2), ("4", 3), ("5", 4)]
        faults = [lambda row: row.update(features=["Fake"]), lambda row: row.update(second_wind=True), lambda row: row.update(weapon_mastery=9),
                  lambda row: row.update(proficiency_bonus=7), lambda row: row.update(slots={"1": 2})]
        for key, reachable in cases:
            for fault in faults:
                with self.subTest(row=key):
                    options = self.options(lambda table: fault(table["levels"][key]))
                    if reachable == 1:
                        self.assertIsNone(options)
                    else:
                        self.assertEqual(options["supported_starting_levels"], list(range(1, reachable + 1)))
                        self.assertNotIn(f"level_{reachable + 1}", options)

    def test_a_missing_subclass_source_hides_level_three_and_above(self):
        options = self.options(lambda table: table.pop("subclass_options"))
        self.assertEqual(options["supported_starting_levels"], [1, 2])


class CreationSchema(unittest.TestCase):
    def test_exact_bundles_parse(self):
        for level in range(2, 6):
            CharacterCreateInput.model_validate(request(level))

    def test_a_bundle_of_the_wrong_class_or_length_is_refused(self):
        bad = [{**request(3), "level_choices": {"2": {}, "3": {"subclass_id": "berserker", "primal_knowledge_skill": "Nature"}}},
               {**request(3), "level_choices": {"2": {}}}, {**request(2), "level_choices": None},
               {**request(4), "level_choices": {"2": {}, "3": {"subclass_id": "champion"}}},
               {**request(5), "level_choices": {"2": {}, "3": {"subclass_id": "champion"}, "4": CHOICES["4"], "5": {"x": 1}}}]
        for value in bad:
            with self.subTest(value["level_choices"]), self.assertRaises(ValidationError):
                CharacterCreateInput.model_validate(value)
        barbarian = {**request(3), "class": "Barbarian", "level_choices": {"2": {}, "3": {"subclass_id": "champion"}}}
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate(barbarian)

    def test_level_up_body_shapes(self):
        base = {"action_id": str(uuid4()), "campaign_id": str(uuid4()), "expected_revision": 0}
        LevelUpApplyRequest.model_validate({**base, "target_level": 3, "choices": {"subclass_id": "champion"}})
        for choices in ({"subclass_id": "battle-master"}, {"subclass_id": "champion", "x": 1}):
            with self.assertRaises(ValidationError):
                LevelUpApplyRequest.model_validate({**base, "target_level": 3, "choices": choices})
        with self.assertRaises(ValidationError):
            LevelUpApplyRequest.model_validate({**base, "target_level": 4, "choices": {"subclass_id": "champion"}})


class FighterHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown
    reopen = prior.LevelFourHttpTests.reopen
    snapshot = berserker.BerserkerHttpTests.snapshot
    url = berserker.BerserkerHttpTests.url
    preview = berserker.BerserkerHttpTests.preview
    command = berserker.BerserkerHttpTests.command
    post = quickened.QuickenedHttpTests.post

    async def create(self, level=1, style="Defense"):
        response = await self.http.post("/api/game/campaigns", json={"character": request(level, style)})
        self.assertEqual(response.status_code, 200, response.text)
        campaign = response.json()
        return campaign, self.manager.get(campaign["session_id"])

    def award(self, campaign, record, level):
        session = record.game_session
        gained = THRESHOLDS[level] - session.character["xp"]
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, f"quest:synthetic-fighter-{level}")
        self.manager.save_campaign(campaign["campaign_id"])

    async def level_up(self, campaign, record, level, choices=None):
        self.award(campaign, record, level)
        preview = await self.preview(campaign)
        self.assertEqual((preview["status"], preview["target_level"], preview["class_name"]), ("ready", level, "Fighter"), preview)
        body = self.command(campaign, copy.deepcopy(CHOICES[str(level)]) if choices is None else choices, preview)
        return preview, body, await self.http.post(self.url(campaign), json=body)

    async def encounter(self, level=2):
        campaign, record = await self.create(level)
        session = record.game_session
        session.commit_location_change("tavern")
        session.character.update(max_hp=60, current_hp=30)
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": "tavern"})
        npc.update(current_hp=100, max_hp=100, armor_class=20, hostile=True, distance_ft=5)
        session.world_state.setdefault("monster_perception", {})[npc["id"]] = {"player": {"visible": True}}
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            session.start_combat(npc)
        self.manager.save_campaign(campaign["campaign_id"])
        return campaign, record

    async def test_every_start_is_created_stored_and_projected(self):
        for level in range(1, 6):
            campaign, record = await self.create(level)
            character = campaign["state"]["character"]
            self.assertEqual(character["fighter"]["second_wind"]["max_uses"], 3 if level >= 4 else 2, level)
            self.assertEqual(character["fighter"]["fighting_style"], "Defense")
            self.assertEqual(character["fighter"]["action_surge"] is None, level == 1)
            self.assertIn("Weapon Mastery", " ".join(character["progression_effects_pending"]))
            self.assertEqual(record.game_session.character["progression_level"] if level > 1 else 1, level)

    async def test_a_removed_style_is_refused_at_creation(self):
        response = await self.http.post("/api/game/campaigns", json={"character": request(1, "Protection")})
        self.assertIn(response.status_code, (400, 422), response.text)

    async def test_earned_steps_one_to_five_through_the_public_route(self):
        campaign, record = await self.create()
        for level in range(2, 6):
            preview, body, response = await self.level_up(campaign, record, level)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["state"]["character"]["level"], level)
            self.assertEqual(record.game_session.character["progression_level"], level)
            before = self.snapshot(record)
            with patch("character_progression.apply_level_choices", side_effect=AssertionError("old receipt reapplied")):
                replay = await self.http.post(self.url(campaign), json=body)
            self.assertEqual(replay.json(), response.json())
            self.assertEqual(self.snapshot(record), before)
        final = await self.preview(campaign)
        self.assertEqual((final["status"], final["reason"]), ("blocked", "target_not_above_applied_level"))

    async def test_preview_offers_the_subclass_and_a_wrong_class_body_is_refused(self):
        campaign, record = await self.create(2)
        self.award(campaign, record, 3)
        preview = await self.preview(campaign)
        self.assertEqual(preview["subclass_options"], [{"id": "champion", "name": "Champion"}])
        before = self.snapshot(record)
        response = await self.http.post(self.url(campaign), json=self.command(
            campaign, {"subclass_id": "berserker", "primal_knowledge_skill": "Nature"}, preview))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "level_up_choice_class_mismatch")
        self.assertEqual(self.snapshot(record), before)

    async def test_an_unearned_step_is_blocked(self):
        campaign, _ = await self.create()
        preview = await self.preview(campaign)
        self.assertEqual((preview["status"], preview["reason"]), ("blocked", "level_not_earned"))

    async def test_second_wind_command_is_receipted_and_replayed(self):
        campaign, record = await self.encounter()
        body = {"message": "Second Wind", "action_id": str(uuid4()), "combat_action": {"steps": [{"kind": "second_wind", "resource": "bonus"}]}}
        with patch.object(record.game_session.rng, "randint", return_value=6):
            response = await self.post(campaign, body)
        self.assertEqual(response.status_code, 200, response.text)
        fighter = response.json()["state"]["character"]["fighter"]
        self.assertEqual(fighter["second_wind"]["uses_remaining"], 1)
        self.assertEqual(response.json()["state"]["character"]["current_hp"], 38)
        before = self.snapshot(record)
        with patch("fighter_features.activate_second_wind", side_effect=AssertionError("replayed")):
            replay = await self.post(campaign, body)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(self.snapshot(record), before)

    async def test_action_surge_command_shape(self):
        campaign, record = await self.encounter()
        before = self.snapshot(record)
        for step in ({"kind": "action_surge", "resource": "bonus"}, {"kind": "second_wind"}, {"kind": "second_wind", "resource": "action"},
                     {"kind": "second_wind", "resource": "bonus", "target_id": "x"}):
            response = await self.post(campaign, {"message": "x", "action_id": str(uuid4()), "combat_action": {"steps": [step]}})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.snapshot(record), before)
        response = await self.post(campaign, {"message": "Action Surge", "action_id": str(uuid4()), "combat_action": {"steps": [{"kind": "action_surge"}]}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"]["character"]["fighter"]["action_surge"]["uses_remaining"], 0)

    async def test_second_wind_outside_combat_through_the_trait_route(self):
        campaign, record = await self.create(2)
        session = record.game_session
        session.commit_location_change("tavern")
        session.character.update(max_hp=60, current_hp=30)
        self.manager.save_campaign(campaign["campaign_id"])
        with patch.object(session.rng, "randint", return_value=6):
            response = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/species-actions",
                                            json={"action": "second_wind", "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"]["character"]["fighter"]["second_wind"]["uses_remaining"], 1)

    async def checked(self, level, *, d20=5, d10=6, dc=None):
        from api.tests.test_campaign_api import ControlledVenueOllamaClient
        campaign, record = await self.create(level)
        session = record.game_session
        session.commit_location_change("tavern")
        self.manager.save_campaign(campaign["campaign_id"])
        narrator = ControlledVenueOllamaClient("narrative")
        body = {"message": "Takla atıyorum", "interaction_mode": "do", "action_id": str(uuid4()), "check_feature": "tactical_mind"}
        with patch("api.tests.test_campaign_api.FakeOllamaClient.chat", side_effect=narrator.chat), patch("game.roll_d20", return_value=d20), \
                patch.object(session.rng, "randint", return_value=d10):
            response = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn", json=body)
        return response, record

    async def test_tactical_mind_reaches_the_real_check_and_is_annotated(self):
        response, record = await self.checked(2, d20=1)
        self.assertEqual(response.status_code, 200, response.text)
        check = response.json()["skill_check_result"]
        self.assertEqual(check["check_feature"], "tactical_mind")
        self.assertEqual(check["tactical_mind_roll"], 6)
        self.assertEqual(check["total"], check["d20"] + check["total_modifier"])
        spent = record.game_session.character.get("fighter_uses", {}).get("second_wind_spent", 0)
        self.assertEqual(spent, 1 if check["outcome"] == "success" else 0)

    async def test_tactical_mind_is_refused_before_level_two_and_for_other_classes(self):
        response, _ = await self.checked(1)
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (400, "tactical_mind_not_available"))

    async def test_tactical_mind_on_an_unsupported_wording_is_refused_with_its_own_code(self):
        campaign, record = await self.create(2)
        record.game_session.commit_location_change("tavern")
        self.manager.save_campaign(campaign["campaign_id"])
        body = {"message": "Bir saat bekliyorum", "interaction_mode": "do", "action_id": str(uuid4()), "check_feature": "tactical_mind"}
        response = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn", json=body)
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (400, "tactical_mind_immediate_check_only"))

    def test_turn_request_keeps_the_do_only_rule(self):
        from api.schemas import TurnRequest
        TurnRequest.model_validate({"message": "x", "interaction_mode": "do", "check_feature": "tactical_mind"})
        for bad in ({"message": "x", "check_feature": "tactical_mind"}, {"message": "x", "interaction_mode": "say", "check_feature": "tactical_mind"},
                    {"message": "x", "interaction_mode": "do", "check_feature": "made_up"}):
            with self.assertRaises(ValidationError):
                TurnRequest.model_validate(bad)

    async def test_fresh_resume_keeps_the_applied_state(self):
        campaign, record = await self.create(3, "Archery")
        record.game_session.character["fighter_uses"] = {"second_wind_spent": 1, "action_surge_spent": 1}
        self.manager.save_campaign(campaign["campaign_id"])
        body, manager = await self.reopen(campaign)
        fresh = manager.get(body["session_id"]).game_session.character
        self.assertEqual(fresh["fighting_style"], "Archery")
        self.assertEqual(fresh["fighter_uses"], {"second_wind_spent": 1, "action_surge_spent": 1})
        self.assertEqual(body["state"]["character"]["fighter"]["second_wind"]["uses_remaining"], 1)


if __name__ == "__main__":
    unittest.main()

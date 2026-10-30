"""Public Paladin 1-5: catalog fail-closed per row, creation, earned level-up and the typed commands through the real ASGI app.

Synthetic SQLite campaigns; a refusal is pinned by status and by the absence of any change.
"""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import character_progression as cp
from pydantic import ValidationError
from api.dnd_2024_rules import get_character_creation_catalog
from api.schemas import CharacterCreateInput, CharacterCreationCatalogResponse, CombatActionInput, LevelUpApplyRequest, SpeciesTraitActionRequest
import xp
from api.tests import test_campaign_api as campaigns
from api.tests import test_roadmap_c06_level4_http as prior
from api.tests import test_roadmap_c10_berserker_http as berserker
from api.tests import test_roadmap_c19_quickened_http as quickened
from api.tests.test_roadmap_c16_paladin import CHOICES, THRESHOLDS, bundle, spec


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
            if name == "Paladin" and mutate:
                mutate(table)
            return table
        with patch.object(cp, "table", side_effect=patched):
            return cp.paladin_starting_creation_options()

    def test_the_verified_catalog_offers_one_to_five(self):
        options = get_character_creation_catalog()["paladin_starting_creation"]
        self.assertEqual(options["supported_starting_levels"], [1, 2, 3, 4, 5])
        self.assertIn("Blessed Warrior", options["level_2"]["fighting_style_options"])
        self.assertIn("Guidance", options["level_2"]["blessed_warrior_cantrip_ids"])
        self.assertNotIn("Divine Smite", options["level_2"]["prepared_spell_ids"], "always prepared from level 2")
        self.assertEqual(options["level_3"]["subclass_options"], [{"id": "oath_of_devotion", "name": "Oath of Devotion"}])
        self.assertEqual(len(options["level_4"]["supported_asi_choices"]), 15)
        self.assertIn("Lesser Restoration", options["level_5"]["prepared_spell_ids"])
        self.assertIn("catalog-only", " ".join(options["level_5"]["effects_pending"]))
        CharacterCreationCatalogResponse.model_validate(get_character_creation_catalog())

    def test_a_bad_row_hides_that_level_and_everything_above(self):
        faults = [lambda row: row.update(features=["Fake"]), lambda row: row.update(prepared_spells=9), lambda row: row.update(proficiency_bonus=7),
                  lambda row: row.update(slots={"1": 9}), lambda row: row.update(channel_divinity=True), lambda row: row.update(cantrips=2)]
        for key, reachable in [("1", 1), ("2", 1), ("3", 2), ("4", 3), ("5", 4)]:
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


class Shapes(unittest.TestCase):
    def test_exact_bundles_parse(self):
        for level in range(2, 6):
            parsed = CharacterCreateInput.model_validate(request(level))
            self.assertEqual(parsed.level_choices.model_dump(by_alias=True, exclude_none=True), bundle(level))

    def test_blessed_warrior_needs_its_two_cantrips_and_a_feat_takes_none(self):
        good = request(2)
        good["level_choices"]["2"] = {"prepared_spells": ["Bless"], "fighting_style": "Blessed Warrior", "cantrips": ["Guidance", "Sacred Flame"]}
        CharacterCreateInput.model_validate(good)
        for body in ({"prepared_spells": ["Bless"], "fighting_style": "Blessed Warrior"},
                     {"prepared_spells": ["Bless"], "fighting_style": "Defense", "cantrips": ["Guidance", "Sacred Flame"]},
                     {"prepared_spells": ["Bless"], "fighting_style": "Protection"}):
            bad = request(2)
            bad["level_choices"]["2"] = body
            with self.assertRaises(ValidationError):
                CharacterCreateInput.model_validate(bad)

    def test_a_bundle_of_the_wrong_class_or_length_is_refused(self):
        for level, choices in ((2, {"2": {}}), (3, bundle(2)), (6, bundle(5))):
            bad = request(2)
            bad.update(starting_level=level, level_choices=choices)
            with self.assertRaises(ValidationError):
                CharacterCreateInput.model_validate(bad)

    def test_level_up_body_shapes(self):
        base = dict(action_id=str(uuid4()), campaign_id=str(uuid4()), expected_revision=0)
        for level in range(2, 6):
            LevelUpApplyRequest.model_validate({**base, "target_level": level, "choices": CHOICES[str(level)]})
        with self.assertRaises(ValidationError):
            LevelUpApplyRequest.model_validate({**base, "target_level": 3, "choices": CHOICES["2"]})

    def test_commands_are_exact(self):
        good = [{"kind": "lay_on_hands", "resource": "bonus", "healing_amount": 3}, {"kind": "lay_on_hands", "resource": "bonus", "remove_poisoned": True},
                {"kind": "divine_smite", "resource": "bonus"}, {"kind": "divine_smite", "resource": "bonus", "slot_level": 2},
                {"kind": "divine_sense", "resource": "bonus"}, {"kind": "attack", "sacred_weapon": True}]
        for step in good:
            CombatActionInput.model_validate({"steps": [step]})
        bad = [{"kind": "lay_on_hands"}, {"kind": "lay_on_hands", "resource": "bonus"}, {"kind": "lay_on_hands", "resource": "bonus", "healing_amount": 0},
               {"kind": "lay_on_hands", "resource": "bonus", "remove_poisoned": False}, {"kind": "lay_on_hands", "resource": "action", "healing_amount": 1},
               {"kind": "lay_on_hands", "resource": "bonus", "healing_amount": 1, "target_id": "x"}, {"kind": "divine_smite"},
               {"kind": "divine_smite", "resource": "bonus", "target_id": "x"}, {"kind": "divine_sense", "resource": "bonus", "slot_level": 1},
               {"kind": "move", "sacred_weapon": True}, {"kind": "magic", "radiant_damage": True}, {"kind": "move", "healing_amount": 1}]
        for step in bad:
            with self.subTest(step), self.assertRaises(ValidationError):
                CombatActionInput.model_validate({"steps": [step]})
        with self.assertRaises(ValidationError):
            CombatActionInput.model_validate({"steps": [{"kind": "divine_smite", "resource": "bonus"}, {"kind": "end_turn"}]})

    def test_the_rest_route_fields_belong_to_lay_on_hands(self):
        SpeciesTraitActionRequest.model_validate({"action": "lay_on_hands", "healing_amount": 2})
        SpeciesTraitActionRequest.model_validate({"action": "divine_sense"})
        for body in ({"action": "lay_on_hands"}, {"action": "short_rest", "healing_amount": 2}, {"action": "lay_on_hands", "remove_poisoned": False}):
            with self.assertRaises(ValidationError):
                SpeciesTraitActionRequest.model_validate(body)


class PaladinHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown
    reopen = prior.LevelFourHttpTests.reopen
    snapshot = berserker.BerserkerHttpTests.snapshot
    url = berserker.BerserkerHttpTests.url
    preview = berserker.BerserkerHttpTests.preview
    command = berserker.BerserkerHttpTests.command
    post = quickened.QuickenedHttpTests.post

    async def create(self, level=1):
        response = await self.http.post("/api/game/campaigns", json={"character": request(level)})
        self.assertEqual(response.status_code, 200, response.text)
        campaign = response.json()
        return campaign, self.manager.get(campaign["session_id"])

    def award(self, campaign, record, level):
        session = record.game_session
        gained = THRESHOLDS[level] - session.character["xp"]
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, f"quest:synthetic-paladin-{level}")
        self.manager.save_campaign(campaign["campaign_id"])

    async def level_up(self, campaign, record, level, choices=None):
        self.award(campaign, record, level)
        preview = await self.preview(campaign)
        self.assertEqual((preview["status"], preview["target_level"], preview["class_name"]), ("ready", level, "Paladin"), preview)
        body = self.command(campaign, copy.deepcopy(CHOICES[str(level)]) if choices is None else choices, preview)
        return preview, body, await self.http.post(self.url(campaign), json=body)

    async def encounter(self, level=3):
        campaign, record = await self.create(level)
        session = record.game_session
        session.commit_location_change("tavern")
        session.ensure_campaign_clock()
        session.character.update(max_hp=60, current_hp=30)
        session.world_state["equipment"] = {"main_hand": "longsword", "off_hand": None}
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": "tavern"})
        npc.update(current_hp=100, max_hp=100, armor_class=5, hostile=True, distance_ft=5)
        session.world_state.setdefault("monster_perception", {})[npc["id"]] = {"player": {"visible": True}}
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            session.start_combat(npc)
        self.manager.save_campaign(campaign["campaign_id"])
        return campaign, record, npc

    async def test_every_start_is_created_stored_and_projected(self):
        for level in range(1, 6):
            campaign, record = await self.create(level)
            character = campaign["state"]["character"]
            self.assertEqual(character["paladin"]["lay_on_hands"]["pool_maximum"], 5 * level)
            self.assertEqual(character["paladin"]["channel_divinity"] is None, level < 3)
            self.assertEqual(character["paladin"]["fighting_style"], None if level == 1 else "Defense")
            self.assertIn("catalog-only", " ".join(character["progression_effects_pending"]))
            self.assertEqual(record.game_session.character.get("progression_level", 1), level)

    async def test_earned_steps_one_to_five_through_the_public_route(self):
        campaign, record = await self.create()
        for level in range(2, 6):
            preview, body, response = await self.level_up(campaign, record, level)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["state"]["character"]["level"], level)
            self.assertEqual(record.game_session.character["progression_level"], level)
            if level == 2:
                self.assertIn("Blessed Warrior", preview["fighting_style_options"])
                self.assertIn("Sacred Flame", preview["cantrip_ids"])
            before = self.snapshot(record)
            with patch("character_progression.apply_level_choices", side_effect=AssertionError("old receipt reapplied")):
                replay = await self.http.post(self.url(campaign), json=body)
            self.assertEqual(replay.json(), response.json())
            self.assertEqual(self.snapshot(record), before)
        final = await self.preview(campaign)
        self.assertEqual((final["status"], final["reason"]), ("blocked", "target_not_above_applied_level"))

    async def test_a_wrong_class_body_and_a_used_spell_are_refused(self):
        campaign, record = await self.create(2)
        self.award(campaign, record, 3)
        preview = await self.preview(campaign)
        before = self.snapshot(record)
        fighter_body = self.command(campaign, {"subclass_id": "champion"}, preview)
        self.assertEqual((await self.http.post(self.url(campaign), json=fighter_body)).status_code, 409)
        used = self.command(campaign, {"prepared_spells": ["Bless"], "subclass_id": "oath_of_devotion"}, preview)
        self.assertEqual((await self.http.post(self.url(campaign), json=used)).status_code, 409)
        self.assertEqual(self.snapshot(record), before)

    async def test_an_unearned_step_is_blocked(self):
        campaign, _ = await self.create()
        self.assertEqual((await self.preview(campaign))["reason"], "level_not_earned")

    async def test_lay_on_hands_is_receipted_and_replayed(self):
        campaign, record, _ = await self.encounter()
        body = {"message": "Lay On Hands", "action_id": str(uuid4()),
                "combat_action": {"steps": [{"kind": "lay_on_hands", "resource": "bonus", "healing_amount": 6}]}}
        response = await self.post(campaign, body)
        self.assertEqual(response.status_code, 200, response.text)
        character = response.json()["state"]["character"]
        self.assertEqual((character["current_hp"], character["paladin"]["lay_on_hands"]["pool_remaining"]), (36, 9))
        before = self.snapshot(record)
        with patch("paladin_features.activate_lay_on_hands", side_effect=AssertionError("replayed")):
            replay = await self.post(campaign, body)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(self.snapshot(record), before)

    async def test_an_attack_with_sacred_weapon_then_a_smite_through_the_public_route(self):
        campaign, record, npc = await self.encounter()
        attack = {"message": "Saldırı", "action_id": str(uuid4()),
                  "combat_action": {"steps": [{"kind": "attack", "target_id": npc["id"], "sacred_weapon": True, "radiant_damage": True}]}}
        with patch("game.roll_attack", return_value=18):
            response = await self.post(campaign, attack)
        self.assertEqual(response.status_code, 200, response.text)
        paladin = response.json()["state"]["character"]["paladin"]
        self.assertTrue(paladin["sacred_weapon"]["active"])
        self.assertEqual(paladin["channel_divinity"]["uses_remaining"], 1)
        self.assertTrue(paladin["divine_smite"]["activate"]["available"], paladin)
        self.assertEqual(paladin["divine_smite"]["target_id"], npc["id"])
        before = record.game_session.world_state["spellcasting_v1"]["slots"]["1"]
        smite = {"message": "Divine Smite", "action_id": str(uuid4()),
                 "combat_action": {"steps": [{"kind": "divine_smite", "resource": "bonus", "slot_level": 1}]}}
        response = await self.post(campaign, smite)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(record.game_session.world_state["spellcasting_v1"]["slots"]["1"], before - 1)
        self.assertFalse(response.json()["state"]["character"]["paladin"]["divine_smite"]["activate"]["available"])

    async def test_lay_on_hands_and_divine_sense_outside_combat_through_the_trait_route(self):
        campaign, record = await self.create(3)
        session = record.game_session
        session.commit_location_change("tavern")
        session.ensure_campaign_clock()
        session.character.update(max_hp=60, current_hp=30)
        self.manager.save_campaign(campaign["campaign_id"])
        url = f"/api/game/sessions/{campaign['session_id']}/species-actions"
        response = await self.http.post(url, json={"action": "lay_on_hands", "healing_amount": 4, "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"]["character"]["paladin"]["lay_on_hands"]["pool_remaining"], 11)
        response = await self.http.post(url, json={"action": "divine_sense", "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["state"]["character"]["paladin"]["divine_sense"]["active"])

    async def test_fresh_resume_keeps_the_applied_state(self):
        campaign, record = await self.create(3)
        record.game_session.character["paladin_uses"] = {"lay_on_hands_spent": 3, "channel_divinity_spent": 1, "free_smite_spent": 1,
                                                         "divine_sense_until": None, "sacred_weapon": None}
        self.manager.save_campaign(campaign["campaign_id"])
        body, manager = await self.reopen(campaign)
        self.assertEqual(manager.get(body["session_id"]).game_session.character["paladin_uses"]["lay_on_hands_spent"], 3)
        self.assertEqual(body["state"]["character"]["paladin"]["channel_divinity"]["uses_remaining"], 1)


if __name__ == "__main__":
    unittest.main()

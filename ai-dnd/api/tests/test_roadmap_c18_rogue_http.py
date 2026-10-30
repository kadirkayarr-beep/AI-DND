"""Public Rogue 1-5: catalog, creation, earned level-up and the typed commands through the real ASGI app.

Synthetic SQLite campaigns; a refusal is pinned by status and by the absence of any change.
"""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import xp
from pydantic import ValidationError
from api.dnd_2024_rules import get_character_creation_catalog
from api.schemas import CharacterCreateInput, CharacterCreationCatalogResponse, CombatActionInput, LevelUpApplyRequest
from api.tests import test_campaign_api as campaigns
from api.tests import test_roadmap_c06_level4_http as prior
from api.tests import test_roadmap_c10_berserker_http as berserker
from api.tests import test_roadmap_c19_quickened_http as quickened
from api.tests.test_roadmap_c18_rogue import CHOICES, THRESHOLDS, bundle, spec


def request(level):
    value = spec()
    value["class"] = value.pop("character_class")
    value.update(mode="custom", starting_level=level, level_choices=bundle(level) if level > 1 else None)
    return value


class Contract(unittest.TestCase):
    def test_catalog_validates_against_the_strict_response(self):
        CharacterCreationCatalogResponse.model_validate(get_character_creation_catalog())

    def test_exact_bundles_parse(self):
        for level in range(2, 6):
            CharacterCreateInput.model_validate(request(level))

    def test_a_bundle_of_the_wrong_class_or_length_is_refused(self):
        for bad in ({"2": {}, "3": {"subclass_id": "champion"}}, {"2": {}, "3": {"subclass_id": "thief"}}, {"2": {}}):
            value = request(3)
            value["level_choices"] = bad
            with self.subTest(bad), self.assertRaises(ValidationError):
                CharacterCreateInput.model_validate(value)

    def test_level_up_body_shapes(self):
        base = {"action_id": str(uuid4()), "campaign_id": str(uuid4()), "expected_revision": 1}
        LevelUpApplyRequest.model_validate({**base, "target_level": 3, "choices": {"subclass_id": "assassin"}})
        with self.assertRaises(ValidationError):
            LevelUpApplyRequest.model_validate({**base, "target_level": 3, "choices": {"subclass_id": "thief"}})
        with self.assertRaises(ValidationError):
            LevelUpApplyRequest.model_validate({**base, "target_level": 4, "choices": {"subclass_id": "assassin"}})

    def test_typed_step_shapes(self):
        good = ({"kind": "cunning_action", "resource": "bonus", "cunning_option": "dash"}, {"kind": "steady_aim", "resource": "bonus"},
                {"kind": "uncanny_dodge", "uncanny_dodge_enabled": False},
                {"kind": "attack", "target_id": "x", "cunning_strike": "withdraw", "cunning_strike_move_ft": 10})
        for step in good:
            CombatActionInput.model_validate({"steps": [step]})
        bad = ({"kind": "cunning_action", "cunning_option": "dash"}, {"kind": "cunning_action", "resource": "bonus"},
               {"kind": "cunning_action", "resource": "bonus", "cunning_option": "hide"},
               {"kind": "steady_aim"}, {"kind": "steady_aim", "resource": "bonus", "target_id": "x"},
               {"kind": "uncanny_dodge"}, {"kind": "uncanny_dodge", "uncanny_dodge_enabled": 1},
               {"kind": "move", "distance_ft": 5, "cunning_strike": "trip"}, {"kind": "attack", "target_id": "x", "cunning_strike": "daze"},
               {"kind": "attack", "target_id": "x", "cunning_option": "dash"},
               {"kind": "react", "opportunity_id": "x", "cunning_strike": "trip"})
        for step in bad:
            with self.subTest(step), self.assertRaises(ValidationError):
                CombatActionInput.model_validate({"steps": [step]})
        with self.assertRaises(ValidationError):
            CombatActionInput.model_validate({"steps": [good[1], {"kind": "end_turn"}]})


class RogueHttp(unittest.IsolatedAsyncioTestCase):
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

    async def encounter(self, level=5):
        campaign, record = await self.create(level)
        session = record.game_session
        session.commit_location_change("tavern")
        session.character.update(max_hp=60, current_hp=30)
        npc = session.create_npc_from_ai({"name": "Rakip", "role": "Guard", "location": "tavern"})
        npc.update(current_hp=100, max_hp=100, armor_class=5, hostile=True, distance_ft=5, conditions=["blinded"])
        session.world_state.setdefault("monster_perception", {})[npc["id"]] = {"player": {"visible": True}}
        session.world_state["inventory"].append("Rapier")
        session.world_state["equipment"] = {"main_hand": "rapier", "off_hand": None}
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            session.start_combat(npc)
        return campaign, record, npc

    async def test_every_start_is_created_stored_and_projected(self):
        for level in range(1, 6):
            campaign, record = await self.create(level)
            character = campaign["state"]["character"]
            self.assertEqual(character["rogue"]["sneak_attack"]["dice"], (1, 1, 2, 2, 3)[level - 1])
            self.assertEqual(character["rogue"]["cunning_action"] is None, level < 2)
            self.assertEqual(character["rogue"]["cunning_strike"] is None, level < 5)
            self.assertIn("Weapon Mastery", " ".join(character["progression_effects_pending"]))
            self.assertEqual(record.game_session.character.get("progression_level", 1), level)

    async def test_earned_steps_one_to_five_through_the_public_route(self):
        campaign, record = await self.create()
        for level in range(2, 6):
            session = record.game_session
            session._receive_xp_award(xp.apply_xp, session.character, session.world_state, THRESHOLDS[level] - session.character["xp"],
                                      f"quest:synthetic-rogue-{level}")
            self.manager.save_campaign(campaign["campaign_id"])
            preview = await self.preview(campaign)
            self.assertEqual((preview["status"], preview["target_level"], preview["class_name"]), ("ready", level, "Rogue"), preview)
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

    async def test_a_wrong_class_body_is_refused(self):
        campaign, record = await self.create(2)
        session = record.game_session
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state, THRESHOLDS[3] - session.character["xp"], "quest:synthetic")
        self.manager.save_campaign(campaign["campaign_id"])
        preview = await self.preview(campaign)
        self.assertEqual(preview["subclass_options"], [{"id": "assassin", "name": "Assassin"}])
        before = self.snapshot(record)
        response = await self.http.post(self.url(campaign), json=self.command(campaign, {"subclass_id": "champion"}, preview))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "level_up_choice_class_mismatch")
        self.assertEqual(self.snapshot(record), before)

    async def test_an_attack_with_cunning_strike_is_receipted_public_and_replayed(self):
        campaign, record, npc = await self.encounter()
        step = {"kind": "attack", "target_id": npc["id"], "cunning_strike": "trip"}
        body = {"message": "Saldırıyorum", "target_id": npc["id"], "action_id": str(uuid4()), "combat_action": {"steps": [step]}}
        with patch("game.roll_attack", return_value=15), patch("game.roll_d20", return_value=1), \
                patch.object(record.game_session.rng, "randint", return_value=3):
            response = await self.post(campaign, body)
        self.assertEqual(response.status_code, 200, response.text)
        rogue = response.json()["state"]["character"]["rogue"]
        self.assertTrue(rogue["sneak_attack"]["used_this_turn"])
        self.assertIn("Sneak Attack: 2d6", response.json()["narration"])
        self.assertIn("Cunning Strike (Trip)", response.json()["narration"])
        self.assertIn("prone", next(entry for entry in record.game_session.world_state["npcs"] if entry["id"] == npc["id"])["conditions"])
        before = self.snapshot(record)
        replay = await self.post(campaign, body)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(self.snapshot(record), before)

    async def test_a_refused_cunning_strike_changes_nothing_and_names_its_code(self):
        campaign, record, npc = await self.encounter(4)
        before = self.snapshot(record)
        step = {"kind": "attack", "target_id": npc["id"], "cunning_strike": "trip"}
        response = await self.post(campaign, {"message": "x", "target_id": npc["id"], "action_id": str(uuid4()), "combat_action": {"steps": [step]}})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"]["code"], "cunning_strike_not_available")
        self.assertEqual(self.snapshot(record), before)

    async def test_cunning_action_steady_aim_and_uncanny_dodge_commands(self):
        campaign, record, _ = await self.encounter()
        steady = await self.post(campaign, {"message": "Steady Aim", "action_id": str(uuid4()),
                                            "combat_action": {"steps": [{"kind": "steady_aim", "resource": "bonus"}]}})
        self.assertEqual(steady.status_code, 200, steady.text)
        self.assertTrue(steady.json()["state"]["character"]["rogue"]["steady_aim"]["active"])
        refused = await self.post(campaign, {"message": "Dash", "action_id": str(uuid4()), "combat_action": {
            "steps": [{"kind": "cunning_action", "resource": "bonus", "cunning_option": "dash"}]}})
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(refused.json()["detail"]["code"], "bonus_action_spent")
        toggled = await self.post(campaign, {"message": "Uncanny Dodge", "action_id": str(uuid4()), "combat_action": {
            "steps": [{"kind": "uncanny_dodge", "uncanny_dodge_enabled": False}]}})
        self.assertEqual(toggled.status_code, 200, toggled.text)
        self.assertFalse(toggled.json()["state"]["character"]["rogue"]["uncanny_dodge"]["enabled"])

    async def test_fresh_resume_keeps_the_applied_state(self):
        campaign, record, _ = await self.encounter()
        await self.post(campaign, {"message": "Uncanny Dodge", "action_id": str(uuid4()), "combat_action": {
            "steps": [{"kind": "uncanny_dodge", "uncanny_dodge_enabled": False}]}})
        self.manager.save_campaign(campaign["campaign_id"])
        body, manager = await self.reopen(campaign)
        self.assertIs(manager.get(body["session_id"]).game_session.character["uncanny_dodge_off"], True)
        self.assertFalse(body["state"]["character"]["rogue"]["uncanny_dodge"]["enabled"])


if __name__ == "__main__":
    unittest.main()

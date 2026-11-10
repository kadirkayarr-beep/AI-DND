"""A two-handed weapon taken in hand puts the shield away and the Armor Class falls by the shield's share (Dilim 3,
Task 16). The share is the one creation formula's difference with and without the shield; the shield stays in the bag;
Undo and reload bring the total back; a refused draw changes nothing."""
import copy
import unittest

import action_economy
import character_progression
import equipment_economy
import game
import gear
from api.dnd_2024_rules import armor_class_total
from api.persistence.campaign_models import CampaignCorruptError
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests import test_roadmap_c06_dex_asi as dex_asi
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, apply_setup
from api.tests.journeys.schema import load_scenario
from api.tests.test_roadmap_c06 import created_sorcerer

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")


class TwoHandedShieldAc(JourneyCase):
    async def _session(self, scenario_file):
        setup = load_scenario(SCENARIO_DIR / scenario_file).setup
        campaign = await self._journey_campaign(setup)
        apply_setup(self, campaign, setup)
        return self.manager.get(campaign["session_id"]).game_session

    async def fighter_with_shield_and_greatsword(self):
        return await self._session("05c_greatsword_shield_ac.json")

    async def fighter_without_shield_with_greatsword(self):
        return await self._session("05b_draw_greatsword.json")

    @staticmethod
    def shield_share(character):
        origin = character["armor_origin"]
        modifiers = {ability: (character[ability] - 10) // 2 for ability in ABILITIES}
        total = lambda shield: armor_class_total(character["class"], modifiers, origin["armor"], shield,  # noqa: E731
                                                 character.get("fighting_style"))
        return total(True) - total(False)

    @staticmethod
    def item_id(session, name):
        return next(item["item_id"] for item in session.world_state["inventory"] if item.get("name") == name)

    def greatsword_id(self, session):
        return self.item_id(session, "Greatsword")

    def shield_id(self, session):
        return self.item_id(session, "Kalkan")

    async def test_two_handed_draw_lowers_ac_by_the_shield_share(self):
        session = await self.fighter_with_shield_and_greatsword()
        before = session.character["armor_class"]
        share = self.shield_share(session.character)
        self.assertGreater(share, 0)
        self.assertEqual(gear.draw(session.world_state, self.greatsword_id(session),
                                   character=session.character).status, "drawn")
        self.assertEqual(session.character["armor_class"], before - share)
        self.assertEqual(session.world_state["shield_down"], {"item_id": self.shield_id(session), "ac_bonus": share})
        self.assertIn(self.shield_id(session), [i["item_id"] for i in session.world_state["inventory"]])

    async def test_no_shield_in_hand_no_change(self):
        session = await self.fighter_without_shield_with_greatsword()
        before = session.character["armor_class"]
        self.assertEqual(gear.draw(session.world_state, self.greatsword_id(session),
                                   character=session.character).status, "drawn")
        self.assertEqual(session.character["armor_class"], before)
        self.assertNotIn("shield_down", session.world_state)

    async def test_drawing_twice_lowers_once(self):
        session = await self.fighter_with_shield_and_greatsword()
        before = session.character["armor_class"]
        for _ in range(2):
            gear.draw(session.world_state, self.greatsword_id(session), character=session.character)
        self.assertEqual(session.character["armor_class"], before - self.shield_share(session.character))
        self.assertEqual(gear.settle_shield(session.world_state, session.character), 0)
        self.assertEqual(session.character["armor_class"], before - self.shield_share(session.character))

    async def test_putting_the_greatsword_away_and_drawing_again_lowers_once(self):
        session = await self.fighter_with_shield_and_greatsword()
        before = session.character["armor_class"]
        gear.draw(session.world_state, self.greatsword_id(session), character=session.character)
        gear.draw(session.world_state, self.item_id(session, "Hançer"), character=session.character)
        gear.draw(session.world_state, self.greatsword_id(session), character=session.character)
        self.assertEqual(session.character["armor_class"], before - self.shield_share(session.character))

    def test_an_untrained_shield_has_no_share(self):
        session = created_sorcerer()                                     # no shield training: the formula adds nothing
        session.character["armor_origin"] = {"armor": None, "shield": True}
        self.assertEqual(self.shield_share(session.character), 0)
        session.world_state["inventory"] = ["Kalkan", "Greatsword"]
        session.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        equipment_economy.materialize(session.world_state)
        before = session.character["armor_class"]
        self.assertEqual(gear.draw(session.world_state, self.greatsword_id(session),
                                   character=session.character).status, "drawn")
        self.assertEqual(session.character["armor_class"], before)

    async def test_a_refused_draw_changes_nothing(self):
        session = await self.fighter_with_shield_and_greatsword()
        session.world_state["equipment"]["main_hand"] = "Uzun Kılıç"     # a hand alias no owned item answers to
        before = (copy.deepcopy(session.world_state), session.character["armor_class"])
        result = gear.draw(session.world_state, self.greatsword_id(session), character=session.character)
        self.assertEqual(result.status, "refused")
        self.assertEqual((session.world_state, session.character["armor_class"]), before)

    async def test_a_refused_item_equip_leaves_no_record_and_the_same_ac(self):
        # The dagger is still in the main hand: the owner writes the shield record on its copy, then refuses.
        session = await self.fighter_with_shield_and_greatsword()
        self.assertEqual(gear.draw(session.world_state, self.item_id(session, "Hançer")).status, "drawn")
        before = (copy.deepcopy(session.world_state), copy.deepcopy(session.character))
        result = equipment_economy.execute(session, f"/item equip {self.greatsword_id(session)} main_hand")
        self.assertEqual((result["action_result"]["success"], result["action_result"]["reason"]),
                         (False, "hand_occupied"))
        self.assertNotIn("shield_down", session.world_state)
        self.assertEqual((session.world_state, session.character), before)

    async def test_every_two_handed_path_lowers_ac(self):
        # The item command (equipment_economy.execute): the hand is freed first, then the greatsword taken.
        session = await self.fighter_with_shield_and_greatsword()
        before = session.character["armor_class"]
        share = self.shield_share(session.character)
        self.assertTrue(equipment_economy.execute(session, "/item unequip main_hand")["action_result"]["success"])
        result = equipment_economy.execute(session, f"/item equip {self.greatsword_id(session)} main_hand")
        self.assertTrue(result["action_result"]["success"], result)
        self.assertEqual(session.character["armor_class"], before - share)
        self.assertIn(self.shield_id(session), [i["item_id"] for i in session.world_state["inventory"]])
        # An attack with an empty hand draws the first bag weapon (action_economy -> gear.attack_weapon).
        session = await self.fighter_with_shield_and_greatsword()
        world = session.world_state
        world["inventory"] = [item for item in world["inventory"] if item.get("name") != "Hançer"]
        self.assertEqual(world["equipment"]["main_hand"], None)
        name, _, instance, _ = action_economy._gear_weapon(session)
        self.assertEqual((name, instance), ("Greatsword", self.greatsword_id(session)))
        self.assertEqual(session.character["armor_class"], before - share)

    async def test_the_lowered_total_still_follows_its_origin(self):
        # A Dexterity increase moves Armor Class through the origin; with the shield down the origin must still hold.
        session = await self.fighter_with_shield_and_greatsword()
        dex = lambda: [c for c in character_progression.supported_asi_choices(session.character,  # noqa: E731
                                                                              session.world_state)
                       if c["increase"] == {"dexterity": 2}]
        self.assertTrue(dex())
        gear.draw(session.world_state, self.greatsword_id(session), character=session.character)
        self.assertTrue(dex())

    async def test_the_shield_record_survives_a_reload_and_a_second_draw_lowers_nothing(self):
        # Without the record a reloaded game would count the bag shield as in hand again and lower the total twice.
        session = await self.fighter_with_shield_and_greatsword()
        before = session.character["armor_class"]
        share = self.shield_share(session.character)
        gear.draw(session.world_state, self.greatsword_id(session), character=session.character)
        record = copy.deepcopy(session.world_state["shield_down"])
        fresh = game.create_session(seed=9)
        restore_campaign_session(fresh, serialize_campaign_payload(session))
        self.assertEqual(fresh.world_state["shield_down"], record)
        self.assertEqual(fresh.character["armor_class"], before - share)
        gear.draw(fresh.world_state, self.item_id(fresh, "Hançer"), character=fresh.character)
        self.assertEqual(gear.draw(fresh.world_state, self.greatsword_id(fresh), character=fresh.character).status,
                         "drawn")
        self.assertEqual(fresh.character["armor_class"], before - share)
        self.assertEqual(fresh.world_state["shield_down"], record)

    async def test_two_handed_draw_lowers_ac_and_undo_restores_it(self):
        results = await self.run_scenario(load_scenario(SCENARIO_DIR / "05c_greatsword_shield_ac.json"))
        self.assertEqual([r.status for r in results], ["pass"] * 5, results)
        self.assertLess(self.last_observations[0]["zirh"], self.last_observations[1]["zirh"])


class TheLoweredTotalNeedsTheShieldRecord(unittest.TestCase):
    """The total without the shield is the origin's only while `world["shield_down"]` records exactly the shield's
    share (Task 21 review I-2); the total with the shield stays the origin's, so a save from before Task 16 loads."""

    @staticmethod
    def fighter(*, lowered, ac_bonus="share"):
        session = dex_asi.level_three("Fighter")                         # Chain Mail and a creation Shield
        share = character_progression.shield_share(session.character)
        assert share > 0
        if lowered:
            session.character["armor_class"] -= share
        if ac_bonus is not None:                                         # the record's shield id is not what is read
            session.world_state["shield_down"] = {"item_id": "kalkan",
                                                  "ac_bonus": share if ac_bonus == "share" else ac_bonus(share)}
        return session

    def test_a_lowered_total_without_the_record_is_not_the_origins(self):
        session = self.fighter(lowered=True, ac_bonus=None)
        self.assertIsNone(character_progression._verified_armor_origin(session.character, session.world_state))
        self.assertNotIn({"dexterity": 2}, dex_asi.offered(session))

    def test_a_lowered_total_with_the_record_is_the_origins(self):
        session = self.fighter(lowered=True)
        self.assertIsNotNone(character_progression._verified_armor_origin(session.character, session.world_state))
        self.assertIn({"dexterity": 2}, dex_asi.offered(session))

    def test_a_record_of_another_share_does_not_explain_the_lowered_total(self):
        for ac_bonus in (lambda share: share + 1, lambda share: 0, lambda share: None):
            with self.subTest(ac_bonus=ac_bonus(2)):
                session = self.fighter(lowered=True, ac_bonus=ac_bonus)
                self.assertIsNone(character_progression._verified_armor_origin(session.character,
                                                                               session.world_state))
                self.assertNotIn({"dexterity": 2}, dex_asi.offered(session))

    def test_the_full_total_stays_the_origins_with_or_without_the_record(self):
        for ac_bonus in (None, "share"):
            with self.subTest(record=ac_bonus):
                session = self.fighter(lowered=False, ac_bonus=ac_bonus)
                self.assertIsNotNone(character_progression._verified_armor_origin(session.character,
                                                                                  session.world_state))

    def test_a_dex_save_with_the_total_lowered_and_no_record_is_refused_on_load(self):
        session = self.fighter(lowered=False, ac_bonus=None)
        dex_asi.apply_four(self, session, {"dexterity": 2})
        payload = serialize_campaign_payload(session)
        payload["engine_save"]["player"]["armor_class"] -= character_progression.shield_share(session.character)
        with self.assertRaises(CampaignCorruptError):
            restore_campaign_session(game.create_session(seed=9), payload)
        payload["engine_save"]["world_state"]["shield_down"] = {
            "item_id": "kalkan", "ac_bonus": character_progression.shield_share(session.character)}
        fresh = game.create_session(seed=9)
        restore_campaign_session(fresh, payload)
        self.assertEqual(fresh.character["asi_choices"], session.character["asi_choices"])

    def test_a_dex_save_from_before_task_16_still_loads(self):
        # Before Task 16 a two-handed weapon left the total alone and wrote no record.
        session = self.fighter(lowered=False, ac_bonus=None)
        dex_asi.apply_four(self, session, {"dexterity": 2})
        payload = serialize_campaign_payload(session)
        self.assertNotIn("shield_down", payload["engine_save"]["world_state"])
        fresh = game.create_session(seed=9)
        restore_campaign_session(fresh, payload)
        self.assertEqual(fresh.character["armor_class"], session.character["armor_class"])
        self.assertIsNotNone(character_progression._verified_armor_origin(fresh.character, fresh.world_state))


if __name__ == "__main__":
    unittest.main()

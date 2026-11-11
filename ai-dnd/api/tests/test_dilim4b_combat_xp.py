"""Dilim 4B Task 1: a beaten foe pays its sourced Challenge Rating value, once per creature, all or nothing.

Engine tests run a real fight (`start_combat`, the foe going down, `_combat_end_if_decided`); the Undo, same-action
replay and save/load tests go through the real routes with the scripted model (scenario 44's setup)."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import bounded_encounter
import fallen
import game
import xp
from api.tests import test_wield_front as wield_front
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase
from api.tests.journeys.schema import load_scenario

ATTACK = {"intent": "attack", "action": "attack",
          "target": {"type": "npc", "reference": "Muhafız", "npc_id": "guard", "evidence_quote": "Muhafız"},
          "completion": "complete"}


def fighter(session):
    session.character.update(
        name="Ari", race="Human", **{"class": "Fighter"}, strength=16, dexterity=14, constitution=14,
        intelligence=10, wisdom=12, charisma=10, level=1, proficiency_bonus=2, max_hp=12, current_hp=12,
        armor_class=16, constitution_mod=2, xp=0)
    session.world_state["location"] = "tavern"
    session.world_state["xp_awarded_event_ids"] = []
    session.world_state["flags"]["turn_index"] = 3


def person(identity, role, **extra):
    return {"id": identity, "name": identity.title(), "role": role, "location": "tavern", "max_hp": 8,
            "current_hp": 8, "armor_class": 10, "combat_status": "active", "dexterity_mod": 0, "hostile": True,
            **extra}


def beat(session, *people, knock_out=False):
    """A real fight: start it with the first foe, bring every foe down, let the engine decide the ending."""
    session.start_combat(people[0])
    for foe in people[1:]:
        session.join_combat_participants([foe["id"]])
    for foe in people:
        if knock_out:
            fallen.knock_out(session, foe)
        else:
            foe.update(current_hp=0, combat_status="dead")
    session.ensure_combat_state()
    return session._combat_end_if_decided()


class CombatXp(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=4801)
        fighter(self.session)
        self.world = self.session.world_state

    def foes(self, *people):
        self.world["npcs"] = list(people)
        return people

    def test_xp_table_is_the_sourced_one(self):
        self.assertEqual(xp.XP_BY_CR, {"0": 10, "1/8": 25, "1/4": 50, "1/2": 100, "1": 200, "2": 450, "3": 700,
                                       "4": 1100, "5": 1800})
        self.assertEqual(xp.PERSON_KIND_CR, {"armed": "1/8", "strong": "0", "plain": "0"})

    def test_a_beaten_guard_pays_25_and_a_drunk_10(self):
        (guard,) = self.foes(person("guard1", "muhafız"))
        self.assertEqual(game.person_fight_kind(guard), "armed")
        self.assertEqual(beat(self.session, guard)["reason"], "target_defeated")
        self.assertEqual(self.session.character["xp"], 25)
        self.assertIn("combat:foe:guard1", self.world["xp_awarded_event_ids"])
        other = game.create_session(seed=4802)
        fighter(other)
        (drunk,) = [person("drunk1", "ayyaş")]
        other.world_state["npcs"] = [drunk]
        self.assertEqual(game.person_fight_kind(drunk), "plain")
        beat(other, drunk)
        self.assertEqual(other.character["xp"], 10)
        self.assertEqual(other.world_state["xp_awarded_event_ids"], ["combat:foe:drunk1"])

    def test_a_knocked_out_foe_counts_as_beaten(self):
        (drunk,) = self.foes(person("drunk1", "ayyaş"))
        beat(self.session, drunk, knock_out=True)
        self.assertEqual(drunk["combat_status"], "unconscious")
        self.assertEqual(self.session.character["xp"], 10)

    def test_the_courtyard_commoner_pays_its_stat_block(self):
        commoner = person("yard1", "Hooligan", monster_stat_block=copy.deepcopy(bounded_encounter.COMMONER))
        self.foes(commoner)
        beat(self.session, commoner)
        self.assertEqual(self.session.character["xp"], 10)

    def test_the_stat_block_outranks_the_role_and_a_server_reward_outranks_both(self):
        block = copy.deepcopy(bounded_encounter.COMMONER)
        block["challenge_rating"] = "1/4"
        self.assertEqual(xp.reward_for({"monster_stat_block": block}, "armed"), 50)
        self.assertEqual(xp.reward_for({"monster_stat_block": block, "xp_reward": 7}, "armed"), 7)
        self.assertEqual(xp.reward_for({"xp_reward": True}, "plain"), 10)           # a bool is not a reward
        self.assertEqual(xp.reward_for({"xp_reward": xp.MAX_GRANT + 1}, "plain"), 10)
        self.assertEqual(xp.reward_for({"monster_stat_block": {"challenge_rating": "30"}}, None), 0)
        self.assertEqual(xp.reward_for({}, None), 0)
        self.assertEqual(xp.reward_for({}, "unknown"), 0)

    def test_a_woken_foe_pays_once_per_campaign(self):
        (drunk,) = self.foes(person("drunk1", "ayyaş"))
        beat(self.session, drunk, knock_out=True)
        self.assertEqual(self.session.character["xp"], 10)
        self.world["campaign_time"] = {"elapsed_seconds": drunk["knocked_out_at"] + 3600}
        fallen.wake(self.session)
        self.assertEqual(drunk["combat_status"], "active")
        drunk["current_hp"] = 8
        beat(self.session, drunk)
        self.assertEqual(self.session.character["xp"], 10)
        self.assertEqual(self.world["xp_awarded_event_ids"], ["combat:foe:drunk1"])

    def test_two_foes_one_ending_pay_together(self):
        self.session.character["xp"] = 280
        guard, drunk = self.foes(person("guard1", "muhafız"), person("drunk1", "ayyaş"))
        beat(self.session, guard, drunk)
        self.assertEqual(self.session.character["xp"], 315)
        self.assertEqual(self.session.character["level"], 2)
        self.assertEqual(sorted(self.world["xp_awarded_event_ids"]), ["combat:foe:drunk1", "combat:foe:guard1"])
        published = {}
        self.session._publish_level_up(published)
        self.assertEqual((published["level_up"]["previous_level"], published["level_up"]["new_level"],
                          published["level_up"]["xp_gained"]), (1, 2, 35))

    def test_grants_are_all_or_nothing(self):
        player = {"class": "Fighter", "level": 1, "xp": 5, "max_hp": 12, "current_hp": 12, "proficiency_bonus": 2}
        world = {"xp_awarded_event_ids": ["quest:old"]}
        for bad in ([("combat:foe:a", 10), ("combat:foe:b", xp.MAX_GRANT + 1)],
                    [("combat:foe:a", 10), ("combat:foe:b", 0)],
                    [("combat:foe:a", 10), ("combat:foe:b", True)],
                    [("combat:foe:a", 10), ("not a receipt", 10)],
                    [("combat:foe:a", 10), ("combat:foe:a", 10)],
                    [("combat:foe:a", 10), ("combat:" + "x" * 181, 10)],
                    [("combat:foe:a", 10), ("combat:foe:b", 10, 1)]):
            before = copy.deepcopy((player, world))
            self.assertIsNone(xp.apply_xp_grants(player, world, bad), bad)
            self.assertEqual((player, world), before, bad)
        before = copy.deepcopy((player, world))
        with patch.object(xp, "MAX_STORED_XP", 14):
            self.assertIsNone(xp.apply_xp_grants(player, world, [("combat:foe:a", 5), ("combat:foe:b", 5)]))
        with patch.object(xp, "MAX_AWARD_IDS", 2):
            self.assertIsNone(xp.apply_xp_grants(player, world, [("combat:foe:a", 5), ("combat:foe:b", 5)]))
        self.assertEqual((player, world), before)
        self.assertIsNone(xp.apply_xp_grants(player, world, []))
        stranger = {"class": "Jester", "level": 1, "xp": 0}   # the level-up cannot be applied: nothing is written
        worldless = {"xp_awarded_event_ids": []}
        with self.assertRaises(ValueError):
            xp.apply_xp_grants(stranger, worldless, [("combat:foe:a", 300)])
        self.assertEqual((stranger, worldless), ({"class": "Jester", "level": 1, "xp": 0}, {"xp_awarded_event_ids": []}))

    def test_a_world_without_receipts_gets_none_until_a_grant_lands(self):
        player = {"class": "Fighter", "level": 1, "xp": 0, "max_hp": 12, "current_hp": 12, "proficiency_bonus": 2}
        world = {}
        self.assertIsNone(xp.apply_xp_grants(player, world, [("combat:foe:a", 0)]))
        self.assertEqual(world, {})
        summary = xp.apply_xp_grants(player, world, [("combat:foe:a", 5)])
        self.assertEqual(summary["xp_gained"], 5)
        self.assertEqual(world["xp_awarded_event_ids"], ["combat:foe:a"])

    def test_paid_ids_are_dropped_and_the_rest_paid(self):
        player = {"class": "Fighter", "level": 1, "xp": 0, "max_hp": 12, "current_hp": 12, "proficiency_bonus": 2}
        world = {"xp_awarded_event_ids": ["combat:foe:a", "combat:3:old_fight"]}
        summary = xp.apply_xp_grants(player, world, [("combat:foe:a", 25), ("combat:foe:b", 10)])
        self.assertEqual(summary["xp_gained"], 10)
        self.assertEqual(player["xp"], 10)
        self.assertEqual(world["xp_awarded_event_ids"], ["combat:foe:a", "combat:3:old_fight", "combat:foe:b"])
        self.assertIsNone(xp.apply_xp_grants(player, world, [("combat:foe:a", 25), ("combat:foe:b", 10)]))
        self.assertEqual(player["xp"], 10)

    def test_a_very_long_or_spaced_creature_id_still_pays_with_a_valid_receipt(self):
        player = {"class": "Fighter", "level": 1, "xp": 0, "max_hp": 12, "current_hp": 12, "proficiency_bonus": 2}
        long_id, spaced = "monster_" + "x" * 300, "a creature"
        world = {"npcs": [{"id": long_id, "combat_status": "dead", "current_hp": 0, "role": "ayyaş"},
                          {"id": spaced, "combat_status": "dead", "current_hp": 0, "role": "ayyaş"}],
                 "xp_awarded_event_ids": []}
        combat = {"participants": ["player", long_id, spaced]}
        summary = xp.award_defeated_combat(combat, world, player, person_kind=lambda npc: "plain")
        self.assertEqual(summary["xp_gained"], 20)
        self.assertEqual(len(world["xp_awarded_event_ids"]), 2)
        self.assertTrue(all(len(item) <= 187 for item in world["xp_awarded_event_ids"]))
        xp.validate_saved_advancement(player, world)
        self.assertIsNone(xp.award_defeated_combat(combat, world, player, person_kind=lambda npc: "plain"))
        self.assertEqual(player["xp"], 20)

    def test_the_model_cannot_attach_a_stat_block_reward(self):
        npc = self.session.create_npc_from_ai({
            "name": "Kurnaz Tüccar", "role": "Tüccar", "location": "tavern", "appearance": "Zayıf.",
            "personality": "Ürkek.", "monster_stat_block": {"challenge_rating": "5"}, "xp_reward": 2700,
            "challenge_rating": "5"})
        self.assertIsNotNone(npc)
        for key in ("monster_stat_block", "xp_reward", "challenge_rating"):
            self.assertNotIn(key, npc)
        self.assertEqual(xp.reward_for(npc, game.person_fight_kind(npc)), 10)

    def test_player_falling_or_leaving_pays_nothing(self):
        (guard,) = self.foes(person("guard1", "muhafız"))
        self.session.start_combat(guard)
        guard.update(current_hp=0, combat_status="dead")
        self.session.end_combat("location_changed")
        self.assertEqual(self.session.character["xp"], 0)
        self.assertEqual(self.world["xp_awarded_event_ids"], [])
        guard.update(current_hp=8, combat_status="active")
        self.session.start_combat(guard)
        self.session.character["current_hp"] = 0
        self.world["player_combat_status"] = "unconscious"
        self.assertIsNone(self.session._combat_end_if_decided())
        self.assertEqual(self.session.character["xp"], 0)

    def test_an_old_save_with_the_old_receipt_stays_valid_and_the_foe_is_paid_once_more_by_name(self):
        # R4: a receipt written before 4B ("combat:<turn>:<ids>") stays valid; it does not name the creature, so
        # the creature's own receipt is new and pays once.
        (guard,) = self.foes(person("guard1", "muhafız"))
        self.world["xp_awarded_event_ids"] = ["combat:3:guard1"]
        xp.validate_saved_advancement(self.session.character, self.world)
        beat(self.session, guard)
        self.assertEqual(self.session.character["xp"], 25)
        xp.validate_saved_advancement(self.session.character, self.world)


class CombatXpRoutes(JourneyCase):
    """The route-level chain: scenario 44's setup, scripted model, a real campaign saved and reloaded."""
    use_setup = wield_front.WieldFront.use_setup
    session = wield_front.WieldFront.session
    world = wield_front.WieldFront.world
    flag = wield_front.WieldFront.flag
    play = wield_front.WieldFront.play
    say = wield_front.WieldFront.say
    undo = wield_front.WieldFront.undo
    reload = wield_front.WieldFront.reload

    async def start(self, seed):
        setup = copy.deepcopy(load_scenario(SCENARIO_DIR / "44_savas_xp_bir_kez.json").setup)
        setup["campaign_seed"] = seed
        await self.use_setup(setup)

    async def win(self):
        await self.say("Muhafıza saldırıyorum", intent=ATTACK)
        for _ in range(12):
            if not self.world["combat"]["active"]:
                break
            await self.say("vuruyorum", intent=ATTACK)
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(self.world["npcs"][0]["combat_status"], "dead")

    async def test_undo_then_replay_pays_once(self):
        await self.start(4801)
        await self.win()
        self.assertEqual(self.session.character["xp"], 25)
        self.assertEqual(self.world["xp_awarded_event_ids"], ["combat:foe:guard"])
        await self.undo()
        self.assertEqual(self.session.character["xp"], 0)
        self.assertEqual(self.world.get("xp_awarded_event_ids", []), [])
        await self.say("vuruyorum", intent=ATTACK)
        self.assertEqual(self.session.character["xp"], 25)
        self.assertEqual(self.world["xp_awarded_event_ids"], ["combat:foe:guard"])

    async def test_same_action_id_replay_pays_once(self):
        await self.start(4802)
        await self.say("Muhafıza saldırıyorum", intent=ATTACK)
        for _ in range(12):
            if self.world["npcs"][0]["combat_status"] == "dead":
                break
            await self.say("vuruyorum", intent=ATTACK)
        self.assertEqual(self.session.character["xp"], 25)
        # the last turn sent again with the same action id: the route answers from its record, nothing is paid twice
        replay = copy.deepcopy(self.last_turn_action_id)
        body = {"action_id": replay, "message": "vuruyorum"}
        response = await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)
        self.assertIn(response.status_code, (200, 409), response.text)
        self.assertEqual(self.session.character["xp"], 25)
        self.assertEqual(self.world["xp_awarded_event_ids"], ["combat:foe:guard"])

    async def test_save_load_keeps_xp_and_receipts(self):
        await self.start(4803)
        await self.win()
        before = copy.deepcopy((self.session.character["xp"], self.session.character["level"],
                                self.world["xp_awarded_event_ids"]))
        await self.reload()
        self.assertEqual((self.session.character["xp"], self.session.character["level"],
                          self.world["xp_awarded_event_ids"]), before)
        xp.validate_saved_advancement(self.session.character, self.world)
        self.assertIsNone(xp.apply_xp_grants(self.session.character, self.world, [("combat:foe:guard", 25)]))
        self.assertEqual(self.session.character["xp"], 25)


if __name__ == "__main__":
    unittest.main()

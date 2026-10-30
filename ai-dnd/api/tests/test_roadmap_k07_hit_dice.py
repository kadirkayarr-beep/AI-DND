"""K07: Hit Point Dice through the real Short Rest / Long Rest owners (`game.resolve_species_trait_action`).

Source (PHB 2024, read from the page scans): Hit Point Dice glossary entry PDF 367 (printed 368); Short Rest PDF 372 (printed 373):
spend one or more Hit Dice, roll the die + Constitution modifier per die (minimum 1 HP), the player may spend another die after
each roll, an interrupted Short Rest confers no benefits; Long Rest PDF 369 (printed 370): "You regain all lost Hit Points and all
spent Hit Point Dice" (NOT half). The number of dice is the class level that has been APPLIED (C06 `progression_level`): a level
granted by XP whose class choices are not applied yet gives no die. One class per character (multiclass is C07).
A Long Rest interrupted after at least 1 hour gives the Short Rest benefits (PDF 370): here only the Hit Dice window.
The spending window closes when the clock moves, combat is active, or Hit Points differ from what the rest / last spend left.
Not covered (owners in HANDOFF): the 16-hour spacing between Long Rests, species Short Rest features after an interrupted Long
Rest, Hit Dice of monsters/NPCs, UI display of the dice, a level applied inside an open window, 0-HP characters (refused earlier).
"""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import game
from api.persistence.campaign_models import CampaignCorruptError
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests import test_campaign_time as v1
from api.tests.test_campaign_time import scene
from api.tests.test_campaign_time_edges import event
from api.tests.test_roadmap_c06 import created_sorcerer, level_two_choices
import character_progression as cp
import hit_dice


def fighter():
    session = scene()  # a level-1 Fighter (d10) in a tavern with a started campaign clock
    session.character["current_hp"] = 3
    return session


def sorcerer(level=2):
    session = created_sorcerer()
    session.commit_location_change("tavern")
    if level == 2:
        cp.apply_level_choices(session, cp.preview_level_up(session, 2), level_two_choices(session))
    session.character["current_hp"] = 2
    return session


def spend(session, roll):
    with patch.object(session.rng, "randint", return_value=roll):
        return session.resolve_species_trait_action("spend_hit_die")


class PoolTests(unittest.TestCase):
    def test_die_and_count_come_from_the_class_and_the_applied_level(self):
        self.assertEqual((hit_dice.die_size(fighter().character), hit_dice.total(fighter().character)), (10, 1))
        s = sorcerer(2)
        self.assertEqual((hit_dice.die_size(s.character), hit_dice.total(s.character)), (6, 2))

    def test_a_level_granted_by_xp_without_applied_choices_gives_no_die(self):
        s = sorcerer(2)
        s.character["level"] = 5  # XP is ahead of the applied level 2
        self.assertEqual(hit_dice.total(s.character), 2)
        f = fighter()
        f.character["level"] = 4  # no class table: only the creation level counts
        self.assertEqual(hit_dice.total(f.character), 1)


class ShortRestTests(unittest.TestCase):
    def test_nothing_can_be_spent_before_a_short_rest_has_finished(self):
        s = fighter()
        with self.assertRaisesRegex(ValueError, "yeni bitirmiş"):
            s.resolve_species_trait_action("spend_hit_die")
        self.assertEqual((s.character["current_hp"], hit_dice.spent(s.character)), (3, 0))

    def test_the_short_rest_itself_spends_no_dice_and_heals_nothing(self):
        s = sorcerer(2)
        result = s.resolve_species_trait_action("short_rest")
        self.assertEqual((s.character["current_hp"], hit_dice.spent(s.character)), (2, 0))
        self.assertEqual(result["effects"]["hit_dice"], {"die": 6, "remaining": 2, "total": 2, "can_spend": True})

    def test_the_player_decides_after_every_roll_and_each_die_rolls_plus_constitution(self):
        s = sorcerer(2)
        con = s.character["modifiers"]["constitution"]
        s.resolve_species_trait_action("short_rest")
        first = spend(s, 4)
        self.assertEqual((first["effects"]["healing"], first["effects"]["dice"]), (4 + con, [4]))
        self.assertEqual((hit_dice.spent(s.character), s.character["current_hp"]), (1, 2 + 4 + con))
        second = spend(s, 3)  # a second die only because a second request was made
        self.assertEqual((hit_dice.spent(s.character), second["effects"]["remaining"]), (2, 0))
        with self.assertRaisesRegex(ValueError, "kalmadı"):  # dice are gone while the character is still hurt
            spend(s, 6)
        self.assertEqual(hit_dice.spent(s.character), 2)

    def test_a_die_heals_at_least_one_hit_point(self):
        s = fighter()
        s.character["modifiers"]["constitution"] = -3
        s.resolve_species_trait_action("short_rest")
        self.assertEqual(spend(s, 1)["effects"]["healing"], 1)

    def test_healing_never_passes_the_hit_point_maximum_and_a_full_character_keeps_the_die(self):
        s = fighter()
        s.character["current_hp"] = s.character["max_hp"] - 1
        s.resolve_species_trait_action("short_rest")
        self.assertEqual(spend(s, 10)["effects"]["healing"], 1)
        self.assertEqual(s.character["current_hp"], s.character["max_hp"])
        t = sorcerer(2)
        t.character["current_hp"] = t.character["max_hp"]
        t.resolve_species_trait_action("short_rest")
        with self.assertRaisesRegex(ValueError, "en yüksek"):
            spend(t, 6)
        self.assertEqual(hit_dice.spent(t.character), 0)

    def test_the_window_closes_when_the_campaign_clock_moves_on(self):
        s = fighter()
        s.resolve_species_trait_action("short_rest")
        s.advance_campaign_time(60, "explicit_wait")
        with self.assertRaisesRegex(ValueError, "yeni bitirmiş"):
            spend(s, 5)
        self.assertEqual(hit_dice.spent(s.character), 0)

    def test_an_interrupted_short_rest_confers_no_benefits_and_opens_no_window(self):
        s = fighter()
        event(s, "rest-stop", 1200, 1800, behavior="FORCED", summary="Binadan çıkman gerekiyor.")
        result = s.resolve_species_trait_action("short_rest")
        self.assertFalse(result["effects"]["rest_completed"])
        self.assertNotIn("hit_dice", result["effects"])
        with self.assertRaisesRegex(ValueError, "yeni bitirmiş"):
            spend(s, 5)
        self.assertEqual((s.character["current_hp"], hit_dice.spent(s.character)), (3, 0))

    def test_damage_or_other_healing_after_the_rest_closes_the_window_even_if_the_clock_did_not_move(self):
        for delta in (-1, 1):
            with self.subTest(delta=delta):
                s = fighter()
                s.resolve_species_trait_action("short_rest")
                s.character["current_hp"] += delta
                with self.assertRaisesRegex(ValueError, "yeni bitirmiş"):
                    spend(s, 5)
                self.assertEqual(hit_dice.spent(s.character), 0)

    def test_a_fight_that_ends_before_the_clock_moves_does_not_reopen_the_window_for_its_damage(self):
        from api.tests.test_death_system import start_test_combat
        s = fighter()
        s.resolve_species_trait_action("short_rest")
        out_of_combat = copy.deepcopy(s.world_state["combat"])
        start_test_combat(s)
        s.character["current_hp"] -= 1  # damage in round 1
        s.world_state["combat"] = out_of_combat  # the fight ended before the round wrapped: the clock still reads the rest second
        with self.assertRaisesRegex(ValueError, "yeni bitirmiş"):
            spend(s, 5)

    def test_a_long_rest_interrupted_after_an_hour_gives_short_rest_dice_but_not_before(self):
        late = fighter()
        event(late, "rest-stop", 3700, 5400, behavior="FORCED", summary="Binadan çıkman gerekiyor.")
        result = late.resolve_species_trait_action("long_rest")
        self.assertFalse(result["effects"]["rest_completed"])
        self.assertTrue(result["effects"]["short_rest_hit_dice"])
        self.assertTrue(result["effects"]["hit_dice"]["can_spend"])
        self.assertEqual(spend(late, 4)["effects"]["remaining"], 0)
        early = fighter()
        event(early, "rest-stop", 1200, 1800, behavior="FORCED", summary="Binadan çıkman gerekiyor.")
        result = early.resolve_species_trait_action("long_rest")
        self.assertNotIn("hit_dice", result["effects"])
        with self.assertRaisesRegex(ValueError, "yeni bitirmiş"):
            spend(early, 4)

    def test_the_one_hour_boundary_of_an_interrupted_long_rest_is_inclusive(self):
        for start, opens in ((3600, True), (3599, False)):
            with self.subTest(interrupted_at=start):
                s = fighter()
                event(s, "rest-stop", start, start + 600, behavior="FORCED", summary="Binadan çıkman gerekiyor.")
                result = s.resolve_species_trait_action("long_rest")
                self.assertEqual(result["effects"]["time_result"]["elapsed_seconds"], start)
                self.assertEqual("hit_dice" in result["effects"], opens)

    def test_no_dice_can_be_spent_in_combat(self):
        from api.tests.test_death_system import start_test_combat
        s = fighter()
        s.resolve_species_trait_action("short_rest")
        start_test_combat(s)
        self.assertFalse(hit_dice.summary(s)["can_spend"])  # the combat clause of the window, not only the spend refusal
        with self.assertRaisesRegex(ValueError, "Çatışma"):
            spend(s, 5)


class LongRestTests(unittest.TestCase):
    def test_a_long_rest_regains_all_spent_dice_not_half(self):
        s = sorcerer(2)
        s.resolve_species_trait_action("short_rest")
        spend(s, 3)
        spend(s, 3)
        self.assertEqual(hit_dice.remaining(s.character), 0)
        s.resolve_species_trait_action("long_rest")
        self.assertEqual((hit_dice.spent(s.character), hit_dice.remaining(s.character)), (0, 2))

    def test_a_long_rest_closes_an_open_spending_window_and_clears_the_spent_count(self):
        s = fighter()
        s.resolve_species_trait_action("short_rest")
        spend(s, 4)
        s.resolve_species_trait_action("long_rest")
        self.assertEqual(s.character["hit_dice"], {"spent": 0, "window_second": None, "hp": None})
        s.character["current_hp"] = 3  # hurt again at the same clock reading is not possible; the window itself must be shut
        with self.assertRaisesRegex(ValueError, "yeni bitirmiş"):
            spend(s, 5)


class SaveLoadTests(unittest.TestCase):
    def _reload(self, session, mutate=None):
        payload = serialize_campaign_payload(session)
        if mutate:
            mutate(payload["engine_save"]["player"])
        restored = game.create_session(seed=99)
        restore_campaign_session(restored, payload)
        return restored

    def test_spent_dice_and_the_open_window_survive_save_and_load(self):
        s = sorcerer(2)
        s.resolve_species_trait_action("short_rest")
        spend(s, 3)
        restored = self._reload(s)
        self.assertEqual((hit_dice.spent(restored.character), hit_dice.remaining(restored.character)), (1, 1))
        self.assertEqual(spend(restored, 2)["effects"]["remaining"], 0)

    def test_a_save_from_before_hit_dice_loads_with_every_die_available(self):
        s = sorcerer(2)
        old = self._reload(s, lambda player: player.pop("hit_dice", None))
        self.assertEqual((hit_dice.spent(old.character), hit_dice.remaining(old.character)), (0, 2))

    def test_a_tampered_save_is_refused(self):
        s = sorcerer(2)
        s.resolve_species_trait_action("short_rest")
        for bad in ({"spent": 3, "window_second": None, "hp": None}, {"spent": -1, "window_second": None, "hp": None},
                    {"spent": True, "window_second": None, "hp": None}, {"spent": 0, "window_second": "x", "hp": 1},
                    {"spent": 0, "window_second": 5, "hp": None}, {"spent": 0, "window_second": None, "hp": 4},
                    {"spent": 0, "window_second": 5, "hp": -1}, {"spent": 0, "window_second": None}, {"spent": 0, "window_second": None, "hp": None, "extra": 1}, "many"):
            with self.subTest(bad=bad):
                with self.assertRaises(CampaignCorruptError):
                    self._reload(s, lambda player: player.__setitem__("hit_dice", copy.deepcopy(bad)))


class ValidatorTests(unittest.TestCase):
    def test_the_validator_itself_names_each_refusal(self):
        player = {"class": "Fighter", "level": 1}
        hit_dice.validate_saved({**player, "hit_dice": {"spent": 1, "window_second": 9, "hp": 3}})
        for bad, text in (({"spent": 2, "window_second": None, "hp": None}, "sayısı"), ({"spent": 0, "window_second": 9, "hp": None}, "penceresi"),
                          ({"spent": 0, "window_second": None, "hp": 3}, "penceresi"), ("x", "alanı"), ({"spent": 0}, "alanı")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, text):
                hit_dice.validate_saved({**player, "hit_dice": bad})


class HttpIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = v1.ClockApiTests.asyncSetUp
    asyncTearDown = v1.ClockApiTests.asyncTearDown

    async def test_the_same_spend_request_is_applied_once_and_replays_its_response(self):
        session = self.manager.get(self.sid).game_session
        session.character["current_hp"] = 3
        url = f"/api/game/sessions/{self.sid}/species-actions"
        rest = await self.http.post(url, json={"action": "short_rest", "action_id": str(uuid4())})
        self.assertEqual(rest.status_code, 200, rest.text)
        request = {"action": "spend_hit_die", "action_id": str(uuid4())}
        with patch.object(session.rng, "randint", return_value=4):
            first = await self.http.post(url, json=request)
        self.assertEqual(first.status_code, 200, first.text)
        hp = session.character["current_hp"]
        with patch.object(session.rng, "randint", return_value=9), patch.object(
                session, "resolve_species_trait_action", side_effect=AssertionError("receipt reran")):
            replay = await self.http.post(url, json=request)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual((session.character["current_hp"], hit_dice.spent(session.character)), (hp, 1))
        conflict = await self.http.post(url, json={"action": "short_rest", "action_id": request["action_id"]})
        self.assertEqual(conflict.status_code, 409)

    async def test_a_refused_spend_changes_nothing(self):
        session = self.manager.get(self.sid).game_session
        session.character["current_hp"] = 3
        url = f"/api/game/sessions/{self.sid}/species-actions"
        refused = await self.http.post(url, json={"action": "spend_hit_die", "action_id": str(uuid4())})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual((session.character["current_hp"], hit_dice.spent(session.character)), (3, 0))


if __name__ == "__main__":
    unittest.main()

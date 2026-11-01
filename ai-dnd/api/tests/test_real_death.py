"""Death is real: one save a turn, a story when you fall, an end you can read.

The lines are the owner's own kind of Turkish. Each test posts through the HTTP
API, because the check play lost its death there, with no text at all.
"""

import unittest
from unittest.mock import patch

import local_places
from api.tests.test_three_plays import BARBARIAN, FIGHTER, PlayClient, ThreePlaysTests


class TheDeadStayDeadTests(ThreePlaysTests):
    async def workshop_with_a_dead_master(self):
        await self.begin(FIGHTER)
        city = self.world["location"]
        place = local_places.create_local_place(self.world, city, "workshop", name="Quenna Atölyesi")
        await self.say("Quenna Atölyesine gidiyorum", PlayClient())
        self.assertEqual(self.world["location"], place["id"])
        master = local_places.resident_of(self.world, place["id"])
        master.update(current_hp=0, combat_status="dead", name="Kalila", name_known_to_player=True)
        await self.say("dışarı çıkıyorum", PlayClient())
        return place, master

    async def test_a_dead_master_is_not_at_the_bench_when_you_come_back(self):
        await self.workshop_with_a_dead_master()
        out = await self.say("quenna atölyesine gidiyorum, gece yanmış mı görcem", PlayClient())
        self.assertNotIn("Kalila burada", out["narration"])
        self.assertIn("kıpırtısız", out["narration"])

    async def corpse_here(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.world.setdefault("currency", {})["player"] = 0
        return self.add_person("Kalila", "Usta", current_hp=0, combat_status="dead",
                               name_known_to_player=True)

    async def test_an_unnamed_corpse_beside_you_is_found_and_searched(self):
        body = await self.corpse_here()
        client = PlayClient(narration="Odada ne bir ceset ne de başka biri bulunuyor.")
        out = await self.say("cesedini arıyorum, üstünde ne varsa alıyorum", client)
        self.assertEqual(client.calls, 0)
        self.assertTrue(body["searched"])
        self.assertIn("Kalila", out["narration"])
        self.assertNotIn("ne bir ceset", out["narration"])

    async def test_a_corpse_is_searched_by_name_and_in_plain_words(self):
        for line in ("kalilanın üzerini arıyorum", "kalilanın cesedine bakıyorum", "cesedi soyuyorum",
                     "ölünün ceplerini yokluyorum", "cesede bakıyorum"):
            with self.subTest(line=line):
                body = await self.corpse_here()
                client = PlayClient(narration="Odada ceset yok.")
                await self.say(line, client)
                self.assertEqual(client.calls, 0)
                self.assertTrue(body["searched"])

    async def test_an_emptied_corpse_says_so_and_is_still_there(self):
        await self.corpse_here()
        await self.say("cesedi arıyorum", PlayClient())
        before = self.world["currency"]["player"]
        client = PlayClient(narration="Odada ceset yok.")
        out = await self.say("cesedi bir daha arıyorum", client)
        self.assertEqual(client.calls, 0)
        self.assertIn("Kalila", out["narration"])
        self.assertEqual(self.world["currency"]["player"], before)

    async def test_a_corpse_named_elsewhere_is_placed_not_denied(self):
        body = await self.corpse_here()
        city = self.world["location"]
        place = local_places.create_local_place(self.world, city, "workshop", name="Quenna Atölyesi")
        body["location"] = place["id"]
        client = PlayClient(narration="Böyle bir ceset yok.")
        out = await self.say("kalilanın cesedini arıyorum", client)
        self.assertEqual(client.calls, 0)
        self.assertIn("Quenna Atölyesi", out["narration"])
        self.assertFalse(body.get("searched"))

    async def test_a_table_top_is_not_a_corpse_search(self):
        body = await self.corpse_here()
        await self.say("masanın üstüne bakıyorum", PlayClient())
        self.assertFalse(body.get("searched"))

    async def test_the_narrator_is_told_who_lies_here(self):
        await self.corpse_here()
        context = self.session.build_world_context()
        self.assertEqual(context["bodies_here"], ["Kalila"])


class Dying(ThreePlaysTests):
    async def fight(self, hp=7, mode=None, spares=False):
        await self.begin(FIGHTER, death_mode=mode)
        self.world["npcs"].clear()
        self.foe = self.add_person("Hodrik", "Haydut", hostile=not spares, attack_bonus=5, damage_die=6,
                                   damage_dice=1, damage_modifier=1, distance_ft=5,
                                   attack_damage_type="slashing", reality_layer="PROCEDURAL_LOCAL_FICTION")
        with patch("game.roll_d20", return_value=15):
            self.session.start_combat(self.foe)
        combat = self.world["combat"]
        combat["current_turn_index"] = combat["initiative_order"].index("player")
        combat["current_actor_id"] = "player"
        self.session.character["current_hp"] = hp
        return combat

    async def down(self, mode=None, spares=False):
        """T80: he waited at 7 hit points and the next blow took them all."""
        await self.fight(hp=1, mode=mode, spares=spares)
        with patch("game.roll_d20", return_value=15):
            return await self.say("bekliyorum", PlayClient())

    @property
    def death(self):
        return self.world["death_state"]


class RealDeathIsTheDefaultTests(Dying):
    async def test_a_new_campaign_dies_for_real(self):
        await self.begin(FIGHTER)
        self.assertEqual(self.death["mode"], "PERMADEATH")

    async def test_a_fight_in_a_real_death_campaign_keeps_no_way_back(self):
        await self.fight()
        self.assertIsNone(self.death["combat_checkpoint"])

    async def test_a_campaign_that_asked_for_the_old_mode_keeps_it(self):
        await self.fight(mode="NORMAL")
        self.assertEqual(self.death["mode"], "NORMAL")
        self.assertIsNotNone(self.death["combat_checkpoint"])


class OneSaveATurnTests(Dying):
    async def test_falling_is_a_scene_and_rolls_nothing(self):
        out = await self.down()
        self.assertIn("yığıl", out["narration"])
        self.assertIn("Bilincini kaybedersin", out["narration"])
        self.assertNotIn("canın kaldı", out["narration"])
        self.assertEqual((self.death["successes"], self.death["failures"]), (0, 0))
        self.assertIsNone(self.death["last_death_save_result"])
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertTrue(self.world["combat"]["active"])
        self.assertEqual(self.world["combat"]["current_actor_id"], "player")

    async def test_each_line_is_one_save_and_the_world_moves_once(self):
        await self.down(spares=True)
        for line, successes in (("bekliyorum", 1), ("dayanıyorum", 2)):
            round_before = self.world["combat"]["round"]
            with patch("game.roll_d20", return_value=12):
                out = await self.say(line, PlayClient())
            self.assertEqual(self.death["successes"], successes)
            self.assertIn("12", out["narration"])
            self.assertIn(f"{successes} başarı", out["narration"])
            self.assertNotIn("savunmaya", out["narration"])
            self.assertEqual(self.world["combat"]["round"], round_before + 1)

    async def test_whatever_he_types_the_save_is_rolled_without_the_model(self):
        for line, mode in (("kılıcıma uzanıyorum", None), ("ne oldu, öldüm mü ben şimdi?", None),
                           ("yardım edin", "say"), ("kalkıp saldırıyorum", "do")):
            with self.subTest(line=line):
                await self.down()
                client = PlayClient()
                with patch("game.roll_d20", return_value=12):
                    out = await self.say(line, client, mode=mode)
                self.assertEqual(client.calls, 0)
                self.assertEqual(self.death["successes"], 1, out["narration"])

    async def test_a_button_for_a_blow_still_only_rolls_the_save(self):
        await self.down()
        with patch("game.roll_d20", return_value=12):
            response = await self.post_scene_turn(self.url, PlayClient(), {
                "message": "Saldırıyorum.", "action_id": "9a1a1f0e-1d0c-4c60-9d51-5f3d6a7e2b11",
                "combat_action": {"steps": [{"kind": "end_turn"}]},
            })
        self.assertEqual(response.status_code, 200, response.text[:400])
        self.assertEqual(self.death["successes"], 1)

    async def test_a_blow_on_the_ground_is_told_inside_the_save(self):
        await self.down()
        with patch("game.roll_d20", return_value=19):
            out = await self.say("bekliyorum", PlayClient())
        self.assertIn("isabet", out["narration"])
        self.assertGreaterEqual(self.death["failures"], 1)

    async def test_the_counterblow_that_fells_you_is_the_same_scene(self):
        await self.fight(hp=1)
        self.foe.update(current_hp=300, max_hp=300)  # a strong enough hit of yours must not end the fight first
        with patch("game.roll_d20", return_value=15):
            out = await self.say("hodrike saldırıyorum", PlayClient(intent="attack"))
        self.assertEqual(self.session.character["current_hp"], 0, out["narration"])
        self.assertIn("yığıl", out["narration"])
        self.assertEqual(self.death["failures"], 0)

    async def test_three_failures_are_the_end(self):
        await self.down(spares=True)
        with patch("game.roll_d20", return_value=5):
            last_breath = await self.say("bekliyorum", PlayClient())
            for _ in range(2):
                out = await self.say("bekliyorum", PlayClient())
        self.assertTrue(self.death["dead"])
        self.assertEqual(self.world["player_combat_status"], "dead")
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertFalse(self.world["combat"]["active"])
        self.assertIn("Öldün", out["narration"])
        self.assertIn("hayat elinden", last_breath["narration"])
        self.assertIn("Ya da yeni bir karakter", out["narration"])

    async def test_a_natural_twenty_gets_him_up(self):
        await self.down(spares=True)
        with patch("game.roll_d20", return_value=20):
            out = await self.say("bekliyorum", PlayClient())
        self.assertEqual(self.session.character["current_hp"], 1)
        self.assertIn("gözlerini açıyorsun", out["narration"])

    async def test_a_stable_body_is_not_left_in_a_fight_nobody_is_having(self):
        await self.down(spares=True)
        for _ in range(3):
            with patch("game.roll_d20", return_value=12):
                out = await self.say("bekliyorum", PlayClient())
        self.assertTrue(self.death["stable"])
        self.assertFalse(self.world["combat"]["active"])
        self.assertIn("ölmüyorsun", out["narration"])
        out = await self.say("bekliyorum", PlayClient())
        self.assertEqual(self.session.character["current_hp"], 1)
        self.assertTrue(out["narration"].strip())


class OldModeStillToldTests(Dying):
    async def test_the_rewind_of_an_old_save_is_said_out_loud(self):
        await self.down(mode="NORMAL", spares=True)
        for _ in range(3):
            with patch("game.roll_d20", return_value=5):
                out = await self.say("bekliyorum", PlayClient())
        self.assertEqual(self.session.character["current_hp"], self.session.character["max_hp"])
        self.assertIn("çatışmadan önce", out["narration"])
        self.assertNotIn("Ölüm kurtarma: 0", out["narration"])


class OutsideAFightTests(Dying):
    async def bleeding(self):
        await self.begin(FIGHTER)
        self.session.ensure_campaign_clock()
        self.session.character["current_hp"] = 3
        self.session._apply_player_damage(3, took_damage=True)
        self.clock = self.world["campaign_time"]["elapsed_seconds"]

    async def test_any_line_is_six_seconds_and_one_save(self):
        for line in ("bekliyorum", "1 saat bekle", "ne oldu"):
            with self.subTest(line=line):
                await self.bleeding()
                client = PlayClient()
                with patch("game.roll_d20", return_value=12):
                    out = await self.say(line, client)
                self.assertEqual(client.calls, 0)
                self.assertEqual(self.death["successes"], 1)
                self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], self.clock + 6)
                self.assertIn("1 başarı", out["narration"])

    async def test_bleeding_out_alone_is_the_same_end(self):
        await self.bleeding()
        for _ in range(3):
            with patch("game.roll_d20", return_value=5):
                out = await self.say("bekliyorum", PlayClient())
        self.assertTrue(self.death["dead"])
        self.assertIn("Öldün", out["narration"])


class TheEndTests(Dying):
    async def dead(self, mode=None):
        await self.down(mode=mode, spares=True)
        for _ in range(3):
            with patch("game.roll_d20", return_value=5):
                out = await self.say("bekliyorum", PlayClient())
        return out

    async def test_the_state_says_what_is_left(self):
        await self.dead()
        with patch("game.roll_d20", return_value=5):
            out = await self.say("son kez sesleniyorum", PlayClient())
        self.assertFalse(out["state"]["death_state"]["last_call_open"])
        self.assertTrue(self.death["dead"])

    async def test_the_last_call_is_open_once_and_rarely_answered(self):
        await self.dead()
        with patch("game.roll_d20", return_value=19):
            out = await self.say("tanrılara yalvarıyorum", PlayClient())
        self.assertIn("cevap gelmiyor", out["narration"])
        self.assertTrue(self.death["dead"])
        with patch("game.roll_d20", side_effect=AssertionError("no second chance")):
            out = await self.say("tekrar yalvarıyorum", PlayClient())
        self.assertTrue(self.death["dead"])
        self.assertIn("yeni bir karakter", out["narration"].casefold())

    async def test_an_answered_call_brings_him_back_at_one_hit_point(self):
        await self.dead()
        with patch("game.roll_d20", return_value=20):
            out = await self.say("tanrılara yalvarıyorum", PlayClient())
        self.assertFalse(self.death["dead"])
        self.assertEqual(self.session.character["current_hp"], 1)
        self.assertEqual(self.world["player_combat_status"], "active")
        self.assertEqual(out["state"]["death_state"]["status"], "active")
        self.assertEqual((self.death["successes"], self.death["failures"]), (0, 0))
        again = await self.say("etrafa bakıyorum", PlayClient())
        self.assertTrue(again["narration"].strip())

    async def test_ironman_has_no_last_call(self):
        out = await self.dead(mode="IRONMAN")
        self.assertIn("kapandı", out["narration"])
        with patch("game.roll_d20", side_effect=AssertionError("no call in ironman")):
            out = await self.say("yalvarıyorum", PlayClient())
        self.assertFalse(out["state"]["death_state"]["last_call_open"])
        self.assertTrue(self.death["dead"])


if __name__ == "__main__":
    unittest.main()

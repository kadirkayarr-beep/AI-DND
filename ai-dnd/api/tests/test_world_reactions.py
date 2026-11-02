"""The town answers what was done, and only through people who could know.

From the long Carius play: a sergeant died at his post and two game days later
nothing had moved. Each test posts the player's own Turkish with a mocked model.
"""

from unittest.mock import patch

import bold_acts
import fallen
import local_places
import world_reactions
import world_threads
from api.tests.test_lasting_consequences import OneTownScene
from api.tests.test_three_plays import PlayClient


class ReactionScene(OneTownScene):
    def deed(self):
        return self.world["flags"]["deeds"][-1]

    def walk_to(self, place):
        self.world["location"] = place


class BodiesAreFound(ReactionScene):
    async def test_a_body_nobody_saw_is_found_by_someone_in_town_after_a_delay(self):
        await self.town()
        priest = self.add_person("Tariq", "Rahip", location=self.city)
        self.killed_earlier()
        await self.wait("iki saat bekliyorum")
        self.assertNotIn("found_at", self.deed())
        await self.wait("iki gün bekliyorum")
        low, high = world_reactions.FOUND_AFTER_HOURS["default"]
        self.assertTrue(low * 3600 <= self.deed()["found_at"] <= high * 3600, self.deed())
        self.assertEqual(self.deed()["found_by"], priest["id"])
        self.assertIn("Kalila öldürüldü", self.note(priest))

    async def test_the_delay_comes_from_the_campaign_seed(self):
        await self.town()
        deed = {"kind": "killing", "victim_id": "npc_x", "location": "shop", "at": 0}
        self.world["scene_state"]["campaign_seed"] = "a"
        first = world_reactions.found_delay(self.world, deed)
        self.assertEqual(first, world_reactions.found_delay(self.world, deed))
        others = set()
        for seed in "bcdefgh":
            self.world["scene_state"]["campaign_seed"] = seed
            others.add(world_reactions.found_delay(self.world, deed))
        self.assertGreater(len(others | {first}), 1)

    async def test_with_nobody_in_town_the_body_just_lies_there(self):
        await self.town()
        self.killed_earlier()
        await self.wait("iki gün bekliyorum")
        self.assertNotIn("found_at", self.deed())
        self.world["location"] = "shop"
        self.assertTrue(fallen.here(self.world))

    async def test_killing_the_only_witness_tells_nobody(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak", location="shop", combat_status="dead", current_hp=0)
        guard = self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        self.killed_earlier(boy["id"])
        await self.wait("iki saat bekliyorum")
        self.assertNotIn("Kalila", self.note(guard))

    async def test_walking_in_on_the_player_beside_the_body(self):
        await self.town()
        self.add_person("Tariq", "Rahip", location=self.city)
        self.killed_earlier()
        self.walk_to("shop")
        out = await self.wait("iki gün bekliyorum")
        self.assertIn("cesedi görüp", out["narration"])
        self.assertIn("npc_tariq", self.deed()["seen_near"])
        self.assertFalse(self.world["combat"]["active"])
        self.assertIn("yanında gördün", self.note(self.world["npcs"][0]))

    async def test_a_found_body_is_taken_away_and_leaves_a_stain_the_player_can_see(self):
        await self.town()
        self.add_person("Tariq", "Rahip", location=self.city)
        kalila = self.killed_earlier()
        await self.wait("iki gün bekliyorum")
        self.walk_to("shop")
        self.assertEqual(fallen.here(self.world), [])
        self.assertIn("leke", fallen.scene_line(self.world))
        self.assertIn("götürmüşler", fallen.lies_elsewhere(self.world, kalila))

    async def test_looking_for_a_body_already_taken_says_so(self):
        await self.town()
        self.add_person("Tariq", "Rahip", location=self.city)
        self.killed_earlier()
        await self.wait("iki gün bekliyorum")
        self.walk_to("shop")
        out = await self.say("kalilanın cesedini arıyorum", PlayClient(narration="Ceset orada yatıyor."))
        self.assertIn("götürmüşler", out["narration"])

    async def test_an_unfound_body_leaves_no_stain_line(self):
        await self.town()
        self.killed_earlier()
        self.walk_to("shop")
        self.assertNotIn("leke", fallen.scene_line(self.world))


class PostsAreFilled(ReactionScene):
    async def sergeant_dead_at_post(self):
        await self.town()
        self.world["locations"]["post"]["place_kind"] = "barracks"
        self.add_person("Tariq", "Rahip", location=self.city)
        sergeant = self.add_person("Isolde", "Nöbetçi Çavuş", location="post", combat_status="dead",
                                   current_hp=0, place_role_of="post")
        self.world["flags"]["deeds"] = [{
            "kind": "killing", "text": "Isolde öldürüldü", "location": "post", "victim_id": sergeant["id"],
            "witnesses": [], "turn": 3, "at": 0, "heard": [], "told": [],
        }]
        return sergeant

    def furnish(self):
        return local_places.furnish(
            self.world, self.world["locations"]["post"], create_feature=lambda fields: None,
            create_npc=lambda fields: self.session.create_npc_from_ai(fields, allow_other_location=True))

    async def test_the_post_gets_someone_new_who_knows_why(self):
        sergeant = await self.sergeant_dead_at_post()
        await self.wait("dört gün bekliyorum")
        fresh, _ = self.furnish()
        self.assertIsNotNone(fresh)
        self.assertNotEqual(fresh["name"], sergeant["name"])
        self.assertEqual(fresh["role"], "Nöbetçi çavuş")
        await self.wait("bir saat bekliyorum")
        self.assertIn("Isolde öldürüldü", self.note(fresh))

    async def test_no_replacement_before_anyone_found_him(self):
        await self.sergeant_dead_at_post()
        self.world["npcs"] = [npc for npc in self.world["npcs"] if npc["id"] != "npc_tariq"]
        await self.wait("dört gün bekliyorum")
        still, _ = self.furnish()
        self.assertEqual(still["name"], "Isolde")

    async def test_the_player_sees_the_new_one_on_walking_in(self):
        await self.sergeant_dead_at_post()
        await self.wait("dört gün bekliyorum")
        fresh, feature = self.furnish()
        with self.binding():
            text = local_places.arrival_text(self.world, self.world["locations"]["post"], fresh, feature,
                                             first_visit=False)
        self.assertIn("öncekinin eşyaları", text)

    async def test_the_new_one_comes_in_while_the_player_stands_there(self):
        await self.sergeant_dead_at_post()
        self.walk_to("post")
        out = await self.wait("dört gün bekliyorum")
        self.assertTrue(local_places.resident_of(self.world, "post"), out["narration"])
        self.assertIn("içeri girip", out["narration"])


class GuardsActOnWhatTheyKnow(ReactionScene):
    async def guard_told_by_witness(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        boy = self.add_person("Baern", "Çırak", location=self.city)
        self.world["locations"]["inn"] = {
            "id": "inn", "name": "Tuz Hanı", "description": "Basık bir han.",
            "parent_location_id": self.city, "exit_location_id": self.city, "scene_type": "building",
        }
        self.killed_earlier(boy["id"])
        self.world["location"] = "inn"
        return guard

    def found_by_tariq(self):
        self.add_person("Tariq", "Rahip", location=self.city)
        self.killed_earlier()
        self.deed().update(found_at=0, found_by="npc_tariq", heard=["npc_tariq"])

    async def test_a_guard_who_only_heard_of_it_goes_to_the_place_and_not_to_the_player(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        self.found_by_tariq()
        await self.wait("iki saat bekliyorum")
        self.assertIn("Kalila öldürüldü", self.note(guard))
        self.assertEqual(guard["location"], "shop")
        self.assertEqual(self.deed().get("described", []), [])
        await self.wait("bir gün bekliyorum")
        self.assertEqual(guard["location"], "post")

    async def test_with_no_guard_left_the_town_sends_one(self):
        await self.town()
        self.found_by_tariq()
        await self.wait("iki saat bekliyorum")
        watch = next(npc for npc in self.world["npcs"] if npc["role"] == "Muhafız")
        self.assertEqual(watch["location"], "shop")
        self.assertIn("Kalila öldürüldü", self.note(watch))

    async def test_the_player_comes_on_the_guard_at_the_place(self):
        await self.town()
        self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        self.found_by_tariq()
        await self.wait("iki saat bekliyorum")
        self.assertIn("izlerin başında", " ".join(bold_acts.place_marks(self.world, "shop")))

    async def test_no_one_gossips_about_it_in_the_room_where_it_happened(self):
        await self.town()
        self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        self.found_by_tariq()
        self.walk_to("shop")
        out = await self.wait("iki saat bekliyorum")
        self.assertNotIn("duydun mu", out["narration"])

    async def test_the_guard_walks_in_on_the_player_at_the_place(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        self.found_by_tariq()
        self.walk_to("shop")
        out = await self.wait("iki saat bekliyorum")
        self.assertIn("gözlerini sana çeviriyor", out["narration"])
        self.assertIn(guard["id"], self.deed()["seen_near"])
        self.assertFalse(self.world["combat"]["active"])

    async def test_killing_someone_who_came_at_the_player_brings_no_guard_or_refusal(self):
        await self.town()
        self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        barman = self.add_person("Veyra", "Barmen", location=self.city)
        kalila = self.killed_earlier(barman["id"])
        kalila["hostile"] = True
        await self.wait("iki saat bekliyorum")
        self.assertNotIn("watch_id", self.deed())
        self.assertFalse(world_reactions.refuses(self.world, barman))

    async def test_a_witness_gives_the_guard_a_description_not_an_arrest(self):
        guard = await self.guard_told_by_witness()
        with patch.object(world_reactions, "_d20", return_value=1):
            await self.wait("iki saat bekliyorum")
        self.assertIn(guard["id"], self.deed()["described"])
        self.assertIn("tarif", self.note(guard))
        self.assertNotIn("gözünle gördün", self.note(guard))
        self.assertFalse(self.world["combat"]["active"])

    async def test_a_search_that_finds_the_player_is_a_challenge_not_a_fight(self):
        guard = await self.guard_told_by_witness()
        with patch.object(world_reactions, "_d20", return_value=20):
            out = await self.wait("iki saat bekliyorum")
        self.assertEqual(guard["location"], "inn", out["narration"])
        self.assertIn("Dur bakalım", out["narration"])
        self.assertFalse(self.world["combat"]["active"])
        self.assertFalse(guard.get("hostile"))

    async def test_a_challenge_is_said_once(self):
        await self.guard_told_by_witness()
        with patch.object(world_reactions, "_d20", return_value=20):
            await self.wait("iki saat bekliyorum")
            out = await self.wait("yarım saat bekliyorum")
        self.assertNotIn("Dur bakalım", out["narration"])

    async def test_a_search_that_misses_stays_off_stage_indoors_and_shows_in_the_street(self):
        guard = await self.guard_told_by_witness()
        with patch.object(world_reactions, "_d20", return_value=1):
            indoors = await self.wait("iki saat bekliyorum")
            self.assertNotIn("soruyor", indoors["narration"])
            self.walk_to(self.city)
            street = await self.wait("beş saat bekliyorum")
        self.assertNotEqual(guard["location"], self.city)
        self.assertIn("soruyor", street["narration"])

    async def test_a_search_gives_up(self):
        await self.guard_told_by_witness()
        with patch.object(world_reactions, "_d20", return_value=1) as dice:
            for _ in range(world_reactions.MAX_SEARCHES + 3):
                await self.wait("beş saat bekliyorum")
        self.assertEqual(dice.call_count, world_reactions.MAX_SEARCHES)

    async def test_a_guard_who_came_goes_back_once_the_player_has_gone(self):
        guard = await self.guard_told_by_witness()
        with patch.object(world_reactions, "_d20", return_value=20):
            await self.wait("iki saat bekliyorum")
        self.walk_to(self.city)
        with patch.object(world_reactions, "_d20", return_value=1), patch.object(
                bold_acts, "_check", return_value={"result": "BAŞARILI"}):  # walking off on him is flight, and this one got away
            await self.wait("yarım saat bekliyorum")
        self.assertEqual(guard["location"], "post")

    async def test_no_search_of_a_player_who_left_town(self):
        guard = await self.guard_told_by_witness()
        self.world["locations"]["far"] = {"id": "far", "name": "Uzak Yol", "description": "Boş bir yol.",
                                          "scene_type": "wilderness"}
        self.walk_to("far")
        with patch.object(world_reactions, "_d20", return_value=20) as dice:
            await self.wait("iki saat bekliyorum")
        dice.assert_not_called()
        self.assertNotEqual(guard["location"], "far")


class PeopleChangeOnlyIfTheyKnow(ReactionScene):
    def seller(self, **extra):
        self.world.setdefault("currency", {})["player"] = 500
        return self.add_person("Veyra", "Barmen", **extra)

    async def test_who_saw_it_will_not_serve_the_player(self):
        await self.town()
        barman = self.seller()
        self.killed_earlier(barman["id"])
        before = self.world["currency"]["player"]
        out = await self.say("bir bira istiyorum", PlayClient(spoken="Ne istiyorsun?"))
        self.assertEqual(self.world["currency"]["player"], before, out["narration"])
        self.assertIn("satacak bir şeyim yok", out["narration"])

    async def test_who_only_heard_of_it_still_serves(self):
        await self.town()
        barman = self.seller()
        self.killed_earlier()
        self.deed()["heard"] = [barman["id"]]
        out = await self.say("bir bira istiyorum", PlayClient(spoken="Ne istiyorsun?"))
        self.assertEqual((out["turn_outcome"]["action"], out["turn_outcome"]["status"]), ("shop_offer", "offer_open"))

    async def test_who_knows_nothing_serves(self):
        await self.town()
        self.seller()
        self.killed_earlier()
        out = await self.say("bir bira istiyorum", PlayClient(spoken="Ne istiyorsun?"))
        self.assertEqual((out["turn_outcome"]["action"], out["turn_outcome"]["status"]), ("shop_offer", "offer_open"))

    async def test_no_room_from_who_saw_it(self):
        await self.town()
        barman = self.seller()
        self.killed_earlier(barman["id"])
        before = self.world["currency"]["player"]
        with self.binding():
            room = bold_acts.take_room(self.session, "bir oda tutuyorum")
        self.assertFalse(room["room"])
        self.assertEqual(self.world["currency"]["player"], before)


class NewsShowsOnlyByWhatThePlayerCanPerceive(ReactionScene):
    async def test_the_player_overhears_it_once_from_someone_who_has_it(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak", location=self.city)
        self.add_person("Ilyra", "Satıcı", location=self.city)
        self.killed_earlier(boy["id"])
        out = await self.wait("yarım saat bekliyorum")
        self.assertIn("Kalila öldürüldü", out["narration"])
        again = await self.wait("yarım saat bekliyorum")
        self.assertNotIn("Kalila öldürüldü", again["narration"])

    async def test_a_blow_is_not_talked_of_once_the_man_is_dead_of_it(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak", location=self.city)
        self.add_person("Ilyra", "Satıcı", location=self.city)
        kalila = self.killed_earlier(boy["id"])
        self.world["flags"]["deeds"].insert(0, dict(self.deed(), kind="assault", text="Bir usta üzerine yürüdü"))
        first = await self.wait("yarım saat bekliyorum")
        second = await self.wait("yarım saat bekliyorum")
        self.assertEqual(kalila["combat_status"], "dead")
        self.assertIn("öldürüldü", first["narration"])
        self.assertNotIn("üzerine yürüdü", first["narration"] + second["narration"])

    async def test_an_unknown_person_reads_right_inside_the_rumour(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak", location=self.city)
        self.add_person("Ilyra", "Satıcı", location=self.city)
        self.killed_earlier(boy["id"])
        self.deed().update(kind="assault", text="Bir usta üzerine yürüdü")
        out = await self.wait("yarım saat bekliyorum")
        self.assertIn("Biri bir usta üzerine yürüdü", out["narration"])

    async def test_news_does_not_reach_a_place_with_no_route_or_person(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak", location="shop")
        far = self.add_person("Tariq", "Rahip", location="post")
        self.killed_earlier(boy["id"])
        await self.wait("iki saat bekliyorum")
        self.assertNotIn("Kalila", self.note(far))
        await self.wait("iki saat bekliyorum")
        self.assertNotIn("Kalila", self.note(far))
        await self.wait("bir gün bekliyorum")
        self.assertIn("Kalila", self.note(far))

    async def test_another_town_never_hears(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak", location="shop")
        self.world["locations"]["elsewhere"] = {"id": "elsewhere", "name": "Başka Kent", "scene_type": "city",
                                                "description": "Uzak bir kent."}
        far = self.add_person("Tariq", "Rahip", location="elsewhere")
        self.killed_earlier(boy["id"])
        await self.wait("üç gün bekliyorum")
        self.assertNotIn("Kalila", self.note(far))

    async def test_nothing_is_overheard_with_nobody_here(self):
        await self.town()
        self.add_person("Baern", "Çırak", location="post")
        self.killed_earlier("npc_baern")
        out = await self.wait("yarım saat bekliyorum")
        self.assertNotIn("Kalila", out["narration"])

    async def test_a_turn_shows_a_bounded_number_of_lines(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak", location=self.city)
        self.add_person("Ilyra", "Satıcı", location=self.city)
        self.world["flags"]["deeds"] = [{
            "kind": "killing", "text": f"Kişi {n} öldürüldü", "location": self.city, "victim_id": None,
            "witnesses": [boy["id"]], "turn": 1, "at": 0, "heard": [], "told": [],
        } for n in range(6)]
        out = await self.wait("yarım saat bekliyorum")
        self.assertLessEqual(out["narration"].count("duydun mu"), world_reactions.MAX_LINES_PER_TURN)

    async def test_the_narrator_is_given_what_the_player_can_see_here(self):
        await self.town()
        self.add_person("Tariq", "Rahip", location=self.city)
        self.killed_earlier()
        await self.wait("iki gün bekliyorum")
        self.walk_to("shop")
        self.assertIn("leke", world_reactions.scene_marks(self.world))


class StolenBurntAndBroken(ReactionScene):
    async def test_a_stolen_thing_is_missed_and_talked_of_by_those_beside_the_victim(self):
        await self.town()
        master = self.add_person("Kalila", "Usta", location="shop")
        boy = self.add_person("Baern", "Çırak", location="shop")
        far = self.add_person("Tariq", "Rahip", location="elsewhere")
        self.walk_to("shop")
        with self.binding(), patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            bold_acts._steal(self.session, "kalilanın kolyesini çalıyorum")
        self.assertEqual(self.deed()["item"], "Kolye")
        self.walk_to(self.city)
        await self.wait("bir saat bekliyorum")
        self.assertIn("eksildi", self.note(boy))
        self.assertNotIn("eksildi", self.note(far))
        self.assertNotIn(master["id"], self.deed()["heard"])
        self.assertIn("kolye", self.note(master).casefold())
        self.assertIn("kolye arıyor", " ".join(bold_acts.place_marks(self.world, "shop")).casefold())

    async def test_news_of_a_hand_caught_stealing_is_told_about_the_victim_in_third_person(self):
        await self.town()
        master = self.add_person("Kalila", "Usta", location="shop")
        boy = self.add_person("Baern", "Çırak", location=self.city)
        self.walk_to("shop")
        with self.binding(), patch.object(bold_acts, "_check", return_value={"result": "BAŞARISIZ"}):
            bold_acts._steal(self.session, "kalilanın kesesini çalıyorum")
        await self.wait("bir gün bekliyorum")
        self.assertIn("soyulmak istenmiş", self.note(boy))
        self.assertNotIn("seni soymaya", self.note(boy))
        self.assertIn("seni soymaya", self.note(master))

    async def test_a_fire_nobody_saw_lit_is_seen_and_talked_of_across_town(self):
        await self.town()
        self.add_person("Kalila", "Usta", location=self.city)
        far = self.add_person("Tariq", "Rahip", location="post")
        self.walk_to("shop")
        with self.binding(), patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            bold_acts._burn(self.session)
        self.assertEqual(self.deed()["witnesses"], [])
        self.walk_to(self.city)
        await self.wait("bir gün bekliyorum")
        self.assertIn("found_at", self.deed())
        self.assertIn("ateş", self.note(far))

    def promised_job(self, owner, status):
        thread = {"thread_id": "t1", "accepted_at": 0, "offered_at": None, "quest_id": None}
        with patch.object(world_threads, "by_id", return_value=thread), \
                patch.object(world_threads, "owner_of", return_value=owner):
            world_threads._apply_effects(self.world, [("t1", status)])

    async def test_a_job_left_undone_is_remembered_and_passed_on(self):
        await self.town()
        master = self.add_person("Kalila", "Usta", location="shop")
        boy = self.add_person("Baern", "Çırak", location="shop")
        self.promised_job(master, "failed")
        self.assertEqual(self.deed()["kind"], "broken_promise")
        self.assertIn("yarım bıraktı", self.note(master))
        await self.wait("bir saat bekliyorum")
        self.assertIn("yarım bıraktı", self.note(boy))
        self.assertIn("yüzünü", " ".join(bold_acts.place_marks(self.world, "shop")))

    async def test_a_job_lost_to_its_owners_death_is_no_broken_promise(self):
        await self.town()
        master = self.add_person("Kalila", "Usta", location="shop", combat_status="dead")
        self.promised_job(master, "expired")
        self.assertEqual(self.world["flags"].get("deeds", []), [])

    async def test_an_offer_never_taken_breaks_no_promise(self):
        await self.town()
        master = self.add_person("Kalila", "Usta", location="shop")
        thread = {"thread_id": "t1", "accepted_at": None, "offered_at": None, "quest_id": None}
        with patch.object(world_threads, "by_id", return_value=thread), \
                patch.object(world_threads, "owner_of", return_value=master):
            world_threads._apply_effects(self.world, [("t1", "expired")])
        self.assertEqual(self.world["flags"].get("deeds", []), [])

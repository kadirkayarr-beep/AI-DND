"""Play fixes of 2026-11-24 (six issues); every class pins the town (seed 4401: barracks, market, workshop, harbor, smithy)."""
import copy

from api.tests.test_arrival_wiring import _ArrivalApi

CITY = "fr:city:neverwinter"


class _Town(_ArrivalApi):
    TOWN_SEED = 4401

    def narration(self, reply):
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()["narration"]


class InnAgain(_Town):
    async def into_the_inn(self):
        world = self.session().world_state
        await self.turn("Köydeki tavernaya gidiyorum.", front={"kind": "go_to", "place_id": "kind:tavern"})
        inn = world["location"]
        self.assertNotEqual(inn, CITY)
        return inn

    async def test_a_walk_to_the_inn_in_the_inn_says_so(self):
        inn = await self.into_the_inn()
        world = self.session().world_state
        name = world["locations"][inn]["name"]
        reply = await self.turn("Hana gidiyorum.", front={"kind": "go_to", "place_id": "none"})
        text = self.narration(reply)
        self.assertIn(f"Zaten {name} içindesin.", text)
        self.assertEqual(world["location"], inn)

    async def test_the_list_of_known_places_keeps_every_place(self):
        world = self.session().world_state
        import grounded_places
        places = grounded_places._town_places(world)
        self.assertGreater(len(places), 4)
        text = grounded_places.known_places_question(self.session(), "Şuraya gidiyorum.")
        for rec in places.values():
            self.assertIn(rec["name"], text)


class DirectionsNotRumour(_Town):
    def present_person(self):
        world = self.session().world_state
        world["npcs"].append({"id": "npc_walker", "name": "Hadrik", "public_name": "Hadrik", "role": "Nöbetçi çavuş",
                              "reality_layer": "PROCEDURAL_LOCAL_FICTION", "relationship": "neutral",
                              "knowledge": [], "combat_status": "active", "current_hp": 12, "status": "active",
                              "memory": [], "location": world["location"]})

    def workshop(self):
        world = self.session().world_state
        return next(key for key, rec in world["locations"].items() if isinstance(rec, dict)
                    and rec.get("place_kind") == "workshop" and rec.get("parent_location_id") == CITY)

    async def test_a_rejected_speech_to_a_directions_question_answers_about_the_place_not_a_lead(self):
        self.present_person()
        shop = self.workshop()
        name = self.session().world_state["locations"][shop]["name"]
        reply = await self.turn("Hadrik, Çömlekçi'ye nasıl giderim?", spoken="Sen atölyeye girdin ve korktun.",
                                front={"kind": "go_to", "place_id": shop})
        text = self.narration(reply)
        self.assertIn(name, text)
        self.assertEqual(self.session().world_state["location"], CITY)

    async def test_the_safety_check_lets_a_person_say_you_will_understand(self):
        self.present_person()
        shop = self.workshop()
        reply = await self.turn("Hadrik, Çömlekçi'ye nasıl giderim?", spoken="Şu sokağın sonunda, görünce anlarsın.",
                                front={"kind": "go_to", "place_id": shop})
        self.assertIn("anlarsın", self.narration(reply))

    async def test_asking_the_way_to_the_place_you_stand_in_says_so(self):
        world = self.session().world_state
        await self.turn("Köydeki tavernaya gidiyorum.", front={"kind": "go_to", "place_id": "kind:tavern"})
        inn = world["location"]
        reply = await self.turn("Hana nasıl giderim?", front={"kind": "go_to", "place_id": inn})
        self.assertIn(f"Zaten {world['locations'][inn]['name']} içindesin.", self.narration(reply))


class FollowMessenger(_Town):
    def people(self):
        world = self.session().world_state
        for npc_id, name, role in (("npc_hadrik", "Hadrik", "Nöbetçi çavuş"), ("npc_haber", "Orlan", "Haberci")):
            world["npcs"].append({"id": npc_id, "name": name, "public_name": name, "role": role,
                                  "name_known_to_player": True, "role_known_to_player": True,
                                  "reality_layer": "PROCEDURAL_LOCAL_FICTION", "relationship": "neutral",
                                  "knowledge": [], "combat_status": "active", "current_hp": 12, "status": "active",
                                  "memory": [], "location": world["location"]})

    async def test_a_listed_person_the_line_never_names_is_not_followed(self):
        self.people()
        reply = await self.turn("Habercinin peşinden gidiyorum.",
                                front={"kind": "go_to", "place_id": "none", "person_id": "npc_hadrik"})
        text = self.narration(reply)
        self.assertNotIn("Hadrik", text)

    async def test_a_listed_person_the_line_names_is_followed(self):
        self.people()
        reply = await self.turn("Hadrik'in peşinden gidiyorum.",
                                front={"kind": "go_to", "place_id": "none", "person_id": "npc_hadrik"})
        self.assertIn("Hadrik", self.narration(reply))

    async def test_a_place_said_many_turns_ago_is_not_what_oraya_means(self):
        import npc_statements
        world = self.session().world_state
        place = next(key for key, rec in world["locations"].items() if isinstance(rec, dict)
                     and rec.get("place_kind") == "workshop" and rec.get("parent_location_id") == CITY)
        npc_statements.overheard_place(world, place, world["locations"][place]["name"])
        world.setdefault("flags", {})["turn_index"] = 6
        reply = await self.turn("Oraya gidiyorum.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(world["location"], CITY)

    async def test_a_place_said_in_the_line_before_is_what_oraya_means(self):
        import npc_statements
        world = self.session().world_state
        place = next(key for key, rec in world["locations"].items() if isinstance(rec, dict)
                     and rec.get("place_kind") == "workshop" and rec.get("parent_location_id") == CITY)
        npc_statements.overheard_place(world, place, world["locations"][place]["name"])
        world.setdefault("flags", {})["turn_index"] = 1
        reply = await self.turn("Oraya gidiyorum.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(world["location"], place)


class TextPurchase(_Town):
    def counter(self):
        world = self.session().world_state
        world["npcs"] = [{"id": "barman", "name": "Marek", "role": "Barmen", "location": world["location"],
                          "current_hp": 10}]
        world["currency"] = {"player": 100, "barman": 0}
        return world

    @staticmethod
    def beers(world):
        return [item for item in world["inventory"] if isinstance(item, dict) and item.get("name") == "Bira"]

    async def open_offer(self, line="Marek, bira alıyorum."):
        world = self.counter()
        reply = await self.turn(line)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual((world["flags"].get("counter_offer_v1") or {}).get("key"), "bira")
        self.assertEqual(world["currency"]["player"], 100)
        return world

    async def test_one_after_an_open_offer_is_a_sale_exactly_once(self):
        world = await self.open_offer()
        reply = await self.turn("Bir tane alıyorum.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(world["currency"]["player"], 96)
        self.assertEqual(world["currency"]["barman"], 4)
        self.assertEqual(len(self.beers(world)), 1)
        self.assertIn("4 bakır", reply.json()["narration"])
        again = await self.turn("Bir tane alıyorum.")  # the offer is settled: the same words buy nothing more
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(world["currency"]["player"], 96)
        self.assertEqual(len(self.beers(world)), 1)

    async def test_undo_gives_back_the_coin_and_the_beer(self):
        world = await self.open_offer()
        before = copy.deepcopy({"wares": world["npcs"][0].get("wares_v1"), "trades": world.get("shop_trades_v1")})
        reply = await self.turn("Bir tane alıyorum.")
        self.assertEqual(len(self.beers(world)), 1)
        self.assertNotEqual(world.get("shop_trades_v1"), before["trades"])
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(__import__("uuid").uuid4()),
                                            "target_action_id": reply.json()["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text)
        world = self.session().world_state
        self.assertEqual(world["currency"], {"player": 100, "barman": 0})
        self.assertEqual(self.beers(world), [])
        self.assertEqual(world["npcs"][0].get("wares_v1"), before["wares"])
        self.assertEqual(world.get("shop_trades_v1"), before["trades"])

    async def test_no_open_offer_no_sale(self):
        world = self.counter()
        reply = await self.turn("Bir tane alıyorum.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(world["currency"]["player"], 100)
        self.assertEqual(self.beers(world), [])

    async def test_another_item_named_is_no_sale_of_the_offered_one(self):
        world = await self.open_offer()
        reply = await self.turn("Bir tane şarap alıyorum.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(world["currency"]["player"], 100)
        self.assertEqual(self.beers(world), [])

    async def test_a_coin_amount_in_the_line_is_not_read_as_a_bare_count(self):
        world = await self.open_offer()
        reply = await self.turn("Bir tane alıyorum, al 10 bakır.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(world["currency"]["player"], 100)
        self.assertEqual(self.beers(world), [])


class TheRollIsShown(__import__("unittest").TestCase):
    def test_only_the_roll_note_is_taken_out_for_the_safety_check(self):
        import weapon_attack
        text = "Haydut ölür. Zar 20, toplam 25; hedefin Zırh Sınıfı 10. +10 deneyim puanı."
        self.assertEqual(weapon_attack.without_roll_note(text), "Haydut ölür. +10 deneyim puanı.")
        loose = "Zar 20 atarsın, toplam 25."
        self.assertEqual(weapon_attack.without_roll_note(loose), loose)

    def test_the_player_attack_tells_its_roll_total_and_target_ac(self):
        from unittest.mock import patch
        import action_economy as ae
        from api.tests.test_combat_lifecycle import ready
        session, npc = ready()
        with patch("game.roll_d20", return_value=7), patch("game.roll_damage", return_value=3), \
             patch("game.ollama.chat", side_effect=AssertionError("no model")):
            result = ae.execute(session, {"steps": [{"kind": "attack", "target_id": npc["id"]}]})
        resolved = result["action_result"]["economy_steps"][0]["result"]
        self.assertIsNotNone(resolved["attack_total"])
        note = f"Zar {resolved['attack_roll']}, toplam {resolved['attack_total']}; hedefin Zırh Sınıfı {resolved['target_ac']}."
        self.assertIn(note, result["narration"])
        self.assertEqual(result["narration"], session._combat_narration(resolved))

    def test_a_result_without_a_roll_tells_none(self):
        import game
        self.assertEqual(game._combat_narration({"outcome": "miss"}), "Saldırın hedefi ıskalar.")

    def test_the_enemy_attack_tells_its_roll_total_and_your_ac(self):
        import game
        text = game._enemy_exchange_text([{"actor": "x", "outcome": "miss", "attack_roll": 9, "attack_total": 13,
                                           "target_ac": 15}])
        self.assertIn("seni ıskalar. Zar 9, toplam 13; senin Zırh Sınıfın 15.", text)
        text = game._enemy_exchange_text([{"actor": "x", "outcome": "hit", "damage": 4, "attack_roll": 14,
                                           "attack_total": 18, "target_ac": 15}])
        self.assertIn("4 hasar alırsın. Zar 14, toplam 18; senin Zırh Sınıfın 15.", text)

    def test_the_enemy_result_the_engine_makes_carries_the_roll(self):
        from unittest.mock import patch
        import action_economy as ae
        from api.tests.test_combat_lifecycle import ready
        session, npc = ready()
        with patch("game.roll_d20", return_value=3), patch("game.roll_damage", return_value=3), \
             patch("game.ollama.chat", side_effect=AssertionError("no model")):
            result = ae.execute(session, {"steps": [{"kind": "attack", "target_id": npc["id"]}, {"kind": "end_turn"}]})
        enemies = [e for step in result["action_result"]["economy_steps"] for e in step.get("result", step).get("enemy_actions", [])
                   if e.get("outcome") in ("hit", "miss", "critical_hit")]
        self.assertTrue(enemies, "the fixture's rival counter-attacks")
        for enemy in enemies:
            self.assertIn(f"Zar {enemy['attack_roll']}, toplam {enemy['attack_total']}; senin Zırh Sınıfın {enemy['target_ac']}.",
                          result["narration"])


from api.tests.test_economic_room import Counter as _Counter


class AskWaresOfANonServer(_Counter):
    def test_a_room_reading_on_someone_who_does_not_serve_goes_on_to_speech(self):
        self.w['npcs'].append({'id': 'walker', 'name': 'Rolan', 'role': 'Yolcu', 'location': self.here, 'current_hp': 10})
        for purpose in ('room_quote', 'room'):
            with self.subTest(purpose=purpose):
                before, turn = self.money(), self.w['flags']['turn_index']
                result = self.s._front_economic_offer(
                    {'kind': 'economic', 'id': 'walker', 'purpose': purpose, 'valid': True}, 'Neler satıyorsun?')
                self.assertIsNone(result)
                self.assertEqual(self.prepared(), [])
                self.assertEqual(self.money(), before)
                self.assertEqual(self.w['flags']['turn_index'], turn)


class ReviewOneFixes(TextPurchase, FollowMessenger):
    people = FollowMessenger.people
    async def test_a_different_thing_named_is_no_sale_of_the_offered_beer(self):
        for line in ("Bir tane kılıç alıyorum.", "Bir tane oda alıyorum.", "Bir tane hançer alıyorum."):
            world = await self.open_offer()
            reply = await self.turn(line)
            self.assertEqual(reply.status_code, 200, reply.text)
            self.assertEqual(world["currency"]["player"], 100, line)
            self.assertEqual(self.beers(world), [], line)
            world["flags"].pop("counter_offer_v1", None)

    async def test_a_price_other_than_the_one_shown_is_no_sale(self):
        world = await self.open_offer()
        world["flags"]["counter_offer_v1"]["unit_cp"] = 3
        await self.turn("Bir tane alıyorum.")
        self.assertEqual(world["currency"]["player"], 100)
        self.assertEqual(self.beers(world), [])

    async def test_a_place_said_long_ago_and_an_old_last_place_do_not_move_the_player(self):
        import grounded_action
        import npc_statements
        world = self.session().world_state
        places = [key for key, rec in world["locations"].items() if isinstance(rec, dict)
                  and rec.get("parent_location_id") == CITY and not rec.get("hidden")]
        said, other = places[0], places[1]
        npc_statements.overheard_place(world, said, world["locations"][said]["name"])
        grounded_action.note_last(world, other)
        world.setdefault("flags", {})["turn_index"] = 4
        reply = await self.turn("Oraya gidiyorum.")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(world["location"], CITY)

    async def test_the_role_word_in_any_case_follows_the_messenger(self):
        self.people()
        reply = await self.turn("Habercinin peşinden gidiyorum.",
                                front={"kind": "go_to", "place_id": "none", "person_id": "npc_haber"})
        self.assertIn("Orlan", self.narration(reply))

    def test_the_spoken_mask_covers_the_back_vowel_forms(self):
        import npc_speech_boundary
        text = 'Marek: "Orayı görürsün, anlarsın."'
        masked = npc_speech_boundary.mask_spoken_questions(text, 0)
        self.assertNotIn("görürsün", masked)
        self.assertNotIn("anlarsın", masked)

    def test_the_spoken_mask_leaves_walks_and_feelings_told_to_the_player(self):
        import npc_speech_boundary
        for claim in ("Sonra hana girersin.", "Korkmuş hissedersin.", "Tavernaya doğru yürürsün.", "Dışarı çıkarsın."):
            text = f'Neris: "{claim}"'
            self.assertEqual(npc_speech_boundary.mask_spoken_questions(text, 0), text)

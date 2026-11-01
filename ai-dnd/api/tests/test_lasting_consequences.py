"""What the player did stays done: real play lines from the long Carius check.

Each test posts the player's own Turkish through the HTTP turn with a mocked
model, so it proves what Python decides on its own.
"""

import game
from api.tests.test_three_plays import FIGHTER, PlayClient, ThreePlaysTests


class OwnWordsAndConfessions(ThreePlaysTests):
    async def scene(self, *people):
        await self.begin(FIGHTER)
        self.session._experimental_npc_dialogue_enabled = True  # as api.local_play runs it
        self.world["npcs"].clear()
        return [self.add_person(name, role) for name, role in people]

    def test_saying_it_again_is_not_a_claim_about_their_words(self):
        for line in ("paket bende mi şimdi çantama koyuyorum. tariq nerde dedim sana",
                     "ee kalila kol gücü lazım mı dedim, altın kazanacak iş var mı sende",
                     "iş var mı diyorum sana"):
            self.assertFalse(game.is_npc_historical_claim(line), line)

    def test_what_they_said_still_counts_as_a_claim(self):
        for line in ("sen bana dokuz bakır dedin", "bana söz verdin", "kalila öyle dedi", "adımı söyledim sana"):
            self.assertTrue(game.is_npc_historical_claim(line), line)

    async def test_a_repeated_question_gets_an_answer_not_a_denial(self):
        await self.scene(("Kalila", "Usta"))
        client = PlayClient(spoken="Sabret biraz, işim bitsin de söyleyeyim.")
        await self.say("selam kalila, iş var mı", client)
        out = await self.say("paket bende mi şimdi çantama koyuyorum. tariq nerde dedim sana", client)
        self.assertIn("Sabret biraz", out["narration"])
        self.assertNotEqual(out["turn_outcome"]["status"], "unverified")

    async def test_a_past_killing_said_to_someone_else_is_speech_not_an_attack(self):
        await self.scene(("Isolde", "Nöbetçi Çavuş"))
        self.world["npcs"].append(dict(self.world["npcs"][0], id="npc_kalila", name="Kalila", role="Usta",
                                       combat_status="dead", location="elsewhere"))
        client = PlayClient(spoken="Ne dedin sen?")
        out = await self.say(
            "peki şunu söyleyim o zaman: quenna atölyesindeki kalilayı ben öldürdüm, atölyeyi de ben yaktım. ne yapacaksın",
            client)
        self.assertNotEqual(out["turn_outcome"]["status"], "clarification", out["narration"])
        self.assertNotIn("Kime saldırıyorsun", out["narration"])

    async def test_a_past_blow_at_the_person_here_stays_an_attack(self):
        await self.scene(("Isolde", "Nöbetçi Çavuş"))
        with self.app.state.ollama_adapter.engine_binding():
            import combat_lifecycle
            self.assertTrue(combat_lifecycle.is_attack_decision(self.session, "isoldeye vurdum"))
            self.assertTrue(combat_lifecycle.is_attack_decision(self.session, "çavuşa saldırıyorum"))
            self.assertFalse(combat_lifecycle.is_attack_decision(self.session, "adamı dün gece ben öldürdüm"))


class WaitingPassesTime(ThreePlaysTests):
    def elapsed(self):
        return self.world["campaign_time"]["elapsed_seconds"]

    async def test_a_wait_with_a_length_passes_that_time_even_with_more_said(self):
        await self.begin(FIGHTER)
        before = self.elapsed()
        out = await self.say("bir duvarın dibine oturup yarım saat kadar bekliyorum, atölyeye ne oluyor izliyorum")
        self.assertEqual(self.elapsed() - before, 1800, out["narration"])
        self.assertIn("Yarım saat", out["narration"])

    async def test_a_bare_wait_passes_a_little_time_instead_of_asking_how_long(self):
        for line in ("bekliyorum", "biraz bekliyorum", "bir süre bekliyorum"):
            with self.subTest(line=line):
                await self.begin(FIGHTER)
                before = self.elapsed()
                out = await self.say(line)
                self.assertGreater(self.elapsed(), before, out["narration"])
                self.assertNotIn("Kaç dakika", out["narration"])

    async def test_waiting_until_evening_reaches_evening(self):
        await self.begin(FIGHTER)
        self.world["campaign_time"]["start_second"] = 10 * 3600
        await self.say("akşama kadar burada bekliyorum")
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], 8 * 3600)

    async def test_in_a_fight_waiting_still_ends_the_turn(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.add_person("Dorn", "Muhafız", current_hp=300, max_hp=300)
        await self.say("muhafıza saldırıyorum", PlayClient(intent="attack"))
        self.assertTrue(self.world["combat"]["active"])
        before = self.elapsed()
        out = await self.say("bekliyorum")
        self.assertEqual(out["turn_outcome"]["action"], "action_economy", out["narration"])
        self.assertLess(self.elapsed() - before, 60)


class OneTownScene(ThreePlaysTests):
    async def town(self):
        await self.begin(FIGHTER)
        self.session._experimental_npc_dialogue_enabled = True
        self.world["npcs"].clear()
        self.city = self.world["location"]
        self.world["locations"]["shop"] = {
            "id": "shop", "name": "Quenna Atölyesi", "description": "Talaş kokulu bir atölye.",
            "parent_location_id": self.city, "exit_location_id": self.city, "scene_type": "building",
        }
        self.world["locations"]["post"] = {
            "id": "post", "name": "Brissa Karakolu", "description": "Sert ışıklı bir karakol.",
            "parent_location_id": self.city, "exit_location_id": self.city, "scene_type": "building",
        }

    def binding(self):
        return self.app.state.ollama_adapter.engine_binding()

    def note(self, npc):
        import bold_acts
        return bold_acts.speech_note(self.world, npc)

    def killed_earlier(self, witness=None):
        """Kalila lies dead in her shop, seen by whoever is given."""
        kalila = self.add_person("Kalila", "Usta", location="shop", combat_status="dead", current_hp=0)
        self.world["flags"]["deeds"] = [{
            "kind": "killing", "text": "Kalila öldürüldü", "location": "shop", "victim_id": kalila["id"],
            "witnesses": [witness] if witness else [], "turn": 3, "at": 0, "heard": [], "told": [],
        }]
        return kalila

    async def wait(self, line):
        return await self.say(line, PlayClient())


class ConfessionsAndGuards(OneTownScene):
    async def test_a_confession_to_a_guard_makes_him_draw(self):
        for line in ("peki şunu söyleyim o zaman: quenna atölyesindeki kalilayı ben öldürdüm. ne yapacaksın",
                     "çavuşa diyorum ki kalila adlı ustanın katili benim"):
            with self.subTest(line=line):
                await self.town()
                guard = self.add_person("Isolde", "Nöbetçi Çavuş")
                self.killed_earlier()
                out = await self.say(line, PlayClient(spoken="Ne dedin sen?"))
                self.assertTrue(self.world["combat"]["active"], out["narration"])
                self.assertIn(guard["id"], self.world["combat"]["participants"])
                self.assertIn("katil", out["narration"])
                self.assertIn("Kalila öldürüldü", self.note(guard))

    async def test_telling_a_barman_is_remembered_without_a_fight(self):
        await self.town()
        barman = self.add_person("Veyra", "Barmen")
        self.killed_earlier()
        await self.say("kalilayı ben öldürdüm veyra", PlayClient(spoken="Duymamış olayım."))
        self.assertFalse(self.world["combat"]["active"])
        self.assertIn("kendi ağzıyla", self.note(barman))
        self.assertIn("Kalila öldürüldü", self.note(barman))

    async def test_a_boast_about_nothing_is_kept_as_words_only(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş")
        await self.say("ben bu şehirde üç kişiyi öldürdüm", PlayClient(spoken="Öyle mi?"))
        self.assertFalse(self.world["combat"]["active"])
        self.assertIn("üç kişiyi", self.note(guard))
        self.assertNotIn("Kalila", self.note(guard))

    async def test_a_guard_who_was_told_draws_when_the_player_comes_back(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş")
        self.killed_earlier()
        self.world["flags"]["deeds"][0]["told"] = [guard["id"]]
        out = await self.say("etrafa bakıyorum", PlayClient())
        self.assertTrue(self.world["combat"]["active"], out["narration"])

    async def test_someone_who_was_only_swung_at_remembers_it_without_drawing_by_himself(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş")
        await self.say("kılıcımı çekip çavuşa saldırıyorum", PlayClient(intent="attack"))
        self.assertIn("üzerine yürüdü", self.note(guard))
        self.assertEqual(self.world["flags"]["deeds"][0]["kind"], "assault")


class NewsTravelsByRealRoutes(OneTownScene):
    async def test_nobody_saw_it_and_nobody_was_told_so_nobody_knows(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        self.killed_earlier()
        await self.wait("iki saat bekliyorum")
        self.assertNotIn("Kalila", self.note(guard))

    async def test_a_witness_reaches_the_guard_after_an_hour_and_not_before(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş", location="post")
        boy = self.add_person("Baern", "Çırak", location=self.city)
        self.killed_earlier(boy["id"])
        await self.wait("yarım saat bekliyorum")
        self.assertNotIn("Kalila", self.note(guard))
        await self.wait("bir saat bekliyorum")
        self.assertIn("Kalila öldürüldü", self.note(guard))

    async def test_what_was_heard_does_not_point_at_the_player(self):
        await self.town()
        guard = self.add_person("Isolde", "Nöbetçi Çavuş", location=self.city)
        boy = self.add_person("Baern", "Çırak", location=self.city)
        self.killed_earlier(boy["id"])
        await self.wait("iki saat bekliyorum")
        self.assertFalse(self.world["combat"]["active"])
        self.assertIn("Kalila öldürüldü", self.note(guard))
        self.assertNotIn("gözünle gördün", self.note(guard))

    async def test_someone_standing_with_a_witness_hears_it_there(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak", location=self.city)
        girl = self.add_person("Ilyra", "Satıcı", location=self.city)
        far = self.add_person("Tariq", "Rahip", location="post")
        self.killed_earlier(boy["id"])
        await self.wait("yarım saat bekliyorum")
        self.assertIn("Kalila öldürüldü", self.note(girl))
        self.assertNotIn("Kalila", self.note(far))


class FireGoesOnByTheClock(OneTownScene):
    def fire_feature(self, location="shop"):
        return [f["name"] for f in self.world.get("features", []) if f.get("location") == location]

    def light(self):
        import bold_acts
        from unittest.mock import patch
        with self.binding(), patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            bold_acts._burn(self.session)

    async def test_a_fire_spreads_clears_the_room_and_burns_the_place_out(self):
        await self.town()
        self.world["location"] = "shop"
        master = self.add_person("Kalila", "Usta", location="shop")
        street = self.add_person("Baern", "Çırak", location=self.city)
        self.light()
        self.assertIn("Tüten ateş", self.fire_feature())
        self.assertIn("duman", self.note(street))
        self.world["location"] = self.city
        out = await self.wait("yarım saat bekliyorum")
        self.assertIn("Yayılan yangın", self.fire_feature())
        self.assertEqual(master["location"], self.city)
        self.assertIn("Quenna Atölyesi", out["narration"])
        self.assertIn("duman", self.world["locations"]["shop"]["description"])
        await self.wait("bir saat bekliyorum")
        self.assertIn("Yanmış kalıntılar", self.fire_feature())
        self.assertNotIn("Talaş", self.world["locations"]["shop"]["description"])
        self.assertIn("kül", self.note(self.add_person("Dorn", "Muhafız", location="post")))

    async def test_a_fire_in_the_open_dies_down_and_leaves_the_city_alone(self):
        await self.town()
        before = self.world["locations"][self.city].get("description")
        self.light()
        await self.wait("iki saat bekliyorum")
        self.assertEqual(self.world["locations"][self.city].get("description"), before)
        self.assertIn("Sönmüş ateş", self.fire_feature(self.city))


class ATheftIsMissedLater(OneTownScene):
    async def test_the_robbed_notice_later_and_do_not_know_who(self):
        await self.town()
        master = self.add_person("Kalila", "Usta")
        import bold_acts
        from unittest.mock import patch
        with self.binding(), patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            bold_acts._steal(self.session, "kalilanın kesesini çalıyorum")
        self.assertNotIn("kesen", self.note(master))
        await self.wait("yarım saat bekliyorum")
        self.assertIn("kesen", self.note(master))
        self.assertIn("kimin aldığını bilmiyorsun", self.note(master))


class ThePlaceShowsWhatHappened(OneTownScene):
    async def workshop(self):
        await self.town()
        import local_places
        self.place = local_places.create_local_place(self.world, self.city, "workshop")
        self.world["location"] = self.place["id"]
        self.master = self.add_person("Kalila", "Usta", location=self.place["id"])

    def arrive(self):
        import local_places
        return local_places.arrival_text(self.world, self.place, self.master, None, first_visit=False)

    def later(self, seconds):
        self.world["campaign_time"]["elapsed_seconds"] += seconds

    async def test_back_at_once_nothing_has_changed(self):
        await self.workshop()
        self.place["visited"] = True
        self.arrive()
        self.later(60)
        self.assertIn("bıraktığın gibi", self.arrive())

    async def test_the_next_morning_it_is_not_the_same_sentence(self):
        await self.workshop()
        self.place["visited"] = True
        evening = self.arrive()
        self.later(14 * 3600)
        morning = self.arrive()
        self.assertNotIn("bıraktığın gibi", morning)
        self.assertNotEqual(evening, morning)

    async def test_people_are_not_always_doing_the_same_thing(self):
        await self.workshop()
        self.place["visited"] = True
        seen = set()
        for _ in range(6):
            self.later(24 * 3600)
            seen.add(self.arrive())
        self.assertGreater(len(seen), 1)

    async def test_the_robbed_person_is_seen_missing_it_once(self):
        await self.workshop()
        self.place["visited"] = True
        self.world["flags"]["deeds"] = [{"kind": "theft_unseen", "text": "Kalila soyuldu", "victim_id": self.master["id"],
                                         "at": 0, "witnesses": [], "heard": [], "told": []}]
        self.arrive()
        self.later(3600)
        self.assertIn("kesesini yokluyor", self.arrive())
        self.assertNotIn("kesesini yokluyor", self.arrive())

    async def test_a_burnt_place_reads_burnt_and_nobody_works_there(self):
        await self.workshop()
        self.place["visited"] = True
        import bold_acts
        from unittest.mock import patch
        with self.binding(), patch.object(bold_acts, "_check", return_value={"result": "BAŞARILI"}):
            bold_acts._burn(self.session)
        await self.wait("iki saat bekliyorum")
        text = self.arrive()
        self.assertIn("Kararmış", text)
        self.assertNotIn("burada.", text)
        self.assertNotIn("bıraktığın gibi", text)


class TheLedger(OneTownScene):
    def project(self, journal=None):
        import campaign_ledger
        return campaign_ledger.project(self.world, journal or {})

    async def test_it_holds_what_the_player_did_and_said_and_nothing_private(self):
        await self.town()
        boy = self.add_person("Baern", "Çırak")
        self.killed_earlier(boy["id"])
        self.world["flags"]["deeds"][0]["told"] = [boy["id"]]
        self.world.setdefault("relationships", {})[boy["id"]] = {"score": -99}
        self.world["quests"] = [{"quest_id": "q", "title": "SIR GOREV", "status": "AVAILABLE"}]
        ledger = self.project({"quests": [
            {"title": "Paket işi", "status": "COMPLETED"}, {"title": "SIR GOREV", "status": "AVAILABLE"},
        ]})
        text = str(ledger)
        self.assertIn("Kalila öldürüldü (Quenna Atölyesi)", text)
        self.assertIn("Kendi ağzınla söyledin", text)
        self.assertIn("Paket işi: COMPLETED", text)
        for secret in ("SIR GOREV", boy["id"], "-99", "witnesses"):
            self.assertNotIn(secret, text)

    async def test_it_stays_small_and_the_same_for_the_same_world(self):
        await self.town()
        self.killed_earlier()
        journal = {"known_npcs": [{"name": f"Kişi {i}", "role": "Satıcı " * 8} for i in range(30)],
                   "discovered_locations": [{"name": f"Yer {i} " * 8} for i in range(30)]}
        import json
        first = self.project(journal)
        self.assertLessEqual(len(json.dumps(first, ensure_ascii=False).encode("utf-8")), 900)
        self.assertEqual(first, self.project(journal))
        self.assertIn("did", first)

    async def test_the_narrator_is_given_the_ledger(self):
        await self.town()
        self.killed_earlier()
        prompts = []

        class Listening(PlayClient):
            def chat(self, *args, **kwargs):
                prompts.append(str(kwargs.get("messages") or args))
                return super().chat(*args, **kwargs)

        out = await self.say("boğazından tutup duvara yapıştırıyorum, paraları çıkar diyorum", Listening())
        self.assertTrue(any("Kalila öldürüldü" in prompt for prompt in prompts), (len(prompts), out["narration"], out["turn_outcome"]))

    def test_the_ledger_is_the_last_thing_cut_from_the_packet(self):
        from api import narrative_memory
        packet = {"canonical": {}, "action_result": {}, "relevant_continuity": {
            "recent_turns": [{"player": "x" * 3000}], "unresolved_threads": ["y" * 3000],
            "ledger": {"did": ["Kalila öldürüldü"]},
        }}
        fitted, _ = narrative_memory._fit_context_packet(packet)
        self.assertEqual(fitted["relevant_continuity"]["ledger"], {"did": ["Kalila öldürüldü"]})

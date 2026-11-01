"""What three real plays broke, replayed with the players' own Turkish lines.

Each test posts through the HTTP API, because the plays failed there: a raw
400 or 500 is a lost turn no matter how the engine got to it.
"""

import json
import unittest
import uuid

import barbarian_rage
import local_places
import npc_statements
import weapon_catalog
from api.tests import test_campaign_api

START = {
    "setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter",
}
ROGUE = {
    "mode": "custom", "starting_level": 1, "name": "Fesat", "race": "Human", "species": "Human",
    "class": "Rogue", "background": "Criminal", "alignment": "Chaotic Neutral",
    "ability_score_method": "standard_array",
    "ability_scores": {"strength": 8, "dexterity": 15, "constitution": 13,
                       "intelligence": 12, "wisdom": 10, "charisma": 14},
    "background_ability_bonuses": {"dexterity": 2, "intelligence": 1},
    "proficient_skills": ["Sleight of Hand", "Stealth", "Deception", "Acrobatics",
                          "Persuasion", "Insight", "Perception"],
    "expertise_skills": ["Stealth", "Deception"], "species_bonus_skills": ["Perception"],
    "species_bonus_feat": "Savage Attacker", "equipment_package": "A",
    "background_equipment_option": "A", "languages": ["Goblin", "Dwarvish"],
    "origin": "Luskan", "appearance": "Zayıf, çevik.", "personality": "Ne yapacağı belli olmaz.",
    "backstory": "Rıhtımlarda büyüdü.",
}
BARBARIAN = {
    "mode": "custom", "starting_level": 3,
    "level_choices": {"2": {}, "3": {"subclass_id": "berserker", "primal_knowledge_skill": "Intimidation"}},
    "name": "Borga", "race": "Human", "species": "Human", "class": "Barbarian",
    "background": "Criminal", "alignment": "Chaotic Neutral", "ability_score_method": "standard_array",
    "ability_scores": {"strength": 15, "dexterity": 13, "constitution": 14,
                       "intelligence": 8, "wisdom": 12, "charisma": 10},
    "background_ability_bonuses": {"dexterity": 1, "constitution": 2},
    "proficient_skills": ["Athletics", "Perception", "Persuasion", "Sleight of Hand", "Stealth"],
    "species_bonus_feat": "Tough", "species_bonus_skills": ["Persuasion"],
    "equipment_package": "A", "background_equipment_option": "A",
    "languages": ["Common", "Dwarvish", "Giant"], "origin": "Luskan",
    "appearance": "İri yarı.", "personality": "Kavgacı.", "backstory": "Meyhanelerde büyüdü.",
}
FIGHTER = {
    "mode": "custom", "starting_level": 3, "level_choices": {"2": {}, "3": {"subclass_id": "champion"}},
    "name": "Carius", "race": "Human", "species": "Human", "class": "Fighter",
    "background": "Soldier", "alignment": "Chaotic Neutral", "ability_score_method": "standard_array",
    "ability_scores": {"strength": 15, "dexterity": 13, "constitution": 14,
                       "intelligence": 12, "wisdom": 10, "charisma": 8},
    "background_ability_bonuses": {"strength": 2, "constitution": 1},
    "proficient_skills": ["Athletics", "Intimidation", "Perception", "Insight", "Persuasion"],
    "species_bonus_skills": ["Persuasion"], "species_bonus_feat": "Alert",
    "origin_feat": "Savage Attacker", "fighting_style": "Defense", "equipment_package": "A",
    "background_equipment_option": "A", "languages": ["Dwarvish", "Goblin"],
    "origin": "Baldur's Gate", "appearance": "Sırım gibi.", "personality": "Kurnaz.",
    "backstory": "Ordudan ayrıldı.",
}


class PlayClient(test_campaign_api.FakeOllamaClient):
    """Stands in for the model: a fixed intent, line of speech and narration."""

    def __init__(self, intent="unknown", spoken="Ne istiyorsun?", narration="Sokakta hayat akıyor."):
        self.intent = intent
        self.spoken = spoken
        self.narration = narration
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        schema = kwargs.get("format") or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if "spoken_text" in properties:
            packet = {"spoken_text": self.spoken, "stage_direction": ""}
        elif "intent" in properties:
            packet = {"intent": self.intent, "action": self.intent, "target": {
                "type": "none", "reference": "", "npc_id": "", "evidence_quote": "",
            }, "completion": "unclear", "confidence": 1.0}
        else:
            packet = {"narration": self.narration}
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class ThreePlaysTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_campaign_api.CampaignApiTests.asyncSetUp
    asyncTearDown = test_campaign_api.CampaignApiTests.asyncTearDown
    post_scene_turn = test_campaign_api.CampaignApiTests.post_scene_turn

    async def begin(self, character=None, death_mode=None):
        body = {"campaign_start": START}
        if character is not None:
            body["character"] = character
        if death_mode is not None:
            body["death_mode"] = death_mode
        created = await self.http.post("/api/game/campaigns", json=body)
        self.assertEqual(created.status_code, 200, created.text)
        self.session_id = created.json()["session_id"]
        self.session = self.manager.get(self.session_id).game_session
        self.world = self.session.world_state
        self.url = f"/api/game/sessions/{self.session_id}/turn"

    async def say(self, line, client=None, mode=None, expected=200):
        body = {"message": line, "action_id": str(uuid.uuid4())}
        if mode is not None:
            body["interaction_mode"] = mode
        response = await self.post_scene_turn(self.url, client or PlayClient(), body)
        self.assertEqual(response.status_code, expected, f"{line!r}: {response.text[:600]}")
        return response.json()

    def add_person(self, name, role, **extra):
        person = {
            "id": f"npc_{name.lower()}", "name": name, "role": role,
            "location": self.world["location"], "personality": "", "appearance": "",
            "relationship": "neutral", "knowledge": [], "memory": [], "combat_status": "active",
            "current_hp": 10, "max_hp": 10, "armor_class": 10, "status": "active",
        }
        person.update(extra)
        self.world["npcs"].append(person)
        return person


class StartingWeaponTests(ThreePlaysTests):
    def test_starting_gear_labels_are_weapons(self):
        self.assertEqual(weapon_catalog.lookup("Kısa Kılıç")["weapon_id"], "shortsword")
        self.assertEqual(weapon_catalog.lookup("2 Hançer")["weapon_id"], "dagger")
        self.assertEqual(weapon_catalog.lookup("Uzun Kılıç")["weapon_id"], "longsword")
        self.assertIsNone(weapon_catalog.lookup("2 Altın"))

    async def test_rogue_draws_starting_weapons_on_a_person(self):
        for line in ("sıkıldım. hançerimi çekip muhafıza saldırıyorum",
                     "kısa kılıcımı çekip muhafıza saldırıyorum"):
            with self.subTest(line=line):
                await self.begin(ROGUE)
                self.session.character.update(current_hp=200, max_hp=200)
                self.add_person("Dorn", "Muhafız", current_hp=300, max_hp=300)
                out = await self.say(line, PlayClient(intent="attack"))
                self.assertTrue(self.world["combat"]["active"], out["narration"])



class AttackWordsTests(ThreePlaysTests):
    async def test_natural_blows_start_the_fight(self):
        for line in ("çelimsize yumruk atıyorum", "yumruklıyorum herifi, suratına",
                     "çavuşun suratına yumruk atıyorum", "çavuşa saplıyorum hançeri"):
            with self.subTest(line=line):
                await self.begin(BARBARIAN)
                self.world["npcs"].clear()
                self.add_person("Dorn", "Nöbetçi çavuş", visible_trait="çelimsiz",
                                current_hp=300, max_hp=300)
                await self.say(line, PlayClient(intent="attack"))
                self.assertTrue(self.world["combat"]["active"], line)

    async def test_a_stranger_is_struck_by_what_shows_with_any_case_ending(self):
        for line, trait, role in (
            ("celimsize vuruyorum", "çelimsiz", None),
            ("çelimsiz olana saldırıyorum işte", "çelimsiz", None),
            ("çelimsiz biriye saldırıyorum", "çelimsiz", None),
            ("işçiye çıplak elle vuruyorum", "suratsız", "Liman işçisi"),
            ("kahverengi cüppeli birine baltayla saldırıyorum", "kahverengi cüppeli", None),
        ):
            with self.subTest(line=line):
                await self.begin(BARBARIAN)
                self.world["npcs"].clear()
                target = self.add_person("Tariq", role or "Kent sakini", visible_trait=trait,
                                         current_hp=300, max_hp=300)
                self.add_person("Ilyra", "Muhafız", visible_trait="gençten")
                out = await self.say(line, PlayClient(intent="attack"))
                self.assertTrue(self.world["combat"]["active"], out["narration"])
                self.assertIn(target["id"], self.world["combat"]["participants"])

    async def test_a_boast_is_not_a_fight_and_loses_no_turn(self):
        await self.begin(FIGHTER)
        self.add_person("Dorn", "Kâhya")
        line = ("kılıç sallarım, kaldırırım taşırım, gerekirse birinin kafasını kırarım. "
                "ağır iş varsa yaparım, altın verirsen")
        await self.say(line, PlayClient(intent="attack"))
        self.assertFalse(self.world["combat"]["active"])

    async def test_vursana_in_a_fight_means_the_one_you_are_fighting(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        self.add_person("Dorn", "Muhafız", current_hp=300, max_hp=300)
        await self.say("muhafıza saldırıyorum", PlayClient(intent="attack"))
        self.assertTrue(self.world["combat"]["active"])
        await self.say("hadi vursana", PlayClient(intent="attack"))


class FightBackTests(ThreePlaysTests):
    async def test_a_person_with_no_stat_block_hits_back(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        with self.app.state.ollama_adapter.engine_binding():
            person = self.session.create_npc_from_ai(
                {"name": "Tariq", "role": "Liman işçisi", "location": self.world["location"]})
        person.update(current_hp=500, max_hp=500, role_known_to_player=True)
        before = self.session.character["current_hp"]
        log = []
        for _ in range(12):
            out = await self.say("liman işçisine vuruyorum", PlayClient(intent="attack"))
            log.append(out["narration"])
            log.append(str(out.get("combat_result"))[:700])
        self.assertLess(self.session.character["current_hp"], before, log)

    async def test_an_armed_guard_is_harder_than_a_passer_by(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        guard = {"name": "A", "role": "Muhafız"}
        worker = {"name": "B", "role": "Kent sakini"}
        with self.app.state.ollama_adapter.engine_binding():
            self.session.ensure_npc_enemy_stats(guard)
            self.session.ensure_npc_enemy_stats(worker)
        self.assertGreater(guard["armor_class"], worker["armor_class"])
        self.assertGreater(guard["max_hp"], worker["max_hp"])
        self.assertGreater(guard["attack_bonus"], worker["attack_bonus"])


class StealingTests(ThreePlaysTests):
    LINES = (
        "yaşlı gezginin kesesine el atıyorum, çaktırmadan yürütcem",
        "bir elma çalıyorum",
        "adam başka tarafa bakarken tezgahtan bi elma yürütüyorum",
        "çavuş yazarken askıdan bi kalkan indirip pelerinimin altına saklıyorum",
        "içeri süzülüp nöbet defterini aşırıyorum",
        "muhafızın cebine el atıyorum",
        "muhafızın kemerindeki keseyi kesip alıyorum",
    )

    async def test_a_steal_rolls_sleight_of_hand_and_leaves_a_mark(self):
        for line in self.LINES:
            with self.subTest(line=line):
                await self.begin(ROGUE)
                self.world["npcs"].clear()
                self.add_person("Dorn", "Muhafız")
                before = (list(self.world["inventory"]), self.world.get("currency", {}).get("player", 0))
                out = await self.say(line, PlayClient())
                self.assertFalse(self.world["combat"]["active"])
                self.assertEqual(out["turn_outcome"]["action"], "theft", out["narration"])
                self.assertNotIn("Gizlenme", out["narration"])
                result = self.world["flags"].get("deeds")
                changed = (list(self.world["inventory"]), self.world.get("currency", {}).get("player", 0)) != before
                self.assertTrue(changed or result or "duraksıyorsun" in out["narration"], out["narration"])

    async def test_a_caught_thief_is_remembered_and_the_person_is_told(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        guard = self.add_person("Dorn", "Muhafız")
        with self.app.state.ollama_adapter.engine_binding():
            import bold_acts
            bold_acts.remember(self.session, "theft", "seni soymaya kalktı", victim_id=guard["id"])
            self.assertIn("soymaya kalktı", bold_acts.speech_note(self.world, guard))

    async def test_ringing_and_music_are_not_theft(self):
        await self.begin(ROGUE)
        with self.app.state.ollama_adapter.engine_binding():
            import bold_acts
            for line in ("zili çalıyorum", "kapıyı çalıyorum", "flüt çalıyorum"):
                self.assertFalse(bold_acts.is_theft(self.session, line), line)


class WorldAnswersTests(ThreePlaysTests):
    async def test_a_killing_in_front_of_a_guard_starts_his_fight(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        self.add_person("Tariq", "Kent sakini", visible_trait="çelimsiz", current_hp=1, max_hp=1, armor_class=1)
        self.add_person("Dorn", "Muhafız")
        await self.say("çelimsize baltayla saldırıyorum", PlayClient(intent="attack"))
        for _ in range(8):
            if self.world["npcs"][0]["combat_status"] == "dead":
                break
            await self.say("çelimsize vuruyorum", PlayClient(intent="attack"))
        self.assertEqual(self.world["npcs"][0]["combat_status"], "dead")
        self.assertTrue(self.world["combat"]["active"])
        self.assertIn(self.world["npcs"][1]["id"], self.world["combat"]["participants"])

    async def test_a_guard_elsewhere_knows_only_what_reached_him(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        guard = self.add_person("Dorn", "Muhafız", location="elsewhere")
        deed = {"kind": "killing", "text": "bir barmen öldürüldü", "witnesses": [], "heard": []}
        self.world["flags"]["deeds"] = [deed]
        with self.app.state.ollama_adapter.engine_binding():
            import bold_acts
            self.assertNotIn("barmen öldürüldü", bold_acts.speech_note(self.world, guard))
            deed["heard"].append(guard["id"])
            self.assertIn("barmen öldürüldü", bold_acts.speech_note(self.world, guard))

    async def test_ordering_a_beer_reaches_the_barman(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        self.add_person("Dorn", "Barmen")
        before = self.world.get("currency", {}).get("player", 0)
        out = await self.say("bira ver bana barmen, en sertinden olsun", PlayClient())
        self.assertIn("bira", out["narration"])
        self.assertEqual(self.world["currency"]["player"], before + 1600 - 4)  # the pack's 16 gold is counted in

    async def test_paying_from_a_pack_full_of_coin_labels(self):
        await self.begin(ROGUE)
        self.world["npcs"].clear()
        self.add_person("Dorn", "Barmen")
        await self.say("bir bira alayım", PlayClient())
        self.assertEqual(self.world["currency"]["player"], 2396)
        self.assertFalse([item for item in self.world["inventory"] if "Altın" in str(item)])

    async def test_a_body_can_be_searched_once(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        self.add_person("Tariq", "Kent sakini", current_hp=0, combat_status="dead")
        out = await self.say("adamın üstünü arıyorum, kesesi varsa alırım", PlayClient())
        self.assertEqual(out["turn_outcome"]["action"], "loot")

    async def test_an_answer_to_kime_finishes_the_attack(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        self.add_person("Tariq", "Kent sakini", visible_trait="çelimsiz", current_hp=300, max_hp=300)
        self.add_person("Ilyra", "Barmen", visible_trait="gençten")
        await self.say("saldırıyorum", PlayClient(intent="attack"))
        await self.say("çelimsiz biri", PlayClient(intent="attack"))
        self.assertTrue(self.world["combat"]["active"])

    async def test_going_inside_after_walking_up(self):
        await self.begin(FIGHTER)
        city = self.world["location"]
        forge = local_places.create_local_place(self.world, city, "smithy", name="Isolde Demirhanesi")
        await self.say("Isolde Demirhanesine yaklaşıyorum")
        await self.say("içeri giriyorum")
        self.assertEqual(self.world["location"], forge["id"])

    async def test_up_onto_an_altar_is_still_in_the_temple(self):
        await self.begin(ROGUE)
        city = self.world["location"]
        temple = local_places.create_local_place(self.world, city, "temple", name="Lidda Tapınağı")
        await self.say("tapınağa gidiyorum")
        self.assertEqual(self.world["location"], temple["id"])
        await self.say("sunağın üstüne çıkıp oturuyorum, ayaklarımı sallıyorum")
        self.assertEqual(self.world["location"], temple["id"])


class InAFightTests(ThreePlaysTests):
    async def fight(self, character=BARBARIAN):
        await self.begin(character)
        self.world["npcs"].clear()
        self.session.character.update(current_hp=300, max_hp=300)
        self.foe = self.add_person("Dorn", "Liman işçisi", current_hp=500, max_hp=500, armor_class=30)
        await self.say("liman işçisine vuruyorum", PlayClient(intent="attack"))
        self.assertTrue(self.world["combat"]["active"])

    async def test_rage_starts_from_plain_words(self):
        for line in ("öfkeye kapılıyorum, rage!", "rage kullanıyorum", "Rage başlatıyorum.", "Öfkeye giriyorum."):
            with self.subTest(line=line):
                await self.fight()
                uses = self.world[barbarian_rage.KEY]["remaining"]
                await self.say(line, PlayClient(intent="combat"))
                self.assertEqual(self.world[barbarian_rage.KEY]["remaining"], uses - 1)

    async def test_running_away_is_a_real_attempt(self):
        for line in ("tamam bu iş sıkıcı, kaçıyorum buradan", "iskeleden çıkıyorum"):
            with self.subTest(line=line):
                await self.fight()
                round_before = self.world["combat"]["round"]
                out = await self.say(line, PlayClient(narration="Rıhtım boyunca uzaklaşıyorsun."))
                self.assertTrue(not self.world["combat"]["active"] or self.world["combat"]["round"] > round_before,
                                out["narration"])

    async def test_waiting_passes_the_turn_in_the_fiction(self):
        await self.fight()
        round_before = self.world["combat"]["round"]
        out = await self.say("bekliyorum", PlayClient())
        self.assertNotIn("sürümünde", out["narration"])
        self.assertGreater(self.world["combat"]["round"], round_before)


class RestingTests(ThreePlaysTests):
    async def test_lying_down_anywhere_is_sleep(self):
        for line in ("tezgahın altına girip kıvrılıyorum, burda uyuycam biraz",
                     "karakolun köşesine uzanıp çavuşun gözü önünde uyuyorum", "burada uyuyorum",
                     "odaya çıkıyorum yatıp uyuyorum",
                     "tamam parasını veriyorum, odaya çıkıp yarın sabaha kadar uyuyorum"):
            with self.subTest(line=line):
                await self.begin(ROGUE)
                self.session.character["current_hp"] = 1
                out = await self.say(line, PlayClient())
                self.assertEqual(self.session.character["current_hp"], self.session.character["max_hp"], out["narration"])

    async def test_a_drink_is_told_not_asked_about(self):
        await self.begin(BARBARIAN)
        out = await self.say("birayi kafaya dikiyorum", PlayClient(intent="use_item", narration="Sokakta hayat akıyor."))
        self.assertNotIn("belirtir misin", out["narration"])


class NoMechanicalAdviceTests(ThreePlaysTests):
    async def test_no_keep_looking_advice_on_a_stroll(self):
        await self.begin(ROGUE)
        client = PlayClient(intent="unknown", narration="Sokakta hayat akıyor.")
        out = await self.say("of bıktım buradan. uzaklaşıp en pis meyhaneyi arıyorum", client)
        self.assertNotIn("biraz daha", out["narration"])


class SmallThingsTests(ThreePlaysTests):
    async def test_the_words_after_a_walk_reach_the_person(self):
        for line in ("defter yazan muhafıza yaklaşıyorum. selam, ne yazıyorsun öyle?",
                     "muhafıza yaklaşıp hey teneke kafa, annen o miğferi sana niye taktı"):
            with self.subTest(line=line):
                await self.begin(ROGUE)
                self.world["npcs"].clear()
                self.add_person("Dorn", "Muhafız")
                out = await self.say(line, PlayClient(spoken="Yürü git işine."))
                self.assertIn("Yürü git", out["narration"])

    async def test_a_bag_question_is_answered(self):
        for line in ("çantamda ne var", "elmayı aldım mı, üstümde ne var bakıyım"):
            with self.subTest(line=line):
                await self.begin(ROGUE)
                out = await self.say(line, PlayClient())
                self.assertIn("Hançer", out["narration"])

    async def test_a_name_said_in_passing_counts(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        steward = self.add_person("Dorn", "Kâhya")
        await self.say("selam, ben carius. burada iş var mı", PlayClient(spoken="Olabilir."), mode="say")
        out = await self.say("kâhyaya dönüyorum. muhafız sana adımı yazdırmamı söyledi. yaz bakalım, carius",
                             PlayClient(spoken="Yazdım, Carius."))
        self.assertNotIn("henüz adını söylemedin", out["narration"])
        self.assertTrue(steward["memory"])

    async def test_following_someone_by_what_shows(self):
        await self.begin(ROGUE)
        self.world["npcs"].clear()
        self.add_person("Dorn", "Kent sakini", visible_trait="gri pelerinli")
        out = await self.say("gri pelerinliyi gizlice takip ediyorum, nereye gidiyor bakalım", PlayClient())
        self.assertNotIn("izini kaybediyorsun", out["narration"])
        self.assertNotIn("Sıradaki adımın", out["narration"])


class FireTests(ThreePlaysTests):
    async def test_a_fire_is_at_least_attempted(self):
        for line in ("çantamdan yağ ve kav çıkarıyorum, şu duvar dibindeki çöp yığınını ateşe veriyorum",
                     "ne sorusu ya. çöpleri yakıyorum diyorum, ateş yakıyorum",
                     "kapüşonluyla konuşmuyorum. yerdeki çöp yığınını ateşe veriyorum"):
            with self.subTest(line=line):
                await self.begin(ROGUE)
                out = await self.say(line, PlayClient())
                self.assertEqual(out["turn_outcome"]["action"], "arson", out["narration"])


class SparedTests(ThreePlaysTests):
    async def test_a_townsman_stops_hitting_you_when_you_are_down(self):
        await self.begin(ROGUE)
        self.world["npcs"].clear()
        with self.app.state.ollama_adapter.engine_binding():
            person = self.session.create_npc_from_ai(
                {"name": "Tariq", "role": "Muhafız", "location": self.world["location"]})
        person.update(current_hp=300, max_hp=300, role_known_to_player=True,
                      reality_layer="PROCEDURAL_LOCAL_FICTION")
        self.session.character["current_hp"] = 1
        out = None
        for _ in range(40):
            out = await self.say("muhafıza saldırıyorum", PlayClient(intent="attack"))
            if self.session.character["current_hp"] == 0:
                break
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertNotIn("kritik", out["narration"])


class TheDeadTests(ThreePlaysTests):
    async def scene_with_a_body(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        self.dead = self.add_person("Tariq", "Muhafız", current_hp=0, combat_status="dead")
        self.living = self.add_person("Ilyra", "Barmen", visible_trait="gençten")

    async def test_the_dead_leave_the_scene_list(self):
        await self.scene_with_a_body()
        out = await self.say("burada kimler var, bakıyorum", PlayClient())
        ids = [person.get("id") for person in out["state"]["scene"]["npcs"]]
        self.assertNotIn(self.dead["id"], ids)
        self.assertIn(self.living["id"], ids)

    async def test_a_look_shows_the_body_on_the_floor(self):
        await self.scene_with_a_body()
        out = await self.say("etrafa bakıyorum", PlayClient())
        self.assertIn("yerde", out["narration"].casefold())

    async def test_the_dead_do_not_answer(self):
        await self.scene_with_a_body()
        client = PlayClient(spoken="Karşında dimdik duruyorum, hayattayım işte.")
        out = await self.say("muhafız, ölmüş olman lazım senin, nasılsın", client)
        self.assertNotIn("hayattayım", out["narration"])

    async def test_an_attack_on_the_dead_asks_about_the_living(self):
        await self.scene_with_a_body()
        out = await self.say("saldırıyorum", PlayClient(intent="attack"))
        self.assertNotIn("muhafız", out["narration"].casefold())


class WhatWasSaidTests(ThreePlaysTests):
    """A reference to what was said goes to the person, who says it was theirs."""

    async def talked_to_steward(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.steward = self.add_person("Dorn", "Kâhya", name_known_to_player=True)
        flags = self.world.setdefault("flags", {})
        flags.update(active_npc_id=self.steward["id"], last_npc_id=self.steward["id"],
                     active_npc_until_turn=flags.get("turn_index", 0) + 6)
        npc_statements.record(self.world, self.steward, "iş var mı",
                              "Dorn, “Ücret otuz sekiz bakır, süre bir gün, gerisini sonra konuşuruz.”",
                              turn=1)

    async def test_bargaining_over_a_price_reaches_the_person(self):
        for line in (
            "38 bakır mı? şaka gibi. en az bir altın ederim ben, çok savaş gördüm. hem detay dedin ne detayı, anlat",
            "nasıl yanılıyorum daha demin sen söyledin otuz sekiz bakır diye, dalga mı geçiyorsun",
            "usta sen birkaç sokak ötede demiştin, yolu tarif et de bulayım",
        ):
            with self.subTest(line=line):
                await self.talked_to_steward()
                client = PlayClient(spoken="Otuz sekiz dedim, bir altın değil. Pazarlık etme.")
                out = await self.say(line, client)
                self.assertIn("Pazarlık etme", out["narration"])

    async def test_someone_else_said_it_is_no_claim_about_this_person(self):
        for line in (
            "selam usta, isolde sen misin? iskeledeki adam seni tavsiye etti, iş var mı dedi",
            "sokakta bir adam dedi senin burada bir derdin varmış",
        ):
            with self.subTest(line=line):
                await self.talked_to_steward()
                client = PlayClient(spoken="Kim dedi onu sana? Derdim bana kalsın.")
                out = await self.say(line, client)
                self.assertIn("Derdim bana kalsın", out["narration"])

    async def test_their_real_words_are_in_front_of_the_model(self):
        await self.talked_to_steward()
        client = PlayClient(spoken="Doğru, öyle demiştim.")
        prompts = []
        real_chat = client.chat
        def chat(*args, **kwargs):
            prompts.extend(str(item.get("content")) for item in kwargs.get("messages", []))
            return real_chat(*args, **kwargs)
        client.chat = chat
        await self.say("dün bana otuz sekiz bakır dedin, bak deftere", client)
        self.assertTrue(any("otuz sekiz bakır" in prompt and "gerisini sonra" in prompt for prompt in prompts))


class GoingPlacesTests(ThreePlaysTests):
    async def city(self, character=FIGHTER):
        await self.begin(character)
        self.settlement = self.world["location"]
        self.estate = local_places.create_local_place(self.world, self.settlement, "estate", name="Hadrik Konağı")
        self.harbor = local_places.create_local_place(self.world, self.settlement, "harbor", name="Aelar İskelesi")

    async def test_a_place_named_in_the_past_is_not_the_destination(self):
        line = ("kâhyanın yanına gidip selam veriyorum. ben carius, eski askerim. "
                "iskelede duydum burada adam arıyormuşsunuz")
        self.assertIsNone(local_places.is_local_place_visit(line))

    async def test_the_place_at_the_motion_verb_wins(self):
        self.assertEqual(local_places.is_local_place_visit("ya iskeleye niye geldim ben, konağa dönüyorum"), "estate")
        self.assertEqual(local_places.is_local_place_visit("peki sağol, ben o konağa gideyim bakayım"), "estate")
        self.assertEqual(local_places.is_local_place_visit("ya önündeyim işte, demirhaneye giriyorum"), "smithy")

    async def test_a_resident_shares_a_first_name_with_a_named_inn(self):
        await self.city()
        self.harbor["resident_name"] = "Berrin"
        self.world["locations"]["inn_1"] = {
            "name": "Berrin Hanı", "parent_location_id": self.settlement, "scene_kind": "tavern",
        }
        line = "Marek'in söylediği Berrin Hanı'e gidiyorum."
        self.assertIsNone(local_places.resident_visit(self.world, self.settlement, line))
        self.assertEqual(local_places.resident_visit(self.world, self.settlement, "Berrin'in yanına gidiyorum"), self.harbor)

    async def test_the_first_visit_of_a_seeded_place_is_a_first_visit(self):
        await self.city()
        out = await self.say("peki sağol, ben o konağa gideyim bakayım")
        self.assertNotIn("Yeniden", out["narration"])
        await self.say("dışarı çıkıyorum")
        out = await self.say("konağa gidiyorum")
        self.assertIn("Yeniden", out["narration"])

    async def test_every_way_of_leaving_leaves(self):
        for line in ("sokaga cikiyorum", "tamam burda is kalmadi sokaga cikiyorum, kan icinde sekilde.",
                     "ikisi de oldu zaten salak misin. handan cikiyorum", "disari cik",
                     "kapidan cikiyorum", "sokaga gidiyorum", "iskeleden çıkıyorum",
                     "boşver, siktir et bu konağı. çıkıyorum", "burdan sıvışıyorum, sokağa çıkıyorum",
                     "pazardan çıkıp soyulacak zengin bir ev bakıyorum"):
            with self.subTest(line=line):
                await self.city()
                await self.say("konağa gidiyorum")
                self.assertEqual(self.world["location"], self.estate["id"])
                out = await self.say(line, PlayClient(narration="Kapıdan dışarı adım atıyorsun."))
                self.assertEqual(self.world["location"], self.settlement, (line, out["narration"], out["turn_outcome"]))

    async def test_going_up_to_a_room_is_not_leaving(self):
        await self.city()
        await self.say("konağa gidiyorum")
        await self.say("odaya çıkıyorum", PlayClient(narration="Merdivenleri çıkıyorsun."))
        self.assertEqual(self.world["location"], self.estate["id"])


class DoorIsNotEverythingTests(ThreePlaysTests):
    async def test_a_threat_near_a_door_word_is_a_threat(self):
        await self.begin(FIGHTER)
        self.world["npcs"].clear()
        self.add_person("Dorn", "Kâhya")
        out = await self.say("elimi kılıcımın kabzasına koyup sakin sakin konuşuyorum: bana bak, ya işimi "
                             "verirsin ya da hadrik efendiye söylerim adamı kapıda oyalıyorsun",
                             PlayClient(spoken="Tehdit mi ediyorsun?"))
        self.assertNotIn("kapı", out["narration"].casefold())

    async def test_shoving_a_person_is_not_opening_a_door(self):
        await self.begin(BARBARIAN)
        self.world["npcs"].clear()
        self.add_person("Dorn", "Demirci")
        out = await self.say("demirciyi itiyorum, yüzümü korların içine bastırıyorum",
                             PlayClient(narration="Demirci sendeliyor."))
        self.assertNotIn("kapı", out["narration"].casefold())

    async def test_shouting_at_a_barman_is_not_a_door(self):
        await self.begin(BARBARIAN)
        await self.say("yakınlarda bir han arıyorum")
        await self.say("hana giriyorum")
        self.add_person("Dorn", "Barmen")
        out = await self.say("barmene bagiriyorum: bu adamin parasi nerde, cikar kasayi yoksa senin de kelleni alirim",
                             PlayClient(spoken="Defol git."))
        self.assertNotIn("kapı", out["narration"].casefold())
        self.assertNotIn("Koşulun", out["narration"])


class DeathTests(ThreePlaysTests):
    async def test_every_line_after_permadeath_gets_a_death_scene(self):
        await self.begin(BARBARIAN, death_mode="PERMADEATH")
        self.session.character["current_hp"] = 0
        self.world["player_combat_status"] = "dead"
        self.world["death_state"].update(dead=True, failures=3, terminal=True)
        for line, mode in (("ne oldu, öldüm mü", None), ("kalkmaya çalışıyorum", "do"), ("selam", "say")):
            with self.subTest(line=line):
                client = PlayClient()
                out = await self.say(line, client, mode=mode)
                self.assertIn("öldün", out["narration"].casefold())
                self.assertEqual(client.calls, 0)
                self.assertEqual(self.world["player_combat_status"], "dead")

    async def test_speaking_while_unconscious_rolls_the_save_instead_of_an_error(self):
        await self.begin(BARBARIAN, death_mode="PERMADEATH")
        self.session.character["current_hp"] = 0
        self.world["player_combat_status"] = "unconscious"
        for line, mode in (("yardım edin", "say"), ("kalkmaya çalışıyorum", None)):
            with self.subTest(line=line):
                out = await self.say(line, PlayClient(), mode=mode)
                self.assertTrue(out["narration"].strip())

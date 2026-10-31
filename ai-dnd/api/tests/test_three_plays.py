"""What three real plays broke, replayed with the players' own Turkish lines.

Each test posts through the HTTP API, because the plays failed there: a raw
400 or 500 is a lost turn no matter how the engine got to it.
"""

import json
import unittest
import uuid

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
                self.add_person("Dorn", "Muhafız")
                out = await self.say(line, PlayClient(intent="attack"))
                self.assertTrue(self.world["combat"]["active"], out["narration"])


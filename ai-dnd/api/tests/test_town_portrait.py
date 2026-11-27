"""Town portrait: the first model-narrated arrival at a settlement leaves its opening lines on the record (D-249)."""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

from api.tests import test_campaign_api as fixtures
from api.tests.town_seed import fixed_town

HOME = "fr:city:neverwinter"
FAR = "town:test-karaduvar"
FIRST = "Sis dağılırken Karaduvar'ın taş kapısı belirir."
SECOND = "Halatlar gıcırdıyor, martılar çığlık atıyor."
THIRD = "Uzakta bir çan üç kez çalıyor."


class _TravelClient(fixtures.ControlledVenueOllamaClient):
    """Intent says travel; the narration call answers a settable text, or raises."""

    def __init__(self, target, narration, fail=False):
        super().__init__(intent="travel", target_reference=target)
        self.narration = narration
        self.fail = fail

    def chat(self, *args, **kwargs):
        properties = (kwargs.get("format") or {}).get("properties", {})
        if "intent" not in properties:
            if self.fail:
                raise RuntimeError("model down")
            return {"message": {"content": json.dumps(
                {"narration": self.narration, "world_updates": {}, "lore_claims": []}, ensure_ascii=False)}}
        return super().chat(*args, **kwargs)


class TownPortrait(unittest.IsolatedAsyncioTestCase):
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown

    async def asyncSetUp(self):
        await fixtures.CampaignApiTests.asyncSetUp(self)
        with fixed_town(self, 6260):
            created = await self.http.post("/api/game/campaigns", json={"campaign_start": {
                "setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                "region_id": "fr:region:the_north", "starting_location_id": HOME}})
        self.assertEqual(created.status_code, 200, created.text)
        self.session_id = created.json()["session_id"]
        locations = self.world["locations"]
        locations[FAR] = {"id": FAR, "name": "Karaduvar", "aliases": ["karaduvar", FAR], "type": "town",
                          "region_id": "fr:region:the_north", "description": "Tuzlu bir liman kasabası.",
                          "travel_routes": {HOME: [300]}}
        locations[HOME].setdefault("travel_routes", {})[FAR] = [300]

    @property
    def world(self):
        return self.manager.get(self.session_id).game_session.world_state

    async def travel(self, target, narration, fail=False):
        action_id = str(uuid.uuid4())
        with (patch.object(self.app.state.ollama_adapter, "_client", _TravelClient(target, narration, fail)),
              patch("timed_gameplay.travel_dice", return_value=(None, {}))):
            response = await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json={
                "message": "Karaduvar'a varıyorum." if target == FAR else "Neverwinter'a varıyorum.", "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.last = response
        self.assertEqual(response.json()['state']['location'], target)
        return action_id

    async def test_first_model_arrival_writes_two_sentence_portrait(self):
        await self.travel(FAR, f"{FIRST} {SECOND} {THIRD}")
        self.assertEqual(self.world["locations"][FAR]["town_portrait"], f"{FIRST} {SECOND}")

    async def test_python_fallback_arrival_writes_nothing(self):
        invented = "Kapıdan girip sandığı açıyorsun ve içindeki mührü cebine koyuyorsun."
        await self.travel(FAR, invented)
        self.assertNotIn(invented, self.last.json()["narration"])
        self.assertNotIn("town_portrait", self.world["locations"][FAR])

    async def test_second_arrival_does_not_overwrite(self):
        await self.travel(FAR, f"{FIRST} {SECOND} {THIRD}")
        await self.travel(HOME, "Eve dönüyorsun. Kapılar hâlâ açık.")
        await self.travel(FAR, "Bambaşka iki cümle. Bunlar yazılmamalı.")
        self.assertEqual(self.world["locations"][FAR]["town_portrait"], f"{FIRST} {SECOND}")

    async def test_undo_removes_portrait(self):
        before = copy.deepcopy(self.world["locations"][FAR])
        action_id = await self.travel(FAR, f"{FIRST} {SECOND}")
        self.assertIn("town_portrait", self.world["locations"][FAR])
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.world["locations"][FAR], before)

    async def test_quoted_speech_is_dropped(self):
        await self.travel(FAR, f"Bir çocuk bağırıyor: “Yeni gelen!” {FIRST} {SECOND} {THIRD}")
        portrait = self.world["locations"][FAR]["town_portrait"]
        self.assertNotIn("“", portrait)
        self.assertNotIn("Yeni gelen", portrait)
        self.assertIn(portrait, self.last.json()["narration"])
        self.assertEqual(len(portrait.split(". ")), 2)

    async def test_money_sentence_is_not_in_the_portrait(self):
        """Direct on the keeper: the finalizer may not catch every figure, the portrait itself must."""
        import game
        world = self.world
        result = {"action": "travel", "success": True, "status": "completed", "previous_location": HOME}
        with patch.object(game._DEFAULT_SESSION, "world_state", world):
            world["location"] = FAR  # D-303: the start settlement (HOME) is never arrived at, so the keeper writes FAR
            world["locations"][FAR].pop("town_portrait", None)
            game._keep_town_portrait(result, f"Kapının üstüne 20 gümüş yazılmış. {FIRST} {SECOND} {THIRD}")
        self.assertEqual(world["locations"][FAR]["town_portrait"], f"{FIRST} {SECOND}")

    async def test_guillemet_and_single_quote_speech_is_dropped(self):
        await self.travel(FAR, f"Bir çocuk bağırıyor: «Yeni gelen!» Biri fısıldıyor: ‘Yabancı.’ {FIRST} {SECOND} {THIRD}")
        portrait = self.world["locations"][FAR]["town_portrait"]
        for mark in ("«", "»", "‘", "’", "Yeni gelen", "Yabancı"):
            self.assertNotIn(mark, portrait)
        self.assertTrue(portrait)

    async def test_return_from_a_local_place_writes_no_portrait(self):
        import local_places
        place = local_places.create_local_place(self.world, HOME, "smithy")
        self.world["location"] = place["id"]
        await self.travel(HOME, "Ana caddeye çıkıyorsun. Pazar kalabalık.")
        self.assertNotIn("town_portrait", self.world["locations"][HOME])


if __name__ == "__main__":
    unittest.main()

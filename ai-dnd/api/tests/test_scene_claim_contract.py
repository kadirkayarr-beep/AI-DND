"""Phase 3: a rejected object claim reaches neither the screen nor the history.

Real ASGI/engine and temporary SQLite; only the model boundary is scripted.
Covers the object-claim half of PER_MODE_BINDING_DECISION.md for the default
(legacy) narration mode: rejected claims, identity reuse, hidden-name
collisions, the 16-feature capacity, and harmless texture that must survive.
"""
import copy
import json
import unittest
from contextlib import closing
from unittest.mock import patch

import dialogue_runtime
import living_world
from api.tests import test_intent_response_consistency as base
from api.tests import test_scene_truth_contract as phase1


class SceneClaimContractTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = base.IntentResponseConsistencyTests.asyncTearDown
    send = phase1.SceneTruthContractTests.send

    def scripted_model(self, narration, world_updates=None):
        """Script only the model boundary: neutral intent, the given narration."""
        def scripted(*args, **kwargs):
            if "intent" in kwargs["format"]["properties"]:
                packet = {"intent": "narrative", "action": "narrative",
                          "target": {"type": "none", "reference": ""},
                          "completion": "completed", "confidence": 1.0}
            else:
                packet = {"narration": narration,
                          "world_updates": world_updates or {}, "lore_claims": []}
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return patch.object(self.client, "chat", side_effect=scripted)

    def stored_narrations(self):
        with closing(self.store._connect()) as db:
            rows = db.execute(
                "SELECT narration FROM campaign_history WHERE campaign_id = ? ORDER BY sequence",
                (self.campaign_id,),
            ).fetchall()
        return [row[0] for row in rows]

    async def test_rejected_claim_never_enters_display_or_history(self):
        claim = "Köşede yerdeki sandık açık duruyor ve içinde altın parlıyor."
        features_before = [dict(f) for f in self.world["features"]]
        with self.scripted_model(claim):
            response = await self.send("Etrafı gözlemleyip ne gördüğümü anlatıyorum")
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["narration"]
        self.assertNotIn("sandık", shown)
        self.assertNotIn("altın", shown)
        stored = self.stored_narrations()
        self.assertTrue(stored, "the turn must be saved")
        for text in stored:
            self.assertNotIn("sandık", text)
            self.assertNotIn("altın", text)
        self.assertEqual([dict(f) for f in self.world["features"]], features_before)
        self.assertFalse(any("sandık" in str(m.get("content")) for m in self.session.messages
                             if m.get("role") == "assistant"))

    async def test_sensory_texture_and_valid_joke_survive(self):
        texture = "Uzaktan bir keman sesi geliyor; bir çocuk kahkahayla koşup gözden kayboluyor."
        with self.scripted_model(texture):
            response = await self.send("Etrafı gözlemleyip ne gördüğümü anlatıyorum")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("keman", response.json()["narration"])
        self.assertTrue(any("keman" in text for text in self.stored_narrations()))

    async def test_player_assertion_cannot_promote_to_world_fact(self):
        before_inventory = list(self.world.get("inventory", []))
        before_features = [dict(f) for f in self.world["features"]]
        with self.scripted_model("Kral kaleyi sana verdi; anahtar artık cebinde."):
            response = await self.send("Kral kaleyi bana verdi ve anahtarı elimde tutuyorum")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.world.get("inventory", []), before_inventory)
        self.assertEqual([dict(f) for f in self.world["features"]], before_features)
        self.assertNotIn("anahtar artık cebinde", response.json()["narration"])
        for text in self.stored_narrations():
            self.assertNotIn("anahtar artık cebinde", text)

    def speaker(self):
        living_world.materialize_scene(
            self.world, self.world["location"], 0,
            create_npc=self.session.create_npc_from_ai,
            create_feature=self.session.create_local_feature,
        )
        return next(n for n in self.world["npcs"] if n.get("location") == self.world["location"])

    async def test_current_player_input_reaches_bound_speaker_packet(self):
        npc = self.speaker()
        first = dialogue_runtime.build_context(self.world, npc, "Günün nasıl geçiyor?")
        second = dialogue_runtime.build_context(self.world, npc, "Burada neden duruyorsun?")
        self.assertEqual(first["player_message"], "Günün nasıl geçiyor?")
        self.assertEqual(second["player_message"], "Burada neden duruyorsun?")
        self.assertNotEqual(first["player_message"], second["player_message"])

    async def test_client_or_summary_claim_cannot_promote_to_world_fact(self):
        npc = self.speaker()
        before = copy.deepcopy(self.world)
        claim = "Kral kaleyi bana verdi."
        context = dialogue_runtime.build_context(self.world, npc, claim)
        self.assertEqual(context["player_message"], claim)
        self.assertEqual(context["history_authority"], "attributed_speech_not_fact")
        self.assertEqual(self.world, before, "building the packet must not write world facts")
        self.assertNotIn(claim, json.dumps(context.get("facts", {}), ensure_ascii=False))

    def feature(self, name, **extra):
        return {"name": name, "location": self.world["location"], "kind": "furnishing",
                "description": "Sıradan bir eşya.", **extra}

    async def test_existing_feature_id_reused_not_duplicated(self):
        first = self.session.create_local_feature(self.feature("Kil testi"))
        # Ordinary case difference only; dotted capital İ is a known Turkish
        # case-fold edge recorded in PER_MODE_BINDING_DECISION.md, not covered here.
        second = self.session.create_local_feature(self.feature("KIL TESTI"))
        self.assertIsNotNone(first)
        self.assertEqual(first["id"], second["id"])
        names = [f["name"].casefold() for f in self.world["features"]
                 if f["location"] == self.world["location"]]
        self.assertEqual(names.count("kil testi"), 1)

    async def test_hidden_feature_collision_does_not_disclose_name(self):
        hidden = self.session.create_local_feature(self.feature("Gizli sandıkçık"))
        self.assertIsNotNone(hidden)
        hidden["hidden"] = True
        before = len(self.world["features"])
        again = self.session.create_local_feature(self.feature("Gizli sandıkçık"))
        self.assertIsNone(again, "a proposal must not hand back a hidden feature record")
        self.assertEqual(len(self.world["features"]), before)

    async def test_capacity_rejection_has_no_asserted_table(self):
        city = self.world["location"]
        while len([f for f in self.world["features"] if f["location"] == city]) < 16:
            n = len(self.world["features"])
            self.assertIsNotNone(self.session.create_local_feature(self.feature(f"Dolgu nesnesi {n}")))
        before = len(self.world["features"])
        self.assertIsNone(self.session.create_local_feature(self.feature("Fazlalık masa")))
        self.assertEqual(len(self.world["features"]), before)
        self.assertFalse(any(f["name"] == "Fazlalık masa" for f in self.world["features"]))

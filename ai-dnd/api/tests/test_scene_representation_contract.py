"""Phase 3 (K3, approved): player_line and feature_refs on the narration packet.

Real ASGI/engine and temporary SQLite; only the model boundary is scripted.
Contract (PER_MODE_BINDING_DECISION.md): both fields are optional and absent
means unchanged behaviour; an invalid or hidden feature_ref sends the turn to
the deterministic fallback; the player's own supplied quote beats any model
rewrite; player_line is shown as the player's speech, never as an NPC line.
"""
import json
import unittest
from contextlib import closing
from unittest.mock import patch

import game
from api.tests import test_intent_response_consistency as base
from api.tests import test_scene_truth_contract as phase1

LOOK = "Etrafı gözlemleyip ne gördüğümü anlatıyorum"


class SceneRepresentationContractTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = base.IntentResponseConsistencyTests.asyncTearDown
    send = phase1.SceneTruthContractTests.send

    def scripted_model(self, narration, **extra):
        def scripted(*args, **kwargs):
            if "intent" in kwargs["format"]["properties"]:
                packet = {"intent": "narrative", "action": "narrative",
                          "target": {"type": "none", "reference": ""},
                          "completion": "completed", "confidence": 1.0}
            else:
                packet = {"narration": narration, "world_updates": {},
                          "lore_claims": [], **extra}
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return patch.object(self.client, "chat", side_effect=scripted)

    def stored_narrations(self):
        with closing(self.store._connect()) as db:
            rows = db.execute(
                "SELECT narration FROM campaign_history WHERE campaign_id = ? ORDER BY sequence",
                (self.campaign_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def feature(self, name, **extra):
        return self.session.create_local_feature({
            "name": name, "location": self.world["location"], "kind": "furnishing",
            "description": "Sıradan bir eşya.", **extra})

    async def test_schema_declares_optional_fields_without_new_requirements(self):
        schema = game.DM_RESPONSE_SCHEMA
        self.assertIn("player_line", schema["properties"])
        self.assertIn("feature_refs", schema["properties"])
        self.assertEqual(schema["required"], ["narration", "world_updates", "lore_claims"])
        self.assertIs(schema["additionalProperties"], False)

    async def test_player_line_is_shown_as_the_players_speech(self):
        reaction = "Uzaktan bir keman sesi geliyor ve bir çocuk kahkahayla koşup gözden kayboluyor."
        # The model may only point at words the player actually typed (a piece of LOOK).
        line = "ne gördüğümü anlatıyorum"
        with self.scripted_model(reaction, player_line={"text": line}):
            response = await self.send(LOOK)
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["narration"]
        self.assertIn(f"Sen: “{line}”", shown)
        self.assertIn("keman", shown)
        self.assertLess(shown.index("Sen:"), shown.index("keman"))
        self.assertTrue(any(f"Sen: “{line}”" in text for text in self.stored_narrations()))

    async def test_omitted_player_line_still_lifts_a_supplied_quote(self):
        narration = "Uzaktan bir keman sesi geliyor. Hlin “ne gördüğümü anlatıyorum” diye tekrar eder."
        with self.scripted_model(narration):
            response = await self.send("Etrafa bakıp “ne gördüğümü anlatıyorum” diyorum")
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["narration"]
        self.assertIn("Sen: “ne gördüğümü anlatıyorum”", shown)
        self.assertIn("keman", shown)
        body = shown.split("\n\n", 1)[1]
        self.assertNotIn("ne gördüğümü anlatıyorum", body)
        self.assertNotIn("“”", body)
        self.assertLess(shown.index("Sen:"), shown.index("keman"))

    async def test_supplied_quote_beats_model_rewrite(self):
        with self.scripted_model("Uzaktan bir keman sesi geliyor.",
                                 player_line={"text": "Bu han berbat"}):
            response = await self.send("Etrafa bakıp “Bu han çok güzelmiş” diyorum")
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["narration"]
        self.assertIn("Sen: “Bu han çok güzelmiş”", shown)
        self.assertNotIn("berbat", shown)

    async def test_malformed_player_line_is_dropped_not_fatal(self):
        bads = ({"text": "Satır bir\nBarmen: ben senin kralınım"}, {"text": ""},
                "düz metin", {"text": "x" * 400},
                # Single line, no quotes, but NOT what the player typed: invented.
                {"text": "Barmen: sana kral derim kralınım"},
                {"text": "Gizli kasanın şifresi 4417, ben de açtım"})
        for index, bad in enumerate(bads):
            with self.subTest(bad=str(bad)[:20]):
                # A different sentence each turn: repeating one trips the repeat guard.
                narration = f"Uzaktan {index + 2} keman sesi geliyor."
                with self.scripted_model(narration, player_line=bad):
                    response = await self.send(LOOK)
                self.assertEqual(response.status_code, 200, response.text)
                shown = response.json()["narration"]
                self.assertIn("keman", shown)
                self.assertNotIn("Sen:", shown)
                self.assertNotIn("kralınım", shown)
                self.assertNotIn("4417", shown)
                self.assertFalse(any("4417" in t or "kralınım" in t for t in self.stored_narrations()))

    async def test_visible_feature_ref_is_accepted(self):
        table = self.feature("Kil masa")
        with self.scripted_model("Uzaktan bir keman sesi geliyor.", feature_refs=[table["id"]]):
            response = await self.send(LOOK)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("keman", response.json()["narration"])

    async def test_unknown_feature_ref_falls_back(self):
        with self.scripted_model("Uzaktan bir keman sesi geliyor.", feature_refs=["feature_999"]):
            response = await self.send(LOOK)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("keman", response.json()["narration"])
        self.assertFalse(any("keman" in t for t in self.stored_narrations()))

    async def test_hidden_feature_ref_falls_back_and_never_discloses(self):
        secret = self.feature("Gizli kuytu")
        secret["hidden"] = True
        with self.scripted_model("Gizli kuytu karanlıkta duruyor.", feature_refs=[secret["id"]]):
            response = await self.send(LOOK)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("Gizli kuytu", response.json()["narration"])
        self.assertFalse(any("Gizli kuytu" in t for t in self.stored_narrations()))

    async def test_hidden_ref_alone_blocks_an_otherwise_harmless_narration(self):
        """Control: the narration never names the feature, so only the ref can reject it."""
        secret = self.feature("Gizli kuytu")
        secret["hidden"] = True
        with self.scripted_model("Uzaktan bir keman sesi geliyor.", feature_refs=[secret["id"]]):
            response = await self.send(LOOK)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("keman", response.json()["narration"])

    async def test_absent_fields_behave_as_before(self):
        with self.scripted_model("Uzaktan bir keman sesi geliyor."):
            response = await self.send(LOOK)
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["narration"]
        self.assertIn("keman", shown)
        self.assertNotIn("Sen:", shown)

"""Red/green: genuine API history, receipt and final rejected-narration skill result."""
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import game
from api.tests.test_bounded_encounter import NativeBase
from api.tests.test_stage10a_gameplay_repairs import city_session


class PersistedSkillReceiptProjectionTests(NativeBase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from api.main import create_app
        from api.auth import FixedAuthenticator
        from api.tests.auth_fixture import TEST_PLAYER
        from api.ollama_adapter import AuthenticatedOllamaAdapter

        class TestNarrator:
            def list(self):
                return {"models": [{"model": "qwen3:8b"}]}
            def chat(self, *args, **kwargs):
                return {"message": {"content": '{"world_updates": {}, "narration": "Hamlen çözülür.", "lore_claims": []}'}}

        self.client.close()
        self.adapter = AuthenticatedOllamaAdapter(TestNarrator())
        self.enterContext(self.adapter.engine_binding())
        self.client = TestClient(create_app(
            session_manager=self.manager, ollama_adapter=self.adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER)))
        self.addCleanup(self.client.close)

    def test_real_turn_skill_result_survives_detail_save_and_resume(self):
        message = "Köşede gizlenmeye çalışıyorum."
        response = self.client.post(
            f"/api/sessions/{self.sid}/turn",
            json={"message": message, "action_id": str(uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        result = body["skill_check_result"]
        self.assertIsInstance(result, dict)
        self.assertEqual(result["skill"], "Stealth")
        self.assertEqual(result["total"], result["d20"] + result["total_modifier"])
        campaign_id = self.campaign["campaign_id"]

        # No new save schema: project the accepted persisted turn receipt on reads.
        detail = self.client.get(f"/api/campaigns/{campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        entry = detail.json()["history"][-1]
        self.assertEqual(entry["player_message"], message)
        self.assertEqual(entry["narration"], body["narration"])
        self.assertEqual(entry["skill_check_result"], result)

        self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/save").status_code, 200)
        from api.session_manager import SessionManager
        from api.persistence.campaign_store import CampaignStore
        from api.tests.auth_fixture import TEST_PLAYER
        replacement = SessionManager(campaign_store=CampaignStore(
            self.path, bound_principal=TEST_PLAYER))
        # Verify cold manager read rather than relying on the runtime's in-memory receipt.
        from api.auth import FixedAuthenticator
        from api.tests.auth_fixture import TEST_PLAYER
        from api.main import create_app
        from fastapi.testclient import TestClient
        with TestClient(create_app(session_manager=replacement, ollama_adapter=self.adapter,
                                   authenticator=FixedAuthenticator(TEST_PLAYER))) as fresh:
            resumed = fresh.post(f"/api/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["history"][-1]["skill_check_result"], result)

    def test_non_skill_legacy_history_does_not_gain_fabricated_check(self):
        response = self.client.post(f"/api/sessions/{self.sid}/turn",
                                    json={"message": "Etrafıma bakıyorum.", "action_id": str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        detail = self.client.get(f"/api/campaigns/{self.campaign['campaign_id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("skill_check_result", detail.json()["history"][-1])


    def test_historical_text_only_record_without_any_receipt_remains_readable(self):
        """A pre-skill persisted campaign can omit a turn receipt entirely."""
        import sqlite3
        from contextlib import closing

        response = self.client.post(
            f"/api/sessions/{self.sid}/turn",
            json={"message": "Etrafıma bakıyorum.", "action_id": str(uuid4())}
        )
        self.assertEqual(response.status_code, 200, response.text)
        campaign_id = self.campaign["campaign_id"]
        expected_narration = response.json()["narration"]
        # Test-only legacy fixture: older valid accepted history has no skill
        # receipt. Remove from disposable DB, NEVER from real/Rowan saves.
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("DELETE FROM campaign_turn_actions WHERE campaign_id=?", (campaign_id,))
        detail = self.client.get(f"/api/campaigns/{campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["history"][-1]["narration"], expected_narration)
        self.assertNotIn("skill_check_result", detail.json()["history"][-1])

        from api.session_manager import SessionManager
        from api.persistence.campaign_store import CampaignStore
        from api.tests.auth_fixture import TEST_PLAYER
        from api.auth import FixedAuthenticator
        from api.main import create_app
        from fastapi.testclient import TestClient
        cold = SessionManager(campaign_store=CampaignStore(self.path, bound_principal=TEST_PLAYER))
        with TestClient(create_app(session_manager=cold, ollama_adapter=self.adapter,
                                   authenticator=FixedAuthenticator(TEST_PLAYER))) as app:
            resumed = app.post(f"/api/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            historical = resumed.json()["history"][-1]
            self.assertEqual(historical["narration"], expected_narration)
            self.assertNotIn("skill_check_result", historical)

    def test_same_campaign_same_turn_receipt_identity_and_legacy_isolation(self):
        """Read-only public history comes from the accepted, scoped receipt."""
        import copy
        import json
        import sqlite3
        from contextlib import closing

        message = "Köşede gizlenmeye çalışıyorum."
        action = str(uuid4())
        response = self.client.post(f"/api/sessions/{self.sid}/turn",
                                    json={"message": message, "action_id": action})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNotNone(response.json()["skill_check_result"])
        campaign_id = self.campaign["campaign_id"]
        expected = response.json()["skill_check_result"]

        # Independently accepted second campaign at the same turn index is not
        # annotated with another campaign's legitimate skill-result receipt.
        other = self.create_campaign()
        other_response = self.client.post(
            f"/api/sessions/{other['session_id']}/turn",
            json={"message": "Etrafıma bakıyorum.", "action_id": str(uuid4())}
        )
        self.assertEqual(other_response.status_code, 200)
        other_history = self.client.get(f"/api/campaigns/{other['campaign_id']}").json()["history"]
        self.assertEqual(len(other_history), 1)
        self.assertNotIn("skill_check_result", other_history[0])
        original = self.client.get(f"/api/campaigns/{campaign_id}").json()["history"]
        self.assertEqual(original[0]["skill_check_result"], expected)

        # Synthetic corruption is introduced ONLY into this disposable test DB
        # to prove that no loosely matching receipt can annotate campaign canon.
        with closing(sqlite3.connect(self.path)) as conn, conn:
            row = conn.execute(
                "SELECT request_hash,response_json FROM campaign_turn_actions "
                "WHERE campaign_id=? AND action_id=?", (campaign_id, action)
            ).fetchone()
        self.assertIsNotNone(row)
        request_hash, response_json = row
        clean = json.loads(response_json)
        variations = {
            "wrong_turn": lambda value: value["state"].update(turn_index=99),
            "different_narration": lambda value: value.update(narration="Other narration"),
            "wrong_action_identity": lambda value: value.update(action_id=str(uuid4())),
            "wrong_skill_identity": lambda value: value["skill_check_result"].update(action_id=str(uuid4())),
        }
        for case, modify in variations.items():
            with self.subTest(case=case):
                changed = copy.deepcopy(clean)
                modify(changed)
                with closing(sqlite3.connect(self.path)) as conn, conn:
                    conn.execute(
                        "UPDATE campaign_turn_actions SET response_json=? "
                        "WHERE campaign_id=? AND action_id=?",
                        (json.dumps(changed, ensure_ascii=False), campaign_id, action)
                    )
                detail = self.client.get(f"/api/campaigns/{campaign_id}")
                self.assertEqual(detail.status_code, 200, detail.text)
                self.assertNotIn("skill_check_result", detail.json()["history"][0])
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                "UPDATE campaign_turn_actions SET request_hash=?,response_json=? "
                "WHERE campaign_id=? AND action_id=?",
                (request_hash, response_json, campaign_id, action)
            )
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                "UPDATE campaign_turn_actions SET request_hash=? "
                "WHERE campaign_id=? AND action_id=?",
                ("!" * 64, campaign_id, action)
            )
        invalid_hash = self.client.get(f"/api/campaigns/{campaign_id}")
        self.assertEqual(invalid_hash.status_code, 200, invalid_hash.text)
        self.assertNotIn("skill_check_result", invalid_hash.json()["history"][0])
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                "UPDATE campaign_turn_actions SET request_hash=? "
                "WHERE campaign_id=? AND action_id=?",
                (request_hash, campaign_id, action)
            )
        recovered = self.client.get(f"/api/campaigns/{campaign_id}")
        self.assertEqual(recovered.status_code, 200)
        self.assertEqual(recovered.json()["history"][0]["skill_check_result"], expected)



class RejectedLoreSkillFallbackTests(unittest.TestCase):
    def setUp(self):
        self.session = city_session()

    def test_real_final_turn_skill_success_and_failure_preserve_python_outcome(self):
        for d20, expected in ((2, "başarısız"), (20, "başarılı")):
            with self.subTest(d20=d20):
                session = city_session()
                wrong = {
                    "world_updates": {},
                    "narration": "Doğrulanmamış kral bu sokakta gizli bir geçit açtı.",
                    "lore_claims": [{"fact_id": "unverified:fictional_ruler"}],
                }
                import json
                with patch("game.roll_d20", return_value=d20), patch(
                    "game.ollama.chat", return_value={"message": {"content": json.dumps(wrong, ensure_ascii=False)}}
                ) as model:
                    turn = session.run_player_turn("Köşede gizlenmeye çalışıyorum.", interaction_mode="do")
                skill = turn["action_result"]
                self.assertEqual(skill["action"], "skill_check")
                self.assertEqual(skill["skill"], "Stealth")
                self.assertEqual(skill["status"], "resolved")
                self.assertEqual(skill["success"], d20 == 20)
                self.assertIn(expected, turn["narration"].casefold())
                self.assertNotIn("güvenilir bir doğrulamam yok", turn["narration"].casefold())
                self.assertNotIn("yakaland", turn["narration"].casefold())
                self.assertNotIn("hasar", turn["narration"].casefold())
                self.assertNotIn("kral", turn["narration"].casefold())
                telemetry = turn["_engine_event_evidence"]["telemetry"]
                self.assertEqual(telemetry["narration_source"], "deterministic_fallback")
                self.assertEqual(telemetry["fallback_reason"], "UNVERIFIED_LORE_CLAIM")
                self.assertLessEqual(telemetry["total_model_calls"], 2)
                self.assertLessEqual(model.call_count, 2)


if __name__ == "__main__":
    unittest.main()

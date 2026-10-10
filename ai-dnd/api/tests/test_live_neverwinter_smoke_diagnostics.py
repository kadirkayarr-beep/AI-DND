"""Offline regression tests for isolated Neverwinter live-smoke diagnostics."""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from api.tests.live_neverwinter_canon_smoke import (
    SmokeFailure,
    _narration_reports_no_shop,
    _post_turn,
    _preserve_failure_logs,
    _start_api,
    _turn_action_status,
)


class NeverwinterSmokeDiagnosticsTests(unittest.TestCase):
    def test_shop_response_is_grounded_without_developer_wording(self):
        self.assertTrue(_narration_reports_no_shop(
            "Bu çevrede şu an görünür bir dükkân ya da dükkâncı yok."
        ))
        self.assertFalse(_narration_reports_no_shop("Burada bir dükkân var."))
        self.assertFalse(_narration_reports_no_shop("Bir tüccar sizi bekliyor."))
        self.assertFalse(_narration_reports_no_shop(""))

    def test_shop_action_status_comes_from_python_turn_diagnostic(self):
        messages = [
            "Lore retrieval (selected_fact_ids=[])",
            "Turn diagnostics (model_calls=0, safety_code=answered_from_campaign_state, rolled_back=false)",
            "Game turn completed (model=qwen3:8b, model_calls=0)",
        ]
        self.assertEqual(_turn_action_status(messages), "answered_from_campaign_state")
        self.assertIsNone(_turn_action_status(["Game turn completed (model=qwen3:8b)"]))

    def test_isolated_api_subprocess_uses_utf8_for_dice_output(self):
        with tempfile.TemporaryDirectory(prefix="ai-dnd-test-encoding-") as temp:
            root = Path(temp)
            with patch("api.tests.live_neverwinter_canon_smoke.subprocess.Popen") as popen:
                _, handle = _start_api(
                    12345, root / "campaigns.sqlite3",
                    root / "turn-audit.jsonl", root / "api-first.log",
                )
                try:
                    self.assertEqual(popen.call_args.kwargs["env"]["PYTHONIOENCODING"], "utf-8")
                finally:
                    handle.close()

    def test_http_failure_logs_survive_disposable_campaign_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="ai-dnd-test-smoke-logs-") as temp:
            root = Path(temp)
            isolated = root / "disposable_campaign"
            isolated.mkdir()
            (isolated / "api-first.log").write_text(
                "Engine turn failed (error_type=RuntimeError, rolled_back=true)\\nTraceback...",
                encoding="utf-8",
            )
            (isolated / "campaigns.sqlite3").write_bytes(b"isolated test data")
            client = Mock()
            response = client.post.return_value
            response.status_code = 500
            response.json.return_value = {"detail": {"code": "engine_error"}}
            with self.assertRaises(SmokeFailure):
                _post_turn(client, "http://127.0.0.1:1234", "test-session", "investigate")
            with patch("api.tests.live_neverwinter_canon_smoke.tempfile.gettempdir", return_value=temp):
                saved = _preserve_failure_logs(isolated)
            self.assertEqual(len(saved), 1)
            shutil.rmtree(isolated)
            self.assertIn("Traceback", Path(saved[0]).read_text(encoding="utf-8"))
            self.assertFalse((Path(saved[0]).parent / "campaigns.sqlite3").exists())


class NeverwinterShopHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_shop_question_and_explicit_refusal_are_python_owned(self):
        from functools import wraps
        import copy
        import httpx
        from api.main import create_app
        from api.ollama_adapter import AuthenticatedOllamaAdapter
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from api.tests.live_neverwinter_canon_smoke import START_SELECTION

        model = Mock()
        model.list.return_value = {"models": [{"model": "qwen3:8b"}]}
        model.chat.side_effect = AssertionError("Deterministic shop turns must not call Qwen")
        adapter = AuthenticatedOllamaAdapter(model)
        with tempfile.TemporaryDirectory(prefix="ai-dnd-shop-http-") as temp:
            manager = SessionManager(campaign_store=CampaignStore(Path(temp) / "campaigns.sqlite3"))
            app = create_app(session_manager=manager, ollama_adapter=adapter)
            with adapter.engine_binding():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
                    created = await http.post("/api/game/campaigns", json={"campaign_start": START_SELECTION})
                    self.assertEqual(created.status_code, 200, created.text)
                    session_id = created.json()["session_id"]
                    session = manager.get(session_id).game_session
                    real_turn = session.run_player_turn
                    results = []

                    @wraps(real_turn)
                    def capture(*args, **kwargs):
                        result = real_turn(*args, **kwargs)
                        results.append(copy.deepcopy(result))
                        return result

                    with patch.object(session, "run_player_turn", new=capture):
                        for message, status in (
                            ("Are there any local shops or merchants here?", "answered_from_campaign_state"),
                            ("Never add or create a local shop or merchant in this campaign.", "explicitly_declined"),
                        ):
                            with self.subTest(status=status):
                                response = await http.post(f"/api/game/sessions/{session_id}/turn", json={"message": message})
                                self.assertEqual(response.status_code, 200, response.text)
                                body = response.json()
                                self.assertEqual(body["state"]["shops"], [])
                                self.assertEqual(body["state"]["npcs"], [])
                                self.assertEqual(results[-1]["action_result"]["status"], status)
                                self.assertEqual(results[-1]["_engine_event_evidence"]["telemetry"]["total_model_calls"], 0)
                                if status == "answered_from_campaign_state":
                                    self.assertTrue(_narration_reports_no_shop(body["narration"]))
                                else:
                                    self.assertIn("aramadan yoluna devam", body["narration"])
                    model.chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()

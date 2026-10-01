import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from api.tests import live_playable_living_world_v1_1_smoke as smoke
from api.tests.live_playable_living_world_v1_smoke import (
    _narration_telemetry_from_result,
    _sanitize_persistent_value,
)


class PlayableLivingWorldV11NarrationEvidenceTests(unittest.TestCase):
    def _turn(self, turn_number, label, *, complete=True):
        engine = {
            "intent_model_calls": 1,
            "narration_model_calls": 1,
            "total_model_calls": 2,
            "intent_source": "qwen",
            "narration_source": "qwen",
            "fallback_reason": None,
            "narration_validation_result": "accepted",
            "resolved_action_type": "conversation",
        }
        if not complete:
            engine.pop("narration_source")
        return smoke._narration_review_turn(
            turn_number=turn_number,
            label=label,
            message=f"Türkçe oyuncu girdisi {turn_number}.",
            target_id=None,
            action_result={"action": "conversation", "target_id": None},
            source={
                "model": smoke.MODEL_NAME,
                "narration": f"Son anlatım {turn_number}.",
                "model_calls": 2,
                "observed_model_calls": 2,
                "narration_telemetry": engine,
            },
            safety={
                "tier": "tier_0_accept",
                "handling": "accepted",
                "reason_code": "SAFE_ACCEPT",
                "scope": "ordinary_play",
            },
        )

    def test_help_exits_without_starting_the_smoke(self):
        output = io.StringIO()
        with (
            patch.object(smoke.sys, "argv", ["smoke", "--help"]),
            patch.object(
                smoke,
                "run_smoke",
                side_effect=AssertionError("live smoke must not run"),
            ),
            contextlib.redirect_stdout(output),
        ):
            status = smoke.main()

        self.assertEqual(status, 0)
        self.assertIn("--review-narrations", output.getvalue())
        self.assertIn("--finalize-review", output.getvalue())

    def test_unknown_option_exits_without_starting_the_smoke(self):
        output = io.StringIO()
        with (
            patch.object(smoke.sys, "argv", ["smoke", "--not-an-option"]),
            patch.object(
                smoke,
                "run_smoke",
                side_effect=AssertionError("live smoke must not run"),
            ),
            contextlib.redirect_stdout(output),
        ):
            status = smoke.main()

        self.assertEqual(status, 2)
        self.assertIn("Invalid smoke arguments", output.getvalue())

    def test_engine_telemetry_extraction_is_whitelisted(self):
        result = {
            "_engine_event_evidence": {
                "telemetry": {
                    "intent_model_calls": 1,
                    "narration_model_calls": 1,
                    "total_model_calls": 2,
                    "intent_source": "qwen",
                    "narration_source": "qwen",
                    "fallback_reason": None,
                    "narration_validation_result": "accepted",
                    "resolved_action_type": "conversation",
                    "private_prompt": "must not be copied",
                },
                "private_text": "must not be copied",
            }
        }

        telemetry = _narration_telemetry_from_result(result)

        self.assertEqual(
            telemetry,
            {
                "intent_model_calls": 1,
                "narration_model_calls": 1,
                "total_model_calls": 2,
                "intent_source": "qwen",
                "narration_source": "qwen",
                "fallback_reason": None,
                "narration_validation_result": "accepted",
                "resolved_action_type": "conversation",
            },
        )

    def test_review_artifact_persists_raw_turns_separately(self):
        rows = [
            self._turn(index, label)
            for index, label in enumerate(smoke.EXPECTED_LABELS, 1)
        ]
        identity = {
            "report_id": "1790000000000000000-1234abcd",
            "git_sha": "fixture-sha",
            "git_branch": "fixture-branch",
            "model": smoke.MODEL_NAME,
            "started_at_utc": "2026-01-01T00:00:00Z",
        }
        document = smoke._narration_review_document(
            identity,
            rows,
            status="finished",
            evidence_gaps=[],
        )

        self.assertTrue(document["run"]["evidence_complete"])
        self.assertEqual(document["run"]["recorded_turn_count"], 30)
        self.assertEqual(rows[0]["player_input"], "Türkçe oyuncu girdisi 1.")
        self.assertEqual(rows[0]["narration"], "Son anlatım 1.")
        sanitized = _sanitize_persistent_value(rows[0])
        self.assertNotIn("player_input", sanitized)
        self.assertNotIn("narration", sanitized)

        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            smoke._write_narration_review(report_dir, document)
            saved = json.loads(
                (report_dir / "narration-review.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(saved, document)

    def test_missing_provenance_makes_report_evidence_incomplete(self):
        rows = [
            self._turn(index, label)
            for index, label in enumerate(smoke.EXPECTED_LABELS, 1)
        ]
        rows[-1] = self._turn(
            len(smoke.EXPECTED_LABELS),
            smoke.EXPECTED_LABELS[-1],
            complete=False,
        )
        identity = {
            "report_id": "1790000000000000000-1234abcd",
            "git_sha": "fixture-sha",
            "git_branch": "fixture-branch",
            "model": smoke.MODEL_NAME,
            "started_at_utc": "2026-01-01T00:00:00Z",
        }

        gaps = smoke._narration_review_gaps(identity, rows)
        document = smoke._narration_review_document(
            identity,
            rows,
            status="finished",
            evidence_gaps=gaps,
        )

        self.assertIn("narration review turn evidence incomplete", gaps)
        self.assertFalse(document["run"]["evidence_complete"])


if __name__ == "__main__":
    unittest.main()
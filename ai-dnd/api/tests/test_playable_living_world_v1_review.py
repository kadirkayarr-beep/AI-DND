import copy
import json
from pathlib import Path
import tempfile
import unittest

from api.tests.live_playable_living_world_v1_smoke import (
    BUDGET_EXEMPT_TURN_IDS,
    EXPECTED_LABELS,
    _is_fallback_candidate,
    _proposal_trace_gaps,
)
from api.tests.live_playable_living_world_v1_1_smoke import (
    BUDGET_EXEMPT_TURN_IDS as BUDGET_EXEMPT_TURN_IDS_V11,
    EXPECTED_LABELS as EXPECTED_LABELS_V11,
    EXPECTED_PENDING_ERROR_V11,
    RESUME_AFTER_TURN as RESUME_AFTER_TURN_V11,
)
from api.tests.playable_living_world_v1_review import (
    ATTESTATION_FILENAME,
    EXPECTED_PENDING_ERROR,
    ReviewFinalizationError,
    finalize_review,
)


class PlayableLivingWorldReviewFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.reports_root = (
            Path(self.temp_dir.name)
            / "reports"
            / "playable-living-world-v1-smokes"
        )
        self.report_dir = self.reports_root / "1790000000000000000-1234abcd"
        self.report_dir.mkdir(parents=True)
        self.summary, self.turns, self.audit = self._valid_evidence()
        self.resume = {
            "campaign_id": "campaign-review-fixture",
            "old_session_id": "session-before-restart",
            "new_session_id": "session-after-restart",
            "equal_public_state": True,
            "equal_sanitized_state": True,
            "equal_state": True,
            "equal_lore": True,
            "equal_memory": True,
            "equal_history": True,
            "equal_combat_history": True,
            "sanitized_state_mismatch_paths": [],
        }
        self._write_report()

    def _state(self, turn):
        in_tavern = turn in {*range(8, 19), 23, 24, 36}
        return {
            "turn_index": turn,
            "location": "location_001" if in_tavern else "fr:city:neverwinter",
            "locations": [{
                "id": "location_001",
                "name": "The Silver Lantern",
                "parent_location_id": "fr:city:neverwinter",
            }],
            "npcs": [{
                "id": "npc_003",
                "name": "Aylin",
                "role": "Barmen",
                "location": "location_001",
            }],
            "features": [{
                "id": "feature_001",
                "name": "Brass bell",
                "location": "location_001",
            }],
            "shops": [],
            "scene": {"referents": []},
            "inventory": [],
            "currency": {"gold": 0},
        }

    def _valid_evidence(self):
        turns = []
        audit = []
        for index, label in enumerate(EXPECTED_LABELS, 1):
            before = self._state(index - 1)
            after = self._state(index)
            action_result = {
                "action": "conversation",
                "status": "completed",
                "success": True,
            }
            if label == "discover local tavern":
                action_result = {
                    "action": "local_search",
                    "status": "found",
                    "success": True,
                    "target_id": "location_001",
                }
            elif label == "enter discovered tavern":
                action_result = {
                    "action": "enter",
                    "status": "completed",
                    "success": True,
                    "target_id": "location_001",
                }
            elif label == "ask bartender name":
                action_result = {
                    "action": "query",
                    "status": "completed",
                    "success": True,
                    "npc_id": "npc_003",
                }
            elif label == "sit at presented table":
                action_result = {
                    "action": "sit",
                    "status": "completed",
                    "success": True,
                    "target_id": "feature_001",
                }
            elif label == "unsupported route challenge":
                action_result = {
                    "action": "travel",
                    "status": "unverified",
                    "success": False,
                }
            elif label == "return to tavern for final continuity check":
                action_result = {
                    "action": "enter",
                    "status": "completed",
                    "success": True,
                    "target_id": "location_001",
                }

            safety = {
                "tier": "tier_0_accept",
                "handling": "accepted",
                "reason_code": "SAFE_ACCEPT",
                "scope": "ordinary_play",
            }
            if label == "unsupported route challenge":
                safety = {
                    "tier": "tier_3_fallback",
                    "handling": "python_fallback",
                    "reason_code": "UNVERIFIED_LORE_CLAIM",
                    "scope": "lore_claim",
                }
            elif label == "supported perception investigation":
                safety = {
                    "tier": "tier_3_fallback",
                    "handling": "python_fallback",
                    "reason_code": "ORDINARY_FALLBACK",
                    "scope": "ordinary_play",
                }
            exempt = index in BUDGET_EXEMPT_TURN_IDS
            fallback_counted = (
                safety["tier"] == "tier_3_fallback"
                and safety["handling"] == "python_fallback"
                and not exempt
            )
            events = {
                "proposed": 0,
                "returned_by_validator": 0,
                "not_returned_by_validator": 0,
            }
            row = {
                "turn": index,
                "label": label,
                "request_telemetry_context_seen": True,
                "action_result_capture_seen": True,
                "action_result_source": "isolated_session_engine_telemetry",
                "resolved_action": action_result["action"],
                "action_result": action_result,
                "location_id": after["location"],
                "state_diff": {"before": before, "after": after},
                "created_ids": (
                    ["locations:location_001"]
                    if label == "discover local tavern" else []
                ),
                "proposal_decisions": [{
                    "kind": "proposal_summary",
                    "status": "validator_not_invoked",
                }],
                "proposal_validation_calls": 0,
                "proposal_validation_call_indices": [],
                "proposal_binding_calls": 0,
                "proposal_binding_call_indices": [],
                "proposal_trace_status": "validator_not_invoked",
                "proposal_category_counts": {
                    "locations": 0,
                    "npcs": 0,
                    "features": 0,
                    "shops": 0,
                    "update_npcs": 0,
                    "events": 0,
                },
                "events": events,
                "model_calls": 0,
                "observed_model_calls": 0,
                "model_call_count_matches": True,
                "safety": safety,
                "budget_exempt": exempt,
                "fallback_budget_counted": fallback_counted,
            }
            turns.append(row)
            audit.append({
                "turn_index": index,
                "model": "qwen3:8b",
                "model_calls": 0,
                "observed_model_calls": 0,
                "action_result": action_result,
                "safety": safety,
                "state": after,
                "request_telemetry_context_seen": True,
                "action_result_capture_seen": True,
                "session_id": "session-after-restart",
            })
        audit.insert(24, {
            "event": "resume",
            "campaign_id": "campaign-review-fixture",
            "session_id": "session-after-restart",
            "state": self._state(24),
        })
        summary = {
            "status": "REVIEW_PENDING",
            "review_status": "pending_human_review",
            "error": EXPECTED_PENDING_ERROR,
            "model": "qwen3:8b",
            "campaign_database": "temporary_disposable",
            "campaign_id": "campaign-review-fixture",
            "report_path": str(self.report_dir.resolve()),
            "evidence_incomplete": [],
            "budget_exempt_turn_ids": sorted(BUDGET_EXEMPT_TURN_IDS),
            "ordinary_fallback_candidate_count": 1,
            "restart_state_equal": True,
            "restart_lore_equal": True,
            "restart_memory_equal": True,
            "restart_history_equal": True,
            "restart_combat_history_equal": True,
            "turns": turns,
        }
        return summary, turns, audit

    def _write_report(self):
        self._write_json("summary.json", self.summary)
        self._write_json("resume-comparison.json", self.resume)
        self._write_jsonl("turn-evidence.jsonl", self.turns)
        self._write_jsonl("api-audit.jsonl", self.audit)
        if getattr(self, "narration_review", None) is not None:
            self._write_json("narration-review.json", self.narration_review)

    def _write_json(self, filename, value):
        (self.report_dir / filename).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _write_jsonl(self, filename, rows):
        (self.report_dir / filename).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def _finalize(self, approve=False):
        return finalize_review(
            self.report_dir,
            approve=approve,
            reports_root=self.reports_root,
            expected_labels=EXPECTED_LABELS,
            budget_exempt_turn_ids=BUDGET_EXEMPT_TURN_IDS,
            proposal_trace_validator=_proposal_trace_gaps,
        )

    def test_valid_36_turn_report_with_explicit_approval_passes(self):
        approved = self._finalize(approve=True)
        self.assertEqual(approved["execution_status"], "COMPLETE")
        self.assertEqual(approved["manual_review_status"], "APPROVED")
        self.assertEqual(approved["final_gate_status"], "PASS")
        self.assertTrue((self.report_dir / ATTESTATION_FILENAME).is_file())
        attestation = json.loads(
            (self.report_dir / ATTESTATION_FILENAME).read_text(encoding="utf-8")
        )
        self.assertTrue(attestation["reviewer_approved"])
        self.assertEqual(attestation["reviewed_turn_count"], 36)

    def test_no_approval_flag_remains_pending(self):
        pending = self._finalize()
        self.assertEqual(pending["objective_validation_result"], "PASS")
        self.assertEqual(pending["manual_review_status"], "PENDING")
        self.assertEqual(pending["final_gate_status"], "REVIEW_PENDING")
        self.assertIsNone(pending["attestation_path"])
        self.assertFalse((self.report_dir / ATTESTATION_FILENAME).exists())

    def test_missing_turn_is_rejected(self):
        self.summary["turns"].pop()
        self.turns.pop()
        self.audit = [
            row for row in self.audit if row.get("turn_index") != 36
        ]
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)

    def test_evidence_gap_is_rejected(self):
        self.summary["evidence_incomplete"] = ["missing sanitized trace"]
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)

    def test_failed_resume_comparison_is_rejected(self):
        self.resume["equal_memory"] = False
        self.summary["restart_memory_equal"] = False
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)

    def test_excess_ordinary_fallbacks_are_rejected(self):
        for turn_number in (2, 4):
            row = self.turns[turn_number - 1]
            row["safety"] = {
                "tier": "tier_2_repair",
                "handling": "repaired",
                "reason_code": "REPAIR",
                "scope": "ordinary_play",
            }
            row["fallback_budget_counted"] = True
            self.audit[turn_number - 1]["safety"] = row["safety"]
        self.summary["ordinary_fallback_candidate_count"] = 3
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)

    def test_wrong_model_is_rejected(self):
        self.summary["model"] = "different-model"
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)

    def test_failed_route_guard_is_rejected(self):
        route = self.turns[31]
        route["safety"]["reason_code"] = "ACCEPTED"
        route["action_result"]["status"] = "completed"
        route["action_result"]["success"] = True
        self.audit[31]["safety"] = route["safety"]
        self.audit[31]["action_result"] = route["action_result"]
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)

    def test_broken_final_tavern_identity_is_rejected(self):
        final_turn = self.turns[35]
        final_state = final_turn["state_diff"]["after"]
        final_state["npcs"] = []
        self.audit[35]["state"] = copy.deepcopy(final_state)
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)

    def test_source_tampering_after_approval_is_rejected(self):
        self._finalize(approve=True)
        self.summary["non_narrative_metadata"] = "changed after approval"
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)

    def test_duplicate_approval_is_idempotent(self):
        first = self._finalize(approve=True)
        path = self.report_dir / ATTESTATION_FILENAME
        initial_bytes = path.read_bytes()
        second = self._finalize(approve=True)
        self.assertEqual(first, second)
        self.assertEqual(path.read_bytes(), initial_bytes)

    def test_approval_attestation_does_not_copy_raw_or_private_text(self):
        self.summary["player_input"] = "RAW_PLAYER_SENTINEL"
        self.summary["turns"][0]["narration"] = "RAW_NARRATION_SENTINEL"
        self.summary["private_text"] = "PRIVATE_TEXT_SENTINEL"
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            self._finalize(approve=True)
        attestation = self.report_dir / ATTESTATION_FILENAME
        self.assertFalse(attestation.exists())

    def test_v11_30_turn_report_is_reviewable_without_changing_v1_attestation(self):
        original_by_label = {row["label"]: row for row in self.turns}
        audit_by_turn = {
            row["turn_index"]: row
            for row in self.audit
            if "turn_index" in row
        }
        route = original_by_label["unsupported route challenge"]
        final_return = original_by_label[
            "return to tavern for final continuity check"
        ]
        selected_sources = []
        generic_source = original_by_label["city look"]
        required_labels = {
            "discover local tavern",
            "enter discovered tavern",
            "ask bartender name",
            "tavern look",
            "sit at presented table",
            "unsupported route challenge",
            "return to tavern for final continuity check",
        }
        for index, label in enumerate(EXPECTED_LABELS_V11, 1):
            if label in required_labels:
                source = original_by_label[label]
            elif label == "unsupported route challenge":
                source = route
            elif label == "return to tavern for final continuity check":
                source = final_return
            else:
                source = generic_source
            row = copy.deepcopy(source)
            row["turn"] = index
            row["label"] = label
            exempt = index in BUDGET_EXEMPT_TURN_IDS_V11
            safety = row["safety"]
            fallback = (
                safety.get("tier") == "tier_2_repair"
                or (
                    safety.get("tier") == "tier_3_fallback"
                    and safety.get("handling")
                    not in {"python_scene_response", "python_memory_response"}
                )
            )
            row["budget_exempt"] = exempt
            row["fallback_budget_counted"] = fallback and not exempt
            selected_sources.append(row)

        resume_turn = RESUME_AFTER_TURN_V11
        selected_audit = []
        for index, turn in enumerate(selected_sources, 1):
            old_turn = original_by_label.get(turn["label"], generic_source)
            source_audit = audit_by_turn.get(old_turn["turn"], audit_by_turn[1])
            audit_row = copy.deepcopy(source_audit)
            audit_row["turn_index"] = index
            audit_row["action_result"] = turn["action_result"]
            audit_row["safety"] = turn["safety"]
            audit_row["state"] = turn["state_diff"]["after"]
            selected_audit.append(audit_row)
        resume_event = {
            "event": "resume",
            "campaign_id": "campaign-review-fixture",
            "session_id": "session-after-restart",
            "state": selected_sources[resume_turn - 1]["state_diff"]["after"],
        }
        selected_audit.append(resume_event)

        self.report_dir = (
            Path(self.temp_dir.name)
            / "reports"
            / "playable-living-world-v1-1-smokes"
            / "1790000000000000000-5678abcd"
        )
        self.report_dir.mkdir(parents=True)
        self.narration_review = None
        self.turns = selected_sources
        self.audit = selected_audit
        self.summary["status"] = "REVIEW_PENDING"
        self.summary["review_status"] = "pending_human_review"
        self.summary["error"] = EXPECTED_PENDING_ERROR_V11
        self.summary["report_path"] = str(self.report_dir.resolve())
        self.summary["budget_exempt_turn_ids"] = sorted(
            BUDGET_EXEMPT_TURN_IDS_V11
        )
        self.summary["ordinary_fallback_candidate_count"] = sum(
            row["fallback_budget_counted"] for row in selected_sources
        )
        self.summary["resume_after_turn"] = resume_turn
        self.summary["turns"] = selected_sources
        self.resume["resume_after_turn"] = resume_turn
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            finalize_review(
                self.report_dir,
                approve=True,
                reports_root=self.report_dir.parent,
                expected_labels=EXPECTED_LABELS_V11,
                budget_exempt_turn_ids=BUDGET_EXEMPT_TURN_IDS_V11,
                proposal_trace_validator=_proposal_trace_gaps,
                expected_pending_error=EXPECTED_PENDING_ERROR_V11,
                narration_review_required=True,
            )

        narration_review_turns = []
        for index, turn in enumerate(selected_sources, 1):
            action_result = turn["action_result"]
            engine_telemetry = {
                "intent_model_calls": 0,
                "narration_model_calls": 0,
                "total_model_calls": 0,
                "intent_source": "fixture",
                "narration_source": "qwen",
                "fallback_reason": None,
                "narration_validation_result": "accepted",
                "resolved_action_type": action_result["action"],
            }
            audit_row = next(
                row for row in selected_audit
                if row.get("turn_index") == index
            )
            audit_row["narration_telemetry_capture_seen"] = True
            audit_row["narration_telemetry"] = engine_telemetry
            narration_review_turns.append({
                "turn": index,
                "label": turn["label"],
                "player_input": f"fixture player input {index}",
                "narration": f"fixture narration {index}",
                "model": "qwen3:8b",
                "action": action_result["action"],
                "request_target_id": turn.get("target_id"),
                "action_target_id": action_result.get("target_id"),
                "intent_model_calls": 0,
                "narration_model_calls": 0,
                "total_model_calls": 0,
                "model_calls": turn["model_calls"],
                "observed_model_calls": turn["observed_model_calls"],
                "intent_source": "fixture",
                "narration_source": "qwen",
                "fallback_reason": None,
                "narration_validation_result": "accepted",
                "resolved_action_type": action_result["action"],
                "engine_telemetry": engine_telemetry,
                "safety": turn["safety"],
                "evidence_complete": True,
            })
        self.summary["narration_review_evidence"] = {
            "file": "narration-review.json",
            "expected_turn_count": len(EXPECTED_LABELS_V11),
            "recorded_turn_count": len(narration_review_turns),
            "evidence_complete": True,
        }
        self.narration_review = {
            "schema_version": 1,
            "run": {
                "report_id": self.report_dir.name,
                "git_sha": "fixture-sha",
                "git_branch": "fixture-branch",
                "model": "qwen3:8b",
                "started_at_utc": "2026-01-01T00:00:00Z",
                "status": "finished",
                "expected_turn_count": len(EXPECTED_LABELS_V11),
                "recorded_turn_count": len(narration_review_turns),
                "model_calls_reported": 0,
                "model_calls_observed": 0,
                "fallback_turn_count": sum(
                    _is_fallback_candidate(row["safety"])
                    for row in selected_sources
                ),
                "evidence_complete": True,
                "evidence_gaps": [],
            },
            "turns": narration_review_turns,
        }
        self.narration_review["run"]["evidence_complete"] = False
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            finalize_review(
                self.report_dir,
                approve=True,
                reports_root=self.report_dir.parent,
                expected_labels=EXPECTED_LABELS_V11,
                budget_exempt_turn_ids=BUDGET_EXEMPT_TURN_IDS_V11,
                proposal_trace_validator=_proposal_trace_gaps,
                expected_pending_error=EXPECTED_PENDING_ERROR_V11,
                narration_review_required=True,
            )
        self.narration_review["run"]["evidence_complete"] = True
        self._write_report()

        approved = finalize_review(
            self.report_dir,
            approve=True,
            reports_root=self.report_dir.parent,
            expected_labels=EXPECTED_LABELS_V11,
            budget_exempt_turn_ids=BUDGET_EXEMPT_TURN_IDS_V11,
            proposal_trace_validator=_proposal_trace_gaps,
            expected_pending_error=EXPECTED_PENDING_ERROR_V11,
            narration_review_required=True,
        )
        self.assertEqual(approved["manual_review_status"], "APPROVED")
        self.assertEqual(approved["final_gate_status"], "PASS")
        attestation = json.loads(
            (self.report_dir / ATTESTATION_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(attestation["reviewed_turn_count"], 30)
        self.narration_review["turns"][0]["player_input"] += " changed"
        self._write_report()
        with self.assertRaises(ReviewFinalizationError):
            finalize_review(
                self.report_dir,
                approve=True,
                reports_root=self.report_dir.parent,
                expected_labels=EXPECTED_LABELS_V11,
                budget_exempt_turn_ids=BUDGET_EXEMPT_TURN_IDS_V11,
                proposal_trace_validator=_proposal_trace_gaps,
                expected_pending_error=EXPECTED_PENDING_ERROR_V11,
                narration_review_required=True,
            )


if __name__ == "__main__":
    unittest.main()
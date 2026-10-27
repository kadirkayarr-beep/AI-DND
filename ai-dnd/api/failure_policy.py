"""Phase-based failure policy (R06): how the API answers a failure is decided by the phase the action had reached.

The phase says what is certain. Unresolved or rolled back before any durable write: nothing happened. A durable commit
whose acknowledgement was lost: the outcome is unknown until the receipt is reconciled. A committed result: it is kept
and never recomputed. A phase that cannot be named is `outcome_unknown`, never a guessed success.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from api.persistence.campaign_models import CampaignStaleError, CampaignStorageError


class ActionPhase(str, Enum):
    UNRESOLVED = "unresolved"
    RESOLVED_UNCOMMITTED = "resolved_uncommitted"
    COMMIT_UNKNOWN = "commit_unknown"
    COMMITTED_NARRATION = "committed_narration"
    NPC_SPEECH = "npc_speech"
    RECONCILIATION = "reconciliation"


@dataclass(frozen=True)
class RecoveryDecision:
    code: str
    status_code: int
    outcome: str  # not_applied | rolled_back | outcome_unknown | committed
    message: str
    retry_safe: bool = True
    same_id_required: bool = True
    reconcile_receipt_first: bool = False
    emit_event: bool = False
    keep_committed_result: bool = False
    narration_fallback: bool = False
    rerun_mechanics: bool = False
    persist_speech: bool = False
    not_applied: bool | None = None  # True only when the failure is certain AND recorded as a refusal

    def detail(self, **extra: Any) -> dict[str, Any]:
        detail: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.not_applied is True:
            detail["not_applied"] = True
        detail.update(extra)
        return detail


QUARANTINE_MESSAGE = "Oturum güvenli biçimde geri alınamadı ve kapatıldı."
_MODEL_DOWN_NAMES = {"OllamaUnavailableError", "RequiredModelUnavailableError"}


def classify_failure(phase: Any, commit_status: str, cause: BaseException) -> RecoveryDecision:
    """Map (phase, commit status, cause) to the one safe answer. Unknown phases are outcome_unknown."""
    if not isinstance(phase, ActionPhase):
        return RecoveryDecision(
            code="outcome_unknown", status_code=500, outcome="outcome_unknown",
            message="The result of this action could not be determined. Retry with the same action ID.",
        )
    if phase is ActionPhase.UNRESOLVED:
        if type(cause).__name__ in _MODEL_DOWN_NAMES:
            return RecoveryDecision("ollama_unavailable", 503, "not_applied",
                                    "The language model is unavailable.", not_applied=True)
        return RecoveryDecision("engine_error", 500, "not_applied",
                                "The game turn could not be completed.", not_applied=True)
    if phase is ActionPhase.NPC_SPEECH:
        return RecoveryDecision("invalid_dialogue_response", 503, "not_applied",
                                "The spoken reply could not be produced; nothing was saved.", not_applied=True)
    if phase is ActionPhase.RESOLVED_UNCOMMITTED:
        if commit_status == "quarantined":
            return RecoveryDecision("session_restore_failed", 409, "rolled_back", QUARANTINE_MESSAGE,
                                    retry_safe=False, same_id_required=False)
        if isinstance(cause, CampaignStaleError):
            return RecoveryDecision("campaign_stale", 409, "rolled_back", str(cause))
        if isinstance(cause, CampaignStorageError):
            return RecoveryDecision("campaign_storage_unavailable", 503, "rolled_back",
                                    "Macera kaydı şu anda güvenli biçimde saklanamıyor.")
        return RecoveryDecision("persistence_error", 500, "rolled_back", "The campaign turn could not be saved safely.")
    if phase is ActionPhase.COMMIT_UNKNOWN:
        return RecoveryDecision(
            "persistence_error", 503, "outcome_unknown",
            "The turn was saved but its confirmation was lost. Retry with the same action ID to receive the saved result.",
            reconcile_receipt_first=True,
        )
    if phase is ActionPhase.COMMITTED_NARRATION:
        return RecoveryDecision("narration_fallback", 200, "committed", "The committed result is shown with fallback narration.",
                                retry_safe=False, same_id_required=False, emit_event=True,
                                keep_committed_result=True, narration_fallback=True)
    # RECONCILIATION: the durable record could not be read back; the receipt stays the authority.
    return RecoveryDecision("reconciliation_failed", 503, "outcome_unknown",
                            "The saved result could not be confirmed yet. Retry with the same action ID.",
                            reconcile_receipt_first=True)

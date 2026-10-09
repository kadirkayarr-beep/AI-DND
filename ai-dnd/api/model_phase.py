"""Request-local evidence for the engine's resolved, read-only narrator boundary."""
from contextlib import contextmanager
from contextvars import ContextVar

_PHASE = ContextVar("resolved_model_phase", default="unresolved")


class ModelFailure(str):
    def __new__(cls, error_type):
        value = super().__new__(cls, error_type)
        value.phase = _PHASE.get()
        return value


@contextmanager
def resolved_narration_scope(enabled):
    token = _PHASE.set("resolved_narration" if enabled else "unresolved")
    try:
        yield
    finally:
        _PHASE.reset(token)


def only_resolved_narration_failures(failures):
    return bool(failures) and all(
        isinstance(failure, ModelFailure) and failure.phase == "resolved_narration"
        for failure in failures
    )

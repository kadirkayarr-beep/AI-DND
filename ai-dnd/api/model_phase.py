"""Request-local evidence for the engine's resolved, read-only narrator boundary."""
from contextlib import contextmanager
from contextvars import ContextVar

_PHASE = ContextVar("resolved_model_phase", default="unresolved")
_CLASSIFIER = ContextVar("classifier_model_call", default=False)
_FRONT = ContextVar("front_model_call", default=False)
_CAUSES = ContextVar("unusable_call_causes", default=None)
MAX_CAUSES = 10


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


@contextmanager
def classifier_call():
    """The engine answers a failed intent classifier with its own unknown intent."""
    token = _CLASSIFIER.set(True)
    try:
        yield
    finally:
        _CLASSIFIER.reset(token)


def in_classifier_call():
    return _CLASSIFIER.get()


@contextmanager
def front_call():
    """The front reading is optional: a failure leaves the old chain, on any provider."""
    token = _FRONT.set(True)
    try:
        yield
    finally:
        _FRONT.reset(token)


def in_front_call():
    return _FRONT.get()


def only_resolved_narration_failures(failures):
    return bool(failures) and all(
        isinstance(failure, ModelFailure) and failure.phase == "resolved_narration"
        for failure in failures
    )


def begin_causes():
    """A new turn's list of why a model call came back unusable. Names only, never text from the player or the model."""
    _CAUSES.set([])


def note_cause(source, cause):
    """One line: which kind of call (front or other), who answered, and which check failed."""
    rows = _CAUSES.get()
    if rows is not None and len(rows) < MAX_CAUSES:
        rows.append(f"{'front' if in_front_call() else 'call'}:{source}:{cause}")


def causes():
    return list(_CAUSES.get() or [])

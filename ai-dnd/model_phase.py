"""Request-local evidence for the engine's resolved, read-only narrator boundary."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from logging import Logger

_PHASE = ContextVar("resolved_model_phase", default="unresolved")
_CLASSIFIER = ContextVar("classifier_model_call", default=False)
_FRONT = ContextVar("front_model_call", default=False)
_INITIATIVE = ContextVar("initiative_model_call", default=False)
_REPAIR = ContextVar("repair_model_call", default=False)
_CAUSES = ContextVar("unusable_call_causes", default=None)
MAX_CAUSES = 10
# What a model call raises when the model is out: the adapter wraps every provider error in RuntimeError; a timeout or a
# dead socket may arrive bare. Any other type at a fallback is a bug in our code, not an outage.
MODEL_OUTAGE = (RuntimeError, TimeoutError, OSError)
# ... except these subtypes, which come from our own code (a stub, a runaway recursion, a missing or locked file).
NOT_OUTAGE = (NotImplementedError, RecursionError, FileNotFoundError, PermissionError)


class ModelFailure(str):
    def __new__(cls, error_type: str):
        value = super().__new__(cls, error_type)
        value.phase = _PHASE.get()
        return value


@contextmanager
def resolved_narration_scope(enabled: bool) -> Iterator[None]:
    token = _PHASE.set("resolved_narration" if enabled else "unresolved")
    try:
        yield
    finally:
        _PHASE.reset(token)


@contextmanager
def classifier_call() -> Iterator[None]:
    """The engine answers a failed intent classifier with its own unknown intent."""
    token = _CLASSIFIER.set(True)
    try:
        yield
    finally:
        _CLASSIFIER.reset(token)


def in_classifier_call() -> bool:
    return _CLASSIFIER.get()


@contextmanager
def front_call() -> Iterator[None]:
    """The front reading: an unusable reply leaves the old chain, on any provider; an outage refuses the turn (G6)."""
    token = _FRONT.set(True)
    try:
        yield
    finally:
        _FRONT.reset(token)


def in_front_call() -> bool:
    return _FRONT.get()


@contextmanager
def initiative_call() -> Iterator[None]:
    """An NPC's optional initiative: it may use the call a front reading took from the turn's budget."""
    token = _INITIATIVE.set(True)
    try:
        yield
    finally:
        _INITIATIVE.reset(token)


def in_initiative_call() -> bool:
    return _INITIATIVE.get()


@contextmanager
def repair_call() -> Iterator[None]:
    """The one repair of an answer a safety check rejected: it may pass the per-turn cap once (D-332)."""
    token = _REPAIR.set(True)
    try:
        yield
    finally:
        _REPAIR.reset(token)


def in_repair_call() -> bool:
    return _REPAIR.get()


class ModelCall(str):
    """One counted call's provider name, marked with whether it was the front reading, an initiative or a repair."""
    third: bool = False  # set by the adapter: the call took the turn's third call (D-419)

    def __new__(cls, provider: str):
        value = super().__new__(cls, provider)
        value.front = _FRONT.get()
        value.initiative = _INITIATIVE.get()
        value.repair = _REPAIR.get()
        return value


def only_resolved_narration_failures(failures: list | tuple | None) -> bool:
    return bool(failures) and all(
        isinstance(failure, ModelFailure) and failure.phase == "resolved_narration"
        for failure in failures
    )


def begin_causes() -> None:
    """A new turn's list of why a model call came back unusable. Names only, never text from the player or the model."""
    _CAUSES.set([])


def note_cause(source: str, cause: str) -> None:
    """One line: which kind of call (front or other), who answered, and which check failed."""
    rows = _CAUSES.get()
    if rows is not None and len(rows) < MAX_CAUSES:
        rows.append(f"{'front' if in_front_call() else 'call'}:{source}:{cause}")


def causes() -> list[str]:
    return list(_CAUSES.get() or [])


def log_fallback(logger: Logger, error: BaseException, what: str) -> None:
    """A broad model-call catch fell back to Python text: an outage is DEBUG (the adapter already counted it), a bug WARNING."""
    if isinstance(error, MODEL_OUTAGE) and not isinstance(error, NOT_OUTAGE):
        logger.debug("%s fell back after a model outage (error_type=%s)", what, type(error).__name__)
    else:
        logger.warning("%s fell back after an unexpected error (error_type=%s)", what, type(error).__name__, exc_info=error)

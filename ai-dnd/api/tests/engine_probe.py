"""N4 probe: which engine patches fired in which test, and how every test ended (game.py split, Plan 2 Task 2).

`install_ledger(out_dir)` wraps `unittest.TestCase.run` and `unittest.mock._patch.__enter__/__exit__` and writes one
JSON line per record to `out_dir/ledger-<pid>.jsonl`:
    {"test": id, "outcome": "ok|fail|error|skip|xfail|xpass"}           after every TestCase.run
    {"test": id, "target": attribute, "kind": "mock|other", "called": bool|None}   at the __exit__ of a patch on `game`
Installs stack: each install wraps the three functions as they are at that moment (possibly an outer install's
wrappers), so an outer ledger keeps recording through an inner one; `uninstall` pops the top install only.
Blind spots (N3 is their only guard): tests that patch without calling, plain `game.X = ...` assignments, kind "other".
It never imports the engine (`game`, `game_parts`).
"""
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_STACK = []
_OUTCOME_LISTS = (("errors", "error"), ("failures", "fail"), ("unexpectedSuccesses", "xpass"),
                  ("expectedFailures", "xfail"), ("skipped", "skip"))


def _is_game(obj) -> bool:
    return isinstance(obj, types.ModuleType) and obj.__name__ == "game"


def _counts(result):
    return [len(getattr(result, name, ())) for name, _ in _OUTCOME_LISTS]


def _outcome(before, result):
    for (_, outcome), old, new in zip(_OUTCOME_LISTS, before, _counts(result)):
        if new > old:
            return outcome
    return "ok"


def _outside_test() -> str:
    frame = sys._getframe(1)
    skip = (Path(__file__).resolve(), Path(mock.__file__).resolve().parent)
    while frame is not None:
        path = Path(frame.f_code.co_filename).resolve()
        if path != skip[0] and skip[1] not in path.parents and path.name != "contextlib.py":
            return f"<outside-test>:{path.name}"
        frame = frame.f_back
    return "<outside-test>:?"


def install_ledger(out_dir: Path, is_target=_is_game) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_run, saved_enter, saved_exit = unittest.TestCase.run, mock._patch.__enter__, mock._patch.__exit__
    tests, pending, sink = [], {}, {}

    def write(record):
        if sink.get("closed"):                  # a wrapper still on the call stack after its uninstall
            return
        if sink.get("pid") != os.getpid():      # one file per process: a forked child opens its own
            sink["pid"] = os.getpid()
            sink["file"] = open(out_dir / f"ledger-{os.getpid()}.jsonl", "a", buffering=1, encoding="utf-8")
        sink["file"].write(json.dumps(record) + "\n")

    def run(self, result=None):
        before = _counts(result)
        tests.append(self.id())
        try:
            result = saved_run(self, result)
        finally:
            tests.pop()
        write({"test": self.id(), "outcome": _outcome(before, result)})
        return result

    def enter(self):
        entered = saved_enter(self)
        if is_target(self.target):
            test = tests[-1] if tests else _outside_test()
            pending[id(self)] = (test, self.attribute, entered)
        return entered

    def exit_(self, *exc_info):
        entry = pending.pop(id(self), None)
        if entry is not None:
            test, attribute, entered = entry
            if hasattr(entered, "called"):
                write({"test": test, "target": attribute, "kind": "mock", "called": bool(entered.called)})
            else:
                write({"test": test, "target": attribute, "kind": "other", "called": None})
        return saved_exit(self, *exc_info)

    _STACK.append((saved_run, saved_enter, saved_exit, sink))
    unittest.TestCase.run, mock._patch.__enter__, mock._patch.__exit__ = run, enter, exit_


def uninstall() -> None:
    if not _STACK:
        raise RuntimeError("engine_probe.uninstall: no ledger is installed")
    saved_run, saved_enter, saved_exit, sink = _STACK.pop()
    unittest.TestCase.run, mock._patch.__enter__, mock._patch.__exit__ = saved_run, saved_enter, saved_exit
    sink["closed"] = True
    if "file" in sink:
        sink["file"].close()

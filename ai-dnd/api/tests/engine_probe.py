"""N4 probe: which engine patches fired in which test, and how every test ended (game.py split, Plan 2 Task 2).

`install_ledger(out_dir)` wraps `unittest.TestCase.run` and `unittest.mock._patch.__enter__/__exit__` and writes one
JSON line per record to `out_dir/ledger-<pid>.jsonl`:
    {"test": id, "outcome": "ok|fail|error|skip|xfail|xpass"}           after every TestCase.run
        (+ "subtests": [sorted ids of its failed or errored subtests], only when there are any)
    {"test": id, "target": attribute, "kind": "mock|other", "called": bool|None}   at the __exit__ of a patch on `game`
Installs stack: each install wraps the three functions as they are at that moment (possibly an outer install's
wrappers), so an outer ledger keeps recording through an inner one; `uninstall` pops the top install only.
Blind spots (N3 is their only guard): tests that patch without calling, plain `game.X = ...` assignments, kind "other".
N7 probe (Task 3): `install_lines(out_dir, engine_files, tool_id)` records which lines of the engine files ran, over
`sys.monitoring` (each line once, then DISABLE), and an `atexit` writer stores them in `out_dir/lines-<pid>.json` as
{"<posix path relative to ai-dnd>": [sorted lines]}. State is kept per tool id: a self-test probe on a free id does not
touch the gate's probe on COVERAGE_ID. `stop_lines(tool_id)` frees that id only and unregisters its writer.
It never imports the engine (`game`, `game_parts`).
"""
import atexit
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_STACK = []
_LINES = {}             # tool id -> (code objects with local LINE events, {(file, line)}, atexit writer)
_N7 = "engine-split-n7"
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


def _failed_subtests(before, result, test) -> list[str]:
    new = [*result.errors[before[0]:], *result.failures[before[1]:]]        # _OUTCOME_LISTS order: errors, failures
    return sorted({case.id() for case, _ in new if case is not test})


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
        record = {"test": self.id(), "outcome": _outcome(before, result)}
        subtests = _failed_subtests(before, result, self)
        if subtests:
            record["subtests"] = subtests
        write(record)
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


def install_lines(out_dir: Path, engine_files: list[Path], tool_id: int = sys.monitoring.COVERAGE_ID) -> None:
    held = sys.monitoring.get_tool(tool_id)
    if held == _N7:
        raise RuntimeError(f"{_N7} already installed")
    if held is not None:
        raise RuntimeError(f"{_N7}: tool id {tool_id} is held by {held!r}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    root = Path(engine_files[0]).resolve().parent           # game.py's folder: ai-dnd
    wanted = {str(Path(f).resolve()): Path(f).resolve().relative_to(root).as_posix() for f in engine_files}
    keys, codes, hits = {}, [], set()
    events = sys.monitoring.events

    def start(code, offset):
        filename = code.co_filename
        if filename not in keys:
            keys[filename] = wanted.get(str(Path(filename).resolve()))
        if keys[filename] is not None:
            sys.monitoring.set_local_events(tool_id, code, events.LINE)
            codes.append(code)
        return sys.monitoring.DISABLE

    def line(code, line_number):
        hits.add((keys[code.co_filename], line_number))
        return sys.monitoring.DISABLE

    def write():
        (out_dir / f"lines-{os.getpid()}.json").write_text(json.dumps(_by_file(hits), sort_keys=True), encoding="utf-8")

    sys.monitoring.use_tool_id(tool_id, _N7)
    sys.monitoring.register_callback(tool_id, events.PY_START, start)
    sys.monitoring.register_callback(tool_id, events.LINE, line)
    sys.monitoring.set_events(tool_id, events.PY_START)
    atexit.register(write)
    _LINES[tool_id] = (codes, hits, write)


def stop_lines(tool_id: int = sys.monitoring.COVERAGE_ID) -> dict[str, list[int]]:
    if tool_id not in _LINES:           # never frees an id this module does not hold
        return {}
    codes, hits, write = _LINES.pop(tool_id)
    atexit.unregister(write)
    events = sys.monitoring.events
    sys.monitoring.set_events(tool_id, events.NO_EVENTS)
    for code in codes:
        sys.monitoring.set_local_events(tool_id, code, events.NO_EVENTS)
    sys.monitoring.register_callback(tool_id, events.PY_START, None)
    sys.monitoring.register_callback(tool_id, events.LINE, None)
    sys.monitoring.free_tool_id(tool_id)
    return _by_file(hits)


def _by_file(hits) -> dict[str, list[int]]:
    out = {}
    for name, line_number in hits:
        out.setdefault(name, []).append(line_number)
    return {name: sorted(lines) for name, lines in out.items()}

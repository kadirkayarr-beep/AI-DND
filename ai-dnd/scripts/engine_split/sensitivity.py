"""N8 sensitivity scan: which top-level functions of game.py touch money, save files, snapshots or file writes.

Reasons come from the function's content, never from its name or target module. A name in the lock moves only under
strongest-model review; it leaves `functions` only through a `removed` row written by that reviewer.
Usage (from ai-dnd/):
    python scripts/engine_split/sensitivity.py --write   # rewrite the lock (keeps existing `removed` rows)
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if __name__ == "__main__":
    sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from engine_split.inventory import top_level_index  # noqa: E402

GAME_PATH = ROOT / "game.py"
LOCK_PATH = ROOT / "api" / "tests" / "engine_split_locks" / "sensitive.json"

# Measured in game.py (Task 4 step 1): the Undo pair on GameSession and the save/load/serialise functions.
SNAPSHOT_NAMES = {"_capture_runtime_snapshot", "_restore_runtime_snapshot"}
SAVE_NAMES = {"save_game", "load_game", "serialize_game_state", "_player_state_for_save"}
MONEY = re.compile(r"currency|coin|gold|money_owner|pay\(")  # spec section 5; matches source text, comments included
WRITE_ATTRS = {"write_text", "write_bytes"}
WRITE_MODE = re.compile(r"[wax+]")


def _called_name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _owner(call: ast.Call) -> str:
    func = call.func
    return func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else ""


def _opens_for_write(call: ast.Call) -> bool:
    mode = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "mode"), None)
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and bool(WRITE_MODE.search(mode.value))


def _call_reasons(call: ast.Call) -> set[str]:
    name, owner = _called_name(call), _owner(call)
    reasons = set()
    if name in SNAPSHOT_NAMES:
        reasons.add("snapshot")
    if name in SAVE_NAMES:
        reasons.add("save")
    if (name == "open" and _opens_for_write(call)) or name in WRITE_ATTRS or owner == "tempfile" \
            or (owner, name) in {("os", "replace"), ("json", "dump")}:
        reasons.add("file_write")
    return reasons


def classify(path: Path) -> dict[str, list[str]]:
    """Top-level function -> sorted reasons (snapshot, save, file_write, money); functions with no reason are absent."""
    source = Path(path).read_text(encoding="utf-8")
    lines = source.splitlines()
    functions = {n.name: n for n in ast.parse(source, filename=str(path)).body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    out: dict[str, list[str]] = {}
    for entry in top_level_index(path):
        if entry["kind"] != "function":
            continue
        reasons = set()
        if MONEY.search("\n".join(lines[entry["def_line"] - 1:entry["end"]])):
            reasons.add("money")
        for node in ast.walk(functions[entry["name"]]):
            if isinstance(node, ast.Call):
                reasons |= _call_reasons(node)
        if reasons:
            out[entry["name"]] = sorted(reasons)
    return out


def is_sensitive(name: str, lock: dict) -> bool:
    return name in lock["functions"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--game", default=str(GAME_PATH))
    ap.add_argument("--lock", default=str(LOCK_PATH))  # the slot's tree is a copy: point these at the worktree
    args = ap.parse_args(argv)
    lock_path = Path(args.lock)
    removed = json.loads(lock_path.read_text(encoding="utf-8"))["removed"] if lock_path.exists() else []
    gone = {row["name"] for row in removed}
    found = classify(Path(args.game))
    functions = {name: reasons for name, reasons in sorted(found.items()) if name not in gone}
    if args.write:
        lock_path.write_text(json.dumps({"functions": functions, "removed": removed}, indent=2) + "\n", encoding="utf-8")
    print(f"flagged={len(found)} functions={len(functions)} removed={len(removed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

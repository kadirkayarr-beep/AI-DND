"""size_lock.json and the engine size_budget.json (D-553) may only shrink versus a base ref (Quality gate, Task 9).

Kept out of ratchet.py on purpose: ratchet.py is itself under the size lock.
Usage: python -m scripts.quality_gate.size_lock_shrink scripts/quality_gate/size_lock.json origin/main
Exit 0 = no growth (or the file is new at the base), 1 = growth, 2 = unusable input or git failure.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 - subprocess with fixed argv lists only, no shell
import sys
from pathlib import Path

_LOCK_TABLES = ("files", "ts_files", "long_functions")
_REQUIRED_TABLES = ("files", "long_functions")  # the engine size budget has no ts_files


def _check_table(data: dict, name: str) -> None:
    table = data.get(name)
    if not isinstance(table, dict) or any(type(v) is not int or v < 0 for v in table.values()):
        raise ValueError(f"size lock table {name} is not a map of non-negative integers")


def _size_lock(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("size lock is not a JSON object")
    for k in ("part_max", "slack", "long_function_min"):
        if type(data.get(k)) is not int:
            raise ValueError(f"size lock {k} is not an integer")
    for t in _LOCK_TABLES:
        if t in data or t in _REQUIRED_TABLES:
            _check_table(data, t)
    return data


def size_lock_growth(old: dict, new: dict) -> list[str]:
    """Ways `new` is looser than `old`: a raised budget, a new long function, a new file entry above part_max, a looser limit,
    or a dropped file entry whose budget was at or below part_max (that entry was the file's only cap below part_max)."""
    out = []
    for k in ("part_max", "slack"):
        if new[k] > old[k]:
            out.append(f"{k} raised from {old[k]} to {new[k]}")
    if new["long_function_min"] < old["long_function_min"]:
        out.append(f"long_function_min lowered from {old['long_function_min']} to {new['long_function_min']}")
    for t in _LOCK_TABLES:
        new_t, old_t = new.get(t, {}), old.get(t, {})
        for name, v in sorted(new_t.items()):
            if name in old_t:
                if v > old_t[name]:
                    out.append(f"{t}: {name} raised from {old_t[name]} to {v}")
            elif t == "long_functions" or v > new["part_max"]:
                out.append(f"{t}: {name} is a new entry ({v})")
        if t != "long_functions":
            for name, v in sorted(old_t.items()):
                if name not in new_t and v <= old["part_max"]:
                    out.append(f"{t}: {name} entry removed but its budget {v} was within part_max; a file above part_max loses its entry only by shrinking")
    return out


def check_size_lock_shrink(path: Path, ref: str) -> int:
    """size_lock.json: budgets may only shrink versus `ref`."""
    try:
        new = _size_lock(path.read_text(encoding="utf-8"))
        rel = os.path.relpath(path)
        res = subprocess.run(  # nosec B603 B607 - fixed argv list, no shell, no user input; git/taskkill resolved from PATH on the developer machine
            ["git", "show", f"{ref}:./{Path(rel).as_posix()}"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        if res.returncode != 0:
            if "does not exist in" in res.stderr or "exists on disk, but not in" in res.stderr:
                return 0
            print(f"BASELINE ERROR: git show failed: {res.stderr.strip()}", file=sys.stderr)
            return 2
        old = _size_lock(res.stdout)
    except (OSError, ValueError) as exc:
        print(f"BASELINE ERROR: {exc}", file=sys.stderr)
        return 2
    grown = size_lock_growth(old, new)
    for g in grown:
        print(f"GREW: {g}")
    return 1 if grown else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="size_lock_shrink")
    ap.add_argument("lock", type=Path)
    ap.add_argument("base_ref")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    return check_size_lock_shrink(a.lock, a.base_ref)


if __name__ == "__main__":
    sys.exit(main())

"""Compare two baselines made by make_baseline.py; any growth is an error.

Usage: python compare_baseline.py BASE.json NEW.json [--touched FILE ...] [--moved SRC:DST ...]
Prints every growth line and exits 1; exits 0 when nothing grew.

Rules (debt-zero plan, G0.5):
1. Keyed tools (rule|file, deptry rule|module): every key new <= old, in any file.
2. Every tool total: new <= old (skylos: only this).
3. List tools (engine_api_edges, import_linter_broken_pairs, audit ids): a new entry is always an error.
Only exception: code a task moved. `--moved SRC:DST` lets keys of file DST grow when the
same rule key of file SRC shrank by at least that much; the total still may not grow.
`touched` only labels lines ("touched"/"untouched"); it never changes the verdict.
"""
import argparse
import json
import sys
from pathlib import Path


def _tools(data):
    return data.get("tools", data)


def _total(value):
    return sum(value.values())


def _file_of(key):
    return key.split("|", 1)[1] if "|" in key else key


def _label(key, touched):
    return "touched" if _file_of(key) in touched else "untouched"


def _compare_keyed(name, old, new, touched, moved, skip_keys=False):
    lines = []
    if not skip_keys:
        consumed = {}
        moves = {}
        for src, dst in moved:
            moves.setdefault(dst, []).append(src)
        for key in sorted(new):
            growth = new[key] - old.get(key, 0)
            if growth <= 0:
                continue
            rule = key.split("|", 1)[0]
            left = growth
            for src in moves.get(_file_of(key), []):
                src_key = f"{rule}|{src}"
                shrink = old.get(src_key, 0) - new.get(src_key, 0) - consumed.get(src_key, 0)
                take = min(max(shrink, 0), left)
                consumed[src_key] = consumed.get(src_key, 0) + take
                left -= take
            if left > 0:
                lines.append(f"{name}: {key} grew {old.get(key, 0)} -> {new[key]} ({_label(key, touched)})")
    if _total(new) > _total(old):
        lines.append(f"{name}: total grew {_total(old)} -> {_total(new)}")
    return lines


def _compare_lists(name, old, new):
    seen = {json.dumps(x, sort_keys=True) for x in old}
    return [f"{name}: new entry {x}" for x in new if json.dumps(x, sort_keys=True) not in seen]


def compare(base, new, touched, moved=()):
    old_tools, new_tools = _tools(base), _tools(new)
    lines = []
    for name in sorted(new_tools):
        if name not in old_tools:
            continue
        old, cur = old_tools[name], new_tools[name]
        if isinstance(old, str):
            continue  # base has no measurement for this tool
        if isinstance(cur, str):
            lines.append(f"{name}: new run has no result ({cur})")
        elif isinstance(old, int):
            if cur > old:
                lines.append(f"{name}: grew {old} -> {cur}")
        elif isinstance(old, list):
            lines.extend(_compare_lists(name, old, cur))
        elif name == "skylos":
            lines.extend(_compare_keyed(name, old, cur, touched, moved, skip_keys=True))
        else:
            lines.extend(_compare_keyed(name, old, cur, touched, moved))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("new")
    parser.add_argument("--touched", nargs="*", default=[])
    parser.add_argument("--moved", nargs="*", default=[], help="SRC:DST file pairs")
    args = parser.parse_args(argv)
    moved = [tuple(item.split(":", 1)) for item in args.moved]
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    lines = compare(base, new, set(args.touched), moved)
    for line in lines:
        print(line)
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())

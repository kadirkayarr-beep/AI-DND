"""Golden surface of the `game` module for the engine split: snapshot, diff rule, new-function check.

Records only names and kinds, never values (no machine paths, no addresses).
Run: python scripts/engine_split/surface.py --write <surface.json>
     python scripts/engine_split/surface.py --diff --old <a.json> --new <b.json> --moved a,b --added c
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
import types
from pathlib import Path

# A script run as a file has only its own folder on sys.path: add ai-dnd and ai-dnd/scripts (same as the tests).
if __name__ == "__main__":
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

SKIPPED = {
    "__builtins__", "__doc__", "__file__", "__cached__", "__spec__", "__loader__", "__name__", "__package__",
}
_PLAIN = (type(None), bool, int, float, str)


class _TypeName:
    """Stands in for a default value: prints as <TypeName>."""

    def __init__(self, value: object):
        self._text = f"<{type(value).__name__}>"

    def __repr__(self) -> str:
        return self._text


def normal_signature(fn) -> str:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return "<no signature>"
    params = [
        p if p.default is inspect.Parameter.empty or isinstance(p.default, _PLAIN)
        else p.replace(default=_TypeName(p.default))
        for p in sig.parameters.values()
    ]
    return str(sig.replace(parameters=params))


def _entry(value: object) -> dict:
    if isinstance(value, types.ModuleType):
        return {"kind": "module"}
    if inspect.isclass(value):
        return {"kind": "class", "module": value.__module__}
    if isinstance(value, (types.FunctionType, types.BuiltinFunctionType)):
        return {
            "kind": "function",
            "module": value.__module__,
            "signature": normal_signature(value),
            "session_bound": bool(getattr(value, "_session_bound", False)),
        }
    return {"kind": "data", "type": type(value).__name__}


def snapshot(module) -> dict[str, dict]:
    return {name: _entry(value) for name, value in vars(module).items() if name not in SKIPPED}


def new_engine_functions(golden: dict, live: dict) -> list[str]:
    return sorted(
        n for n, e in live.items()
        if e.get("kind") == "function" and e.get("module") == "game" and n not in golden
    )


def diff_rule(old: dict, new: dict, moved: set[str], added: set[str] = frozenset()) -> list[str]:
    out = [f"missing: {name}" for name in sorted(set(old) - set(new))]
    out += [f"unexpected new name: {name}" for name in sorted(set(new) - set(old)) if name not in added]
    for name in sorted(set(old) & set(new)):
        a, b = dict(old[name]), dict(new[name])
        if name in moved:
            a.pop("module", None)
            b.pop("module", None)
        if a != b:
            out.append(f"changed: {name}: {old[name]} -> {new[name]}")
    # F19: an added name must not be a new top-level function left in game (spec section 11 allow-list).
    out += [f"new engine function in game: {n}" for n in new_engine_functions(old, new) if n in added]
    return out


def _names(text: str) -> set[str]:
    return {n for n in text.split(",") if n}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--old")
    ap.add_argument("--new")
    ap.add_argument("--moved", default="")
    ap.add_argument("--added", default="")
    args = ap.parse_args(argv)
    if args.write:
        import game
        text = json.dumps(snapshot(game), sort_keys=True, indent=1, ensure_ascii=False) + "\n"
        Path(args.write).write_text(text, encoding="utf-8", newline="\n")
        return 0
    if args.diff:
        old = json.loads(Path(args.old).read_text(encoding="utf-8"))
        new = json.loads(Path(args.new).read_text(encoding="utf-8"))
        violations = diff_rule(old, new, _names(args.moved), _names(args.added))
        print("\n".join(violations))
        return 1 if violations else 0
    ap.error("use --write or --diff")


if __name__ == "__main__":
    raise SystemExit(main())

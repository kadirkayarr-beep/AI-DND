"""Top-level blank runs in engine files (game.py split T7.1): find, delete and verify blank lines beyond `keep` in a row.

Only whole blank lines (whitespace only) between top-level statements go; a line inside a statement's span (first
decorator line to end_lineno) is never touched, so code, comments, strings and line order stay the same.
Text is split on "\n" only (a "\r" stays on its line, a form feed inside a string does not start a new line), so line
numbers match ast. The text after the last "\n" counts as a line only when it is not empty.
Run: python scripts/engine_split/blank_runs.py --check <file>...   (prints RUNS <file> <n>; exit 1 if any n > 0)
     python scripts/engine_split/blank_runs.py --apply <file>      (deletes those lines in place; prints DELETED <file> <n>)
"""
from __future__ import annotations

import argparse
import ast
import io
import sys
import tokenize
from pathlib import Path


def _spans(text: str) -> list[tuple[int, int]]:
    """(first decorator or statement line, end_lineno) of every top-level statement."""
    out = []
    for node in ast.parse(text).body:
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        out.append((first, node.end_lineno))
    return out


def _inside(number: int, spans: list[tuple[int, int]]) -> bool:
    return any(first <= number <= end for first, end in spans)


def _real(lines: list[str]) -> list[str]:
    return lines[:-1] if lines and lines[-1] == "" else lines


def find(lines: list[str], keep: int = 2) -> list[int]:
    """1-based numbers of blank lines outside every top-level span that come after `keep` such lines in the same run."""
    spans = _spans("\n".join(lines))
    out, run = [], 0
    for number, line in enumerate(_real(lines), 1):
        if line.strip() or _inside(number, spans):
            run = 0
            continue
        run += 1
        if run > keep:
            out.append(number)
    return out


def _comments(text: str) -> list[str]:
    return [tok.string for tok in tokenize.generate_tokens(io.StringIO(text).readline) if tok.type == tokenize.COMMENT]


def verify(old: str, new: str, keep: int = 2) -> list[str]:
    """Empty when `new` is `old` with exactly the lines find(old, keep) removed; else one finding per broken rule."""
    old_lines, new_lines = _real(old.split("\n")), _real(new.split("\n"))
    deleted, j = [], 0
    for number, line in enumerate(old_lines, 1):
        if j < len(new_lines) and new_lines[j] == line:
            j += 1
        else:
            deleted.append(number)
    findings = []
    if j < len(new_lines):
        findings.append(f"new has {len(new_lines) - j} line(s) from line {j + 1} on that are not in old")
    expected = find(old.split("\n"), keep)
    if deleted != expected:
        findings.append(f"deleted lines {deleted} are not the found lines {expected}")
    spans = _spans(old)
    inside = [number for number in deleted if _inside(number, spans)]
    if inside:
        findings.append(f"deleted lines {inside} are inside a top-level statement")
    if [line for line in old_lines if line.strip()] != [line for line in new_lines if line.strip()]:
        findings.append("non-blank lines differ")
    if ast.dump(ast.parse(old)) != ast.dump(ast.parse(new)):
        findings.append("ast.dump differs")
    if _comments(old) != _comments(new):
        findings.append("comment tokens differ")
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", nargs="+", metavar="FILE")
    mode.add_argument("--apply", metavar="FILE")
    args = ap.parse_args(argv)
    if args.check:
        found = 0
        for name in args.check:
            n = len(find(Path(name).read_bytes().decode("utf-8").split("\n")))
            print(f"RUNS {name} {n}")
            found += n
        return 1 if found else 0
    path = Path(args.apply)
    lines = path.read_bytes().decode("utf-8").split("\n")
    drop = set(find(lines))
    path.write_bytes("\n".join(line for number, line in enumerate(lines, 1) if number not in drop).encode("utf-8"))
    print(f"DELETED {args.apply} {len(drop)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

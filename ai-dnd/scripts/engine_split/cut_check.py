"""Equivalence check for turn-split cuts (cut_block.py): each helper is the cut block, the call site is the only change.

Per helper in the report: the block text recorded by cut_block is found unchanged in the base file; the helper body
(without its added trailing `return`) has the same ast.dump as that block after folding `game.X` back to `X`; the
comment tokens are the same; the cut function in --root equals the base function with every block replaced by its
call-site lines (ast.dump); the helper's parameters and return match the report; total comments over game.py and
game_parts/ did not change. A finding prints `FINDING <text>`; the last line is `CHANGED <n>` (exit 0 only for 0).
Run: python scripts/engine_split/cut_check.py --base-root <archive>/ai-dnd --root . --report out.json
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import sys
import tokenize
from pathlib import Path

# A script run as a file has only its own folder on sys.path: add ai-dnd and ai-dnd/scripts (same as the tests).
if __name__ == "__main__":
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

from engine_split.cut_block import SENTINEL, call_lines, find_function  # noqa: E402
from engine_split.move_check import _FoldGame, comment_counts  # noqa: E402


def _read(path: Path) -> str:
    return Path(path).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _comments(text: str) -> list[str]:
    wrapped = "if 1:\n" + text if not text.startswith("def ") else text
    return [t.string.strip() for t in tokenize.generate_tokens(io.StringIO(wrapped).readline) if t.type == tokenize.COMMENT]


def _fold(stmts: list[ast.stmt]) -> str:
    return ast.dump(_FoldGame().visit(ast.Module(body=stmts, type_ignores=[])))


def _function_dump(text: str, function: str) -> str:
    return ast.dump(find_function(ast.parse(text), function)[-1])


def _find_all(lines: list[str], block: list[str]) -> list[int]:
    n = len(block)
    return [i for i in range(len(lines) - n + 1) if lines[i:i + n] == block]


def check(base_root: Path, root: Path, rows: list[dict]) -> list[str]:
    findings: list[str] = []
    base_root, root = Path(base_root), Path(root)
    groups: dict[tuple[str, str], list[tuple[int, int, dict]]] = {}
    for row in rows:
        name = row["helper"]
        block = row["block"].split("\n")
        base_lines = _read(base_root / row["file"]).split("\n")
        hits = _find_all(base_lines, block)
        if len(hits) != 1:
            findings.append(f"{name}: the recorded block is found {len(hits)} times in the base {row['file']}; expected once")
            continue
        groups.setdefault((row["file"], row["function"]), []).append((hits[0], hits[0] + len(block), row))
        part_text = _read(root / row["part"])
        helpers = [n for n in ast.parse(part_text).body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(helpers) != 1:
            findings.append(f"{name}: defined {len(helpers)} times in {row['part']}; expected once")
            continue
        fn = helpers[0]
        kwonly = [a.arg for a in fn.args.kwonlyargs]
        if kwonly != row["params"] or fn.args.args or fn.args.vararg or fn.args.kwarg:
            findings.append(f"{name}: parameters {kwonly} differ from the report {row['params']}")
        body = list(fn.body)
        tail = body[-1] if body and isinstance(body[-1], ast.Return) else None
        cut_tail = row["class"] == "B" or bool(row["outputs"])
        if cut_tail:
            want = f"game.{SENTINEL}" if row["class"] == "B" else ", ".join(row["outputs"])
            want = ast.unparse(ast.parse(want, mode="eval").body)
            got = ast.unparse(tail.value) if tail is not None and tail.value is not None else None
            if got != want:
                findings.append(f"{name}: final return is {got!r}; expected {want!r}")
            body = body[:-1]
        block_tree = ast.parse("if 1:\n" + row["block"]).body[0].body
        if _fold(body) != _fold(block_tree):
            findings.append(f"{name}: the helper body is not the cut block (ast differs)")
        part_lines = part_text.split("\n")
        end = (tail.lineno - 1) if cut_tail and tail is not None else fn.end_lineno
        if _comments("\n".join(part_lines[fn.lineno - 1:end])) != _comments(row["block"]):
            findings.append(f"{name}: the comments of the block and the helper differ")
    for (file, function), cuts in groups.items():
        text = _read(base_root / file).split("\n")
        spans = sorted((s, e) for s, e, _ in cuts)
        if any(b[0] < a[1] for a, b in zip(spans, spans[1:])):
            findings.append(f"{function}: cut blocks overlap")
            continue
        for s, e, row in sorted(cuts, key=lambda c: -c[0]):
            text[s:e] = call_lines(row["indent"], row["class"], row["helper"], row["params"], row["outputs"])
        try:
            if _function_dump("\n".join(text), function) != _function_dump(_read(root / file), function):
                findings.append(f"{function}: the cut function is not the base function with the call sites in place of the blocks")
        except Exception as exc:  # a syntax error or a missing function is a finding
            findings.append(f"{function}: cannot compare ({exc})")
    base_n, now_n = comment_counts(base_root, root)
    if base_n != now_n:
        findings.append(f"comment tokens over game.py and game_parts/: base {base_n}, now {now_n}")
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-root", required=True, type=Path, help="ai-dnd folder of the base archive")
    ap.add_argument("--root", required=True, type=Path, help="ai-dnd folder with the cuts")
    ap.add_argument("--report", required=True, type=Path, help="cut_block.py --report file")
    args = ap.parse_args(argv)
    rows = json.loads(args.report.read_text(encoding="utf-8"))["helpers"]
    findings = check(args.base_root, args.root, rows)
    for f in findings:
        print(f"FINDING {f}")
    print(f"CHANGED {len(findings)}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())

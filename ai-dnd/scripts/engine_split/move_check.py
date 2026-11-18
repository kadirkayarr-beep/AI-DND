"""Equivalence check for one game.py split move (N5).

Proves that blocks moved from game.py into game_parts/<x>.py are the same code apart from the added `game.` prefixes,
and that no comment was lost. Three tests per moved name: ast.dump after folding `game.X` back to `X`, the token stream
with comments and docstrings after dropping each added `game` `.` pair, and the start line from top_level_index (the
comment block directly above travels with the block). Files are read with universal newlines, so an LF base and a
CRLF working copy give the same verdict.
Run: python scripts/engine_split/move_check.py --base-root <dir>/ai-dnd --root . --moved name=part.py,... --tier normal|strong
     python scripts/engine_split/move_check.py --comments-only --base-root <dir>/ai-dnd --root .
`CHANGED` above zero is never patched forward: the move is redone from scratch.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import io
import json
import sys
import tokenize
from pathlib import Path

# A script run as a file has only its own folder on sys.path: add ai-dnd and ai-dnd/scripts (same as the tests).
if __name__ == "__main__":
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

from engine_split.inventory import top_level_index  # noqa: E402
from engine_split.sensitivity import LOCK_PATH, is_sensitive  # noqa: E402

LAYOUT = (tokenize.NEWLINE, tokenize.NL)


def _text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _tokens(text: str) -> list[tokenize.TokenInfo]:
    return list(tokenize.generate_tokens(io.StringIO(text).readline))


def _comment_count(path: Path) -> int:
    return sum(1 for tok in _tokens(_text(path)) if tok.type == tokenize.COMMENT)


def _part_files(root: Path) -> list[Path]:
    parts = Path(root) / "game_parts"
    return sorted(parts.glob("*.py")) if parts.is_dir() else []


def comment_counts(base_root: Path, new_root: Path) -> tuple[int, int]:
    """tokenize.COMMENT totals over game.py and every game_parts/*.py on each side: (base, now)."""
    return tuple(sum(_comment_count(f) for f in [Path(root) / "game.py", *_part_files(root)])
                 for root in (base_root, new_root))


class _FoldGame(ast.NodeTransformer):
    """`game.X` becomes the bare name `X` (the context of the attribute is kept)."""

    def visit_Attribute(self, node: ast.Attribute):
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "game":
            return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
        return node


def _folded_dump(block: str) -> str:
    return ast.dump(_FoldGame().visit(ast.parse(block)))


def _stream(block: str, drop_game: bool) -> list[tuple]:
    toks = _tokens(block)
    out, i = [], 0
    while i < len(toks):
        tok = toks[i]
        if (drop_game and tok.type == tokenize.NAME and tok.string == "game" and i + 2 < len(toks)
                and toks[i + 1].type == tokenize.OP and toks[i + 1].string == "."
                and toks[i + 2].type == tokenize.NAME):
            i += 2
            continue
        out.append((tok.type, "" if tok.type in LAYOUT else tok.string))
        i += 1
    return out


def _entries(path: Path, name: str) -> list[dict]:
    return [e for e in top_level_index(path) if e["name"] == name]


def _block(path: Path, entry: dict) -> str:
    return "\n".join(_text(path).splitlines()[entry["start"] - 1:entry["end"]]) + "\n"


def _manual_lines(manual: list[str], file: str) -> set[int]:
    lines = set()
    for item in manual:
        name, _, rest = item.partition(":")
        number = rest.partition(":")[0]
        if name == file and number.isdigit():
            lines.add(int(number))
    return lines


def _check_block(base_game: Path, part: Path, name: str, part_name: str) -> tuple[list[str], tuple | None]:
    """Findings for one moved name and the (start, end) span of its block in the part (None when not found)."""
    base = _entries(base_game, name)
    if len(base) != 1:
        return [f"{name}: bound {len(base)} times in the base game.py; expected exactly once"], None
    if not part.exists():
        return [f"{name}: part file {part_name} does not exist"], None
    now = _entries(part, name)
    if len(now) != 1:
        return [f"{name}: bound {len(now)} times in {part_name}; expected exactly once"], None
    base_block, new_block = _block(base_game, base[0]), _block(part, now[0])
    span = (now[0]["start"], now[0]["end"])
    found = []
    try:
        if _folded_dump(base_block) != _folded_dump(new_block):
            found.append(f"{name}: syntax tree differs after folding game.X back to X")
        if _stream(base_block, False) != _stream(new_block, True):
            found.append(f"{name}: token stream differs (comments, docstrings, spelling or layout changed)")
    except (tokenize.TokenError, SyntaxError) as exc:
        found.append(f"{name}: cannot compare the blocks: {exc}")
    return found, span


def _import_group_problem(lines: list[str], moved: dict[str, str]) -> str | None:
    """None when the lines are only `from game_parts.<x> import <moved names>` statements; else the reason."""
    try:
        body = ast.parse("\n".join(lines)).body
    except SyntaxError:
        return "not a complete `from game_parts.<x> import ...` statement"
    for stmt in body:
        if not isinstance(stmt, ast.ImportFrom) or stmt.level != 0 or not (stmt.module or "").startswith("game_parts."):
            return "not a `from game_parts.<x> import ...` statement"
        for alias in stmt.names:
            if alias.asname or alias.name not in moved or f"game_parts.{Path(moved[alias.name]).stem}" != stmt.module:
                return f"imports {alias.name!r}, which is not a moved name of that part"
    return None


def _game_py_findings(base_game: Path, new_game: Path, spans: list[tuple], manual: list[str],
                      moved: dict[str, str]) -> list[str]:
    base_lines, new_lines = _text(base_game).splitlines(), _text(new_game).splitlines()
    exempt = _manual_lines(manual, "game.py")
    found, deleted = [], set()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base_lines, new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        deleted.update(range(i1 + 1, i2 + 1))
        for i in range(i1, i2):  # a deleted line must be blank or sit inside a moved block
            if base_lines[i].strip() and not any(s <= i + 1 <= e for s, e in spans) and (i + 1) not in exempt:
                found.append(f"game.py: base line {i + 1} deleted outside the moved blocks: {base_lines[i].strip()[:60]}")
        group = [(j + 1, new_lines[j]) for j in range(j1, j2) if new_lines[j].strip() and (j + 1) not in exempt]
        if group:  # inserted or replaced lines must parse as import statements of moved names only
            problem = _import_group_problem([line for _, line in group], moved)
            if problem:
                found.append(f"game.py:{group[0][0]}: {problem}: {group[0][1].strip()[:60]}")
    for start, end in spans:  # every non-blank line of a moved block must be deleted
        for number in range(start, end + 1):
            if base_lines[number - 1].strip() and number not in deleted and number not in exempt:
                found.append(f"game.py: base line {number} of a moved block is still in game.py: {base_lines[number - 1].strip()[:60]}")
    try:
        for entry in top_level_index(new_game):
            if entry["name"] in moved and entry["kind"] != "import":
                found.append(f"game.py: {entry['name']!r} is still bound at top level ({entry['kind']}, line {entry['start']})")
    except SyntaxError as exc:
        found.append(f"game.py does not parse: {exc}")
    return found


def _import_only_lines(part: Path) -> set[int]:
    """Lines of the part that hold top-level import statements and nothing else (F16)."""
    body = ast.parse(_text(part)).body
    imports, others = set(), set()
    for stmt in body:
        target = imports if isinstance(stmt, (ast.Import, ast.ImportFrom)) else others
        target.update(range(stmt.lineno, stmt.end_lineno + 1))
    return imports - others


def _part_findings(base_part: Path, part: Path, part_name: str, spans: list[tuple], manual: list[str]) -> list[str]:
    """F16: a part line outside the moved blocks must be an import statement, blank, a line the base part already had, or manual.

    Gate TM0: every line of the base part must survive in the new part, in order; the new part may only insert lines.
    """
    base_lines = _text(base_part).splitlines() if base_part.exists() else []
    new_lines = _text(part).splitlines()
    exempt = _manual_lines(manual, part_name)
    import_lines = _import_only_lines(part)
    found, known = [], set()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base_lines, new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            known.update(range(j1 + 1, j2 + 1))
        elif tag in ("delete", "replace"):
            for i in range(i1, i2):
                found.append(f"{part_name}: base line {i + 1} deleted or changed: {base_lines[i].strip()[:60]}")
    for number, line in enumerate(new_lines, start=1):
        if not line.strip() or any(s <= number <= e for s, e in spans) or number in exempt:
            continue
        if number in import_lines or number in known:
            continue
        found.append(f"{part_name}:{number}: hand-written line outside the moved blocks: {line.strip()[:60]}")
    return found


def check_move(base_root: Path, new_root: Path, moved: dict[str, str], sensitive: dict, tier: str,
               manual: list[str] = []) -> dict:
    base_root, new_root = Path(base_root), Path(new_root)
    changed: list[str] = []
    spans_by_part: dict[str, list[tuple]] = {}
    base_spans: list[tuple] = []
    for name, part_name in moved.items():
        if is_sensitive(name, sensitive) and tier != "strong":
            changed.append(f"{name}: sensitive name; this move needs the strong tier")
        found, span = _check_block(base_root / "game.py", new_root / "game_parts" / part_name, name, part_name)
        changed += found
        if span:
            spans_by_part.setdefault(part_name, []).append(span)
        for entry in _entries(base_root / "game.py", name):  # statements that bind several names move whole
            base_spans += [(e["start"], e["end"]) for e in top_level_index(base_root / "game.py")
                           if (e["start"], e["end"]) == (entry["start"], entry["end"])]
    changed += _game_py_findings(base_root / "game.py", new_root / "game.py", base_spans, manual, moved)
    for part_name, spans in spans_by_part.items():
        changed += _part_findings(base_root / "game_parts" / part_name, new_root / "game_parts" / part_name,
                                  part_name, spans, manual)
    try:
        comments_base, comments_now = comment_counts(base_root, new_root)
    except (tokenize.TokenError, SyntaxError) as exc:
        changed.append(f"comment count failed: {exc}")
        comments_base = comments_now = 0
    if comments_base != comments_now:
        changed.append(f"comment count differs: base {comments_base}, now {comments_now}")
    return {"changed": changed, "comments_base": comments_base, "comments_now": comments_now, "manual": list(manual)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-root", required=True, type=Path, help="folder holding the base game.py (<dir>/ai-dnd after git archive)")
    ap.add_argument("--root", required=True, type=Path, help="folder holding the new game.py and game_parts/")
    ap.add_argument("--moved", default="", help="name=part.py,name=part.py")
    ap.add_argument("--tier", choices=["normal", "strong"], default="normal")
    ap.add_argument("--manual", action="append", default=[], help="file:line:reason (repeatable)")
    ap.add_argument("--comments-only", action="store_true")
    args = ap.parse_args(argv)
    if args.comments_only:
        base, now = comment_counts(args.base_root, args.root)
        print(f"COMMENTS base={base} now={now}")
        return 0 if base == now else 1
    moved = dict(pair.split("=", 1) for pair in args.moved.split(",") if pair)
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    result = check_move(args.base_root, args.root, moved, lock, args.tier, args.manual)
    for line in result["changed"]:
        print(f"  {line}")
    for item in result["manual"]:
        print(f"MANUAL {item} (mekanik değil)")
    print(f"CHANGED {len(result['changed'])}")
    return 1 if result["changed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

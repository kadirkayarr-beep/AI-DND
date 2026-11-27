"""Equivalence check for one game.py split move (N5).

Proves that blocks moved from game.py into game_parts/<x>.py are the same code apart from the added `game.` prefixes,
and that no comment was lost. Three tests per moved name: ast.dump after folding `game.X` back to `X`, the token stream
with comments and docstrings after dropping each added `game` `.` pair, and the start line from top_level_index (the
comment block directly above travels with the block). Files are read with universal newlines, so an LF base and a
CRLF working copy give the same verdict.
Run: python scripts/engine_split/move_check.py --base-root <dir>/ai-dnd --root . --moved name=part.py,... --tier normal|strong
     python scripts/engine_split/move_check.py --base-root <dir>/ai-dnd --root . --moved-file names.txt --part part.py
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
from engine_split.move_block import read_names  # noqa: E402
from engine_split.sensitivity import LOCK_PATH, is_sensitive  # noqa: E402

LAYOUT = (tokenize.NEWLINE, tokenize.NL)


def _text(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"cannot decode {path}") from None


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


def _manual_lines(manual: list[str], part_names: list[str],
                  other_parts: list[str] = ()) -> tuple[dict[str, set[int]], list[tuple[str, str, int]]]:
    """Exempt line numbers by key: "game.py:base", "game.py:new" and "game_parts/<part>" for each part in this check,
    and one (entry, key, line number) per entry.

    game.py entries name their side (`game.py:base:N:reason` or `game.py:new:N:reason`), so an entry exempts only
    the base line or only the new line with that number. Part entries are `game_parts/<part>:N:reason`.
    A part that is not in this check but differs from the base (D-360) is named the same way and exempts that finding.
    Any other entry, and an entry without a reason, raises ValueError.
    """
    lines = {"game.py:base": set(), "game.py:new": set(),
             **{f"game_parts/{p}": set() for p in [*part_names, *other_parts]}}
    refs = []
    for item in manual:
        name, _, rest = item.partition(":")
        if name == "game.py":
            side, _, rest = rest.partition(":")
            key = f"game.py:{side}"
            if key not in lines:
                raise ValueError(f"--manual {item!r}: a game.py entry is game.py:base:N:reason or game.py:new:N:reason")
        elif name in lines:
            key = name
        else:
            raise ValueError(f"--manual {item!r}: {name} is neither game.py nor a part in this check "
                             f"({', '.join(sorted(k for k in lines if k.startswith('game_parts/'))) or 'none'})")
        number, _, reason = rest.partition(":")
        if not number.isdigit():
            raise ValueError(f"--manual {item!r}: the line number {number!r} is not a number")
        if not reason.strip():
            raise ValueError(f"--manual {item!r}: the reason is missing (<file>:N:reason)")
        lines[key].add(int(number))
        refs.append((item, key, int(number)))
    return lines, refs


def _check_block(base_game: Path, part: Path, name: str, part_name: str) -> tuple[list[str], tuple | None]:
    """Findings for one moved name and the (start, end) span of its block in the part (None when not found)."""
    base = _entries(base_game, name)
    if len(base) != 1:
        return [f"{name}: bound {len(base)} times in the base game.py; expected exactly once"], None
    if not part.exists():
        return [f"{name}: part file {part_name} does not exist"], None
    try:
        now = _entries(part, name)
    except SyntaxError as exc:
        return [f"{name}: {part_name} does not parse: {exc}"], None
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


def _game_py_findings(base_game: Path, new_game: Path, spans: list[tuple], exempt_base: set[int],
                      exempt_new: set[int], moved: dict[str, str], used: set[tuple[str, int]],
                      deleted_out: set[int] | None = None) -> list[str]:
    """Findings for game.py; adds to `used` each ("game.py:base"|"game.py:new", line) exemption that hid a finding.

    The deleted non-blank lines outside the moved blocks are put back in `deleted_out` (base line numbers) when given.
    """
    base_lines, new_lines = _text(base_game).splitlines(), _text(new_game).splitlines()
    found = []
    deleted = deleted_out if deleted_out is not None else set()
    # D-376: base minus the moved spans must equal new minus this batch's re-export lines, line for line. Both lists
    # are compared from each end, and only the differing middle goes to SequenceMatcher: an exact move has no middle,
    # and kept lines can never pair across a span (the spans and the re-export lines are not in either list)
    kept = [i for i in range(len(base_lines)) if not any(s <= i + 1 <= e for s, e in spans)]
    reexport, other = set(), set()
    try:
        source = _text(new_game)
        for stmt in ast.parse(source).body:
            lines = set(range(stmt.lineno, stmt.end_lineno + 1))
            if isinstance(stmt, ast.ImportFrom) and not _import_group_problem([ast.get_source_segment(source, stmt)], moved):
                reexport |= lines
            else:
                other |= lines
    except SyntaxError:  # reported below
        pass
    shown = [j for j in range(len(new_lines)) if j + 1 not in reexport - other]
    rest, now = [base_lines[i] for i in kept], [new_lines[j] for j in shown]
    head = 0
    while head < min(len(rest), len(now)) and rest[head] == now[head]:
        head += 1
    tail = 0
    while tail < min(len(rest), len(now)) - head and rest[-1 - tail] == now[-1 - tail]:
        tail += 1
    middle = difflib.SequenceMatcher(None, rest[head:len(rest) - tail], now[head:len(now) - tail], autojunk=False)
    for tag, i1, i2, j1, j2 in middle.get_opcodes():
        if tag == "equal":
            continue
        for i in kept[head + i1:head + i2]:  # a deleted line must be blank
            if base_lines[i].strip():
                deleted.add(i + 1)
                if (i + 1) in exempt_base:
                    used.add(("game.py:base", i + 1))
                else:
                    found.append(f"game.py: base line {i + 1} deleted outside the moved blocks: {base_lines[i].strip()[:60]}")
        every = [(j + 1, new_lines[j]) for j in shown[head + j1:head + j2] if new_lines[j].strip()]
        group = [(number, line) for number, line in every if number not in exempt_new]
        if len(group) < len(every) and _import_group_problem([line for _, line in every], moved):
            # D-360, D-431: an exemption is used only when its own line is a bad line
            used.update(("game.py:new", number) for number, line in every
                        if number in exempt_new
                        and _import_group_problem([line], moved))
        if group:  # inserted or replaced lines must parse as import statements of moved names only
            problem = _import_group_problem([line for _, line in group], moved)
            if problem:
                found.append(f"game.py:{group[0][0]}: {problem}: {group[0][1].strip()[:60]}")
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


def _part_findings(base_part: Path, part: Path, part_name: str, spans: list[tuple], exempt: set[int],
                   used: set[tuple[str, int]]) -> list[str]:
    """F16: a part line outside the moved blocks must be an import statement, blank, a line the base part already had, or manual.

    Gate TM0: every line of the base part must survive in the new part, in order; the new part may only insert lines.
    Adds ("game_parts/<part>", line) to `used` for each manual line that hid a finding.
    """
    base_lines = _text(base_part).splitlines() if base_part.exists() else []
    new_lines = _text(part).splitlines()
    import_lines = _import_only_lines(part)
    found, known = [], set()
    # a new block's line must not stand in for a base line deleted from an earlier block (tail delete): mask it
    masked = [None if any(s <= j <= e for s, e in spans) else line for j, line in enumerate(new_lines, start=1)]
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base_lines, masked, autojunk=False).get_opcodes():
        if tag == "equal":
            known.update(range(j1 + 1, j2 + 1))
        elif tag in ("delete", "replace"):
            for i in range(i1, i2):
                found.append(f"{part_name}: base line {i + 1} deleted or changed: {base_lines[i].strip()[:60]}")
    for number, line in enumerate(new_lines, start=1):
        if not line.strip() or any(s <= number <= e for s, e in spans):
            continue
        if number in import_lines or number in known:
            continue
        if number in exempt:
            used.add((f"game_parts/{part_name}", number))
            continue
        found.append(f"{part_name}:{number}: hand-written line outside the moved blocks: {line.strip()[:60]}")
    return found


def _wrong_root(base_game: Path, new_game: Path, moved: dict[str, str], deleted: set[int]) -> str | None:
    """D-376: the message when every base line deleted outside the moved blocks sits in a whole top-level block of a
    name the new game.py re-exports from a part but this batch did not move (a later batch moved it); else None."""
    reexported = set()
    try:
        body = ast.parse(_text(new_game)).body
    except SyntaxError:  # reported by _game_py_findings
        return None
    for stmt in body:
        if isinstance(stmt, ast.ImportFrom) and stmt.level == 0 and (stmt.module or "").startswith("game_parts."):
            reexported.update(alias.name for alias in stmt.names)
    index = top_level_index(base_game)
    later = [e for e in index if e["name"] in reexported - set(moved) and e["kind"] != "import"]
    covered = {n for e in later for n in range(e["start"], e["end"] + 1)}
    registry = {n for e in index if e["name"] == "_PART_MODULES" for n in range(e["start"], e["end"] + 1)}
    deleted = deleted - registry  # a later batch also registers its part in _PART_MODULES
    if not deleted or not deleted <= covered:
        return None
    names = {e["name"] for e in later if any(e["start"] <= n <= e["end"] for n in deleted)}
    return (f"WRONG ROOT? {len(deleted)} base lines belong to {len(names)} names moved by later batches; "
            f"use the parent of this batch's move commit, "
            f"or add the missing names to --moved")


def _other_parts_differing(base_root: Path, new_root: Path, part_names: list[str]) -> list[str]:
    """D-360: part files outside this check whose bytes differ from the base (a file on one side only differs)."""
    names = {f.name for root in (base_root, new_root) for f in _part_files(root)} - set(part_names)
    def raw(root: Path, name: str):
        path = root / "game_parts" / name
        return _text(path) if path.exists() else None  # universal newlines: LF and CRLF copies compare equal
    return sorted(n for n in names if raw(base_root, n) != raw(new_root, n))


def _changed_lines(base_part: Path, new_part: Path) -> set[int]:
    """D-432: the new part's line numbers inserted or replaced against the base.

    A deletion names the line that follows it; a new file changes every line,
    a gone file none.
    """
    if not new_part.exists():
        return set()
    base_lines = _text(base_part).splitlines() if base_part.exists() else []
    new_lines = _text(new_part).splitlines()
    out: set[int] = set()
    matcher = difflib.SequenceMatcher(None, base_lines, new_lines, autojunk=False)
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            out.add(min(j1 + 1, len(new_lines)))
        elif tag != "equal":
            out.update(range(j1 + 1, j2 + 1))
    return out


def check_move(base_root: Path, new_root: Path, moved: dict[str, str], sensitive: dict, tier: str,
               manual: list[str] | None = None) -> dict:
    manual = manual or []
    base_root, new_root = Path(base_root), Path(new_root)
    differing = _other_parts_differing(base_root, new_root, list(moved.values()))
    exempt, refs = _manual_lines(manual, list(moved.values()), differing)  # ValueError on an entry outside this check
    for root in (base_root, new_root):  # ValueError naming the first file that is not UTF-8
        for path in [root / "game.py", *_part_files(root)]:
            if path.exists():
                _text(path)
    used: set[tuple[str, int]] = set()
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
    deleted_out: set[int] = set()
    changed += _game_py_findings(base_root / "game.py", new_root / "game.py", base_spans, exempt["game.py:base"],
                                 exempt["game.py:new"], moved, used, deleted_out)
    wrong_root = _wrong_root(base_root / "game.py", new_root / "game.py", moved, deleted_out)
    for name in differing:  # D-360: a hand edit in a part this batch does not move
        key = f"game_parts/{name}"
        named = exempt[key] & _changed_lines(base_root / "game_parts" / name,
                                             new_root / "game_parts" / name)
        if named:  # D-432: an entry counts only for a line that differs from the base
            used.update((key, number) for number in named)
        else:
            changed.append(f"CHANGED other part {name} differs from base")
    for part_name, spans in spans_by_part.items():
        changed += _part_findings(base_root / "game_parts" / part_name, new_root / "game_parts" / part_name,
                                  part_name, spans, exempt[f"game_parts/{part_name}"], used)
    changed += [f"manual entry exempts nothing: {item}" for item, key, number in refs if (key, number) not in used]
    try:
        comments_base, comments_now = comment_counts(base_root, new_root)
    except (tokenize.TokenError, SyntaxError) as exc:
        changed.append(f"comment count failed: {exc}")
        comments_base = comments_now = 0
    if comments_base != comments_now:
        changed.append(f"comment count differs: base {comments_base}, now {comments_now}")
    return {"changed": changed, "comments_base": comments_base, "comments_now": comments_now, "manual": list(manual),
            "wrong_root": wrong_root}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-root", required=True, type=Path, help="folder holding the base game.py (<dir>/ai-dnd after git archive)")
    ap.add_argument("--root", required=True, type=Path, help="folder holding the new game.py and game_parts/")
    moved_group = ap.add_mutually_exclusive_group()
    moved_group.add_argument("--moved", default="", help="name=part.py,name=part.py")
    moved_group.add_argument("--moved-file", type=Path, help="one moved name per line; needs --part")
    ap.add_argument("--part", help="the part file name of every name in --moved-file (part.py)")
    ap.add_argument("--tier", choices=["normal", "strong"], default="normal")
    ap.add_argument("--manual", action="append", default=[], help="game.py:base|new:line:reason or game_parts/<part>:line:reason (repeatable)")
    ap.add_argument("--comments-only", action="store_true")
    args = ap.parse_args(argv)
    if (args.moved_file is None) != (args.part is None):
        ap.error("--moved-file and --part go together")
    if args.moved_file is not None:
        moved = {name: args.part for name in read_names(args.moved_file)}
    else:
        moved = dict(pair.split("=", 1) for pair in args.moved.split(",") if pair)
    if not moved and not args.comments_only:
        ap.error("no moved names: give --moved or a non-empty --moved-file (or --comments-only)")
    bad_parts = sorted(p for p in set(moved.values()) if not (p.endswith(".py") and p[:-3].isidentifier()))
    if bad_parts:   # a path would be joined under game_parts/ (an absolute one replaces it): only a bare file name
        ap.error(f"a part is a bare <identifier>.py file name under game_parts/, not {', '.join(bad_parts)}")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    try:
        if args.comments_only:
            base, now = comment_counts(args.base_root, args.root)
            print(f"COMMENTS base={base} now={now}")
            return 0 if base == now else 1
        result = check_move(args.base_root, args.root, moved, lock, args.tier, args.manual)
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    if result["wrong_root"]:  # no CHANGED list: the findings of a wrong root only mislead
        print(result["wrong_root"])
        return 2
    for line in result["changed"]:
        print(f"  {line}")
    for item in result["manual"]:
        print(f"MANUAL {item} (mekanik değil)")
    print(f"CHANGED {len(result['changed'])} names={len(moved)}")
    return 1 if result["changed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Plan 6 draft measurement (read-only). stdlib only.

Usage: p6_measure.py <tree root (holds ai-dnd/)> <plan-5 batches dir> <out json>

1. game.py composition today (blank, comment-only, code; top-level blank runs).
2. Projection: remove every top-level block whose names are in a Plan 4 batch file of the tree or a Plan 5 batch
   file, the way move_block does (comment block above, decorators, body); add one re-export line per batch.
3. The projected file after the blank-line rule: between two top-level statements keep at most K blank lines
   (K = 2, PEP 8; K = 1 shown too); blank lines inside a statement's span are never touched.
4. Part sizes today and the long-function list.
5. Dead-code name scan (spec section 10 condition 1 only): top-level functions/classes of game.py and every part
   whose name occurs nowhere in the tree outside its own definition, the re-export lines and the split's own
   bookkeeping files.
"""
import ast
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
p5dir = Path(sys.argv[2])
out_json = Path(sys.argv[3])
engine = root / "ai-dnd"
sys.path.insert(0, str(engine / "scripts")); sys.path.insert(0, str(engine / "scripts" / "engine_split"))
from inventory import top_level_index  # noqa: E402

game = engine / "game.py"
text = game.read_text(encoding="utf-8").split("\n")
if text and text[-1] == "":
    text = text[:-1]


def composition(lines):
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(1 for l in lines if l.strip().startswith("#"))
    return {"lines": len(lines), "blank": blank, "comment_only": comment, "code": len(lines) - blank - comment}


def top_spans(lines):
    tree = ast.parse("\n".join(lines) + "\n")
    spans = []
    for node in tree.body:
        decorators = getattr(node, "decorator_list", [])
        start = min([node.lineno] + [d.lineno for d in decorators])
        spans.append((start, node.end_lineno))
    return spans


def blank_rule(lines, keep):
    spans = top_spans(lines)
    inside = set()
    for s, e in spans:
        inside.update(range(s, e + 1))
    out, run = [], 0
    for number, line in enumerate(lines, start=1):
        if not line.strip() and number not in inside:
            run += 1
            if run > keep:
                continue
        else:
            run = 0
        out.append(line)
    # leading blank lines at top of file and trailing ones count as runs as well
    return out


def runs(lines):
    spans = top_spans(lines)
    inside = set()
    for s, e in spans:
        inside.update(range(s, e + 1))
    hist, run = {}, 0
    for number, line in enumerate(lines + ["x"], start=1):
        if number <= len(lines) and not line.strip() and number not in inside:
            run += 1
        else:
            if run:
                hist[run] = hist.get(run, 0) + 1
            run = 0
    return dict(sorted(hist.items()))


result = {"today": composition(text), "today_top_level_blank_runs": runs(text)}

# 2. projection
batch_names = {}
for f in sorted((engine / "scripts" / "engine_split" / "batches").glob("*.txt")):
    batch_names[f.stem] = [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
for f in sorted(p5dir.glob("*.txt")):
    batch_names["p5:" + f.stem] = [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
index = top_level_index(game)
top_names = {e["name"] for e in index if e["kind"] != "import"}
remove, used_batches = set(), {}
for batch, names in batch_names.items():
    here = [n for n in names if n in top_names]
    if here:
        used_batches[batch] = len(here)
    for e in index:
        if e["name"] in here and e["kind"] != "import":
            remove.update(range(e["start"], e["end"] + 1))
projected = [l for n, l in enumerate(text, start=1) if n not in remove]
projected += ["from game_parts.x import y"] * len(used_batches)  # one re-export line per batch (position irrelevant)
result["projection"] = {
    "batches_still_to_move": used_batches,
    "names_still_to_move": sum(used_batches.values()),
    "after_plan_5": composition(projected),
    "top_level_blank_runs": runs(projected),
}
for keep in (2, 1):
    cleaned = blank_rule(projected, keep)
    result["projection"][f"after_blank_rule_keep_{keep}"] = composition(cleaned)
result["today_after_blank_rule_keep_2"] = composition(blank_rule(text, 2))

# remaining top-level names after the projection
remaining = [e for e in index if not any(e["start"] <= n <= e["end"] for n in remove)]
result["projection"]["remaining_top_level_names"] = len(remaining)
result["projection"]["remaining_kinds"] = {}
for e in remaining:
    result["projection"]["remaining_kinds"][e["kind"]] = result["projection"]["remaining_kinds"].get(e["kind"], 0) + 1

# 4. parts
parts = {}
for p in sorted((engine / "game_parts").glob("*.py")):
    lines = p.read_text(encoding="utf-8").split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    parts[p.name] = composition(lines)
result["parts"] = parts

# 5. dead-code name scan (condition 1 only)
SKIP_PARTS = (
    "docs/superpowers/", "docs/agents/debt-register.md", "docs/agents/onay-listesi", "ai-dnd/api/tests/engine_split_locks/",
    "ai-dnd/scripts/engine_split/batches/", ".superpowers/", "graphify-out/", "docs/engine-split/",
)
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
counts, counts_all, skipped = {}, {}, []
for f in root.rglob("*"):
    if not f.is_file() or f.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".mp3",
                                                ".wav", ".ogg", ".woff", ".woff2", ".ttf", ".db", ".sqlite", ".pyc"}:
        continue
    rel = f.relative_to(root).as_posix()
    if "node_modules/" in rel:
        continue
    try:
        data = f.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        skipped.append(rel)
        continue
    skip = rel.startswith(SKIP_PARTS) or any(s in rel for s in SKIP_PARTS)
    for w in WORD.findall(data):
        counts_all[w] = counts_all.get(w, 0) + 1
        if not skip:
            counts[w] = counts.get(w, 0) + 1

engine_files = [game] + sorted((engine / "game_parts").glob("*.py"))
reexported = set()
for node in ast.parse(game.read_text(encoding="utf-8")).body:
    if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("game_parts."):
        reexported.update(a.asname or a.name for a in node.names)
candidates = []
for f in engine_files:
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            if name.startswith("__"):
                continue
            expected = 1 + (1 if name in reexported else 0)  # the def plus the re-export line
            if counts.get(name, 0) <= expected:
                candidates.append({"name": name, "file": f.relative_to(engine).as_posix(),
                                   "lines": node.end_lineno - node.lineno + 1,
                                   "count_outside_bookkeeping": counts.get(name, 0),
                                   "count_everywhere": counts_all.get(name, 0)})
result["dead_name_scan"] = {"count": len(candidates), "lines": sum(c["lines"] for c in candidates),
                            "candidates": candidates}
SPEC = ["_filter_unsupported_lore_paragraphs", "_existing_local_tavern", "analyze_player_action",
        "update_world_state_from_player", "is_dialogue_or_emotion"]
spec_rows = []
for name in SPEC:
    where = None
    for f in engine_files:
        for node in ast.parse(f.read_text(encoding="utf-8")).body:
            if getattr(node, "name", None) == name:
                where = (f.relative_to(engine).as_posix(), node.end_lineno - node.lineno + 1)
    spec_rows.append({"name": name, "where": where, "count_outside_bookkeeping": counts.get(name, 0),
                      "count_everywhere": counts_all.get(name, 0)})
result["spec_candidates"] = spec_rows

out_json.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
print("TODAY", result["today"])
print("TODAY_RUNS", result["today_top_level_blank_runs"])
print("TODAY_KEEP2", result["today_after_blank_rule_keep_2"])
pr = result["projection"]
print("STILL_TO_MOVE", pr["names_still_to_move"], pr["batches_still_to_move"])
print("AFTER_P5", pr["after_plan_5"])
print("AFTER_P5_RUNS", pr["top_level_blank_runs"])
print("AFTER_P5_KEEP2", pr["after_blank_rule_keep_2"])
print("AFTER_P5_KEEP1", pr["after_blank_rule_keep_1"])
print("REMAINING", pr["remaining_top_level_names"], pr["remaining_kinds"])
for k, v in parts.items():
    print("PART", k, v)
print("SKIPPED", len(skipped))
for p_ in skipped:
    print("  SKIPPED", p_)
print("DEAD_SCAN", result["dead_name_scan"]["count"], "names", result["dead_name_scan"]["lines"], "lines")
for c in candidates:
    print("  DEAD", c["file"], c["name"], c["lines"], "outside", c["count_outside_bookkeeping"], "all", c["count_everywhere"])
for r in spec_rows:
    print("SPEC", r)

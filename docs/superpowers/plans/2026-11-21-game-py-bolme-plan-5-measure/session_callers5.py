"""Read-only (Plan 5, from Plan 4's session_callers.py): which Plan 5 (`turn`) names are called with a `session=` keyword outside game.py.
Counts calls `<anything>.<name>(..., session=...)` and `<name>(..., session=...)` in every .py file under <ai-dnd root>
except game.py itself (tests, engine modules, parts, scripts). Names come from the plan5 rows of <p4-map.json>.
Usage: python session_callers.py <ai-dnd root> <p4-map.json>. Prints SESSION_CALLERS names=<n> calls=<m> and one line per name.
"""
import ast
import collections
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
rows = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["rows"]
names = {row["name"] for row in rows if row["scope"] == "plan5"}
counts, files = collections.Counter(), collections.defaultdict(set)
for path in sorted(ROOT.rglob("*.py")):
    rel = path.relative_to(ROOT).as_posix()
    if rel == "game.py" or any(part in {".venv", "node_modules", "__pycache__"} for part in path.parts):
        continue
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except (SyntaxError, UnicodeDecodeError):
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not any(k.arg == "session" for k in node.keywords):
            continue
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if called in names:
            counts[called] += 1
            files[called].add(rel)
print(f"SESSION_CALLERS names={len(counts)} calls={sum(counts.values())}")
for name, n in counts.most_common():
    print(f"  {name} {n} {sorted(files[name])[:6]}")

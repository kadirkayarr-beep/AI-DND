"""Count import edges from flat engine modules in ai-dnd/*.py into the api package.

import-linter only accepts packages as roots, and the engine is mostly flat modules,
so this script covers the flat part. Run from the repo root:
    python docs/agents/kalite-taramasi-20261125/engine_api_edges.py
Prints one line per edge (module -> api target, including imports inside functions) and a total.
"""
import ast
from pathlib import Path

ROOT = Path("ai-dnd")
edges = []
for path in sorted(ROOT.glob("*.py")):
    if path.stem.startswith("test_") or path.stem in {"acceptance_test", "conftest"}:
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        else:
            continue
        for name in names:
            if name == "api" or name.startswith("api."):
                edges.append(f"{path.stem} -> {name}")
for edge in sorted(set(edges)):
    print(edge)
print(f"TOTAL distinct edges: {len(set(edges))}")

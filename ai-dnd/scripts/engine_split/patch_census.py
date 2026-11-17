"""N2 patch census: every place under ai-dnd that patches or rebinds an attribute of the `game` module.

Reads surface.json as data and never imports `game`. Usage (from ai-dnd/):
    python scripts/engine_split/patch_census.py --write   # rewrite the lock and the report
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACE_PATH = ROOT / "api" / "tests" / "engine_split_locks" / "surface.json"
LOCK_PATH = ROOT / "api" / "tests" / "engine_split_locks" / "patch_census.json"
REPORT_PATH = ROOT.parent / "docs" / "engine-split" / "patch-census.md"

# Same skip rule as test_coin_writers (F2): docs/ and __pycache__ differ between the slot and CI.
SKIP_PARTS = {"docs", "__pycache__"}
SKIP_PREFIXES = (("game_parts",), ("scripts", "engine_split"))
# Plain assignments count only on these object names (F3); by-name counting is for patch/setattr only.
ASSIGN_NAMES = {"game", "engine", "game_module"}


def _surface() -> dict:
    return json.loads(SURFACE_PATH.read_text(encoding="utf-8"))


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _str_arg(call: ast.Call, index: int):
    if len(call.args) > index and isinstance(call.args[index], ast.Constant) and isinstance(call.args[index].value, str):
        return call.args[index].value
    return None


def _aliases(tree: ast.AST) -> set[str]:
    names = {"game"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.asname for a in node.names if a.name == "game" and a.asname)
    return names


def _first_attr(node: ast.AST, aliases: set[str]):
    """For `A` or `A.x.y` with A a game alias return (True, None) or (True, "x"); otherwise (False, None)."""
    if isinstance(node, ast.Name):
        return (node.id in aliases), None
    if isinstance(node, ast.Attribute):
        chain = _dotted(node).split(".")
        if chain[0] in aliases and len(chain) >= 2:
            return True, chain[1]
    return False, None


def _object_site(call: ast.Call, how: str, aliases: set[str], game_names: set[str]):
    """patch.object / patch.multiple / setattr: first arg is the object, then the attribute name(s)."""
    if not call.args:
        return []
    obj = call.args[0]
    if isinstance(obj, ast.Constant) and isinstance(obj.value, str):  # monkeypatch.setattr("game.x", v), patch.multiple("game", ...)
        parts = obj.value.split(".")
        if parts[0] != "game":
            return []
        if how == "setattr":
            return [(parts[1], how)] if len(parts) >= 2 else []
        resolved, nested = True, (parts[1] if len(parts) >= 2 else None)
    else:
        resolved, nested = _first_attr(obj, aliases)
    if how == "patch_multiple":
        names = [k.arg for k in call.keywords if k.arg]
    else:
        name = _str_arg(call, 1)
        names = [name] if name else []
    if nested:
        return [(nested, how)]
    if resolved:
        return [(n, how) for n in names]
    return [(n, how) for n in names if n in game_names or n == "open"]  # unresolved (parameter, fixture): by name


def _call_sites(call: ast.Call, aliases: set[str], game_names: set[str]):
    func = _dotted(call.func)
    last = func.split(".")[-1]
    if func == "patch" or func.endswith(".patch"):
        text = _str_arg(call, 0)
        if text and text.startswith("game.") and text.split(".")[1]:
            return [(text.split(".")[1], "patch_string")]
        return []
    if func.endswith("patch.object"):
        return _object_site(call, "patch_object", aliases, game_names)
    if func.endswith("patch.multiple"):
        return _object_site(call, "patch_multiple", aliases, game_names)
    if last == "setattr" and len(call.args) >= 2:
        return _object_site(call, "setattr", aliases, game_names)
    return []


def _assign_sites(node: ast.Assign, aliases: set[str]):
    out = []
    stack = list(node.targets)
    while stack:
        target = stack.pop(0)
        if isinstance(target, (ast.Tuple, ast.List)):
            stack.extend(target.elts)
        elif isinstance(target, ast.Attribute):
            chain = _dotted(target).split(".")
            if len(chain) >= 2 and chain[0] in (aliases | ASSIGN_NAMES):
                out.append((chain[1], "assign"))
    return out


class _Visitor(ast.NodeVisitor):
    def __init__(self, aliases: set[str], game_names: set[str]):
        self.aliases, self.game_names = aliases, game_names
        self.functions: list[str] = []
        self.sites: list[dict] = []

    def _add(self, node, found):
        in_test = any(name.startswith("test") for name in self.functions)
        for target, how in found:
            self.sites.append({"line": node.lineno, "target": target, "how": how, "in_test_function": in_test})

    def _function(self, node):
        self.functions.append(node.name)  # decorators belong to the function they decorate
        self.generic_visit(node)
        self.functions.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _function

    def visit_Call(self, node):
        self._add(node, _call_sites(node, self.aliases, self.game_names))
        self.generic_visit(node)

    def visit_Assign(self, node):
        self._add(node, _assign_sites(node, self.aliases))
        self.generic_visit(node)


def _skipped(rel: Path) -> bool:
    parts = rel.parts
    if set(parts) & SKIP_PARTS or rel.as_posix() == "game.py":
        return True
    return any(parts[:len(prefix)] == prefix for prefix in SKIP_PREFIXES)


def _python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if not _skipped(rel):
            yield path, rel.as_posix()


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def scan(root: Path, game_names: set[str]) -> list[dict]:
    """Every patch or rebinding of a `game` attribute: file, line, target, how, in_test_function."""
    sites = []
    for path, rel in _python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        visitor = _Visitor(_aliases(tree), game_names)
        visitor.visit(tree)
        sites.extend({"file": rel, **site} for site in visitor.sites)
    return sorted(sites, key=lambda s: (s["file"], s["line"], s["target"]))


def targets(sites: list[dict]) -> dict[str, str]:
    """target -> function | data | import | absent. Classes count as function; names whose own module is not game are import."""
    surface = _surface()
    out = {}
    for target in sorted({s["target"] for s in sites}):
        entry = surface.get(target)
        if entry is None:
            kind = "absent"
        elif entry["kind"] == "data":
            kind = "data"
        elif entry["kind"] == "module" or entry.get("module", "game") != "game":
            kind = "import"
        else:
            kind = "function"
        out[target] = kind
    return out


def not_called_tests(root: Path) -> list[str]:
    """`file::test` ids that patch a game target and then assert assert_not_called() on that patch (N4 blind spot)."""
    game_names = set(_surface())
    found = set()
    for path, rel in _python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        aliases = _aliases(tree)
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)) or not func.name.startswith("test"):
                continue
            bound: set[str] = set()
            patched: set[str] = set()
            for node in ast.walk(func):
                if isinstance(node, ast.withitem) and isinstance(node.context_expr, ast.Call):
                    if _call_sites(node.context_expr, aliases, game_names) and isinstance(node.optional_vars, ast.Name):
                        bound.add(node.optional_vars.id)
                elif isinstance(node, ast.Call):
                    patched.update(t for t, _ in _call_sites(node, aliases, game_names))
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "assert_not_called":
                    owner = node.func.value
                    if isinstance(owner, ast.Name) and owner.id in bound:
                        found.add(f"{rel}::{func.name}")
                    else:
                        resolved, nested = _first_attr(owner, aliases)
                        if resolved and nested in patched:
                            found.add(f"{rel}::{func.name}")
    return sorted(found)


def report(sites: list[dict], kinds: dict[str, str], not_called: list[str]) -> str:
    by_target = Counter(s["target"] for s in sites)
    by_file = Counter(s["file"] for s in sites)
    by_how = Counter(s["how"] for s in sites)
    lines = ["# N2 patch census", "",
             "Generated by `ai-dnd/scripts/engine_split/patch_census.py --write`. Do not edit by hand.", "",
             f"Sites: {len(sites)}. Distinct targets: {len(by_target)}. Files: {len(by_file)}.", "",
             "## By form", "", "| how | sites |", "|---|---|"]
    lines += [f"| {how} | {count} |" for how, count in sorted(by_how.items())]
    lines += ["", "## Per target", "", "| target | kind | sites |", "|---|---|---|"]
    lines += [f"| `{t}` | {kinds[t]} | {c} |" for t, c in sorted(by_target.items(), key=lambda i: (-i[1], i[0]))]
    lines += ["", "## Per file", "", "| file | sites |", "|---|---|"]
    lines += [f"| `{f}` | {c} |" for f, c in sorted(by_file.items(), key=lambda i: (-i[1], i[0]))]
    lines += ["", "## Tests that assert assert_not_called() on a game patch", ""]
    lines += [f"- `{item}`" for item in not_called] or ["- none"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--lock", default=str(LOCK_PATH))  # the slot's tree is a copy: point these at the worktree
    ap.add_argument("--report", default=str(REPORT_PATH))
    args = ap.parse_args(argv)
    sites = scan(ROOT, set(_surface()))
    kinds, not_called = targets(sites), not_called_tests(ROOT)
    if args.write:
        Path(args.lock).write_text(json.dumps({"targets": kinds, "not_called_tests": not_called}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report(sites, kinds, not_called), encoding="utf-8")
    print(f"sites={len(sites)} targets={len(kinds)} not_called_tests={len(not_called)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

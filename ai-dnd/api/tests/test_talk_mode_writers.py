"""Talk mode has one writer: a source census (AST, not words) that only talk_mode writes the three talk fields, that
every interlocutor clear names its reason, and that no product code hands talk_mode.current a list (Dilim 2, Task 9)."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

import game
import talk_mode

ROOT = Path(__file__).resolve().parents[2]          # ai-dnd/
FIELDS = ("active_npc_id", "active_npc_until_turn", "last_npc_id")


def _skipped(rel):
    return ("/tests/" in f"/{rel}" or rel.startswith(("legacy_debug/", "docs/", "reports/")) or "__pycache__" in rel
            or ("/" not in rel and (rel.startswith("test_") or rel.endswith("_test.py"))))


def _field(node):
    return isinstance(node, ast.Constant) and node.value in FIELDS


def _writes(scope):
    """A subscript store of a field, a flags.update/pop/setdefault that names one, or a flags dict literal holding one."""
    names_one = any(_field(sub) for sub in ast.walk(scope))
    for sub in ast.walk(scope):
        targets = (sub.targets if isinstance(sub, ast.Assign)
                   else [sub.target] if isinstance(sub, (ast.AugAssign, ast.AnnAssign)) else [])
        if any(isinstance(t, ast.Subscript) and _field(t.slice) for t in targets):
            return True
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr in {"update", "pop", "setdefault"} and "flags" in ast.unparse(sub.func.value)):
            if any(k.arg in FIELDS for k in sub.keywords) or any(_field(a) for a in sub.args):
                return True
            if sub.args and isinstance(sub.args[0], (ast.Name, ast.Dict)) and names_one:
                return True                              # flags.pop(key) / flags.update(kept) over the three fields
        if isinstance(sub, ast.Dict):
            for key, value in zip(sub.keys, sub.values):
                if (isinstance(key, ast.Constant) and key.value == "flags" and isinstance(value, ast.Dict)
                        and any(_field(k) for k in value.keys if k is not None)):
                    return True                          # "flags": {"active_npc_id": None, ...}
    return False


def writers():
    found = set()
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if _skipped(rel):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _writes(node):
                found.add(f"{rel}:{node.name}")
        module_level = ast.Module(body=[s for s in tree.body
                                        if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))],
                                  type_ignores=[])
        if _writes(module_level):
            found.add(f"{rel}:<module>")
    return found


class OnlyTalkModeWrites(unittest.TestCase):
    def test_only_talk_mode_writes_the_talk_fields(self):
        self.assertEqual(sorted(w for w in writers() if not w.startswith("talk_mode.py:")), [])

    def test_the_census_sees_todays_kinds_of_writer(self):
        # each kind of writer the census must catch (tasarım §2.6), on a tiny source of its own
        for source in ('def f(flags):\n    flags["active_npc_id"] = None\n',
                       'def f(flags):\n    flags.update(active_npc_id="a")\n',
                       'def f(flags):\n    for key in ("active_npc_id",):\n        flags.pop(key, None)\n',
                       'def f(flags, kept):\n    x = "last_npc_id"\n    flags.update(kept)\n',
                       'world_state = {"flags": {"active_npc_id": None}}\n'):
            with self.subTest(source=source):
                self.assertTrue(_writes(ast.parse(source)))
        for source in ('def f(flags):\n    return flags.get("active_npc_id")\n',
                       'def f(w):\n    return {"active_npc_id": w.get("flags", {}).get("active_npc_id")}\n'):  # reads
            with self.subTest(source=source):
                self.assertFalse(_writes(ast.parse(source)))

    def test_every_interlocutor_clear_names_its_reason(self):
        # callers of the wrapper do not write the fields themselves, so writers() cannot see them (tasarım karar 51)
        calls = []
        for path in sorted(ROOT.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if _skipped(rel):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if (isinstance(node, ast.Call)
                        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
                        == "_clear_active_interlocutor"):
                    reason = node.args[0].value if (len(node.args) == 1 and not node.keywords
                                                    and isinstance(node.args[0], ast.Constant)) else None
                    calls.append((rel, reason))
        self.assertEqual(sorted(calls), [("game.py", "combat"), ("game.py", "ended"), ("grounded_action.py", "walking")])
        self.assertTrue({reason for _, reason in calls} <= set(talk_mode.REASONS))
        with self.assertRaises(TypeError):
            game._clear_active_interlocutor()                            # no default reason

    def test_no_product_call_passes_a_people_list_to_current(self):
        calls = []
        for path in sorted(ROOT.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if _skipped(rel) or rel == "talk_mode.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "current"
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "talk_mode"):
                    calls.append((rel, len(node.args), sorted(k.arg for k in node.keywords)))
        self.assertEqual(sorted({rel for rel, _, _ in calls}), ["api/serializers.py", "game.py"])
        self.assertEqual([c for c in calls if c[1] != 1 or c[2]], [])        # exactly one argument: the world


if __name__ == "__main__":
    unittest.main()

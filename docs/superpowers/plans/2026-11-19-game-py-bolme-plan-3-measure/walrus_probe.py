# Read-only (Plan 3 fix wave): routing_audit.audit on four walrus shapes (D-349 M9). Usage: python walrus_probe.py <ai-dnd root>
import json, sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from engine_split.routing_audit import audit, character_names
LOCKS = ROOT / "api/tests/engine_split_locks"
TARGETS = json.loads((LOCKS / "patch_census.json").read_text(encoding="utf-8"))["targets"]
ALLOWED = set(json.loads((LOCKS / "allowed_imports.json").read_text(encoding="utf-8")))
ALLOW = json.loads((LOCKS / "identity_allowlist.json").read_text(encoding="utf-8"))
CHARS = character_names(ROOT / "game.py")
GAME_PY = ('if __name__ == "__main__":\n    import game\n    from game_parts import terminal\n'
           '    raise SystemExit(terminal.run(input_fn=input, print_fn=print))\n'
           "import random\nimport sys\nK = 1\ndef roll_d20():\n    return random.randint(1, 20)\ndef _session():\n    return None\n")
SHAPES = {
 "function_genexp": "import game\n\n\ndef f(text):\n    return min((p for m in \".!?\" if (p := text.find(m)) >= 0), default=0)\n",
 "function_listcomp": "import game\n\n\ndef f(text):\n    return [p for m in \".!?\" if (p := text.find(m)) >= 0]\n",
 "module_genexp": "import game\n\nFIRST = min((p for m in \".!?\" if (p := \"a.b\".find(m)) >= 0), default=0)\n",
 "module_listcomp": "import game\n\nFIRST = [p for m in \".!?\" if (p := \"a.b\".find(m)) >= 0]\n",
}
for key, part in SHAPES.items():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for rel, text in {"game.py": GAME_PY, "game_parts/__init__.py": "import game\n", "game_parts/p.py": part}.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(text, encoding="utf-8")
        f = [x for x in audit(d, TARGETS, ALLOWED, ALLOW, CHARS) if not x.startswith("R8 ")]
        print(key, f)
print("PY", sys.version.split()[0])

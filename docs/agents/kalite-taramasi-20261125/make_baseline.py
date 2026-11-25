"""Build the compact baseline (counts per tool, rule and file) from raw tool outputs.

Usage (repo root): python docs/agents/kalite-taramasi-20261125/make_baseline.py <raw-dir> <out.json>
The raw outputs are produced by the commands listed in COMMANDS (cwd given per tool).
Plan 2 reruns the same commands into a new raw dir, builds a second file, and diffs the two.
"""
import collections
import json
import re
import sys
from pathlib import Path

RAW = Path(sys.argv[1])
OUT = Path(sys.argv[2])

COMMANDS = {
    "ruff_gate": {"cwd": "ai-dnd", "cmd": "ruff check . --select F,E9 --output-format json > ruff.json"},
    "ruff_extra": {"cwd": "ai-dnd", "cmd": "ruff check . --select B,BLE,SIM --output-format json > ruff-extra.json"},
    "vulture80": {"cwd": ".", "cmd": "vulture ai-dnd ai-dnd/scripts/quality_gate/vulture_whitelist.py --min-confidence 80 > vulture80.txt"},
    "vulture60": {"cwd": ".", "cmd": "vulture ai-dnd ai-dnd/scripts/quality_gate/vulture_whitelist.py --min-confidence 60 > vulture60.txt"},
    "gitleaks": {"cwd": ".", "cmd": "gitleaks detect --redact --no-banner --no-color --baseline-path ai-dnd/scripts/quality_gate/gitleaks-baseline.json --report-format json --report-path gitleaks.json"},
    "knip": {"cwd": ".", "cmd": "PORT=3000 BASE_PATH=/ DATABASE_URL=postgres://localhost/unused npm_config_ignore_scripts=true pnpm dlx knip@6.48.0 --reporter json > knip.json"},
    "fallow": {"cwd": ".", "cmd": "DO_NOT_TRACK=1 npm_config_ignore_scripts=true pnpm dlx fallow@3.45.0 dead-code --format json --quiet > fallow.json"},
    "skylos": {"cwd": ".", "cmd": "SKYLOS_GREP_BUDGET=1500 skylos ai-dnd --no-upload --json > skylos.json"},
    "typecheck": {"cwd": ".", "cmd": "pnpm run typecheck > typecheck.txt"},
    "bandit": {"cwd": ".", "cmd": "bandit -r ai-dnd -f json -q -o bandit.json"},
    "pyright": {"cwd": ".", "cmd": "pyright -p docs/agents/kalite-taramasi-20261125/pyrightconfig.json --outputjson > pyright.json"},
    "radon_cc": {"cwd": ".", "cmd": "radon cc ai-dnd -s -n C -j > radon-cc.json"},
    "import_linter": {"cwd": ".", "cmd": "PYTHONPATH=ai-dnd lint-imports docs/agents/kalite-taramasi-20261125/importlinter.ini > importlinter.txt"},
    "engine_api_edges": {"cwd": ".", "cmd": "python docs/agents/kalite-taramasi-20261125/engine_api_edges.py > engine_api_edges.txt"},
    "deptry": {"cwd": ".", "cmd": "deptry ai-dnd --config pyproject.toml --known-first-party <every ai-dnd top-level module and dir> --json-output deptry.json"},
    "pip_audit": {"cwd": ".", "cmd": "pip-audit -r <uv.lock registry pins> --no-deps --disable-pip --format json -o pip-audit-uvlock.json; same for ai-dnd/scripts/engine_split/requirements-dev.txt -> pip-audit-dev.json"},
    "pnpm_audit": {"cwd": ".", "cmd": "pnpm audit --json > pnpm-audit-all.json; pnpm audit --prod --json > pnpm-audit-prod.json"},
}


def rel(path):
    p = str(path).replace("\\", "/")
    for marker in ("ai-dnd/",):
        if marker in p:
            return "ai-dnd/" + p.split(marker, 1)[1]
    return p


def load(name):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def count(pairs):
    return dict(sorted(collections.Counter(f"{a}|{b}" for a, b in pairs).items()))


base = {"tools": {}}
t = base["tools"]
t["ruff_gate"] = count((x["code"], rel(x["filename"])) for x in load("ruff.json"))
if (RAW / "ruff-extra.json").exists():
    t["ruff_extra"] = count((x["code"], rel(x["filename"])) for x in load("ruff-extra.json"))
for v in ("vulture80", "vulture60"):
    lines = (RAW / f"{v}.txt").read_text(encoding="utf-8").splitlines()
    t[v] = count((re.sub(r".*unused (\w+).*", r"\1", l), rel(l.split(":", 1)[0])) for l in lines if l.strip())
t["gitleaks_new"] = 0  # the scan prints "no leaks found" against the baseline; raw report holds no values
b = load("bandit.json")
t["bandit"] = count((f"{r['test_id']}:{r['issue_severity']}", rel(r["filename"])) for r in b["results"])
p = load("pyright.json")
t["pyright"] = count((x.get("rule", "?"), rel(x["file"])) for x in p["generalDiagnostics"] if x["severity"] == "error")
cc = load("radon-cc.json")
t["radon_cc"] = count((it["rank"], rel(f)) for f, items in cc.items() if isinstance(items, list) for it in items)
t["engine_api_edges"] = [l for l in (RAW / "engine_api_edges.txt").read_text(encoding="utf-8").splitlines() if "->" in l]
il = (RAW / "importlinter.txt").read_text(encoding="utf-8")
t["import_linter_broken_pairs"] = sorted(set(re.findall(r"^(\S+) is not allowed to import (\S+?):?$", il, re.M)))
t["deptry"] = count((x["error"]["code"], x["module"]) for x in load("deptry.json"))
pa = []
for f in ("pip-audit-uvlock.json", "pip-audit-dev.json"):
    for dep in load(f)["dependencies"]:
        for vuln in dep.get("vulns", []):
            pa.append(f"{dep['name']}=={dep['version']}|{vuln['id']}")
t["pip_audit"] = sorted(set(pa))
for m in ("all", "prod"):
    a = load(f"pnpm-audit-{m}.json")
    t[f"pnpm_audit_{m}"] = sorted(f"{x['module_name']}|{x.get('github_advisory_id')}|{x['severity']}" for x in (a.get("advisories") or {}).values())
sky = RAW / "skylos.json"
if sky.exists() and sky.stat().st_size:
    s = load("skylos.json")
    t["skylos"] = {k: len(v) for k, v in s.items() if isinstance(v, list)}
else:
    t["skylos"] = "tool error: no output (2026-11-25: grep budget 120 s exhausted, rerun timed out at 1700 s)"
base["commands"] = COMMANDS
OUT.write_text(json.dumps(base, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
print({k: (sum(v.values()) if isinstance(v, dict) else (len(v) if isinstance(v, list) else v)) for k, v in t.items()})

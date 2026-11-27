"""Retain this pass's actual evidence without changing historical records."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, "ai-dnd/scripts")
from run_regression_evidence import source_snapshot, now

ROOT = Path("ai-dnd/docs/evidence/development-runs/package2-closeout-20261005")
OUT = ROOT / "closeout"
OUT.mkdir(exist_ok=False)
start = json.loads(Path("/tmp/package2-closeout-start.json").read_text())
(OUT / "initial-source.json").write_text(json.dumps(start, indent=2))
snap = source_snapshot(ROOT)
(OUT / "final-tested-source.json").write_text(json.dumps(snap, indent=2))
shutil.copyfile(".local/closeout-http.py", OUT / "verify-http.py")
shutil.copyfile(".local/retain-closeout.py", OUT / "retain-evidence.py")
attempts = []
for name in ("first", "natural", "native-qwen", "fixed", "final", "accepted", "validated"):
    src = Path("/tmp/package2-http-" + name)
    if not src.exists():
        continue
    dest = OUT / ("http-" + name)
    shutil.copytree(src, dest)
    result = json.loads((dest / "live-http.json").read_text())
    attempts.append({"path": str(dest.relative_to(ROOT)), "reported_status": result["status"],
                     "accepted": result["status"] == "PASS" and name == "validated",
                     "limitation": (
                         "HTTP-200/replay-only trading checks were insufficient: both sell operations "
                         "were rejected. Original reported PASS is retained, NOT accepted."
                         if name == "final" else
                         "Setup rejected before gameplay/model" if name in ("first", "natural") else
                         "See retained failure; never retroactively certified" if result["status"] != "PASS"
                         else "Canonical movement, explicit consent, actual payments and receipts checked")})

# Only this pass's drained FastAPI workflow logs, never user save exports.
logs = sorted(Path("/tmp/logs").glob("artifactsai-dnd-web_AI-DND_FastAPI_20261005_11*.log"))
telemetry = []
for src in logs:
    shutil.copyfile(src, OUT / src.name)
    pending, starts = None, 0
    for line in src.read_text().splitlines():
        if "Ollama chat request started" in line:
            starts += 1
        match = re.search(r"Game turn completed \(model=qwen3:8b, model_calls=(\d+)", line)
        if match:
            pending = int(match.group(1))
        access = re.search(r'POST /api/game/sessions/([^/]+)/turn HTTP/1.1" (\d+)', line)
        if access:
            telemetry.append({"log": src.name, "session_id": access.group(1),
                              "http_status": int(access.group(2)), "completion_model_calls": pending,
                              "chat_starts_since_previous_turn_access": starts})
            pending, starts = None, 0

records = []
for p in ROOT.glob("*/run.json"):
    r = json.loads(p.read_text())
    records.append({"path": str(p.relative_to(ROOT)), "kind": r.get("evidence_kind"),
                    "started_at": r["started_at"], "status": r["status"],
                    "exit_status": r["exit_status"], "aggregate": r.get("aggregate"),
                    "source_changed_during_run": r.get("source_changed_during_run"),
                    "result": r.get("result")})
gates = sorted((r for r in records if r["kind"] == "final_gate"), key=lambda r: r["started_at"])
gate = json.loads((ROOT / gates[-1]["path"]).read_text())
changed = [f for f in snap["files"] if
           {i["path"]: i["sha256"] for i in gate["source_end"]["files"]}.get(f["path"]) != f["sha256"]]
assert not changed, [r["path"] for r in changed]
assert start["head"] == snap["revision"], "HEAD changed during closeout"
runtime = [f for f in snap["files"] if
           f["path"].startswith(("ai-dnd/", "artifacts/ai-dnd-experience/src/")) and
           f["path"].endswith((".py", ".ts", ".tsx")) and "/docs/" not in f["path"]]
manifest = {
    "evidence_kind": "Package2 bounded V1 exact-HEAD closeout", "created_at": now(),
    "historical_certification": False, "initial_head": start["head"], "final_head": snap["revision"],
    "initial_branch": start["branch"], "initial_tree_clean": not start["status_porcelain"],
    "final_git_status_before_docs": subprocess.check_output(
        ["git", "--no-optional-locks", "status", "--porcelain=v1"], text=True),
    "source_stability": {
        "final_source_matches_last_gate": True,
        "last_gate_changed_during_run": gate["source_changed_during_run"],
        "runtime_test_frontend_fingerprints": runtime,
        "scope": "HEAD + uncommitted P1 corrections; NOT a clean committed-HEAD certificate"},
    "records": records, "http_attempts": attempts, "actual_model_telemetry": telemetry,
    "repository_gate": {"path": gates[-1]["path"], "result": gate["result"],
                        "blocking_checks": [x for x in gate["checks"]
                                            if x["required"] and x["status"] != "PASS"]},
    "server_identity": {"method": "managed 8008 workflow restarted after each runtime correction",
                        "evidence": "retained FastAPI startup PID, /proc cwd/cmdline and proxied access logs",
                        "remote_published_server": "NOT CERTIFIED"},
    "limitations": [
        "Only disposable campaigns created by this pass were read and deleted.",
        "Raw synthetic player inputs/narration are separate narration-review files.",
        "Boundary fixtures prove accessibility/defeat consumers, not fresh combat/container producers.",
        "Repository policy and clean-tree requirements were not relaxed.",
        "No commit/push/merge/force-push/rebase/amend.",
    ],
}
pid = sys.argv[1]
manifest["server_identity"]["current_process"] = {
    "pid": int(pid), "cwd": str(Path("/proc", pid, "cwd").resolve()),
    "cmdline": Path("/proc", pid, "cmdline").read_bytes().replace(b"\0", b" ").decode(),
    "stat": Path("/proc", pid, "stat").read_text(),
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
hashes = {}
for p in sorted(ROOT.rglob("*")):
    if p.is_file() and p != OUT / "checksums.json":
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
(OUT / "checksums.json").write_text(json.dumps(hashes, indent=2))
print(json.dumps({"path": str(OUT), "files_hashed": len(hashes),
                  "last_gate": gates[-1]["path"], "http_attempts": attempts}, ensure_ascii=False))

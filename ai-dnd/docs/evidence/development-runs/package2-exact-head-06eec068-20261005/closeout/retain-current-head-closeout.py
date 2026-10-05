"""Seal only newly executed exact-HEAD results; do not alter older records."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, "ai-dnd/scripts")
from run_regression_evidence import now, source_snapshot

start = json.loads(Path("/tmp/package2-exact-head-start.json").read_text())
root = Path(start["archive_root"])
out = root / "closeout"
out.mkdir(exist_ok=True)
assert not any(out.iterdir()), "Never overwrite a retained closeout"
head = subprocess.check_output(["git", "--no-optional-locks", "rev-parse", "HEAD"], text=True).strip()
final = source_snapshot(root)
assert head == start["head"] == final["revision"]
assert final["working_tree_sha256"] == start["source"]["working_tree_sha256"]
records = []
for path in sorted(root.glob("*/run.json")):
    row = json.loads(path.read_text())
    assert row["status"] == "completed"
    assert row["source_start"]["revision"] == row["source_end"]["revision"] == head
    assert row["source_changed_during_run"] is False
    assert row["source_start"]["working_tree_sha256"] == final["working_tree_sha256"]
    assert row["source_end"]["working_tree_sha256"] == final["working_tree_sha256"]
    if row["evidence_kind"] == "suite_run":
        assert row["exit_status"] == 0 and row["aggregate"]["failures"] == 0
        assert row["aggregate"]["errors"] == row["aggregate"]["skips"] == 0
    records.append({"path": str(path.relative_to(root)), "kind": row["evidence_kind"],
                    "source_revision": row["source_start"]["revision"],
                    "started_at": row["started_at"], "ended_at": row["ended_at"],
                    "exit_status": row["exit_status"], "aggregate": row.get("aggregate"),
                    "result": row.get("result")})
gate_path = next(root / r["path"] for r in records if r["kind"] == "final_gate")
gate = json.loads(gate_path.read_text())
assert all(x["status"] == "PASS" for x in gate["checks"] if x["name"].startswith("frontend_"))
frontend_log = (gate_path.parent / "output.log").read_text()
assert re.search(r"tests 57\b", frontend_log) and re.search(r"pass 57\b", frontend_log)
assert sorted(r["aggregate"]["tests_run"] for r in records if r["aggregate"]) == [78, 161, 299]
for name in ("targeted", "integration", "regression"):
    count = {"targeted": 78, "integration": 299, "regression": 161}[name]
    assert sum(r["aggregate"] is not None and r["aggregate"]["tests_run"] == count for r in records) == 1

shutil.copyfile("/tmp/package2-exact-head-start.json", out / "initial-source.json")
(out / "final-source.json").write_text(json.dumps(final, indent=2))
for label, src in (("natural-transfer", "/tmp/package2-current-head-http"),
                   ("ground-loot", "/tmp/package2-current-head-loot")):
    shutil.copytree(src, out / label)
    data = json.loads((out / label / "live-http.json").read_text())
    assert data["head"] == head and data["status"] == "PASS"
    assert all(c["status"] == "PASS" for c in data["cleanup"])
for src in (".local/closeout-http.py", ".local/current-head-ground-loot.py",
            ".local/retain-current-head-closeout.py"):
    shutil.copyfile(src, out / Path(src).name)
shutil.copyfile("/tmp/replit-screenshots/ai-dnd-experience_T9Vp.jpg", out / "current-head-preview.jpg")

raw_log = Path("/tmp/logs/artifactsai-dnd-web_AI-DND_FastAPI_20261005_121133_886_e826c335.log")
text = raw_log.read_text()
assert "Started server process [8715]" in text
shutil.copyfile(raw_log, out / "current-server.log")
natural = json.loads((out / "natural-transfer/live-http.json").read_text())
loot = json.loads((out / "ground-loot/live-http.json").read_text())
sessions = {step["path"].split("/")[2] for r in (natural, loot) for step in r["steps"]
            if step["path"].startswith("/sessions/")}
telemetry = []
pending, starts = None, 0
for line in text.splitlines():
    if "Ollama chat request started" in line:
        starts += 1
    match = re.search(r"Game turn completed \(model=qwen3:8b, model_calls=(\d+)", line)
    if match:
        pending = int(match.group(1))
    access = re.search(r'POST /api/game/sessions/([^/]+)/turn HTTP/1.1" (\d+)', line)
    if access:
        if access.group(1) in sessions:
            telemetry.append({"session_id": access.group(1), "http_status": int(access.group(2)),
                              "completion_model_calls": pending, "actual_chat_starts": starts})
        pending, starts = None, 0
assert all(t["actual_chat_starts"] <= 2 for t in telemetry)
assert sum(t["actual_chat_starts"] for t in telemetry) == 4
assert sum(t["actual_chat_starts"] == 2 for t in telemetry) == 2
pid = "8715"
identity = {"pid": int(pid), "cwd": str(Path("/proc", pid, "cwd").resolve()),
            "cmdline": Path("/proc", pid, "cmdline").read_bytes().replace(b"\0", b" ").decode(),
            "stat": Path("/proc", pid, "stat").read_text(),
            "method": "Managed 8008 backend restarted after current-HEAD/start capture; workspace "
                      "runtime stayed exact-HEAD identical; own-session proxied access and adapter "
                      "logs independently tie live requests to this process.",
            "published_server": "NOT VERIFIED"}
assert identity["cwd"].endswith("/ai-dnd") and "--port 8008" in identity["cmdline"]
git_status = subprocess.check_output(
    ["git", "--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=all"], text=True)
assert all(line[3:].startswith(str(root) + "/") for line in git_status.splitlines())

manifest = {
    "created_at": now(), "evidence_kind": "NEW current exact-HEAD Package2 bounded V1 closeout",
    "historical_certification": False, "branch": start["branch"], "initial_head": start["head"],
    "final_head": head, "initial_working_tree_clean": start["working_tree"] == "",
    "source_sha256": final["working_tree_sha256"], "source_unchanged": True,
    "production_test_frontend_edits": [], "source_matches_current_commit": True,
    "records": records, "server_identity": identity, "actual_server_model_telemetry": telemetry,
    "live_http": {"natural_transfer": "PASS", "merchant_reward_replay_resume_isolation": "PASS",
                  "ground_drop_take_replay_conflict_equipment": "PASS"},
    "rollback_save_compatibility": {
        "method": "NEW current-HEAD full API contracts and persistence/legacy-save suite",
        "live_storage_failure_injection": "NOT PERFORMED",
        "scope": "Existing autosave owner fault injection, atomic receipts, inventory/consent/"
                 "equipment/RNG restoration, resume and cross-session boundaries"},
    "loot_boundaries": {"ground_producer_consumer_real_http": "PASS",
                        "corpse_container_consumers": "PASS via existing owner-boundary fixtures",
                        "fresh_combat_defeat_or_arbitrary_container_producer": "NOT CLAIMED"},
    "known_new_gameplay_p0_p1": [], "package2_bounded_v1_decision": "READY/COMPLETE",
    "repository_release_decision": gate["result"],
    "gate_path": str(gate_path.relative_to(root)),
    "gate_blocking_checks": [x for x in gate["checks"] if x["required"] and x["status"] != "PASS"],
    "gate_live_checks": "NOT RUN by gate; separate NEW live records above",
    "git_history_actions_this_pass": "No commit/checkpoint/push/merge/rebase/force-push/amend",
    "final_working_tree": "Only newly requested evidence under archive root; no cleanup or ignore edits",
    "unverified": ["GitHub Actions", "published-server revision", "excluded future gameplay"],
    "no_future_scope_started": True,
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
summary = f"""# Package #2 current exact-HEAD closeout

New evidence only; historical PASS/NO-GO records were not rewritten.

- **Bounded Equipment, Loot & Economy V1: READY/COMPLETE.**
- **Repository/release gate: {gate['result']}; not authorized for release.**
- Branch: `{start['branch']}`; start/final HEAD: `{head}`.
- Initial working tree clean; final runtime/test/frontend unchanged and identical to HEAD.
- Source SHA-256: `{final['working_tree_sha256']}`.
- No new known gameplay P0/P1 in the exercised bounded scope.

## Newly executed on this HEAD

| Verification | Result |
|---|---|
| Targeted | 78/78 PASS |
| Integration | 299/299 PASS |
| Gate selected regression | 161/161 PASS |
| Frontend libraries/typecheck | PASS |
| Frontend tests/build | 57/57 PASS / PASS |
| Real Qwen + HTTP natural-language NPC-to-player transfer (#75) | PASS |
| Real HTTP native ground-loot drop/take producer/consumer | PASS |
| Source stability | PASS for all three suites and gate |

`manifest.json` links each new execution record and full gate checks.
The real #75 run used an actual Python-created NPC-owned Club instance,
explicit Python consent, same-ID one-time movement and source-hand cleanup.
Receipt replay did not transfer/pay again; a changed payload with the same
action ID returned 409. A second campaign could not import the first campaign's
item/consent. No stock or model proposal was injected into live acceptance.

Actual server logs show two model calls for each natural input and zero for
native commands, including ground loot; replay makes no model call.
Max-two-call and rejected-narration/no-retry contracts ran in the new regression.
Merchant sell/buy/sell and funded once-only reward conserve 1800 CP:
player 800 -> 805 -> 605 -> 705 -> 805, NPC 1000 -> 995 -> 1195 -> 1095 -> 995.
Ground drop/take moved the same real instance once with unchanged wallets,
consistent equipped references, exact replay and changed-payload conflicts.

Save-failure rollback is covered through current-HEAD full API contracts using
the existing autosave owner, not production SQLite fault injection.
Current-HEAD persistence tests cover atomic receipts, session/RNG isolation,
legacy-save upgrade and resume. Corpse/open-container consumers use the existing
authoritative defeat/accessibility boundary fixtures, not a claimed new combat
or container producer. Unknown ownership, prices and future mechanics remain
fail-closed; no gameplay feature or parallel owner was added.

The unmodified gate remains NO-GO for its unchanged infrastructure-only scope
comparison and tree entries consisting solely of newly generated suite evidence
at gate start/end; there is no dirty production source. These policy/evidence
checks are not relabeled as PASS and no cleanup, ignore edit or policy bypass
was used. Bounded feature completion is not repository/release approval.

Evidence is only under this new package directory. Synthetic raw narration is
separate in each `narration-review.json`; checksums cover all retained files.
Only this pass's own three disposable campaigns were read/deleted via normal
APIs. The current backend PID is 8715, independently tied to its own-session
access and adapter logs; no published server identity is asserted.

No manual commit/checkpoint, push, merge, rebase, force push or amend was made.
HEAD stayed unchanged through closeout; older records remain historical.
No later package, mission, gameplay scope or GitHub Actions run was started.
"""
(out / "SUMMARY.md").write_text(summary)
hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(root.rglob("*")) if p.is_file() and p != out / "checksums.json"}
(out / "checksums.json").write_text(json.dumps(hashes, indent=2))
print(json.dumps({"head": head, "source_unchanged": True, "files": len(hashes),
                  "summary": str(out / "SUMMARY.md"),
                  "feature": manifest["package2_bounded_v1_decision"],
                  "repository_gate": gate["result"]}))

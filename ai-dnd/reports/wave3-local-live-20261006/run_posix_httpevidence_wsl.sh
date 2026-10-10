#!/usr/bin/env bash
set -euo pipefail
SRC=/mnt/c/Users/Kadir/Desktop/AI-DND-pre04-wave3/ai-dnd
DST=/tmp/ai-dnd-posix-evidence
REPORT=/mnt/c/Users/Kadir/Desktop/AI-DND-pre04-wave3/ai-dnd/reports/wave3-local-live-20261006

rm -rf "$DST"
mkdir -p "$DST"
rsync -a \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude 'node_modules' \
  --exclude 'reports' \
  --exclude '.venv' \
  --exclude 'venv' \
  "$SRC/" "$DST/"

cd "$DST"
git init -q
git config user.email "posix-evidence@local"
git config user.name "POSIX Evidence"
git add -A
# Avoid host-side commit trailer injection; plain commit message only.
git -c "trailer.ifexists=doNothing" commit -qm "posix evidence fixture"
echo "=== git ok ==="
git rev-parse --show-toplevel

echo "=== run 2 tests ==="
set +e
python3 -m unittest \
  api.tests.test_http_acceptance_evidence.HttpEvidenceTests.test_sigterm_has_end_time_and_actual_exit_status \
  api.tests.test_http_acceptance_evidence.HttpEvidenceTests.test_hard_kill_leaves_identifiable_incomplete_record_never_pass \
  -v 2>&1 | tee "$REPORT/posix_httpevidence_wsl.log"
EXIT=${PIPESTATUS[0]}
set -e
echo "EXIT=$EXIT"

python3 - <<'PY' > "$REPORT/evidence_posix_httpevidence_wsl.json"
import json, platform, subprocess, pathlib
log = pathlib.Path("/mnt/c/Users/Kadir/Desktop/AI-DND-pre04-wave3/ai-dnd/reports/wave3-local-live-20261006/posix_httpevidence_wsl.log").read_text(errors="replace")
wsl = subprocess.check_output(["wsl.exe", "-l", "-v"], text=True, errors="replace") if False else ""
status = "PASS" if "OK" in log and "FAILED" not in log and "ERROR" not in log else "FAIL"
# Prefer exit from marker line written by shell after this script portion — set below via env
import os
exit_code = int(os.environ.get("POSIX_EXIT", "1"))
out = {
  "status": "PASS" if exit_code == 0 else "FAIL",
  "exit_code": exit_code,
  "platform": platform.platform(),
  "python": platform.python_version(),
  "workdir": "/tmp/ai-dnd-posix-evidence",
  "note": "Copied ai-dnd to native Linux FS + git init because Windows worktree gitdir is not resolvable under /mnt/c",
  "tests": [
    "HttpEvidenceTests.test_sigterm_has_end_time_and_actual_exit_status",
    "HttpEvidenceTests.test_hard_kill_leaves_identifiable_incomplete_record_never_pass",
  ],
  "log_path": "posix_httpevidence_wsl.log",
  "log_tail": log[-2500:],
}
print(json.dumps(out, indent=2))
PY

# rewrite JSON with real exit
POSIX_EXIT="$EXIT" python3 - <<'PY'
import json, os, platform, pathlib
report = pathlib.Path("/mnt/c/Users/Kadir/Desktop/AI-DND-pre04-wave3/ai-dnd/reports/wave3-local-live-20261006")
log = (report / "posix_httpevidence_wsl.log").read_text(errors="replace")
exit_code = int(os.environ["POSIX_EXIT"])
out = {
  "status": "PASS" if exit_code == 0 else "FAIL",
  "exit_code": exit_code,
  "platform": platform.platform(),
  "python": platform.python_version(),
  "distro": "Ubuntu-24.04 (WSL2)",
  "workdir": "/tmp/ai-dnd-posix-evidence",
  "note": "Copied ai-dnd to native Linux FS + git init because Windows worktree gitdir is not resolvable under /mnt/c",
  "tests": [
    "HttpEvidenceTests.test_sigterm_has_end_time_and_actual_exit_status",
    "HttpEvidenceTests.test_hard_kill_leaves_identifiable_incomplete_record_never_pass",
  ],
  "log_path": str(report / "posix_httpevidence_wsl.log"),
  "log_tail": log[-2500:],
}
(report / "evidence_posix_httpevidence_wsl.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps({"status": out["status"], "exit_code": exit_code}))
PY
exit "$EXIT"

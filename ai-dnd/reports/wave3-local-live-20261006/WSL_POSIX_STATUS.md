# WSL / POSIX (B) — status

**Date:** 2026-10-06  
**Result:** PASS — 2 POSIX HttpEvidenceTests

## Environment
- WSL2 + Ubuntu-24.04 (`wsl -l -v` → Running/Stopped VERSION 2)
- Python 3.12.3
- Workdir for tests: `/tmp/ai-dnd-posix-evidence` (native Linux FS copy + local `git init`)
- Reason for copy: Windows worktree `.git` points at `C:/Users/...` and is not resolvable under `/mnt/c`

## Tests
- `HttpEvidenceTests.test_sigterm_has_end_time_and_actual_exit_status` → ok
- `HttpEvidenceTests.test_hard_kill_leaves_identifiable_incomplete_record_never_pass` → ok

## Artifacts
- `posix_httpevidence_wsl.log`
- `evidence_posix_httpevidence_wsl.json` (status PASS, exit_code 0)
- `run_posix_httpevidence_wsl.sh`

## A (for GO context)
Rejected narration live: **PASS** — `evidence_rejected_narration_live.json` (1 model turn, budget 3 remaining).

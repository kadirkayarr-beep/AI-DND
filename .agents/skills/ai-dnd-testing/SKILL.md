---
name: ai-dnd-testing
description: How to run AI-DND product tests safely (guarded WSL launcher, targeted modules, whole suite, web tests, codegen). Use when running, debugging or interpreting tests in ai-dnd/.
---

# AI-DND testing

Current rules (2026-11-03). The full contract is `C:\Users\Kadir\Desktop\AI-DND-TOOLS\NIGHT_BRIEF.md`.

Run from Git Bash, with `T=/c/Users/Kadir/Desktop/AI-DND-TOOLS`:

| Goal | Command |
|------|---------|
| Targeted modules | `bash "$T/slot.sh" 2 AI-DND-c-merge test LABEL 600 api.tests.test_x api.tests.test_y` |
| Whole suite (over 25 minutes; run in the background) | `bash "$T/slot.sh" 2 AI-DND-c-merge par PREFIX 3 2400 '^test_'` |
| tsc and web tests | `bash "$T/slot.sh" 2 AI-DND-c-merge node` |
| After an OpenAPI change | `bash "$T/slot.sh" 2 AI-DND-c-merge codegen` |

## Rules
- Product tests run only through the guarded launcher in WSL. Never run them with plain Windows Python or `dev.ps1`. Never modify `linux_guarded_launcher.py` or the guard.
- `slot.sh` stages `ai-dnd content lib artifacts start_local.ps1` so the test sees your working-tree edits. `NOSTAGE=1` tests HEAD.
- Slots 1, 2 and 3 exist; use one slot per session.
- While fixing, run the targeted modules. Run the whole suite once per task at the end, in the background, and do not batch it with edits.
- Never delete or skip a test to save time. Never push or reset git to "fix" tests.
- Branch: `task/c-series-merge`.

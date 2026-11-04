# Night brief, 2026-10-31

Project: AI-DND, a Turkish D&D 2024 game with an AI DM (FastAPI, React, local Gemma via Ollama). The owner approved this work overnight with no further questions.

## Read first
- `C:\Users\Kadir\Desktop\AI-DND-b01-isolated\OYUN_TARIFI_KADIR_20261031.md`: what the owner wants. Examples are illustrations; never script them into the game.
- `C:\Users\Kadir\Desktop\AI-DND-b01-isolated\OLCUM_20TUR_20261031.md`: the 20-turn measurement.
- `C:\Users\Kadir\Desktop\AI-DND-b01-isolated\SIKAYET_IZLEME_20261031.md`: 43 traced findings with file:line, root cause and smallest fix. Line numbers can drift; verify before editing.
- Jarvis's cases: `C:\Users\Kadir\Desktop\AI-DND-JARVIS-DORT-IS-20261030\00B_OYUNCU_DENEYIMI_RUYA_KARAKTER_TR.md` (R01-R10). Never send `gm_only/` content to the narrator.

## Where
Worktree `C:\Users\Kadir\Desktop\AI-DND-c-merge`, branch `task/c-series-merge`. Only one writer at a time works there. Do not touch `main`, do not merge, do not push (the main session pushes backups). No book text in the repo. No secrets. Commit messages are plain English, one sentence, with no attribution or co-author lines. Commit each fix separately.

## Rules of the design
- Minimal AI blocking: repair over reject, a natural reply over a mechanical refusal. K2 (owner, 2026-11-03, "Yap, esnet"): the old "do not add new rejecting validators" rule is relaxed. A money or item result with no backing (no confirmed offer, no engine acceptance) may be stopped. A creative player attempt is never blocked as if it were a system error. New word lists remain forbidden.
- The "Real Gemma turns, no guard" line below is not an authorisation for the step-0 money work (ADIM0_PLAN_V4): that work uses only fake models, temp databases and the guarded launcher.
- Python owns state. Narration never decides money, location, locks, success or secrets.
- A plausible failure is fine. A refusal to process the attempt is not.
- Never decide what the player feels or does.
- Prefer deleting special cases and using an existing owner over adding a new layer.
- When a test pins behaviour the owner explicitly rejected (such as the first inn always being locked), change that test and state why in the commit message. Never loosen a test just to pass.

## Testing
TDD: failing test first, watch it fail, fix, watch it pass.
Python product tests run ONLY through the guarded launcher in WSL, through these commands from Git Bash, with `S=/c/Users/Kadir/AppData/Local/Temp/claude/C--Users-Kadir-Desktop-AI-DND-b01-isolated/c134425a-5bcb-4c1a-acea-0872e07e0766/scratchpad/stage`:
- `bash "$S/slot.sh" 2 AI-DND-c-merge test LABEL 600 api.tests.test_x test_y`
- `bash "$S/slot.sh" 2 AI-DND-c-merge par PREFIX 3 1500 '^test_'` for the whole suite (about 25 minutes); run in the background.
- `bash "$S/slot.sh" 2 AI-DND-c-merge node` for tsc and web tests, and `... codegen` after an OpenAPI change.
`slot.sh` stages `ai-dnd content lib artifacts start_local.ps1` so the test sees your edits. `NOSTAGE=1` tests HEAD. Never modify `linux_guarded_launcher.py` or the guard. Do not run product tests with plain Python. Known baseline at `cba0408`: 5121 tests, 0 failing, 166 skipped.

## Real play check
Real Gemma turns, no guard (not a product test): from `ai-dnd`, `python "$S/m20_harness.py" "$S/OUT_DIR"`, then read `OUT_DIR/main.turns.json`. Use a new OUT_DIR name per run. Print with UTF-8. Ollama is on the Windows host. Only one process may use the GPU at a time.

## Report
Keep it short: commits, what the tests and the real play check showed, what you could not verify. Never claim acceptance.

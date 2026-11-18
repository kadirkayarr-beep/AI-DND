# game.py Split, Plan 2 (missing nets N4/N7, then T3 leaves: tables, schemas, text_rules_a/b, to spec TM2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gate gap Plan 1 left open (no N4, no N7, no ruff, "flag on" suites that ran flag off), then move the leaf data and the closed pure text helpers out of `ai-dnd/game.py` into `game_parts/tables.py`, `schemas.py`, `text_rules_a.py`, `text_rules_b.py` and pass spec gate TM2.

**Architecture:** Unchanged from Plan 1: moved code lives in `ai-dnd/game_parts/`, reaches engine names as `game.X` (centre rule), `game.py` re-exports every moved name with explicit `from game_parts.<part> import ...` lines. New in this plan: two dynamic probes that run inside the guarded test child without a `.pth` file (a boot module imported first in each shard reads tokens from the run-root label), so a full suite can really run flag on, record which patches on `game` fired (N4) and which engine lines ran (N7, stdlib `sys.monitoring`).

**Tech Stack:** Python stdlib (`ast`, `symtable`, `tokenize`, `unittest`, `sys.monitoring`); guarded WSL runner `slot.sh`; a repo-local gate runner `slot_gate.sh`; `ruff==0.17.5` through `uvx` (second opinion only, never `--fix`/`format`).

**Spec:** `docs/superpowers/specs/2026-11-17-game-py-bolme-design.md` (approved by Kadir 2026-11-17). The spec is the authority; where this plan and the spec differ without a `Ruling` line, the spec wins. Plan 1 (`docs/superpowers/plans/2026-11-17-game-py-bolme-plan-1.md`) and its ledger (`C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t0/.superpowers/sdd/2026-11-17-game-py-bolme-plan-1/progress.md`) hold the rulings this plan builds on.

**Scope:** spec stage T3 and gate TM2, plus the debt rows whose trigger is "Plan 2 Görev 0 / ilk toplu taşıma" (D-346..D-353). T4-T7 are later plans (see "Sonraki planlar").

**Gates in this plan:** G3a = net gate (Task 8): the N4/N7 and real flag-on bases the spec wanted at TM0 and D-352 deferred to here; PR 4. TM2 = spec TM2 (Task 16); PR 5, stacked on PR 4.

**Measured base (2026-11-18, main `afe0023b`):** `ai-dnd/game.py` 24 940 lines; parts `terminal.py`, `character_rules.py` (`roll_d20`), `text_rules_a.py` (`_inside_speech`, `_SPEECH_SPAN_RE`); `_PART_MODULES = ("game_parts.character_rules", "game_parts.text_rules_a")`; comments `1083`; TM0 suite 1959 s (flag off), turn bench 21.03 / 21.14 ms; TM1 suite 1586 s, bench 21.53 / 21.78 ms.

## Global Constraints

- **Precondition:** `origin/main` contains `afe0023b` (Plan 1, PRs #128-#130). Kadir has approved this plan.
- **Finding that shapes this plan (read from the launcher, not yet seen in a test):** `linux_guarded_launcher.py` builds the test child's environment from scratch (`build_env`), so the Plan 1 prefix `WSLENV=AI_DND_FRONT_PROPOSAL AI_DND_FRONT_PROPOSAL=1` never reached the child; every "flag on" suite since TM0 ran flag off (same test and skip counts as its twin). Task 1 fixes how the flag reaches the child; Task 8 takes the first real flag-on base **before any move**. A red test in a `fon` base is pre-existing: trace it to its commit, write a debt row, tell Kadir (information, not a wait). Its id goes into the recorded set `F_fon` (ledger and `AI-DND-TOOLS/measure/engine-split/p2/F_fon.txt`; union of the failing ids of every `fon` base run). Ruling: a `fon` run passes when `failing_ids ⊆ F_fon`, every id in `F_fon` has a debt row, and (where N4 runs) `LOST` holds no id outside `F_fon` (`LOST` counts only ids `ok` in both N4 bases, Task 2; an `F_fon` id never counts as `LOST`, also one that failed only in the probe-free `p2g0-fon-a`); a red outside `F_fon` stops the plan; flag off keeps `failing_ids 0`; a `F_fon` test that reads a name of a batch holds that name (`Ruling`, name to the held table) instead of stopping the plan; Stage B may start while `F_fon` rows are open — pre-existing reds are not this plan's regression, and the spec's stop conditions do not list them — if wrong: a pre-existing flag-on fault rides one plan longer, visible in the debt register.
- **Worktrees and branches:** Stage A in `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t3n`, branch `task/game-py-bolme-t3-nets` off `origin/main`. Stage B in `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t3`, branch `task/game-py-bolme-t3` cut from the Stage A tip. Ruling: Stage B is stacked on Stage A and does not wait for PR 4's merge (Plan 1 stacked #128-#130 the same way) — the N4/N7 base is only valid while engine bytes stay equal — if wrong: bases are retaken (about 2.5 h of machine time). One writer per worktree.
- **Push, PR, merge:** only with Kadir's fresh approval for that action. No force push. Never delete a branch. After every push/merge: `gh run list --repo kadirkayarr-beep/AI-DND --limit 5`; "AI-DND bounded verification" must be green before "done". CI wait (speed rule 6): poll every 2-3 min for at most 25 min (the job's own limit is 20 min); if it has not finished by then, read it with `gh run view <id> --log-failed` (or its status) and report to Kadir; a red run is reported at once. Local work never waits for an approval; only the push does.
- **Freeze (spec decision 3):** while either branch is open, no other branch touches `ai-dnd/game.py` or `ai-dnd/game_parts/`.
- **Tests run only through the slot runner.** `SLOT` (targeted runs), `FSLOT` (full suites) and `RSLOT` (overlapping reviews in Stage A) are the slot numbers the controller is assigned in Task 0 (another session owns slots; never take one unasked). `WT` = worktree folder name only.
  - Targeted: `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <SLOT> <WT> test <label> 1800 <modules...> <NEIGHBOURS>`; pass = a line `RESULT exit=0 Ran <n> tests`.
  - `NEIGHBOURS` = `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys` (in every task's targeted run; never dropped).
  - `ENGINE_SET` = `api.tests.test_engine_parts_pilot api.tests.test_engine_routing api.tests.test_engine_surface api.tests.test_engine_patch_census api.tests.test_engine_size_budget api.tests.test_engine_hash_parts api.tests.test_engine_sources api.tests.test_engine_split_inventory` (in every Stage B targeted run).
  - Targeted run with a probe: put `api.tests.gate_boot` first in the module list and a token in the label (`-fon`, `-n4`, `-n7`).
  - Full suite: only through `bash C:/Users/Kadir/Desktop/<WT>/ai-dnd/scripts/engine_split/slot_gate.sh <FSLOT> <WT> <label> 3 3000 '.'` (Task 1); pass = `PAR_EXIT=0` and `failing_ids 0` for flag off; for flag on the `F_fon` rule above. Flag off: label without `fon`. Flag on: label with the token `fon`. The Plan 1 `WSLENV=...` prefix is void.
  - Full suites run only in Task 8 (bases) and Task 16 (TM2). Never two at once, and no other slot work while one runs (16 GB RAM; WSL crashed twice in Plan 1). No browser tests.
  - **Before every `slot_gate.sh` call:** a read-only check that no other guarded run is active on the machine: a script file (`SLOTPY` form) running `pgrep -af linux_guarded_launcher; echo "RC=$?"`; the output goes in the ledger. If a run is active: wait in a bounded loop (poll every 5 min, at most 35 min = one suite + margin), then check again; still active = ask Kadir. Prefer the time window Kadir names in Task 0.
- **Scripts that are not tests** (`SLOTPY`): after a `slot.sh ... test` call has synced the tree, run them with the slot's Python outside the guard: `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash /mnt/c/Users/Kadir/Desktop/AI-DND-k2-bolme-t3n/.superpowers/sdd/2026-11-18-game-py-bolme-plan-2/run-<name>.sh` (the ledger dir of Stage A, in both stages: the Stage B worktree has no `.superpowers/sdd` folder), where the `.sh` file holds `cd /root/aidnd-env-<SLOT>/src/ai-dnd && /root/aidnd-env-<SLOT>/proj/.venv/bin/python scripts/engine_split/<script>.py <args>; echo "RC=$?"`. Always a script file, never `bash -c '...'` (D-351: `$?` and `$var` expand on the Windows side). Output paths are `/mnt/c/Users/Kadir/Desktop/<WT>/...`.
- **Measurement store:** `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/` (approved for Plan 1 as store (c)).
- **Red first.** Every new test is seen failing for the stated reason before the change. A guard test that is green on a clean tree is shown red with a planted fault in the working tree, then restored. Restore rule (`slot.sh` stages files, so a plain `git checkout -- .` leaves the staged fault): in the exam tasks (7, 15), where the tree is clean before each fault, `git checkout HEAD -- ai-dnd`. Inside any other task, never a broad checkout: before planting, copy the one file to be planted to `<ledger dir>/pre-plant/<file name>` and record its sha256; plant; run; copy the saved file back; `git add` it if `slot.sh` had staged the fault; check the sha256 equals the recorded one and `git diff HEAD --stat` equals the one taken before planting. A file the task did not change may be restored with `git checkout HEAD -- <that file>` alone. Every new test that starts a campaign or session wraps it in `fixed_town(self, <seed>)` from `api/tests/town_seed.py`.
- **Old-behaviour tests** are rewritten only with equal strictness and get a row in `docs/agents/onay-listesi-20261115.md` (`Test | Değişiklik | İşaret`; mark "gevşetme olabilir" when a boundary moves). Unmarked loosening, skipping or deleting stops the work.
- **Findings** go to `docs/agents/debt-register.md` as rows with exactly 8 `|`. On `afe0023b` the highest id is D-353; another session may add rows in parallel, so Task 0 Step 3 first reads the highest id on `origin/main` and on the other session's open branches (read-only `git fetch` + `git grep -o "D-3[0-9][0-9]" <ref> -- docs/agents/debt-register.md`) and uses the next free id after the maximum; the ids are checked again before the PR 4 and PR 5 pushes. Below, `D-354..D-358` name the first five new rows; read them as "the next five free ids".
- **Ledger:** `.superpowers/sdd/2026-11-18-game-py-bolme-plan-2/progress.md` in the Stage A worktree (local, not committed; Stage B appends to the same file). `<ledger dir>` = `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t3n/.superpowers/sdd/2026-11-18-game-py-bolme-plan-2/` in both stages (the `SLOTPY` scripts and `pre-plant/` live there too). Decisions as `Ruling: <karar> — <neden> — <yanlışsa maliyeti>`. Each gate records N1/N4/N5/N7 output, suite seconds and the turn benchmark.
- **Review tier is by content** (spec §5, decision 11). "strong" = independent review on the strongest model. Ruling: the strongest model is the one Kadir's 2026-11-17 exception allows for the game.py split (fable); Task 0 asks him once whether that still holds for Plan 2; if he says no, strong = Opus and the ledger says `Ruling: fable yerine Opus`. "normal" = independent review on Opus for move tasks and for N3/N4/N7 code, Sonnet for the small tool tasks. Every task states tier and models. Reviews run on a `git archive <sha>` copy.
- **Speed rule 1 (overlapping review)** is used only in Stage A and only between tasks whose file lists do not overlap. The overlapping reviewer runs on `RSLOT` (if Kadir gives no third slot: on `FSLOT`, which has no full suite before Task 8), never on `SLOT`. It syncs the reviewed sha as its own worktree: `git worktree add ../AI-DND-k2-bolme-r<task> <sha>` (detached; not deleted afterwards), passed to `slot.sh` as `WT`. With neither slot free, Stage A runs strictly one task after another. In Stage B every task writes `game.py`: strictly one after the other, review finished before the next move starts.
- **Tools:** stdlib only in CI. Forbidden: `ast.unparse`, formatters, `ruff --fix`, `ruff format`, rope, libcst codegen, import-linter, desloppify. Moved source is edited in place only. `sensitivity.py --write` is never run (it refuses once `game_parts/` exists); a name leaves `sensitive.json` only as a `removed` row written by a strong reviewer.
- **Centre rule (spec §4):** a part never calls another engine function or class bare; it writes `game.X`. A constant read by code in the same part stays bare (spec §6 N3 rule 5). No part imports a sibling part or writes `from game import`. Only `game.py` imports `game_parts.*`; tests never do.
- **Never moved** (`move_block.NEVER_MOVED`, 18 names): `world_state, messages, RULE_ORDER, GameSession, _session, _bind_session_engine, create_session, _GameModule, _speech_debug_trail, DEFAULT_SAVE_PATH, start_terminal_game, _DEFAULT_SESSION, _ACTIVE_SESSION, _ENGINE_FUNCTIONS, _ENGINE_NAMESPACE, _CHARACTER_GLOBALS, _PART_MODULES, recent_dm_narrations`.
- **Never read or print key files** (`.env`, `apikeys*`, `*.pem`, `~/.aidnd-*-key`). Old saves do not matter: no compatibility work.
- **Every implementer brief** carries `docs/agents/implementer-preamble.md`, the graphify rule (`graphify query "<question>"` first; raw files only for lines the graph or an earlier read located), "a move task changes nothing else", "the prefix is added in place; source is never regenerated", and names functions and files, not line numbers. `game.py` is 24 940 lines: never read it whole.
- **Stop and ask** only for: irreversible/destructive action, security-sensitive action, side effect outside the worktree (push, merge, publish), a plan so broken every path is a guess. Everything else: decide, write a `Ruling`, continue.
- **Play gate (spec decision 7, approved: "Oynayış. TM3'te ve kapanışta 10'ar dakika yeterli mi? Öneri: evet."; spec §12: "Oynayış: TM3'te ve kapanışta, en az 10'ar dakika."):** no play gate inside Plan 2. The ledger ends with "oynayış: Plan 2'de gerekmez (karar 7)". Plan 3 (TM3) carries the next one.

## Move procedure (binding for Tasks 9-14; goes into every move brief word for word)

`B` = the batch name, `P` = the part file, `NAMES` = `/mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd/scripts/engine_split/batches/<B>.txt` (one name per line, committed in Task 6; under `ai-dnd/` because `slot.sh` does not sync `docs/`; always the absolute path, because `SLOTPY` runs with cwd `/root/aidnd-env-<SLOT>/src/ai-dnd`). `WTROOT` = `/mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd`. The mover and the checker are run from the slot copy but always against `WTROOT`; every other `SLOTPY` step reads the slot copy, so it needs a sync first.

- **M1 Base.** `BASE_SHA` = the commit right before the move. `git archive <BASE_SHA> ai-dnd/game.py ai-dnd/game_parts | tar -x -C C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/base-<B>/`.
- **M2 Measure before cutting.** For every name in `NAMES`: not in `NEVER_MOVED`, not in `sensitive.json`, still a top-level name of `game.py`. For every constant in `NAMES`: run the N8 patterns of `sensitivity.py` (money, save, snapshot, file write) over the constant's own source text; a constant with a hit **and** a reader in `sensitive.json` is held (take it out of the move, ledger line with the reason, the batch file is edited in the same commit); a hit with no sensitive reader moves and is listed in the ledger. **`F_fon` hold:** read `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/F_fon.txt`; for each id whose module is in the output of `SLOTPY inventory.py --touching <NAMES>`, read that test and hold every batch name it reads (`Ruling`, name to the held table, batch file edited in the same commit). Any other surprise (a decorator, a non-constant default, an identity name, a module-level mutation of the name) = hold that name and write a `Ruling`.
- **M3 Red test.** Add the batch's membership test (given in the task) to `api/tests/test_engine_parts_pilot.py`; run; see it fail because the names are not re-exported from the part yet.
- **M4 Move with the CLI** (`SLOTPY`): `move_block.py --game /mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd/game.py --part /mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd/game_parts/<P> --names-file /mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd/scripts/engine_split/batches/<B>.txt --census /mnt/c/Users/Kadir/Desktop/<WT>/ai-dnd/api/tests/engine_split_locks/patch_census.json --report /mnt/c/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/move-<B>.json`. Expected: `MOVED names=<n> ...`, `RC=0`. `REFUSED <reason>` (exit 2, files untouched): hold the named name, write a `Ruling`, run again. The mover runs only with the slot's Python 3.13 (`SLOTPY`), never with Windows Python 3.14: under 3.14 (PEP 649) it falsely refuses `_rumour_lane_on` and `_has_private_profile_value` with `name 'bool' missing from the symtable` (debt row, Task 0 Step 3). Review briefs say the same.
- **M5 Part header by hand.** For each stdlib or project module the moved code reads at module level or in a function body (the task lists the expected ones), copy the import statement **exactly as `game.py` spells it** (same form, same alias) to the top of the part, after `import game` when the part has functions. A data-only part has no `import game`. In-function imports move with their function untouched. `allowed_imports.json` must stay byte-equal.
- **M6 Sync, then bookkeeping in the same commit.** Sync the slot by rerunning the M3 test through `slot.sh` (expected: green now). Then: `size_budget.json` `files["game.py"]` = the new real line count of `game.py`; `surface.json` regenerated in the slot (`SLOTPY surface.py --write /mnt/c/.../ai-dnd/api/tests/engine_split_locks/surface.json`, Python 3.13 of the slot, never Windows Python). Nothing else changes: no unused import is removed from `game.py` (`tr_names`, `unicodedata` stay; ruff F401 on them is noted, not fixed).
- **M7 N5.** `SLOTPY move_check.py --base-root /mnt/c/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/base-<B>/ai-dnd --root <WTROOT> --moved-file <NAMES> --part <P> --tier <tier>`. Header import lines need no `--manual`: `move_check` already accepts import-only part lines (F16, `_import_only_lines`); a `--manual` for them exempts nothing and is a finding since Task 5. `--manual` is only for a real non-import edit the task names (Task 13: the `_PART_MODULES` base/new pair); each needs a reason. Expected: `CHANGED 0`, `RC=0`, and `--comments-only` prints `COMMENTS base=1083 now=1083`. Paste both in the ledger. `CHANGED` above zero: never patch forward and never a broad checkout (it would wipe the M2/M3 edits and leave a new part on disk); restore only what M4-M6 wrote: `git checkout HEAD -- ai-dnd/game.py ai-dnd/api/tests/engine_split_locks/size_budget.json ai-dnd/api/tests/engine_split_locks/surface.json`; an existing part with `git checkout HEAD -- ai-dnd/game_parts/<P>`; a new part (Tasks 9, 10, 13) with `git rm -f -q --ignore-unmatch ai-dnd/game_parts/<P>` and deleting the file if it is still on disk; then `git diff HEAD --stat` lists only the M2/M3 files (`test_engine_parts_pilot.py`, a held batch file), and redo from M4. The reviewer runs M7 again on the archive copy.
- **M8 N1 and N3.** `SLOTPY surface.py --diff --old <golden at BASE_SHA> --new <new golden> --moved <function names of the batch>`: no output, `RC=0` (constants have no `module` line). `SLOTPY routing_audit.py`: `clean`, `RC=0`.
- **M9 Outside-guard probe** (controller, `SLOTPY`, slot copy with the same `game.py` sha256 as the worktree): `outside_probe.py`. Expected last line `PROBE ok parts=<sorted part modules>`, `RC=0`.
- **M10 Targeted run:** `ENGINE_SET` + the modules listed by `SLOTPY inventory.py --touching <NAMES>` + the task's named modules + `NEIGHBOURS`. Expected: `RESULT exit=0`. If `test_engine_patch_census` is red only because a moved target's `kind` changed, regenerate the lock (Plan 1 Task 18 Step 8) and explain each changed target in the ledger; any other census difference stops the task.
- **M11 Commit** with the message given in the task. One move = one commit; a Step 0 tool fix from the previous review is its own earlier commit.

## Review Focus

Failure modes the spec implies but none of its listed checks exercise; each is pinned by a test or a gate step in the task named.

1. **The game Kadir actually plays runs flag on** (`api.local_play` sets `AI_DND_FRONT_PROPOSAL=1`), and no slot suite has ever run that path. A moved helper called only on the flag-on path must be exercised: `test_the_fon_token_turns_the_flag_on_inside_the_child` (Task 1) and the real flag-on bases and gate runs (Tasks 8, 16).
2. **Turkish and typographic characters in moved text** (`ğüşıöç`, `“ ” —`): a part written with a BOM, CRLF or a non-UTF-8 codec changes prompts and regexes silently on Windows. `test_the_cli_keeps_utf8_bytes_and_line_endings` (Task 5).
3. **A patch on a moved table still reaches the API readers** (`api/character_creation.py`, `api/main.py` read `game.CLASSES` / `game.RACES`): `test_a_patched_class_table_reaches_the_api_reader` (Task 9).
4. **`system_prompt` after the move:** `game.messages[0]["content"]` is still the same text object as `game.system_prompt`, and a new session's first message carries it. `test_the_system_prompt_is_one_object_for_module_and_sessions` (Task 10).
5. **Windows local play imports every part:** the slot runs Python 3.13 on Linux; Kadir starts the game with the interpreter `start_local.ps1` uses. Task 16 Step 6 runs both import orders with that interpreter.

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `ai-dnd/api/tests/gate_boot.py` | read tokens from the run-root name; turn on flag / N4 / N7 inside the guarded child. Not collected by `par` or CI (no `test_` prefix) | 1, 2, 3 |
| `ai-dnd/scripts/engine_split/slot_gate.sh` | full-suite runner: as `slot.sh ... par`, but every shard imports `api.tests.gate_boot` first | 1 |
| `ai-dnd/api/tests/engine_probe.py` | runtime hooks: `install_ledger`, `uninstall`, `install_lines`, `stop_lines` | 2, 3 |
| `ai-dnd/scripts/engine_split/ledger_diff.py` | N4 pure functions + CLI (`--collect`, `--diff`) | 2 |
| `ai-dnd/scripts/engine_split/coverage_by_function.py` | N7 pure functions + CLI | 3 |
| `ai-dnd/scripts/engine_split/routing_audit.py` | N3: six new rules (D-349) | 4 |
| `ai-dnd/scripts/engine_split/move_block.py`, `move_check.py` | CLI for the mover (D-348); four checker fixes (D-350); `--names-file` / `--moved-file` | 5 |
| `ai-dnd/scripts/engine_split/inventory.py` | scans parts; honest `closed_helpers`; `--touching` | 6 |
| `ai-dnd/scripts/engine_split/outside_probe.py` | import orders + `python game.py` start, outside the guard (D-341 helper) | 6 |
| `ai-dnd/scripts/engine_split/batches/*.txt` | the six name lists of this plan | 6 |
| `ai-dnd/game_parts/tables.py` | 20 data tables | 9 |
| `ai-dnd/game_parts/schemas.py` | 12 schema and prompt constants | 10 |
| `ai-dnd/game_parts/text_rules_a.py` | pilot + batches `text-a1`, `text-a2` (about 940 lines with header; `move()` puts a blank line between blocks) | 11, 12 |
| `ai-dnd/game_parts/text_rules_b.py` | batches `text-b1`, `text-b2` (about 1 000 lines with header) | 13, 14 |

Tests import the tooling the way `api/tests/test_engine_move_tool.py` does (copy its import header). Tooling functions take paths as arguments so tests run on small fixtures in a temp dir.

**Batches (Ruling, "Option B-hold"):** the spec sends every non-sensitive closed helper to `text_rules`. 25 of them (about 400 lines) belong by meaning to a later module (`character_rules`, `savefile`, `places`, `turn`, `combat_flow`) and would move twice. They are held in `game.py` and move once, in Plans 3-5 — it also keeps the seven save-shaped validators/filters (with `_known_happenings`, called by `_validate_save_payload` and `_repair_dilim2_fields`) and the death helper out of normal-review tasks — if wrong: those names move one plan later, no behaviour change. The full lists are in "Appendix: batch lists"; the measurement in Task 6 wins over the appendix and every difference is a `Ruling`.

---

# Stage A — nets (worktree `AI-DND-k2-bolme-t3n`, PR 4). `ai-dnd/game.py` and `ai-dnd/game_parts/` do not change in this stage.

### Task 0: Open the stage

**Review tier:** none (no code).

- [ ] **Step 1: One batched question to Kadir.** (a) slot numbers `SLOT`, `FSLOT` and a third `RSLOT` for overlapping reviews (none = `FSLOT` in Stage A, see Global Constraints), and a time window in which the other session runs no full suite; (b) news: Plan 1's flag-on suites ran flag off (Global Constraints); the first real flag-on suite may show old reds; (c) `Ruling: N7 uses stdlib sys.monitoring instead of coverage.py — the guarded child runs python -I -S, no .pth is processed, the shared venv has no pip — if wrong: one tool swap later` (spec §9 names coverage.py: this row goes on the approval list); (d) one download of `ruff==0.17.5` into the `uvx` cache (`/root/.local/bin/uvx`), outside the shared venv; if refused: "ruff koşmadı" in the ledger and the PR text, N3 rule 7 stays the lock; (e) strongest model for strong reviews: fable under the 2026-11-17 exception, or Opus; (f) 7 full suites expected, at most 12 (Task 8: 5, plus 1 under its Ruling; Task 16: 2, plus 2 probe-free if a time limit is exceeded, plus 2 if a change after the Task 16 suites forces a rerun (Task 16 Step 1b Ruling)); a move of `origin/main` under the bases adds 4. The probe suites' time is unmeasured until Task 3 Step 3.
- [ ] **Step 2:** `git fetch origin`; `git worktree add ../AI-DND-k2-bolme-t3n -b task/game-py-bolme-t3-nets origin/main`; create the ledger. Bring this plan file: `git checkout task/game-py-bolme-plan2 -- docs/superpowers/plans/2026-11-18-game-py-bolme-plan-2.md` if it is committed on that branch, else copy the file from `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-p2`; add one line for it to `docs/design/INDEX.md`. Write Kadir's Step 1 answers in the new ledger.
- [ ] **Step 3: Debt rows** (8 `|` each) in `docs/agents/debt-register.md`, ids from the free-id check in Global Constraints ("Findings"): D-354 [YÜKSEK] flag-on suites since TM0 ran flag off (launcher `build_env`; trigger: closed by Task 1 + Task 8 of this plan); D-355 [ORTA] `sensitivity.classify` scans `game.py` only, so `test_engine_sensitivity` checks nothing for a moved name (trigger: Plan 4 Görev 0, before the first sensitive move); D-356 [DÜŞÜK] no guard test against a test module putting `api/tests` on `sys.path` (trigger: next test-infrastructure work); D-357 [DÜŞÜK] rows D-079 and D-213 break the 8-pipe rule (trigger: next debt-register clean-up); D-358 [DÜŞÜK] `move_block._Scan.name` falsely refuses under Python 3.14 (PEP 649 annotation scope: `name 'bool' missing from the symtable`); the slot's 3.13 is unaffected (trigger: the slot or CI moves to 3.14). `Ruling: D-346 (live smoke scripts print a digest of game.py only) stays open with its trigger narrowed to "first work touching those scripts" — print-only, no gate reads it — if wrong: a live smoke prints a stale digest`. Edit the D-346 row's trigger text accordingly.
- [ ] **Step 4:** Run `NEIGHBOURS` once; record the seconds. Expected: `RESULT exit=0`. Commit `game.py split plan 2: plan document and debt rows D-354..D-358`.

### Task 1: The flag and the probes reach the guarded child (`gate_boot.py`, `slot_gate.sh`)

**Review tier:** normal (Sonnet implementer, Opus review). Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/api/tests/gate_boot.py`, `ai-dnd/scripts/engine_split/slot_gate.sh`
- Test: `ai-dnd/api/tests/test_engine_gate_boot.py`

**Interfaces — Produces:**
- `gate_boot.tokens(run_root: str) -> set[str]`: `set(Path(run_root).name.split("-")[1:])`; empty string gives the empty set. The run root is `<stamp>-<label>` and `par` appends `-<shard>`.
- `gate_boot.boot(run_root: str, environ=os.environ) -> set[str]`: applies the tokens it knows and returns them. In this task only `fon`: `environ["AI_DND_FRONT_PROPOSAL"] = "1"`. Tasks 2 and 3 add `n4` and `n7`. It never imports `game`.
- Importing `api.tests.gate_boot` calls `boot(os.environ.get("AI_DND_GUARD_RUN_ROOT", ""))`.
- `slot_gate.sh <FSLOT> <WT> <LABEL> <SHARDS> <TIMEOUT> <PATTERN>`: the staging, sync and shard lines of `AI-DND-TOOLS/slot.sh` and `slot_par.sh` (read both first; reuse, do not redesign), with one change: each shard's selector list starts with `api.tests.gate_boot`. Same output lines (`tests N skipped S failing_ids F`, `PAR_EXIT=`). `slot.sh` and `slot_par.sh` are not edited (shared with another session). Ruling: the runner lives in the repo, not in `AI-DND-TOOLS` — it is reviewed and versioned with the probe it serves — if wrong: move one file.

- [ ] **Step 1: Write the failing tests:**

```python
def test_tokens_come_from_the_run_root_name(self):
    self.assertEqual(gate_boot.tokens("/x/20261118T061934-p2g0-fon-n4-0"), {"p2g0", "fon", "n4", "0"})
    self.assertEqual(gate_boot.tokens(""), set())
def test_no_token_changes_nothing(self):
    env = {}
    self.assertEqual(gate_boot.boot("/x/20261118T061934-p2g0off-0", env), set())
    self.assertEqual(env, {})
def test_fon_sets_the_flag(self):
    env = {}
    self.assertEqual(gate_boot.boot("/x/20261118T061934-p2g0-fon-0", env), {"fon"})
    self.assertEqual(env, {"AI_DND_FRONT_PROPOSAL": "1"})
def test_the_fon_token_turns_the_flag_on_inside_the_child(self):      # Review Focus 1
    if "fon" not in gate_boot.tokens(os.environ.get("AI_DND_GUARD_RUN_ROOT", "")):
        self.skipTest("no fon token")       # proof: outcome ok in fon ledgers, skip in off ledgers (Task 8 Step 5 a)
    self.assertTrue(front_proposal.enabled())
def test_boot_never_imports_the_engine(self):
    # ast: gate_boot.py has no import of game or game_parts at any depth
```

- [ ] **Step 2:** Run `api.tests.test_engine_gate_boot` + `NEIGHBOURS`. Expected: FAIL (`gate_boot` does not exist).
- [ ] **Step 3:** Implement both files. Run again. Expected: `RESULT exit=0`.
- [ ] **Step 4: Proof in the child.** Targeted run with label `p2t1-fon` and modules `api.tests.gate_boot api.tests.test_engine_gate_boot` + `NEIGHBOURS`: `RESULT exit=0`. Then, in the working tree only, delete the `environ[...] = "1"` line and run the same command: expected FAIL in `test_the_fon_token_turns_the_flag_on_inside_the_child`. Restore by the pre-plant copy rule (`gate_boot.py` is new and uncommitted: a checkout from HEAD would not restore it). Record both result lines and the `env_names` list from that run's `proof.json` (it will not show the flag: the flag is set in-process; the test is the proof).
- [ ] **Step 5: Shard order.** One `slot_gate.sh` run on a small pattern (`<FSLOT> <WT> p2t1-fon-shard 3 600 'test_engine_gate_boot'`): `PAR_EXIT=0`, and each shard's `proof.json` `selectors` starts with `api.tests.gate_boot`. If the launcher imports product code before the selectors, write what it imports in the ledger (N7 then misses only import-time lines, the same in base and new).
- [ ] **Step 6: Commit** `game.py split plan 2: gate_boot and slot_gate.sh, flag on reaches the guarded child (D-354)`.

### Task 2: N4 patch-hit ledger and per-test outcome ledger (D-352, first half)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/api/tests/engine_probe.py`, `ai-dnd/scripts/engine_split/ledger_diff.py`
- Modify: `ai-dnd/api/tests/gate_boot.py` (token `n4`)
- Test: `ai-dnd/api/tests/test_engine_probe_tools.py`

**Interfaces — Produces:**
- `engine_probe.install_ledger(out_dir: Path, is_target=_is_game) -> None`: wraps `unittest.TestCase.run` (keeps the running test id on a stack: push when `run` starts, pop after it, so a tiny `TestCase` run inside a test does not take over the outer test's later records; after the run appends `{"test": id, "outcome": "ok|fail|error|skip|xfail|xpass"}`) and `unittest.mock._patch.__enter__/__exit__`. For a patch whose target object passes `is_target` it appends at `__exit__`, also when the test raised, `{"test", "target": <attribute name>, "kind", "called"}`; `kind` is `"mock"` when the entered object has a `called` attribute, else `"other"` with `called: null`. Outside a test, `test` is `<outside-test>:<file name>`. One line-buffered file per install and process: `out_dir/ledger-<pid>.jsonl` (the out dir belongs to that install).
- **Re-entrant (stack):** the full suites run this module's own tests in a shard where `gate_boot` has already installed the gate ledger. So `install_ledger` saves the three functions **as they are at that moment** (possibly an outer install's wrappers) on a module stack and wraps those; the outer ledger keeps recording through the inner one.
- `engine_probe._is_game(obj) -> bool`: a module whose `__name__ == "game"` (not identity with `sys.modules["game"]`: the surface test swaps in a fresh copy).
- `engine_probe.uninstall() -> None`: pops the top install and restores the three functions saved by that install (the state from before it), not the first originals; uninstall with an empty stack raises `RuntimeError`. An outer gate ledger stays installed and keeps its own out dir.
- `gate_boot.boot`: token `n4` calls `install_ledger(Path(run_root) / "engine-probe")`.
- `ledger_diff.merge_ledger(lines_dir: Path) -> dict[str, bool | None]` keyed `"<test>|<target>"`, `True` if any record was called.
- `ledger_diff.merge_outcomes(lines_dir: Path) -> dict[str, str]`.
- `ledger_diff.noise(a: dict, b: dict) -> list[str]`: keys whose values differ (a missing key differs).
- `ledger_diff.drops(base: dict, new: dict, noise_keys: set[str]) -> list[str]`: keys `True` in `base` and not `True` in `new`, minus noise.
- `ledger_diff.lost_tests(base: dict[str, str], new: dict[str, str], noise_keys: set[str]) -> list[str]`: ids `ok` in `base` and not `ok` in `new`, minus noise. The CLI passes `--base` as `base` and the outcome noise of `--base` vs `--base2` as `noise_keys`, so `LOST` holds only ids `ok` in both bases.
- CLI: `ledger_diff.py --collect "<runs glob>" --out <file.json>` writes `{"hits", "outcomes", "seconds": max of the shards' proof.json seconds, "tree": <sha>}`; `ledger_diff.py --diff --base A.json --base2 B.json --new C.json` prints `NOISE <n>`, `DROPS <n>` + keys, `LOST <n>` + ids; exit 1 if `DROPS` or `LOST` is above 0.

**What N4 cannot see (write it in the ledger and in both PR texts):** the 48 `not_called_tests` of the census lock, the 66 plain `game.X = ...` assignment sites, and `kind "other"` patches. N3 is their only guard.

- [ ] **Step 1: Write the failing tests** (each with the assertions named):

```python
def test_merge_keeps_true_over_false(self):                # two lines, same key, called False then True -> True
def test_noise_is_what_two_equal_runs_disagree_on(self):
    self.assertEqual(noise({"t|roll_d20": True, "u|x": True}, {"t|roll_d20": True, "u|x": False}), ["u|x"])
def test_a_patch_that_stopped_firing_is_a_drop(self):
    self.assertEqual(drops({"t|roll_d20": True}, {"t|roll_d20": False}, set()), ["t|roll_d20"])
    self.assertEqual(drops({"t|roll_d20": True}, {}, set()), ["t|roll_d20"])
    self.assertEqual(drops({"t|roll_d20": True}, {"t|roll_d20": False}, {"t|roll_d20"}), [])
def test_a_test_that_stopped_passing_is_lost(self):
    self.assertEqual(lost_tests({"a": "ok"}, {"a": "skip"}, set()), ["a"])
    self.assertEqual(lost_tests({"a": "ok"}, {}, set()), ["a"])
    self.assertEqual(lost_tests({"a": "skip"}, {}, set()), [])
def test_a_test_that_failed_in_one_base_is_never_lost(self):    # red first: an intermittent pre-existing red (F_fon) is noise
    self.assertEqual(lost_tests({"a": "ok", "b": "ok"}, {"a": "fail", "b": "fail"}, {"b"}), ["a"])
def test_a_record_is_written_when_the_test_body_raises(self):   # tiny in-process TestCase, patch.object(fake_game, "x") then raise -> one line, called False
def test_a_patch_on_another_object_writes_nothing(self):
def test_an_autospec_patch_is_kind_mock_and_a_plain_function_is_kind_other(self):   # new=<function> -> called None
def test_uninstall_restores_the_state_before_its_own_install(self):   # the three functions equal the ones seen just before install (not module-level originals)
def test_an_outer_ledger_still_records_after_an_inner_install_and_uninstall(self):
    # red first: install_ledger(outer_dir) (stands in for the gate), then install_ledger(inner_dir), a patch.object(fake_game, "x")
    # inside a tiny TestCase, uninstall(); then one more patched tiny TestCase: its record is in outer_dir, not in inner_dir;
    # the three functions are the outer install's wrappers; finally uninstall() the outer one
def test_a_patch_after_an_inner_test_run_is_filed_under_the_outer_test(self):   # outer tiny TestCase runs an inner one, then patch.object(fake_game, "x"): that record's "test" is the outer id
def test_the_n4_token_installs_the_ledger_under_the_run_root(self):   # boot("<tmp>/20261118T000000-x-n4-0", {}) -> out dir exists; uninstall in addCleanup
```

Every test that installs a hook uninstalls it in `addCleanup`: these tests run in the same guarded process as other tests, and in an `n4` shard a gate ledger is already active underneath them (the stack keeps it).

- [ ] **Step 2:** Run `api.tests.test_engine_probe_tools api.tests.test_engine_gate_boot` + `NEIGHBOURS`. Expected: FAIL (module missing). Implement. Run again: `RESULT exit=0`.
- [ ] **Step 3: Smoke in the child.** Targeted run, label `p2t2-n4`, modules `api.tests.gate_boot api.tests.test_engine_parts_pilot api.tests.test_engine_surface` + `NEIGHBOURS`: `RESULT exit=0`; `SLOTPY ledger_diff.py --collect` on that run: `hits` holds a key ending `|roll_d20` with value `true`, `outcomes` holds every test that ran. The same modules without the token: no `engine-probe` folder in the run root.
- [ ] **Step 4: Commit** `game.py split plan 2: N4 patch-hit ledger and per-test outcome ledger (D-352)`.

### Task 3: N7 per-function executed lines with `sys.monitoring` (D-352, second half)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no.

**Files:**
- Modify: `ai-dnd/api/tests/engine_probe.py`, `ai-dnd/api/tests/gate_boot.py` (token `n7`)
- Create: `ai-dnd/scripts/engine_split/coverage_by_function.py`
- Test: `ai-dnd/api/tests/test_engine_probe_tools.py`

**Interfaces — Consumes:** `engine_sources.engine_source_files()` (Plan 1 N6), `inventory.top_level_index(path) -> list[dict]` (`name`, `def_line`, `end`).

**Interfaces — Produces:**
- `engine_probe.install_lines(out_dir: Path, engine_files: list[Path], tool_id: int = sys.monitoring.COVERAGE_ID) -> None`: `sys.monitoring.use_tool_id(tool_id, "engine-split-n7")`; state is kept per `tool_id`, so a second probe on a free id does not touch the gate's; on `PY_START`, code whose `co_filename` resolves to one of `engine_files` gets local `LINE` events, any other code returns `sys.monitoring.DISABLE`; the `LINE` callback records `(file, line)` and returns `DISABLE`. `atexit` writes `out_dir/lines-<pid>.json` = `{"<posix path relative to ai-dnd>": [sorted lines]}`. A second install on a tool id that is held raises `RuntimeError("engine-split-n7 already installed")`.
- `engine_probe.stop_lines(tool_id: int = sys.monitoring.COVERAGE_ID) -> dict[str, list[int]]`: frees that tool id only, unregisters that install's own `atexit` writer (so no file is written later into a removed temp dir), returns what it recorded.
- `gate_boot.boot(run_root, environ=os.environ, tool_id=sys.monitoring.COVERAGE_ID)`: token `n7` calls `install_lines(Path(run_root) / "engine-probe", engine_source_files(), tool_id)`.
- **Self-tests never use `COVERAGE_ID`:** in an `n7` shard the gate holds it. They use the free id `4` (`sys.monitoring` reserves 0, 1, 2, 5), and `stop_lines(4)` in `addCleanup`.
- `coverage_by_function.function_hits(lines: dict[str, list[int]], index: dict[str, list[dict]]) -> dict[str, int]`: top-level name → executed lines inside `def_line..end`, summed over `game.py` and all parts by name. `index` is built on the **measured tree** (a `git archive <measured sha>` copy), never on the current worktree.
- `coverage_by_function.unequal(base: dict[str, int], new: dict[str, int], noise_names: set[str]) -> list[str]`.
- CLI: `coverage_by_function.py --collect "<runs glob>" --engine-root <archived ai-dnd dir> --out <file.json>`; `--diff --base A --base2 B --new C` prints `NOISE <n>`, `DOWN <n>` + names, `UP <n>` + names; exit 1 if `DOWN` is above 0.

**Gate rule (Ruling, approval-list row marked "gevşetme olabilir"):** the spec says per-function counts are "aynı". This plan adds tests, which can raise a count. `DOWN` must be empty (else stop, tell Kadir); every `UP` name is listed in the ledger with the new test that explains it — if wrong: an unexplained rise is looked at one gate late.

- [ ] **Step 1: Write the failing tests:**

```python
def test_function_hits_follow_the_function_across_files(self):
    self.assertEqual(function_hits({"game.py": [2, 3]}, {"game.py": [{"name": "f", "def_line": 1, "end": 3}]}), {"f": 2})
    self.assertEqual(function_hits({"game.py": [2], "game_parts/p.py": [5, 6]},
                                   {"game.py": [{"name": "f", "def_line": 1, "end": 3}],
                                    "game_parts/p.py": [{"name": "f", "def_line": 4, "end": 6}]}), {"f": 3})
def test_unequal_ignores_only_the_noise_names(self):
    self.assertEqual(unequal({"f": 3, "g": 2}, {"f": 2, "g": 1}, {"g"}), ["f"])
def test_only_the_lines_of_a_called_function_are_recorded(self):
    # temp module file with two functions; install_lines(..., tool_id=4) on it; call one; stop_lines(4) -> exactly that function's body lines
def test_a_second_install_is_an_error_not_silence(self):    # two installs on tool_id=4; the second raises; stop_lines(4) in addCleanup
def test_the_n7_token_installs_the_line_probe(self):         # boot("<tmp>/...-x-n7-0", {}, tool_id=4); stop_lines(4) in addCleanup
def test_a_self_test_probe_leaves_the_gate_probe_running(self):
    # red first: install_lines(gate_dir, [f], tool_id=sys.monitoring.COVERAGE_ID) when that id is free (skip with a reason when
    # it is held: then the gate itself is the outer probe), and addCleanup(stop_lines, COVERAGE_ID) only when it installed it;
    # run the three tests' pattern on id 4; afterwards
    # sys.monitoring.get_tool(COVERAGE_ID) == "engine-split-n7" and a call of f is still recorded on the outer id
```

- [ ] **Step 2:** Run `api.tests.test_engine_probe_tools` + `NEIGHBOURS`: FAIL. Implement. Run: `RESULT exit=0`. If the guard's audit hook refuses `sys.monitoring` inside the child, stop: write the refusal text in the ledger and tell Kadir (the fallback is spec §9: "N3 + N7 + tam paket kalır ve Kadir'e bildirilir", and N7 would be missing too).
- [ ] **Step 3: Smoke in the child.** Label `p2t3-n7`, modules `api.tests.gate_boot api.tests.test_engine_parts_pilot` + `NEIGHBOURS`: `RESULT exit=0`; `--collect` on that run with `--engine-root` = an archive of HEAD: `roll_d20` and `_inside_speech` have counts above 0. Record the run's seconds with and without the token (probe overhead, measured). If that overhead puts the expected shard time (TM0 1959 s wall / 3 shards × overhead factor, plus margin) near the `slot_gate.sh` shard timeout of 3000 s, raise the timeout in the Task 8 and Task 16 calls before Task 8 (`Ruling` with the numbers).
- [ ] **Step 3b: The self-tests under a live gate probe.** Targeted run, label `p2t3-n4-n7`, modules `api.tests.gate_boot api.tests.test_engine_probe_tools api.tests.test_engine_gate_boot` + `NEIGHBOURS`. Expected: `RESULT exit=0`; `--collect` on that run: the outcomes ledger holds the `NEIGHBOURS` tests (they run after the probe tests, so the gate ledger survived), and the lines file has counts for engine functions the journey tests reach. Seeded proof: in the working tree only, make `uninstall` restore the first originals (the non-stacked behaviour) and run the same command; expected: the `NEIGHBOURS` ids are missing from the outcomes ledger. Restore by the pre-plant copy rule. Record both.
- [ ] **Step 4: Commit** `game.py split plan 2: N7 per-function executed lines over sys.monitoring (D-352)`.

### Task 4: N3 closes its known holes (D-349)

**Review tier:** strong (Opus implementer, strongest-model review): N3 is the only guard for the 48 `not_called_tests`. Money/save/Undo: no.

**Files:**
- Modify: `ai-dnd/scripts/engine_split/routing_audit.py`
- Test: `ai-dnd/api/tests/test_engine_routing.py`, `ai-dnd/api/tests/test_engine_surface.py`

**Interfaces — Produces:** `routing_audit.re_exports(root: Path) -> dict[str, list[str]]` (part short name → names `game.py` imports from it at top level, the `__main__` guard excluded; expose the reader R2/R3 already use, do not write a second one). New finding ids, each with one bad fixture part asserting exactly that id and one clean fixture:

| Id | Rule |
|---|---|
| R8 | every top-level `def`, `class` and assignment target of a part is imported by `game.py` from that part; it is not also bound at top level in `game.py`; no two parts bind the same name by `def`, `class` or assignment (import bindings such as `import game`, `import re` are not counted). A part the `__main__` guard imports as a module (`terminal`) is exempt from the first clause: its `<part>.<name>` uses inside the guard count as imports (`terminal.run`). Clean fixture: a terminal-style part used only as `terminal.run(...)` in the guard |
| R9 | a bare read, inside a part, of a name that is a top-level `def` or `class` of the same part (constants stay bare) |
| R10 | a store to `game.<name>` in a part |
| R11 | `<module>.<attr>` in a part where `attr` is a census target of kind `import` or `absent` (`uuid4`, `chat`, `open`, ...) and `<module>` is an `ast.Name` bound in the part by an import statement, or the literal names `builtins` / `io` (`uuid.uuid4()`, `builtins.open`, `io.open`). Attribute chains rooted in `game` are exempt. Clean fixture: `game._session().rng.randint(1, 20)` (`rng` is an `absent` target; `game_parts/character_rules.py` has this form) |
| R12 | `getattr(game, ...)` or a local alias of `game` (`g = game`) in a part, unless an identity allow-list row names it |
| R13 | `game_parts/__init__.py` contains anything other than `import game` |

- [ ] **Step 1: Write the failing fixture tests** for R8-R13 in `test_each_rule_fires_on_its_fixture` / `test_each_escape_gives_exactly_its_rule` style (the file's existing table style), plus in `test_engine_surface.py`:

```python
def test_every_re_export_is_the_parts_own_object(self):
    parts = {name: module for name, module in sys.modules.items() if name.startswith("game_parts.")}
    for part, names in routing_audit.re_exports(ROOT).items():
        module = parts["game_parts." + part]
        for name in names:
            own, seen = vars(module)[name], getattr(game, name)
            if inspect.isfunction(own):
                self.assertIs(seen.__wrapped__, own, name)
                self.assertTrue(seen._session_bound, name)
                self.assertIn(module.__name__, game._PART_MODULES, name)
            else:
                self.assertIs(seen, own, name)
```

Ruling: this test is how the spec's "`game.RACES is tables.RACES`" is proven — tests may not import `game_parts` (N3 R2) and a data-only part has no function whose `__globals__` could be read — R8 proves it statically, this test at run time — if wrong: one allow-list row and a direct import in one test.

- [ ] **Step 2:** Run `api.tests.test_engine_routing api.tests.test_engine_surface` + `NEIGHBOURS`: the six fixture rows FAIL; the runtime test is green on a clean tree. Show it red three times in the working tree, restoring `game.py` after each with `git checkout HEAD -- ai-dnd/game.py` only (Stage A never changes `game.py`; a broad checkout would wipe the Step 1 test edits): `_PART_MODULES = ()`; a line `_SPEECH_SPAN_RE = re.compile(_SPEECH_SPAN_RE.pattern)` after the re-export in `game.py`; `roll_d20 = roll_d20.__wrapped__` after `_bind_session_engine()` has run. Record the three failing lines.
- [ ] **Step 3:** Implement R8-R13. Run: `RESULT exit=0`, and `test_the_real_tree_is_clean` stays green. Record the audit's seconds.
- [ ] **Step 4: Accepted, documented, not closed** (one ledger line each and one sentence in the D-349 row): M5, M7, M8 (0 PEP 695 sites), M9 (walrus in a generator expression: 4 sites in `game.py`; a false R5 fails closed; a move that hits one adds an allow-list row), a patch target string held in a variable. Process rule for "lock regenerated with a new import": a move commit leaves `allowed_imports.json` byte-equal unless the brief names the new module; the reviewer checks `git diff --stat`. Update the D-349 row: closed parts, open parts, new trigger "Plan 3 Görev 0".
- [ ] **Step 5: Commit** `game.py split plan 2: routing audit rules R8-R13 and the runtime re-export identity test (D-349)`.

### Task 5: Mover CLI and checker fixes (D-348, D-350)

**Review tier:** normal (Sonnet implementer, Opus review). Money/save/Undo: no.

**Files:**
- Modify: `ai-dnd/scripts/engine_split/move_block.py`, `ai-dnd/scripts/engine_split/move_check.py`
- Test: `ai-dnd/api/tests/test_engine_move_tool.py`, `ai-dnd/api/tests/test_engine_move_check.py`

**Interfaces — Produces:**
- `move_block.main(argv: list[str] | None = None) -> int`: `--game PATH --part PATH (--names a,b | --names-file PATH) --census PATH [--report PATH]`. Loads the census lock, `surface_targets = {name for name, kind in targets.items() if kind != "absent"}`, calls the existing `move(game_py, part_py, names, surface_targets)`, prints `MOVED names=<n> import_line=<L> insertions=<k>`, writes `move()`'s dict as JSON to `--report`. `MoveRefused` → `REFUSED <reason>` on stderr, exit 2, both files byte-equal to before.
- `move_check.main`: new `--moved-file PATH --part <part file name>` (equal to `--moved n1=<part>,n2=<part>,...`); the four fixes below.

- [ ] **Step 1: Write the failing tests.** `test_engine_move_tool.py`:

```python
def test_the_cli_gives_the_same_files_as_move(self):          # temp fixture; --names and --names-file both
def test_a_refusal_exits_2_and_changes_no_byte(self):         # a NEVER_MOVED name
def test_an_absent_census_target_is_not_prefixed(self):
def test_the_cli_keeps_utf8_bytes_and_line_endings(self):     # Review Focus 2: fixture block holds "ğüşıöç “x” —"; part has no BOM, no \r, and the block's bytes equal the base bytes
def test_a_multi_name_block_and_a_decorated_function_round_trip(self):   # Plan 1 Task 5 deferred minor
```

`test_engine_move_check.py`:

```python
def test_a_manual_entry_that_exempts_nothing_is_a_finding(self):   # text: "manual entry exempts nothing: <entry>"
def test_an_undecodable_file_is_named(self):                        # "ERROR cannot decode <file>", exit 2
def test_a_manual_entry_without_a_reason_is_refused(self):          # exit 2
def test_a_part_that_does_not_parse_is_a_finding_not_a_traceback(self):
def test_moved_file_equals_the_long_moved_form(self):
```

- [ ] **Step 2:** Run both modules + `NEIGHBOURS`: FAIL. Implement. Run: `RESULT exit=0`.
- [ ] **Step 3:** Update the D-348 row (closed) and the D-350 row (closed, or what stays). Note for this task's brief and for Stage B briefs: header import lines of a part need no `--manual`; F16 (`_import_only_lines`) already accepts import-only lines, and after this task a `--manual` for them is a finding (Plan 1 ledger, Task 19 minor: they were no-ops). Note for Stage B briefs (Plan 1 Task 6 minor): the mover refuses annotated assignments more strictly than the pilot brief said; a refusal is handled by M4, never by editing the tool inside a move task.
- [ ] **Step 4: Commit** `game.py split plan 2: move_block CLI, names files, move_check stale-manual and decode fixes (D-348, D-350)`.

### Task 6: Fresh measurement, batch files, small tool debts (D-347, D-351, D-341 helper)

**Review tier:** normal (Sonnet implementer, Sonnet review). Money/save/Undo: no.

**Files:**
- Modify: `ai-dnd/scripts/engine_split/inventory.py`, `ai-dnd/api/tests/test_engine_split_inventory.py`, `ai-dnd/api/tests/test_engine_surface.py`, `ai-dnd/api/tests/test_engine_size_budget.py`, `ai-dnd/api/tests/engine_split_locks/size_budget.json`, `ai-dnd/api/tests/test_engine_sources.py`
- Modify: `ai-dnd/api/tests/engine_sources.py`
- Create: `ai-dnd/scripts/engine_split/outside_probe.py`, `ai-dnd/scripts/engine_split/batches/{tables,schemas,text-a1,text-a2,text-b1,text-b2}.txt`
- Regenerate: `docs/engine-split/inventory.json`, `docs/engine-split/patch-census.md`

**Interfaces — Produces:**
- `inventory.closed_helpers(path)`: a name `game.py` binds with `from game_parts.<x> import` counts as a function, so its callers are not "closed" (today `roll_attack`, `roll_initiative`, `roll_initiative_npc`, `_unseen_speakers` look closed by accident).
- `engine_sources.batch_names(batch: str) -> list[str]`: the names in `scripts/engine_split/batches/<batch>.txt`, in file order.
- `inventory.touching_tests(root: Path, names: set[str]) -> list[str]`: dotted test modules (under `api/tests` and the `ai-dnd` root) that read `game.<name>` or hold the string `"game.<name>"` for a name in `names`; CLI `inventory.py --touching <names file>` prints them space-separated.
- `outside_probe.py` (run with the slot Python outside the guard): both import orders in fresh interpreters (`import game, game_parts` / `import game_parts, game`), each printing `sorted(n for n in sys.modules if n.startswith("game_parts."))`; `python game.py` from a fresh temp cwd with input `2`, `zar at`, `exit` (rc 0, one `D20 sonucu:`, one `Oyun kapatılıyor`); closed stdin (rc 1, `EOFError`). Prints `PROBE ok parts=<list>` and exits 0, or `PROBE FAIL <step>` and exits 1.
- `size_budget.json` `long_functions` keys become `"<file>::<name>"` (`"game_parts/terminal.py::run": 184`); approval-list row (lock format read by a test, equal strictness).

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_caller_of_a_re_exported_function_is_not_closed(self):      # fixture game.py: from game_parts.p import f; def g(): return f()
def test_touching_tests_finds_attribute_and_string_uses(self):
def test_t3_batches_are_movable(self):
    # every name of every batch file: a top-level name of game.py, or re-exported from that batch's part;
    # none in NEVER_MOVED; none in sensitive.json; no name in two files;
    # cluster rule by direction (inventory.constant_clusters): no batch constant's value reads a name that stays in game.py
    # (the mover's F6 refusal); a staying member of a cluster (e.g. NEVER_MOVED `messages` in
    # [NARRATOR_VOICE, system_prompt, messages]) is fine only if it lies below the first cut block of that batch,
    # where the re-export line will be
def test_a_missing_re_export_is_named_in_the_failure(self):           # the surface test's message holds diff_rule lines, not a cut dict diff
def test_long_functions_are_keyed_by_file_and_name(self):
def test_part_file_names_are_lower_case(self):                        # sorted(Path) order is the same on Windows and POSIX
```

- [ ] **Step 2:** Run `api.tests.test_engine_split_inventory api.tests.test_engine_surface api.tests.test_engine_size_budget api.tests.test_engine_sources` + `NEIGHBOURS`: FAIL. Implement; write the six batch files from "Appendix: batch lists"; regenerate `inventory.json` and `patch-census.md` (Ruling: the report gets no test — `docs/` is not synced to the slot, so a test could only run in CI — it is regenerated here and at the TM2 gate instead — if wrong: the report drifts by a few sites again) (`SLOTPY patch_census.py --write --lock /mnt/c/.../patch_census.json --report /mnt/c/.../docs/engine-split/patch-census.md`). Run: `RESULT exit=0`.
- [ ] **Step 3: Appendix against measurement.** For each batch file print names, line total and header imports from the fresh inventory. Expected: tables 20 names / about 366 lines; schemas 12 / 290; text-a1 50 / about 276; text-a2 63 / about 518; text-b1 39 / 544; text-b2 44 / 367. A different number is a `Ruling` in the ledger (measurement wins) and the batch file is corrected here, not inside a move task.
- [ ] **Step 4:** `SLOTPY outside_probe.py`: `PROBE ok parts=['game_parts.character_rules', 'game_parts.text_rules_a']`. Update the D-347 row (closed), D-351 (closed items; `import game` unused in `text_rules_a.py` stays open with its real state: "stays unused until a `text_rules_a` function needs `game.X`; removing it changes only the comment-free header" — a read-only AST check found no `text-a1`/`text-a2` function that reads a top-level engine name outside its own part, so Tasks 11-12 add no `game.` prefix there; Tasks 11 and 12 record the measured fact (`grep -c "game\." game_parts/text_rules_a.py` and ruff F401 if approved), not an assumed close; `api/live_smoke.py` importing the whole engine stays, trigger as D-346), D-341 (probe is now one script; still not a CI test).
- [ ] **Step 5: Commit** `game.py split plan 2: honest closed-helper count, T3 batch files, census report regenerated, outside probe (D-347, D-351)`.

### Task 7: The new nets' own exam (spec §6: "Hiç kırmızı görülmemiş ağa güvenilmez")

**Review tier:** none (Opus runner, no review; nothing is committed). Money/save/Undo: no.

**Files:** none committed. Throwaway local branch `tmp/game-py-bolme-ag-sinavi-p2` cut from the Stage A tip; never pushed, not deleted.

For each fault: apply it alone, run the named check, see the stated red, `git checkout HEAD -- ai-dnd`, next fault. Record the failing line of each.

- [ ] **Clean pair first.** `ROLL10` = the ten test modules with the most `roll_d20` sites, derived (the report has no per-file table per target) with `SLOTPY` from `patch_census.scan(ROOT, <surface names>)` filtered to `target == "roll_d20"`, counted by file, top ten; the list goes in the ledger. Two targeted runs, labels `p2x-a-n4-n7` and `p2x-b-n4-n7`, modules `api.tests.gate_boot` + `ROLL10` + `NEIGHBOURS`; `--collect` both. Expected: `--diff --base A --base2 B --new B` prints `DROPS 0`, `LOST 0`, `DOWN 0`; record `NOISE`.
- [ ] **Fault 1 — frozen alias (N4).** In `game.py` add `_ROLL = roll_d20` at module level after the re-export and make `perform_skill_check` call `_ROLL(...)`. Same run, label `p2x-f1-n4`. Expected: `DROPS` above 0 with keys ending `|roll_d20`. (N3 is silent here: it audits parts only.)
- [ ] **Fault 2 — lost coverage (N7).** N7 records lines per process, not per test, so this fault uses its own small set and module-level data. Set `PILOTSET` = `api.tests.gate_boot api.tests.test_engine_parts_pilot` + `NEIGHBOURS` (Task 3 Step 3 showed `_inside_speech` > 0 there). Own clean pair: labels `p2x-f2a-n4-n7`, `p2x-f2b-n4-n7`, `--collect` both. One probe run (`p2x-f2probe-n4-n7`) with class `PilotSpeechSpan` skipped: `_inside_speech` must fall to 0; if not, pick a function whose count falls to 0 there (write the function and the class in the ledger). The fault: `@unittest.skip("exam")` on that class, label `p2x-f2-n4-n7`, `--diff` against the clean pair (both tools). Expected: `DOWN` lists the chosen function; `LOST` lists the skipped ids.
- [ ] **Fault 3 — flag off again.** Remove the `fon` branch in `gate_boot.boot`. Run `api.tests.gate_boot api.tests.test_engine_gate_boot`, label `p2x-f3-fon`. Expected red: `test_the_fon_token_turns_the_flag_on_inside_the_child`.
- [ ] **Fault 4 — orphan in a part (R8).** Add `def _nobody_imports_me(): return 1` to `game_parts/text_rules_a.py`. Expected red: `api.tests.test_engine_routing`.
- [ ] **Fault 5 — bare call inside a part (R9).** Add to `game_parts/character_rules.py` a function `_twice()` returning `roll_d20() + roll_d20()` and re-export it. Expected red: `test_engine_routing` (R9) and `test_engine_surface` (new function in the surface).
- [ ] **Fault 6 — rebound constant.** `_SPEECH_SPAN_RE = re.compile(_SPEECH_SPAN_RE.pattern)` after the re-export in `game.py`. Expected red: `test_engine_routing` (R8) and `test_every_re_export_is_the_parts_own_object`.
- [ ] **ruff (once).** If Kadir approved (Task 0 d): a script file running `cd /root/aidnd-env-<SLOT>/src/ai-dnd && /root/.local/bin/uvx --from ruff==0.17.5 ruff check --select F821,F401,F811 --no-fix game.py game_parts`. Paste the output in the ledger. It gates nothing (spec §9: "N3'e ikinci göz, kilit değil"); an F821 is looked at now.
- [ ] **Final step:** back on the Stage A branch, `git status` clean, `api.tests.test_engine_routing api.tests.test_engine_surface api.tests.test_engine_probe_tools` + `NEIGHBOURS` green. A fault that stayed green stops the plan: fix the check red-first in its owning task's files, then repeat the whole exam.

### Task 8: Gate G3a — bases on unmoved code, PR 4

**Review tier:** whole-branch review on the strongest model. Money/save/Undo: no (tooling only).

- [ ] **Step 1:** `git fetch origin`; merge `origin/main` if it moved, then rerun Tasks 1-6's test modules + `NEIGHBOURS`. Check `git diff afe0023b..HEAD -- ai-dnd/game.py ai-dnd/game_parts` is empty: the bases below are bases of unmoved code. If `origin/main` changed `game.py`, the base tree is that new commit; write its sha.
- [ ] **Step 2: Whole-branch review before the bases.** Whole-branch review of `$(git merge-base origin/main HEAD)..HEAD` (after a Step 1 merge, `afe0023b..HEAD` would also hold main's own commits); fix findings red-first in one fix wave (Opus), scoped re-review (Opus). No second wave: remaining minors are parked as debt rows. Ruling: the review and its fix wave run before the bases — a fix to `engine_probe.py`, `gate_boot.py`, `slot_gate.sh`, `ledger_diff.py`, `coverage_by_function.py` or a test module changes what the bases record — if wrong: nothing, the order only costs the bases' wait. If the fix wave touches a probe tool, rerun the Task 7 fault(s) that exercise that tool before Step 3. From Step 3 on, any change to those files or to the set of test modules before Task 16 retakes the affected flag's b/c bases (Step 3-4), with the reason in the ledger; a change to `ledger_diff.py` or `coverage_by_function.py` alone reruns `--collect` on the stored run folders instead (no new suite).
- [ ] **Step 3: Bases, one full suite at a time, nothing else on the slots** (`slot_gate.sh`, each after the other-run check of Global Constraints; labels in this order): `p2g0-off-n4-n7-b`, `p2g0-off-n4-n7-c`, `p2g0-fon-a`, `p2g0-fon-n4-n7-b`, `p2g0-fon-n4-n7-c`. Ruling: five suites — two probe runs per flag give the N4/N7 base and its noise set (spec: "Taban TM0'da iki kez"); one probe-free flag-on run gives the first real flag-on time; probe-free flag-off times already exist (TM0 1959 s, TM1 1586 s) — if wrong: one more suite (27 min). Flag-off runs: `PAR_EXIT=0`, `failing_ids 0`. Flag-on runs: the `F_fon` rule of Global Constraints — every failing id is traced to its commit, gets a debt row and goes into `F_fon` (written to the ledger and `p2/F_fon.txt` after the three `fon` runs); Kadir is told in one message; the plan goes on. A flag-off red stops the gate.
- [ ] **Step 4: Compute and store** in `AI-DND-TOOLS/measure/engine-split/p2/`: per flag `ledger-{b,c}.json`, `lines-{b,c}.json` (`--engine-root` = archive of the base tree), the N4 noise set (`noise` of b vs c, hits and outcomes), the N7 noise set (`unequal` of b vs c), seconds of every run; turn benchmark twice (`slot.sh <SLOT> <WT> test p2g0bench1 1800 api.tests.bench_engine_turn`, the `TURN_BENCH` line from `target.log`). Probe completeness: every shard of every `n4`/`n7` run has a non-empty `engine-probe/ledger-*.jsonl` and `lines-*.json`, and the shard that ran `test_engine_probe_tools` has outcome records for tests that ran after that module; otherwise the probe broke mid-shard: stop and fix red-first in Task 2/3 files. Ledger: all numbers, both noise-set sizes, probe overhead (b/c seconds against 1586 s and against `p2g0-fon-a`). Note in the ledger: the two pilots moved before any N7 base existed; this base cannot show coverage they lost.
- [ ] **Step 5: Gate checks without a suite.** `SLOTPY outside_probe.py` → `PROBE ok` (D-341). `python test_regression.py` as a script on the slot copy → `Results: 30 passed, 0 failed out of 30` (D-342). **Flag proof** (test and skip counts alone prove nothing: no test selects or skips on `AI_DND_FRONT_PROPOSAL`): (a) in both `fon` N4 outcome ledgers, `...test_engine_gate_boot...test_the_fon_token_turns_the_flag_on_inside_the_child` is `ok`, and in both off ledgers it is `skip`; (a) failing = the flag still does not reach the child: stop. (b) N7: at least one engine function has a different count in both `fon` bases than in both off bases (start with the callers of `front_proposal.enabled()` in `game.py`); name it in the ledger. No such function: `Ruling` + debt row + tell Kadir (the flag reaches the child but no test drives a flag-on path; Review Focus 1 then rests on the outcomes only), not a stop.
- [ ] **Step 6:** Update D-352 (N4/N7 built, bases taken; stays open until Task 16 uses them) and D-354 (closed, with the two run labels). Approval-list rows: N7 over `sys.monitoring`; N7 rule "DOWN empty"; the `F_fon` pass rule; `long_functions` re-key; the surface test's new failure message.
- [ ] **Step 7:** Recheck the free debt ids (Global Constraints). Ask Kadir: push + PR 4 (text says what N4 cannot see, that N7 uses `sys.monitoring`, and the `F_fon` list). After the push: CI wait as in Global Constraints (at most 25 min) until "AI-DND bounded verification" is green. Stage B starts without waiting for the push or the merge. Ledger line "G3a geçti".

---

# Stage B — T3 moves (worktree `AI-DND-k2-bolme-t3`, branch `task/game-py-bolme-t3` from the Stage A tip, PR 5). Each task is a pure move: the Move procedure applies in full.

### Task 9: `tables.py` — 20 data tables (spec T3.1)

**Review tier:** strong (Opus implementer, strongest-model review). Ruling: the spec says normal; the moved tables are read by five functions in `sensitive.json` (measured, read-only AST): `_origin_choices_for_save` and `load_game` (`_ORIGIN_TEXT_KEYS`, `_ORIGIN_LIST_KEYS`, `_ORIGIN_SCORE_KEYS`; `load_game` also `SPECIES_WITH_TRAIT_STATE`), `_player_state_for_save` (`SPECIES_WITH_TRAIT_STATE`), `_validate_save_payload` (`RACES`, `CLASSES`, `SKILLS`, `GIANT_ANCESTRY_IDS`), `_execute_intent_internal` (`SKILLS`) — save-shaped content gets the strong tier, as Task 10 does for money-adjacent keys — if wrong: one stronger review than needed. Money/save/Undo: save-adjacent data (keys a save reads), no save code; all five readers stay in `game.py`.

**Files:**
- Create: `ai-dnd/game_parts/tables.py`
- Modify: `ai-dnd/game.py`, `size_budget.json`; `surface.json` expected unchanged
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch:** `ai-dnd/scripts/engine_split/batches/tables.txt`. Header by hand: the `effect_targeting` import as `game.py` spells it (for `INNER_RADIANCE_SPEC`, `NECROTIC_SHROUD_SPEC`); no `import game`. `tables` is **not** added to `_PART_MODULES` (R2: only parts with a re-exported `def`). `RULE_ORDER` sits between the species rows and stays.

- [ ] **Step 1: Dry run of the path no pilot took** (a census-target constant, and a constant whose value calls into an imported module). In the working tree only (clean at HEAD before this step): M4 with `--names CLASSES,INNER_RADIANCE_SPEC`, header import, then sync the slot: `slot.sh <SLOT> <WT> test p2t9-dry 1800 api.tests.test_engine_routing <NEIGHBOURS>` (it also shows the R-rules on the moved pair; `Ruling: this run leaves out ENGINE_SET — it is a sync and an R-rule look, not a test gate; the half-move has no membership test, size budget or surface update, so ENGINE_SET would be red by design — if wrong: nothing, M10 runs ENGINE_SET on the real move`); check the slot's `game.py` sha256 equals the worktree's; then `SLOTPY routing_audit.py` and `SLOTPY outside_probe.py`. Expected: `MOVED names=2`, `RESULT exit=0`, `clean`, `PROBE ok`. Record; `git checkout HEAD -- ai-dnd/game.py`; `git rm -f -q --ignore-unmatch ai-dnd/game_parts/tables.py` and delete the file if it is still on disk; `git status --short` is empty. A refusal or a finding here: stop the task, fix the tool red-first as a Step 0 commit in Task 5's files, start again.
- [ ] **Step 2: Capture, then write the tests** (M3). On the base commit, compute `value_digest(TABLES)` and pin the hex. Helper `value_digest(names) -> str` in the test file (Tasks 10-14 reuse it) works on a canonical form, never on `repr` (a `set`/`frozenset` of `str`, e.g. `SPECIES_WITH_TRAIT_STATE`, `INTENT_TYPES`, `SCENE_DETAIL_KIND_ALLOWLIST`, changes `repr` order per process: measured, two fresh processes gave two digests): a recursive normaliser turns `set`/`frozenset` into a sorted list, keeps `dict` insertion order, turns `tuple` into a list, maps a compiled regex to `[pattern, flags]`, and refuses any other type with `TypeError` naming it; then `json.dumps(..., ensure_ascii=False)` of `[[name, canonical(value)] ...]` in name order, then sha256. Red check first, in-process (subprocess tests are skipped in the slot): `test_the_digest_form_sorts_sets` asserts `_canonical({"b", "a", "c"}) == ["a", "b", "c"]`, `_canonical(frozenset({"y", "x"})) == ["x", "y"]` and `_canonical(re.compile("a", re.I)) == ["a", re.I.value]`. Measured once outside the guard (`SLOTPY` script, two runs of the digest of `TABLES` and of `SCHEMAS` with `PYTHONHASHSEED=1` and `=2`): equal; record both lines:

```python
TABLES = tuple(batch_names("tables"))          # engine_sources.batch_names (Task 6)
def test_the_digest_form_sorts_sets(self):     # red before _canonical exists; green before the move
def test_the_tables_live_in_the_part(self):
    self.assertEqual(set(TABLES) - set(routing_audit.re_exports(ROOT).get("tables", [])), set())   # red before the move
def test_the_table_values_did_not_change(self):
    self.assertEqual(value_digest(TABLES), "<hex captured on the base commit>")
def test_a_patched_class_table_reaches_the_api_reader(self):                                      # Review Focus 3
    # patch("game.CLASSES", [<one class>]) and call the reader in api/character_creation.py that lists classes
    # (find it with graphify: "who reads game.CLASSES"); assert it returns that one class
```

- [ ] **Step 3:** Run (FAIL on the first test only). M4-M9. Expected at M8: `surface.py --diff` silent with an empty `--moved`.
- [ ] **Step 4: The comment exam (D-353).** Pick a moved block that carries a comment line directly above it (the table banners qualify; if none moved, do this in Task 11 and say so). Save `game_parts/tables.py` by the pre-plant copy rule (it is new and uncommitted), then in the working tree delete that one comment line from it; M7 again. Expected: `CHANGED` above zero and `COMMENTS base=1083 now=1082`. Restore from the saved copy, M7 again: `CHANGED 0`. Record both outputs; update the D-353 row (closed).
- [ ] **Step 5:** M10 with the named modules `api.tests.test_roadmap_c06_creation_http api.tests.test_roadmap_c10_starting_equipment_http`. Expected: `RESULT exit=0`.
- [ ] **Step 6: Commit** `game.py split T3.1: data tables live in game_parts/tables.py`.

### Task 10: `schemas.py` — 12 schema and prompt constants (spec T3.2)

**Review tier:** strong (Opus implementer, strongest-model review). Ruling: the spec says normal; `_EXPERIMENTAL_NPC_SPEECH_SCHEMA` holds the `coin_answer` keys, `WORLD_UPDATE_SCHEMA` holds `create_shops`, and every reader is in `sensitive.json` — money-adjacent content gets the strong tier — if wrong: one stronger review than needed. Money/save/Undo: money-adjacent data (the keys of money answers), no money code.

**Files:**
- Create: `ai-dnd/game_parts/schemas.py`
- Modify: `ai-dnd/game.py`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch:** `ai-dnd/scripts/engine_split/batches/schemas.txt`. Clusters move whole: `INTENT_TYPES` + `INTENT_SCHEMA`; `NPC_SCHEMA` + `LOCATION_SCHEMA` + `WORLD_UPDATE_SCHEMA` + `DM_RESPONSE_SCHEMA`; `NARRATOR_VOICE` + `system_prompt`. `messages` (reads `system_prompt` at import, NEVER_MOVED) stays in `game.py`; the re-export line lands at the first cut block, far above it, so `messages` reads the re-exported name. `_dm_response_schema_for_turn` is sensitive and stays. Not in `_PART_MODULES`. Header: none expected (measure in M2; a schema value that calls into a module needs that module's import).

- [ ] **Step 1: Capture, then write the tests:**

```python
SCHEMAS = tuple(batch_names("schemas"))
def test_the_schemas_live_in_the_part(self):                       # red before the move
def test_the_schema_values_did_not_change(self):                   # value_digest(SCHEMAS) pinned on the base commit
def test_the_system_prompt_is_one_object_for_module_and_sessions(self):   # Review Focus 4
    self.assertIs(game.messages[0]["content"], game.system_prompt)
    with fixed_town(self, 20261121):
        s = game.create_session(seed=7)
        self.assertEqual(s.messages[0]["content"], game.system_prompt)
```

Before writing the last test read how `GameSession.__init__` seeds its messages (graphify: "GameSession.__init__ system_prompt") and use the attribute it really sets; the two assertions above are the contract, the attribute name is measured.

- [ ] **Step 2:** Run (FAIL on the first test only). M4-M9.
- [ ] **Step 3:** Write `parse_player_intent`, `ask_dungeon_master`, `_dm_response_schema_for_turn` (the staying readers), one per line, to `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/touching-schemas.txt`; M10 with the modules `SLOTPY inventory.py --touching /mnt/c/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p2/touching-schemas.txt` prints, added to the batch's own list. `live_integration_test.py` rebinding `system_prompt` on a session object is not a module patch (read in the census as a false positive): no action, one ledger line. Expected: `RESULT exit=0`.
- [ ] **Step 4: Commit** `game.py split T3.2: schemas and the system prompt live in game_parts/schemas.py`.

### Task 11: `text_rules_a.py`, batch `text-a1` — 50 names, about 276 lines (spec T3.3)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no. Held out of this range and why: the six character helpers, the six save-shaped validators/defaults, `_known_happenings` (save-load filter: strips unknown ledger rows from saved `world_threads_v1`; called by `_validate_save_payload`, which is sensitive, and by `_repair_dilim2_fields`), three door helpers (Option B-hold).

**Files:**
- Modify: `ai-dnd/game_parts/text_rules_a.py`, `ai-dnd/game.py`, `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch:** `ai-dnd/scripts/engine_split/batches/text-a1.txt`. Header additions expected: the `living_world` import as `game.py` spells it (`re` is already there). Known M2 hits to rule on: `_COUNTER_ROLE` (words "merchant", "shop"; role vocabulary, reader `_serves_at_a_counter` is not sensitive: moves); `_REWOUND_LINE`, `_FALL_LINE` (check their readers against `sensitive.json`; a sensitive reader = hold both). `_topic_place_name` is a census target (3 `patch.object` sites in `api/tests/test_talk_front.py`): callers in `game.py` keep reading the module global, so the patch still reaches them.

- [ ] **Step 1: Capture, then write the tests:**

```python
TEXT_A1 = tuple(batch_names("text-a1"))
def test_text_a1_lives_in_the_part(self):                          # red before the move
    self.assertEqual(set(TEXT_A1) - set(routing_audit.re_exports(ROOT)["text_rules_a"]), set())
def test_text_a1_helpers_answer_as_before(self):
    # clean_dm_response, _affirmative_door_verb, _reads_english, _strip_proposal_markers, _drop_repeated_sentences:
    # two inputs each, taken from the helper's existing tests or, when it has none, a string its regex matches;
    # expected values captured on the base commit and pinned as literals
def test_a_moved_text_helper_still_takes_a_session(self):         # spec §6: session binding survives the move
    with fixed_town(self, 20261122):
        s = game.create_session(seed=9)
        self.assertEqual(game._strip_proposal_markers("a", session=s), game._strip_proposal_markers("a"))
def test_a_patch_on_a_moved_helper_reaches_its_caller_in_game_py(self):
    # patch.object(game, "_topic_place_name", return_value="X") and call the game.py caller test_talk_front uses; assert "X" was used
```

- [ ] **Step 2:** Run (FAIL on the first test). M4-M9; M8 `--moved` = the functions of the batch.
- [ ] **Step 3:** M10 with `api.tests.test_talk_front`. Expected: `RESULT exit=0`. D-351 fact in the ledger: the count of `game.` reads in `game_parts/text_rules_a.py` after this move (expected 0: `import game` stays unused; the row stays open).
- [ ] **Step 4: Commit** `game.py split T3.3: text helpers and regexes, first batch, live in game_parts/text_rules_a.py`.

### Task 12: `text_rules_a.py`, batch `text-a2` — 63 names, about 518 lines (spec T3.4)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no. Held: `_town_in_play`, `_local_place_access` (places); `_STOCK_SAID` (session-less mutable state, see below).

**Files:** as Task 11.

**Batch:** `ai-dnd/scripts/engine_split/batches/text-a2.txt`. Header additions expected, each as `game.py` spells it: `json`, `hashlib`, `unicodedata`, `collections`, `local_dialogue`, `npc_statements`, `tr_names`, `interaction_adventure`. M2 points: `_STOCK_SAID` (`collections.deque(maxlen=256)`, returned by `_stock_said()` for a call with no session and appended to) is state, not a constant: it is already held (not in `text-a2.txt`; held table); its only reader `_stock_said()` is not in this batch either; `_dm_prompt_note` is read by `inspect.getsource` in `api/tests/test_tr_names.py` (the call `tr_names.narrator_note(` must stay bare: `tr_names` is not an engine name).

- [ ] **Step 1: Capture, then write the tests:** `test_text_a2_lives_in_the_part` (red before the move) and `test_text_a2_helpers_answer_as_before` for `_fold_keep_punctuation`, `_extract_json_object`, `_strip_pictographs`, `_normalize_turkish_typos`, `_without_real_world_faith` (two inputs each, pinned on the base commit; at least one input with Turkish letters and one with curly quotes).
- [ ] **Step 2:** Run (FAIL on the first test). M4-M9.
- [ ] **Step 3:** M10 with `api.tests.test_tr_names`. Expected: `RESULT exit=0`. `text_rules_a.py` line count goes in the ledger (expected about 940 with header, limit 2 500). D-351 fact again: the count of `game.` reads in `text_rules_a.py` (expected 0).
- [ ] **Step 4: Commit** `game.py split T3.4: text helpers and regexes, second batch, live in game_parts/text_rules_a.py`.

### Task 13: `text_rules_b.py`, batch `text-b1` — 39 names, about 544 lines (spec T3.5)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no.

**Files:**
- Create: `ai-dnd/game_parts/text_rules_b.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.text_rules_b"`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`

**Batch:** `ai-dnd/scripts/engine_split/batches/text-b1.txt`. Header: `import game`, then `re` and `equipment_economy` as `game.py` spells them. `_unseen_speakers` and `_split_sentences_keep_speech` read the pilot's names: the mover writes `game._inside_speech` and `game._SPEECH_SPAN_RE` (Ruling: they stay in line order in `text_rules_b` — the prefix is legal and only cosmetic — if wrong: nothing breaks; a later tidy-up moves two functions). M2 hit to rule on: `_LORE_ENTITY_FOLLOWING_CUE_RE` (words "merchant", "shop"; lore vocabulary: moves unless a reader is sensitive). `_LORE_UNSUPPORTED_DETAIL_PATTERNS` is one 127-line block.

- [ ] **Step 1: Write the tests:** `test_text_b1_lives_in_the_part` (red); `test_text_b1_helpers_answer_as_before` for `_split_sentences_keep_speech`, `_unseen_speakers`, `_lore_guard_text`, `_is_generic_speaker_label`, `_salvage_plain_speech`; `PilotSpeechSpan.test_the_reader_left_in_game_py_still_works` asserts `game._split_sentences_keep_speech.__module__ == "game"`, which this move makes false: keep that test id (a renamed id is `LOST` at TM2, Task 16 Step 3) and its pinned value assertion unchanged, take out only the `__module__ == "game"` assertion, and add `PilotSpeechSpan.test_the_speech_reader_lives_in_text_rules_b` that asserts `__module__ == "game_parts.text_rules_b"` (approval-list row, equal strictness: the assertion moves to the new test; red before the move); update `test_the_wrapper_filter_reads_an_explicit_part_list` to expect `("game_parts.character_rules", "game_parts.text_rules_a", "game_parts.text_rules_b")` (approval-list row, equal strictness); extend `test_both_import_orders_work_in_a_fresh_interpreter` to print one `text_rules_b` function's `__module__` too (it is skipped in the slot and first runs in CI; M9 is its slot-side stand-in).
- [ ] **Step 2:** Run (FAIL on membership, on the `_PART_MODULES` value and on the new speech-reader test). M4-M6, then set `_PART_MODULES` by hand (one `--manual "game.py:new:<N>:_PART_MODULES value"` and its `base` twin in M7). M7-M9; `PROBE ok parts=` must list `game_parts.text_rules_b`.
- [ ] **Step 3: Seeded proof for the wrapper.** Save `game.py` by the pre-plant copy rule (it holds the uncommitted move), then in the working tree only take `"game_parts.text_rules_b"` out of `_PART_MODULES`: `test_every_re_export_is_the_parts_own_object` and `test_engine_routing` (R2) go red. Restore from the saved copy (sha256 check). Record.
- [ ] **Step 4:** M10. Expected: `RESULT exit=0`.
- [ ] **Step 5: Commit** `game.py split T3.5: lore and narration text helpers, first batch, live in game_parts/text_rules_b.py`.

### Task 14: `text_rules_b.py`, batch `text-b2` — 44 names, about 367 lines (spec T3.6)

**Review tier:** normal (Opus implementer, Opus review). Money/save/Undo: no. One name, `_skill_result_category`, is patched by a money test (`api/tests/test_coin_writers.py`, `patch("game._skill_result_category", ...)`): the reviewer reads that test and confirms the file is unchanged and green. Held and why: `_death_resolution_from_actions` (death, Undo neighbour; goes with `combat_flow` under a strong review in Plan 4), `_adventure_travel_reply`, `_a_walk`, `_is_canonical_city_id` (places), `_intent_infrastructure_result`, `turn_source_key`, `_dynamic_engine_transitions` (turn).

**Files:** as Task 11, on `text_rules_b.py`.

**Batch:** `ai-dnd/scripts/engine_split/batches/text-b2.txt`. Header additions expected: `unicodedata`, `living_world`, `combat_lifecycle`.

- [ ] **Step 1: Write the tests:** `test_text_b2_lives_in_the_part` (red); `test_text_b2_helpers_answer_as_before` for `_trim_dangling_quote`, `_turkish_genitive_form`, `_word_root`, `_singular_narrator`, `_attack_verb_tokens`.
- [ ] **Step 2:** Run (FAIL on the first test). M4-M9.
- [ ] **Step 3:** M10 with `api.tests.test_coin_writers`. Expected: `RESULT exit=0`; `git diff <BASE_SHA> -- ai-dnd/api/tests/test_coin_writers.py` is empty.
- [ ] **Step 4:** Ledger: line counts of `game.py` (expected about 22 570) and of the four leaf parts (`text_rules_a` about 940, `text_rules_b` about 1 000); the list of everything held in Plan 2 with its reason and target plan.
- [ ] **Step 5: Commit** `game.py split T3.6: narration and combat-text helpers, second batch, live in game_parts/text_rules_b.py`.

### Task 15: The net's exam again, on the moved tree

**Review tier:** none (Opus runner; nothing committed). Money/save/Undo: no.

**Files:** none committed. Branch `tmp/game-py-bolme-ag-sinavi-p2b` from the Stage B tip; never pushed, not deleted. Same routine as Task 7 (one fault, its red, `git checkout HEAD -- ai-dnd`).

- [ ] **Fault 1 — bare call to a patched name.** In `text_rules_a.py` make one moved helper call bare `_topic_place_name(...)`. Expected red: `test_engine_routing` (R3 and R9).
- [ ] **Fault 2 — missing re-export.** Delete `CLASSES` from the `from game_parts.tables import` line. Expected red: `test_engine_surface` with `CLASSES` named in the message, and `test_engine_routing` (R8).
- [ ] **Fault 3 — forbidden text in a part.** The first row of `docs/engine-split/source-readers.md`: put its forbidden text into `text_rules_b.py`. Expected red: that test.
- [ ] **Fault 4 — deleted comment.** Remove one comment line from a block moved in Task 12. Expected: `move_check` `CHANGED` above zero.
- [ ] **Fault 5 — identity name.** Add `_HERE = __file__` to `schemas.py`. Expected red: `test_engine_routing` (R6).
- [ ] **Fault 6 — rebound table.** `CLASSES = list(CLASSES)` after the re-export in `game.py`. Expected red: R8 and `test_every_re_export_is_the_parts_own_object`.
- [ ] **Fault 7 — frozen alias of a moved helper (N4).** `_TOPIC = _topic_place_name` in `game.py`, one caller uses `_TOPIC`. Clean pair first (the tree before the fault): two targeted runs, labels `p2y-f7a-n4` and `p2y-f7b-n4`, modules `api.tests.gate_boot api.tests.test_talk_front` + `NEIGHBOURS`; `--collect` both. Then the fault, label `p2y-f7-n4`, same modules; `--diff --base <p2y-f7a> --base2 <p2y-f7b> --new <p2y-f7>`. Expected: `DROPS` above 0.
- [ ] **Final step:** as Task 7. A fault that stayed green stops the plan before the gate.

### Task 16: Gate TM2 (spec TM2) and PR 5

**Review tier:** whole-branch review on the strongest model (the Stage B diff).

- [ ] **Step 1:** `git fetch origin`; merge `origin/main` if it moved. If `game.py` or a part changed underneath: rerun M7 for every batch against a fresh base and regenerate the locks; the N4/N7 bases are then stale for the changed functions: list them and tell Kadir before going on.
- [ ] **Step 1b: Whole-branch review before the suites.** Whole-branch review of the Stage B diff (the reviewer reruns M7 for all six batches on the archive copy); one fix wave red-first (Opus); scoped re-review (Opus). No second wave: remaining minors are parked as debt rows. Ruling: the review and its fix wave run before the suites, as in Task 8 Step 2 — a fix after the gate would need the suites again, and a tests-only fix after them would never be `LOST`-checked — if wrong: nothing, the order only costs the suites' wait. From Step 2 on only the ledger, debt rows and PR text change; any change to code, tests or locks reruns Steps 2-5 (`Ruling` with the reason).
- [ ] **Step 2: Two full suites, one at a time, nothing else on the slots** (each after the other-run check of Global Constraints): `slot_gate.sh` labels `p2tm2-off-n4-n7`, then `p2tm2-fon-n4-n7`. Flag off: `PAR_EXIT=0`, `failing_ids 0`. Flag on: `failing_ids ⊆ F_fon` (Task 8 Step 3), every id in `F_fon` has a debt row, and no `LOST` id outside `F_fon` in Step 3; `PAR_EXIT` may be non-zero only by `F_fon` ids. A red outside `F_fon` (either flag): the plan stops and Kadir is told. Ruling: the gate runs carry the probes and are compared with the probe-carrying bases of Task 8 — like for like — and are also held to the spec's TM0 limit: a probe run under the limit proves the probe-free code is under it (probe overhead only adds time) — if a limit is exceeded, one probe-free run of that flag is made before deciding (Step 5 says what it is compared with).
- [ ] **Step 3: N4 per flag.** `ledger_diff.py --diff --base <flag>-b --base2 <flag>-c --new <tm2 flag>`: `DROPS 0` and `LOST 0` (flag on: `LOST` ids outside `F_fon` 0, Global Constraints). Stage B never renames or deletes a test id: a renamed id counts as `LOST`. Any drop or lost test: the plan stops here and Kadir is told. PR text names what N4 cannot see (48 `not_called_tests`, assignment sites, `kind other`); N3 is their guard.
- [ ] **Step 4: N7 per flag.** `coverage_by_function.py --collect` with `--engine-root` = archive of the gate commit; `--diff`: `DOWN 0`. Every `UP` name in the ledger with the test that explains it.
- [ ] **Step 5: Speed (spec §7: "Herhangi biri %10'dan fazla yavaşlarsa dur ve bildir").** Suite seconds per flag: at most 1.10 × the mean of that flag's two Task 8 probe runs, and flag off at most 2 155 s (1.10 × TM0 1959 s). A probe-free fallback run (Step 2 Ruling) is compared with probe-free references: flag off with 2 155 s, flag on with 1.10 × the seconds of `p2g0-fon-a`. Turn benchmark twice (`api.tests.bench_engine_turn`, each line is the median of 5 sessions), compared pairwise as at TM1: first reading at most 23.13 ms (1.10 × TM0 21.03 ms), second at most 23.25 ms (1.10 × TM0 21.14 ms), and each at most 1.10 × the matching Task 8 reading. Above any limit: stop and report; do not explain it away.
- [ ] **Step 6: Gate checks without a suite.** `SLOTPY outside_probe.py` → `PROBE ok parts=` lists `character_rules`, `schemas`, `tables`, `text_rules_a`, `text_rules_b` (D-341). `python test_regression.py` as a script → `Results: 30 passed, 0 failed out of 30` (D-342). `move_check.py --comments-only` against the `afe0023b` archive → `COMMENTS base=1083 now=1083`. `routing_audit.py` → `clean`. `docs/engine-split/patch-census.md` regenerated from the lock if any task changed the lock. ruff once more (if approved), output in the ledger. Review Focus 5: read `start_local.ps1` for the interpreter it starts; with that interpreter, from `ai-dnd`, run both import orders (`-c "import game, game_parts"`, `-c "import game_parts, game"`): rc 0 twice. Sizes: `game.py` real lines = `size_budget.json` value; every part under 2 500.
- [ ] **Step 7: Debt rows.** D-352 closed (N4, N7, ruff state, with the run labels). D-353, D-347, D-348, D-350 closed in their tasks: confirm. D-349, D-351, D-341, D-342, D-346 updated. New rows for every park in the ledger: no park without an owner. One row listing the 25 names held by Option B-hold and the held constants and state (`_STOCK_SAID`) with their target plan. `F_fon` rows: still open or closed, each with its state.
- [ ] **Step 8:** Recheck the free debt ids (Global Constraints). Ask Kadir: push + PR 5 (stacked on PR 4), then the merges in order. Before each: check the target tip is an ancestor (no commit lost). After each: `gh run list --repo kadirkayarr-beep/AI-DND --limit 5`, CI wait as in Global Constraints (at most 25 min), until "AI-DND bounded verification" is green; red is reported at once.
- [ ] **Step 9:** Check for open `bash`/`sleep` processes. Five-line Turkish morning summary. Ledger lines: "TM2 geçti", "oynayış: Plan 2'de gerekmez (karar 7)", "Plan 2 bitti; Plan 3 (T4) yazılabilir". The plan workspace is not deleted.

---

## Appendix: batch lists (line order of `game.py`; Task 6 writes them to `ai-dnd/scripts/engine_split/batches/`)

**tables (20):** `RACES, RACE_FEATURES, CLASSES, CLASS_FEATURES, CLASS_HIT_DICE, SKILLS, CLASS_SKILL_OPTIONS, DIFFICULTY_DC, RANDOM_NAMES, GIANT_ANCESTRY_IDS, CELESTIAL_REVELATION_FORMS, INNER_RADIANCE_SPEC, NECROTIC_SHROUD_SPEC, SPECIES_WITH_TRAIT_STATE, _ABILITY_NAMES, _ORIGIN_TEXT_KEYS, _ORIGIN_LIST_KEYS, _ORIGIN_SCORE_KEYS, DEATH_MODES, CHECK_FEATURES`

**schemas (12):** `INTENT_TYPES, SKILL_INTENT_TO_SKILL, INTENT_SCHEMA, SCENE_DETAIL_KIND_ALLOWLIST, _EXPERIMENTAL_NPC_SPEECH_SCHEMA, _EXPERIMENTAL_NPC_SPEECH_OPTIONS, NPC_SCHEMA, LOCATION_SCHEMA, WORLD_UPDATE_SCHEMA, DM_RESPONSE_SCHEMA, NARRATOR_VOICE, system_prompt`

**text-a1 (50):** `ollama_response_content, ollama_reply_was_cut, _ASKS_SOMETHING, _just_served, _THIRD_PERSON_REPORT, _SECOND_PERSON_SAID, _SAID_IT_AGAIN, _ENDS_IN_SPEECH, is_ordinary_environment_look, npc_ambiguity_response, _NEGATED_VERB_SUFFIX, _affirmative_door_verb, _SKILL_CHECK_WORD, _SKILL_ENDING, _ABILITY_WORD, _OPEN_SCARE, _COVER_WORD, _COVER, _OWN_THING_HIDDEN, _READING_CHECKS, _COMMON_SENTENCE_OPENERS, _QUESTION_CUE_RE, clean_dm_response, _hand_names_something, _ARMED_ROLE, _STRONG_ROLE, _PERSON_FIGHT, _clean_world_text, _scene_texts_for_referents, _ENGLISH_STOP_WORDS, _reads_english, _SAVE_ABILITY_TR, _unarmed_save_text, _FALL_LINE, _REWOUND_LINE, _PROPOSAL_MARKER_RE, _INTERNAL_MARK_RE, _strip_proposal_markers, _normalize_interaction_mode, _GUARD_ROLE, _GUARD_WORD, _GENERIC_PERSON, _is_guard, _serves_at_a_counter, _topic_place_name, _LOCATED_PERSON, _IN_REACH_WORDS, _COUNTER_WORDS, _COUNTER_ROLE, _drop_repeated_sentences`

**text-a2 (63):** `_is_plain_person_reference, _ADDRESSEE_OPERATIONS, _OFFER_OPERATIONS, _OFFER_MARKER, _fold_keep_punctuation, _ADDRESS_VERB, _SPEAKING_VERB, _CONTINUATION_TERMS, _OBJECT_INSPECTION, _claim_keywords, _format_npc_memory, _CLAIM_DENIAL_LINES, _SPEECH_REPEAT_LINES, _lines_already_said, speech_repeat_line, _NARRATOR_PROFILE_FIELDS, _narrator_visible_profile, _bodies_here_context, _untrusted_player_block, _extract_json_object, _NPC_SPEECH_LOG_KEY, _NPC_SPEECH_KEEP, _MENTIONS_PROMPT_RULE, _VOICED_PROMPT_RULE, _rumour_lane_on, _voiced_keys, _CLAIM_REJECTION_RE, _CLAIM_ACCEPTANCE_RE, _SPEECH_CUT_RE, _SPEECH_META_RE, _strip_pictographs, _REAL_WORLD_FAITH, _without_real_world_faith, _is_explicit_name_led_gesture_line, _clean_npc_stage_direction, _compose_experimental_npc_speech, _without_label_variant, _npc_speech_rejects_claim, _CLAIM_PLAIN_DENIAL_RE, _npc_speech_grants_claim, _spoken_name_answer, _SPEECH_ANSWER_RULES, _job_news_line, _turns_to_someone_else, _elsewhere_line, _overheard_work, _ASKS_WHO_YOU_ARE, _accept_named_job, _REFUSED_MOVE_RULE, _bag_note, _dm_prompt_note, _claim_denial_quotes, _has_private_profile_value, _FOLLOWUP_WORDS, _is_short_followup, _experimental_speech_recap, _normalize_turkish_typos, _mechanical_outcome, _GENERIC_NO_CHANGE_RESPONSE, _GENERIC_NO_CHANGE_RESPONSES, _INTERNAL_PLAYER_FACING_RE, _is_internal_player_facing_text, _narration_scene_type`

**text-b1 (39):** `_NARRATION_PERSISTENT_OBJECT_HEADS, _NARRATION_PERSISTENT_OBJECT_STATE, _registered_persistent_object_names, _HELD_SKIP, _PLAYER_MENTAL_STATE_PREFIXES, _PLAYER_MENTAL_STATE_CONTEXT_RE, _PLAYER_MENTAL_STATE_COPULA_RE, _PLAYER_MENTAL_STATE_EXPLICIT_SUBJECT_RE, _PLAYER_MENTAL_STATE_AFFECT_RE, _PLAYER_FEELING_RE, _is_figurative_key_transfer, _NARRATED_NAME_PATTERNS, _unseen_registered_names, _SPEAKING_NAME_PATTERNS, _unseen_speakers, _empty_lore_authority_context, _lore_claims_are_supported, _lore_guard_text, _lore_fact_records, _LORE_ENTITY_TITLE_RE, _LORE_PROPER_NAME_RE, _LORE_ENTITY_FOLLOWING_CUE_RE, _LORE_SENTENCE_START_WORDS, _GENERIC_SPEAKER_LABEL_RE, _is_generic_speaker_label, _LORE_UNSUPPORTED_DETAIL_PATTERNS, _LORE_RULER_TITLE_RE, _LORE_ENTITY_RELATION_RE, _LORE_ROUTE_DISTANCE_QUERY_RE, _UNVERIFIED_LORE_RESPONSE, _UNVERIFIED_DISTANCE_RESPONSE, _UNVERIFIED_RULER_RESPONSE, _INDOOR_DETAIL, _ASKS_DISTANCE, _salvage_plain_speech, _TERMINATOR_MASK, _split_sentences_keep_speech, _spoken_lore_fact_ids, _has_active_local_npc_focus_for_place_request`

**text-b2 (44):** `_validated_player_line, _WINDOW_WORDS, _LOCK_WORDS, _TRACK_WORDS, _resolved_skill_result_narration, _TELLS_FAILURE, _UNMOVED, _QUOTE_CLOSER_RE, _QUOTE_OPENER_RE, _trim_dangling_quote, _dialogue_repair_has_attributed_answer, _skill_result_category, _print_skill_result, _ATTACK_VERB_PATTERN, _ATTACK_BLOW_PHRASE, _CHARGING_IN, _ATTACK_LOOKALIKE_TOKEN, _ATTACK_INSTRUMENT_TOKENS, _INANIMATE_HIT_OBJECT, _CREATURE_REFERENCE, _attack_verb_tokens, _immediate_check_refusal, _turkish_genitive_form, _asks_what_is_going_on, _is_bare_greeting, _is_scene_referent_activity_observation, _public_scene_person_text, _LOOK_OPENINGS, _CONVERSATION_OPENINGS, _OWN_ACTS, _WALKED_UP, _said_after_approach, _SAY_VERBS, _SAY_ENGLISH, _HAIL_FILLERS, _line_addresses, _PLANNER_STAYS_OUT, _NO_BLOW_NOW, _BLOW_WORDS, _word_root, _NOT_A_LOCAL_PLACE, _NARRATOR_PRONOUNS, _NARRATOR_PLURAL, _singular_narrator`

**Held in `game.py` by this plan (not in any batch):**

| Names | Reason | Goes in |
|---|---|---|
| `_validate_combat_v3_payload, _validate_saved_multilevel_slots, _is_shopkeeper_role, _explicit_campaign_shop_request, _shop_economy_request, _explicit_campaign_shop_negative_request, _shop_presence_question, _carry_out_thread_turn, _show_coin_roll, _with_only_backed_money, _dm_response_schema_for_turn, _narrated_money_can_lie, _clear_turn_transients, _economic_listing, _restore_in_place` | in `sensitive.json` (money, save, snapshot) | Plan 4, strong |
| `_speech_debug_trail, _session` | NEVER_MOVED | never |
| `_repair_dilim1_fields` | identity name `__name__` (logger), payment-adjacent | Plan 4 |
| `roll_attack, roll_initiative, roll_initiative_npc` | call `roll_d20`: not closed | Plan 3 (`character_rules`) |
| `_has_session` | session core (reads `_ACTIVE_SESSION`) | never (Ruling candidate for Plan 5) |
| `_said_to_someone_here` | `test_talk_mode_writers` pins the files that call `talk_mode.current` | Plan 3, with the test change on the approval list |
| `get_modifier, choose_option, choose_skill_proficiencies, calculate_hp, calculate_ac, _new_species_trait_state` | Option B-hold: `character_rules` | Plan 3 |
| `_validate_player_condition_state, _validate_player_weapon_proficiencies, _validate_long_rest_history, _origin_choices_valid, _death_state_defaults, _combat_defaults, _known_happenings` | Option B-hold: `savefile` (caller `_validate_save_payload` is sensitive; `_known_happenings` filters saved `world_threads_v1`) | Plan 4, strong |
| `_STOCK_SAID` | session-less mutable state (`collections.deque`, appended through `_stock_said()`), not a constant | with `_stock_said` (Plan 3 or 5) |
| `_death_resolution_from_actions` | Option B-hold: death, Undo neighbour | Plan 4, strong |
| `_venue_door_id, _mark_lock_seen, _lock_known_to_player, _local_place_access, _a_walk, _is_canonical_city_id, _adventure_travel_reply, _town_in_play` | Option B-hold: `places` | Plan 3 |
| `turn_source_key, _intent_infrastructure_result, _dynamic_engine_transitions` | Option B-hold: turn/intent | Plan 3 or 5 |
| `INITIAL_WORLD_STATE` | one cluster with NEVER_MOVED `world_state` | never |
| `SAVE_FORMAT_VERSION, _SUPPORTED_SAVE_VERSIONS, _PERSISTED_PLAYER_CONDITION_FIELDS` | save | Plan 4 |
| `_SHOP_ECONOMY_PATTERN, _SHOP_TRANSACTION_REQUEST_PATTERN, _SHOP_ENTITY_QUERY_PATTERN, _SHOP_CREATION_ACTION_PATTERN, COIN_LEFT_BEHIND, _SOMEONE_ELSES_PURSE` | money (`_SHOP_CREATION_ACTION_PATTERN` has no reader: dead-code candidate for Plan 6, not deleted) | Plan 4 |
| `DEBUG_MODE` | config flag, not text | Plan 5 |

---

## Sonraki planlar

Each is written after Task 16 passes, as its own plan, worktree and PR. Only the inputs each needs from Plan 2.

- **Plan 3 — T4 low-impact areas to spec TM3 + Kadir's 10-minute play.** Needs: the held list above (Plan 3 rows), the refreshed `inventory.json` (call graph with re-exports counted as functions), TM2 speed numbers and the flag-on time base, N4/N7 bases retaken on the TM2 tree, D-349's open parts, the `test_talk_mode_writers` file-set pin.
- **Plan 4 — T5 money, save, combat and sensitive leftovers to spec TM4.** Needs: D-355 closed first (`sensitivity.classify` over the engine file set), the held list's Plan 4 rows, N7 noise set (equality is due at TM4).
- **Plan 5 — T6 turn core.** Needs: identity allow-list state, N4 noise set, the zero-tolerance journey list.
- **Plan 6 — T7 closure.** Needs: final sizes, dead-code candidates with both-flag N7 evidence (now real for flag on), the list of dev-only pieces to remove or keep (`gate_boot.py`, `engine_probe.py`, `slot_gate.sh`, the `uvx` ruff cache).

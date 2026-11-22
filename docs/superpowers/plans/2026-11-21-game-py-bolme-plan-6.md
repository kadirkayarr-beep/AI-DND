# game.py Split, Plan 6 (T7 closure: layout to `game.py` ≤ 1 500, final budgets, dead-code evidence, docs, closing gate, Kadir's play) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: DRAFT, amended 2026-11-22 for Plan 5's outcomes.** Plan 5 Stage A is merged (PR #139, `ae68f323`); Stage B is running. The numbers come from a read-only measurement of a `git archive` copy of p5m `f1bc2ad1` (Stage B after T6.1e) with the last batch (`turn-3`) removed by projection. They are draft numbers: Task 0 measures again on the tree that holds Plan 5's merges (Ruling M). Plan 5 held `_narrate_resolved_turn` in `game.py`; Ruling N keeps it there.

**Goal:** Close the game.py split (spec stage T7). Bring `ai-dnd/game.py` to ≤ 1 500 lines by deleting the blank lines the moves left behind, lock the final sizes, report dead-code candidates with evidence for Kadir, write the permanent rules and docs, pass the closing gate, and end with Kadir's play.

**Architecture:** Plan 6 moves nothing. One committed tool (`blank_runs.py`) deletes whole top-level blank lines beyond two in a row; a permanent test keeps it so. The dead-code report is evidence only; deletion is a separate PR after Kadir's explicit "evet" per row (spec §10). The closing gate repeats the TM routine (N4/N7 against two bases per flag, cumulative speed against `TM0BASE`) and adds a split-wide recheck: every batch's M7 and every commit's comment delta since `TM0BASE`.

**Tech Stack:** Python stdlib (`ast`, `tokenize`, `unittest`); guarded WSL runner `slot.sh`; `ai-dnd/scripts/engine_split/slot_gate.sh`; `ruff==0.17.5` and `vulture==2.14` through `uvx --from <pkg>==<ver> <pkg> ...` (Plan 3's proven form; reports only, never `--fix`). `VULTURE` = `vulture==2.14` or Task 0 Step 5's Ruling version.

**Spec:** `docs/superpowers/specs/2026-11-17-game-py-bolme-design.md` (approved 2026-11-17): §2 (goals, non-goals), §8 rows T7.1-T7.4 and "Kapı", §9 (tools), §10 (dead code), §11 (re-bloat prevention), §14 (owner decisions 7, 8, 9, 10). Where this plan and the spec differ without a `Ruling` line, the spec wins.
- Plans 3, 4 and 5 (`docs/superpowers/plans/2026-11-19-…-plan-3.md`, `2026-11-20-…-plan-4.md`, `2026-11-21-…-plan-5.md`) hold the gate routines this plan reuses by name.

**Measure folder:** `docs/superpowers/plans/2026-11-21-game-py-bolme-plan-6-measure/` (scripts `p6_measure.py <tree> <extra batch dir> <out.json>`, `remaining.py <tree> <extra batch dir>`, `part_runs.py <tree>`; `<tree>` is the folder that holds `ai-dnd/`; on `P6BASE` the extra batch dir is an empty dir; raw outputs in `out-p5m-f1bc2ad1/` (current draft) and `out/` (first draft, superseded)). Other paths: `classify_all.py` = `docs/superpowers/plans/2026-11-20-game-py-bolme-plan-4-measure/classify_all.py`; Plan 5's ledger dir = `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-p5n/.superpowers/sdd/2026-11-21-game-py-bolme-plan-5/`.

**Scope:**
- spec rows T7.1, T7.2, T7.3, T7.4 and the closing play;
- the Plan 5 I5 requirement: a Ruling and an approval row before any blank line leaves `game.py`;
- debt rows D-343, D-351, D-379, D-380(3), D-470..D-473 (Plan 5), and every row whose trigger names Plan 6, T7 or "kapanış" (table "Debt rows");
- Plan 5's parks owned by Plan 6: P5T5-1, P5T5-2, P5T5-3, P5T5-8, P5T5-11, P5T4-1, P5T4-3 (table "Plan 5 parks").

**Gates:**
- Closing gate (Task 6): N4/N7 against Task 4's bases, gate suites in both flags, cumulative speed, split-wide recheck, whole-branch review, then one PR.
- Play gate (Task 7): Kadir plays at least 10 minutes. Plan 6 and the split are "done" only after it.
- PR D (Task 8) exists only if Kadir says "evet" to deleting a dead-code row. It comes after Plan 6 and after the ledger line "oynayış yapıldı"; it is outside the autonomy grant, so its push, PR and merge each need Kadir's fresh approval in chat.

**Measured draft base (2026-11-22, read-only, `git archive` of p5m `f1bc2ad12421a21a74a9c2932914c9a6f3fefb4b`, WSL Python 3.12.3; `p6_measure.py <tree> <empty dir>`, `remaining.py`, `part_runs.py`; raw outputs `-measure/out-p5m-f1bc2ad1/`). Draft numbers; Task 0 Step 3 measures again on `P6BASE`. The first draft (p4m `9c42a1ef`, `-measure/out/`) is superseded:**
- `game.py` at `f1bc2ad1`: 5 264 lines = 1 381 blank + 298 comment-only + 3 585 code.
- Still to move before Plan 6: 1 name (`turn-3`: `_run_player_turn_internal`). `_narrate_resolved_turn` (351 lines, 1 sensitive) is held: Plan 5 Task 4's `move_block` refused it ("engine name 'ResolvedTurn' in a annotation", N3 rule 4; parts have no `from __future__ import annotations`), and `turn-2.txt` now holds only `_owner_module_reply`. It is not projected out.
- Projected `game.py` after Plan 5: **2 509 lines = 1 315 blank + 107 comment-only + 1 087 code** (1 projected re-export line). Plan 5's rehearsal (Task 4, after `turn-3`) measured 2 509 too.
- Top-level blank runs in that projection: largest 105, 96, 90, 74; 79 runs in all.
- **Blank rule (at most 2 blank lines between two top-level statements, PEP 8; nothing inside a statement touched): 2 509 → 1 398 lines** (204 blank; 1 111 lines deleted; 102 lines under 1 500). Keeping at most 1 would give 1 326. Without the hold (first draft) it was 1 021.
- What stays in `game.py`: 8 functions (`_speech_debug_trail`, `_narrate_resolved_turn`, `start_terminal_game`, `_restore_in_place`, `_dynamic_engine_transitions`, `_session`, `_bind_session_engine`, `create_session`), `GameSession` (439 lines), 13 assignments, 7 other top-level statements, and the import/re-export lines.
- Parts at `f1bc2ad1`: every part has at most 2 blank lines in a row at top level (`part-runs.out`); the layout touches only `game.py`. Largest: `turn_front.py` 2 250 (final; ≤ 2 500), `combat_flow.py` 2 206, `narration.py` 2 073. `turn.py` is 903 now and 3 667 after `turn-3` (rehearsal), then frozen at that size (spec §11).
- `p6_measure.py` printed `SKIPPED 5` (not UTF-8): `ai-dnd/docs/evidence/v01-20261025/phase1-run1.log`, `phase1-run2.log`, `phase2-red.log`, `ai-dnd/reports/wave3-local-live-20261006/full_suite_api_discover_retry.log`, `full_suite_release_gates_retry.log`. Task 0 Step 3 and Task 5 Step 1 rule each one.
- Dead-code draft (spec §10 condition 1 only, `p6_measure.py` scan over the whole tree): the spec's 5 candidates are all still defined. 2 have no mention outside their definition, their re-export line and the split's own bookkeeping files: `_filter_unsupported_lore_paragraphs` (`lore.py`, 13 lines), `_existing_local_tavern` (`places.py`, 13). 3 are called only by the split's own pin tests in `test_engine_parts_pilot`: `analyze_player_action` (`intent.py`, 10), `is_dialogue_or_emotion` (`intent.py`, 3), `update_world_state_from_player` (`intent.py`, 5; moved in `intent-s` after the first draft; its pin calls `game.update_world_state_from_player`). The whole-engine scan found no further name. Conditions 2-4 are not tested yet.

## Global Constraints

- **Precondition and base.**
  - Plan 5's ledger ends with "Plan 5 bitti; Plan 6 (T7) yazılabilir"; Plan 5's PRs A, B and C are merged; `origin/main` contains them.
  - `P6BASE` = the `origin/main` commit when Task 0 starts.
  - `TM0BASE` = `2e576967dda2fbfdf6a47d22d9313fbc76c195f8` (unchanged since Plan 4).
  - `CUM_P5` = Plan 5's last binding cumulative ratio (its ledger, Task 14). Information only for this plan.
- **Ruling M (draft, amended 2026-11-22): measured on p5m `f1bc2ad1` with `turn-3` projected, not measured on `P6BASE`** — `P6BASE` does not exist yet (Plan 5 Stage B and C still run) and the controller asked for the amendment now — if wrong: Task 0 Step 3 measures again on `P6BASE`; measurement wins, with a `Ruling` per changed number.
- **Ruling N: `_narrate_resolved_turn` stays in `game.py` in Plan 6 (no move, no pre-move edit)** — with it, `game.py` after the blank rule is 1 398 lines (draft), under spec §2's "1 500 satırın altına" and §11's cap, so the size goal holds with zero code change; every move costs more and two options break a limit: `turn.py` is frozen at its arrival size (spec §11, "yalnız küçülebilir"); `turn_front.py` would be about 2 605 > 2 500; `narration.py` would be about 2 430 (fits, but the function is turn core: it commits travel and reaches `GameSession.evaluate_quest_events`, a save writer); a new part adds a header, a `_PART_MODULES` entry and a budget entry; and every move first needs the annotation fix (P5T4-1), the save-writer pin (P5T5-8), a strong M1-M12 move task and a bench series, in a plan that moves nothing; spec §5's "`game.py` (kalır)" list does not name it, so §24 row 9 marks the deviation "gevşetme olabilir", and the move goes to the turn-split slice (spec §12, D-470's owner) with its preconditions in the "Plan 5 parks" table — if wrong: 351 lines stay in `game.py` one slice longer and the cap keeps only about 100 lines of headroom; the later move is the same work it is today.
- **Autonomy (Kadir 2026-11-20, Plans 3-6).**
  - Every "ask Kadir" or "tell Kadir" becomes a ledger entry plus a line in `kadir-notes.md`, with a `Ruling`. Nothing waits for an answer, except the two owner stops below.
  - The controller pushes, opens PRs and merges under that grant, for Tasks 0-7 only. Task 8 runs after Plan 6: the grant does not cover it, and CLAUDE.md's default applies (push, PR and merge each with Kadir's fresh approval in chat). Workers never push, open PRs, merge, delete branches or force anything. No force push. Never delete a branch.
  - Before a merge, check that the target tip is an ancestor of the merged branch.
  - After every push or merge, run `gh run list --repo kadirkayarr-beep/AI-DND --limit 5`. "AI-DND bounded verification" must be green before "done". A red run is reported at once; before any rerun, save `gh run view <id> --log-failed` in the ledger dir and rerun only the failed job.
- **Owner stops (not covered by the autonomy grant).**
  - **Dead code is never deleted in Plan 6.** Spec §10: "Hiçbir şey Kadir'in 'evet'i olmadan silinmez. Silme, plan bittikten sonra kendi küçük PR'ıdır." §14 decision 9: "tablo gelmeden karar verme." CLAUDE.md: deletion needs the owner's view. Task 5 writes the table; Task 8 runs only on Kadir's own "evet" in chat, quoted into the ledger.
  - **Play gate.** CLAUDE.md (Kadir, 2026-11-12): no slice is done before Kadir plays at least 10 minutes. Ruling D (Plans 4-5: "oynayış ertelendi") ends here, in Task 7.
- **Real stops** (unchanged): a speed limit exceeded (spec §7); an irreversible or destructive action; a security-sensitive action; a plan so broken that every path is a guess.
- **Ruling B: cumulative speed, binding at the closing gate only.** Plan 4's fair A/B, OLD = `p6o` (`TM0BASE`), NEW = the closure tip, prefix `p6t6cum`. Ratio above 1.10: STOP and tell Kadir; no retake to pass.
  - Ruling: no A/B in Tasks 1-3 — they change no executed line (blank lines, one comment block, one subtest keyword, docs) — if wrong: Task 6's binding series still catches it, later.
  - Method (labels `p6t6cum-bench-warmold-off`, `-warmnew-off`, `-old<k>-off`, `-new<k>-off`, k = 1..5): gate wait and foreign-load check before every run, `FSLOT` 4; one warm-up each, discarded; five pairs O,N,N,O,O,N,N,O,O,N; each `slot.sh 4 <WT> test <label> 1800 api.tests.bench_engine_turn`; pass median(NEW)/median(OLD) ≤ 1.10. Raw `RESULT` and `TURN_BENCH` lines to the ledger with both tree identities. A failed single run is rerun once at its position; the series is never rerun.
  - Plus one flag-on reading `p6tcbench-fon` on `p6n` (Plan 5's `p5tm5bench-fon` form): recorded only, information, never a stop.
- **Ruling C: full suites.** Shard timeout 4 500 s: `slot_gate.sh <FSLOT> <WT> <label> 3 4500 '.'`; pattern runs too. Wall clock. Limits: flag off ≤ 2 155 s and ≤ 1.10 × the mean of Task 4's two flag-off bases; flag on ≤ 1.10 × the mean of its two flag-on bases. Longest-shard ratio is information.
- **Ruling E: waits, long runs, continuation** (Plan 5 text, unchanged):
  - No Monitor tool, no background wait. Foreground bash loops of at most 9 minutes per call (`sleep 60`), at most 150 minutes per agent.
  - Long runs are written to `<ledger>/run-<label>.sh` and started detached with exactly:
    `powershell.exe -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath 'C:\Program Files\Git\bin\bash.exe' -ArgumentList '-lc','\"bash <ledger>/run-<label>.sh > <ledger>/<label>.out 2>&1\"'"`
    The escaped inner quotes are required (Plan 4 Task 10 lost two starts without them). Start check within 2 minutes: the `.out` file exists and `pgrep -af slot_gate` shows the label; otherwise stop the stray bash processes by recorded pid, ledger line, start once more.
  - At 150 minutes: **Status CONTINUE** with the label, start time and `.out` path. A running or finished run is never restarted.
  - Continuation after a lost agent: save `git diff HEAD` and `git status --short` to `<ledger>/task-<N>-killed-partial.diff`; check no run of the task is still going; `git checkout HEAD -- <the task's Files>`; redo the task from Step 1 with labels suffixed `-r2`. A half-made `game.py` edit is never resumed.
- **Ruling F: slots and safety.**
  - `SLOT` 2 for targeted runs; `FSLOT` 4 for `slot_gate.sh` and benches. Slots 3 and 5 belong to others. Ruling: slots 2 and 4 again — Plan 5 has finished with them — if wrong: Task 0 Step 1 reads Plan 5's ledger end and `pgrep`; a slot in use waits.
  - Gate wait `run-gatewait.sh` before every `slot_gate.sh` call and bench; go only on `RC=1`, and for `slot_gate.sh` also `AVAIL_MB` ≥ 3 500; `pgrep -af slot_gate` empty. Never two full suites at once. No other slot run of this plan while a full suite or bench runs. No browser tests.
  - Foreign load: `run-foreignload.sh` copied unchanged from Plan 5's ledger dir (WMI class `Win32_PerfFormattedData_PerfOS_Processor`). `FOREIGN_CPU_PCT` ≤ 25 before a series or suite; else poll every 5 minutes for at most 35 minutes, then go and write "yük altında".
  - Keys and `.env` are never read. Debt rows have exactly 8 `|`.
- **The flag.** Every targeted run happens twice: `<run>-fon` with `api.tests.gate_boot` first and `api.tests.test_engine_gate_boot` in the list; `<run>-off`, never containing the letters `fon`. Labels `p6t<task>-<step>-<off|fon>`. Never `slot.sh ... par`. Pass at every gate: `failing_ids 0` in both flags.
- **Worktrees** (one writer each; `WT` = folder name only):

  | Worktree | What | Used by |
  |---|---|---|
  | `AI-DND-k2-bolme-p6` | branch `task/game-py-bolme-p6` (this draft) | plan files only |
  | `AI-DND-k2-bolme-p6n` | branch `task/game-py-bolme-p6-close` off `P6BASE` | Tasks 0-3, 5, 6 |
  | `AI-DND-k2-bolme-p6b` | detached at `P6BASE` | Task 4 bases, Task 5 evidence |
  | `AI-DND-k2-bolme-p6o` | detached at `TM0BASE` | cumulative OLD |

  Ruling: a new `p6o`, not Plan 5's `p5o` — one plan never runs from another plan's worktree — if wrong: one more checkout on disk.
- **Freeze (spec decision 3):** while the closure PR is open, no other branch touches `ai-dnd/game.py` or `ai-dnd/game_parts/`.
- **Run commands.**
  - Targeted: `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <SLOT> <WT> test <label> 1800 <modules...> <NEIGHBOURS>`. Pass `RESULT exit=0 Ran <n> tests`. Modules under `ai-dnd/api/tests/` are `api.tests.<m>`; root modules bare.
  - `NEIGHBOURS` = `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`, in every targeted run.
  - `ENGINE_SET` = Plan 5's eleven modules plus `api.tests.test_engine_layout` (Task 1) from Task 1 on: `api.tests.test_engine_parts_pilot api.tests.test_engine_routing api.tests.test_engine_surface api.tests.test_engine_patch_census api.tests.test_engine_size_budget api.tests.test_engine_hash_parts api.tests.test_engine_sources api.tests.test_engine_split_inventory api.tests.test_engine_sensitivity api.tests.test_engine_module_alias api.tests.test_engine_move_tool`.
  - `SLOTPY`: after a `slot.sh` call synced the tree, run a script with the slot's Python 3.13 as `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash <ledger>/run-<name>.sh < /dev/null`. Never `bash -c '...'` (D-351). Never Windows Python for engine_split tools (D-358). The slot's tree is a synced copy: a tool that writes a file gets the absolute worktree path (`/mnt/c/Users/Kadir/Desktop/AI-DND-k2-bolme-p6n/...`), never a relative one.
  - `SLOT_GATE` = `ai-dnd/scripts/engine_split/slot_gate.sh`.
- **Stores.**
  - `STORE` = `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p6/` (draft measurement `tree/`, `out/`; Task 0's `out-p6base/`). Worker rules: `STORE/common.md`.
  - Ledger: `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-p6n/.superpowers/sdd/2026-11-21-game-py-bolme-plan-6/progress.md` (local, not committed). `run-*.sh`, `pre-plant/`, `kadir-notes.md`, `task-<N>-report.md` live there. Raw lines are copied, never estimated. Decisions: `Ruling: <karar> — <neden> — <yanlışsa maliyeti>`.
- **Red first.** Every new test is seen failing for the stated reason before the change. A guard green on a clean tree is shown red with a planted fault under Plan 3's pre-plant rule (copy file and sha256 to `pre-plant/`; plant; run; copy back; check sha256 and `git diff HEAD --stat` unchanged). A first-run green meant to be red becomes a guard plus a `Ruling`; a red is never forced.
- **Old-behaviour tests** change only with equal or greater strictness, each with a row in `docs/agents/onay-listesi-20261115.md` §24. Ruling: a new section "## 24. game.py bölme Plan 6 (dal `task/game-py-bolme-p6-close`)", created in Task 0 — if wrong: a heading. A moved boundary is marked "gevşetme olabilir". Unmarked loosening, skipping or deleting stops the work.
- **Findings** go to `docs/agents/debt-register.md`, ids `D-490..D-509` (Plan 4 holds D-450..D-469, Plan 5 D-470..D-489; Plan 5's controller found D-469 as the highest id on `origin/main` and `p5n` on 2026-11-22). Before each push, read the highest id on `origin/main` and open branches.
- **Review tiers.** Opus implementers; Opus runners for Tasks 0 and 4. Every committed change gets an independent Opus review on a `git archive <sha>` copy. Strong (deletion, whole-branch): Tasks 1 and 6, and Task 8 if it runs. Normal Opus: Tasks 2, 3, 5. The fable model is never used.
- **Tools.** Stdlib only in committed code and in CI. Forbidden: `ast.unparse`, formatters, `ruff --fix`, `ruff format`, rope, libcst codegen, import-linter, desloppify. `blank_runs.py` deletes whole lines in place and never rewrites a line. `sensitivity.py --write` is never run.
- **Every implementer brief carries:** `docs/agents/implementer-preamble.md`; `STORE/common.md`; the graphify rule (`graphify query "<question>"` with cwd `C:/Users/Kadir/Desktop/AI - DND` before the first grep or source read; raw files only for located lines; `graphify update .` once at the end, never committed); function and file names, never line numbers; "never read `game.py` or a part over 1 000 lines whole"; the superpowers skills `test-driven-development` and `verification-before-completion`.

## Review Focus

Failure modes the spec implies but no listed check exercises; each is pinned in the task named.

1. **A blank line inside a string or a statement is deleted.** A triple-quoted prompt or a multi-line literal in `game.py` changes its value. Pinned by `test_blank_lines_inside_a_statement_are_kept` (fixture with a blank line inside a triple-quoted string and inside a function, Task 1), `test_verify_refuses_a_blank_line_removed_inside_a_def` and Task 1 Step 4's verify (`ast.dump` equal, and the deleted line numbers are exactly `find(old, keep)`).
2. **The layout breaks a test that reads `game.py` text.** Source readers (N6) and the hash change. Pinned by Task 1 Step 5's pattern run over every module named in `docs/engine-split/source-readers.md` plus `test_engine_sources` and `test_engine_hash_parts`, both flags.
3. **A function looks dead because only its spelling is searched.** A dynamic `getattr` or `session.<name>` reaches it. Pinned by Task 5 Step 3 (every non-literal `getattr(<engine alias>, …)` site listed and ruled) and condition 2 read from raw executed lines, both flags, two runs each.
4. **The size cap drifts back up.** `size_budget.json` is raised later without the spec cap noticing. Pinned by `test_game_py_is_within_the_spec_cap` (Task 1): the lock value and the real size are both under 1 500.
5. **The closing gate compares against the wrong base.** Bases taken on a tree that already holds Plan 6 changes would hide nothing but would also prove nothing about Plan 6. Pinned by Task 4 Step 1 (`p6b` HEAD = `P6BASE`, checked) and Task 6 Step 5 (`ledger_diff.py` refuses a base and base2 taken on different trees; the NEW tree is checked by the HEAD line in the ledger).

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `ai-dnd/scripts/engine_split/blank_runs.py` (new) | find and delete top-level blank lines beyond `keep` in a row; verify a layout edit | 1 |
| `ai-dnd/api/tests/test_engine_layout.py` (new) | tool tests on fixtures; the permanent guard over every engine file | 1 |
| `ai-dnd/game.py` | blank lines only (Task 1); one comment block leaves (Task 2) | 1, 2 |
| `ai-dnd/api/tests/engine_split_locks/size_budget.json` | `game.py` lowered to its real size | 1 |
| `ai-dnd/api/tests/test_engine_size_budget.py` | `test_game_py_is_within_the_spec_cap` | 1 |
| `ai-dnd/game_parts/tables.py` | the K01/K02 comment block above the spec constants it describes (D-379) | 2 |
| `ai-dnd/api/tests/test_engine_parts_pilot.py` | subtest keyword `raw` → `after` (D-380(3)); two `TurnIdentityNames` pins turn without the classifier warning (P5T5-11) | 2 |
| `ai-dnd/scripts/engine_split/requirements-dev.txt` | `vulture==2.14` | 2 |
| `CLAUDE.md`, `docs/agents/implementer-preamble.md`, `GLOSSARY.md` (new), `docs/adr/0001-game-parts-merkez-kurali.md` (new), `docs/design/INDEX.md` | permanent rules and the record of the split (spec T7.3, decision 8) | 3 |
| `docs/engine-split/olu-kod-kaniti.md` (new) | dead-code evidence table for Kadir (spec §10, T7.2) | 5 |
| `docs/agents/debt-register.md`, `docs/agents/onay-listesi-20261115.md` §24 | rows | 0-6 |

---

### Task 0: Open the closure, measure again

**Review tier:** none (Opus runner). Its commit is read by Task 6's whole-branch review.

- [ ] **Step 1: Precondition.** `git fetch origin`. Plan 5's ledger ends with "Plan 5 bitti; Plan 6 (T7) yazılabilir"; Plan 5's PR C tip is an ancestor of `origin/main`. `P6BASE` = `origin/main`; write its sha. Read `CUM_P5`. `pgrep -af slot_gate` empty; no Plan 5 run on slots 2 and 4.
- [ ] **Step 2: Worktrees and ledger.**
  - `git worktree add ../AI-DND-k2-bolme-p6n -b task/game-py-bolme-p6-close <P6BASE>`; `--detach ../AI-DND-k2-bolme-p6b <P6BASE>`; `--detach ../AI-DND-k2-bolme-p6o 2e576967dda2fbfdf6a47d22d9313fbc76c195f8`.
  - Bring the plan in: `git checkout task/game-py-bolme-p6 -- docs/superpowers/plans/2026-11-21-game-py-bolme-plan-6.md docs/superpowers/plans/2026-11-21-game-py-bolme-plan-6-measure`.
  - `docs/design/INDEX.md`: bring only this branch's one added line (`git diff <merge-base of task/game-py-bolme-p6 and origin/main> task/game-py-bolme-p6 -- docs/design/INDEX.md`, keep only the `bolme-plan-6` line, `git apply`). If it refuses, add the line by hand after the Plan 5 line. Check: `git diff P6BASE -- docs/design/INDEX.md` shows exactly one added line and no removed line.
  - Create the ledger. Copy Plan 5's `run-gatewait.sh` and `run-foreignload.sh` unchanged.
- [ ] **Step 3: Measure again (Ruling M).** `git archive P6BASE | tar -x -C STORE/tree/p6base`; run `-measure/p6_measure.py STORE/tree/p6base <an empty dir> STORE/p6base.json`, `remaining.py STORE/tree/p6base <an empty dir>` and `part_runs.py STORE/tree/p6base` with WSL `python3 -I`; outputs to `STORE/out-p6base/` and copy them into `-measure/out-p6base/`. Expected:
  - `STILL_TO_MOVE 0`; `AFTER_P5` equals `TODAY` (nothing left to move);
  - `SKIPPED` from `p6_measure.py`: each skipped path gets a Ruling (is a mention lost?); draft: 5 old logs, not UTF-8;
  - `TODAY_KEEP2` < 1 500 → "the size path holds" (draft: 1 398). Write the real numbers in the plan's "Measured draft base" as a `P6BASE` line.
  - `remaining.py` lists `function _narrate_resolved_turn 351` (Ruling N applies). If Plan 5 moved it after all: Ruling N lapses, ledger line, §24 row 9 is not written.
  - If `TODAY_KEEP2` ≥ 1 500: Ruling plus `kadir-notes.md` line; Task 1 still runs, `game.py`'s budget becomes the real size, D-473 stays open with the number. Plan 6 does not move code to reach 1 500.
  - Every part ≤ 2 500 or at a frozen `files` entry (`narration_safety.py`, `turn.py`); every part's top-level blank runs ≤ 2. A part with a run > 2: Ruling, and Task 1's layout covers it too.
  - The spec's five dead-code candidates: where each is defined now (draft: `lore.py`, `places.py`, `intent.py` ×3).
- [ ] **Step 4: Locks on `P6BASE`** (Plan 5 Task 0 Step 4 routine, in `p6n`): targeted `p6t0-base-off`/`-fon` with `ENGINE_SET` + `NEIGHBOURS`: `RESULT exit=0` twice; `surface.py --write`, `patch_census.py --write --lock STORE/census-p6base.json`, `wc -l game.py`, `move_check.py --comments-only` (gives `<C6>`, the comment count of `P6BASE`), `classify_all.py`. Expected: byte-equal locks, `wc -l` = `size_budget.json`, `DIFF not_in_lock=0`. A difference: trace the commit, debt row, fix in Task 1's commit.
- [ ] **Step 5: Tools.** In WSL: `uvx --from ruff==0.17.5 ruff --version` and `uvx --from vulture==2.14 vulture --version` print those versions. If `vulture==2.14` cannot be resolved: Ruling, the newest release at least two weeks old, pinned exactly (spec §9 "sabit sürüm"); that is `VULTURE` from here on. Ledger line with both outputs. `p6o` smoke: `slot.sh 4 AI-DND-k2-bolme-p6o test p6t0-oldtree-off 1800 api.tests.bench_engine_turn` gives a `TURN_BENCH` line, or STOP.
- [ ] **Step 6: Batch → commit map** (read-only, ledger script; used by Task 6 Step 2). For every `scripts/engine_split/batches/<B>.txt` listed in `T3_BATCHES`..`T6_BATCHES` of `test_engine_surface.py`:
  - primary key: the batch's M11 commit subject from its plan's task text (Plans 2-5), `git log --no-merges --fixed-strings --grep "<subject>" --format=%H TM0BASE..P6BASE` (`--no-merges`: a single-commit PR's merge message can repeat the subject);
  - cross-check: `git log --format=%H -S "def <name>(" TM0BASE..P6BASE -- ai-dnd/game_parts/<part>.py` (or `-S "class <name>"`) for the batch's first name, searching for the name token, not the whole line; for a constant use `-G '^<NAME> ='` instead of `-S "<NAME> ="` (`-S "RACES ="` also counts `SUBRACES =`) and take the oldest listed commit (`-G` also lists a later edit of that line);
  - the batch file as it is at `P6BASE`: `turn-2.txt` holds only `_owner_module_reply` (Plan 5 hold commit `c506d846`), so its first name is `_owner_module_reply`; `_narrate_resolved_turn` is in no batch file and in no map row;
  - both give the same single commit; the manual pair `game.py:base:<N>:_PART_MODULES` and `game.py:new:<M>:_PART_MODULES` (`<N>`, `<M>` from `grep -n '^_PART_MODULES'` in `<commit>^:ai-dnd/game.py` and `<commit>:ai-dnd/game.py`), only when the `_PART_MODULES` line text differs between `<commit>^` and `<commit>` (compare the line text, not `grep -n` output). It is not tied to a part's first batch: on this branch the line does not change in the first batch of `tables`, `schemas`, `text_rules_a`, `character_rules`, and a `--manual` entry that exempts nothing is itself a `CHANGED` line.
  - Table batch / part / commit / manual pair (`pair` or `none`) in the ledger. A batch with no commit, two commits, or disagreeing keys: Ruling with the evidence; a batch that cannot be mapped at all is a STOP for Task 6 Step 2, found now instead of at the gate.
- [ ] **Step 7: Debt bookkeeping** (ledger only): every row whose trigger names Plan 6, T7, "kapanış" or "bölme kapanışı", Plan 5's D-470..D-489 included, added to this plan's table with its task. For each park in "Plan 5 parks": the register row id Plan 5's Task 13 Step 8 wrote for it, or "none". Free-id check for D-490..D-509.
- [ ] **Step 8: Approval list and commit.** Create §24 with rows 1 and 6 ("Approval list §24 rows"). **Commit** `game.py split plan 6: plan and measurements (measured again on P6BASE)`.

### Task 1: Layout — delete the blank lines the moves left behind; final `game.py` budget

**Review tier:** strong (Opus implementer, Opus review). It deletes lines from the file that holds `GameSession` (Undo); spec T7 and Plan 4's outline: "strong review on any deletion".

**Ruling (Plan 5 I5, D-379, D-473): deleting blank lines that moves orphaned is the end of the moves, not a format fix** — spec §2 lists "biçim düzeltme" as a non-goal, but spec §2 also sets `game.py` ≤ 1 500 as a goal, and moving cannot reach it (2 509 projected lines, 1 315 blank); D-379 already holds the Plan 3 Ruling "Plan 6'da tek bir düzen commit'i"; the rule removes only whole blank lines between top-level statements beyond two (PEP 8), never inside a statement, so code, comments, strings and line order are unchanged — if wrong: one revert commit restores every blank line; `engine_hash` changes either way. §24 row 2 marks it "gevşetme olabilir (spec §2 hedef olmayanı yorumlanıyor)". `kadir-notes.md` lines: "game.py'deki taşımadan kalan boş satırlar silindi: <önce> → <sonra> satır; kod, yorum ve metin aynı." and "yeni kalıcı kural: motor dosyalarında üst düzeyde en çok iki boş satır (test_engine_layout)".

**Ruling: the cap test asserts `< 1500`** — spec §2 says "1 500 satırın altına" (strictly under), §5 and §11 say ≤ 1 500; the strict form satisfies both — if wrong: a file of exactly 1 500 lines is refused, one line short of the looser reading.

**Files:**
- Create: `ai-dnd/scripts/engine_split/blank_runs.py`, `ai-dnd/api/tests/test_engine_layout.py`
- Modify: `ai-dnd/game.py` (blank lines only) plus any part Task 0 Step 3 named, `ai-dnd/api/tests/engine_split_locks/size_budget.json` (`files["game.py"]`), `ai-dnd/api/tests/test_engine_size_budget.py`, `docs/agents/onay-listesi-20261115.md` §24 (rows 2, 3, 4, 9)

**Interfaces — Produces:**
- `blank_runs.find(lines: list[str], keep: int = 2) -> list[int]`: 1-based numbers of blank lines (only whitespace) that are outside every top-level statement's span (first decorator line to `end_lineno`) and come after `keep` such blank lines in the same run. Runs at the very start or end of the file count the same way. Callers split text on `"\n"` only (keeping `\r`), never `str.splitlines`, so line numbers match `ast`.
- `blank_runs.verify(old: str, new: str, keep: int = 2) -> list[str]`: empty when `new` is `old` with exactly the lines `find(old_lines, keep)` removed: with greedy forward alignment (old line i matches the next new line when equal, else it is deleted; this matches `find`'s "after `keep`" rule), the set of deleted line numbers equals `find(old_lines, keep)`; every deleted line number lies outside every `[first decorator line, end_lineno]` span of `ast.parse(old).body`, computed in `verify` itself without calling `find`; the non-blank lines are equal in order; `ast.dump(ast.parse(old)) == ast.dump(ast.parse(new))` (no attributes); the `tokenize` COMMENT tokens are equal in order. Otherwise one finding per broken rule.
- CLI: `blank_runs.py --check <file>...` prints `RUNS <file> <n>` and exits 1 if any file has a line to delete; `blank_runs.py --apply <file>` deletes those lines in place (bytes outside them unchanged, line endings kept) and prints `DELETED <file> <n>`.

- [ ] **Step 1: Tool tests (red: no module).** In `test_engine_layout.py`, on fixtures:

```python
def test_a_run_of_five_between_two_defs_keeps_two(self):          # find -> the 3 extra lines; apply -> 2 left
def test_blank_lines_inside_a_statement_are_kept(self):            # blank line inside a triple-quoted string and inside a def body: find -> []
def test_a_comment_block_keeps_its_place(self):                    # "def a\n\n\n\n# note\ndef b": only blank lines go; the comment stays above b
def test_apply_keeps_crlf_and_every_other_byte(self):              # CRLF fixture: removed lines are exactly the found ones
def test_verify_refuses_a_changed_line_and_a_lost_comment(self):   # verify -> findings for an edited line and for a deleted comment
def test_verify_refuses_a_blank_line_removed_inside_a_def(self):   # one blank line deleted inside a def body: ast/comments equal, verify -> a finding
def test_a_form_feed_inside_a_string_does_not_shift_lines(self):   # "\x0c" inside a string literal before a run of 5: find -> the right 3 line numbers
def test_verify_refuses_a_line_inside_a_def_even_if_find_returns_it(self):  # mock.patch find to also return a blank line inside a def; that line deleted: verify -> a finding (span check)
```

  Run `api.tests.test_engine_layout` + `ENGINE_SET` + `NEIGHBOURS` (`p6t1-red-off/-fon`): the new module fails on import.
- [ ] **Step 2: Implement `blank_runs.py`** with the interface above (stdlib only; reuse `inventory.top_level_index` spans where it fits — its `start` includes the comment block above, so derive spans from `ast` decorators and `end_lineno` as `find` defines). Run again (`p6t1-tool-off/-fon`): `RESULT exit=0`. **Commit** (only the tool and `test_engine_layout.py` with the fixture tests; no real-file test yet, so no red test is committed) `game.py split T7.1a: blank_runs.py finds and deletes top-level blank runs beyond two (tests on fixtures)`.
- [ ] **Step 3: Guards on the real files (red on `P6BASE`).**

```python
def test_no_engine_file_has_more_than_two_blank_lines_in_a_row_at_top_level(self):
    # for every path in engine_source_files(ROOT): blank_runs.find(lines, keep=2) == []
def test_game_py_is_within_the_spec_cap(self):   # in test_engine_size_budget.py
    # LOCK["files"]["game.py"] < 1500 and real_sizes()["game.py"] < 1500  (spec §2 "altına"; §5, §11 say <= 1500)
```

  Run them: both red on `game.py` only (draft: 1 111 lines to delete, 2 509 > 1 500). If the cap test is green here (a smaller `P6BASE`), it becomes a guard: plant `files["game.py"] = 1500`, see red, restore.
- [ ] **Step 4: Apply.** `SLOTPY blank_runs.py --apply /mnt/c/Users/Kadir/Desktop/AI-DND-k2-bolme-p6n/ai-dnd/game.py` (absolute worktree path, never relative: the slot's tree is a copy; the same for any part Task 0 Step 3 named). Then:
  - in `p6n`: `git diff --numstat -- ai-dnd/game.py` shows 0 added and about 1 111 deleted (the `DELETED` number); a worktree diff of 0 lines means the copy was edited: STOP, redo with the absolute path;
  - write the old text with Git Bash, `git -C <p6n> show P6BASE:ai-dnd/game.py > <ledger>/game-p6base.py` (WSL git cannot read the `p6n` worktree: its `.git` file points at a `C:/...` gitdir); then a ledger script run through SLOTPY on the two `/mnt/c/...` paths: `blank_runs.verify(<ledger>/game-p6base.py, <p6n>/ai-dnd/game.py)` prints nothing;
  - `move_check.py --comments-only` against the `P6BASE` archive: `COMMENTS base=<C6> now=<C6>`;
  - `size_budget.json` `files["game.py"]` = the new real size (lowering needs no approval, spec §11);
  - `routing_audit.py` → `clean`; `outside_probe.py` → `PROBE ok`; `python test_regression.py` → `Results: 30 passed, 0 failed out of 30`.
- [ ] **Step 5: Runs.** Targeted `p6t1-off/-fon`: `ENGINE_SET` + `api.tests.test_engine_layout` + `NEIGHBOURS`: `RESULT exit=0`. Pattern run `p6t1-readers-off`, then `p6t1-readers-fon` (Ruling E form): every module in `docs/engine-split/source-readers.md`, `test_engine_sources`, `test_engine_hash_parts`, `test_sessions`, `test_startup`: `PAR_EXIT=0`, `failing_ids 0`.
- [ ] **Step 6:** §24 rows 2, 3, 4, 9; `kadir-notes.md` lines (above) plus "Tur anlatım işlevi `_narrate_resolved_turn` (351 satır) game.py'de kaldı (Ruling N); boyut hedefi yine tutuyor, tur bölme diliminde çıkacak.". **Commit** (the real-file guard, the cap test, the budget and the blank-line deletion) `game.py split T7.1b: game.py loses the blank lines the moves left behind (<before> -> <after> lines); budget and spec cap locked`.

### Task 2: Closing tidy-ups (D-379 comment, D-380(3), D-351, dev tools, parks P5T5-11 and P5T5-2)

**Review tier:** normal (Opus implementer, Opus review). No executed engine line changes. Four commits, one review.

**Files:** Modify `ai-dnd/game.py` (one comment block leaves), `ai-dnd/game_parts/tables.py` (it arrives), `ai-dnd/api/tests/test_engine_parts_pilot.py`, `ai-dnd/scripts/engine_split/requirements-dev.txt`, `docs/agents/onay-listesi-20261115.md` §24 (rows 5, 10). Planted and restored only (never committed): `ai-dnd/scripts/engine_split/move_block.py` (Step 6).

- [ ] **Step 1: D-379 second half.** The K01 and K02 comment lines above `RULE_ORDER` in `game.py` describe the species-trait specs that live in `game_parts/tables.py` (graphify "INNER_RADIANCE_SPEC Necrotic Shroud spec constant tables"). The K04 line describes `RULE_ORDER` and stays.
  - Ruling: the move completes T3.1's move of these specs (the comments were left behind), not a format fix (spec §2 non-goal) — the text and order are unchanged, only the file changes — if wrong: one revert puts the lines back.
  - Ruling: K01 (Necrotic Shroud) and K02 (Inner Radiance) move as one block, unchanged and in their order, to directly above `INNER_RADIANCE_SPEC` (the first of the two constants in `tables.py`) — splitting the block would reorder comment text — if wrong: a reader sees the Necrotic Shroud line one constant early. If K01 or K02 describes a constant that is not in `tables.py`, the block stays where it is (Ruling). D-379 says "K02/K04": K04 describes `RULE_ORDER` and stays.
  - Check: `move_check.py --comments-only` → `COMMENTS base=<C6> now=<C6>`; the COMMENT token texts over all engine files are equal as a multiset (ledger script); `blank_runs.py --check` clean; `ast.dump` of both files unchanged.
  - **Commit** `game.py split T7: the Aasimar rule comments sit above their specs in game_parts/tables.py (D-379)`.
- [ ] **Step 2: D-380(3).** In `test_engine_parts_pilot.py`, the `_salvage_plain_speech` subtest passes the expected text as `raw=after`. Rename the keyword to `after=after`; nothing else changes. §24 row 5 (eşit sıkılık). Run `api.tests.test_engine_parts_pilot` + `NEIGHBOURS` (`p6t2-off/-fon`): `RESULT exit=0`. Plant `after` ≠ the real result (pre-plant rule): red; restore.
  - **Commit** `game.py split T7: the salvage subtest names its expected text after, not raw (D-380 item 3)`.
- [ ] **Step 3: D-351 open item (`import game` unused in `text_rules_a.py`).** Measure: `grep -c "game\." game_parts/text_rules_a.py` (draft: 0). Ruling: it stays — every part starts with `import game` (spec §7 cycle rule; `routing_audit` and the surface test expect the uniform header), it costs nothing at run time, and its ruff F401 line is counted in D-445 — if wrong: a later prefix-removal slice (D-343) deletes it with the others. No code change; the row is closed in Task 6 Step 8 with this Ruling.
- [ ] **Step 4: Dev-only tools (spec §9, decision 5).** Add `VULTURE` (`vulture==2.14` or Task 0's Ruling version) to `requirements-dev.txt`. Nothing installs it in CI. **Commit** `game.py split T7: vulture pinned as a dev-only report tool (spec section 9)`.
- [ ] **Step 5: P5T5-11 (flag-on classifier warning in two Plan 5 pins).** In `TurnIdentityNames`, `test_a_local_place_turn_hands_the_game_module_to_arrival` and `test_heard_rumours_gets_the_game_module_from_the_turn` wrap their `_turn` call in `self.assertNoLogs("ai_dnd.api.ollama", level="WARNING")` (the logger of `api/ollama_adapter.py`, which logs "Classifier unavailable; turn goes on"). Every existing assertion stays.
  - Red: `p6t2-p5t5-11-red-fon` (gate_boot first), `api.tests.test_engine_parts_pilot` + `NEIGHBOURS`: both tests fail on that warning. Run `p6t2-p5t5-11-red-off` too and record the result (Plan 5 saw the warning in flag-on runs only).
  - Fix: both tests answer the classifier call with a test-local client in `test_engine_parts_pilot.py` that returns a valid classifier reading and hands every other call to the client the test uses today. The borrowed helpers (`campaign_api.CampaignApiTests`, `test_heard_rumours_turn`'s `_Client`) are not edited (P5T5-6).
  - Ruling if answering the classifier changes what the pin asserts (arrival not called, another `record_mention` count): keep today's client and replace `assertNoLogs` with `assertLogs` on the same logger plus the exact warning count measured on `P6BASE` per flag (the park's second form) — equal strictness, the test still states what happens — if wrong: the pin keeps a known warning, now counted.
  - Green: `p6t2-p5t5-11-off/-fon`, `RESULT exit=0`. §24 row 10. **Commit** `game.py split T7: two turn identity pins answer the classifier and assert no warning (park P5T5-11)`.
- [ ] **Step 6: P5T5-2 (proof only, no commit).** Pre-plant rule on `move_block.py`: drop the `name in IDENTITY_ROW_NAMES` condition from `_Scan.allowed()` (a row then lets any name through); run `api.tests.test_engine_move_tool` + `NEIGHBOURS` (`p6t2-p5t5-2-plant-off`): the `globals` and `vars` subtests of `IdentityAllowlistTests.test_move_block_still_refuses_dunder_name_even_with_a_row` are red; restore, `sha256sum -c` OK, `git diff HEAD --stat` unchanged. Ledger the run. If either subtest stays green: Ruling, park for Task 6 Step 8 (debt row, owner the next plan that runs `move_block`).

### Task 3: Permanent rules and docs (spec T7.3, decision 8)

**Review tier:** normal (Opus implementer, Opus review). Docs only; the review checks every rule text against the spec.

**Files:** Modify `CLAUDE.md`, `docs/agents/implementer-preamble.md`, `docs/design/INDEX.md`, `docs/agents/onay-listesi-20261115.md` §24 (row 7); create `GLOSSARY.md`, `docs/adr/0001-game-parts-merkez-kurali.md`. Both new files follow `docs/agents/domain.md` (single context: root `GLOSSARY.md`, `docs/adr/0001-*.md`) and the `mattpocock-skills:domain-modeling` skill's term and ADR format, so later skills can read them.

- [ ] **Step 1: CLAUDE.md** (decision 8, approved 2026-11-17). Add under "Kodlama ilkeleri", word for word from spec §11: "game.py'ye yeni işlev eklenmez; yeni kod ilgili `game_parts` modülüne ya da kendi modülüne girer. `game_parts` içinde motor adları `game.X` diye çağrılır. Boyut bütçesi yalnız Kadir'in onayıyla yükseltilir." Nothing else in `CLAUDE.md` changes.
- [ ] **Step 2: `implementer-preamble.md`.** New checklist item `(i)` with the same three sentences, plus: "Yeni bir parça ya da `game.py`'de iki boş satırdan uzun boşluk `test_engine_layout` ve `test_engine_size_budget` tarafından reddedilir."
- [ ] **Step 3: `GLOSSARY.md`** (new; Turkish, one line each): `game_parts`, merkez kuralı (`game.X`), yeniden dışa vurum, yama yüzeyi, boyut bütçesi (mandal, `slack` 50, `part_max` 2 500, dondurulmuş dosya), hassas liste, N1-N8 (one line each, which stay permanent and which are retired; the N2 and N8 lines carry the live duty of Step 4).
- [ ] **Step 4: ADR `docs/adr/0001-game-parts-merkez-kurali.md`** (new; Turkish; Context / Decision / Consequences): `game.py` split into `game_parts/` with the centre rule; never-moved names (spec §5); the one held name, `_narrate_resolved_turn` (not a never-moved name: Ruling N, N3 rule 4, moves in the turn-split slice); the size latch and karar 10; N1, N2, N3, the size and layout tests stay in CI; **N4 (`ledger_diff.py`), N5 (`move_check.py`, `move_block.py`), N7 (`coverage_by_function.py`) and N8 (`sensitivity.py`) are retired as required gate steps** (spec §11) — their scripts and their tests stay in the repo and in CI unchanged; what retired means: no future task must run the N4, N5, N7 tools, a future split may. **Live duties that stay** (stated in the ADR and the GLOSSARY):
  - N8: `test_engine_sensitivity.test_every_flagged_function_in_every_engine_file_is_in_the_lock_or_removed` checks the live engine in CI, and `sensitivity.py --write` refuses once `game_parts/` exists. So a new money or save function turns CI red until it gets a hand-written `sensitive.json` row, under strong review and with an approval-list row.
  - N2 (`patch_census`) is permanent and live: a new patch target changes its lock the same way.
  §24 row 7 ("gevşetme olabilir (spec §11 emeklilik; testler yerinde)").
- [ ] **Step 5: `docs/design/INDEX.md`** (spec T7.3): the Plan 6 line drops "TASLAĞI" and links the ADR, `GLOSSARY.md` and `docs/engine-split/olu-kod-kaniti.md` (Task 5 writes it; the link is added now); the spec's line is marked "kapandı (oynayış bekliyor)".
- [ ] **Step 6:** `git diff --stat` shows only the six files. **Commit** `game.py split T7.3: CLAUDE.md rule, preamble item, glossary, ADR 0001 and INDEX (decision 8)`.

### Task 4: N4/N7 bases on `P6BASE`

**Review tier:** none (Opus runner; nothing committed). Worktree `p6b`.

- [ ] **Step 1:** `git -C ../AI-DND-k2-bolme-p6b rev-parse HEAD` = `P6BASE` (Review Focus 5). Ruling: bases on `P6BASE` itself, not on a merged stage tip as Plan 5 did — Plan 6 has one stage and its only engine change is whitespace and one comment, so `P6BASE` is the tree the gate must equal — if wrong: none; N4/N7 compare by test id and by name.
- [ ] **Step 2: Four suites, one at a time** (Plan 5 Task 13 Step 3 routine: gate wait, foreign-load check, empty `pgrep -af slot_gate`, detached start with the Ruling E form and its start check), `WT` = `AI-DND-k2-bolme-p6b`: `p6g0-off-n4-n7-b`, `p6g0-off-n4-n7-c`, `p6g0-fon-n4-n7-b`, `p6g0-fon-n4-n7-c`. At most two suites per agent (CONTINUE between). Each: `PAR_EXIT=0`, `failing_ids 0`, wall clock and longest shard in the ledger.
- [ ] **Step 3:** `ledger_diff.py --collect` and `coverage_by_function.py --collect --engine-root <P6BASE archive>/ai-dnd` per suite (Plan 5 Task 13 Step 5 commands); the noise sets per flag in the ledger. Keep every run directory's `engine-probe/lines-*.json` path list for Task 5.

### Task 5: Dead-code evidence for Kadir (spec §10, T7.2)

**Review tier:** normal (Opus implementer, Opus review). Nothing is deleted (owner stop).

**Files:** Create `docs/engine-split/olu-kod-kaniti.md`; modify `docs/agents/onay-listesi-20261115.md` §24 (row 8). The evidence script is a ledger file (`run-p6t5-dead.sh` + `dead_code.py`), not committed.

**Candidate set:** the spec's five names, plus every top-level function or class in `game.py` or a part that the condition-1 scan finds (`-measure/p6_measure.py` `dead_name_scan`, run on the `P6BASE` archive). Draft: 5 names, 44 lines.

- [ ] **Step 1: Condition 1 — no mention outside the definition.** Word scan over the whole `P6BASE` archive (ai-dnd, artifacts, lib, scripts, tools, JSON, docs). Excluded as bookkeeping (Ruling, §24 row 8 "gevşetme olabilir (spec §10 koşul 1 yorumlanıyor)"): the definition line, `game.py`'s re-export line, `api/tests/engine_split_locks/*`, `scripts/engine_split/batches/*`, `docs/superpowers/`, `docs/engine-split/`, `docs/agents/debt-register.md`, `docs/agents/onay-listesi-*`, `.superpowers/`, `graphify-out/` — they list every name because of the split, not because they use it. Mentions in the split's own pin tests (`test_engine_parts_pilot`, `test_engine_surface`) are reported in their own column "yalnız bölme sabitleme testi", never hidden. Every other mention is listed with `path:line`. `dead_code.py` prints `SKIPPED <n>` and each path it could not read (not UTF-8, OS error); each skipped file is ruled (can it hold a mention?), never dropped silently.
- [ ] **Step 2: Condition 2 — no body line ran, flag off and on.** For each candidate, its body = first body statement line to `end_lineno` in the `P6BASE` archive. Read the raw `engine-probe/lines-*.json` of Task 4's four suites: holds when no executed line of that file falls in the body in any of the four. Ruling: raw lines, not the per-name N7 count — the count includes the `def` line that may run at import, so "0 lines" is not the test — if wrong: none; raw lines are what the count is made of.
  - A candidate called only by a split pin test fails condition 2 because of that test. The table says so in plain words.
- [ ] **Step 3: Condition 3 — no dynamic reach.** List every `getattr(<game or an engine alias>, <non-literal>)`, `setattr` with a non-literal name, and `session.__getattr__`-style forwarding site in the archive (`graphify query "getattr game dynamic engine name dispatch"`, then a scan). For each, write which names it can reach (prefix, table) and whether a candidate can match. Literal `getattr(game, "<name>")` and `session.<name>` are already counted by Step 1.
- [ ] **Step 4: Condition 4 — vulture agrees.** `uvx --from <VULTURE> vulture <archive>/ai-dnd --min-confidence 0 > <ledger>/p6t5-vulture.out` (WSL; a report only; Task 0's pinned version). Exit code 3 means "unused code found" and is not a failure; any other non-zero exit is. Holds when vulture lists the candidate as unused. Raw output kept in the ledger dir; the table quotes only the candidate lines.
- [ ] **Step 5: The table** `docs/engine-split/olu-kod-kaniti.md` (Turkish, plain; spec §10 columns): ad, dosya, satır (at `P6BASE`), "ne yapıyordu" (one sentence from reading the function), kanıt (conditions 1-4 each ✓/✗ with the evidence path), son dokunan commit (`git log -1 --format='%h %ad %s' <TM0BASE> -L '/^def <ad>(/,+<n>:ai-dnd/game.py'`: the last change before the split), silinecek testler (every test, by module and name, that would be deleted with the name; "yok" if none), öneri ("sil" only when all four hold; "sil (yalnız sabitleme testiyle birlikte)" for a name called only by a split pin test; otherwise "kalsın" with the reason). Kadir's "evet" covers the name and exactly the tests listed in its row. Header lines: "Hiçbir şey Kadir'in 'evet'i olmadan silinmez (spec §10). Silme ayrı küçük bir PR'dır." and the honest expectation from spec §10 (gain is tens of lines).
- [ ] **Step 6:** `kadir-notes.md`: "Ölü kod tablosu hazır: <n> aday, <m> tanesi dört koşulu da tutuyor (<satır> satır). Her satır için 'evet/hayır' bekleniyor; cevap gelmeden hiçbir şey silinmez." **Commit** `game.py split T7.2: dead-code evidence table for Kadir (nothing deleted; spec section 10)`.

### Task 6: Closing gate (spec T7.4), PR

**Review tier:** strong (whole-branch review on Opus).

- [ ] **Step 1:** `git fetch origin`. If `origin/main` moved: merge it (`MAIN_SHA`); if `game.py` or a part changed, rerun Task 1 Steps 3-5 (`blank_runs.py --check` must stay clean) and take fresh bases (Task 4) on `MAIN_SHA`.
- [ ] **Step 2: Split-wide recheck (T7.4 "move_check taze main'e karşı yeniden").** Ledger scripts, no commit:
  - **M7 for every batch**, from Task 0 Step 6's batch → commit map. For each row: `git archive <commit>^ ai-dnd/game.py ai-dnd/game_parts` and `git archive <commit> ai-dnd/game.py ai-dnd/game_parts` (only what the tool reads), then `move_check.py --base-root <parent archive>/ai-dnd --root <commit archive>/ai-dnd --moved-file <p6n>/ai-dnd/scripts/engine_split/batches/<B>.txt --part <part>.py --tier strong`, plus `--manual` with the map's `_PART_MODULES` pair only on rows where the map says `pair` (the line text differs between `<commit>^` and `<commit>`); never on a `none` row. Ruling: `--tier strong` for every batch — purity is the same check at both tiers, tier was checked at move time, and a Plan 2-3 name added to today's `sensitive.json` later would false-stop `--tier normal` — if wrong: none, strong is the stricter tier. Pass: `CHANGED 0` for every batch. Table batch / commit / result in the ledger. Plan 1's pilot names have no batch file: covered by N1 and N3 and by the whole-split check below (Ruling).
  - **Merge commits.** List merges with no pathspec, `git log --merges --format=%H TM0BASE..HEAD` (a path-limited `git log` simplifies history and drops a merge whose result equals one parent on those paths: exactly a "take ours" resolution that drops `main`'s change to a moved block; the re-review measured 1 listed with the pathspec, 15 without). For each: `git show --remerge-diff --format= <m> -- ai-dnd/game.py ai-dnd/game_parts` prints nothing. Any output: STOP, debt row, and the output goes to Step 3 item 3. A correctly resolved conflict also prints output; only the Step 3 reviewer's written verdict lifts that STOP, never the executor.
  - **Whole split against the fresh main** (spec T7.4 literal): one `move_check.py --base-root <TM0BASE archive>/ai-dnd --root <HEAD archive>/ai-dnd --moved "$(paste -sd, <ledger>/p6-all-moved.txt)" --tier strong`, where the file lists `name=part.py`, one per line, from every batch file plus the pilot names (batch files hold bare names; the part comes from the batch-to-commit map built in Task 0: the part file that commit created or grew) (`--moved-file` takes a single `--part`, so it does not fit here). It is a detached long run (Ruling E form; the re-review measured more than 25 minutes uncached for 568 names: `move_check` re-parses `game.py` about three times per name), under WSL Python (UTF-8): Windows Python crashed printing an emoji finding (cp1254, D-358). Expected: findings in about 30 hunks (re-review: `CHANGED 163 names=568` on a mid-Plan-4 tree), including T1.1 helpers and `__init__.py`. Explain them mechanically:
    - group the findings into hunks: one name; one contiguous cluster of `game.py` base lines; one new-side group; `__init__.py`; the comment count;
    - trace a name hunk with `git log --format=%h TM0BASE..HEAD -L '/^def <name>(/,+1:<file>'` (`<file>` = the part file that holds the name at HEAD, e.g. `ai-dnd/game_parts/text_rules_b.py`; `ai-dnd/game.py` gives `fatal: -L parameter ... No match` for a moved name) or `git log --format=%h TM0BASE..HEAD -S "<a changed token>" -- ai-dnd/game.py ai-dnd/game_parts`; a new-side `game.py` hunk with `git blame HEAD -L <a>,<b> -- ai-dnd/game.py`; a base-side hunk with `git blame --reverse TM0BASE..HEAD -L <a>,<b> -- ai-dnd/game.py` (it names the last commit that held the line; the deleting commit is the next commit on `ai-dnd/game.py` after it);
    - a hunk is explained when a traced commit is a non-M11 row of the comment-ledger table below (or a recorded identity or logger edit commit) and that commit's diff shows the change; the comment count difference must equal that table's sum. Table hunk / commit / subject in the ledger;
    - a hunk whose only traced commit is an M11 move commit (the map's commits), or that traces to no commit: STOP.
  - **Comment ledger.** For every non-merge commit in `git log TM0BASE..HEAD -- ai-dnd/game.py ai-dnd/game_parts`: `move_check.py --comments-only` between its parent and itself. Pass: every M11 move commit (the map's commits) has delta 0; every other commit, `game.py split` or not, is listed with its delta, subject and the approval-list row or debt row that approved it. The sum equals `COMMENTS` at `TM0BASE` → now.
  - Any `CHANGED` above 0 in a batch, any move commit with a comment delta, or any non-move commit with a delta and no approving row: STOP (a pure move is not pure), debt row, tell Kadir.
- [ ] **Step 3: Whole-branch review before the suites** (strong, Opus). The reviewer reads in full:
  1. the Plan 6 diff, line by line;
  2. every non-move engine commit since `TM0BASE` (the comment-ledger table's non-M11 rows): at least T1.1 `c745b89f`, T2.1 `42fbbe0d`, T2.2 (`engine_hash`), Plan 4's `77e03670` (alias properties), the logger edit, Plan 5's identity edits, D-429, the FB/G11 lane commits;
  3. every remerge-diff from Step 2;
  4. `git diff TM0BASE..HEAD` of the six lock files (`surface`, `patch_census`, `sensitive`, `identity_allowlist`, `allowed_imports`, `size_budget`), each change mapped to its approval-list row;
  5. every "gevşetme olabilir" row in approval sections §18-§24;
  6. the final `game.py` after Task 1 (about 1 400 lines; `GameSession`, `_narrate_resolved_turn`, the wrapper and the binding code), read in two halves (the 1 000-line rule).
  Plus Step 2's tables; `routing_audit.py` `clean`; D-472 (`sys.modules["game"]` vs the spec's literal `game`): the reviewer confirms or rejects Plan 5's Ruling J and the row is closed or kept with that verdict.
  Independent second method, not based on `move_check`: for 3 move commits chosen at random (one each from Plans 3, 4 and 5; the seed in the ledger), `git show --color-moved=plain --color-moved-ws=no <c>` shows no uncoloured `+`/`-` line except re-export, header and `_PART_MODULES` lines.
  One fix wave, red-first (Opus); scoped re-review (Opus). Ruling: the review reads the list above, not the ~25 000 moved lines again — move purity is machine-proven (Step 2) and spot-checked by the second method, and every move had its own review and stage gate — if wrong: a missed defect surfaces in Kadir's play or later. From Step 4 on, only the ledger, debt rows, PR text and Task 5's table text may change; any code, test or lock change reruns Steps 4-7, and any engine-file change also reruns Step 2.
- [ ] **Step 4: Gate suites** on `p6n`: `p6tc-off-n4-n7`, then `p6tc-fon-n4-n7` (Ruling E form). Pass: `PAR_EXIT=0`, `failing_ids 0`. An unseeded red follows Plan 3's 40-fixed-town-seed procedure; any other red stops the plan.
- [ ] **Step 5: N4 and N7 per flag.** `ledger_diff.py --diff --base <b> --base2 <c> --new <gate>`: `DROPS 0`, `LOST 0`, `SUBLOST 0`, `SUBGONE 0`, `SUBCRASH 0`. `coverage_by_function.py --diff`: `DOWN 0` outside the noise set; every `UP` explained. Any drop stops the plan.
- [ ] **Step 6: Speed (Rulings B, C).** Suites by wall clock against the Ruling C limits. Cumulative A/B `p6t6cum`, OLD `p6o`, NEW `p6n`: ≤ 1.10, above it STOP. One flag-on reading `p6tcbench-fon`, recorded only. Every number with its load line. D-448 closed with these numbers or carried with them.
- [ ] **Step 7: Checks without a suite.** `outside_probe.py` → `PROBE ok parts=` listing every part (D-341); `test_regression.py` 30/30 (D-342); `classify_all.py` → `not_in_lock=0`; ruff once (`uvx --from ruff==0.17.5 ruff check --select F821,F401,F811 --no-fix game.py game_parts`, count into D-445); both import orders with the `start_local.ps1` interpreter rc 0; sizes: `game.py` = `size_budget.json` < 1 500, every part ≤ 2 500 or at its frozen entry; `blank_runs.py --check` clean. Zero-tolerance journeys: `NEIGHBOURS` alone in both flags (`p6tc-journeys-off/-fon`), journey count pasted.
- [ ] **Step 8: Debt rows** (tables "Debt rows" and "Plan 5 parks" below; every park from Tasks 0-7 gets a row with an owner).
- [ ] **Step 9:** Recheck free ids. Push, open the PR (text: the size path, Step 2's tables, N4/N7, speed, the dead-code table link and "nothing deleted"; it never says "done" or "bitti": the split counts as done only after Kadir's play), ancestor check, merge, CI rules. `graphify update .` in the main repo folder (local only; `graphify-out` is gitignored).
- [ ] **Step 10:** Open `bash`/`sleep` processes and slot runs checked. Ledger lines "kapanış kapısı geçti", "oynayış bekliyor". Worktrees are not deleted.

### Task 7: Kadir's closing play and owner decisions (owner stop)

**Review tier:** none (controller). Ruling D ends here.

- [ ] **Step 1: Five-line Turkish summary** (CLAUDE.md "Sabah özeti"): ne değişti ("taşıma ve kapanış kapısı tamam, main'de; bölme oynayışından sonra bitti sayılır", `game.py` <n> satır, <k> parça), neden, hangi dosyalar, ne doğrulandı (paketler, N4/N7, hız oranı, CI), Kadir'den ne bekleniyor.
- [ ] **Step 2: The ask, in `kadir-notes.md` and relayed by the controller, plain Turkish:**
  1. En az 10 dakika oyna (`main`, yeni kampanya). Gördüğün tuhaflığı yaz.
  2. Ölü kod tablosu (`docs/engine-split/olu-kod-kaniti.md`): her satır için "evet sil" ya da "kalsın".
  3. `game.` önekini kaldırmak (D-343): öneri "şimdilik hayır, ayrı karar".
  4. `legacy_debug/` altındaki 25 eski betik (D-339): öneri "bilinerek bırakılsın"; silmek senin kararın.
  5. Sonraki dilim: tur işlevini parçalamak (spec §12, D-470). `game.py`'de kalan tur anlatım işlevi `_narrate_resolved_turn` (351 satır) da o dilimde taşınır (Ruling N). Bu dilim "oynayış yapıldı" satırından önce başlamaz (CLAUDE.md oynayış kapısı).
- [ ] **Step 3: Wait for the play.** Nothing in this step is a Ruling. When Kadir reports the play: ledger "oynayış yapıldı (Kadir <tarih>, <dakika> dk)". A defect he finds that traces to the split gets a red-first fix task (strong) and a new play; any other defect gets a debt row. Then "Plan 6 bitti; bölme bitti". The `docs/design/INDEX.md` spec line "kapandı (oynayış bekliyor)" becomes "kapandı" in Task 8's first commit or, if Task 8 does not run, in the next slice's first commit; the ledger records which. Ruling: no PR for one line — if wrong: INDEX shows "oynayış bekliyor" a little longer.

### Task 8 (conditional, after Plan 6): delete the rows Kadir approved

Runs only for rows Kadir answered "evet" in chat (quoted in the ledger), and not before the ledger line "oynayış yapıldı" (otherwise the closing play tested another tree and a new play is needed). Its own branch `task/game-py-bolme-olu-kod` from `origin/main`, its own PR (spec §10).

**Outside the autonomy grant** (Plans 3-6 only): its push, its PR and its merge each need Kadir's fresh approval in chat, asked one at a time with what will be pushed or merged. No Ruling replaces that approval.

**Review tier:** strong (Opus implementer, Opus review).

- [ ] **Step 1:** For each approved name: red-first proof that nothing reaches it (patch census: no target; `surface.json` row; pin tests that call it). Only the tests listed in that name's "silinecek testler" cell of `olu-kod-kaniti.md` are deleted with it; a test not listed there is not deleted (it goes back to Kadir as a new question). Each deleted test and the `surface.json`/`sensitive.json` change gets a new approval section row marked "gevşetme olabilir (Kadir onayıyla silindi)".
- [ ] **Step 2:** Delete the definition and its re-export name; `surface.py --write` only for those names (N1 fark kuralı); `size_budget.json` lowered if a file shrank by more than 50 lines. `ENGINE_SET` + the modules that named it + `NEIGHBOURS` in both flags; one full suite per flag. **Commit** `Dead code removed on Kadir's yes: <names> (spec section 10)`.
- [ ] **Step 3:** Ask Kadir in chat before the push, before opening the PR and before the merge (three asks). After the merge, the CI rules of Global Constraints apply.

---

## Approval list §24 rows (the executor adds them with the task that makes the change)

| # | Test or rule | Change | Mark | Written in |
|---|---|---|---|---|
| 1 | Speed rule | cumulative A/B against `TM0BASE` at the closing gate, ≤ 1.10 | sıkılaştırma, gevşetme değil | Task 0 |
| 2 | Spec §2 non-goal "biçim düzeltme" | top-level blank lines beyond two deleted from `game.py` (D-379, D-473, Plan 5 I5) | gevşetme olabilir (spec §2 hedef olmayanı yorumlanıyor) | Task 1 |
| 3 | `test_no_engine_file_has_more_than_two_blank_lines_in_a_row_at_top_level` | new permanent guard over every engine file | iddia eklendi (sıkılaştırma) | Task 1 |
| 4 | `size_budget.json` `game.py`; `test_game_py_is_within_the_spec_cap` | budget lowered to the real size; the spec cap becomes a test (`< 1500`, spec §2 "altına") | sıkılaştırma | Task 1 |
| 5 | `test_engine_parts_pilot` salvage subtest | keyword `raw` → `after` (D-380 item 3) | eşit sıkılık | Task 2 |
| 6 | Shard timeout 4 500 s, wall clock | carried from Plans 3-5 (D-448) | taşındı | Task 0 |
| 7 | N4, N5, N7, N8 | retired as required gate steps (spec §11); scripts and tests stay in CI unchanged | gevşetme olabilir (spec §11 emeklilik; testler yerinde) | Task 3 |
| 8 | Dead-code condition 1 | the split's bookkeeping files do not count as uses; split pin tests reported in their own column | gevşetme olabilir (spec §10 koşul 1 yorumlanıyor) | Task 5 |
| 9 | Spec §5 "`game.py` (kalır)" list | `_narrate_resolved_turn` stays in `game.py` (Ruling N; held by N3 rule 4 in Plan 5); the size goal still holds | gevşetme olabilir (spec §5 hedef yapısından sapma; boyut hedefi tutuyor) | Task 1 |
| 10 | `TurnIdentityNames` arrival and heard-rumours pins | no WARNING from `ai_dnd.api.ollama` during the turn, or its exact count (P5T5-11) | sıkılaştırma | Task 2 |

## Debt rows this plan owns and what happens to each

| Row | Handling |
|---|---|
| D-379 blank runs; K01/K02 comments | Task 1 (blank lines) and Task 2 Step 1 (comments); closed in Task 6 Step 8 with the numbers |
| D-473 `game.py` ≤ 1 500 not reachable by moving (Plan 5) | Task 1; closed with the before/after sizes, or kept open with the number if Task 0 Step 3 found the path does not hold |
| D-351 `import game` unused in `text_rules_a.py` | Task 2 Step 3 Ruling (stays); closed |
| D-380 item 3 subtest keyword | Task 2 Step 2; item closed, row closed if no item is left open |
| D-343 `game.` prefix | not done (spec §4: separate, optional); Task 7 asks Kadir; trigger → "Kadir'in kararı (Plan 6 Görev 7)" |
| D-339 `legacy_debug` exec scripts | Task 7 asks Kadir; Ruling until he answers: "bölmeden sonra çalışmadıkları bilinerek bırakılır" (the row's own trigger), row stays open for his answer |
| D-470 `turn.py` frozen at arrival (Plan 5; 3 667 lines in the rehearsal, not the about 4 020 the row's text expects) | carried with the real size; owner: the turn-split slice (spec §12) |
| D-471 `_restore_in_place`, `_dynamic_engine_transitions` stay (Plan 5) | closed: permanent, spec §5 "Geri Al anlık görüntüsü dokunulmadan kalır" |
| D-472 `sys.modules["game"]` (Plan 5) | Task 6 Step 3 review verdict; closed or kept with it |
| D-341, D-342 probes | Task 6 Step 7; carried (they close only with an automated test) |
| D-445 ruff count | Task 6 Step 7 count; trigger → D-343's decision (the F401s are re-export lines) |
| D-448 load-sensitive speed | Task 6 Step 6; closed or carried with the numbers |
| Rows with a Plan 6/T7 trigger found in Task 0 Step 7 | handled in the task they name |

New rows (ids from `D-490`, written in Task 6 Step 8): `D-490` dead-code table waits for Kadir's answer per row (owner Kadir, trigger "Kadir'in cevabı; Görev 8"); `D-491` and `D-492` from "Plan 5 parks" only when Plan 5 wrote no row for them (Task 0 Step 7); further rows only for parks.

Carried unchanged: D-344, D-345, D-346, D-356-D-358, D-362, D-363, D-365, D-436.

### Plan 5 parks

Plan 5's Task 13 Step 8 may write register rows for these parks. Task 0 Step 7 records each row id. Where a row exists, Task 6 Step 8 updates its owner and trigger as below instead of writing a new row.

| Park | What | Handling and owner |
|---|---|---|
| P5T5-8 | No test drives the save writer path `_narrate_resolved_turn` travel branch → `GameSession.evaluate_quest_events` → `_forfeit_unrecordable_xp` | Row with the hold (`D-491` if Plan 5 wrote none): "`_narrate_resolved_turn` held in `game.py` (Ruling N)". Owner: the turn-split slice. Before its move: trace one candidate test or add a base pin (travel turn completing a `visit_location` quest, award refused and forfeited). Plan 6 runs no move, and its only `game.py` edit (Task 1) is checked by `verify` and `ast.dump` |
| P5T4-1 | Parts have no `from __future__ import annotations`; moved annotations are evaluated at def time (root of the hold) | Same row as P5T5-8. Owner: the turn-split slice decides, red first and under strong review: quote the annotation in `game.py` before the move, or add the import to part headers (a mover and N3 rule change) |
| P5T5-1 | `move_block.py` `main` reads `--identity-allowlist` rows without a shape check: a malformed file gives a traceback, not `REFUSED` exit 2 | Row "move_block hardening" (`D-492` if Plan 5 wrote none). Owner: the next plan that runs `move_block` (first expected: the turn-split slice); fix red first before its first move. Ruling: no fix in Plan 6 — Plan 6 runs no `move_block`, N5 retires as a required step at Plan 6's end (Task 3), and P5T4-1's fix changes the same N3 scan, so one strong-reviewed tool change later instead of two — if wrong: the gaps stay one plan longer; no Plan 6 step can hit them |
| P5T5-3 | `move_block` `_Scan.visit` misses `sys.modules` through an alias, `from sys import modules`, `game.sys.modules` and a bare uncalled `locals` | Same row and owner as P5T5-1 |
| P5T4-3 | `move_block`'s `REFUSED` text on stderr interleaves with the caller's echo through `wsl.exe` (cosmetic; the message is complete) | Same row and owner as P5T5-1: callers write stderr to its own file |
| P5T5-11 | Flag-on `Classifier unavailable` warning in two `TurnIdentityNames` pins | Task 2 Step 5; closed in Task 6 Step 8 |
| P5T5-2 | `globals`/`vars` subtests of `test_move_block_still_refuses_dunder_name_even_with_a_row` never planted red | Task 2 Step 6 (proof only); closed in Task 6 Step 8, or a row if a subtest stayed green |

---

## Self-review

1. **Spec coverage.**
   - T7.1 (budgets to final values; the import rule test stays) → Task 1 (layout, budget, cap test); `test_engine_routing` stays in CI (ADR, Task 3).
   - T7.2 (dead-code report, no deletion) → Task 5; §10's four conditions → Steps 1-4; vulture once → Step 4; deletion only after Kadir → Task 8.
   - T7.3 (CLAUDE.md, preamble, GLOSSARY/ADR, INDEX, debt rows, graphify) → Task 3 (INDEX content in Step 5), Task 0 (INDEX plan line), Task 6 Steps 8-9.
   - T7.4 (move_check again against the fresh main, N4+N7 final, whole-branch review, suites ×2, CI, morning summary) → Task 0 Step 6 (map), Task 6 Step 2 (per batch, merges, whole split), Steps 3-9, Task 7 Step 1.
   - "Kapı: Kadir 10 dk oynar" → Task 7.
   - §11 re-bloat: size latch and cap (Task 1), layout guard (Task 1), CLAUDE.md line (Task 3), N1-N3 kept (ADR).
   - Plan 5 I5 (Ruling and approval row before any blank line goes) → Task 1's Ruling and §24 row 2.
2. **Size path.** Draft: 5 264 at p5m `f1bc2ad1` → 2 509 after `turn-3` → 1 398 after the blank rule (under 1 500 by 102 lines, with `_narrate_resolved_turn` held, Ruling N). Task 0 confirms on `P6BASE`; if it does not hold, Plan 6 lowers what it can and says so (no new moves).
3. **Lessons carried:** 4 500 s shards; WMI foreign-load script; detached start in the escaped `'-lc','\"…\"'` form with a start check; 9-minute polls, 150-minute cap, Status CONTINUE, redo after a kill; cumulative rule against `TM0BASE` ≤ 1.10 as a real stop; both flags everywhere; red-first with the pre-plant rule; approval rows in a new §24; "gevşetme olabilir" marking.
4. **Names.** `blank_runs.find/verify(old, new, keep)`, CLI `--check/--apply`; test names match Review Focus and §24; `VULTURE` set in Task 0 Step 5, used in Tasks 2 and 5; labels `p6t<N>-…`, gate `p6g0-…`/`p6tc-…`; no flag-off label contains `fon`.
5. **Proportion.** 9 tasks (8 plus the conditional one). Strong: 1, 6 (and 8). Normal Opus: 2, 3, 5. Runner: 0, 4. Full suites: 6 (4 bases, 2 gate), one A/B series.
6. **Loosening check.** No Ruling loosens a controller or CLAUDE.md rule. Boundary rows marked "gevşetme olabilir": §24 rows 2, 7, 8, 9. Rows 1, 3, 4, 10 are stricter; row 5 equal.
7. **Plan 5 outcomes (2026-11-22).** `_narrate_resolved_turn` hold → Ruling N, §24 row 9, Task 0 Step 3 check, Task 1 note, Task 3 ADR, Task 6 Step 3 read, Task 7 item 5. Parks P5T5-1, -2, -3, -8, -11, P5T4-1, -3 → "Plan 5 parks", each with an owner.

## Execution

Subagent-driven, strictly in order (0, 1, 2, 3, 4, 5, 6, 7). No overlap: Task 4's suites need quiet slots. The controller holds the ledger, gate waits, labels, the A/B series, push, PR and merge. Implementers get `STORE/common.md` and their task text. Task 8 starts only on Kadir's "evet" and after "oynayış yapıldı"; its push, PR and merge each need his fresh approval in chat.

## Pre-flight review fixes

Review: `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p6/p6-preflight-review.md` (0 critical, 9 important, 16 minor). All fixed as proposed; no finding ruled against.

| Id | What changed |
|---|---|
| I1 | `STORE/common.md`: the only hand edit of `game.py` is Task 2 Step 1's comment move (its own commit), not Task 3's. |
| I2 | Task 1 Step 4: `--apply` gets the absolute `p6n` path; `verify` reads the old text with `git show P6BASE:`; `numstat` in `p6n` must show 0 added, about 1 137 deleted (1 111 after the 2026-11-22 amendment). Global SLOTPY rule says the slot's tree is a copy. |
| I3 | `verify(old, new, keep)` also requires the deleted line set to equal `find(old, keep)`; new test `test_verify_refuses_a_blank_line_removed_inside_a_def`; Review Focus 1 updated. |
| I4 | Task 6 Step 2: remerge-diff check for every merge since `TM0BASE`; one whole-split `move_check` from `TM0BASE` to HEAD, every `CHANGED` name explained by a non-move commit or STOP. |
| I5 | New Task 0 Step 6: batch → commit map (M11 subject primary, `-S "def <name>("` cross-check, both agree), `_PART_MODULES` pair by `grep -n`; Task 6 Step 2 writes the full command, `--tier strong` for all (Ruling), archives only `game.py` and `game_parts`. |
| I6 | Task 7 Step 1 wording "taşıma ve kapanış kapısı tamam ... oynayışından sonra bitti sayılır"; Task 6 Step 9 PR text never says "done"/"bitti". |
| I7 | Task 8 outside the grant: push, PR, merge each with Kadir's fresh approval (Global Constraints, Gates, Task 8, Execution). Task 5 table gets "silinecek testler"; only listed tests are deleted. |
| I8 | Task 6 Step 3: the reviewer's six-item minimum read list plus the `--color-moved` second method on 3 random move commits; Ruling reworded. |
| I9 | Task 3 Step 4: ADR and GLOSSARY state the N8 live duty (hand-written `sensitive.json` row, strong review, approval row) and that N2 is permanent and live. |
| M1 | `uvx --from <pkg>==<ver> <pkg>` everywhere; vulture exit 3 is not a failure; `VULTURE` = Task 0's pinned version in Tasks 2 and 5. |
| M2 | `find` callers split on `"\n"` only; new fixture `test_a_form_feed_inside_a_string_does_not_shift_lines`. |
| M3 | T7.1a commit (tool + fixture tests) moves to Step 2; guards, cap test and budget go in T7.1b. |
| M4 | Task 1 Files: "plus any part Task 0 Step 3 named". |
| M5 | Task 2 Step 1: Ruling (completes T3.1, not a format fix); Ruling (block whole, in order, above `INNER_RADIANCE_SPEC`); subject "the Aasimar rule comments"; K04 note. |
| M6 | Paths for `classify_all.py`, Plan 5's ledger dir, `slot_gate.sh`; arguments of `p6_measure.py`, `remaining.py`, `part_runs.py`. |
| M7 | Task 3 Step 5 updates `docs/design/INDEX.md` (drop "TASLAĞI", links, spec row "kapandı (oynayış bekliyor)"); six files. |
| M8 | Task 3: GLOSSARY and ADR follow `docs/agents/domain.md` and the `domain-modeling` skill's format. |
| M9 | Ruling B and Task 6 Step 6: flag-on reading `p6tcbench-fon`, information only; Review Focus 5 cites Step 5 and states what `ledger_diff` refuses. |
| M10 | Task 5 Step 1: `dead_code.py` prints `SKIPPED <n>` and paths, each ruled. Also `p6_measure.py` (both copies) now prints `SKIPPED` (Ruling: Task 0 and the candidate set use it — if wrong: two extra output lines). |
| M11 | Task 5 table: öneri "sil (yalnız sabitleme testiyle birlikte)"; "satır" at `P6BASE`. |
| M12 | Ruling: cap test asserts `< 1500` (spec §2 strict); Task 0 Step 3, Task 6 Step 7, §24 row 4, Review Focus 4. |
| M13 | Task 1 `kadir-notes.md` gets the new permanent layout-rule line. |
| M14 | Comment ledger: M11 move commits need delta 0; other commits are listed with delta and approving row. |
| M15 | Task 8 not before "oynayış yapıldı". |
| M16 | Task 7 Step 2 item 5: the turn-split slice waits for "oynayış yapıldı". |
| Scan table | Task 6 Step 3: an engine-file change after the review also reruns Step 2. |

Re-review: `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p6/p6-rereview.md` (0 critical, 2 important, 7 minor). All fixed as proposed; no finding ruled against.

| Id | What changed |
|---|---|
| R1 | Task 6 Step 2: merges listed with no pathspec; remerge-diff on each; any output is a STOP that only the Step 3 reviewer's verdict lifts. |
| R2 | Task 0 Step 6 and Task 6 Step 2: the `_PART_MODULES` `--manual` pair only when the line text differs between `<commit>^` and `<commit>`; the map records `pair` or `none`. |
| Whole split | Task 6 Step 2: detached long run (Ruling E), WSL Python, `--moved` built from the batch files plus pilot names (`name=part.py`). |
| m1 | Task 6 Step 2: findings grouped into hunks, traced with `git log -L`/`-S` and `git blame` (`--reverse` for base lines); an M11 commit or no commit: STOP. |
| m2 | Task 1 Step 4: old text written with Git Bash `git -C <p6n> show`, then `verify` through SLOTPY on `/mnt/c/...` paths. |
| m3 | `verify`: greedy forward alignment, matching `find`'s "after `keep`" rule. |
| m4 | `verify`: deleted lines outside every top-level span, computed without `find`; new test `test_verify_refuses_a_line_inside_a_def_even_if_find_returns_it`. |
| m5 | Task 0 Step 6: `--no-merges` on the subject lookup; `-G '^<NAME> ='` for constants, oldest listed commit. |
| m6 | Task 7 Step 3: INDEX "kapandı (oynayış bekliyor)" → "kapandı" in Task 8's or the next slice's first commit (Ruling). |
| m-a | Task 6 Step 2: `-L` names the part file at HEAD. |
| m-b | Task 6 Step 2: the part for `p6-all-moved.txt` comes from the batch-to-commit map. |
| m7 | Fix report: the branch is on origin at 10c6f63b (pushed by the controller); report corrected. |

## Amendment after Plan 5 outcomes (2026-11-22)

Sources: Plan 5 ledger ("Task 4", "Ruling: Plan 5 amendment after Task 4", "Parks from the review minors", "Controller (Task 5 Step 4)", Tasks 6-10), `task-4-report.md`; measurement on a `git archive` copy of p5m `f1bc2ad1` (`-measure/out-p5m-f1bc2ad1/`). Report: `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p6/p6-amend-after-p5.md`.

| What | Changed |
|---|---|
| Status, Ruling M, measured base | Draft numbers re-measured on p5m `f1bc2ad1` with `turn-3` projected: `game.py` 2 509 after Plan 5, 1 398 after the blank rule (was 2 158 and 1 021). `SKIPPED 5`; dead-code draft 2 + 3. |
| Ruling N (new) | `_narrate_resolved_turn` stays in `game.py`; §24 row 9; owner of the move: the turn-split slice. |
| Task 0 | Step 3 checks the hold and rules the skipped paths; Step 6 notes `turn-2.txt` after the hold; Step 7 records Plan 5's row ids for the parks. |
| Task 1 | Numbers 1 111 / 2 509; §24 row 9; one more `kadir-notes.md` line. |
| Task 2 | Step 5 (P5T5-11, red first, §24 row 10, own commit); Step 6 (P5T5-2 plant proof, no commit). |
| Tasks 3, 6, 7 | ADR names the held function; review reads about 1 400 lines; Kadir's item 5 names it. |
| Debt | Ids: Plan 5 D-470..D-489, Plan 6 D-490..D-509; new table "Plan 5 parks" with owners; D-470 real size. |

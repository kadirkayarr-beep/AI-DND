# game.py Split, Plan 4 (T5 combat_flow, coin, savefile and the sensitive leftovers, to spec TM4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** First remove the split's per-turn cost of the Python-level `_GameModule` hook (red-first, behaviour unchanged). Then move the 139 names of spec stage T5 out of `ai-dnd/game.py` (about 7 070 lines). They go into three new parts (`combat_flow`, `coin`, `savefile`) and the existing `schemas`, `character_rules`, `places`, `intent`, `dialogue`, `lore`, `narration` and `living_world_turn`. Every moved name either touches money, death, save or Undo, or sits next to them. Then pass spec gate TM4.

**Architecture:** Unchanged from Plans 1-3. Moved code lives in `ai-dnd/game_parts/` and reaches engine names as `game.X` (centre rule). The mover adds the prefix in place. `game.py` re-exports every moved name with explicit `from game_parts.<part> import ...` lines. Every new part with a re-exported function joins `_PART_MODULES`.

Stage A has three jobs. It first replaces the `_GameModule.__getattribute__`/`__setattr__` hook with class-level properties for the 22 character aliases. Then it closes the net debts that a sensitive move can hit. Then it rehearses the whole move on a throwaway branch with a cumulative speed check. Stage B moves the names, every task under the strong review.

**Tech Stack:** Python stdlib (`ast`, `symtable`, `unittest`, `sys.setprofile`, `cProfile`); guarded WSL runner `slot.sh`; repo gate runner `ai-dnd/scripts/engine_split/slot_gate.sh`; `ruff==0.17.5` through `uvx` (a second opinion only, never `--fix`/`format`).

**Spec:** `docs/superpowers/specs/2026-11-17-game-py-bolme-design.md` (approved 2026-11-17). The spec is the authority: where this plan and the spec differ without a `Ruling` line, the spec wins. Plan 3 (`docs/superpowers/plans/2026-11-19-game-py-bolme-plan-3.md`) holds the Move procedure this plan builds on. Its ledger (`C:/Users/Kadir/Desktop/AI-DND-k2-bolme-t4n/.superpowers/sdd/2026-11-19-game-py-bolme-plan-3/progress.md`) holds the rulings this plan builds on.

**Appendix:** `docs/superpowers/plans/2026-11-20-game-py-bolme-plan-4-appendix.md` holds:
- the measured module map;
- the 15 batches with headers, prefixed names and census targets;
- the risk checks, the `session=` callers and the speed measurements;
- every command.

Scripts and raw outputs are in `docs/superpowers/plans/2026-11-20-game-py-bolme-plan-4-measure/`: the scripts at its top, the outputs in `out/`.

**Scope:**
- spec rows T5.1-T5.5 and gate TM4;
- Plan 3's 15 fix-wave holds;
- D-378's held names;
- every debt row whose trigger names Plan 4, T5 or TM4 (see the table "Debt rows this plan owns").

`turn` names stay for Plan 5. The outline of Plans 5-6 is at the end.

**Gates in this plan:**
- G5a = net gate (Task 6): Stage A reviewed, then PR A.
- TM4 = spec TM4 (Task 17): N4/N7 bases, gate suites, cumulative speed, then PR B, stacked on PR A.

**Measured base (2026-11-20, read-only, `origin/main` `bdeddf2a`, slot 2 Python 3.13.16; appendix B-G):**
- `game.py` has 15 363 lines and 226 top-level names, with 11 parts in `_PART_MODULES`.
- Plan 4 scope: 138 names / 7 069 lines, plus `COIN_LEFT_BEHIND` = 139 / 7 070. Of these, 54 are sensitive and 15 are Plan 3 holds.
- D-355 measurement: `sensitivity.classify` over `game.py` and all parts flags only one name missing from the lock: `game_parts/terminal.py: run ['save']`.
- Hook: 3 050.7 Python-level `_GameModule.__getattribute__` calls per bench turn. A read costs 134.2 ns through the hook and 14.0 ns plain. Estimated cost 0.367 ms per turn (1.3-1.6 % of a turn).
- Indicative cumulative ratio against the TM0 tree, measured outside the guard: about 1.052.

## Global Constraints

- **Precondition and execution base.**
  - `origin/main` must contain `bdeddf2a` (Plan 3, PR #136).
  - `P4BASE` is the `origin/main` commit when Task 0 starts.
  - `TM0BASE` = `2e576967dda2fbfdf6a47d22d9313fbc76c195f8`. This is the PR #128 merge (T0): the last tree without `game_parts`, with `bench_engine_turn.py` byte-equal to today's (appendix G).
- **Autonomy (Kadir 2026-11-20, Plans 3-6).**
  - Every "ask Kadir" or "tell Kadir" becomes a ledger entry plus a line in `kadir-notes.md`, with a `Ruling`. Nothing waits for an answer.
  - The controller pushes, opens PRs and merges under that grant. Workers never push, open PRs, merge, delete branches or force anything.
  - No force push. Never delete a branch.
  - Before a merge, check that the target tip is an ancestor of the merged branch.
  - After every push or merge, run `gh run list --repo kadirkayarr-beep/AI-DND --limit 5`. "AI-DND bounded verification" must be green before "done".
    - A red run is reported at once.
    - Before any rerun, save its `gh run view <id> --log-failed` in the ledger dir. Rerun only the failed job.
  - Real stops stay:
    - a speed limit exceeded (spec §7);
    - an irreversible or destructive action;
    - a security-sensitive action;
    - a plan so broken that every path is a guess.
- **Ruling A (controller): speed first.**
  - Task 1 is the speed task: the `_GameModule` hook cut, red-first, behaviour unchanged, strong review.
  - Ruling (spec §7 deviation, controller I4): spec §7 marks the `__class__` mechanism (`_GameModule`) "Dokunulmaz". The mechanism stays: the class and its name, the swap only when `__name__ != "__main__"`, the `__class__` assignment, and the aliases mirroring the default session. Only its implementation changes: the per-read `__getattribute__`/`__setattr__` hook becomes 22 class properties. Task 1's tests prove the unchanged behaviour (alias read and write through the default session, `__main__` path untouched, N3 green). Approval §22 row 9 records it — the hook costs every `game.X` read a Python call and Plan 4 moves the hottest callers — if wrong: Task 1's pins and Task 16 Fault 7 show it; revert one commit.
  - No move task starts before Task 1 is reviewed and its cumulative check passed.
- **Ruling B (controller): cumulative speed baseline.** Wherever this plan says "cumulative A/B":
  - OLD = the `TM0BASE` tree (worktree `p4o`); NEW = the tree under test.
  - The method is the fair A/B of Plan 3 G4a.
  - It runs at Task 0 (information), at the end of Task 1 (binding), in Task 5 (binding, on the fully moved rehearsal tree) and at TM4 (binding).
  - Above 1.10 at a binding point: STOP and tell Kadir (spec §7 real stop). No retake to pass.
  - Per-task M10b keeps Plan 3's rule: OLD = the unmoved Stage A tip, cumulative over Stage B.
  - Approval list §22 row 1 marks the cumulative rule as stricter, not a loosening.
- **Fair A/B method** (labels `<pfx>bench-warmold-off`, `<pfx>bench-warmnew-off`, `<pfx>bench-old<k>-off`, `<pfx>bench-new<k>-off`, k = 1..5, flag off, no `fon`):
  - Gate wait before every run, `FSLOT` 4.
  - One warm-up each, discarded.
  - Five pairs in the order O,N,N,O,O,N,N,O,O,N.
  - Each run: `slot.sh 4 <WT> test <label> 1800 api.tests.bench_engine_turn`. Read `TURN_BENCH median_ms_per_turn` from `target.log`.
  - Pass: median(NEW five) / median(OLD five) ≤ 1.10.
  - The absolute 23.13 / 23.25 ms limits are information only (Plan 3 G4a Ruling).
  - Every raw `RESULT` and `TURN_BENCH` line goes to the ledger.
  - Per series, record the OLD sha and the NEW tree identity (`git rev-parse HEAD` and `git write-tree` of the staged tree).
  - A single run with `RESULT exit≠0` or no `TURN_BENCH` line is rerun once at the same position; the series is never rerun.
  - After a speed STOP: Stage A net tasks may finish and commit locally; no PR, no push and no move task until Kadir's answer.
- **Ruling C (controller): full suites.**
  - Shard timeout 4 500 s: `slot_gate.sh <FSLOT> <WT> <label> 3 4500 '.'`. This is carried from Plan 3 Task 17 and is already marked in D-448.
  - Suite speed is read as wall clock.
  - The longest-shard ratio is recorded as information (D-448).
  - Limits:
    - flag off ≤ 2 155 s (1.10 × TM0 1 959 s) and ≤ 1.10 × the mean of the two flag-off bases;
    - flag on ≤ 1.10 × the mean of the two flag-on bases.
- **Ruling D (controller): play gate deferred** to the end of Plan 6.
  - TM4 writes "oynayış ertelendi (Kadir 2026-11-20)".
  - The zero-tolerance journeys stand in for the play: `NEIGHBOURS` in every run, plus Task 17 Step 7.
- **Ruling E (controller): waits.**
  - No agent, controller or worker ever uses the Monitor tool or a background wait (`run_in_background` plus a notification).
  - Every wait is a foreground bash loop of at most 9 minutes per tool call and at most 150 minutes per agent.
  - A run that can outlive one call (pattern runs, full suites) is started detached from Windows and polled. The command is `powershell.exe -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath 'C:\Program Files\Git\bin\bash.exe' -ArgumentList '-lc','<command> > <ledger>/<label>.out 2>&1'"`. Foreground loops then poll the `.out` file for its final `PAR_EXIT=`/`RESULT` line.
  - An agent at 150 minutes hands over the label and the `.out` path to the next agent.
  - Task 0 Step 5 proves the detached start on a short pattern run.
  - Ruling: Windows `Start-Process`, not `nohup ... &` in Git Bash — a Git Bash child can die with the tool's shell; a process started by Windows does not — if wrong: the Task 0 smoke run shows it, and the controller picks another detached start before any long run.
- **Ruling F (controller): test and safety.**
  - Tests run only through `slot.sh` / `slot_gate.sh` (`FSLOT` 4 for `slot_gate.sh` and benches, `SLOT` 2 for targeted runs). Slots 3 and 5 belong to others.
  - Gate wait `run-gatewait.sh` before every `slot_gate.sh` call and every bench. Go only on `RC=1`, and for `slot_gate.sh` also `AVAIL_MB` ≥ 3 500.
  - `pgrep -af slot_gate` must print nothing before any `slot_gate.sh`.
  - Never two full suites at once. No browser tests: only Kod-1 runs them on this machine.
  - Debt rows have exactly 8 `|`.
  - Keys and `.env` are never read.
  - No branch deletion, no force push.
- **Foreign load (D-448).** A separate Git Bash script `<ledger dir>/run-foreignload.sh` (Windows side; `run-gatewait.sh` stays a WSL script) runs next to every gate wait and prints:
  - `MSYS_NO_PATHCONV=1 typeperf "\Processor(_Total)\% Processor Time" -sc 5 | awk -F'"' '$4 ~ /^[0-9.]+$/ {s+=$4; n++} END {printf "FOREIGN_CPU_PCT=%.0f\n", n ? s/n : -1}'`;
  - `MSYS_NO_PATHCONV=1 tasklist /FI "IMAGENAME eq node.exe" /NH | grep -c node.exe | sed 's/^/NODE_PROCS=/'`.
  - `FOREIGN_CPU_PCT=-1` means the read failed: fix the script before the series.
  - Before a bench series or a full suite, `FOREIGN_CPU_PCT` must be ≤ 25. Otherwise poll every 5 minutes for at most 35 minutes, then go and write "yük altında" next to the result.
  - Ruling: go after 35 minutes rather than stop — ABBA order spreads steady load over both trees, and a stop under load is still a stop (no retake) — if wrong: a load spike can fake a speed stop; the recorded load line lets Kadir see it.
- **Ruling G: two stages, two PRs.**
  - Stage A (tools, speed, nets, rehearsal) = PR A.
  - Stage B (moves, exam, TM4) = PR B, stacked on PR A. Stage B does not wait for PR A's merge.
  - Why: the speed cut and the net fixes get their own gate review before 15 sensitive batches build on them.
  - If wrong: one rebase of PR B.
- **The flag.** Every targeted run happens twice:
  - flag on: label `<run>-fon`, `api.tests.gate_boot` first and `api.tests.test_engine_gate_boot` in the list;
  - flag off: label `<run>-off`, never containing the letters `fon`.
  - Labels: `p4t<task>-<batch or step>-<off|fon>`. No batch name contains `fon`.
  - Never `slot.sh ... par`.
  - `F_fon` (flag-on reds tolerated by Plan 2's rule) is read again in Task 0.
  - Pass at every gate: `failing_ids 0` in both flags. If `F_fon` is not empty, Plan 3's `F_fon` Ruling applies to exactly those ids.
- **Worktrees** (one writer each; `WT` = folder name only):

  | Worktree | What | Used by |
  |---|---|---|
  | `AI-DND-k2-bolme-p4n` | branch `task/game-py-bolme-p4-nets` off `P4BASE` | Stage A |
  | `AI-DND-k2-bolme-p4m` | branch `task/game-py-bolme-p4-moves`, cut from the Stage A tip after Task 6 | Stage B |
  | `AI-DND-k2-bolme-p4a` | detached at `P4BASE` | Task 0 bench, Task 1 OLD |
  | `AI-DND-k2-bolme-p4o` | detached at `TM0BASE` | cumulative OLD |
  | `AI-DND-k2-bolme-p4p` | local branch `tmp/game-py-bolme-p4-prova` | rehearsal |
  | `AI-DND-k2-bolme-p4x` | local branch `tmp/game-py-bolme-ag-sinavi-p4` | exam |
  | `AI-DND-k2-bolme-p4b` | detached; the Stage A tip merged with the gate's `MAIN_SHA` | TM4 bases |

  - Throwaway branches are never pushed and never deleted.
- **Freeze (spec decision 3):** while PR A or PR B is open, no other branch touches `ai-dnd/game.py` or `ai-dnd/game_parts/`. The D-429 behaviour fix waits (Ruling in Task 0).
- **Run commands.**
  - Targeted run: `bash C:/Users/Kadir/Desktop/AI-DND-TOOLS/slot.sh <SLOT> <WT> test <label> 1800 <modules...> <NEIGHBOURS>`. Pass: `RESULT exit=0 Ran <n> tests`.
  - Pattern run, when a list has more than 60 modules: `bash C:/Users/Kadir/Desktop/<WT>/ai-dnd/scripts/engine_split/slot_gate.sh <FSLOT> <WT> <label> 3 4500 '^(<b1>|<b2>|...)$'`. Pass: `PAR_EXIT=0` and `failing_ids 0`.
    - Use base names only: strip `api.tests.` from every entry and leave out `gate_boot`.
    - Before reading the result, check that the printed `modules=<n>` equals the intended count.
  - `NEIGHBOURS` = `api.tests.test_journey_runner api.tests.test_journey_report api.tests.test_journey_schema api.tests.test_journeys`. They are in every targeted run.
  - `ENGINE_SET` = Plan 3's eight modules plus two (Ruling: stricter; sensitive names now move, so the sensitivity lock and the alias cost test run every time — if wrong: about 5 s more per run):
    - Plan 3's: `api.tests.test_engine_parts_pilot api.tests.test_engine_routing api.tests.test_engine_surface api.tests.test_engine_patch_census api.tests.test_engine_size_budget api.tests.test_engine_hash_parts api.tests.test_engine_sources api.tests.test_engine_split_inventory`;
    - added: `api.tests.test_engine_sensitivity api.tests.test_engine_module_alias` (the second is created in Task 1).
- **`WTROOT`** = `/mnt/c/Users/Kadir/Desktop/AI-DND-k2-bolme-p4n/ai-dnd` in Stage A (Tasks 0-6) and `/mnt/c/Users/Kadir/Desktop/AI-DND-k2-bolme-p4m/ai-dnd` in Stage B (Tasks 7-17). Where a step says "slot copy", it means `/root/aidnd-env-<SLOT>/src/ai-dnd` after a sync.
- **Scripts that are not tests (`SLOTPY`).** After a `slot.sh` call has synced the tree, run them with the slot's Python 3.13 as a script file: `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash <ledger dir>/run-<name>.sh`.
  - Never `bash -c '...'` (D-351).
  - Never Windows Python 3.14 for the mover or the checker (D-358).
- **Stores.**
  - Measurement store: `C:/Users/Kadir/Desktop/AI-DND-TOOLS/measure/engine-split/p4/` (`STORE`).
  - Ledger: `C:/Users/Kadir/Desktop/AI-DND-k2-bolme-p4n/.superpowers/sdd/2026-11-20-game-py-bolme-plan-4/progress.md`. It is local and not committed; Stage B appends to it. `run-*.sh`, `pre-plant/` and `kadir-notes.md` live there too.
  - Seconds, bench readings and `RESULT` lines are copied raw, never estimated.
  - Decisions are written as `Ruling: <karar> — <neden> — <yanlışsa maliyeti>`.
- **Red first.** Every new test is seen failing for the stated reason before the change.
  - A guard that is green on a clean tree is shown red with a planted fault, then restored with Plan 3's pre-plant rule: copy the file and its sha256 to `pre-plant/`; plant; run; copy back; check the sha256 and that `git diff HEAD --stat` is unchanged.
  - New tests that start a campaign or a session use `fixed_town(self, <seed>)`, with seeds `20261301` and up, one per test.
- **Old-behaviour tests** are rewritten only with equal or greater strictness. Each rewrite gets a row in `docs/agents/onay-listesi-20261115.md` §22 (`Test | Değişiklik | İşaret`). A moved boundary is marked "gevşetme olabilir". Unmarked loosening, skipping or deleting stops the work.
- **Findings** go to `docs/agents/debt-register.md`, ids `D-450..D-469`.
  - Ruling: D-449 is skipped; it lay inside Plan 3's block — if wrong: one unused id.
  - Before each push, read the highest id on `origin/main` and on open branches.
- **Review tiers.** Every task has an Opus implementer, or an Opus runner for Tasks 0, 5 and 16. Every committed change gets an independent Opus review on a `git archive <sha>` copy, and the reviewer reruns M7 itself.
  - "strong" = money/save/death/Undo reading, `move_check --tier strong`, and the reviewer runs M12.
  - Task 1, every move task (7-15) and both gates (6, 17) are strong. Tool tasks 2-4 are reviewed by Opus with net scope.
  - The fable model is never used (owner rule 2026-11-14).
- **Speed rule 1 (overlapping review)** applies only in Stage A and only between tasks with disjoint file lists. The controller writes each task's debt rows after its review. Stage B runs strictly one task after another.
- **Tools.** Stdlib only in CI.
  - Forbidden: `ast.unparse`, formatters, `ruff --fix`, `ruff format`, rope, libcst codegen, import-linter, desloppify.
  - Moved source is edited in place only, and never by hand inside a move. Spec T5.3's logger name is changed in `game.py` in its own red-green commit before the save move (Task 9 Step 2), so the move stays pure.
  - `sensitivity.py --write` is never run. `sensitive.json` grows only by hand under a strong review and never shrinks.
- **Centre rule (spec §4).**
  - A part never calls another engine function or class bare. It writes `game.X` (R9).
  - A part constant read by the same part stays bare.
  - No sibling-part imports, no `from game import`. Only `game.py` imports `game_parts.*`.
- **Never moved** (`move_block.NEVER_MOVED`, 18 names): `world_state, messages, RULE_ORDER, GameSession, _session, _bind_session_engine, create_session, _GameModule, _speech_debug_trail, DEFAULT_SAVE_PATH, start_terminal_game, _DEFAULT_SESSION, _ACTIVE_SESSION, _ENGINE_FUNCTIONS, _ENGINE_NAMESPACE, _CHARACTER_GLOBALS, _PART_MODULES, recent_dm_narrations`. Task 1 edits `_GameModule` in place; it stays in `game.py`.
- **Every implementer brief carries:**
  - `docs/agents/implementer-preamble.md`;
  - the graphify rule: run `graphify query "<question>"` before the first grep or source read; read raw files only for lines the graph or an earlier read located; run `graphify update .` once at the end. The graph lives in `C:/Users/Kadir/Desktop/AI - DND/graphify-out` and is stale for line numbers;
  - "a move task changes nothing else";
  - "the prefix is added in place; source is never regenerated";
  - function and file names, never line numbers;
  - "`game.py` is about 15 000 lines: never read it whole";
  - the superpowers skills to load: `test-driven-development`, `verification-before-completion`.

## Move procedure (binding for Tasks 7-15; Plan 3's M1-M12 with these deltas, given to every move brief word for word together with Plan 3's text)

Definitions:
- `B` = batch, `P` = part file.
- `NAMES` = `WTROOT/scripts/engine_split/batches/<B>.txt` (written in Task 4).
- `WTROOT` = the Stage B path (Global Constraints).
- Labels `p4t<N>-<B>-<off|fon>`. `STORE` is Plan 4's.

- **M2 (changed).**
  - Every name in `NAMES` must be:
    - not in `NEVER_MOVED`;
    - still a top-level name of `game.py`;
    - in the batch file's order.
  - Sensitive names move. Batch notes list them, and the count must match `sensitive.json` (appendix D, column S). A mismatch → `Ruling`.
  - Surprises → hold the name and write a `Ruling`. Surprises are: a decorator, a non-constant default that names an engine name, a module-level mutation, a top-level `if`/`try` around the name (D-363), or an identity name (`move_block` itself refuses `__name__`/`__file__`). The two `__name__` reads in `_repair_dilim1_fields`/`_repair_dilim2_fields` are gone before `save-1` (Task 9 Step 2).
- **M3** red membership test: as Plan 3. Plus the task's behaviour tests, which are pinned on `BASE_SHA` before the move.
- **M4, M5, M6** as Plan 3, with these changes:
  - M5 header per appendix D / `out/p4-batches.out`, under Plan 3's M5 Ruling: a multi-name `from X import (...)` keeps its form and lists only the names read, never a census target.
  - M6 `_PART_MODULES` gains `"game_parts.combat_flow"`, `"game_parts.coin"`, `"game_parts.savefile"` in each part's first batch, and the tuple stays sorted.
- **M7:** `move_check.py ... --tier strong` always. Expected `CHANGED 0` with no `--manual` entry other than the `_PART_MODULES` pair, and `COMMENTS base=<C> now=<C>`, with `<C>` measured in Task 0.
- **M8, M9** as Plan 3. M9's `PROBE ok parts=` must list `P`.
- **M10:** module list = `ENGINE_SET` + `SLOTPY inventory.py --touching <NAMES>` (since Task 3 this includes session readers, D-446) + the task's named modules + `NEIGHBOURS`, in both flags.
  - In the flag-on run, `test_the_fon_token_turns_the_flag_on_inside_the_child` reads `ok`.
  - Every money, save, death or Undo test the task names must be unchanged since `BASE_SHA` and green in both flags. The reviewer confirms it.
- **M10b (once per task, after its last batch):** fair A/B, OLD = the Stage A tip (`p4n`, unmoved), NEW = the `p4m` working tree, prefix `p4t<N>`. Above 1.10 → speed stop.
- **M11** commit: one batch, one commit.
- **M12 (changed: a reading list, not a clean count; approval §22 row 8, "gevşetme olabilir").** The reviewer runs `SLOTPY <M3>/writer_scan.py <ARCH> <ARCH>/ai-dnd/scripts/engine_split/batches/<B>.txt`.
  - Pass: `missing=0`; the set of `HELD` names equals `STORE/writer-expected-<B>.txt` (recorded in Task 4) exactly; exit code 1 when that file is non-empty and 0 when it is empty (the script exits 1 on any `HELD`).
  - The reviewer reads every `HELD` path's writer in the moved code and confirms that the test Task 4 recorded for that writer kind (`STORE/writer-tests-<B>.txt`) is named in the task's M10 list and green.
  - A `HELD` name not in the expected file is a new writer reach: hold it, write a `Ruling` and a debt row.

## Review Focus

These are failure modes the spec implies but no listed check exercises. Each is pinned to a test or gate step in the task named.

1. **Turn latency grows with every moved hot caller.** `ask_dungeon_master`, `finalize_narration`, `parse_player_intent`, `execute_intent` and combat run every turn and will read `game.X`. Pinned by:
   - Task 1's `test_reading_an_engine_name_through_the_module_runs_no_python_code`;
   - the cumulative A/B (Tasks 1, 5, 17);
   - M10b in every move task.
2. **A death in combat is undone into the same session.** `_capture_combat_death_checkpoint`/`_restore_combat_death_checkpoint` read `game.GameSession` and `game._session()` from `combat_flow`. Pinned by `test_combat_death_checkpoint_round_trips_from_the_part` (Task 7) and Task 16 Fault 3.
3. **A save written and loaded through `savefile` is the same game, and its repair warnings still log as `game`.** Pinned by `test_save_round_trip_after_the_move`, `test_the_save_repair_warnings_log_under_game` (Task 9) and Task 16 Fault 5.
4. **Moved `session=` helpers bind the given session.** 19 names, 122 outside calls (appendix F), with inputs that only the given session has (D-447). Pinned by `test_<part>_session_helpers_use_the_given_session` (Tasks 7, 9, 10-15) and Task 16 Fault 6.
5. **Production rebinding reaches moved callers.**
   - The narrative adapter (`api/main.py` → `install_narrative_context_adapter`) rebinds `build_world_context`, `ask_dungeon_master`, `finalize_narration`.
   - `trace_ai_pipeline.py` rebinds `execute_intent`.
   - Pinned by `test_the_identity_check_sees_through_the_narrative_adapter` (Task 4), `test_the_narrative_adapter_reaches_the_moved_ask` (Task 14), `test_a_rebound_execute_intent_reaches_its_moved_caller` (Task 12) and Task 16 Fault 4.

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `ai-dnd/game.py` (`_GameModule` only) | the alias hook becomes class-level properties | 1 |
| `ai-dnd/api/tests/test_engine_module_alias.py` (new) | alias cost and behaviour pins | 1 |
| `ai-dnd/api/tests/test_engine_sensitivity.py`, `engine_split_locks/sensitive.json` | D-355: classify every engine file; `run` joins the lock | 2 |
| `ai-dnd/scripts/engine_split/routing_audit.py`, `api/tests/test_engine_routing.py` | D-440: R11 sees a module that re-exports a builtin | 2 |
| `ai-dnd/scripts/engine_split/inventory.py`, `api/tests/test_engine_split_inventory.py` | D-446: `touching_tests` counts session readers | 3 |
| `ai-dnd/api/tests/test_engine_parts_pilot.py` (Plan 3 session tests) | D-447: inputs that only the given session has | 3 |
| `ai-dnd/scripts/engine_split/batches/*.txt` (15 new) | batch lists (appendix D) | 4 |
| `ai-dnd/api/tests/test_engine_surface.py` | `test_t5_batches_are_movable`; identity check sees through the narrative adapter (D-349) | 4 |
| `ai-dnd/game_parts/combat_flow.py` (new) | batches `combat-1/2/3` | 7 |
| `ai-dnd/game_parts/coin.py` (new) | batch `coin` | 8 |
| `ai-dnd/game_parts/savefile.py` (new) | batches `save-1`, `save-2` | 9 |
| `game_parts/schemas.py`, `character_rules.py`, `lore.py` | batches `schemas`, `cr-s`, `lore-s` | 10 |
| `game_parts/places.py`, `intent.py`, `dialogue.py`, `narration.py`, `living_world_turn.py` | `places-s`, `intent-s`, `dialogue-s`, `narration-s-1/2`, `lwt-s` | 11-15 |
| `ai-dnd/api/tests/test_engine_parts_pilot.py` | membership, behaviour, session and rebinding tests of every move | 7-15 |

Batches come from measurement (appendix A, D): the region map, the misfit rule and CAP 1 000.
- One task per part. A task's batches are steps, each with its own M1-M11 cycle and commit, with one strong review per task.
- Ruling: `schemas`, `cr-s` and `lore-s` (1 name each, 128 lines in total) share Task 10 — three tiny, same-shaped moves into existing parts; speed rule 5 — if wrong: one review reads three commits.

---

# Stage A — speed, nets and rehearsal (worktree `AI-DND-k2-bolme-p4n`, PR A)

Only Task 1 changes `ai-dnd/game.py`, and only in `_GameModule`.

### Task 0: Open the stage

**Review tier:** none (Opus runner). Its commit is read by the G5a review.

- [ ] **Step 1: Precondition.**
  - `git fetch origin`; `git merge-base --is-ancestor bdeddf2a origin/main`. `P4BASE` = `origin/main`; write its sha.
  - If `git diff bdeddf2a P4BASE -- ai-dnd/game.py ai-dnd/game_parts` is not empty, Task 4 Step 2 re-measures everything and measurement wins.
  - Read Plan 3's ledger end lines ("TM3 geçti", the `F_fon` state). Write `STORE/F_fon.txt` (empty if none).
- [ ] **Step 2: Worktrees and ledger.**
  - `git worktree add ../AI-DND-k2-bolme-p4n -b task/game-py-bolme-p4-nets <P4BASE>`;
  - `git worktree add --detach ../AI-DND-k2-bolme-p4a <P4BASE>`;
  - `git worktree add --detach ../AI-DND-k2-bolme-p4o 2e576967dda2fbfdf6a47d22d9313fbc76c195f8`.
  - Bring the plan into `p4n`: `git checkout task/game-py-bolme-p4 -- docs/superpowers/plans/2026-11-20-game-py-bolme-plan-4.md docs/superpowers/plans/2026-11-20-game-py-bolme-plan-4-appendix.md docs/superpowers/plans/2026-11-20-game-py-bolme-plan-4-measure`.
  - Add one line to `docs/design/INDEX.md`. Create the ledger.
  - Copy Plan 3's `run-gatewait.sh` unchanged and write `run-foreignload.sh` (Global Constraints).
- [ ] **Step 3: Locks on `P4BASE`** (Plan 3 Task 0 Step 4 routine, run in `p4n`):
  - targeted runs `p4t0-base-off`/`-fon`, `ENGINE_SET` minus `test_engine_module_alias` (it does not exist yet) + `NEIGHBOURS`: `RESULT exit=0` twice;
  - with `SLOTPY` into `STORE`: `surface.py --write`, `patch_census.py --write --lock STORE/census-p4base.json --report STORE/census-p4base.md`, `wc -l game.py`, `move_check.py --comments-only` (gives `<C>`), `M4/classify_all.py WTROOT`.
  - Expected:
    - `cmp` equal with the committed locks;
    - `wc -l` equal to `size_budget.json`;
    - classify prints only `NOT_IN_LOCK game_parts/terminal.py: run ['save']` (appendix C; Task 2 adds it to the lock).
  - Any other difference: trace its commit, write a debt row, fix the lock in Task 4.
- [ ] **Step 4: The OLD tree runs.** `slot.sh 4 AI-DND-k2-bolme-p4o test p4t0-oldtree-off 1800 api.tests.bench_engine_turn`: `RESULT exit=0` and a `TURN_BENCH` line. If it does not run, STOP and tell Kadir: the cumulative rule cannot be checked (Ruling B).
- [ ] **Step 5: Detached-run smoke (Ruling E).**
  - Gate wait. Start `slot_gate.sh 4 AI-DND-k2-bolme-p4n p4t0-detach-off 3 4500 '^(test_engine_sources|test_engine_hash_parts)$'` with the `Start-Process` form.
  - Poll in foreground loops.
  - Expected: the `.out` file ends with `PAR_EXIT=0` and `modules=2`. Record the method that worked.
  - Run `run-foreignload.sh` once: `FOREIGN_CPU_PCT=<0..100>` and `NODE_PROCS=<n>`.
- [ ] **Step 6: Speed bases.**
  - Cumulative A/B: OLD `p4o`, NEW `p4a`, prefix `p4t0cum`. This is information only, not a stop; it is the split's cost before Plan 4.
  - Bench `p4t0bench-fon` on `p4a` (`gate_boot` first): recorded, not a limit.
  - `M4/hook_profile.py` on the `p4a` slot copy, to compare with appendix G.
- [ ] **Step 7: Debt bookkeeping** (rows keep 8 `|`):
  - **D-429.** `Ruling: the D-429 behaviour fix is not in Plan 4 — its code (`_coin_without_a_reading`, only caller `_front_step`) is turn code, Plan 5 scope (appendix C), and a behaviour change cannot ride in a move — if wrong: three flag-on routing gaps (no coin moves in any, per the row) stay open until after TM5`. Trigger → "Plan 5 TM5 sonrası, ayrı kırmızı-yeşil para işi (güçlü inceleme)".
  - **D-448.** Write the method lines: foreign-load line, wall clock, cumulative A/B. Trigger → "Plan 4 Görev 17 (sayılar)".
- [ ] **Step 8: Commit** `game.py split plan 4: plan, appendix and measure scripts; debt bookkeeping (D-429, D-448)`.

### Task 1: Speed — the character aliases without a Python-level hook (Ruling A)

**Review tier:** strong (Opus implementer, Opus review). This is session core: every engine read from a part passes through it, and every character alias reads and writes the default session's character (HP, so death).

**Files:**
- Modify: `ai-dnd/game.py` (`_GameModule` block only), `ai-dnd/api/tests/engine_split_locks/size_budget.json` (`files["game.py"]`), `surface.json` (only if `test_engine_surface` shows a change; explain each line)
- Create: `ai-dnd/api/tests/test_engine_module_alias.py`

**Interfaces:**
- **Consumes:**
  - `game._CHARACTER_GLOBALS` (22 names → character keys);
  - `game._DEFAULT_SESSION`, `game._ACTIVE_SESSION`, `game.create_session`;
  - the prototype `git show b4b1cd11 -- ai-dnd/game.py` (Plan 3 rehearsal, measured `ALTPROBE _GameModule 22 bad []`).
- **Ruling:** see Ruling A's spec §7 line: only the hook's form changes; the mechanism stays. The controller writes in `kadir-notes.md`: "Görev 1, tasarımda 'dokunulmaz' denen `_GameModule` mekanizmasının yalnız uygulama biçimini değiştirdi: karakter adları (`game.max_hp` gibi) yine varsayılan oturuma okunup yazılıyor, `python game.py` yolu aynı; yalnız her okumada çalışan yavaş kanca kalktı. Testler davranışın aynı kaldığını gösteriyor; yanlışsa tek commit geri alınır."
- **Produces:**
  - `type(game)` is `_GameModule`, with no `__getattribute__` or `__setattr__` in its `__dict__`;
  - one `property` per `_CHARACTER_GLOBALS` name, with getter and setter on `_DEFAULT_SESSION.character[<key>]`;
  - no new top-level name in `game.py` (loop names are deleted, as in the prototype).

- [ ] **Step 1: Measure the shapes on the Task 1 base** (`SLOTPY` script on the `p4n` slot copy). Print, for `character_name` and `current_hp`:
  - `patch.object(game, <name>, <v>)`: the value inside, whether `__exit__` raises (and which exception), and the value after;
  - `hasattr(game, <name>)`;
  - `<name> in dir(game)`;
  - `<name> in vars(game)` after `setattr`.

  Write the output in the ledger. These are the pins of Step 2: today's behaviour, whatever it is. Pin an exception by its class, not its message. A pin that changes under the property form is a behaviour change: fix the implementation (for example a deleter that raises the same class), never the pin.
- [ ] **Step 2: Write the tests** (new module; one `fixed_town` seed per test, `20261301`-`20261304`):

```python
def test_reading_an_engine_name_through_the_module_runs_no_python_code(self):   # red today: 300 hook calls
    # sys.setprofile collects co_qualname of every "call" event while reading game.roll_d20, game._session and
    # game.world_state 100 times each; assert the list is empty; also assertNotIn("__getattribute__", type(game).__dict__)
    # and assertNotIn("__setattr__", type(game).__dict__)
def test_every_character_alias_reads_and_writes_the_default_character(self):
    # for each name, key in game._CHARACTER_GLOBALS.items(): getattr(game, name) == _DEFAULT_SESSION.character[key];
    # setattr(game, name, sentinel) -> character[key] is sentinel; restore the character in place in finally
def test_the_aliases_stay_on_the_default_session_inside_another_session(self):
    # s = game.create_session(seed=13); s.character["name"] = "Baska"; with s active (game._ACTIVE_SESSION.set):
    # game.character_name == _DEFAULT_SESSION.character["name"] != "Baska"; game.current_hp = 7 changes only the default
def test_the_alias_shapes_tests_use_are_unchanged(self):
    # the Step 1 outcomes pinned as literals: patch.object inside/exit/after, hasattr, dir membership, vars membership
```

  Run `api.tests.test_engine_module_alias` + `ENGINE_SET` + `NEIGHBOURS` (labels `p4t1-red-off`, `p4t1-red-fon`). Expected: only the first test fails, with the hook's qualname in the list; the pins are green.
- [ ] **Step 3: Implement** the property form from the prototype. Do not change `_CHARACTER_GLOBALS`, the `__main__` guard or the `__class__` assignment. Update `size_budget.json`.
  - Run again (`p4t1-off`, `p4t1-fon`): `RESULT exit=0` twice. Also run `test_sessions test_startup` (they hold the alias assignments of appendix C; census `absent` sites), both flags, `RESULT exit=0`.
- [ ] **Step 4: Prove the cut and the unchanged mechanism.** `M4/hook_profile.py` on the new slot copy: `MODULE_CLASS _GameModule HOOK False`, `HOOK_CALLS_PER_TURN 0.0`. `SLOTPY outside_probe.py`: `PROBE ok`, including its `python game.py` dice turn (`__main__` path untouched). `SLOTPY routing_audit.py`: `clean` (N3). Add approval §22 row 9.
- [ ] **Step 5: Speed.**
  - Task A/B: OLD `p4a`, NEW `p4n`, prefix `p4t1`. Pass ≤ 1.10.
  - Cumulative A/B (binding): OLD `p4o`, NEW `p4n`, prefix `p4t1cum`. Above 1.10 → STOP, tell Kadir, no move task starts.
  - Record both ratios and the change against Task 0's `p4t0cum`.
- [ ] **Step 6: Commit** `game.py split plan 4: character aliases are class properties, no Python-level module hook (speed, Ruling A)`.

### Task 2: D-355 sensitivity over every engine file; D-440 R11 builtin re-export

**Review tier:** Opus implementer, Opus review (net scope). It touches `sensitive.json` (one hand-added name), and the review reads that edit as strong. Files are disjoint from Task 1's, so speed rule 1 applies.

**Files:**
- Modify: `ai-dnd/api/tests/test_engine_sensitivity.py`, `ai-dnd/api/tests/engine_split_locks/sensitive.json`, `ai-dnd/scripts/engine_split/routing_audit.py` (`_part_findings`), `ai-dnd/api/tests/test_engine_routing.py`

**Interfaces — Produces:**
- `sensitive.json["functions"]["run"] == ["save"]`, added by hand. It is never removed.
- R11 fires when a part reads `<mod>.<b>` for a patched builtin `<b>` and `<mod>`'s source binds `<b>` from builtins (`from builtins import <b>` or `<b> = builtins.<b>`).

- [ ] **Step 1: Tests.**

```python
def test_every_flagged_function_in_every_engine_file_is_in_the_lock_or_removed(self):   # red today: `run`
    # classify(game.py) and classify(each game_parts/*.py); every flagged name in lock["functions"] or lock["removed"]
def test_a_module_that_re_exports_a_builtin_is_r11(self):   # red today (D-440)
    # fixture: shim.py "from builtins import open"; part reads shim.open; census absent target "open" -> one R11 line
def test_a_modules_own_open_is_still_not_r11(self):         # guard: green today (b585dd96 behaviour)
```

  Run both modules + `ENGINE_SET` + `NEIGHBOURS` (`p4t2-red-off/-fon`). Expected: two reds as stated.
- [ ] **Step 2:** Add `run` by hand. If an existing test pins the lock's exact set, add `run` to it (approval §22: "iddia eklendi"). Implement R11. Run again (`p4t2-off/-fon`): `RESULT exit=0`. `routing_audit.py` on the tree: `clean`.
- [ ] **Step 3:** Rows: D-355 closed with the test name, plus "geçişli yarı: `writer_scan.py` (D-430), M12 her taşımada". D-440 closed.
- [ ] **Step 4: Commit** `game.py split plan 4: sensitivity lock covers every engine file; R11 sees a module that re-exports a builtin (D-355, D-440)`.

### Task 3: D-446 session readers in `touching_tests`; D-447 session-only inputs

**Review tier:** Opus implementer, Opus review (net scope). Files are disjoint from Tasks 1-2.

**Files:**
- Modify: `ai-dnd/scripts/engine_split/inventory.py` (`touching_tests`, `_units`), `ai-dnd/api/tests/test_engine_split_inventory.py`, `ai-dnd/api/tests/test_engine_parts_pilot.py` (Plan 3 `*_session_helpers_use_the_given_session` tests), `docs/agents/onay-listesi-20261115.md` §22

**Interfaces — Produces:**
- `touching_tests(root, names)` also lists a module that reads `<recv>.<name>` or calls `getattr(<recv>, "<name>")` for a name in `names`, where `<recv>` is:
  - a Name or Attribute whose last identifier contains `session` (case-insensitive), or
  - a Name bound in that module from a call ending in `create_session` or `GameSession`.
- The rule is conservative: more modules is safe.

- [ ] **Step 1: Tests:** `test_touching_tests_sees_a_session_attribute_read`, `test_touching_tests_sees_a_getattr_on_a_session`, `test_touching_tests_sees_a_created_session_under_another_name` (three fixtures; red today).
- [ ] **Step 2: D-447.**
  - Each Plan 3 session-helper case whose answer is the same in both sessions gets an input that only the given session has (Plan 3's `t16_kuyu`/`t14_square` pattern): `_npc_speech_is_claim_refusal`, `is_npc_historical_claim`, `_generic_no_change_response`, `_direct_npc_smalltalk_response`, `_inspection_findings`.
  - Red proof per case, pre-plant rule: plant `game._DEFAULT_SESSION` in place of `game._session()` in that helper. The new case goes red; the old one was green.
  - Approval §22: "iddia güçlendi".
- [ ] **Step 3:** Run the two modules + `ENGINE_SET` + `NEIGHBOURS` (`p4t3-off/-fon`): `RESULT exit=0`. Live proof: `SLOTPY inventory.py --touching` for `create_npc_from_ai` before and after. The after-list is a superset of the before-list and holds at least one module Plan 3 added by grep (Plan 3 ledger, Tasks 13-15); list the added modules.
- [ ] **Step 4:** D-446 and D-447 closed with test names. **Commit** `game.py split plan 4: touching_tests counts session readers; session-helper tests use inputs only the given session has (D-446, D-447)`.

### Task 4: Batch files, T5 movable test, adapter-aware identity check (D-349)

**Review tier:** Opus implementer, Opus review. The review checks the batch lists against measurement.

**Files:**
- Create: `ai-dnd/scripts/engine_split/batches/{combat-1,combat-2,combat-3,coin,save-1,save-2,schemas-schema,cr-s,places-s,intent-s,dialogue-s,lore-s,narration-s-1,narration-s-2,lwt-s}.txt`
  - Ruling: the batch `schemas` is filed as `schemas-schema.txt` — Plan 2's `schemas.txt` exists — if wrong: a rename.
- Modify: `ai-dnd/api/tests/test_engine_surface.py`, `docs/agents/onay-listesi-20261115.md` §22
- Regenerate: `docs/engine-split/inventory.json`, `docs/engine-split/patch-census.md` if Task 0 found a lock out of step

**Interfaces — Produces:**
- `_batches_are_movable(self, batches, sensitive_allowed=False)`. The T3/T4 tests call it unchanged. `test_t5_batches_are_movable` calls it with `True`.
  - Approval §22 row: "T5 için hassas ad izinli (spec T5, güçlü inceleme ve `move_check --tier strong`); T3/T4 aynı — gevşetme olabilir".
- `_assert_part_object(self, module, name, seen)`: the loop body of `test_every_re_export_is_the_parts_own_object`. When `game._narrative_context_adapter_installed` is true and `name` is one of `build_world_context`, `ask_dungeon_master`, `finalize_narration`, it takes the adapter closure's `original_build`/`original_ask`/`original_finalize` (`inspect.getclosurevars(seen).nonlocals`) and applies the same checks to it: `__wrapped__ is own`, `_session_bound`, module in `_PART_MODULES`.
  - Approval §22: "adaptör sarmalayıcısı, yakaladığı özgün nesne aynı denetimden geçerse kabul — sınır yeniden tanımlandı, gevşetme olabilir".

- [ ] **Step 1: Tests:**
  - `test_t5_batches_are_movable` (red: no batch files);
  - `test_the_identity_check_sees_through_the_narrative_adapter`. Install the real adapter on a fresh `types.ModuleType` holding three bound fakes made the way `_bind_session_engine` makes them, then run `_assert_part_object` on each. Red today: `AttributeError: __wrapped__` (D-349 false red).
  - Guard `test_the_identity_check_still_fails_a_wrong_original` (an adapter around another function → `AssertionError`).
- [ ] **Step 2: Measure on `P4BASE` with the slot Python** (appendix A steps 1-5 and 8, outputs to `STORE`): step 1 on a fresh `git archive 5ea18cc7 ai-dnd` copy with `M4/overrides-p4.json` (it makes `topic-map.json`), steps 2-5 and 8 against `WTROOT`. Compare with appendix C-F:
  - equal names, and lines within ±5 % per batch → "appendix holds";
  - otherwise measurement wins, with a `Ruling` per changed name;
  - a batch over 1 000 lines is re-cut with `batches4.py`;
  - a name inside a top-level `if`/`try` (D-363) is held.
- [ ] **Step 3:** Write the 15 batch files from `STORE/p4-batches.json`, in file order (`COIN_LEFT_BEHIND` last in `coin`).
  - Ruling: `COIN_LEFT_BEHIND` goes to `coin` — it is a one-line alias of `money_owner.COIN_LEFT_BEHIND` on D-378's money list, read by `test_economic_room` and `test_money_cards` — if wrong: one name in another part, no behaviour change.
  - Run `SLOTPY <M3>/writer_scan.py WTROOT/.. <batch>` once per batch and save each `HELD` name set as `STORE/writer-expected-<B>.txt` (exit 1 when the set is non-empty, by design). For each writer kind in it, record at least one existing test that drives that writer through a batch name in `STORE/writer-tests-<B>.txt`; the move task adds those tests to its M10 named list. Expected `missing=0` for all 15; record the `SUMMARY` lines.
- [ ] **Step 4: D-349 recheck.** With the `p4_checks.py` output, check each of Plan 3's carried items against the 139 names:
  - `builtins.eval/exec`, `__builtins__.open`, the two-step chain, `getattr(<module>, "uuid4")`, an assignment-bound function, the R8 static gap, a missing `__init__.py`, an import-time `game.X` in another module.
  - Measured on `bdeddf2a`: only `__import__("grounded_action")` inside `plan_living_world_turn`. It is an in-function import, not an engine name, and moves untouched.
  - Write the row line. The narrative-adapter item is now closed by Step 1 plus Task 14.
- [ ] **Step 5:** Run `api.tests.test_engine_surface` + `ENGINE_SET` + `NEIGHBOURS` (`p4t4-off/-fon`): `RESULT exit=0`. **Commit** `game.py split plan 4: T5 batch files from a fresh measurement, T5 movable test, identity check sees through the narrative adapter (D-349)`.

### Task 5: Rehearsal — the whole T5 move on a throwaway branch (refusals, imports, cumulative speed)

**Review tier:** none (Opus runner; nothing reaches a plan branch).

**Files:** none committed to a plan branch. Worktree `p4p`, branch `tmp/game-py-bolme-p4-prova`, from the Stage A tip. Local commits are allowed, one per batch.

- [ ] **Step 1: Move everything.**
  - Sync the slot from `p4p`.
  - First apply Task 9 Step 2's logger edit in `game.py` (local commit). Then, for the 15 batches in appendix D's order: M4, M5 (headers from `out/p4-batches.out`), the `_PART_MODULES` edits, and M7 per batch against that batch's parent commit (`CHANGED 0` expected; any other result is a tool gap, fixed red-first in Stage A).
  - Every `REFUSED` name and every header gap goes in the ledger as a hold.
- [ ] **Step 2: Static and outside checks.**
  - `routing_audit.py` → `clean`;
  - `outside_probe.py` → `PROBE ok` listing `coin`, `combat_flow`, `savefile`;
  - targeted `test_sessions test_startup test_narrative_director` + `NEIGHBOURS`, both flags.
- [ ] **Step 3: Speed.**
  - Cumulative A/B: OLD `p4o`, NEW `p4p`, prefix `p4t5cum`. Above 1.10 → STOP before Stage B (Ruling B), tell Kadir.
  - Plan A/B: OLD `p4n`, NEW `p4p`, prefix `p4t5`. Record it as the projection for M10b.
- [ ] **Step 4: Feed back.** Each finding becomes a hold or a red-first tool fix on `p4n` (commit `game.py split plan 4: holds found by the rehearsal`). Ledger line "prova: <n> red, <m> tutuldu, kümülatif <ratio>".

### Task 6: Gate G5a — Stage A review, PR A

**Review tier:** strong (whole-branch review on Opus). It reads Task 1's session core and Task 2's `sensitive.json` edit.

- [ ] **Step 1:** `git fetch origin`. If `origin/main` moved: merge it, rerun Tasks 1-4's modules + `ENGINE_SET` + `NEIGHBOURS` in both flags, and if `game.py` changed, repeat Task 4 Steps 2-3 and Task 1 Step 5's cumulative A/B. These reruns are binding: the same pass rules and stops apply.
- [ ] **Step 2: Whole-branch review** of `$(git merge-base origin/main HEAD)..HEAD`. One fix wave, red-first (Opus); scoped re-review (Opus). Remaining minors become debt rows.
- [ ] **Step 3: Checks without a suite:**
  - `outside_probe.py` → `PROBE ok`;
  - `python test_regression.py` → `Results: 30 passed, 0 failed out of 30`;
  - `routing_audit.py` → `clean`;
  - ruff once (`--select F821,F401,F811 --no-fix`), output in the ledger.
- [ ] **Step 4:** Recheck the free debt ids. Push and open PR A; the text holds Task 1's ratios, the rehearsal line and the closed rows. Run the CI rules. Ledger line "G5a geçti". Cut `p4m` from the Stage A tip: `git worktree add ../AI-DND-k2-bolme-p4m -b task/game-py-bolme-p4-moves task/game-py-bolme-p4-nets`.

---

# Stage B — T5 moves (worktree `AI-DND-k2-bolme-p4m`, PR B)

Each task is a pure move under the Move procedure. Every task is strong. Behaviour pins are captured on `BASE_SHA` and written as literals.

### Task 7: `combat_flow.py` — batches `combat-1` (30, 925), `combat-2` (24, 995), `combat-3` (7, 209) (spec T5.1)

**Review tier:** strong. Money/save/death/Undo: death state, death checkpoints, death saves, combat Undo. M12 expected sets come from Task 4.

**Files:**
- Create: `ai-dnd/game_parts/combat_flow.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.combat_flow"` in `combat-1`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`; in `combat-1`, `test_both_import_orders_work_in_a_fresh_interpreter` gains one `combat_flow` function in its expected output (§22 row 6)

**Batch notes:**
- Headers per appendix D. `combat-2` uses the M5 Ruling for `from api.core_resolution import (...)` without `resolve_saving_throw`.
- Prefixed: `uuid4`, `effect_lifecycle` and `resolve_saving_throw` become `game.<x>`.
- `PlayerCannotAct` is a class. It moves and is re-exported, and the staying `except` clauses must catch the same class.
- `end_combat` is named in `docs/engine-split/source-readers.md`: the test that reads its source must still find it (read the row; update the reader path only if it reads `game.py` text, with an approval row).
- `_restore_combat_death_checkpoint` reads `game.GameSession` (never moved).

- [ ] **Step 1: Tests for `combat-1`** (seeds `20261310`-`20261319`, one per test):
  - `test_combat_1_lives_in_the_part` (red).
  - `test_the_player_cannot_act_error_is_one_class`: `game.PlayerCannotAct` is the class caught by the staying handlers (graphify: "who catches PlayerCannotAct").
  - `test_a_patched_uuid4_reaches_moved_combat_code`: `patch.object(game, "uuid4", ...)` with a fixed value; `_apply_player_damage` (or `_migrate_legacy_combat_state` if simpler) records it.
  - `test_combat_session_helpers_use_the_given_session` for `ensure_death_state`, `ensure_combat_state`, `_apply_player_damage`, `_capture_combat_death_checkpoint`, `_restore_combat_death_checkpoint`, with an input that only the given session has (D-447).
  - `test_combat_death_checkpoint_round_trips_from_the_part` (Review Focus 2): with `fixed_town`, `s = game.create_session(seed=21)`; capture on `s`; damage `s` to 0 HP; restore; the character, death state and combat state equal the captured ones, and `game._DEFAULT_SESSION` is untouched.
- [ ] **Step 2:** M1-M10 for `combat-1`. M10 is a pattern run of about 320 touching modules plus the named modules: `test_death_system test_dilim4a_death_audit test_d113_death_checkpoint_format test_real_death test_death_bounded test_d145_species_rest_death test_combat_test_matrix test_sessions`. M11 `game.py split T5.1a: death state and damage helpers live in game_parts/combat_flow.py`.
- [ ] **Step 3: `combat-2`.**
  - Tests: `test_combat_2_lives_in_the_part` (red); add `resolve_enemy_attack`, `resolve_species_trait_action`, `_resolve_player_death_turn`, `_resolve_enemy_turns_until_player`, `_begin_combat_actor_turn` to the session test; `test_a_patched_resolve_saving_throw_reaches_the_moved_species_action` (census `import` target through `game.`).
  - M1-M10, with named modules adding `test_d234_combat_undo test_d140_undone_combat_log test_d211_undone_fight_answer test_d115_undone_fight_question test_lr00_p7_undo`. M11 `game.py split T5.1b: attacks, species actions and combat turns live in game_parts/combat_flow.py`.
- [ ] **Step 4: `combat-3`.** `test_combat_3_lives_in_the_part` (red); `test_combat_texts_answer_as_before` (`_death_save_line`, `_public_combatant_label`, two inputs each, pinned). M1-M10. M10b. M11 `game.py split T5.1c: combat narration and death closing live in game_parts/combat_flow.py`.

### Task 8: `coin.py` — batch `coin` (16, 218) (spec T5.2)

**Review tier:** strong. Money: shop proposal and creation, the purse alias. `test_coin_writers` must be unchanged and green.

**Files:**
- Create: `ai-dnd/game_parts/coin.py`
- Modify: `ai-dnd/game.py` (`_PART_MODULES` gains `"game_parts.coin"`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`; `test_both_import_orders_work_in_a_fresh_interpreter` gains one `coin` function (§22 row 6)

**Batch notes:**
- Header `import money_owner`, `import re`.
- The four `_SHOP_*` regex constants and `_SOMEONE_ELSES_PURSE` stay bare inside the part.
- `create_shop_from_proposal` is a census target.

- [ ] **Step 1: Tests** (seeds `20261320`-`20261329`, one per test):
  - `test_coin_lives_in_the_part` (red).
  - `test_the_coin_left_behind_alias_is_money_owners_object`: `game.COIN_LEFT_BEHIND is money_owner.COIN_LEFT_BEHIND`.
  - `test_a_patched_create_shop_from_proposal_reaches_its_staying_caller`: graphify "who calls create_shop_from_proposal".
  - `test_shop_requests_answer_as_before`: `_shop_economy_request`, `_explicit_campaign_shop_negative_request`, `_shop_presence_question`, with Turkish inputs, pinned.
- [ ] **Step 2:** M1-M10. M10 is a pattern run of about 294 touching modules plus the named money modules: `test_coin_writers test_money_cards test_economic_room test_money_path_repair test_d207_written_purse test_money_owner test_front_money test_dilim3d_money test_coin_never_works test_d096_dead_coin_card test_economic_undo test_shops`. `test_coin_writers` names its writers by `file:function` and none is in `game.py` (measured): it stays byte-unchanged and green. A coin writer found inside a moved name is a new writer in the part: hold it, `Ruling`, debt row. The K2 money-text tests are named too: `test_d5_money_text test_d142_false_purse_line`.
- [ ] **Step 3:** M10b. M11 `game.py split T5.2: shop and purse helpers live in game_parts/coin.py`. D-429 stays with its Task 0 Ruling (not in this move).

### Task 9: `savefile.py` — batches `save-1` (18, 862), `save-2` (`load_game`, 186) (spec T5.3)

**Review tier:** strong. Save, load and repair: Undo snapshots and old-format repair.

**Files:**
- Create: `ai-dnd/game_parts/savefile.py`
- Modify: `ai-dnd/game.py` (Step 2 logger edit; `_PART_MODULES` gains `"game_parts.savefile"`), `surface.json`, `size_budget.json`
- Test: `ai-dnd/api/tests/test_engine_parts_pilot.py`; `test_both_import_orders_work_in_a_fresh_interpreter` gains one `savefile` function (§22 row 6)

**Batch notes:**
- `save_game` reads `os` (census `import`): it becomes `game.os`.
- `_validate_save_payload` reads `game.INITIAL_WORLD_STATE`.
- Spec T5.3 logger edit: `move_block` refuses `__name__` (N3 rule 6) and `move_check` ignores `--manual` inside moved spans, so the edit cannot ride in the move. Step 2 changes `logging.getLogger(__name__)` to `logging.getLogger("game")` in both repair functions in `game.py`, as its own commit. It is behaviour-neutral: `game.py` re-imports itself as `game` when run as `__main__`, so `__name__` is always `"game"` in these functions. `save-1` is then a pure move.
- `logging` must be in the header if the part reads it.

- [ ] **Step 1: Pin first** (green on the Task 9 base, seeds `20261330`-`20261339`, one per test):
  - `test_the_save_repair_warnings_log_under_game`: `assertLogs("game", "WARNING")` around a load that triggers each repair (graphify: "test_dilim1_save_repair payload").
  - `test_save_round_trip_after_the_move` (Review Focus 3): `s = game.create_session(seed=31)`; `game.save_game(path, session=s)` into a temp dir; load; `serialize_game_state(session=loaded)` equals the saved payload.
  - `test_a_patched_os_reaches_the_moved_save_game`: with `patch.object(game, "os", wraps=os)`, one `save_game` call calls `game.os.fsync` once (the replace is pathlib's, not `os`).
  - `test_save_session_helpers_use_the_given_session` for `serialize_game_state`.
  - Run: green.
- [ ] **Step 2: Logger edit in `game.py` (red-green, own commit, strong review).** Edit both functions. Run the Step 1 pins + `ENGINE_SET` + `NEIGHBOURS`, both flags: green. Commit `game.py split T5.3 prep: save repair warnings name the game logger explicitly (spec T5.3)`.
- [ ] **Step 3: `save-1` (pure move).**
  - `test_save_1_lives_in_the_part` (red).
  - M1-M9 with `BASE_SHA` = the Step 2 commit; M7 `CHANGED 0` with only the `_PART_MODULES` pair.
  - Red proof after M4 (pre-plant rule): put `logging.getLogger(__name__)` back in `savefile.py`'s `_repair_dilim1_fields`; the logger pin goes red (`game_parts.savefile`); restore and check the sha256.
  - M10: 34 touching modules plus the named modules (count the list; ≤ 60 → `slot.sh`, otherwise a pattern run): `test_dilim1_save_repair test_dilim2_save_repair test_save_migration test_persistence test_persistence_idempotency test_d258_real_format3_save test_campaign_persistence test_lr00_p4_persistence test_journey_reload_continuation test_d110_undo_after_lost_ack test_d112_ironman_undo test_d162_undo_status_contract`, plus `STORE/writer-tests-save-1.txt`.
  - M11 `game.py split T5.3a: save validation, repair and writing live in game_parts/savefile.py (logger kept as game)`.
- [ ] **Step 4: `save-2`.** `test_save_2_lives_in_the_part` (red). M1-M10, same named modules. M10b. M11 `game.py split T5.3b: load_game lives in game_parts/savefile.py`.

### Task 10: Small sensitive leftovers — `schemas-schema` (52), `cr-s` (`perform_skill_check`, 22), `lore-s` (`_lore_entity_names`, 54) (spec T5.4)

**Review tier:** strong (Ruling under File Structure: one review, three commits).

- [ ] **Step 1: `schemas-schema`.**
  - `test_the_npc_speech_schema_lives_in_schemas` (red); `test_the_npc_speech_schema_did_not_change` (`value_digest(("_EXPERIMENTAL_NPC_SPEECH_SCHEMA",))` pinned).
  - M1-M10 (named: the `--touching` output for `parse_player_intent` plus the schema). Data only: not in `_PART_MODULES`.
  - M11 `game.py split T5.4a: NPC speech schema lives in game_parts/schemas.py`.
- [ ] **Step 2: `cr-s`.**
  - `test_perform_skill_check_lives_in_character_rules` (red).
  - `test_character_rules_session_helpers_use_the_given_session` gains `perform_skill_check`, with an input only `s` has.
  - `test_a_patched_perform_skill_check_reaches_its_staying_caller` (24 patch sites; graphify "who calls perform_skill_check").
  - M1-M10 (named `test_roadmap_c10_rage test_roadmap_c06_barbarian_level4`). M11 `game.py split T5.4b: perform_skill_check lives in game_parts/character_rules.py`.
- [ ] **Step 3: `lore-s`.** `test_lore_entity_names_lives_in_lore` (red); `test_lore_entity_names_answer_as_before` (pinned). M1-M10 (0 touching: `ENGINE_SET` + `NEIGHBOURS`). M10b. M11 `game.py split T5.4c: _lore_entity_names lives in game_parts/lore.py`.

### Task 11: `places.py` — batch `places-s` (10, 342) (spec T5.4)

**Review tier:** strong. Purse via `create_npc_from_ai` → `give_person_purse`; travel death and supply paths; quest gold.

- [ ] **Step 1: Tests** (seeds `20261340`-`20261349`, one per test):
  - `test_places_s_lives_in_the_part` (red).
  - `test_places_session_helpers_use_the_given_session` gains `commit_location_change`, `create_npc_from_ai`.
  - `test_a_created_npc_gets_its_written_purse_from_the_part`: the `test_d207_written_purse` shape, called through `game.create_npc_from_ai(..., session=s)`; the purse is in `s.world_state["currency"]` only.
  - `test_grounded_action_still_reaches_create_npc_from_ai`: `grounded_action.py` calls it with `session=` in production; `patch.object(game, "create_npc_from_ai", wraps=...)` sees the call.
- [ ] **Step 2:** M1-M10 (named `test_economic_room test_d207_written_purse test_persistence_idempotency test_scene_transaction_contract test_table_absence_trigger`; the travel-death, supply and quest-gold writers `test_exploration_boundaries test_roadmap_k04 test_local_place_travel test_quest_reward_units test_quest_delivery`; plus `STORE/writer-tests-places-s.txt`). M10b. M11 `game.py split T5.4d: NPC creation, location commit and travel replies live in game_parts/places.py`.

### Task 12: `intent.py` — batch `intent-s` (6, 635) (spec T5.4)

**Review tier:** strong. `execute_intent` holds runtime snapshot and restore (Undo); `parse_player_intent` calls the model (`ollama` → `game.ollama`).

- [ ] **Step 1: Tests** (seeds `20261350`-`20261359`, one per test):
  - `test_intent_s_lives_in_the_part` (red).
  - `test_intent_session_helpers_use_the_given_session` gains `execute_intent`.
  - `test_a_rebound_execute_intent_reaches_its_moved_caller` (Review Focus 5): `patch.object(game, "execute_intent", side_effect=record)`, then `game.update_world_state_from_player(...)` with the shape `test_shops.py` uses; `record` sees one call.
  - `test_a_patched_ollama_reaches_the_moved_parse`: `patch.object(game, "ollama")` whose `chat` returns a fixed intent JSON; `parse_player_intent` returns it parsed.
- [ ] **Step 2:** M1-M10 (pattern run of about 326 modules; named `test_shops test_lr00_p1_intent test_sessions test_combat_lifecycle test_lr00_grounded_human`; the Undo tests `test_lr00_p7_undo test_d110_undo_after_lost_ack test_economic_undo test_undo_names_turn`; plus `STORE/writer-tests-intent-s.txt`. Task 4's writer-tests file names at least one Undo test that reaches `execute_intent`; the reviewer confirms it). M10b. M11 `game.py split T5.4e: intent parsing and execution live in game_parts/intent.py`.

### Task 13: `dialogue.py` — batch `dialogue-s` (8, 218) (spec T5.4)

**Review tier:** strong. NPC coin through `economic_actions.npc_gift`; spoken commitments; backed-money checks.

- [ ] **Step 1: Tests** (seeds `20261360`-`20261369`, one per test):
  - `test_dialogue_s_lives_in_the_part` (red).
  - `test_dialogue_session_helpers_use_the_given_session` gains `_experimental_speech_note`.
  - `test_coin_persuasion_answers_as_before`: two inputs, pinned.
  - The `test_talk_mode_writers` file-set pin is checked: if a moved name passes a people list to `current`, the pin gains nothing new (measure). Any change gets an approval row.
- [ ] **Step 2:** M1-M10 (named `test_money_path_repair test_economic_dialogue test_economic_spoken_consent test_heard_rumours_turn test_coin_ask_persuasion test_d097_coin_to_the_one_talked_to test_talk_mode_writers test_dialogue_commitments test_d5_money_text`, plus `STORE/writer-tests-dialogue-s.txt`). M10b. M11 `game.py split T5.4f: coin talk and spoken commitments live in game_parts/dialogue.py`.

### Task 14: `narration.py` — batches `narration-s-1` (8, 585), `narration-s-2` (6, 954) (spec T5.4)

**Review tier:** strong. Money in narration (`_narrated_money_can_lie`, `_narrator_shop_record`), world updates, and the model call. These are the narrative-adapter targets.

- [ ] **Step 1: `narration-s-1`.**
  - `test_narration_s_1_lives_in_the_part` (red).
  - `test_narration_session_helpers_use_the_given_session` gains `build_world_context`.
  - `test_world_updates_validate_as_before`: `validate_world_updates` on two update dicts from existing tests, pinned.
  - M1-M10 (pattern run; named `test_narrative_director test_campaign_time test_phase7_package`). M11 `game.py split T5.4g: world updates and context building live in game_parts/narration.py`.
- [ ] **Step 2: `narration-s-2`.** Tests:

```python
def test_narration_s_2_lives_in_the_part(self):                    # red
def test_the_narrative_adapter_reaches_the_moved_ask(self):          # Review Focus 5
    # install_narrative_context_adapter(game) (permanent; test_narrative_director does the same in-process).
    # Inside the director's turn frame (the context manager test_narrative_director uses; graphify "narrative_director
    # active turn frame"), call game.ask_dungeon_master with the offline model: the frame's diagnostics are set
    # (the build wrapper ran, reached through game.build_world_context from the part) and finalize ran once
    # (patch the adapter's captured original_finalize via wraps and count).
def test_a_patched_ollama_reaches_the_moved_ask(self):
```

  - Add `finalize_narration`, `ask_dungeon_master` to the session test.
  - M1-M10 (named as Step 1, plus `test_narrative_rebalance test_playable_living_world test_ai_pipeline_port` and the K2 money-text tests `test_d5_money_text test_d142_false_purse_line test_dialogue_commitments`, plus `STORE/writer-tests-narration-s-<1|2>.txt`).
  - M10b. M11 `game.py split T5.4h: the model call and narration finalizing live in game_parts/narration.py`.

### Task 15: `living_world_turn.py` — batch `lwt-s` (2, 813) (spec T5.4/T5.5)

**Review tier:** strong. `advance_campaign_time` reaches supply days (`condition_death`), healing and death turns.

- [ ] **Step 1: Tests** (seeds `20261370`-`20261379`, one per test):
  - `test_lwt_s_lives_in_the_part` (red).
  - `test_a_patched_uuid4_reaches_the_moved_clock` (Plan 3 handed this to Plan 4).
  - `test_living_world_session_helpers_use_the_given_session` gains `advance_campaign_time`, with an input only `s` has.
  - `test_the_rule_order_is_read_from_game`: `patch.object(game, "RULE_ORDER", ...)` reaches `advance_campaign_time`, or measure and pin what is true.
- [ ] **Step 2:** M1-M10 (named `test_economic_undo test_economic_dialogue test_death_bounded test_campaign_time test_campaign_time_edges`). M10b. M11 `game.py split T5.5: campaign time and the living-world planner live in game_parts/living_world_turn.py`.
- [ ] **Step 3:** Ledger:
  - line counts of `game.py` and every part (all ≤ 2 500);
  - the held table (if any);
  - the D-378 names moved;
  - the 15 Plan 3 holds, each with its move commit.

### Task 16: The net's exam on the moved tree

**Review tier:** none (Opus runner; nothing committed). Worktree `p4x` from the Stage B tip.

Routine: apply one fault alone, run the named check, see the stated red, `git checkout HEAD -- ai-dnd`, then the next fault.

- [ ] **Fault 1 — a part binds a patched name.** `combat_flow.py` gains `from uuid import uuid4` and `_apply_player_damage` calls bare `uuid4()`. Expected red: `test_engine_routing` (R3).
- [ ] **Fault 2 — missing `_PART_MODULES` entry.** Remove `"game_parts.coin"`. Expected red: `test_every_re_export_is_the_parts_own_object`, R2.
- [ ] **Fault 3 — checkpoint on the wrong session.** `_restore_combat_death_checkpoint` reads `game._DEFAULT_SESSION`. Expected red: `test_combat_death_checkpoint_round_trips_from_the_part`.
- [ ] **Fault 4 — frozen adapter alias.** In `narration.py`, add `_BUILD = build_world_context` right after that def (a same-part bare capture; import still works), and `ask_dungeon_master` calls `_BUILD(...)` in place of `game.build_world_context(...)`. Expected red: R9 and `test_the_narrative_adapter_reaches_the_moved_ask`.
- [ ] **Fault 5 — logger name lost.** Put `logging.getLogger(__name__)` back in `savefile.py`'s `_repair_dilim2_fields`. Expected red: `test_the_save_repair_warnings_log_under_game`.
- [ ] **Fault 6 — session dropped.** `execute_intent` reads `game._DEFAULT_SESSION` where it read `game._session()`. Expected red: `test_intent_session_helpers_use_the_given_session`.
- [ ] **Fault 7 — the hook comes back.** Restore the old `_GameModule.__getattribute__`. Expected red: `test_reading_an_engine_name_through_the_module_runs_no_python_code`.
- [ ] **Fault 8 — sensitive name hidden in a part.** Add a function writing `world["currency"]` to `coin.py` that is not in `sensitive.json`. Expected red: Task 2's whole-file-set test.
- [ ] **Final step:** `p4x` restored and clean, `p4m` untouched; `ENGINE_SET` + `NEIGHBOURS` green in both flags. A fault that stayed green stops the plan before the gate: fix the check red-first, then repeat the exam.

### Task 17: Gate TM4 (spec TM4), PR B

**Review tier:** strong. This is the whole-branch review on Opus:
- the Stage B diff;
- the money, save, death and Undo tests named in Tasks 7-15;
- M7 for all 15 batches, each against its move commit's parent;
- `writer_scan.py` on the gate tree with all 15 batch files: `missing=0`, `HELD` sets equal to the `writer-expected` files exactly, exit 1 by design.

- [ ] **Step 1:** `git fetch origin`; merge `origin/main` if it moved (`MAIN_SHA`). If `game.py` or a part changed underneath: rerun M7 for every batch against a fresh base and regenerate the locks.
- [ ] **Step 2: Whole-branch review before the suites.** One fix wave, red-first (Opus); scoped re-review (Opus). From Step 3 on, only the ledger, debt rows and PR text change; any change to code, tests or locks reruns Steps 3-6.
- [ ] **Step 3: N4/N7 bases.**
  - Ruling (Plan 3 Task 0 Ruling (a) carried; spec §6 says the N7 base is measured at TM0): the N4/N7 bases are taken here, on the Stage A tip merged with the gate's `MAIN_SHA`, in a detached worktree — this keeps full suites only at the gate and gives a like-for-like base — if wrong: a pre-existing flag-on red shows only here; it is traced and handled by the `F_fon` rule.
  - `git worktree add --detach ../AI-DND-k2-bolme-p4b <Stage A tip>`; in it, `git merge --no-ff --no-edit <MAIN_SHA>` (local, never pushed).
  - Check: `git diff <p4b HEAD> <Stage B tip> --stat -- . ':!ai-dnd/game.py' ':!ai-dnd/game_parts'` lists only Stage B's own tests, locks and docs.
  - Check: `git diff --quiet <P4BASE> <Stage B tip> -- <every money, save, death and Undo test named in Tasks 7-15>`: RC 0. `test_engine_parts_pilot.py` is the one expected change and is not in that list.
  - Four suites, one at a time, each after the gate wait, the foreign-load check and an empty `pgrep -af slot_gate`, `WT` = `p4b`: `p4g0-off-n4-n7-b`, `p4g0-off-n4-n7-c`, `p4g0-fon-n4-n7-b`, `p4g0-fon-n4-n7-c`. Started detached (Ruling E).
  - Ruling: at most two suites per agent — about 50 min each plus the waits stays under 150 minutes — if wrong: an agent hands over mid-wait with the label and `.out` path.
  - Pass and probe completeness as Plan 3 Task 17 Step 3: every shard has a ledger and line files; `selectors` start with `gate_boot`; the fon token reads `ok` in the fon ledgers and `skip` in the off ledgers.
- [ ] **Step 4: Gate suites** on `p4m`: `p4tm4-off-n4-n7`, then `p4tm4-fon-n4-n7`. Pass: `PAR_EXIT=0` and `failing_ids 0`. An unseeded red follows Plan 3's 40-fixed-town-seed procedure; any other red stops the plan.
- [ ] **Step 5: N4 and N7 per flag.**
  - `ledger_diff.py --diff --base <b> --base2 <c> --new <tm4>`: `DROPS 0`, `LOST 0`, `SUBLOST 0`, `SUBGONE 0`, `SUBCRASH 0`.
  - `coverage_by_function.py --diff`: `DOWN 0` outside the noise set (spec §6: equality is due at TM4). Every `UP` name is explained in the ledger.
  - Any drop, lost test or `DOWN` stops the plan.
- [ ] **Step 6: Speed (Rulings B, C).**
  - Suites by wall clock against the Ruling C limits. Record the longest-shard ratio as information.
  - Cumulative A/B: OLD `p4o`, NEW `p4m`, prefix `p4t17cum`. Pass ≤ 1.10; above it, STOP.
  - One flag-on reading `p4tm4bench-fon`: recorded only.
  - Every number in the ledger with its load line.
- [ ] **Step 7: Checks without a suite.**
  - `outside_probe.py` → `PROBE ok parts=` including `coin`, `combat_flow`, `savefile`.
  - `test_regression.py` → 30/30.
  - `move_check.py --comments-only` against the `P4BASE` archive → `COMMENTS base=<C> now=<C>`.
  - `routing_audit.py` → `clean`.
  - `M4/classify_all.py` → only names that are in the lock.
  - ruff once.
  - Both import orders with the `start_local.ps1` interpreter: rc 0.
  - Sizes: `game.py` = `size_budget.json`; every part ≤ 2 500.
  - **Zero-tolerance journeys (Ruling D):** a targeted run of `NEIGHBOURS` alone in both flags (`p4tm4-journeys-off/-fon`): `RESULT exit=0`, with the journey count pasted.
- [ ] **Step 8: Debt rows.**
  - D-378: Plan 4 names moved; `turn` remains for Plan 5.
  - D-430: closed (all 15 holds moved under the strong review, with M12 reading lists).
  - D-448: closed with this gate's numbers, or carried with them.
  - D-341, D-342, D-349 updated.
  - Every park gets a row; none is left without an owner.
- [ ] **Step 9:** Recheck the free debt ids. Push and open PR B, then merge PR A and PR B in order, with the ancestor check before each merge and the CI rules after each.
- [ ] **Step 10:**
  - Check for open `bash`/`sleep` processes and the `p4b`/`p4p`/`p4x` slots' runs.
  - Write the five-line Turkish morning summary.
  - Ledger lines: "TM4 geçti", "oynayış ertelendi (Kadir 2026-11-20)", "Plan 4 bitti; Plan 5 (T6) yazılabilir".
  - Worktrees are not deleted.

---

## Approval list §22 rows (the executor adds them to `docs/agents/onay-listesi-20261115.md` with the task that makes the change)

| # | Test or rule | Change | Mark |
|---|---|---|---|
| 1 | Speed rule (Tasks 0, 1, 5, 17) | cumulative A/B against `TM0BASE` `2e576967` at each binding point, ≤ 1.10 | sıkılaştırma, gevşetme değil |
| 2 | `test_engine_sensitivity` | classifies every engine file; `run` added by hand | iddia genişledi |
| 3 | Plan 3 session-helper tests | inputs only the given session has (D-447) | iddia güçlendi |
| 4 | `_batches_are_movable` | `sensitive_allowed=True` for T5 only (spec T5; strong review, `--tier strong`) | gevşetme olabilir |
| 5 | `test_every_re_export_is_the_parts_own_object` | the adapter wrapper is accepted when its captured original passes the same check | gevşetme olabilir (sınır yeniden tanımlandı) |
| 6 | `test_both_import_orders_work_in_a_fresh_interpreter` | expected output gains one function each from `combat_flow`, `coin`, `savefile` (Task 7, 8, 9 as each part arrives) | iddia eklendi |
| 7 | Shard timeout 4 500 s, wall clock | carried from Plan 3 (D-448, already marked) | taşındı |
| 8 | M12 writer scan | `held=0` becomes: the HELD set equals Task 4's recorded set exactly, and every path is read and covered by a named M10 test (spec T5 moves sensitive code) | gevşetme olabilir (sınır yeniden tanımlandı) |
| 9 | `_GameModule` (spec §7 "Dokunulmaz") | mekanizma aynı (sınıf değişimi yalnız `__name__ != "__main__"` iken, adlar varsayılan oturuma yansır); kanca yerine 22 sınıf özelliği (Task 1) | spec sapması: mekanizma aynı, yalnız uygulama biçimi değişir (güçlü inceleme) |

## Debt rows this plan owns (trigger names Plan 4, T5 or TM4) and what happens to each

| Row | Handling |
|---|---|
| D-355 N8 only on `game.py` | Task 2 (whole file set); transitive half via D-430 |
| D-430 15 Plan 3 holds, writer scan | Task 4 records expected reading lists; M12 every batch; Task 17 closes |
| D-349 N3 carried items, narrative adapter | Task 4 (adapter identity, recheck line); Task 14 adapter test; rest → Plan 5 Görev 0 |
| D-440 R11 builtin re-export | Task 2 |
| D-446 `touching_tests` session readers | Task 3 |
| D-447 session tests with equal answers | Task 3 |
| D-448 load-sensitive speed | Task 0 (method), Task 17 (numbers) |
| D-378 held names | Tasks 7-15 move them; Task 17 updates the row |
| D-429 coin decision without a reading | Ruling (Task 0): trigger → after TM5 (turn code, Plan 5) |
| D-341, D-342 probes | Task 6 Step 3, Task 17 Step 7 |
| D-363 top-level `if`/`try` | Task 4 Step 2 recheck; carried |

Carried unchanged: D-343 (T7), D-344/D-345 (Plan 5), D-351, D-379 and D-380(3) (Plan 6), D-356-D-358, D-362, D-365.

---

## Plans 5-6 outline

**Plan 5 — T6 turn core, to spec TM5.**
- **Scope:** `turn`, 38 names / 815 lines plus 32 sensitive / 5 417 (appendix C; `_run_player_turn_internal`, `_front_step`, `_coin_without_a_reading`). `turn.py` is frozen at arrival size. D-344, D-345.
- **Entry:** TM4 passed. The cumulative A/B ratio at TM4 is the start value.
- **Strong review:** all of it. The D-429 fix comes after TM5 as its own red-green money task.
- **Handed over:** M10b deltas per Plan 4 task; the hook-free `_GameModule`; the session-only test pattern; the M12 reading-list rule.

**Plan 6 — T7 closure.**
- **Scope:** final sizes (`game.py` ≤ 1 500); dead-code candidates with both-flag N7 evidence; D-343, D-379, D-351, D-380(3); dev-only tools; Kadir's closing play (Ruling D ends here).
- **Strong review:** any deletion; the closing whole-branch review.

---

## Self-review

1. **Spec coverage.**
   - T5.1 → Task 7 (death/Undo tests named).
   - T5.2 → Task 8 (`test_coin_writers` unchanged; money and K2 tests named).
   - T5.3 → Task 9 (logger pin first, then the hand edit; save round-trip).
   - T5.4-5 → Tasks 10-15 (zero-tolerance journeys in every run and in Task 17 Step 7).
   - TM4 → Task 17 (suites ×2 per flag with bases, N4, N7 equality, time and bench, PR).
   - §7 speed stop → Tasks 1, 5, M10b, 17. §11 sizes → Tasks 15 and 17. §12 freeze → Global Constraints.
2. **Controller rulings:**
   - A → Task 1 before any move;
   - B → Tasks 0, 1, 5, 17 and §22 row 1;
   - C → Global Constraints and Task 17 Step 6;
   - D → Task 17 Steps 7 and 10;
   - E → Global Constraints and Task 0 Step 5;
   - F → Global Constraints;
   - G → the two stages.
3. **Step scan.** Every move task names its batches, tests, seeds, named M10 modules and commit messages. Test bodies that depend on existing tests name the graphify query that finds them.
4. **Name consistency.**
   - Batch names match appendix D and Task 4's files (`schemas` is filed as `schemas-schema.txt`, Ruling).
   - Labels follow `p4t<N>-<B>-<off|fon>`; no batch name contains `fon`.
   - Review Focus test names match Tasks 1, 4, 7, 9, 12 and 14.
   - `_PART_MODULES` gains `combat_flow`, `coin`, `savefile`.
5. **Proportion.**
   - 18 tasks: Stage A 7, Stage B 11.
   - Strong: Tasks 1, 6, 7-15, 17. Opus net review: Tasks 2-4. Runner only: Tasks 0, 5, 16.
   - Full suites: 6, all in Task 17.
   - A/B series: Task 0, Task 1 (×2), Task 5 (×2), Task 17, plus 9 M10b runs; each is 12 bench runs of about 2 min.
6. **Loosening check.**
   - No Ruling loosens a controller or CLAUDE.md rule.
   - Three boundary rows are marked "gevşetme olabilir" as CLAUDE.md requires: §22 rows 4 (required by spec T5), 5 (the adapter-aware identity check) and 8 (M12 reading list). Row 9 records the controller-approved spec §7 implementation change.
   - The 4 500 s timeout and wall clock are carried from Plan 3 (row 7).

## Execution

Subagent-driven. Speed rule 1 applies only among Stage A Tasks 2-4 and Task 1's review. Stage B runs strictly in order. The controller holds the ledger, the gate waits, the labels and the A/B series. Implementers get the Move procedure (Plan 3's text plus the deltas above) word for word and their task text.
